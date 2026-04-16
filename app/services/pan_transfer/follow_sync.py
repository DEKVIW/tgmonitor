from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    LinkTarget,
    PanTransferAccount,
    PanTransferBatch,
    PanTransferBatchItem,
    PanTransferPublishRecord,
    PanTransferSyncTask,
    ensure_runtime_storage_tables,
)

from .common import normalize_relative_path, utcnow
from .constants import (
    DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS,
    DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS,
    PAN_TRANSFER_BATCH_STATUS_RUNNING,
    PAN_TRANSFER_ITEM_STATUS_QUEUED,
    PAN_TRANSFER_REPLACEMENT_STATUS_PENDING,
    PAN_TRANSFER_SHARE_STATUS_PENDING,
    PAN_TRANSFER_VALIDATION_STATUS_PENDING,
)
from .follow_tasks import (
    PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND,
    PAN_TRANSFER_SYNC_STATE_ERROR,
    PAN_TRANSFER_SYNC_STATE_IDLE,
    PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED,
    _append_follow_task_log,
    _apply_follow_task_state_without_candidate,
    _clear_follow_task_candidate_fields,
    _ensure_follow_task_identity_snapshot,
    _get_follow_task_source_origin,
    _get_follow_task,
    _get_latest_link_target_message_snapshot,
    _get_task_automation_config,
    _is_follow_task_using_origin_source,
    _normalize_source_message_snapshot,
    _normalize_optional_int,
    _parse_datetime,
    _refresh_follow_task_source_message_snapshot,
    _schedule_follow_task_next_check,
    _serialize_json_value,
    _set_follow_task_automation_state,
    _normalize_text,
    _serialize_follow_task,
    _sync_follow_task_publish_binding,
    bind_follow_task_publish_record,
)
from .publishing import sync_pan_transfer_publish_record_source_url
from .queue import refresh_pan_transfer_batch_summary


def _normalize_source_kind(value: Any) -> str:
    normalized = _normalize_text(value, max_length=32).lower() or "current"
    if normalized not in {"current", "candidate"}:
        raise ValueError("source_kind must be current or candidate")
    return normalized


def _normalize_sync_mode(value: Any) -> str:
    normalized = _normalize_text(value, max_length=32).lower() or "standard"
    if normalized not in {"standard", "incremental", "replace_all"}:
        raise ValueError("sync_mode must be standard, incremental, or replace_all")
    return normalized


def _normalize_target_relative_path(value: Any) -> str | None:
    parts = [part for part in str(value or "").replace("\\", "/").split("/") if part.strip()]
    if not parts:
        return None
    return "/".join(parts)


