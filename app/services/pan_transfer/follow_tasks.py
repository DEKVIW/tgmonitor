from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models.models import (
    LinkTarget,
    Message,
    MessageLinkRef,
    PanTransferAccount,
    PanTransferBatchItem,
    PanTransferPublishRecord,
    PanTransferSyncTask,
    PanTransferSyncTaskLog,
    ResourceWorkBinding,
    ensure_runtime_storage_tables,
)
from app.services.resource_ops import get_work_binding_lookup

from .common import normalize_relative_path, utcnow
from .validation import validate_share_url


PAN_TRANSFER_SYNC_STATUS_ACTIVE = "active"
PAN_TRANSFER_SYNC_STATUS_PAUSED = "paused"

PAN_TRANSFER_SYNC_STATE_IDLE = "idle"
PAN_TRANSFER_SYNC_STATE_QUEUED = "queued"
PAN_TRANSFER_SYNC_STATE_CHECKING = "checking"
PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND = "candidate_found"
PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED = "sync_queued"
PAN_TRANSFER_SYNC_STATE_SOURCE_INVALID = "source_invalid"
PAN_TRANSFER_SYNC_STATE_SHARE_INVALID = "share_invalid"
PAN_TRANSFER_SYNC_STATE_ERROR = "error"

PAN_TRANSFER_SYNC_ALLOWED_STATUS = {
    PAN_TRANSFER_SYNC_STATUS_ACTIVE,
    PAN_TRANSFER_SYNC_STATUS_PAUSED,
}

PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES = 6 * 60
PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES = 15
PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES = 7 * 24 * 60
PAN_TRANSFER_SYNC_CANDIDATE_LOOKBACK_DAYS = 30


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_interval_minutes(value: Any) -> int:
    if value in (None, ""):
        return PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("check_interval_minutes must be an integer") from exc
    if normalized < PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES or normalized > PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES:
        raise ValueError(
            f"check_interval_minutes must be between {PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES} and {PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES}"
        )
    return normalized


def _next_check_time(*, interval_minutes: int) -> Any:
    return utcnow() + timedelta(minutes=max(PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES, int(interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES)))


def _append_follow_task_log(
    session: Session,
    *,
    task: PanTransferSyncTask,
    stage: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        PanTransferSyncTaskLog(
            task_id=int(task.id),
            level=_normalize_text(level, max_length=16) or "info",
            stage=_normalize_text(stage, max_length=32) or "general",
            message=_normalize_text(message, max_length=4000),
            payload=dict(payload or {}),
        )
    )
    session.flush()


def _serialize_follow_task_log(row: PanTransferSyncTaskLog) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "task_id": int(row.task_id),
        "level": str(row.level or "info"),
        "stage": str(row.stage or "general"),
        "message": str(row.message or ""),
        "payload": dict(row.payload or {}),
        "created_at": row.created_at,
    }


def _build_task_automation_config(raw_value: Any) -> dict[str, Any]:
    raw = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    switch_source_mode = _normalize_text(raw.get("switch_source_mode"), max_length=64).lower() or "source_invalid_only"
    if switch_source_mode not in {"disabled", "source_invalid_only", "candidate_preferred"}:
        switch_source_mode = "source_invalid_only"
    return {
        "enabled": bool(raw.get("enabled")),
        "switch_source_mode": switch_source_mode,
        "reuse_existing_share_if_valid": bool(raw.get("reuse_existing_share_if_valid", True)),
        "update_publish_record": bool(raw.get("update_publish_record", True)),
    }


def _build_follow_publish_binding_snapshot(row: PanTransferPublishRecord | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "record_id": int(row.id),
        "published_title": _normalize_text(row.published_title, max_length=255) or None,
        "published_message_id": int(row.published_message_id) if row.published_message_id is not None else None,
        "published_at": row.published_at.isoformat() if row.published_at is not None else None,
        "source_url": _normalize_text(row.source_url) or None,
    }


