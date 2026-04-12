from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.models import PanTransferBatch, PanTransferBatchItem, ensure_runtime_storage_tables

from .common import dedupe_ints, utcnow
from .constants import (
    DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS,
    DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS,
    DEFAULT_PAN_TRANSFER_STALE_LOCK_SECONDS,
    PAN_TRANSFER_BATCH_STATUS_COMPLETED,
    PAN_TRANSFER_BATCH_STATUS_COMPLETED_WITH_ERRORS,
    PAN_TRANSFER_BATCH_STATUS_DRAFT,
    PAN_TRANSFER_BATCH_STATUS_FAILED,
    PAN_TRANSFER_BATCH_STATUS_RUNNING,
    PAN_TRANSFER_ITEM_STATUS_COMPLETED,
    PAN_TRANSFER_ITEM_STATUS_FAILED,
    PAN_TRANSFER_ITEM_STATUS_PROCESSING,
    PAN_TRANSFER_ITEM_STATUS_QUEUED,
    PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
)


def refresh_pan_transfer_batch_summary(session: Session, *, batch_id: int) -> PanTransferBatch:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")

    rows = (
        session.query(
            PanTransferBatchItem.transfer_status,
            func.count(PanTransferBatchItem.id),
        )
        .filter(PanTransferBatchItem.batch_id == int(batch_id))
        .group_by(PanTransferBatchItem.transfer_status)
        .all()
    )
    counts = {str(status or ""): int(total or 0) for status, total in rows}
    total_count = int(sum(counts.values()))
    queued_count = counts.get(PAN_TRANSFER_ITEM_STATUS_QUEUED, 0)
    processing_count = counts.get(PAN_TRANSFER_ITEM_STATUS_PROCESSING, 0)
    retry_wait_count = counts.get(PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT, 0)
    completed_count = counts.get(PAN_TRANSFER_ITEM_STATUS_COMPLETED, 0)
    failed_count = counts.get(PAN_TRANSFER_ITEM_STATUS_FAILED, 0)

    batch.success_item_count = completed_count
    batch.failed_item_count = failed_count
    batch.total_link_target_count = total_count

    current_status = str(batch.status or "")
    if total_count == 0 and current_status == PAN_TRANSFER_BATCH_STATUS_DRAFT:
        next_status = PAN_TRANSFER_BATCH_STATUS_DRAFT
    elif (
        current_status == PAN_TRANSFER_BATCH_STATUS_DRAFT
        and queued_count == total_count
        and processing_count == 0
        and retry_wait_count == 0
        and completed_count == 0
        and failed_count == 0
    ):
        next_status = PAN_TRANSFER_BATCH_STATUS_DRAFT
    elif queued_count or processing_count or retry_wait_count:
        next_status = PAN_TRANSFER_BATCH_STATUS_RUNNING
    elif total_count > 0 and completed_count == total_count:
        next_status = PAN_TRANSFER_BATCH_STATUS_COMPLETED
    elif total_count > 0 and failed_count == total_count:
        next_status = PAN_TRANSFER_BATCH_STATUS_FAILED
    elif total_count > 0 and completed_count + failed_count == total_count:
        next_status = PAN_TRANSFER_BATCH_STATUS_COMPLETED_WITH_ERRORS
    else:
        next_status = PAN_TRANSFER_BATCH_STATUS_RUNNING

    now = utcnow()
    if next_status == PAN_TRANSFER_BATCH_STATUS_RUNNING and batch.started_at is None:
        batch.started_at = now
    if next_status in {
        PAN_TRANSFER_BATCH_STATUS_COMPLETED,
        PAN_TRANSFER_BATCH_STATUS_COMPLETED_WITH_ERRORS,
        PAN_TRANSFER_BATCH_STATUS_FAILED,
    }:
        batch.finished_at = now
    else:
        batch.finished_at = None
    batch.status = next_status
    batch.result_json = {
        **dict(batch.result_json or {}),
        "summary": {
            "total_count": total_count,
            "queued_count": queued_count,
            "processing_count": processing_count,
            "retry_wait_count": retry_wait_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
        },
    }
    session.add(batch)
    session.flush()
    return batch


