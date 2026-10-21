from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db, get_optional_current_user
from app.schemas.learning_resources import (
    LearningAdminOverviewResponse,
    LearningCategoryResponse,
    LearningChannelUpdateRequest,
    LearningChannelUpdateResponse,
    LearningDirectoryListResponse,
    LearningImportConfirmRequest,
    LearningImportConfirmResponse,
    LearningImportPreviewResponse,
    LearningAutomationLogListResponse,
    LearningAutomationRetryResponse,
    LearningAutomationTaskCreateRequest,
    LearningAutomationTaskDeleteResponse,
    LearningAutomationTaskListResponse,
    LearningAutomationTaskProcessRequest,
    LearningAutomationTaskProcessResponse,
    LearningAutomationTaskResponse,
    LearningAutomationTaskUpdateRequest,
    LearningAutomationReplayRequest,
    LearningResourceAdminListResponse,
    LearningResourceAdminResponse,
    LearningResourceDeleteResponse,
    LearningResourceListResponse,
    LearningResourceResponse,
    LearningResourceUpdateRequest,
    LearningResourceVisibilityRequest,
)
from app.services.learning_resources import (
    count_admin_learning_items,
    count_public_learning_resources,
    delete_all_imported_learning_resources,
    delete_learning_resource,
    update_learning_resource,
    list_admin_learning_items,
    list_learning_admin_overview,
    list_public_learning_categories,
    list_public_learning_resources,
    preview_learning_import,
    confirm_learning_import,
    retry_learning_resource,
    update_learning_channel_config,
)
from app.services.learning_automation import (
    get_learning_automation_task,
    delete_learning_automation_task,
    list_learning_automation_logs,
    list_learning_automation_tasks,
    process_learning_automation_task_now,
    retry_failed_learning_automation_jobs,
    save_learning_automation_task,
    set_learning_automation_task_enabled,
)
from app.services.pan_transfer import list_pan_transfer_directories
from app.services.system_config_service import is_public_dashboard_enabled
from app.models.models import LearningResourceItem, LearningResourceLink


router = APIRouter(tags=["learning-resources"])


def _ensure_public_access(current_user: dict[str, Any] | None) -> None:
    if current_user is None and not is_public_dashboard_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要开启游客公开页面后才能访问学习资料",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _operator(current_user: dict[str, Any]) -> str:
    return str(current_user.get("username") or current_user.get("name") or "admin")


