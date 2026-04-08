from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies_runtime_v2 import get_admin_user
from app.schemas.backup_models import (
    BackupRemoteFileDeleteResponse,
    BackupRemoteFileResponse,
    BackupRunDeleteRequest,
    BackupRunDeleteResponse,
    BackupRunResponse,
    BackupTargetCreate,
    BackupTargetResponse,
    BackupTargetTestResult,
    BackupTargetUpdate,
)
from app.services.backup_service import (
    create_backup_target,
    delete_backup_runs,
    delete_backup_target,
    delete_backup_target_remote_file,
    list_backup_runs,
    list_backup_target_remote_files,
    list_backup_targets,
    start_backup_run,
    test_backup_target,
    update_backup_target,
)


router = APIRouter(prefix="/api/admin/backups", tags=["backups"])


def _raise_backup_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/targets", response_model=List[BackupTargetResponse], summary="List backup targets")
async def get_backup_targets(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> List[BackupTargetResponse]:
    del current_user
    return [BackupTargetResponse(**item) for item in list_backup_targets()]


@router.post("/targets", response_model=BackupTargetResponse, summary="Create backup target")
async def create_backup_target_api(
    payload: BackupTargetCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupTargetResponse:
    try:
        result = create_backup_target(payload.model_dump(), updated_by=current_user.get("username"))
        return BackupTargetResponse(**result)
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.put("/targets/{target_id}", response_model=BackupTargetResponse, summary="Update backup target")
async def update_backup_target_api(
    target_id: int,
    payload: BackupTargetUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupTargetResponse:
    try:
        result = update_backup_target(target_id, payload.model_dump(), updated_by=current_user.get("username"))
        return BackupTargetResponse(**result)
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.delete("/targets/{target_id}", summary="Delete backup target")
async def delete_backup_target_api(
    target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> dict[str, Any]:
    del current_user
    try:
        delete_backup_target(target_id)
        return {"success": True, "id": target_id}
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.post("/targets/{target_id}/run", response_model=BackupRunResponse, summary="Run backup target now")
async def run_backup_target_api(
    target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupRunResponse:
    try:
        result = start_backup_run(target_id, trigger_source="manual", created_by=current_user.get("username"))
        return BackupRunResponse(**result)
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.post("/targets/{target_id}/test", response_model=BackupTargetTestResult, summary="Test backup target")
async def test_backup_target_api(
    target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupTargetTestResult:
    del current_user
    try:
        return BackupTargetTestResult(**test_backup_target(target_id))
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.get("/targets/{target_id}/remote-files", response_model=List[BackupRemoteFileResponse], summary="List remote backup files")
async def list_backup_target_remote_files_api(
    target_id: int,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> List[BackupRemoteFileResponse]:
    del current_user
    try:
        return [BackupRemoteFileResponse(**item) for item in list_backup_target_remote_files(target_id)]
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.delete("/targets/{target_id}/remote-files", response_model=BackupRemoteFileDeleteResponse, summary="Delete remote backup file")
async def delete_backup_target_remote_file_api(
    target_id: int,
    remote_path: str = Query(..., min_length=1),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupRemoteFileDeleteResponse:
    del current_user
    try:
        return BackupRemoteFileDeleteResponse(**delete_backup_target_remote_file(target_id, remote_path))
    except Exception as exc:
        _raise_backup_error(exc)
        raise


@router.get("/runs", response_model=List[BackupRunResponse], summary="List backup runs")
async def get_backup_runs(
    limit: int = Query(default=40, ge=1, le=200),
    target_id: int | None = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> List[BackupRunResponse]:
    del current_user
    return [BackupRunResponse(**item) for item in list_backup_runs(limit=limit, target_id=target_id)]


@router.post("/runs/delete", response_model=BackupRunDeleteResponse, summary="Delete backup runs")
async def delete_backup_runs_api(
    payload: BackupRunDeleteRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BackupRunDeleteResponse:
    del current_user
    try:
        return BackupRunDeleteResponse(**delete_backup_runs(payload.ids))
    except Exception as exc:
        _raise_backup_error(exc)
        raise
