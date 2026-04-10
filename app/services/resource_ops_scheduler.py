from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import engine
from app.services.resource_ops.maintenance import run_resource_ops_retention
from app.services.resource_ops.recognition_service import run_resource_ops_recognition_job
from app.services.resource_ops.recognition_service import get_work_binding_summary
from app.services.resource_ops.settings import (
    get_resource_ops_recognition_request_mode,
    get_resource_ops_runtime_config,
    is_resource_ops_ai_ready,
    is_resource_ops_recognition_running,
)


logger = logging.getLogger(__name__)

_scheduler_lock = threading.RLock()
_scheduler_stop_event = threading.Event()
_scheduler_wakeup_event = threading.Event()
_scheduler_thread: threading.Thread | None = None
_scheduler_advisory_lock_key = 42025091


def _should_run(last_run_at, *, interval_seconds: int) -> bool:
    if interval_seconds <= 0:
        return False
    if last_run_at is None:
        return True
    return (last_run_at + timedelta(seconds=interval_seconds)) <= datetime.utcnow()


def _try_claim_scheduler_lock(session: Session) -> bool:
    try:
        return bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _scheduler_advisory_lock_key},
            ).scalar()
        )
    except Exception:
        logger.exception("Resource ops scheduler failed to acquire advisory lock")
        return False


def _release_scheduler_lock(session: Session) -> None:
    try:
        session.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": _scheduler_advisory_lock_key},
        )
    except Exception:
        logger.exception("Resource ops scheduler failed to release advisory lock")


def _scheduler_tick() -> None:
    with Session(engine) as session:
        if not _try_claim_scheduler_lock(session):
            return
        try:
            config = get_resource_ops_runtime_config(session)

            cleanup_due = _should_run(
                config.get("last_cleanup_at"),
                interval_seconds=max(3600, int(config.get("cleanup_interval_hours") or 24) * 3600),
            )
            if cleanup_due:
                run_resource_ops_retention(session, operator="system")
                session.commit()
                config = get_resource_ops_runtime_config(session)

            if not is_resource_ops_ai_ready(config):
                return
            if is_resource_ops_recognition_running(config):
                return

            requested_mode = get_resource_ops_recognition_request_mode(config)
            if requested_mode:
                run_resource_ops_recognition_job(
                    session,
                    mode=requested_mode,
                    operator="system",
                )
                return

            if bool(config.get("auto_recognition_enabled")):
                summary = get_work_binding_summary(session)
                if int(summary.get("pending_count") or 0) > 0:
                    run_resource_ops_recognition_job(
                        session,
                        mode="pending",
                        respect_retry_after=True,
                        operator="system",
                    )
        except Exception:
            session.rollback()
            logger.exception("Resource ops scheduler tick failed")
        finally:
            _release_scheduler_lock(session)


def _scheduler_loop() -> None:
    while not _scheduler_stop_event.is_set():
        _scheduler_tick()
        _scheduler_wakeup_event.wait(5)
        _scheduler_wakeup_event.clear()


def notify_resource_ops_scheduler() -> None:
    _scheduler_wakeup_event.set()


def start_resource_ops_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_stop_event.clear()
        _scheduler_wakeup_event.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            daemon=True,
            name="resource-ops-scheduler",
        )
        _scheduler_thread.start()


def stop_resource_ops_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        _scheduler_stop_event.set()
        _scheduler_wakeup_event.set()
        thread = _scheduler_thread
        _scheduler_thread = None

    if thread is not None and thread.is_alive():
        thread.join(timeout=1.0)