@router.get(
    "/api/admin/learning-resources/automation-tasks",
    response_model=LearningAutomationTaskListResponse,
    summary="获取学习资料自动转存任务",
)
def get_learning_automation_tasks(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskListResponse:
    del current_user
    items = list_learning_automation_tasks(db)
    return LearningAutomationTaskListResponse(items=items, total=len(items))


@router.post(
    "/api/admin/learning-resources/automation-tasks",
    response_model=LearningAutomationTaskResponse,
    summary="创建学习资料自动转存任务",
)
def create_learning_automation_task(
    payload: LearningAutomationTaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskResponse:
    try:
        result = save_learning_automation_task(
            db,
            task_id=None,
            payload=payload.model_dump(),
            operator=_operator(current_user),
        )
        db.commit()
        return LearningAutomationTaskResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/api/admin/learning-resources/automation-tasks/{task_id}",
    response_model=LearningAutomationTaskResponse,
    summary="获取学习资料自动转存任务详情",
)
def get_learning_automation_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskResponse:
    del current_user
    result = get_learning_automation_task(db, task_id=int(task_id))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习资料自动任务不存在")
    return LearningAutomationTaskResponse(**result)


@router.patch(
    "/api/admin/learning-resources/automation-tasks/{task_id}",
    response_model=LearningAutomationTaskResponse,
    summary="编辑学习资料自动转存任务",
)
def update_learning_automation_task(
    task_id: int,
    payload: LearningAutomationTaskUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskResponse:
    try:
        result = save_learning_automation_task(
            db,
            task_id=int(task_id),
            payload=payload.model_dump(),
            operator=_operator(current_user),
        )
        db.commit()
        return LearningAutomationTaskResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/api/admin/learning-resources/automation-tasks/{task_id}",
    response_model=LearningAutomationTaskDeleteResponse,
    summary="删除学习资料自动转存任务",
)
def delete_learning_automation_task_api(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskDeleteResponse:
    del current_user
    try:
        result = delete_learning_automation_task(db, task_id=int(task_id))
        db.commit()
        return LearningAutomationTaskDeleteResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/automation-tasks/{task_id}/pause",
    response_model=LearningAutomationTaskResponse,
    summary="暂停学习资料自动转存任务",
)
def pause_learning_automation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskResponse:
    del current_user
    try:
        result = set_learning_automation_task_enabled(db, task_id=int(task_id), enabled=False)
        db.commit()
        return LearningAutomationTaskResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/automation-tasks/{task_id}/resume",
    response_model=LearningAutomationTaskResponse,
    summary="恢复学习资料自动转存任务",
)
def resume_learning_automation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskResponse:
    del current_user
    try:
        result = set_learning_automation_task_enabled(db, task_id=int(task_id), enabled=True)
        db.commit()
        return LearningAutomationTaskResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/automation-tasks/{task_id}/process-now",
    response_model=LearningAutomationTaskProcessResponse,
    summary="补处理学习资料遗漏消息",
)
def process_learning_automation_task(
    task_id: int,
    payload: LearningAutomationTaskProcessRequest | None = None,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskProcessResponse:
    try:
        result = process_learning_automation_task_now(
            db,
            task_id=int(task_id),
            message_ids=(payload.message_ids if payload else None),
            from_message_id=(payload.from_message_id if payload else None),
            to_message_id=(payload.to_message_id if payload else None),
            dry_run=bool(payload.dry_run) if payload else False,
            operator=_operator(current_user),
        )
        db.commit()
        return LearningAutomationTaskProcessResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/replay",
    response_model=LearningAutomationTaskProcessResponse,
    summary="按消息范围补处理学习资料",
)
def replay_learning_resources(
    payload: LearningAutomationReplayRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationTaskProcessResponse:
    try:
        result = process_learning_automation_task_now(
            db,
            task_id=int(payload.task_id),
            message_ids=payload.message_ids,
            from_message_id=payload.from_message_id,
            to_message_id=payload.to_message_id,
            dry_run=bool(payload.dry_run),
            operator=_operator(current_user),
        )
        db.commit()
        return LearningAutomationTaskProcessResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/automation-tasks/{task_id}/retry-failed",
    response_model=LearningAutomationRetryResponse,
    summary="重试学习资料自动转存失败任务",
)
def retry_learning_automation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationRetryResponse:
    del current_user
    try:
        result = retry_failed_learning_automation_jobs(db, task_id=int(task_id))
        db.commit()
        return LearningAutomationRetryResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/api/admin/learning-resources/automation-tasks/{task_id}/logs",
    response_model=LearningAutomationLogListResponse,
    summary="获取学习资料自动转存日志",
)
def get_learning_automation_task_logs(
    task_id: int,
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAutomationLogListResponse:
    del current_user
    try:
        items = list_learning_automation_logs(db, task_id=int(task_id), limit=limit)
        return LearningAutomationLogListResponse(items=items, total=len(items))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/api/public/learning-resources/categories",
    response_model=list[LearningCategoryResponse],
    summary="获取公开学习资料分类",
)
def get_public_learning_categories(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] | None = Depends(get_optional_current_user),
) -> list[LearningCategoryResponse]:
    _ensure_public_access(current_user)
    return [LearningCategoryResponse(**item) for item in list_public_learning_categories(db)]


