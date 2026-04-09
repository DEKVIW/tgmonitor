from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_db, get_optional_current_user
from app.schemas.message import MessageListResponse, MessageResponse, TagStatsResponse
from app.services.message_query_service import (
    get_filtered_messages,
    get_message_by_id,
    get_tag_stats,
)
from app.services.resource_ops import (
    build_tracked_link_payloads,
    ensure_message_link_refs,
    ensure_message_link_refs_for_messages,
)
from app.services.security_service import SEARCH_CLEARANCE_HEADER, ensure_search_challenge_clearance
from app.services.system_config_service import is_public_dashboard_enabled


router = APIRouter(prefix="/api/messages", tags=["messages"])
logger = logging.getLogger(__name__)

PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES = frozenset({"最近1小时", "最近24小时", "最近7天"})
PUBLIC_DASHBOARD_MAX_AGE_DAYS = 7


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
) -> MessageResponse:
    return MessageResponse(
        id=int(message.id),
        timestamp=message.timestamp,
        title=message.title,
        description=message.description,
        links=message.links,
        tracked_links=tracked_links or None,
        tags=message.tags,
        source=message.source,
        channel=message.channel,
        group_name=message.group_name,
        bot=message.bot,
        created_at=message.created_at,
        netdisk_types=message.netdisk_types,
    )


@router.get("", response_model=MessageListResponse, summary="获取消息列表")
async def get_messages(
    request: Request,
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
            time_range=time_range,
            selected_tags=selected_tags or [],
            selected_netdisks=selected_netdisks or [],
            min_content_length=min_content_length,
            has_links_only=has_links_only,
            page=page,
            page_size=page_size,
        )

        tracked_by_message: Dict[int, List[Dict[str, Any]]] = {}
        try:
            refs_by_message, changed = ensure_message_link_refs_for_messages(db, messages)
            if changed:
                db.commit()
            tracked_by_message = {
                int(message_id): build_tracked_link_payloads(refs)
                for message_id, refs in refs_by_message.items()
            }
        except Exception:
            db.rollback()
            logger.exception("Failed to build tracked links for message list")

        return MessageListResponse(
            messages=[
                _build_message_response(message, tracked_by_message.get(int(message.id)))
                for message in messages
            ],
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
async def get_message(
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

    tracked_links: Optional[List[Dict[str, Any]]] = None
    try:
        refs, changed = ensure_message_link_refs(db, message)
        if changed:
            db.commit()
        tracked_links = build_tracked_link_payloads(refs)
    except Exception:
        db.rollback()
        logger.exception("Failed to build tracked links for message %s", message_id)

    return _build_message_response(message, tracked_links)


@router.get("/tags/stats", response_model=List[TagStatsResponse], summary="获取标签统计")
async def get_tags_stats(
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
