from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime import get_admin_user, get_db
from app.models.models import Channel, ensure_channel_parser_profile_column
from app.schemas.admin_models import (
    ChannelSampleResponse,
    LinkCheckHistoryBatchDeleteRequest,
    LinkCheckHistoryBatchDeleteResult,
    LinkCheckDateRange,
    LinkCheckPlanResponse,
    LinkCheckPlanUpdate,
    LinkCheckPreviewRequest,
    LinkCheckPreviewResponse,
    LinkCheckHistoryDeleteResult,
    LinkCheckTaskStatus,
)
from app.services.channel_service import fetch_channel_message_samples
from app.services.link_check_plan_service import get_link_check_plan, update_link_check_plan
from app.services.link_check_selection_service import build_manual_selection_preview
from app.services.link_check_runtime import (
    delete_task_history_entries,
    delete_task_history_entry,
    get_active_task_snapshot,
    get_link_check_date_range,
    request_task_stop,
)
from app.services.system_config_service import get_link_check_runtime_config
from app.utils.channel_utils import normalize_channel_username


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/channels/{channel_id}/samples",
    response_model=ChannelSampleResponse,
    summary="获取频道样本",
)
async def get_channel_samples_api(
    channel_id: int,
    limit: Optional[int] = Query(None, ge=1, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    only_with_links: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> ChannelSampleResponse:
    del current_user

    try:
        ensure_channel_parser_profile_column()
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if channel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"频道 {channel_id} 不存在",
            )

        effective_page_size = int(limit or page_size)
        sample_data = await fetch_channel_message_samples(
            normalize_channel_username(channel.username),
            limit=effective_page_size,
            page=page,
            page_size=effective_page_size,
            only_with_links=only_with_links,
            parser_profile=getattr(channel, "parser_profile", None),
        )
        sample_data["channel_id"] = channel.id
        return ChannelSampleResponse(**sample_data)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取频道样本失败: {exc}",
        ) from exc


@router.get(
    "/link-check/date-range",
    response_model=LinkCheckDateRange,
    summary="获取链接检测日期范围",
)
async def get_link_check_date_range_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckDateRange:
    del current_user

    try:
        return LinkCheckDateRange(**get_link_check_date_range())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取链接检测日期范围失败: {exc}",
        ) from exc


@router.post(
    "/link-check/preview",
    response_model=LinkCheckPreviewResponse,
    summary="预估手动检测范围",
)
async def preview_link_check_task_api(
    request: LinkCheckPreviewRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckPreviewResponse:
    del current_user

    try:
        runtime_config = get_link_check_runtime_config()
        preview = build_manual_selection_preview(
            db,
            selection_mode=request.selection_mode,
            task_link_limit=int(runtime_config["link_check_max_allowed_links"]),
            range_start=request.range_start,
            range_end=request.range_end,
            target_link_count=request.target_link_count,
            direction=request.direction,
        )
        return LinkCheckPreviewResponse(**preview)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预估链接检测范围失败: {exc}",
        ) from exc


@router.get(
    "/link-check/plan",
    response_model=LinkCheckPlanResponse,
    summary="获取自动巡检计划",
)
async def get_link_check_plan_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckPlanResponse:
    del current_user

    try:
        return LinkCheckPlanResponse(**get_link_check_plan())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取自动巡检计划失败: {exc}",
        ) from exc


@router.put(
    "/link-check/plan",
    response_model=LinkCheckPlanResponse,
    summary="更新自动巡检计划",
)
async def update_link_check_plan_api(
    request: LinkCheckPlanUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckPlanResponse:
    try:
        return LinkCheckPlanResponse(**update_link_check_plan(request.model_dump(), updated_by=current_user.get("username")))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新自动巡检计划失败: {exc}",
        ) from exc


@router.get(
    "/link-check/active",
    response_model=LinkCheckTaskStatus,
    summary="获取当前活动任务",
)
async def get_active_link_check_task_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckTaskStatus:
    del current_user

    active_task = get_active_task_snapshot()
    if active_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前没有进行中的检测任务",
        )

    task_id, status_data = active_task
    return LinkCheckTaskStatus(task_id=task_id, **status_data)


@router.post(
    "/link-check/tasks/{task_id}/stop",
    response_model=LinkCheckTaskStatus,
    summary="停止链接检测任务",
)
async def stop_link_check_task_api(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckTaskStatus:
    del current_user

    status_data = request_task_stop(task_id)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在",
        )
    return LinkCheckTaskStatus(task_id=task_id, **status_data)


@router.delete(
    "/link-check/tasks/{check_time}/history",
    response_model=LinkCheckHistoryDeleteResult,
    summary="删除检测历史",
)
async def delete_link_check_history_api(
    check_time: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckHistoryDeleteResult:
    del current_user

    try:
        return LinkCheckHistoryDeleteResult(**delete_task_history_entry(check_time))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"检测时间格式无效: {exc}",
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除检测历史失败: {exc}",
        ) from exc


@router.post(
    "/link-check/history/delete",
    response_model=LinkCheckHistoryBatchDeleteResult,
    summary="批量删除检测历史",
)
async def delete_link_check_histories_api(
    request: LinkCheckHistoryBatchDeleteRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> LinkCheckHistoryBatchDeleteResult:
    del current_user

    try:
        return LinkCheckHistoryBatchDeleteResult(**delete_task_history_entries(request.check_times))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"检测时间格式无效: {exc}",
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除检测历史失败: {exc}",
        ) from exc
