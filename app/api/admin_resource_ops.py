from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db
from app.schemas.resource_ops_models_v2 import (
    ResourceOpsCandidateDetailResponse,
    ResourceOpsCandidateItem,
    ResourceOpsCandidateListResponse,
    ResourceOpsCatalogStatusResponse,
    ResourceOpsWorkbenchDetailResponse,
    ResourceOpsWorkbenchItem,
    ResourceOpsWorkbenchListResponse,
    ResourceOpsWorkbenchLogItem,
    ResourceOpsWorkbenchSummaryResponse,
    ResourceOpsWorkbenchUpdateRequest,
    ResourceOpsRecognitionRunResponse,
    ResourceOpsRetentionRunResponse,
    ResourceOpsRuntimeSettingsResponse,
    ResourceOpsRuntimeSettingsUpdateRequest,
    ResourceOpsOverviewResponse,
    ResourceOpsPlatformDistributionItem,
    ResourceOpsPlatformDistributionResponse,
    ResourceOpsTrendPoint,
    ResourceOpsTrendResponse,
    ResourceOpsWorkBindingSummaryResponse,
)
from app.services.resource_ops import (
    append_resource_ops_runtime_log,
    clear_resource_ops_runtime_logs,
    get_catalog_sync_status,
    get_resource_op_candidate_detail,
    get_resource_op_workbench_detail,
    get_resource_ops_overview,
    get_resource_ops_platform_distribution,
    get_resource_ops_runtime_settings,
    get_resource_ops_trend,
    get_work_binding_summary,
    list_resource_op_candidates,
    list_resource_op_workbench_items,
    run_resource_ops_retention,
    sync_resource_work_bindings,
    sync_message_link_catalog_batch,
    update_resource_ops_runtime_settings,
    update_resource_op_workbench_item,
)


router = APIRouter(prefix="/api/admin/resource-ops", tags=["resource-ops-admin"])


@router.get("/overview", response_model=ResourceOpsOverviewResponse, summary="Get resource operations overview")
async def get_resource_ops_overview_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsOverviewResponse:
    del current_user
    try:
        return ResourceOpsOverviewResponse(**get_resource_ops_overview(db))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load resource overview: {exc}",
        ) from exc


