from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    LinkTarget,
    PanTransferAccount,
    PanTransferBatch,
    PanTransferBatchItem,
    PanTransferExecutionLog,
    PanTransferReplacementLog,
    ensure_runtime_storage_tables,
)

from .accounts import get_recommended_accounts_by_platform
from .common import dedupe_ints, normalize_batch_path_strategy, normalize_positive_int, resolve_batch_item_storage_plan, utcnow
from .constants import (
    DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS,
    DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS,
    PAN_TRANSFER_BATCH_STATUS_CANCELLED,
    PAN_TRANSFER_BATCH_STATUS_DRAFT,
    PAN_TRANSFER_BATCH_STATUS_RUNNING,
    PAN_TRANSFER_ITEM_STATUS_COMPLETED,
    PAN_TRANSFER_ITEM_STATUS_FAILED,
    PAN_TRANSFER_ITEM_STATUS_PROCESSING,
    PAN_TRANSFER_ITEM_STATUS_QUEUED,
    PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
    PAN_TRANSFER_REPLACEMENT_STATUS_PENDING,
    PAN_TRANSFER_SHARE_STATUS_PENDING,
    PAN_TRANSFER_VALIDATION_STATUS_PENDING,
)
from .execution_logs import append_pan_transfer_execution_log
from .preview import collect_manual_pan_transfer_candidates, collect_manual_pan_transfer_candidates_for_link_targets
from .queue import refresh_pan_transfer_batch_summary, reset_pan_transfer_batch_items


def _normalize_retry_delay_seconds(value: Any) -> int:
    if value in (None, ""):
        return int(DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS)
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("retry_delay_seconds must be an integer") from exc
    if normalized < 0 or normalized > 86400:
        raise ValueError("retry_delay_seconds must be between 0 and 86400")
    return normalized


def _serialize_batch(batch: PanTransferBatch) -> dict[str, Any]:
    summary = dict((batch.result_json or {}).get("summary") or {})
    status = str(batch.status or "")
    active_count = int(summary.get("queued_count") or 0) + int(summary.get("processing_count") or 0) + int(summary.get("retry_wait_count") or 0)
    return {
        "id": int(batch.id),
        "batch_type": str(batch.batch_type or "manual"),
        "source_scope": str(batch.source_scope or "message_selection"),
        "status": status,
        "created_by": str(batch.created_by or "") or None,
        "total_message_count": int(batch.total_message_count or 0),
        "total_link_target_count": int(batch.total_link_target_count or 0),
        "success_item_count": int(batch.success_item_count or 0),
        "failed_item_count": int(batch.failed_item_count or 0),
        "retry_delay_seconds": int(batch.retry_delay_seconds or 0),
        "active_item_count": active_count,
        "request_json": dict(batch.request_json or {}),
        "result_json": dict(batch.result_json or {}),
        "started_at": batch.started_at,
        "finished_at": batch.finished_at,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "can_retry": bool(int(batch.failed_item_count or 0) > 0),
        "can_delete": active_count <= 0,
        "can_cancel": status == PAN_TRANSFER_BATCH_STATUS_RUNNING and active_count > 0,
    }


