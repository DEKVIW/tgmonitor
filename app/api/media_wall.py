from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db, get_optional_current_user
from app.schemas.media_wall_models import (
    MediaWallCategoryCreateRequest,
    MediaWallCategoryResponse,
    MediaWallCategoryUpdateRequest,
    MediaWallImportConfirmRequest,
    MediaWallImportConfirmResponse,
    MediaWallImportPreviewResponse,
    MediaWallItemCreateRequest,
    MediaWallItemBulkDeleteRequest,
    MediaWallItemBulkDeleteResponse,
    MediaWallItemListResponse,
    MediaWallItemResponse,
    MediaWallItemUpdateRequest,
    MediaWallLinkCreateRequest,
    MediaWallLinkResponse,
    MediaWallLinkUpdateRequest,
    MediaWallSourceRequest,
    MediaWallSourceResponse,
    MediaWallSourceTestResponse,
    MediaWallSyncTaskResponse,
)
from app.services.media_wall import (
    add_item_link,
    confirm_import,
    create_category,
    create_item,
    create_source,
    delete_item,
    delete_items,
    disable_category,
    get_public_item,
    list_admin_categories,
    list_admin_items,
    list_public_categories,
    list_public_items,
    list_sources,
    list_sync_tasks,
    preview_import,
    test_source,
    update_category,
    update_item,
    update_item_link,
    update_source,
)
from app.services.system_config_service import is_public_dashboard_enabled


router = APIRouter(tags=["media-wall"])


def _ensure_public_access(current_user: Optional[Dict[str, Any]]) -> None:
    if current_user is None and not is_public_dashboard_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要开启游客公开页面后才能访问影视墙",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _operator(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("username") or current_user.get("name") or "admin")