@router.get("/trend", response_model=ResourceOpsTrendResponse, summary="Get click trend")
async def get_resource_ops_trend_api(
    days: int = Query(30, ge=3, le=90),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsTrendResponse:
    del current_user
    try:
        payload = get_resource_ops_trend(db, days=days)
        return ResourceOpsTrendResponse(
            days=[ResourceOpsTrendPoint(**item) for item in payload["days"]],
            days_window=payload["days_window"],
            generated_at=payload["generated_at"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load click trend: {exc}",
        ) from exc


@router.get("/platforms", response_model=ResourceOpsPlatformDistributionResponse, summary="Get platform distribution")
async def get_resource_ops_platform_distribution_api(
    days: int = Query(30, ge=3, le=90),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsPlatformDistributionResponse:
    del current_user
    try:
        payload = get_resource_ops_platform_distribution(db, days=days)
        return ResourceOpsPlatformDistributionResponse(
            items=[ResourceOpsPlatformDistributionItem(**item) for item in payload["items"]],
            days_window=payload["days_window"],
            generated_at=payload["generated_at"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load platform distribution: {exc}",
        ) from exc


@router.get("/candidates", response_model=ResourceOpsCandidateListResponse, summary="List hot resource candidates")
async def list_resource_candidates_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: Optional[str] = Query(default=None),
    heat_type: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    sort_by: str = Query("score"),
    sort_order: str = Query("desc"),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsCandidateListResponse:
    del current_user
    try:
        payload = list_resource_op_candidates(
            db,
            page=page,
            page_size=page_size,
            platform=platform,
            heat_type=heat_type,
            keyword=keyword,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return ResourceOpsCandidateListResponse(
            items=[ResourceOpsCandidateItem(**item) for item in payload["items"]],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load resource candidates: {exc}",
        ) from exc


@router.get("/candidates/{link_target_id}", response_model=ResourceOpsCandidateDetailResponse, summary="Get candidate detail")
async def get_resource_candidate_detail_api(
    link_target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsCandidateDetailResponse:
    del current_user
    try:
        payload = get_resource_op_candidate_detail(db, link_target_id=link_target_id)
        return ResourceOpsCandidateDetailResponse(
            item=ResourceOpsCandidateItem(**payload["item"]),
            recent_refs=payload["recent_refs"],
            trend=[ResourceOpsTrendPoint(**item) for item in payload["trend"]],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load candidate detail: {exc}",
        ) from exc


@router.get("/workbench/items", response_model=ResourceOpsWorkbenchListResponse, summary="List resource operation workbench items")
async def list_resource_workbench_items_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: Optional[str] = Query(default=None),
    heat_type: Optional[str] = Query(default=None),
    operation_status: Optional[str] = Query(default=None),
    value_status: Optional[str] = Query(default=None),
    resource_kind: Optional[str] = Query(default=None),
    health_status: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    sort_by: str = Query("overall_score"),
    sort_order: str = Query("desc"),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsWorkbenchListResponse:
    del current_user
    try:
        payload = list_resource_op_workbench_items(
            db,
            page=page,
            page_size=page_size,
            platform=platform,
            heat_type=heat_type,
            operation_status=operation_status,
            value_status=value_status,
            resource_kind=resource_kind,
            health_status=health_status,
            keyword=keyword,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return ResourceOpsWorkbenchListResponse(
            items=[ResourceOpsWorkbenchItem(**item) for item in payload["items"]],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            summary=ResourceOpsWorkbenchSummaryResponse(**payload["summary"]),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load workbench items: {exc}",
        ) from exc


@router.get("/workbench/items/{link_target_id}", response_model=ResourceOpsWorkbenchDetailResponse, summary="Get workbench item detail")
async def get_resource_workbench_detail_api(
    link_target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsWorkbenchDetailResponse:
    del current_user
    try:
        payload = get_resource_op_workbench_detail(db, link_target_id=link_target_id)
        return ResourceOpsWorkbenchDetailResponse(
            item=ResourceOpsWorkbenchItem(**payload["item"]),
            recent_refs=payload["recent_refs"],
            trend=[ResourceOpsTrendPoint(**item) for item in payload["trend"]],
            logs=[ResourceOpsWorkbenchLogItem(**item) for item in payload["logs"]],
            auto_reasons=payload["auto_reasons"],
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load workbench detail: {exc}",
        ) from exc


@router.put("/workbench/items/{link_target_id}", response_model=ResourceOpsWorkbenchDetailResponse, summary="Update workbench item")
async def update_resource_workbench_item_api(
    link_target_id: int,
    payload: ResourceOpsWorkbenchUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsWorkbenchDetailResponse:
    try:
        operator = current_user.get("username") or current_user.get("name") or "admin"
        result = update_resource_op_workbench_item(
            db,
            link_target_id=link_target_id,
            payload=payload,
            operator=str(operator),
        )
        db.commit()
        return ResourceOpsWorkbenchDetailResponse(
            item=ResourceOpsWorkbenchItem(**result["item"]),
            recent_refs=result["recent_refs"],
            trend=[ResourceOpsTrendPoint(**item) for item in result["trend"]],
            logs=[ResourceOpsWorkbenchLogItem(**item) for item in result["logs"]],
            auto_reasons=result["auto_reasons"],
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update workbench item: {exc}",
        ) from exc


@router.get("/settings", response_model=ResourceOpsRuntimeSettingsResponse, summary="Get resource operations runtime settings")
async def get_resource_ops_runtime_settings_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRuntimeSettingsResponse:
    del current_user
    try:
        settings_payload = get_resource_ops_runtime_settings(db)
        settings_payload["binding_summary"] = ResourceOpsWorkBindingSummaryResponse(**get_work_binding_summary(db))
        return ResourceOpsRuntimeSettingsResponse(**settings_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load resource runtime settings: {exc}",
        ) from exc


@router.put("/settings", response_model=ResourceOpsRuntimeSettingsResponse, summary="Update resource operations runtime settings")
async def update_resource_ops_runtime_settings_api(
    payload: ResourceOpsRuntimeSettingsUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRuntimeSettingsResponse:
    operator = current_user.get("username") or current_user.get("name") or "admin"
    try:
        update_resource_ops_runtime_settings(
            db,
            payload.dict(exclude_unset=True),
            updated_by=str(operator),
        )
        append_resource_ops_runtime_log(
            db,
            log_line=(
                f"[INFO] 归并配置已保存 -> AI 路由 resource_ops_title_extract / "
                f"自动识别 {'开启' if payload.auto_recognition_enabled else '关闭'}"
            ),
            updated_by=str(operator),
        )
        db.commit()
        settings_payload = get_resource_ops_runtime_settings(db)
        settings_payload["binding_summary"] = ResourceOpsWorkBindingSummaryResponse(**get_work_binding_summary(db))
        return ResourceOpsRuntimeSettingsResponse(**settings_payload)
    except ValueError as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 保存归并配置失败 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 保存归并配置异常 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update resource runtime settings: {exc}",
        ) from exc


@router.post("/logs/clear", response_model=ResourceOpsRuntimeSettingsResponse, summary="Clear resource operations runtime logs")
async def clear_resource_ops_logs_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRuntimeSettingsResponse:
    operator = current_user.get("username") or current_user.get("name") or "admin"
    try:
        settings_payload = clear_resource_ops_runtime_logs(db, updated_by=str(operator))
        db.commit()
        settings_payload["binding_summary"] = ResourceOpsWorkBindingSummaryResponse(**get_work_binding_summary(db))
        return ResourceOpsRuntimeSettingsResponse(**settings_payload)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear resource runtime logs: {exc}",
        ) from exc


@router.post("/recognition/pending", response_model=ResourceOpsRecognitionRunResponse, summary="Queue pending resource recognition")
async def sync_resource_recognition_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRecognitionRunResponse:
    operator = current_user.get("username") or current_user.get("name") or "admin"
    try:
        payload = sync_resource_work_bindings(
            db,
            mode="pending",
            operator=str(operator),
        )
        append_resource_ops_runtime_log(
            db,
            log_line=f"[INFO] 手动入队 -> 待处理 / {payload.get('message') or '-'}",
            updated_by=str(operator),
        )
        db.commit()
        return ResourceOpsRecognitionRunResponse(**payload)
    except ValueError as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 手动入队失败 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 手动入队异常 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run resource recognition sync: {exc}",
        ) from exc


@router.post("/recognition/all", response_model=ResourceOpsRecognitionRunResponse, summary="Queue a full AI recognition cycle")
async def sync_resource_recognition_full_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRecognitionRunResponse:
    operator = current_user.get("username") or current_user.get("name") or "admin"
    try:
        payload = sync_resource_work_bindings(
            db,
            mode="all",
            operator=str(operator),
        )
        append_resource_ops_runtime_log(
            db,
            log_line=f"[INFO] 手动入队 -> 全部扫描 / {payload.get('message') or '-'}",
            updated_by=str(operator),
        )
        db.commit()
        return ResourceOpsRecognitionRunResponse(**payload)
    except ValueError as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 全部扫描入队失败 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        append_resource_ops_runtime_log(
            db,
            log_line=f"[ERR] 全部扫描入队异常 -> {exc}",
            updated_by=str(operator),
            last_error=str(exc),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run full resource recognition sync: {exc}",
        ) from exc


@router.post("/maintenance/run", response_model=ResourceOpsRetentionRunResponse, summary="Run resource operations retention cleanup")
async def run_resource_ops_maintenance_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsRetentionRunResponse:
    operator = current_user.get("username") or current_user.get("name") or "admin"
    try:
        payload = run_resource_ops_retention(db, operator=str(operator))
        db.commit()
        return ResourceOpsRetentionRunResponse(**payload)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run resource retention cleanup: {exc}",
        ) from exc


@router.get("/catalog/status", response_model=ResourceOpsCatalogStatusResponse, summary="Get catalog sync status")
async def get_resource_catalog_status_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsCatalogStatusResponse:
    del current_user
    try:
        return ResourceOpsCatalogStatusResponse(**get_catalog_sync_status(db))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load catalog status: {exc}",
        ) from exc


@router.post("/catalog/sync", response_model=ResourceOpsCatalogStatusResponse, summary="Sync one catalog batch")
async def sync_resource_catalog_api(
    batch_size: int = Query(500, ge=50, le=2000),
    current_user: Dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ResourceOpsCatalogStatusResponse:
    del current_user
    try:
        return ResourceOpsCatalogStatusResponse(**sync_message_link_catalog_batch(db, batch_size=batch_size))
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync resource catalog: {exc}",
        ) from exc
