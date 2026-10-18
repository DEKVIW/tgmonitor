from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_db, get_optional_current_user
from app.models.models import MessageLinkRef, engine
from app.schemas.message import MessageListResponse, MessageResponse, TagStatsResponse
from app.services.message_query_service import (
    get_filtered_messages,
    get_message_by_id,
    get_tag_stats,
)
from app.services.resource_ops import (
    build_tracked_link_payloads,
)
from app.services.foreground_link_health_service import (
    FOREGROUND_LINK_HEALTH,
)
from app.services.security_service import SEARCH_CLEARANCE_HEADER, ensure_search_challenge_clearance
from app.services.system_config_service import is_public_dashboard_enabled


router = APIRouter(prefix="/api/messages", tags=["messages"])
logger = logging.getLogger(__name__)
_UNSET = object()

PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES = frozenset({"最近1小时", "最近24小时", "最近7天"})
PUBLIC_DASHBOARD_MAX_AGE_DAYS = 7
_FOREGROUND_CHECK_CONCURRENCY = 2
_FOREGROUND_CHECK_SEMAPHORE = asyncio.Semaphore(_FOREGROUND_CHECK_CONCURRENCY)


def _record_foreground_link_health_observations(observations: List[Dict[str, Any]]) -> None:
    with Session(engine) as observation_db:
        FOREGROUND_LINK_HEALTH.record_observations(observation_db, observations)


async def _run_foreground_link_health_check(messages: List[Any]) -> None:
    async with _FOREGROUND_CHECK_SEMAPHORE:
        try:
            foreground_check = await FOREGROUND_LINK_HEALTH.check_messages(messages)
            if not foreground_check.network_observations:
                return

            await asyncio.to_thread(
                _record_foreground_link_health_observations,
                foreground_check.network_observations,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("background foreground link health check failed")


def _is_public_guest(current_user: Optional[Dict[str, Any]]) -> bool:
    return current_user is None and is_public_dashboard_enabled()


def _ensure_public_access_allowed(current_user: Optional[Dict[str, Any]], detail: str) -> None:
    if current_user is None and not is_public_dashboard_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_public_dashboard_cutoff() -> datetime:
    return datetime.now() - timedelta(days=PUBLIC_DASHBOARD_MAX_AGE_DAYS)


def _enforce_public_dashboard_time_range(time_range: str) -> None:
    if time_range not in PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="公开页面仅支持查看近 7 天内的数据",
        )


def _build_message_response(
    message: Any,
    tracked_links: Optional[List[Dict[str, Any]]] = None,
    *,
    links: Any = _UNSET,
    netdisk_types: Any = _UNSET,
) -> MessageResponse:
    return MessageResponse(
        id=int(message.id),
        timestamp=message.timestamp,
        title=message.title,
        description=message.description,
        links=message.links if links is _UNSET else links,
        tracked_links=tracked_links or None,
        tags=message.tags,
        source=message.source,
        channel=message.channel,
        group_name=message.group_name,
        bot=message.bot,
        created_at=message.created_at,
        netdisk_types=message.netdisk_types if netdisk_types is _UNSET else netdisk_types,
    )


def _load_tracked_links_for_message_ids(
    db: Session,
    *,
    message_ids: list[int],
) -> Dict[int, List[Dict[str, Any]]]:
    normalized_message_ids = sorted({int(message_id) for message_id in message_ids if int(message_id) > 0})
    if not normalized_message_ids:
        return {}

    refs = (
        db.query(MessageLinkRef)
        .filter(MessageLinkRef.message_id.in_(normalized_message_ids))
        .order_by(MessageLinkRef.message_id.asc(), MessageLinkRef.link_index.asc())
        .all()
    )
    refs_by_message: Dict[int, List[MessageLinkRef]] = {}
    for ref in refs:
        refs_by_message.setdefault(int(ref.message_id), []).append(ref)

    return {
        message_id: build_tracked_link_payloads(message_refs)
        for message_id, message_refs in refs_by_message.items()
    }


@router.get("", response_model=MessageListResponse, summary="获取消息列表")
def get_messages(
    request: Request,
    background_tasks: BackgroundTasks,
    sort_mode: Literal["relevance", "newest"] = Query("newest", description="search result sort mode"),
    search_query: Optional[str] = Query(None, description="搜索关键词（支持多关键词，空格分隔）"),
    time_range: str = Query("最近24小时", description="时间范围"),
    selected_tags: Optional[List[str]] = Query(None, description="选中的标签列表"),
    selected_netdisks: Optional[List[str]] = Query(None, description="选中的网盘类型列表"),
    min_content_length: int = Query(0, description="最小内容长度"),
    has_links_only: bool = Query(False, description="是否只显示有链接的消息"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(100, ge=1, le=200, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> MessageListResponse:
    _ensure_public_access_allowed(current_user, "需要登录后才能访问消息列表")

    if _is_public_guest(current_user):
        _enforce_public_dashboard_time_range(time_range)

    try:
        ensure_search_challenge_clearance(
            search_query,
            current_user,
            clearance_token=request.headers.get(SEARCH_CLEARANCE_HEADER) if request else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    try:
        messages, total, max_page = get_filtered_messages(
            db=db,
            search_query=search_query,
            sort_mode=sort_mode,
            time_range=time_range,
            selected_tags=selected_tags or [],
            selected_netdisks=selected_netdisks or [],
            min_content_length=min_content_length,
            has_links_only=has_links_only,
            page=page,
            page_size=page_size,
        )

        tracked_by_message = _load_tracked_links_for_message_ids(
            db,
            message_ids=[int(message.id) for message in messages if getattr(message, "id", None) is not None],
        )

        if search_query and search_query.strip():
            background_tasks.add_task(_run_foreground_link_health_check, list(messages))
            db.close()

        visible_messages = []
        for message in messages:
            visible_messages.append(
                _build_message_response(
                    message,
                    tracked_by_message.get(int(message.id)),
                )
            )

        return MessageListResponse(
            messages=visible_messages,
            total=total,
            page=page,
            page_size=page_size,
            max_page=max_page,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取消息列表失败: {exc}",
        ) from exc


@router.get("/{message_id}", response_model=MessageResponse, summary="获取单条消息详情")
def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> MessageResponse:
    _ensure_public_access_allowed(current_user, "需要登录后才能访问消息详情")

    message = get_message_by_id(db, message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"消息 {message_id} 不存在",
        )

    if _is_public_guest(current_user) and message.timestamp < _get_public_dashboard_cutoff():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"消息 {message_id} 不存在",
        )

    tracked_links = _load_tracked_links_for_message_ids(
        db,
        message_ids=[int(message.id)],
    ).get(int(message.id))

    return _build_message_response(message, tracked_links)


@router.get("/tags/stats", response_model=List[TagStatsResponse], summary="获取标签统计")
def get_tags_stats(
    limit: int = Query(50, ge=1, le=100, description="返回的标签数量限制"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> List[TagStatsResponse]:
    _ensure_public_access_allowed(current_user, "需要登录后才能访问标签统计")

    try:
        tag_stats = get_tag_stats(
            db,
            limit=limit,
            since=_get_public_dashboard_cutoff() if _is_public_guest(current_user) else None,
        )
        return [TagStatsResponse(tag=tag, count=count) for tag, count in tag_stats]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取标签统计失败: {exc}",
        ) from exc
