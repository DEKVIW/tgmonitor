from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import ensure_runtime_storage_tables
from app.services.resource_ops.maintenance import run_resource_ops_retention
from app.services.resource_ops.recognition_queue import (
    claim_next_recognition_task,
    mark_recognition_task_error,
    mark_recognition_task_success,
)
from app.services.resource_ops.recognition_service import (
    build_recognition_log_line,
    get_work_binding_summary,
    resolve_link_target_work,
)
from app.services.resource_ops.settings import (
    get_resource_ops_runtime_config,
    update_resource_ops_runtime_meta,
    update_resource_ops_worker_state,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_utc_naive(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _should_run_cleanup(config: dict[str, Any]) -> bool:
    interval_hours = max(1, int(config.get("cleanup_interval_hours") or 24))
    last_cleanup_at = _normalize_utc_naive(config.get("last_cleanup_at"))
    if last_cleanup_at is None:
        return True
    return last_cleanup_at + timedelta(hours=interval_hours) <= _utcnow()


def _set_worker_idle(
    session: Session,
    *,
    worker_name: str,
    last_error: str | None = None,
    log_line: str | None = None,
) -> None:
    now = _utcnow()
    update_resource_ops_worker_state(
        session,
        {
            "worker_state": "idle",
            "worker_finished_at": now,
            "worker_last_heartbeat_at": now,
            "worker_current_link_target_id": None,
            "worker_current_title": "",
            "worker_current_source": "",
            "worker_last_error": last_error or "",
            "log_line": log_line,
        },
        updated_by=worker_name,
    )


def _set_worker_running(
    session: Session,
    *,
    worker_name: str,
    link_target_id: int,
    source: str,
) -> None:
    now = _utcnow()
    update_resource_ops_worker_state(
        session,
        {
            "worker_state": "running",
            "worker_started_at": now,
            "worker_last_heartbeat_at": now,
            "worker_current_link_target_id": int(link_target_id),
            "worker_current_title": f"link_target:{int(link_target_id)}",
            "worker_current_source": str(source or "manual")[:32],
            "worker_last_error": "",
        },
        updated_by=worker_name,
    )


def run_resource_ops_maintenance_if_due(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)
    if not _should_run_cleanup(config):
        return False
    run_resource_ops_retention(session, operator=worker_name)
    return True


def process_next_recognition_task(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)

    task = claim_next_recognition_task(session, worker_name=worker_name)
    if task is None:
        _set_worker_idle(session, worker_name=worker_name, last_error=None)
        return False

    _set_worker_running(
        session,
        worker_name=worker_name,
        link_target_id=int(task.link_target_id),
        source=str(task.source or "manual"),
    )
    task_id = int(task.id)
    task_link_target_id = int(task.link_target_id)

    try:
        result = resolve_link_target_work(
            session,
            link_target_id=task_link_target_id,
            config=config,
        )
        log_line = build_recognition_log_line(result)
        work_payload = dict(result.get("work") or {})
        recognized_title = work_payload.get("work_title") or work_payload.get("work_canonical_title")

        result_status = str(result.get("status") or "").lower()
        if result_status in {"matched", "ignored"}:
            mark_recognition_task_success(
                session,
                task=task,
                recognized_title=str(recognized_title or "").strip() or None,
            )
            binding_summary = get_work_binding_summary(session)
            update_resource_ops_runtime_meta(
                session,
                last_sync_summary={
                    "processed_count": 1,
                    "matched_count": 1 if result_status == "matched" else 0,
                    "error_count": 0,
                    "pending_count": binding_summary["pending_count"],
                    "link_target_id": task_link_target_id,
                    "recognized_title": recognized_title,
                    "status": result_status,
                },
                updated_by=worker_name,
            )
            update_resource_ops_worker_state(
                session,
                {
                    "worker_last_processed_at": _utcnow(),
                },
                updated_by=worker_name,
            )
            _set_worker_idle(session, worker_name=worker_name, last_error=None, log_line=log_line)
            return True

        error_message = str(result.get("reason") or "AI recognition failed")
        mark_recognition_task_error(session, task=task, error_message=error_message)
        binding_summary = get_work_binding_summary(session)
        update_resource_ops_runtime_meta(
            session,
            last_sync_summary={
                "processed_count": 1,
                "matched_count": 0,
                "error_count": 1,
                "pending_count": binding_summary["pending_count"],
                "link_target_id": task_link_target_id,
                "recognized_title": recognized_title,
            },
            updated_by=worker_name,
        )
        update_resource_ops_worker_state(
            session,
            {
                "worker_last_processed_at": _utcnow(),
            },
            updated_by=worker_name,
        )
        _set_worker_idle(session, worker_name=worker_name, last_error=error_message, log_line=log_line)
        return True
    except Exception as exc:
        error_message = str(exc)
        session.rollback()
        task_for_error = session.get(type(task), task_id)
        if task_for_error is not None:
            mark_recognition_task_error(session, task=task_for_error, error_message=error_message)
        update_resource_ops_worker_state(
            session,
            {
                "worker_last_processed_at": _utcnow(),
            },
            updated_by=worker_name,
        )
        _set_worker_idle(
            session,
            worker_name=worker_name,
            last_error=error_message,
            log_line=f"[ERR] link_target:{task_link_target_id} -> {error_message}",
        )
        return True