def _normalize_selection_group_payload(raw_value: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = dict(raw_value or {})
    raw_entries = raw.get("selected_entries")
    normalized_entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(raw_entries, list):
        for row in raw_entries:
            if not isinstance(row, dict):
                continue
            name = _normalize_text(row.get("name"), max_length=255)
            if not name:
                continue
            entry_id = _normalize_text(row.get("entry_id"), max_length=255) or None
            path = _normalize_text(row.get("path"), max_length=1024) or None
            is_dir = bool(row.get("is_dir"))
            dedupe_key = (entry_id or "", path or "", f"{name}:{int(is_dir)}")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_entries.append(
                {
                    "name": name,
                    "is_dir": is_dir,
                    "entry_id": entry_id,
                    "path": path,
                }
            )
    if not normalized_entries:
        return None
    return {
        "parent_entry_id": _normalize_text(
            raw.get("selection_parent_entry_id") or raw.get("parent_entry_id"),
            max_length=255,
        )
        or None,
        "parent_path": _normalize_text(
            raw.get("selection_parent_path") or raw.get("parent_path"),
            max_length=1024,
        )
        or None,
        "parent_name": _normalize_text(
            raw.get("selection_parent_name") or raw.get("parent_name"),
            max_length=255,
        )
        or None,
        "target_relative_path": _normalize_target_relative_path(raw.get("target_relative_path")),
        "selected_entries": normalized_entries,
        "selected_count": len(normalized_entries),
    }


def _normalize_source_selection(payload: dict[str, Any] | None, *, sync_mode: str) -> dict[str, Any] | None:
    raw = dict(payload or {})
    normalized_groups: list[dict[str, Any]] = []
    raw_groups = raw.get("selection_groups")
    if isinstance(raw_groups, list):
        for row in raw_groups:
            if not isinstance(row, dict):
                continue
            normalized_group = _normalize_selection_group_payload(row)
            if normalized_group is None:
                continue
            normalized_groups.append(normalized_group)
    if not normalized_groups:
        fallback_group = _normalize_selection_group_payload(raw)
        if fallback_group is not None:
            normalized_groups.append(fallback_group)

    if sync_mode == "standard":
        if normalized_groups:
            raise ValueError("selected entries are only supported for incremental or replace_all mode")
        return None

    if not normalized_groups:
        raise ValueError("selected_entries cannot be empty for follow sync")

    return {
        "selection_groups": normalized_groups,
        "selected_count": sum(int(group.get("selected_count") or 0) for group in normalized_groups),
    }


def _resolve_follow_sync_paths(task: PanTransferSyncTask) -> tuple[dict[str, Any], dict[str, Any]]:
    extra_json = dict(task.extra_json or {})
    path_strategy = dict(extra_json.get("path_strategy") or {})
    resolved_paths = dict(extra_json.get("resolved_paths") or {})
    staging_root = normalize_relative_path(_normalize_text(resolved_paths.get("staging_root"), max_length=255))
    staging_folder_name = _normalize_text(resolved_paths.get("staging_folder_name"), max_length=120)
    if staging_folder_name:
        resolved_path = normalize_relative_path(
            _normalize_text(resolved_paths.get("resolved_path"), max_length=512)
            or "/".join(part for part in (staging_root, staging_folder_name) if part)
        )
        normalized_resolved_paths = {
            **resolved_paths,
            "staging_root": staging_root,
            "staging_folder_name": staging_folder_name,
            "resolved_path": resolved_path,
            "share_target_mode": _normalize_text(
                resolved_paths.get("share_target_mode") or path_strategy.get("share_target_mode"),
                max_length=32,
            )
            or str(task.share_target_mode or "resource_dir"),
            "transfer_layout": _normalize_text(
                resolved_paths.get("transfer_layout") or path_strategy.get("transfer_layout"),
                max_length=32,
            )
            or str(task.transfer_layout or "independent"),
            "batch_folder_name": _normalize_text(
                resolved_paths.get("batch_folder_name") or path_strategy.get("batch_folder_name"),
                max_length=120,
            )
            or None,
        }
        return path_strategy, normalized_resolved_paths

    fixed_save_path = normalize_relative_path(_normalize_text(task.fixed_save_path, max_length=512))
    if not fixed_save_path:
        raise ValueError("follow task is missing fixed_save_path")
    path_parts = [part for part in fixed_save_path.split("/") if part]
    if not path_parts:
        raise ValueError("follow task fixed_save_path is invalid")
    fallback_folder_name = path_parts[-1]
    fallback_root = "/".join(path_parts[:-1])
    normalized_path_strategy = {
        "transfer_layout": _normalize_text(task.transfer_layout, max_length=32) or "independent",
        "batch_folder_name": _normalize_text(task.batch_folder_name, max_length=120) or None,
        "item_folder_mode": _normalize_text(task.item_folder_mode, max_length=32) or "auto",
        "item_folder_template": _normalize_text(task.item_folder_template, max_length=120) or None,
        "share_target_mode": _normalize_text(task.share_target_mode, max_length=32) or "resource_dir",
    }
    normalized_resolved_paths = {
        "transfer_layout": normalized_path_strategy["transfer_layout"],
        "batch_folder_name": normalized_path_strategy["batch_folder_name"],
        "staging_root": fallback_root,
        "staging_folder_name": fallback_folder_name,
        "resolved_path": fixed_save_path,
        "share_target_mode": normalized_path_strategy["share_target_mode"],
    }
    return normalized_path_strategy, normalized_resolved_paths


def _resolve_follow_sync_source(
    session: Session,
    *,
    task: PanTransferSyncTask,
    source_kind: str,
) -> tuple[LinkTarget, str, dict[str, Any]]:
    if source_kind == "candidate":
        link_target_id = _normalize_optional_int(task.last_candidate_link_target_id)
        if link_target_id is None:
            raise ValueError("follow task has no candidate source")
        source_target = session.get(LinkTarget, int(link_target_id))
        if source_target is None:
            raise LookupError("candidate source link target not found")
        source_snapshot = _get_latest_link_target_message_snapshot(
            session,
            link_target_id=int(link_target_id),
            fallback_snapshot={
                "title": _normalize_text(task.last_candidate_title, max_length=255)
                or _normalize_text(task.topic_title, max_length=255)
                or None,
                "description": None,
                "tags": [],
                "message_time": task.last_candidate_message_time,
            },
        )
        return source_target, _normalize_text(source_target.original_url), source_snapshot

    link_target_id = _normalize_optional_int(task.source_link_target_id)
    if link_target_id is None:
        raise ValueError("follow task has no source link target")
    source_target = session.get(LinkTarget, int(link_target_id))
    if source_target is None:
        raise LookupError("source link target not found")
    source_snapshot = _refresh_follow_task_source_message_snapshot(
        session,
        task=task,
        fallback_snapshot=dict(dict(task.extra_json or {}).get("source_message_snapshot") or {}),
    )
    if not source_snapshot.get("title"):
        source_snapshot["title"] = (
            _normalize_text(task.work_title, max_length=255)
            or _normalize_text(task.topic_title, max_length=255)
            or None
        )
    return source_target, _normalize_text(source_target.original_url), source_snapshot


def create_pan_transfer_follow_sync_batch(
    session: Session,
    *,
    task_id: int,
    payload: dict[str, Any] | None,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    if task.task_state == PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED:
        raise ValueError("follow task already has a sync batch queued")

    publish_record = bind_follow_task_publish_record(session, task=task)
    account = session.get(PanTransferAccount, int(task.target_account_id or 0))
    if account is None:
        raise LookupError("target account not found")
    if not bool(account.is_enabled):
        raise ValueError("target account is disabled")

    source_kind = _normalize_source_kind((payload or {}).get("source_kind"))
    sync_mode = _normalize_sync_mode((payload or {}).get("sync_mode"))
    source_target, source_url, source_message_snapshot = _resolve_follow_sync_source(
        session,
        task=task,
        source_kind=source_kind,
    )
    if not source_url:
        raise ValueError("source_url cannot be empty")

    path_strategy, resolved_paths = _resolve_follow_sync_paths(task)
    source_selection = _normalize_source_selection(payload, sync_mode=sync_mode)
    selection_groups = list((source_selection or {}).get("selection_groups") or [])
    selection_parent_path = selection_groups[0].get("parent_path") if len(selection_groups) == 1 else None
    confirm_full_replace = bool((payload or {}).get("confirm_full_replace"))
    if sync_mode == "replace_all" and not confirm_full_replace:
        raise ValueError("confirm_full_replace is required for replace_all mode")
    reuse_existing_share_if_valid = bool((payload or {}).get("reuse_existing_share_if_valid", True))
    update_publish_record = bool((payload or {}).get("update_publish_record", True))
    trigger_mode = _normalize_text((payload or {}).get("trigger_mode"), max_length=32).lower() or "manual"
    clear_existing_contents = sync_mode == "replace_all"

    batch = PanTransferBatch(
        batch_type="follow_sync",
        source_scope="follow_task",
        status=PAN_TRANSFER_BATCH_STATUS_RUNNING,
        created_by=_normalize_text(operator, max_length=128) or None,
        total_message_count=1,
        total_link_target_count=1,
        retry_delay_seconds=int(DEFAULT_PAN_TRANSFER_RETRY_DELAY_SECONDS),
        request_json={
            "follow_task_id": int(task.id),
            "trigger_mode": trigger_mode,
            "source_kind": source_kind,
            "sync_mode": sync_mode,
            "source_link_target_id": int(source_target.id),
            "source_url": source_url,
            "reuse_existing_share_if_valid": reuse_existing_share_if_valid,
            "update_publish_record": update_publish_record,
            "confirm_full_replace": confirm_full_replace,
            "source_selection": source_selection,
            "selection_group_count": len(selection_groups),
            "path_strategy": path_strategy,
            "resolved_paths": resolved_paths,
        },
        result_json={},
        started_at=utcnow(),
    )
    session.add(batch)
    session.flush()

    row = PanTransferBatchItem(
        batch_id=int(batch.id),
        link_target_id=int(source_target.id),
        target_account_id=int(account.id),
        platform=_normalize_text(task.platform, max_length=64),
        short_title=_normalize_text(source_message_snapshot.get("title"), max_length=255)
        or _normalize_text(task.task_name, max_length=255)
        or _normalize_text(task.topic_title, max_length=255),
        original_url=source_url,
        source_message_count=1,
        source_ref_count=1,
        latest_message_title=_normalize_text(source_message_snapshot.get("title"), max_length=255) or None,
        latest_message_time=(
            _parse_datetime(source_message_snapshot.get("message_time"))
            or (task.last_candidate_message_time if source_kind == "candidate" else task.last_checked_at)
        ),
        latest_link_health=_normalize_text(task.source_link_status if source_kind == "current" else "unknown", max_length=32) or "unknown",
        transfer_status=PAN_TRANSFER_ITEM_STATUS_QUEUED,
        share_status=PAN_TRANSFER_SHARE_STATUS_PENDING,
        validation_status=PAN_TRANSFER_VALIDATION_STATUS_PENDING,
        replacement_status=PAN_TRANSFER_REPLACEMENT_STATUS_PENDING,
        attempt_count=0,
        max_attempts=int(DEFAULT_PAN_TRANSFER_MAX_ATTEMPTS),
        extra_json={
            "recommended_account_name": _normalize_text(account.account_name, max_length=128) or None,
            "path_strategy": path_strategy,
            "resolved_paths": resolved_paths,
            "source_message_snapshot": _normalize_source_message_snapshot(
                {
                    **source_message_snapshot,
                    "message_time": source_message_snapshot.get("message_time")
                    or _serialize_json_value(
                        task.last_candidate_message_time if source_kind == "candidate" else task.last_checked_at
                    ),
                }
            ),
            "follow_sync_context": {
                "follow_task_id": int(task.id),
                "trigger_mode": trigger_mode,
                "source_kind": source_kind,
                "sync_mode": sync_mode,
                "source_link_target_id": int(source_target.id),
                "source_url": source_url,
                "clear_existing_contents": clear_existing_contents,
                "reuse_existing_share_if_valid": reuse_existing_share_if_valid,
                "existing_share_url": _normalize_text(task.current_share_url) or None,
                "share_target_mode": _normalize_text(task.share_target_mode, max_length=32) or "resource_dir",
                "publish_record_id": int(publish_record.id) if publish_record is not None else None,
                "update_publish_record": update_publish_record,
                "selection_group_count": len(selection_groups),
            },
            "source_selection": source_selection,
        },
    )
    session.add(row)
    session.flush()

    refresh_pan_transfer_batch_summary(session, batch_id=int(batch.id))

    extra_json = dict(task.extra_json or {})
    last_sync = {
        "batch_id": int(batch.id),
        "batch_item_id": int(row.id),
        "source_kind": source_kind,
        "sync_mode": sync_mode,
        "started_at": utcnow().isoformat() + "Z",
        "trigger_mode": trigger_mode,
        "selected_count": int((source_selection or {}).get("selected_count") or 0),
        "selection_group_count": len(selection_groups),
    }
    extra_json["last_sync"] = last_sync
    task.extra_json = extra_json
    task.task_state = PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED
    task.last_error_message = None
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    session.add(task)
    session.flush()

    _append_follow_task_log(
        session,
        task=task,
        stage="sync",
        message="Created a follow-sync batch targeting the existing resource directory",
        payload={
            "batch_id": int(batch.id),
            "batch_item_id": int(row.id),
            "source_kind": source_kind,
            "sync_mode": sync_mode,
            "source_link_target_id": int(source_target.id),
            "source_url": source_url,
            "resolved_path": resolved_paths.get("resolved_path"),
            "reuse_existing_share_if_valid": reuse_existing_share_if_valid,
            "update_publish_record": update_publish_record,
            "trigger_mode": trigger_mode,
            "clear_existing_contents": clear_existing_contents,
            "selected_count": int((source_selection or {}).get("selected_count") or 0),
            "selection_group_count": len(selection_groups),
            "selection_parent_path": selection_parent_path,
        },
    )
    session.flush()
    return {
        "task": _serialize_follow_task(task),
        "batch_id": int(batch.id),
        "batch_item_id": int(row.id),
        "started": True,
    }


def _get_follow_sync_context(item: PanTransferBatchItem) -> dict[str, Any] | None:
    raw_value = dict(item.extra_json or {}).get("follow_sync_context")
    return dict(raw_value) if isinstance(raw_value, dict) else None


def _build_follow_sync_success_source_snapshot(
    session: Session,
    *,
    source_link_target_id: int | None,
    fallback_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if source_link_target_id is None:
        return _normalize_source_message_snapshot(fallback_snapshot)
    return _get_latest_link_target_message_snapshot(
        session,
        link_target_id=int(source_link_target_id),
        fallback_snapshot=fallback_snapshot,
    )


def _apply_follow_sync_success_automation(
    session: Session,
    *,
    task: PanTransferSyncTask,
    source_kind: str,
    trigger_mode: str,
    synced_at,
) -> dict[str, Any]:
    origin = _get_follow_task_source_origin(session, task=task)
    current_automation = _get_task_automation_config(task)
    if not _is_follow_task_using_origin_source(task, origin=origin):
        return _set_follow_task_automation_state(
            task,
            enabled=False,
            stop_reason="source_switched",
            stopped_at=synced_at,
            cooldown_until=None,
        )
    if source_kind != "current":
        return _set_follow_task_automation_state(
            task,
            enabled=bool(current_automation.get("enabled")),
            cooldown_until=None,
        )
    if bool(current_automation.get("enabled")) or trigger_mode == "automation":
        return _set_follow_task_automation_state(
            task,
            enabled=bool(current_automation.get("enabled")),
            cooldown_until=None,
            last_auto_sync_at=synced_at if trigger_mode == "automation" else None,
        )
    return _set_follow_task_automation_state(
        task,
        enabled=False,
        cooldown_until=None,
    )


def handle_follow_sync_item_success(
    session: Session,
    *,
    item: PanTransferBatchItem,
    worker_name: str,
) -> None:
    context = _get_follow_sync_context(item)
    if context is None:
        return

    follow_task_id = _normalize_optional_int(context.get("follow_task_id"))
    if follow_task_id is None:
        return
    task = session.get(PanTransferSyncTask, int(follow_task_id))
    if task is None:
        return

    source_kind = _normalize_text(context.get("source_kind"), max_length=32) or "current"
    sync_mode = _normalize_text(context.get("sync_mode"), max_length=32) or "standard"
    trigger_mode = _normalize_text(context.get("trigger_mode"), max_length=32).lower() or "manual"
    synced_at = utcnow()

    source_link_target_id = _normalize_optional_int(context.get("source_link_target_id"))
    source_target = session.get(LinkTarget, int(source_link_target_id)) if source_link_target_id is not None else None
    if source_link_target_id is not None:
        task.source_link_target_id = int(source_link_target_id)
    source_url = _normalize_text(context.get("source_url")) or _normalize_text(getattr(source_target, "original_url", None)) or None
    if source_url:
        task.source_url = source_url
    source_share_key = _normalize_text(getattr(source_target, "share_key", None), max_length=255) or None
    task.source_share_key = source_share_key or task.source_share_key

    source_message_snapshot = _build_follow_sync_success_source_snapshot(
        session,
        source_link_target_id=source_link_target_id,
        fallback_snapshot=dict(dict(item.extra_json or {}).get("source_message_snapshot") or {}),
    )
    _clear_follow_task_candidate_fields(task)

    if _normalize_text(item.new_share_url):
        task.current_share_url = _normalize_text(item.new_share_url)
    task.current_share_link_target_id = int(item.new_link_target_id) if item.new_link_target_id is not None else task.current_share_link_target_id
    task.current_share_status = _normalize_text(item.validation_status, max_length=32).lower() or task.current_share_status
    task.task_state = PAN_TRANSFER_SYNC_STATE_IDLE
    task.last_change_type = "candidate_applied" if source_kind == "candidate" else "sync_completed"
    task.last_error_message = None
    task.updated_by = _normalize_text(worker_name, max_length=128) or task.updated_by

    extra_json = dict(task.extra_json or {})
    if source_message_snapshot:
        extra_json["source_message_snapshot"] = source_message_snapshot
    extra_json["last_sync"] = {
        "batch_id": int(item.batch_id),
        "batch_item_id": int(item.id),
        "source_kind": source_kind,
        "sync_mode": sync_mode,
        "started_at": _normalize_text(dict(extra_json.get("last_sync") or {}).get("started_at")) or None,
        "finished_at": synced_at.isoformat() + "Z",
        "share_url": _normalize_text(item.new_share_url) or None,
        "trigger_mode": trigger_mode,
    }
    task.extra_json = extra_json
    session.add(task)
    session.flush()

    _refresh_follow_task_source_message_snapshot(
        session,
        task=task,
        fallback_snapshot=source_message_snapshot,
    )
    automation = _apply_follow_sync_success_automation(
        session,
        task=task,
        source_kind=source_kind,
        trigger_mode=trigger_mode,
        synced_at=synced_at,
    )
    _schedule_follow_task_next_check(task, now=synced_at)
    session.add(task)
    session.flush()
    identity_snapshot, identity_updated = _ensure_follow_task_identity_snapshot(session, task=task)

    if identity_updated:
        _append_follow_task_log(
            session,
            task=task,
            stage="identity",
            message="Built follow task identity snapshot",
            payload=identity_snapshot,
        )

    _append_follow_task_log(
        session,
        task=task,
        stage="sync",
        message="Follow-sync batch completed and the tracked resource directory was refreshed",
        payload={
            "batch_id": int(item.batch_id),
            "batch_item_id": int(item.id),
            "source_kind": source_kind,
            "sync_mode": sync_mode,
            "trigger_mode": trigger_mode,
            "new_share_url": _normalize_text(item.new_share_url) or None,
            "new_link_target_id": int(item.new_link_target_id) if item.new_link_target_id is not None else None,
            "automation": automation,
        },
    )

    publish_record = bind_follow_task_publish_record(session, task=task)
    publish_record_id = _normalize_optional_int(context.get("publish_record_id")) or _normalize_optional_int(task.publish_record_id)
    if publish_record_id is not None and bool(context.get("update_publish_record")) and _normalize_text(item.new_share_url):
        publish_record_payload = sync_pan_transfer_publish_record_source_url(
            session,
            record_id=int(publish_record_id),
            source_url=str(item.new_share_url or ""),
            operator=worker_name,
            validation_result=dict(dict(item.extra_json or {}).get("share_validation") or {}),
            sync_payload={
                "follow_task_id": int(task.id),
                "batch_id": int(item.batch_id),
                "batch_item_id": int(item.id),
                "source_kind": source_kind,
                "sync_mode": sync_mode,
                "trigger_mode": trigger_mode,
            },
        )
        publish_record = session.get(PanTransferPublishRecord, int(publish_record_payload["id"]))
        _sync_follow_task_publish_binding(task, publish_record=publish_record)
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="publish",
            message="Bound frontend publish record was updated to the latest share URL",
            payload={
                "publish_record_id": int(publish_record_id),
                "source_url": _normalize_text(item.new_share_url) or None,
            },
        )


def handle_follow_sync_item_failure(
    session: Session,
    *,
    item: PanTransferBatchItem,
    worker_name: str,
    error_message: str,
) -> None:
    context = _get_follow_sync_context(item)
    if context is None:
        return

    follow_task_id = _normalize_optional_int(context.get("follow_task_id"))
    if follow_task_id is None:
        return
    task = session.get(PanTransferSyncTask, int(follow_task_id))
    if task is None:
        return

    task.task_state = PAN_TRANSFER_SYNC_STATE_ERROR
    task.last_change_type = PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND if _normalize_text(context.get("source_kind"), max_length=32) == "candidate" else "sync_failed"
    task.last_error_message = _normalize_text(error_message, max_length=2000) or task.last_error_message
    task.updated_by = _normalize_text(worker_name, max_length=128) or task.updated_by
    extra_json = dict(task.extra_json or {})
    last_sync = dict(extra_json.get("last_sync") or {})
    last_sync["failed_at"] = utcnow().isoformat() + "Z"
    last_sync["error_message"] = _normalize_text(error_message, max_length=2000) or None
    extra_json["last_sync"] = last_sync
    task.extra_json = extra_json
    _schedule_follow_task_next_check(task)
    session.add(task)
    session.flush()

    _append_follow_task_log(
        session,
        task=task,
        stage="sync",
        level="error",
        message=f"Follow-sync batch failed: {_normalize_text(error_message, max_length=2000) or 'unknown error'}",
        payload={
            "batch_id": int(item.batch_id),
            "batch_item_id": int(item.id),
            "source_kind": _normalize_text(context.get("source_kind"), max_length=32) or "current",
            "sync_mode": _normalize_text(context.get("sync_mode"), max_length=32) or "standard",
        },
    )