def _serialize_batch_item(
    item: PanTransferBatchItem,
    *,
    account: PanTransferAccount | None,
    original_target: LinkTarget | None,
    new_target: LinkTarget | None,
) -> dict[str, Any]:
    source_message_snapshot = dict(item.extra_json or {}).get("source_message_snapshot") or {}
    return {
        "id": int(item.id),
        "batch_id": int(item.batch_id),
        "link_target_id": int(item.link_target_id),
        "target_account_id": int(item.target_account_id) if item.target_account_id is not None else None,
        "target_account_name": (str(account.account_name or "") or None) if account is not None else None,
        "platform": str(item.platform or ""),
        "short_title": str(item.short_title or ""),
        "original_url": str(item.original_url or ""),
        "current_original_url": str(original_target.original_url or item.original_url or "") if original_target is not None else str(item.original_url or ""),
        "source_message_count": int(item.source_message_count or 0),
        "source_ref_count": int(item.source_ref_count or 0),
        "latest_message_title": str(item.latest_message_title or "") or None,
        "source_message_description": str(source_message_snapshot.get("description") or "") or None,
        "source_message_tags": [
            str(tag).strip()
            for tag in list(source_message_snapshot.get("tags") or [])
            if str(tag).strip()
        ],
        "latest_message_time": item.latest_message_time,
        "latest_link_health": str(item.latest_link_health or "unknown"),
        "transfer_status": str(item.transfer_status or ""),
        "share_status": str(item.share_status or ""),
        "validation_status": str(item.validation_status or ""),
        "replacement_status": str(item.replacement_status or ""),
        "attempt_count": int(item.attempt_count or 0),
        "max_attempts": int(item.max_attempts or 0),
        "next_retry_at": item.next_retry_at,
        "locked_by": str(item.locked_by or "") or None,
        "locked_at": item.locked_at,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
        "last_validated_at": item.last_validated_at,
        "new_share_url": str(item.new_share_url or "") or None,
        "new_link_target_id": int(item.new_link_target_id) if item.new_link_target_id is not None else None,
        "new_link_target_url": (str(new_target.original_url or "") or None) if new_target is not None else None,
        "error_message": str(item.error_message or "") or None,
        "extra_json": dict(item.extra_json or {}),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _serialize_execution_log(row: PanTransferExecutionLog) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "batch_id": int(row.batch_id),
        "batch_item_id": int(row.batch_item_id),
        "level": str(row.level or "info"),
        "stage": str(row.stage or "general"),
        "message": str(row.message or ""),
        "payload": dict(row.payload or {}),
        "created_at": row.created_at,
    }


