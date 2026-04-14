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
    PanTransferFollowTaskCreateRequest,
    PanTransferFollowTaskDetailResponse,
    PanTransferFollowTaskListResponse,
    PanTransferFollowTaskSyncRequest,
    PanTransferFollowTaskSyncResponse,
    PanTransferLinkDirectoryPreviewRequest,
    PanTransferLinkDirectoryPreviewResponse,
    PanTransferManualPublishRequest,
    PanTransferMessagePublishRequest,
    PanTransferMessagePublishResponse,
    PanTransferPublishRecordItem,
    PanTransferPublishRecordListResponse,
    PanTransferPublishRuleUpdateRequest,
    PanTransferPublishRecordUpdateRequest,
    PanTransferBatchRetryRequest,
    PanTransferBatchSummaryItem,
    PanTransferDeleteResponse,
    PanTransferManualPreviewRequest,
    PanTransferManualPreviewResponse,
)
from app.services.pan_transfer import (
    cancel_pan_transfer_batch,
    clear_pan_transfer_batch_logs,
    clear_pan_transfer_follow_task_candidate,
    create_pan_transfer_account,
    create_pan_transfer_follow_task_from_batch_item,
    create_pan_transfer_follow_sync_batch,
    create_manual_pan_transfer_batch,
    delete_pan_transfer_account,
    delete_pan_transfer_batch,
    delete_pan_transfer_follow_task,
    delete_pan_transfer_publish_record,
    get_pan_transfer_batch_detail,
    get_pan_transfer_follow_task_detail,
    list_pan_transfer_accounts,
    list_pan_transfer_batches,
    list_pan_transfer_follow_tasks,
    list_pan_transfer_publish_records,
    pause_pan_transfer_follow_task,
    archive_pan_transfer_publish_record,
    publish_manual_pan_transfer_message,
    publish_pan_transfer_batch_item_message,
    preview_pan_transfer_link_directory,
    preview_manual_pan_transfer_selection,
    queue_pan_transfer_follow_task_check,
    republish_pan_transfer_publish_record,
    refresh_pan_transfer_publish_record_share,
    retry_pan_transfer_batch,
    resume_pan_transfer_follow_task,
    start_pan_transfer_batch,
    update_pan_transfer_publish_rule,
    update_pan_transfer_publish_record,
    update_pan_transfer_account,
    validate_pan_transfer_account,
    validate_pan_transfer_publish_record,
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


@router.post(
    "/batches/{batch_id}/items/{item_id}/publish",
    response_model=PanTransferMessagePublishResponse,
    summary="Publish a pan transfer batch item to the frontend feed",
)
async def publish_pan_transfer_batch_item_message_api(
    batch_id: int,
    item_id: int,
    payload: PanTransferMessagePublishRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferMessagePublishResponse:
    try:
        result = publish_pan_transfer_batch_item_message(
            db,
            batch_id=batch_id,
            item_id=item_id,
            payload=payload.model_dump(),
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferMessagePublishResponse(**result)
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
            detail=f"Failed to publish pan transfer batch item: {exc}",
        ) from exc


@router.post(
    "/publishes/manual",
    response_model=PanTransferMessagePublishResponse,
    summary="Publish a manual message to the frontend feed",
)
async def publish_manual_pan_transfer_message_api(
    payload: PanTransferManualPublishRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferMessagePublishResponse:
    try:
        result = publish_manual_pan_transfer_message(
            db,
            payload=payload.model_dump(),
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferMessagePublishResponse(**result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish manual message: {exc}",
        ) from exc


@router.post(
    "/link-preview",
    response_model=PanTransferLinkDirectoryPreviewResponse,
    summary="Preview the top-level directory of a public share link",
)
async def preview_pan_transfer_link_directory_api(
    payload: PanTransferLinkDirectoryPreviewRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
) -> PanTransferLinkDirectoryPreviewResponse:
    del current_user
    try:
        result = await preview_pan_transfer_link_directory(
            url=payload.url,
            entry_id=payload.entry_id,
            entry_path=payload.entry_path,
            entry_name=payload.entry_name,
        )
        return PanTransferLinkDirectoryPreviewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview link directory: {exc}",
        ) from exc


@router.get("/publishes", response_model=PanTransferPublishRecordListResponse, summary="List pan transfer publish records")
async def list_pan_transfer_publish_records_api(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    scope: str = Query(default="active"),
    sort_by: str = Query(default="published_at"),
    sort_order: str = Query(default="desc"),
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordListResponse:
    del current_user
    try:
        result = list_pan_transfer_publish_records(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            platform=platform,
            scope=scope,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return PanTransferPublishRecordListResponse(
            items=[PanTransferPublishRecordItem(**item) for item in result["items"]],
            page=result["page"],
            page_size=result["page_size"],
            total=result["total"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list publish records: {exc}",
        ) from exc


@router.post(
    "/publishes/{record_id}/republish",
    response_model=PanTransferPublishRecordItem,
    summary="Republish a managed resource to the frontend feed",
)
async def republish_pan_transfer_publish_record_api(
    record_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    try:
        result = republish_pan_transfer_publish_record(
            db,
            record_id=record_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to republish resource: {exc}",
        ) from exc


@router.put("/publishes/{record_id}", response_model=PanTransferPublishRecordItem, summary="Update a publish record")
async def update_pan_transfer_publish_record_api(
    record_id: int,
    payload: PanTransferPublishRecordUpdateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    try:
        result = update_pan_transfer_publish_record(
            db,
            record_id=record_id,
            payload=payload.model_dump(),
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to update publish record: {exc}",
        ) from exc


@router.post(
    "/publishes/{record_id}/archive",
    response_model=PanTransferPublishRecordItem,
    summary="Archive a publish record resource",
)
async def archive_pan_transfer_publish_record_api(
    record_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    try:
        result = archive_pan_transfer_publish_record(
            db,
            record_id=record_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to archive publish record: {exc}",
        ) from exc


@router.delete(
    "/publishes/{record_id}",
    response_model=PanTransferDeleteResponse,
    summary="Delete a publish record resource",
)
async def delete_pan_transfer_publish_record_api(
    record_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferDeleteResponse:
    del current_user
    try:
        result = delete_pan_transfer_publish_record(db, record_id=record_id)
        db.commit()
        return PanTransferDeleteResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete publish record: {exc}",
        ) from exc


@router.put(
    "/publishes/{record_id}/rule",
    response_model=PanTransferPublishRecordItem,
    summary="Update a publish rule",
)
async def update_pan_transfer_publish_rule_api(
    record_id: int,
    payload: PanTransferPublishRuleUpdateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    del current_user
    try:
        result = update_pan_transfer_publish_rule(
            db,
            record_id=record_id,
            payload=payload.model_dump(),
        )
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to update publish rule: {exc}",
        ) from exc


@router.post(
    "/publishes/{record_id}/validate",
    response_model=PanTransferPublishRecordItem,
    summary="Validate the current published link",
)
async def validate_pan_transfer_publish_record_api(
    record_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    del current_user
    try:
        result = await validate_pan_transfer_publish_record(db, record_id=record_id)
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to validate publish record: {exc}",
        ) from exc


@router.post(
    "/publishes/{record_id}/refresh-share",
    response_model=PanTransferPublishRecordItem,
    summary="Create a refreshed share and update the published message",
)
async def refresh_pan_transfer_publish_record_share_api(
    record_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferPublishRecordItem:
    try:
        result = await refresh_pan_transfer_publish_record_share(
            db,
            record_id=record_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferPublishRecordItem(**result)
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
            detail=f"Failed to refresh publish share: {exc}",
        ) from exc


@router.post(
    "/batches/{batch_id}/items/{item_id}/follow",
    response_model=PanTransferFollowTaskDetailResponse,
    summary="Create a follow task from a pan transfer batch item",
)
async def create_pan_transfer_follow_task_from_batch_item_api(
    batch_id: int,
    item_id: int,
    payload: PanTransferFollowTaskCreateRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    try:
        result = create_pan_transfer_follow_task_from_batch_item(
            db,
            batch_id=batch_id,
            item_id=item_id,
            payload=payload.model_dump(exclude_unset=True),
            created_by=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskDetailResponse(**result)
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
            detail=f"Failed to create follow task: {exc}",
        ) from exc


@router.get("/follow-tasks", response_model=PanTransferFollowTaskListResponse, summary="List follow tasks")
async def list_pan_transfer_follow_tasks_api(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskListResponse:
    del current_user
    try:
        result = list_pan_transfer_follow_tasks(db, page=page, page_size=page_size, status=status_filter)
        return PanTransferFollowTaskListResponse(**result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list follow tasks: {exc}",
        ) from exc


@router.get("/follow-tasks/{task_id}", response_model=PanTransferFollowTaskDetailResponse, summary="Get follow task detail")
async def get_pan_transfer_follow_task_detail_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    del current_user
    try:
        result = get_pan_transfer_follow_task_detail(db, task_id=task_id)
        return PanTransferFollowTaskDetailResponse(**result)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load follow task detail: {exc}",
        ) from exc


@router.post("/follow-tasks/{task_id}/queue", response_model=PanTransferFollowTaskDetailResponse, summary="Queue a follow task for immediate check")
async def queue_pan_transfer_follow_task_check_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    try:
        result = queue_pan_transfer_follow_task_check(
            db,
            task_id=task_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskDetailResponse(**result)
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
            detail=f"Failed to queue follow task: {exc}",
        ) from exc


@router.post(
    "/follow-tasks/{task_id}/sync",
    response_model=PanTransferFollowTaskSyncResponse,
    summary="Create a follow sync batch from the tracked resource",
)
async def create_pan_transfer_follow_sync_batch_api(
    task_id: int,
    payload: PanTransferFollowTaskSyncRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskSyncResponse:
    try:
        result = create_pan_transfer_follow_sync_batch(
            db,
            task_id=task_id,
            payload=payload.model_dump(),
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskSyncResponse(**result)
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
            detail=f"Failed to create follow sync batch: {exc}",
        ) from exc


@router.post("/follow-tasks/{task_id}/pause", response_model=PanTransferFollowTaskDetailResponse, summary="Pause a follow task")
async def pause_pan_transfer_follow_task_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    try:
        result = pause_pan_transfer_follow_task(
            db,
            task_id=task_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskDetailResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause follow task: {exc}",
        ) from exc


@router.post("/follow-tasks/{task_id}/resume", response_model=PanTransferFollowTaskDetailResponse, summary="Resume a follow task")
async def resume_pan_transfer_follow_task_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    try:
        result = resume_pan_transfer_follow_task(
            db,
            task_id=task_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskDetailResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume follow task: {exc}",
        ) from exc


@router.post(
    "/follow-tasks/{task_id}/candidate/clear",
    response_model=PanTransferFollowTaskDetailResponse,
    summary="Clear the stored candidate source for a follow task",
)
async def clear_pan_transfer_follow_task_candidate_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferFollowTaskDetailResponse:
    try:
        result = clear_pan_transfer_follow_task_candidate(
            db,
            task_id=task_id,
            operator=str(current_user.get("username") or current_user.get("account") or "admin"),
        )
        db.commit()
        return PanTransferFollowTaskDetailResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear follow task candidate: {exc}",
        ) from exc


@router.delete("/follow-tasks/{task_id}", response_model=PanTransferDeleteResponse, summary="Delete a follow task")
async def delete_pan_transfer_follow_task_api(
    task_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferDeleteResponse:
    del current_user
    try:
        result = delete_pan_transfer_follow_task(db, task_id=task_id)
        db.commit()
        return PanTransferDeleteResponse(id=result["id"], platform="follow_task", deleted=True)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete follow task: {exc}",
        ) from exc


@router.post("/batches/{batch_id}/logs/clear", response_model=PanTransferBatchDetailResponse, summary="Clear batch execution logs")
async def clear_pan_transfer_batch_logs_api(
    batch_id: int,
    current_user: dict[str, Any] = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> PanTransferBatchDetailResponse:
    del current_user
    try:
        result = clear_pan_transfer_batch_logs(db, batch_id=batch_id)
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
            detail=f"Failed to clear pan transfer batch logs: {exc}",
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
