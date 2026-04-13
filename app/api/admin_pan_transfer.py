from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db
from app.schemas.pan_transfer_models import (
    PanTransferAccountCreateRequest,
    PanTransferAccountItem,
    PanTransferAccountListResponse,
    PanTransferAccountValidationResponse,
    PanTransferAccountUpdateRequest,
    PanTransferBatchCreateRequest,
    PanTransferBatchDetailResponse,
    PanTransferBatchListResponse,
    PanTransferBatchRetryRequest,
    PanTransferBatchSummaryItem,
    PanTransferDeleteResponse,
    PanTransferManualPreviewRequest,
    PanTransferManualPreviewResponse,
)
from app.services.pan_transfer import (
    cancel_pan_transfer_batch,
    create_pan_transfer_account,
    create_manual_pan_transfer_batch,
    delete_pan_transfer_account,
    delete_pan_transfer_batch,
    get_pan_transfer_batch_detail,
    list_pan_transfer_accounts,
    list_pan_transfer_batches,
    preview_manual_pan_transfer_selection,
    retry_pan_transfer_batch,
    start_pan_transfer_batch,
    update_pan_transfer_account,
    validate_pan_transfer_account,
)


router = APIRouter(prefix="/api/admin/pan-transfer", tags=["pan-transfer-admin"])


@router.get("/accounts", response_model=PanTransferAccountListResponse, summary="List pan transfer accounts")
async def list_pan_transfer_accounts_api(
    platform: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferAccountListResponse:
    del current_user
    try:
        items = list_pan_transfer_accounts(db, platform=platform)
        return PanTransferAccountListResponse(
            items=[PanTransferAccountItem(**item) for item in items],
            total=len(items),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load pan transfer accounts: {exc}",
        ) from exc


@router.post("/accounts", response_model=PanTransferAccountItem, summary="Create pan transfer account")
async def create_pan_transfer_account_api(
    payload: PanTransferAccountCreateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferAccountItem:
    del current_user
    try:
        result = create_pan_transfer_account(db, payload.model_dump())
        db.commit()
        return PanTransferAccountItem(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pan transfer account: {exc}",
        ) from exc


@router.put("/accounts/{account_id}", response_model=PanTransferAccountItem, summary="Update pan transfer account")
async def update_pan_transfer_account_api(
    account_id: int,
    payload: PanTransferAccountUpdateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferAccountItem:
    del current_user
    try:
        result = update_pan_transfer_account(
            db,
            account_id=account_id,
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        return PanTransferAccountItem(**result)
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
            detail=f"Failed to update pan transfer account: {exc}",
        ) from exc


@router.delete("/accounts/{account_id}", response_model=PanTransferDeleteResponse, summary="Delete pan transfer account")
async def delete_pan_transfer_account_api(
    account_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferDeleteResponse:
    del current_user
    try:
        result = delete_pan_transfer_account(db, account_id=account_id)
        db.commit()
        return PanTransferDeleteResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete pan transfer account: {exc}",
        ) from exc


@router.post("/accounts/{account_id}/validate", response_model=PanTransferAccountValidationResponse, summary="Validate pan transfer account")
async def validate_pan_transfer_account_api(
    account_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferAccountValidationResponse:
    del current_user
    try:
        result = await validate_pan_transfer_account(db, account_id=account_id)
        db.commit()
        return PanTransferAccountValidationResponse(**result)
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
            detail=f"Failed to validate pan transfer account: {exc}",
        ) from exc


@router.post("/preview/manual", response_model=PanTransferManualPreviewResponse, summary="Preview manual pan transfer selection")
async def preview_manual_pan_transfer_api(
    payload: PanTransferManualPreviewRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferManualPreviewResponse:
    del current_user
    try:
        result = preview_manual_pan_transfer_selection(db, payload.model_dump())
        return PanTransferManualPreviewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview manual pan transfer selection: {exc}",
        ) from exc


@router.post("/batches/manual", response_model=PanTransferBatchDetailResponse, summary="Create manual pan transfer batch")
async def create_manual_pan_transfer_batch_api(
    payload: PanTransferBatchCreateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    try:
        result = create_manual_pan_transfer_batch(
            db,
            payload=payload.model_dump(),
            created_by=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferBatchDetailResponse(
            batch=PanTransferBatchSummaryItem(**result["batch"]),
            items=result["items"],
        )
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
            detail=f"Failed to create pan transfer batch: {exc}",
        ) from exc


@router.get("/batches", response_model=PanTransferBatchListResponse, summary="List pan transfer batches")
async def list_pan_transfer_batches_api(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchListResponse:
    del current_user
    try:
        result = list_pan_transfer_batches(db, page=page, page_size=page_size)
        return PanTransferBatchListResponse(
            items=[PanTransferBatchSummaryItem(**item) for item in result["items"]],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list pan transfer batches: {exc}",
        ) from exc


@router.get("/batches/{batch_id}", response_model=PanTransferBatchDetailResponse, summary="Get pan transfer batch detail")
async def get_pan_transfer_batch_detail_api(
    batch_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    del current_user
    try:
        result = get_pan_transfer_batch_detail(db, batch_id=batch_id)
        return PanTransferBatchDetailResponse(
            batch=PanTransferBatchSummaryItem(**result["batch"]),
            items=result["items"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load pan transfer batch detail: {exc}",
        ) from exc


@router.post("/batches/{batch_id}/start", response_model=PanTransferBatchDetailResponse, summary="Start a draft pan transfer batch")
async def start_pan_transfer_batch_api(
    batch_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    del current_user
    try:
        result = start_pan_transfer_batch(db, batch_id=batch_id)
        db.commit()
        return PanTransferBatchDetailResponse(
            batch=PanTransferBatchSummaryItem(**result["batch"]),
            items=result["items"],
        )
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
            detail=f"Failed to start pan transfer batch: {exc}",
        ) from exc


@router.post("/batches/{batch_id}/retry", response_model=PanTransferBatchDetailResponse, summary="Retry failed pan transfer items")
async def retry_pan_transfer_batch_api(
    batch_id: int,
    payload: PanTransferBatchRetryRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    del current_user
    try:
        result = retry_pan_transfer_batch(db, batch_id=batch_id, item_ids=payload.item_ids)
        db.commit()
        return PanTransferBatchDetailResponse(
            batch=PanTransferBatchSummaryItem(**result["batch"]),
            items=result["items"],
        )
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
            detail=f"Failed to retry pan transfer batch: {exc}",
        ) from exc


@router.post("/batches/{batch_id}/cancel", response_model=PanTransferBatchDetailResponse, summary="Cancel an active pan transfer batch")
async def cancel_pan_transfer_batch_api(
    batch_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    try:
        result = cancel_pan_transfer_batch(
            db,
            batch_id=batch_id,
            cancelled_by=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferBatchDetailResponse(
            batch=PanTransferBatchSummaryItem(**result["batch"]),
            items=result["items"],
        )
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
            detail=f"Failed to cancel pan transfer batch: {exc}",
        ) from exc


@router.delete("/batches/{batch_id}", response_model=PanTransferDeleteResponse, summary="Delete pan transfer batch")
async def delete_pan_transfer_batch_api(
    batch_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferDeleteResponse:
    del current_user
    try:
        result = delete_pan_transfer_batch(db, batch_id=batch_id)
        db.commit()
        return PanTransferDeleteResponse(id=result["id"], platform="batch", deleted=True)
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
            detail=f"Failed to delete pan transfer batch: {exc}",
        ) from exc