def create_manual_pan_transfer_batch(
    session: Session,
    *,
    payload: dict[str, Any],
    created_by: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    candidate_result = collect_manual_pan_transfer_candidates(session, payload)
    selected_link_target_ids = dedupe_ints(payload.get("selected_link_target_ids") or [])
    all_items = list(candidate_result.get("items") or [])
    if selected_link_target_ids:
        selected_set = set(selected_link_target_ids)
        selected_items = [item for item in all_items if int(item.get("link_target_id") or 0) in selected_set]
        if not selected_items:
            selected_items = collect_manual_pan_transfer_candidates_for_link_targets(
                session,
                link_target_ids=selected_link_target_ids,
            )
    else:
        selected_items = all_items
    if not selected_items:
        raise ValueError("no transferable items selected")

    recommended_accounts = get_recommended_accounts_by_platform(session)
    missing_platforms = sorted(
        {
            str(item.get("platform") or "")
            for item in selected_items
            if not recommended_accounts.get(str(item.get("platform") or ""))
        }
    )
    if missing_platforms:
        raise ValueError(f"missing enabled pan transfer account for: {', '.join(missing_platforms)}")

    max_attempts = max(1, int(normalize_positive_int(payload.get("max_attempts"), default=DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS) or DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS))
    retry_delay_seconds = _normalize_retry_delay_seconds(payload.get("retry_delay_seconds"))
    start_immediately = bool(payload.get("start_immediately", True))
    path_strategy = normalize_batch_path_strategy(
        {
            "transfer_layout": payload.get("transfer_layout"),
            "batch_folder_name": payload.get("batch_folder_name"),
            "item_folder_mode": payload.get("item_folder_mode"),
            "item_folder_template": payload.get("item_folder_template"),
            "share_target_mode": payload.get("share_target_mode"),
        }
    )
    batch = PanTransferBatch(
        batch_type="manual",
        source_scope="message_selection",
        status=PAN_TRANSFER_BATCH_STATUS_RUNNING if start_immediately else PAN_TRANSFER_BATCH_STATUS_DRAFT,
        created_by=created_by,
        total_message_count=sum(int(item.get("impact_message_count") or 0) for item in selected_items),
        total_link_target_count=len(selected_items),
        retry_delay_seconds=retry_delay_seconds,
        request_json={
            "selection_payload": payload,
            "selection_summary": {
                key: value
                for key, value in candidate_result.items()
                if key != "items"
            },
            "selected_link_target_ids": [int(item.get("link_target_id") or 0) for item in selected_items],
            "retry_policy": {
                "max_attempts": max_attempts,
                "retry_delay_seconds": retry_delay_seconds,
            },
            "path_strategy": path_strategy,
        },
        result_json={},
        started_at=utcnow() if start_immediately else None,
    )
    session.add(batch)
    session.flush()

    created_rows: list[tuple[PanTransferBatchItem, dict[str, Any], dict[str, Any]]] = []
    for item in selected_items:
        recommended_account = recommended_accounts[str(item.get("platform") or "")]
        row = PanTransferBatchItem(
            batch_id=int(batch.id),
            link_target_id=int(item.get("link_target_id") or 0),
            target_account_id=int(recommended_account["id"]),
            platform=str(item.get("platform") or ""),
            short_title=str(item.get("short_title") or ""),
            original_url=str(item.get("original_url") or ""),
            source_message_count=int(item.get("impact_message_count") or 0),
            source_ref_count=int(item.get("source_ref_count") or 0),
            latest_message_title=str(item.get("latest_message_title") or "") or None,
            latest_message_time=item.get("latest_message_time"),
            latest_link_health=str(item.get("latest_link_health") or "unknown"),
            transfer_status=PAN_TRANSFER_ITEM_STATUS_QUEUED,
            share_status=PAN_TRANSFER_SHARE_STATUS_PENDING,
            validation_status=PAN_TRANSFER_VALIDATION_STATUS_PENDING,
            replacement_status=PAN_TRANSFER_REPLACEMENT_STATUS_PENDING,
            attempt_count=0,
            max_attempts=max_attempts,
            extra_json={
                "recommended_account_name": recommended_account.get("account_name"),
                "path_strategy": path_strategy,
                "source_message_snapshot": {
                    "title": item.get("latest_message_title"),
                    "description": item.get("latest_message_description"),
                    "tags": list(item.get("latest_message_tags") or []),
                },
            },
        )
        session.add(row)
        created_rows.append((row, item, recommended_account))
    session.flush()

    for row, item, recommended_account in created_rows:
        resolved_paths = resolve_batch_item_storage_plan(
            default_save_root=str(recommended_account.get("default_save_root") or ""),
            batch_id=int(batch.id),
            item_id=int(row.id),
            title=str(row.short_title or ""),
            platform=str(row.platform or ""),
            share_key=str(item.get("share_key") or "") or None,
            strategy=path_strategy,
        )
        row.extra_json = {
            **dict(row.extra_json or {}),
            "resolved_paths": resolved_paths,
        }
        session.add(row)
    session.flush()

    refresh_pan_transfer_batch_summary(session, batch_id=int(batch.id))
    return get_pan_transfer_batch_detail(session, batch_id=int(batch.id))


def list_pan_transfer_batches(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    query = session.query(PanTransferBatch)
    total = int(query.count() or 0)
    rows = (
        query.order_by(PanTransferBatch.created_at.desc(), PanTransferBatch.id.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return {
        "items": [_serialize_batch(row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
    }


def get_pan_transfer_batch_detail(session: Session, *, batch_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")

    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    items = (
        session.query(PanTransferBatchItem)
        .filter(PanTransferBatchItem.batch_id == int(batch_id))
        .order_by(PanTransferBatchItem.created_at.asc(), PanTransferBatchItem.id.asc())
        .all()
    )
    account_ids = dedupe_ints(item.target_account_id for item in items)
    original_target_ids = dedupe_ints(item.link_target_id for item in items)
    new_target_ids = dedupe_ints(item.new_link_target_id for item in items)

    accounts = {
        int(row.id): row
        for row in (
            session.query(PanTransferAccount)
            .filter(PanTransferAccount.id.in_(account_ids))
            .all()
            if account_ids
            else []
        )
    }
    targets = {
        int(row.id): row
        for row in (
            session.query(LinkTarget)
            .filter(LinkTarget.id.in_(original_target_ids + new_target_ids))
            .all()
            if original_target_ids or new_target_ids
            else []
        )
    }
    replacement_logs = (
        session.query(PanTransferReplacementLog)
        .filter(PanTransferReplacementLog.batch_item_id.in_(dedupe_ints(item.id for item in items)))
        .order_by(PanTransferReplacementLog.created_at.desc(), PanTransferReplacementLog.id.desc())
        .all()
        if items
        else []
    )
    execution_logs = (
        session.query(PanTransferExecutionLog)
        .filter(PanTransferExecutionLog.batch_item_id.in_(dedupe_ints(item.id for item in items)))
        .order_by(PanTransferExecutionLog.created_at.asc(), PanTransferExecutionLog.id.asc())
        .all()
        if items
        else []
    )
    replacement_log_map: dict[int, list[dict[str, Any]]] = {}
    for row in replacement_logs:
        replacement_log_map.setdefault(int(row.batch_item_id), []).append(
            {
                "id": int(row.id),
                "old_link_target_id": int(row.old_link_target_id),
                "new_link_target_id": int(row.new_link_target_id) if row.new_link_target_id is not None else None,
                "old_url": str(row.old_url or ""),
                "new_url": str(row.new_url or "") or None,
                "affected_message_count": int(row.affected_message_count or 0),
                "status": str(row.status or ""),
                "operator": str(row.operator or "") or None,
                "payload": dict(row.payload or {}),
                "created_at": row.created_at,
            }
        )
    execution_log_map: dict[int, list[dict[str, Any]]] = {}
    for row in execution_logs:
        execution_log_map.setdefault(int(row.batch_item_id), []).append(_serialize_execution_log(row))

    return {
        "batch": _serialize_batch(batch),
        "items": [
            {
                **_serialize_batch_item(
                    item,
                    account=accounts.get(int(item.target_account_id or 0)),
                    original_target=targets.get(int(item.link_target_id or 0)),
                    new_target=targets.get(int(item.new_link_target_id or 0)),
                ),
                "execution_logs": execution_log_map.get(int(item.id), []),
                "replacement_logs": replacement_log_map.get(int(item.id), []),
            }
            for item in items
        ],
    }


def start_pan_transfer_batch(session: Session, *, batch_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")
    if str(batch.status or "") != PAN_TRANSFER_BATCH_STATUS_DRAFT:
        raise ValueError("only draft batches can be started")
    batch.status = PAN_TRANSFER_BATCH_STATUS_RUNNING
    batch.started_at = batch.started_at or utcnow()
    (
        session.query(PanTransferBatchItem)
        .filter(
            PanTransferBatchItem.batch_id == int(batch_id),
            PanTransferBatchItem.transfer_status == PAN_TRANSFER_ITEM_STATUS_QUEUED,
        )
        .update({"transfer_status": PAN_TRANSFER_ITEM_STATUS_QUEUED}, synchronize_session=False)
    )
    session.add(batch)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    return get_pan_transfer_batch_detail(session, batch_id=int(batch_id))


def retry_pan_transfer_batch(
    session: Session,
    *,
    batch_id: int,
    item_ids: list[int] | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")
    reset_count = reset_pan_transfer_batch_items(session, batch_id=int(batch_id), item_ids=item_ids)
    if reset_count <= 0:
        raise ValueError("no failed items available to retry")
    batch.status = PAN_TRANSFER_BATCH_STATUS_RUNNING
    batch.finished_at = None
    session.add(batch)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    return get_pan_transfer_batch_detail(session, batch_id=int(batch_id))


def cancel_pan_transfer_batch(
    session: Session,
    *,
    batch_id: int,
    cancelled_by: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    if str(batch.status or "") != PAN_TRANSFER_BATCH_STATUS_RUNNING:
        raise ValueError("only running batches can be cancelled")

    now = utcnow()
    items = (
        session.query(PanTransferBatchItem)
        .filter(PanTransferBatchItem.batch_id == int(batch_id))
        .order_by(PanTransferBatchItem.id.asc())
        .all()
    )
    cancelled_count = 0
    processing_count = 0
    for item in items:
        item_status = str(item.transfer_status or "")
        if item_status in {PAN_TRANSFER_ITEM_STATUS_QUEUED, PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT}:
            item.transfer_status = PAN_TRANSFER_ITEM_STATUS_FAILED
            item.next_retry_at = None
            item.locked_by = None
            item.locked_at = None
            item.finished_at = now
            item.error_message = "Batch cancelled by admin"
            session.add(item)
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="finish",
                level="warning",
                message="Batch cancelled before this item started or retried",
                payload={"cancelled_by": str(cancelled_by or "") or None},
            )
            cancelled_count += 1
        elif item_status == PAN_TRANSFER_ITEM_STATUS_PROCESSING:
            processing_count += 1
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="finish",
                level="warning",
                message="Batch cancellation requested while item is processing; current attempt will finish first",
                payload={"cancelled_by": str(cancelled_by or "") or None},
            )

    batch.status = PAN_TRANSFER_BATCH_STATUS_CANCELLED
    batch.finished_at = now
    batch.result_json = {
        **dict(batch.result_json or {}),
        "cancellation": {
            "cancelled_at": now.isoformat() + "Z",
            "cancelled_by": str(cancelled_by or "") or None,
            "cancelled_item_count": cancelled_count,
            "processing_item_count": processing_count,
        },
    }
    session.add(batch)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))
    return get_pan_transfer_batch_detail(session, batch_id=int(batch_id))


def delete_pan_transfer_batch(session: Session, *, batch_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch_id))

    active_exists = bool(
        session.query(PanTransferBatchItem.id)
        .filter(
            PanTransferBatchItem.batch_id == int(batch_id),
            PanTransferBatchItem.transfer_status.in_(
                [
                    PAN_TRANSFER_ITEM_STATUS_QUEUED,
                    PAN_TRANSFER_ITEM_STATUS_PROCESSING,
                    PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
                ]
            ),
        )
        .first()
    )
    if active_exists:
        raise ValueError("cannot delete a batch while transfer items are still active; cancel it first or wait for the current processing item to finish")

    item_ids = [
        int(item_id)
        for (item_id,) in session.query(PanTransferBatchItem.id).filter(PanTransferBatchItem.batch_id == int(batch_id)).all()
    ]
    if item_ids:
        (
            session.query(PanTransferExecutionLog)
            .filter(PanTransferExecutionLog.batch_item_id.in_(item_ids))
            .delete(synchronize_session=False)
        )
        (
            session.query(PanTransferReplacementLog)
            .filter(PanTransferReplacementLog.batch_item_id.in_(item_ids))
            .delete(synchronize_session=False)
        )
        (
            session.query(PanTransferBatchItem)
            .filter(PanTransferBatchItem.id.in_(item_ids))
            .delete(synchronize_session=False)
        )
    session.delete(batch)
    session.flush()
    return {
        "id": int(batch_id),
        "deleted": True,
    }


def clear_pan_transfer_batch_logs(session: Session, *, batch_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    batch = session.get(PanTransferBatch, int(batch_id))
    if batch is None:
        raise LookupError("batch not found")

    item_ids = [
        int(item_id)
        for (item_id,) in session.query(PanTransferBatchItem.id).filter(PanTransferBatchItem.batch_id == int(batch_id)).all()
    ]
    if item_ids:
        (
            session.query(PanTransferExecutionLog)
            .filter(PanTransferExecutionLog.batch_item_id.in_(item_ids))
            .delete(synchronize_session=False)
        )
        (
            session.query(PanTransferReplacementLog)
            .filter(PanTransferReplacementLog.batch_item_id.in_(item_ids))
            .delete(synchronize_session=False)
        )
    session.flush()
    return get_pan_transfer_batch_detail(session, batch_id=int(batch_id))