@router.get(
    "/api/public/learning-resources",
    response_model=LearningResourceListResponse,
    summary="获取公开学习资料",
)
def get_public_learning_resources(
    category: str | None = Query(default=None, max_length=160),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] | None = Depends(get_optional_current_user),
) -> LearningResourceListResponse:
    _ensure_public_access(current_user)
    total = count_public_learning_resources(db, category_slug=category, search=search)
    items = list_public_learning_resources(
        db,
        category_slug=category,
        search=search,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return LearningResourceListResponse(
        items=[LearningResourceResponse(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/api/admin/learning-resources/overview",
    response_model=LearningAdminOverviewResponse,
    summary="获取学习资料管理概览",
)
def get_learning_admin_overview(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningAdminOverviewResponse:
    del current_user
    return LearningAdminOverviewResponse(**list_learning_admin_overview(db))


@router.get(
    "/api/admin/learning-resources/items",
    response_model=LearningResourceAdminListResponse,
    summary="获取学习资料管理条目",
)
def get_learning_admin_items(
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceAdminListResponse:
    del current_user
    total = count_admin_learning_items(db, search=search, category_slug=category)
    items = list_admin_learning_items(
        db,
        search=search,
        category_slug=category,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return LearningResourceAdminListResponse(
        items=[LearningResourceAdminResponse(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/api/admin/learning-resources/items/{resource_id}",
    response_model=LearningResourceAdminResponse,
    summary="编辑学习资料表格行",
)
def update_learning_resource_item(
    resource_id: int,
    payload: LearningResourceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceAdminResponse:
    try:
        result = update_learning_resource(
            db,
            resource_id=int(resource_id),
            display_title=payload.display_title,
            category_name=payload.category,
            tags=payload.tags,
            share_url=payload.share_url,
            operator=_operator(current_user),
        )
        db.commit()
        return LearningResourceAdminResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/api/admin/learning-resources/items/{resource_id}",
    response_model=LearningResourceDeleteResponse,
    summary="删除单条学习资料",
)
def delete_learning_resource_item(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceDeleteResponse:
    del current_user
    try:
        result = delete_learning_resource(db, resource_id=int(resource_id))
        db.commit()
        return LearningResourceDeleteResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/api/admin/learning-resources/imported",
    response_model=LearningResourceDeleteResponse,
    summary="删除全部手动导入学习资料",
)
def delete_all_imported_learning_resource_data(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceDeleteResponse:
    del current_user
    try:
        result = delete_all_imported_learning_resources(db)
        db.commit()
        return LearningResourceDeleteResponse(**result)
    except Exception:
        db.rollback()
        raise


@router.get(
    "/api/admin/learning-resources/directories",
    response_model=LearningDirectoryListResponse,
    summary="浏览学习资料网盘目录",
)
async def get_learning_directories(
    account_id: int = Query(..., ge=1),
    parent_id: str = Query(default="0", max_length=255),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningDirectoryListResponse:
    del current_user
    try:
        items = await list_pan_transfer_directories(db, account_id=account_id, parent_id=parent_id)
        return LearningDirectoryListResponse(
            account_id=int(account_id),
            parent_id=str(parent_id or "0"),
            items=items,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"读取网盘目录失败: {exc}") from exc


@router.post(
    "/api/admin/learning-resources/imports/preview",
    response_model=LearningImportPreviewResponse,
    summary="预览学习资料导入文件",
)
async def preview_learning_resources_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningImportPreviewResponse:
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="导入文件不能超过 8MB")
    try:
        result = preview_learning_import(
            db,
            filename=file.filename or "learning-resource-import.txt",
            content=content,
            operator=_operator(current_user),
        )
        db.commit()
        return LearningImportPreviewResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/api/admin/learning-resources/imports/{job_id}/confirm",
    response_model=LearningImportConfirmResponse,
    summary="确认学习资料导入",
)
def confirm_learning_resources_import(
    job_id: int,
    payload: LearningImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningImportConfirmResponse:
    try:
        result = confirm_learning_import(
            db,
            job_id=job_id,
            mode=payload.mode,
            target_account_id=payload.target_account_id,
            save_root=payload.save_root,
            operator=_operator(current_user),
        )
        db.commit()
        return LearningImportConfirmResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put(
    "/api/admin/learning-resources/channels/{channel_id}",
    response_model=LearningChannelUpdateResponse,
    summary="更新学习资料频道自动流程",
)
def update_learning_channel(
    channel_id: int,
    payload: LearningChannelUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningChannelUpdateResponse:
    try:
        result = update_learning_channel_config(
            db,
            channel_id=channel_id,
            payload=payload.model_dump(exclude_unset=True),
            operator=_operator(current_user),
        )
        db.commit()
        return LearningChannelUpdateResponse(
            channel_id=int(result["channel_id"]),
            channel_key=str(result["channel_key"]),
            config_id=int(result["config_id"]),
            is_enabled=bool(result["is_enabled"]),
            target_account_id=result["target_account_id"],
            save_root=str(result["save_root"] or ""),
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch(
    "/api/admin/learning-resources/items/{resource_id}/visibility",
    response_model=LearningResourceAdminResponse,
    summary="隐藏或恢复学习资料",
)
def update_learning_visibility(
    resource_id: int,
    payload: LearningResourceVisibilityRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceAdminResponse:
    del current_user
    resource = db.get(LearningResourceItem, int(resource_id))
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习资料不存在")
    if payload.visible:
        link = (
            db.query(LearningResourceLink)
            .filter(
                LearningResourceLink.resource_id == int(resource.id),
                LearningResourceLink.is_primary.is_(True),
                LearningResourceLink.is_enabled.is_(True),
                LearningResourceLink.status == "published",
                LearningResourceLink.share_url.isnot(None),
            )
            .first()
        )
        if link is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可公开的有效分享链接")
        resource.status = "published"
    else:
        resource.status = "hidden"
    db.add(resource)
    db.commit()
    return LearningResourceAdminResponse(
        id=int(resource.id),
        display_title=str(resource.display_title or ""),
        status=str(resource.status or ""),
        share_url=None,
        category=None,
        latest_source_at=resource.latest_source_at,
        updated_at=resource.updated_at,
    )


@router.post(
    "/api/admin/learning-resources/items/{resource_id}/retry",
    response_model=LearningResourceAdminResponse,
    summary="重试学习资料转存",
)
def retry_learning_resource_api(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceAdminResponse:
    del current_user
    try:
        retry_learning_resource(db, resource_id=int(resource_id))
        resource = db.get(LearningResourceItem, int(resource_id))
        db.commit()
        return LearningResourceAdminResponse(
            id=int(resource.id),
            display_title=str(resource.display_title or ""),
            status=str(resource.status or ""),
            share_url=None,
            category=None,
            latest_source_at=resource.latest_source_at,
            updated_at=resource.updated_at,
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