@router.get("/api/public/media-wall/categories", response_model=list[MediaWallCategoryResponse], summary="获取公开影视墙分类")
async def get_public_media_wall_categories(
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> list[MediaWallCategoryResponse]:
    _ensure_public_access(current_user)
    return [MediaWallCategoryResponse(**item) for item in list_public_categories(db)]


@router.get("/api/public/media-wall", response_model=MediaWallItemListResponse, summary="获取公开影视墙")
async def get_public_media_wall(
    category: Optional[str] = Query(default=None, max_length=160),
    search: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> MediaWallItemListResponse:
    _ensure_public_access(current_user)
    payload = list_public_items(db, category_slug=category, search=search, page=page, page_size=page_size)
    return MediaWallItemListResponse(
        items=[MediaWallItemResponse(**item) for item in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
    )


@router.get("/api/public/media-wall/items/{item_id}", response_model=MediaWallItemResponse, summary="获取公开影视详情")
async def get_public_media_wall_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> MediaWallItemResponse:
    _ensure_public_access(current_user)
    try:
        return MediaWallItemResponse(**get_public_item(db, item_id))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/api/admin/media-wall/categories", response_model=list[MediaWallCategoryResponse], summary="获取影视墙分类")
async def get_admin_media_wall_categories(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> list[MediaWallCategoryResponse]:
    del current_user
    return [MediaWallCategoryResponse(**item) for item in list_admin_categories(db)]


@router.post("/api/admin/media-wall/categories", response_model=MediaWallCategoryResponse, summary="创建影视墙分类")
async def create_admin_media_wall_category(
    payload: MediaWallCategoryCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallCategoryResponse:
    try:
        result = create_category(
            db,
            name=payload.name,
            slug=payload.slug,
            sort_order=payload.sort_order,
            is_enabled=payload.is_enabled,
            operator=_operator(current_user),
        )
        db.commit()
        return MediaWallCategoryResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/api/admin/media-wall/categories/{category_id}", response_model=MediaWallCategoryResponse, summary="更新影视墙分类")
async def update_admin_media_wall_category(
    category_id: int,
    payload: MediaWallCategoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallCategoryResponse:
    try:
        result = update_category(
            db,
            category_id=category_id,
            name=payload.name,
            slug=payload.slug,
            sort_order=payload.sort_order,
            is_enabled=payload.is_enabled,
            operator=_operator(current_user),
        )
        db.commit()
        return MediaWallCategoryResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/api/admin/media-wall/categories/{category_id}", response_model=MediaWallCategoryResponse, summary="停用影视墙分类")
async def delete_admin_media_wall_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallCategoryResponse:
    del current_user
    try:
        result = disable_category(db, category_id=category_id)
        db.commit()
        return MediaWallCategoryResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/api/admin/media-wall/items", response_model=list[MediaWallItemResponse], summary="获取影视墙条目")
async def get_admin_media_wall_items(
    search: Optional[str] = Query(default=None, max_length=120),
    visibility: Optional[str] = Query(default=None, max_length=32),
    category_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> list[MediaWallItemResponse]:
    del current_user
    return [
        MediaWallItemResponse(**item)
        for item in list_admin_items(db, search=search, visibility=visibility, category_id=category_id)
    ]


@router.post("/api/admin/media-wall/items", response_model=MediaWallItemResponse, summary="创建影视墙条目")
async def create_admin_media_wall_item(
    payload: MediaWallItemCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallItemResponse:
    try:
        result = create_item(
            db,
            display_title=payload.display_title,
            metadata_query_title=payload.metadata_query_title,
            visibility=payload.visibility,
            sort_order=payload.sort_order,
            category_ids=payload.category_ids,
            sync_task_id=payload.sync_task_id,
            custom_poster_url=payload.custom_poster_url,
            links=[item.model_dump() for item in payload.links],
            operator=_operator(current_user),
        )
        db.commit()
        return MediaWallItemResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/api/admin/media-wall/items/{item_id}", response_model=MediaWallItemResponse, summary="更新影视墙条目")
async def update_admin_media_wall_item(
    item_id: int,
    payload: MediaWallItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallItemResponse:
    try:
        result = update_item(
            db,
            item_id=item_id,
            display_title=payload.display_title,
            metadata_query_title=payload.metadata_query_title,
            visibility=payload.visibility,
            sort_order=payload.sort_order,
            category_ids=payload.category_ids,
            sync_task_id=payload.sync_task_id,
            custom_poster_url=payload.custom_poster_url,
            operator=_operator(current_user),
        )
        db.commit()
        return MediaWallItemResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/api/admin/media-wall/items/bulk-delete",
    response_model=MediaWallItemBulkDeleteResponse,
    summary="批量删除影视墙条目",
)
async def bulk_delete_admin_media_wall_items(
    payload: MediaWallItemBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallItemBulkDeleteResponse:
    del current_user
    try:
        deleted_ids = delete_items(db, item_ids=payload.item_ids)
        db.commit()
        return MediaWallItemBulkDeleteResponse(deleted_ids=deleted_ids, deleted_count=len(deleted_ids))
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/api/admin/media-wall/items/{item_id}", response_model=MediaWallItemResponse, summary="删除影视墙条目")
async def delete_admin_media_wall_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallItemResponse:
    del current_user
    try:
        result = delete_item(db, item_id=item_id)
        db.commit()
        return MediaWallItemResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/admin/media-wall/items/{item_id}/links", response_model=MediaWallLinkResponse, summary="添加影视墙链接")
async def add_admin_media_wall_link(
    item_id: int,
    payload: MediaWallLinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallLinkResponse:
    del current_user
    try:
        result = add_item_link(
            db,
            item_id=item_id,
            url=payload.url,
            label=payload.label,
            source_type=payload.source_type,
            is_primary=payload.is_primary,
        )
        db.commit()
        return MediaWallLinkResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/api/admin/media-wall/links/{link_id}", response_model=MediaWallLinkResponse, summary="更新影视墙链接")
async def update_admin_media_wall_link(
    link_id: int,
    payload: MediaWallLinkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallLinkResponse:
    del current_user
    try:
        result = update_item_link(
            db,
            link_id=link_id,
            url=payload.url,
            label=payload.label,
            is_enabled=payload.is_enabled,
            is_primary=payload.is_primary,
        )
        db.commit()
        return MediaWallLinkResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/api/admin/media-wall/sync-tasks", response_model=list[MediaWallSyncTaskResponse], summary="获取追更任务")
async def get_admin_media_wall_sync_tasks(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> list[MediaWallSyncTaskResponse]:
    del current_user
    return [MediaWallSyncTaskResponse(**item) for item in list_sync_tasks(db)]


@router.get("/api/admin/media-wall/sources", response_model=list[MediaWallSourceResponse], summary="获取影视采集源")
async def get_admin_media_wall_sources(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> list[MediaWallSourceResponse]:
    del current_user
    return [MediaWallSourceResponse(**item) for item in list_sources(db)]


@router.post("/api/admin/media-wall/sources", response_model=MediaWallSourceResponse, summary="创建影视采集源")
async def create_admin_media_wall_source(
    payload: MediaWallSourceRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallSourceResponse:
    del current_user
    try:
        result = create_source(db, **payload.model_dump())
        db.commit()
        return MediaWallSourceResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/api/admin/media-wall/sources/{source_id}", response_model=MediaWallSourceResponse, summary="更新影视采集源")
async def update_admin_media_wall_source(
    source_id: int,
    payload: MediaWallSourceRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallSourceResponse:
    del current_user
    try:
        result = update_source(db, source_id=source_id, **payload.model_dump())
        db.commit()
        return MediaWallSourceResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/admin/media-wall/sources/{source_id}/test", response_model=MediaWallSourceTestResponse, summary="测试影视采集源")
async def test_admin_media_wall_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallSourceTestResponse:
    del current_user
    try:
        result = test_source(db, source_id=source_id)
        db.commit()
        return MediaWallSourceTestResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/admin/media-wall/sources/{source_id}/refresh", response_model=MediaWallSourceTestResponse, summary="刷新影视采集源")
async def refresh_admin_media_wall_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallSourceTestResponse:
    del current_user
    try:
        result = test_source(db, source_id=source_id, refresh=True)
        db.commit()
        return MediaWallSourceTestResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/admin/media-wall/imports/preview", response_model=MediaWallImportPreviewResponse, summary="预览影视墙导入文件")
async def preview_admin_media_wall_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallImportPreviewResponse:
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="导入文件不能超过 8MB")
    try:
        result = preview_import(db, filename=file.filename or "media-wall-import.txt", content=content, operator=_operator(current_user))
        db.commit()
        return MediaWallImportPreviewResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/admin/media-wall/imports/{job_id}/confirm", response_model=MediaWallImportConfirmResponse, summary="确认影视墙导入")
async def confirm_admin_media_wall_import(
    job_id: int,
    payload: MediaWallImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> MediaWallImportConfirmResponse:
    try:
        result = confirm_import(
            db,
            job_id=job_id,
            category_ids=payload.category_ids,
            visibility=payload.visibility,
            operator=_operator(current_user),
        )
        db.commit()
        return MediaWallImportConfirmResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