def recycle_stale_pan_transfer_locks(
    session: Session,
    *,
    stale_seconds: int = DEFAULT_PAN_TRANSFER_STALE_LOCK_SECONDS,
) -> int:
    ensure_runtime_storage_tables()
    stale_before = utcnow() - timedelta(seconds=max(60, int(stale_seconds or DEFAULT_PAN_TRANSFER_STALE_LOCK_SECONDS)))
    rows = (
        session.query(PanTransferBatchItem)
        .filter(
            PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_PROCESSING,
            PanTransferBatchItem.locked_at.isnot(None),
            PanTransferBatchItem.locked_at < stale_before,
        )
        .all()
    )
    recycled = 0
    for row in rows:
        row.transfer_status = PAN_TRANSFER_ITEM_STATUS_QUEUED
        row.locked_by = None
        row.locked_at = None
        row.started_at = None
        row.error_message = "Worker exited before finishing the transfer item"
        session.add(row)
        recycled += 1
    if recycled:
        session.flush()
        affected_batch_ids = dedupe_ints(row.batch_id for row in rows)
        for batch_id in affected_batch_ids:
            refresh_pan_transfer_batch_summary(session, batch_id=batch_id)
    return recycled


def claim_next_pan_transfer_batch_item(session: Session, *, worker_name: str) -> PanTransferBatchItem | None:
    ensure_runtime_storage_tables()
    recycle_stale_pan_transfer_locks(session)
    now = utcnow()
    candidate = (
        session.query(PanTransferBatchItem)
        .join(PanTransferBatch, PanTransferBatch.id == PanTransferBatchItem.batch_id)
        .filter(
            PanTransferBatch.status == PAN_TRANSFER_BATCH_STATUS_RUNNING,
            or_(
                PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_QUEUED,
                and_(
                    PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
                    PanTransferBatchItem.next_retry_at.isnot(None),
                    PanTransferBatchItem.next_retry_at <= now,
                ),
            ),
        )
        .order_by(
            case((PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_QUEUED, 0), else_=1),
            PanTransferBatch.created_at.asc(),
            PanTransferBatchItem.created_at.asc(),
            PanTransferBatchItem.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if candidate is None:
        return None

    candidate.transfer_status = PAN_TRANSFER_ITEM_STATUS_PROCESSING
    candidate.locked_by = str(worker_name or "tg-worker")[:128]
    candidate.locked_at = now
    candidate.started_at = now
    candidate.finished_at = None
    candidate.error_message = None
    session.add(candidate)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(candidate.batch_id))
    return candidate


def mark_pan_transfer_item_success(
    session: Session,
    *,
    item: PanTransferBatchItem,
) -> None:
    now = utcnow()
    item.transfer_status = PAN_TRANSFER_ITEM_STATUS_COMPLETED
    item.attempt_count = max(1, int(item.attempt_count or 0) + 1)
    item.next_retry_at = None
    item.locked_by = None
    item.locked_at = None
    item.finished_at = now
    session.add(item)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(item.batch_id))


def mark_pan_transfer_item_error(
    session: Session,
    *,
    item: PanTransferBatchItem,
    error_message: str,
    retryable: bool = True,
    retry_delay_seconds: int = DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS,
    max_attempts: int | None = None,
) -> None:
    now = utcnow()
    item.attempt_count = max(1, int(item.attempt_count or 0) + 1)
    item.error_message = str(error_message or "Pan transfer execution failed").strip()[:2000]
    item.locked_by = None
    item.locked_at = None
    item.finished_at = now
    item.max_attempts = max(1, int(max_attempts or item.max_attempts or DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS))
    if retryable and int(item.attempt_count or 0) < int(item.max_attempts or DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS):
        item.transfer_status = PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT
        item.next_retry_at = now + timedelta(seconds=max(60, int(retry_delay_seconds or DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS)))
    else:
        item.transfer_status = PAN_TRANSFER_ITEM_STATUS_FAILED
        item.next_retry_at = None
    session.add(item)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(item.batch_id))


def reset_pan_transfer_batch_items(
    session: Session,
    *,
    batch_id: int,
    item_ids: Iterable[int] | None = None,
) -> int:
    ensure_runtime_storage_tables()
    query = session.query(PanTransferBatchItem).filter(PanTransferBatchItem.batch_id == int(batch_id))
    normalized_item_ids = dedupe_ints(item_ids or [])
    if normalized_item_ids:
        query = query.filter(PanTransferBatchItem.id.in_(normalized_item_ids))
    rows = query.filter(PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_FAILED).all()
    if not rows:
        return 0
    now = utcnow()
    for row in rows:
        row.transfer_status = PAN_TRANSFER_ITEM_STATUS_QUEUED
        if str(row.new_share_url or "").strip():
            row.share_status = "shared"
            row.validation_status = "pending"
            row.replacement_status = "pending"
        else:
            row.share_status = "pending"
            row.validation_status = "pending"
            row.replacement_status = "pending"
            row.new_link_target_id = None
        row.next_retry_at = None
        row.locked_by = None
        row.locked_at = None
        row.started_at = None
        row.finished_at = None
        row.error_message = None
        row.updated_at = now
        session.add(row)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    return len(rows)