def _sync_follow_task_publish_binding(
    task: PanTransferSyncTask,
    *,
    publish_record: PanTransferPublishRecord | None,
) -> None:
    extra_json = dict(task.extra_json or {})
    extra_json["publish_binding"] = _build_follow_publish_binding_snapshot(publish_record)
    task.publish_record_id = int(publish_record.id) if publish_record is not None else None
    task.extra_json = extra_json


def _find_follow_task_publish_record(
    session: Session,
    *,
    task: PanTransferSyncTask,
) -> PanTransferPublishRecord | None:
    if task.publish_record_id is not None:
        row = session.get(PanTransferPublishRecord, int(task.publish_record_id))
        if row is not None:
            return row
    if task.source_batch_item_id is None:
        return None
    return (
        session.query(PanTransferPublishRecord)
        .filter(PanTransferPublishRecord.source_batch_item_id == int(task.source_batch_item_id))
        .order_by(PanTransferPublishRecord.updated_at.desc(), PanTransferPublishRecord.id.desc())
        .first()
    )


def bind_follow_task_publish_record(
    session: Session,
    *,
    task: PanTransferSyncTask,
) -> PanTransferPublishRecord | None:
    publish_record = _find_follow_task_publish_record(session, task=task)
    _sync_follow_task_publish_binding(task, publish_record=publish_record)
    session.add(task)
    session.flush()
    return publish_record


