from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db, get_optional_current_user
from app.schemas.learning_resources import (
    LearningAdminOverviewResponse,
    LearningCategoryResponse,
    LearningChannelUpdateRequest,
    LearningChannelUpdateResponse,
    LearningResourceAdminListResponse,
    LearningResourceAdminResponse,
    LearningResourceListResponse,
    LearningResourceResponse,
    LearningResourceVisibilityRequest,
)
from app.services.learning_resources import (
    list_admin_learning_items,
    list_learning_admin_overview,
    list_public_learning_categories,
    list_public_learning_resources,
    retry_learning_resource,
    update_learning_channel_config,
)
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
    db: Session = Depends(get_db),
    current_user: dict[str, Any] | None = Depends(get_optional_current_user),
) -> LearningResourceListResponse:
    _ensure_public_access(current_user)
    items = list_public_learning_resources(db, category_slug=category, search=search)
    return LearningResourceListResponse(
        items=[LearningResourceResponse(**item) for item in items],
        total=len(items),
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
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> LearningResourceAdminListResponse:
    del current_user
    items = list_admin_learning_items(db, search=search)
    return LearningResourceAdminListResponse(
        items=[LearningResourceAdminResponse(**item) for item in items],
        total=len(items),
    )


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
