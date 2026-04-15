from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db
from app.schemas.ai_center_models import (
    AiCenterCallEventClearResponse,
    AiCenterCallEventItem,
    AiCenterCallEventListResponse,
    AiCenterDeleteResponse,
    AiCenterOverviewResponse,
    AiCenterProviderItem,
    AiCenterProviderListResponse,
    AiCenterProviderTestRequest,
    AiCenterProviderTestResponse,
    AiCenterProviderUpsertRequest,
    AiCenterRouteItem,
    AiCenterRouteListResponse,
    AiCenterRouteReadinessResponse,
    AiCenterRouteTestRequest,
    AiCenterRouteTestResponse,
    AiCenterRouteUpsertRequest,
)
from app.services.ai_center import (
    clear_ai_call_events,
    delete_ai_provider,
    get_ai_center_overview,
    get_ai_provider_detail,
    get_ai_route_detail,
    get_ai_route_readiness,
    list_ai_call_events,
    list_ai_providers,
    list_ai_routes,
    refresh_ai_provider_models,
    save_ai_provider,
    save_ai_route,
    test_ai_provider,
    test_ai_route,
)


router = APIRouter(prefix="/api/admin/ai-center", tags=["ai-center-admin"])


def _operator_name(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("username") or current_user.get("name") or "admin")


@router.get("/overview", response_model=AiCenterOverviewResponse, summary="Get AI center overview")
async def get_ai_center_overview_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterOverviewResponse:
    del current_user
    try:
        return AiCenterOverviewResponse(**get_ai_center_overview(db))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI center overview: {exc}",
        ) from exc


@router.get("/providers", response_model=AiCenterProviderListResponse, summary="List AI providers")
async def list_ai_providers_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderListResponse:
    del current_user
    try:
        payload = list_ai_providers(db)
        return AiCenterProviderListResponse(
            items=[AiCenterProviderItem(**item) for item in payload["items"]],
            total=payload["total"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI providers: {exc}",
        ) from exc


@router.post("/providers", response_model=AiCenterProviderItem, summary="Create AI provider")
async def create_ai_provider_api(
    payload: AiCenterProviderUpsertRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderItem:
    try:
        result = save_ai_provider(
            db,
            payload=payload.model_dump(exclude_unset=True),
            updated_by=_operator_name(current_user),
        )
        db.commit()
        return AiCenterProviderItem(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create AI provider: {exc}",
        ) from exc


@router.put("/providers/{provider_id}", response_model=AiCenterProviderItem, summary="Update AI provider")
async def update_ai_provider_api(
    provider_id: int,
    payload: AiCenterProviderUpsertRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderItem:
    try:
        result = save_ai_provider(
            db,
            provider_id=provider_id,
            payload=payload.model_dump(exclude_unset=True),
            updated_by=_operator_name(current_user),
        )
        db.commit()
        return AiCenterProviderItem(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI provider: {exc}",
        ) from exc


@router.get("/providers/{provider_id}", response_model=AiCenterProviderItem, summary="Get AI provider detail")
async def get_ai_provider_detail_api(
    provider_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderItem:
    del current_user
    try:
        return AiCenterProviderItem(**get_ai_provider_detail(db, provider_id=provider_id))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI provider detail: {exc}",
        ) from exc


@router.delete("/providers/{provider_id}", response_model=AiCenterDeleteResponse, summary="Delete AI provider")
async def delete_ai_provider_api(
    provider_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterDeleteResponse:
    del current_user
    try:
        result = delete_ai_provider(db, provider_id=provider_id)
        db.commit()
        return AiCenterDeleteResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete AI provider: {exc}",
        ) from exc


@router.post("/providers/{provider_id}/models/refresh", response_model=AiCenterProviderItem, summary="Refresh provider models")
async def refresh_ai_provider_models_api(
    provider_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderItem:
    del current_user
    try:
        result = refresh_ai_provider_models(db, provider_id=provider_id)
        db.commit()
        return AiCenterProviderItem(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh provider models: {exc}",
        ) from exc


@router.post("/providers/{provider_id}/test", response_model=AiCenterProviderTestResponse, summary="Test provider connectivity")
async def test_ai_provider_api(
    provider_id: int,
    payload: AiCenterProviderTestRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterProviderTestResponse:
    del current_user
    try:
        result = test_ai_provider(db, provider_id=provider_id, payload=payload.model_dump(exclude_unset=True))
        db.commit()
        return AiCenterProviderTestResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test AI provider: {exc}",
        ) from exc


@router.get("/routes", response_model=AiCenterRouteListResponse, summary="List AI routes")
async def list_ai_routes_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterRouteListResponse:
    del current_user
    try:
        payload = list_ai_routes(db)
        return AiCenterRouteListResponse(
            items=[AiCenterRouteItem(**item) for item in payload["items"]],
            total=payload["total"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI routes: {exc}",
        ) from exc


@router.get("/routes/{route_key}", response_model=AiCenterRouteItem, summary="Get AI route detail")
async def get_ai_route_detail_api(
    route_key: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterRouteItem:
    del current_user
    try:
        return AiCenterRouteItem(**get_ai_route_detail(db, route_key=route_key))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI route detail: {exc}",
        ) from exc


@router.put("/routes/{route_key}", response_model=AiCenterRouteItem, summary="Save AI route configuration")
async def save_ai_route_api(
    route_key: str,
    payload: AiCenterRouteUpsertRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterRouteItem:
    try:
        result = save_ai_route(
            db,
            route_key=route_key,
            payload=payload.model_dump(exclude_unset=True),
            updated_by=_operator_name(current_user),
        )
        db.commit()
        return AiCenterRouteItem(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save AI route: {exc}",
        ) from exc


@router.get("/routes/{route_key}/readiness", response_model=AiCenterRouteReadinessResponse, summary="Get route readiness")
async def get_ai_route_readiness_api(
    route_key: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterRouteReadinessResponse:
    del current_user
    try:
        return AiCenterRouteReadinessResponse(**get_ai_route_readiness(db, route_key=route_key))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI route readiness: {exc}",
        ) from exc


@router.post("/routes/{route_key}/test", response_model=AiCenterRouteTestResponse, summary="Test AI route")
async def test_ai_route_api(
    route_key: str,
    payload: AiCenterRouteTestRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterRouteTestResponse:
    del current_user
    try:
        result = test_ai_route(db, route_key=route_key, payload=payload.model_dump(exclude_unset=True))
        db.commit()
        return AiCenterRouteTestResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test AI route: {exc}",
        ) from exc


@router.get("/events", response_model=AiCenterCallEventListResponse, summary="List recent AI call events")
async def list_ai_call_events_api(
    route_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterCallEventListResponse:
    del current_user
    try:
        payload = list_ai_call_events(db, route_key=route_key, limit=limit)
        return AiCenterCallEventListResponse(
            items=[AiCenterCallEventItem(**item) for item in payload["items"]],
            total=payload["total"],
            limit=payload["limit"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load AI call events: {exc}",
        ) from exc


@router.post("/events/clear", response_model=AiCenterCallEventClearResponse, summary="Clear AI call events")
async def clear_ai_call_events_api(
    route_key: str | None = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AiCenterCallEventClearResponse:
    del current_user
    try:
        payload = clear_ai_call_events(db, route_key=route_key)
        db.commit()
        return AiCenterCallEventClearResponse(**payload)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear AI call events: {exc}",
        ) from exc