def _serialize_follow_task(row: PanTransferSyncTask) -> dict[str, Any]:
    extra_json = dict(row.extra_json or {})
    publish_binding = dict(extra_json.get("publish_binding") or {})
    last_sync = dict(extra_json.get("last_sync") or {})
    return {
        "id": int(row.id),
        "task_name": str(row.task_name or ""),
        "status": str(row.status or PAN_TRANSFER_SYNC_STATUS_ACTIVE),
        "task_state": str(row.task_state or PAN_TRANSFER_SYNC_STATE_IDLE),
        "platform": str(row.platform or ""),
        "source_batch_id": int(row.source_batch_id) if row.source_batch_id is not None else None,
        "source_batch_item_id": int(row.source_batch_item_id) if row.source_batch_item_id is not None else None,
        "source_link_target_id": int(row.source_link_target_id) if row.source_link_target_id is not None else None,
        "source_url": str(row.source_url or ""),
        "source_share_key": str(row.source_share_key or "") or None,
        "topic_key": str(row.topic_key or ""),
        "topic_title": str(row.topic_title or ""),
        "work_id": int(row.work_id) if row.work_id is not None else None,
        "work_title": str(row.work_title or "") or None,
        "publish_record_id": int(row.publish_record_id) if row.publish_record_id is not None else _normalize_optional_int(publish_binding.get("record_id")),
        "publish_record_title": _normalize_text(publish_binding.get("published_title"), max_length=255) or None,
        "publish_record_message_id": _normalize_optional_int(publish_binding.get("published_message_id")),
        "publish_record_published_at": _parse_datetime(publish_binding.get("published_at")),
        "publish_record_source_url": _normalize_text(publish_binding.get("source_url")) or None,
        "target_account_id": int(row.target_account_id) if row.target_account_id is not None else None,
        "target_account_name": str(row.target_account_name or "") or None,
        "fixed_save_path": str(row.fixed_save_path or ""),
        "transfer_layout": str(row.transfer_layout or "independent"),
        "batch_folder_name": str(row.batch_folder_name or "") or None,
        "item_folder_mode": str(row.item_folder_mode or "auto"),
        "item_folder_template": str(row.item_folder_template or "") or None,
        "share_target_mode": str(row.share_target_mode or "resource_dir"),
        "current_share_url": str(row.current_share_url or "") or None,
        "current_share_link_target_id": int(row.current_share_link_target_id) if row.current_share_link_target_id is not None else None,
        "source_link_status": str(row.source_link_status or "unknown"),
        "current_share_status": str(row.current_share_status or "unknown"),
        "last_change_type": str(row.last_change_type or "") or None,
        "last_candidate_link_target_id": int(row.last_candidate_link_target_id) if row.last_candidate_link_target_id is not None else None,
        "last_candidate_url": str(row.last_candidate_url or "") or None,
        "last_candidate_title": str(row.last_candidate_title or "") or None,
        "last_candidate_message_time": row.last_candidate_message_time,
        "check_interval_minutes": int(row.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES),
        "last_checked_at": row.last_checked_at,
        "next_check_at": row.next_check_at,
        "locked_by": str(row.locked_by or "") or None,
        "locked_at": row.locked_at,
        "last_error_message": str(row.last_error_message or "") or None,
        "last_sync_batch_id": _normalize_optional_int(last_sync.get("batch_id")),
        "last_sync_batch_item_id": _normalize_optional_int(last_sync.get("batch_item_id")),
        "last_sync_source_kind": _normalize_text(last_sync.get("source_kind"), max_length=32) or None,
        "last_sync_started_at": _parse_datetime(last_sync.get("started_at")),
        "extra_json": extra_json,
        "created_by": str(row.created_by or "") or None,
        "updated_by": str(row.updated_by or "") or None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _get_follow_task(session: Session, *, task_id: int) -> PanTransferSyncTask:
    task = session.get(PanTransferSyncTask, int(task_id))
    if task is None:
        raise LookupError("follow task not found")
    return task


def _get_follow_task_logs(session: Session, *, task_id: int) -> list[dict[str, Any]]:
    rows = (
        session.query(PanTransferSyncTaskLog)
        .filter(PanTransferSyncTaskLog.task_id == int(task_id))
        .order_by(PanTransferSyncTaskLog.created_at.asc(), PanTransferSyncTaskLog.id.asc())
        .all()
    )
    return [_serialize_follow_task_log(row) for row in rows]


def get_pan_transfer_follow_task_detail(session: Session, *, task_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    return {
        "task": _serialize_follow_task(task),
        "logs": _get_follow_task_logs(session, task_id=int(task.id)),
    }


def list_pan_transfer_follow_tasks(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    query = session.query(PanTransferSyncTask)
    normalized_status = _normalize_text(status, max_length=32).lower()
    if normalized_status in PAN_TRANSFER_SYNC_ALLOWED_STATUS:
        query = query.filter(PanTransferSyncTask.status == normalized_status)
    total = int(query.count() or 0)
    rows = (
        query.order_by(
            PanTransferSyncTask.updated_at.desc(),
            PanTransferSyncTask.next_check_at.asc().nullslast(),
            PanTransferSyncTask.id.desc(),
        )
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return {
        "items": [_serialize_follow_task(row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
    }


def _build_follow_topic_payload(
    session: Session,
    *,
    item: PanTransferBatchItem,
) -> dict[str, Any]:
    lookup = get_work_binding_lookup(session, link_target_ids=[int(item.link_target_id)]).get(int(item.link_target_id), {})
    work_id = lookup.get("work_id")
    work_title = _normalize_text(lookup.get("work_title"), max_length=255) or None
    if work_id and work_title:
        return {
            "work_id": int(work_id),
            "work_title": work_title,
            "topic_key": f"work:{int(work_id)}",
            "topic_title": work_title,
        }
    topic_title = _normalize_text(item.short_title, max_length=255) or _normalize_text(item.latest_message_title, max_length=255) or f"资源 {int(item.link_target_id)}"
    return {
        "work_id": None,
        "work_title": None,
        "topic_key": f"link:{int(item.link_target_id)}",
        "topic_title": topic_title,
    }


def create_pan_transfer_follow_task_from_batch_item(
    session: Session,
    *,
    batch_id: int,
    item_id: int,
    payload: dict[str, Any] | None,
    created_by: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    item = (
        session.query(PanTransferBatchItem)
        .filter(
            PanTransferBatchItem.batch_id == int(batch_id),
            PanTransferBatchItem.id == int(item_id),
        )
        .first()
    )
    if item is None:
        raise LookupError("pan transfer batch item not found")

    existing = (
        session.query(PanTransferSyncTask)
        .filter(
            PanTransferSyncTask.status.in_([PAN_TRANSFER_SYNC_STATUS_ACTIVE, PAN_TRANSFER_SYNC_STATUS_PAUSED]),
            or_(
                PanTransferSyncTask.source_batch_item_id == int(item.id),
                PanTransferSyncTask.source_link_target_id == int(item.link_target_id),
            ),
        )
        .first()
    )
    if existing is not None:
        raise ValueError(f"follow task #{int(existing.id)} already exists for this resource")

    source_target = session.get(LinkTarget, int(item.link_target_id))
    current_share_target = session.get(LinkTarget, int(item.new_link_target_id)) if item.new_link_target_id is not None else None
    account = session.get(PanTransferAccount, int(item.target_account_id)) if item.target_account_id is not None else None
    extra_json = dict(item.extra_json or {})
    resolved_paths = dict(extra_json.get("resolved_paths") or {})
    path_strategy = dict(extra_json.get("path_strategy") or {})
    share_validation = dict(extra_json.get("share_validation") or {})
    topic_payload = _build_follow_topic_payload(session, item=item)
    interval_minutes = _normalize_interval_minutes((payload or {}).get("check_interval_minutes"))
    task_name = (
        _normalize_text((payload or {}).get("task_name"), max_length=255)
        or topic_payload["topic_title"]
        or _normalize_text(item.short_title, max_length=255)
        or f"追更任务 {int(item.id)}"
    )
    source_url = (
        _normalize_text(getattr(source_target, "original_url", None))
        or _normalize_text(item.original_url)
    )
    if not source_url:
        raise ValueError("source url is missing")

    current_share_url = (
        _normalize_text(getattr(current_share_target, "original_url", None))
        or _normalize_text(item.new_share_url)
        or source_url
    )
    current_share_link_target_id = (
        int(item.new_link_target_id)
        if item.new_link_target_id is not None
        else (int(item.link_target_id) if source_url == current_share_url else None)
    )
    fixed_save_path = normalize_relative_path(_normalize_text(resolved_paths.get("resolved_path"), max_length=512))
    source_share_key = _normalize_text(getattr(source_target, "share_key", None), max_length=255) or None
    current_share_status = _normalize_text(share_validation.get("status"), max_length=32).lower() or (
        _normalize_text(item.latest_link_health, max_length=32).lower() if current_share_url == source_url else "unknown"
    )
    publish_record = (
        session.query(PanTransferPublishRecord)
        .filter(PanTransferPublishRecord.source_batch_item_id == int(item.id))
        .order_by(PanTransferPublishRecord.updated_at.desc(), PanTransferPublishRecord.id.desc())
        .first()
    )
    task = PanTransferSyncTask(
        task_name=task_name,
        status=PAN_TRANSFER_SYNC_STATUS_ACTIVE,
        task_state=PAN_TRANSFER_SYNC_STATE_QUEUED,
        platform=str(item.platform or ""),
        source_batch_id=int(item.batch_id),
        source_batch_item_id=int(item.id),
        source_link_target_id=int(item.link_target_id),
        source_url=source_url,
        source_share_key=source_share_key,
        topic_key=str(topic_payload["topic_key"]),
        topic_title=str(topic_payload["topic_title"]),
        work_id=int(topic_payload["work_id"]) if topic_payload["work_id"] is not None else None,
        work_title=str(topic_payload["work_title"] or "") or None,
        publish_record_id=int(publish_record.id) if publish_record is not None else None,
        target_account_id=int(item.target_account_id) if item.target_account_id is not None else None,
        target_account_name=_normalize_text(getattr(account, "account_name", None), max_length=128) or _normalize_text(extra_json.get("recommended_account_name"), max_length=128) or None,
        fixed_save_path=fixed_save_path,
        transfer_layout=_normalize_text(resolved_paths.get("transfer_layout"), max_length=32) or _normalize_text(path_strategy.get("transfer_layout"), max_length=32) or "independent",
        batch_folder_name=_normalize_text(resolved_paths.get("batch_folder_name"), max_length=120) or None,
        item_folder_mode=_normalize_text(path_strategy.get("item_folder_mode"), max_length=32) or "auto",
        item_folder_template=_normalize_text(path_strategy.get("item_folder_template"), max_length=120) or None,
        share_target_mode=_normalize_text(resolved_paths.get("share_target_mode"), max_length=32) or _normalize_text(path_strategy.get("share_target_mode"), max_length=32) or "resource_dir",
        current_share_url=current_share_url or None,
        current_share_link_target_id=current_share_link_target_id,
        source_link_status=_normalize_text(item.latest_link_health, max_length=32).lower() or "unknown",
        current_share_status=current_share_status or "unknown",
        check_interval_minutes=interval_minutes,
        next_check_at=utcnow(),
        extra_json={
            "source_message_snapshot": dict(extra_json.get("source_message_snapshot") or {}),
            "path_strategy": path_strategy,
            "resolved_paths": resolved_paths,
            "publish_binding": _build_follow_publish_binding_snapshot(publish_record),
            "automation": _build_task_automation_config((payload or {}).get("automation")),
            "created_from_batch_item": {
                "batch_id": int(item.batch_id),
                "item_id": int(item.id),
            },
        },
        created_by=_normalize_text(created_by, max_length=128) or None,
        updated_by=_normalize_text(created_by, max_length=128) or None,
    )
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="setup",
        message="Follow task created from transfer batch item",
        payload={
            "source_batch_id": int(item.batch_id),
            "source_batch_item_id": int(item.id),
            "source_url": source_url,
            "current_share_url": current_share_url,
            "fixed_save_path": fixed_save_path,
        },
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def queue_pan_transfer_follow_task_check(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    if str(task.status or "") != PAN_TRANSFER_SYNC_STATUS_ACTIVE:
        raise ValueError("only active follow tasks can be queued")
    task.task_state = PAN_TRANSFER_SYNC_STATE_QUEUED
    task.next_check_at = utcnow()
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="queue",
        message="Follow task queued for immediate check",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def pause_pan_transfer_follow_task(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    task = _get_follow_task(session, task_id=task_id)
    task.status = PAN_TRANSFER_SYNC_STATUS_PAUSED
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    task.next_check_at = None
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="control",
        message="Follow task paused",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def resume_pan_transfer_follow_task(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    task = _get_follow_task(session, task_id=task_id)
    task.status = PAN_TRANSFER_SYNC_STATUS_ACTIVE
    task.task_state = PAN_TRANSFER_SYNC_STATE_QUEUED
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    task.next_check_at = utcnow()
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="control",
        message="Follow task resumed and queued",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def delete_pan_transfer_follow_task(session: Session, *, task_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    (
        session.query(PanTransferSyncTaskLog)
        .filter(PanTransferSyncTaskLog.task_id == int(task.id))
        .delete(synchronize_session=False)
    )
    session.delete(task)
    session.flush()
    return {"id": int(task_id), "deleted": True}


def _build_task_excluded_target_ids(task: PanTransferSyncTask) -> list[int]:
    excluded: list[int] = []
    for raw_value in [task.source_link_target_id, task.current_share_link_target_id, task.last_candidate_link_target_id]:
        if raw_value is None:
            continue
        value = int(raw_value)
        if value <= 0 or value in excluded:
            continue
        excluded.append(value)
    return excluded


def _find_follow_candidate_by_work(session: Session, *, task: PanTransferSyncTask) -> dict[str, Any] | None:
    if task.work_id is None:
        return None
    excluded_ids = _build_task_excluded_target_ids(task)
    earliest_message_time = utcnow() - timedelta(days=PAN_TRANSFER_SYNC_CANDIDATE_LOOKBACK_DAYS)
    latest_ref_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.id).label("latest_ref_id"),
        )
        .filter(
            or_(
                MessageLinkRef.message_timestamp.is_(None),
                MessageLinkRef.message_timestamp >= earliest_message_time,
            )
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )
    latest_ref = aliased(MessageLinkRef)
    latest_message = aliased(Message)
    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.original_url.label("original_url"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            latest_ref.message_timestamp.label("latest_message_time"),
        )
        .join(ResourceWorkBinding, ResourceWorkBinding.link_target_id == LinkTarget.id)
        .join(latest_ref_subquery, latest_ref_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .filter(
            ResourceWorkBinding.work_id == int(task.work_id),
            ResourceWorkBinding.match_status == "matched",
            LinkTarget.platform == str(task.platform or ""),
        )
        .order_by(latest_ref.message_timestamp.desc().nullslast(), LinkTarget.last_seen_at.desc(), LinkTarget.id.desc())
    )
    if excluded_ids:
        query = query.filter(~LinkTarget.id.in_(excluded_ids))
    row = query.first()
    if row is None:
        return None
    return {
        "link_target_id": int(row.link_target_id),
        "url": _normalize_text(row.original_url),
        "title": _normalize_text(row.latest_message_title, max_length=255) or _normalize_text(row.display_text, max_length=255) or _normalize_text(task.topic_title, max_length=255),
        "latest_message_time": row.latest_message_time,
    }


def _find_follow_candidate_by_topic_title(session: Session, *, task: PanTransferSyncTask) -> dict[str, Any] | None:
    topic_title = _normalize_text(task.topic_title, max_length=120)
    if len(topic_title) < 4:
        return None
    excluded_ids = _build_task_excluded_target_ids(task)
    earliest_message_time = utcnow() - timedelta(days=PAN_TRANSFER_SYNC_CANDIDATE_LOOKBACK_DAYS)
    latest_ref_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.id).label("latest_ref_id"),
        )
        .filter(
            or_(
                MessageLinkRef.message_timestamp.is_(None),
                MessageLinkRef.message_timestamp >= earliest_message_time,
            )
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )
    latest_ref = aliased(MessageLinkRef)
    latest_message = aliased(Message)
    like_pattern = f"%{topic_title}%"
    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.original_url.label("original_url"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            latest_ref.message_timestamp.label("latest_message_time"),
        )
        .join(latest_ref_subquery, latest_ref_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .filter(
            LinkTarget.platform == str(task.platform or ""),
            or_(
                latest_message.title.ilike(like_pattern),
                latest_message.description.ilike(like_pattern),
                latest_ref.display_text.ilike(like_pattern),
            ),
        )
        .order_by(latest_ref.message_timestamp.desc().nullslast(), LinkTarget.last_seen_at.desc(), LinkTarget.id.desc())
    )
    if excluded_ids:
        query = query.filter(~LinkTarget.id.in_(excluded_ids))
    row = query.first()
    if row is None:
        return None
    return {
        "link_target_id": int(row.link_target_id),
        "url": _normalize_text(row.original_url),
        "title": _normalize_text(row.latest_message_title, max_length=255) or _normalize_text(row.display_text, max_length=255) or topic_title,
        "latest_message_time": row.latest_message_time,
    }


async def _safe_validate_url(url: str | None) -> dict[str, Any]:
    normalized_url = _normalize_text(url)
    if not normalized_url:
        return {"status": "unknown", "detail_message": None, "result": None}
    try:
        return await validate_share_url(normalized_url)
    except Exception as exc:
        return {
            "status": "error",
            "detail_message": _normalize_text(exc, max_length=1000) or type(exc).__name__,
            "result": None,
        }


async def _process_pan_transfer_follow_task_async(
    session: Session,
    *,
    task: PanTransferSyncTask,
    worker_name: str,
) -> None:
    _append_follow_task_log(
        session,
        task=task,
        stage="check",
        message="Starting follow task check",
        payload={
            "worker_name": worker_name,
            "source_url": str(task.source_url or ""),
            "current_share_url": str(task.current_share_url or "") or None,
        },
    )

    source_status = await _safe_validate_url(task.source_url)
    task.source_link_status = _normalize_text(source_status.get("status"), max_length=32).lower() or "unknown"
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="source",
        message=f"Source link validation finished with status: {task.source_link_status}",
        level="warning" if task.source_link_status in {"invalid", "error"} else "info",
        payload=dict(source_status),
    )

    share_status = await _safe_validate_url(task.current_share_url)
    task.current_share_status = _normalize_text(share_status.get("status"), max_length=32).lower() or "unknown"
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="share",
        message=f"Current share validation finished with status: {task.current_share_status}",
        level="warning" if task.current_share_status in {"invalid", "error"} else "info",
        payload=dict(share_status),
    )

    candidate = _find_follow_candidate_by_work(session, task=task) or _find_follow_candidate_by_topic_title(session, task=task)
    if candidate is not None:
        task.task_state = PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND
        task.last_change_type = "candidate_found"
        task.last_candidate_link_target_id = int(candidate["link_target_id"])
        task.last_candidate_url = str(candidate["url"])
        task.last_candidate_title = str(candidate["title"])
        task.last_candidate_message_time = candidate.get("latest_message_time")
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            message="Detected a recent candidate source link for this tracked resource",
            payload=dict(candidate),
        )
    elif task.source_link_status == "invalid":
        task.task_state = PAN_TRANSFER_SYNC_STATE_SOURCE_INVALID
        task.last_change_type = "source_invalid"
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            level="warning",
            message="No new candidate found and the current source link is invalid",
        )
    elif task.current_share_url and task.current_share_status == "invalid":
        task.task_state = PAN_TRANSFER_SYNC_STATE_SHARE_INVALID
        task.last_change_type = "share_invalid"
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            level="warning",
            message="No new candidate found and the current outward share is invalid",
        )
    else:
        task.task_state = PAN_TRANSFER_SYNC_STATE_IDLE
        task.last_change_type = "no_change"
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            message="No recent candidate source link was found for this check",
        )


def process_next_pan_transfer_follow_task(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    now = utcnow()
    task = (
        session.query(PanTransferSyncTask)
        .filter(
            PanTransferSyncTask.status == PAN_TRANSFER_SYNC_STATUS_ACTIVE,
            PanTransferSyncTask.next_check_at.isnot(None),
            PanTransferSyncTask.next_check_at <= now,
        )
        .order_by(PanTransferSyncTask.next_check_at.asc(), PanTransferSyncTask.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if task is None:
        return False

    task.task_state = PAN_TRANSFER_SYNC_STATE_CHECKING
    task.locked_by = worker_name[:128]
    task.locked_at = now
    task.updated_by = worker_name[:128]
    task.last_error_message = None
    session.add(task)
    session.flush()

    try:
        asyncio.run(_process_pan_transfer_follow_task_async(session, task=task, worker_name=worker_name))
        task.locked_by = None
        task.locked_at = None
        task.last_checked_at = utcnow()
        task.next_check_at = _next_check_time(interval_minutes=int(task.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES))
        task.last_error_message = None
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="finish",
            message="Follow task check completed",
            payload={
                "task_state": str(task.task_state or ""),
                "next_check_at": task.next_check_at.isoformat() + "Z" if task.next_check_at is not None else None,
            },
        )
        return True
    except Exception as exc:
        error_message = _normalize_text(exc, max_length=2000) or type(exc).__name__
        task.task_state = PAN_TRANSFER_SYNC_STATE_ERROR
        task.locked_by = None
        task.locked_at = None
        task.last_checked_at = utcnow()
        task.next_check_at = _next_check_time(interval_minutes=int(task.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES))
        task.last_error_message = error_message
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="finish",
            level="error",
            message=f"Follow task check failed: {error_message}",
            payload={
                "error_type": type(exc).__name__,
                "next_check_at": task.next_check_at.isoformat() + "Z" if task.next_check_at is not None else None,
            },
        )
        return True
