from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import engine
from app.services.resource_ops import run_resource_ops_retention, sync_resource_work_bindings
from app.services.resource_ops.settings import (
    get_resource_ops_runtime_config,
    is_resource_ops_ai_ready,
    is_resource_ops_full_sync_active,
)


logger = logging.getLogger(__name__)

_scheduler_lock = threading.RLock()
_scheduler_stop_event = threading.Event()
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
            ai_ready = is_resource_ops_ai_ready(config)
            full_sync_active = is_resource_ops_full_sync_active(config)

            cleanup_due = _should_run(
                config.get("last_cleanup_at"),
                interval_seconds=max(3600, int(config.get("cleanup_interval_hours") or 24) * 3600),
            )
            if cleanup_due:
                run_resource_ops_retention(session, operator="system")
                session.commit()

            sync_due = ai_ready and _should_run(
                config.get("last_sync_at"),
                interval_seconds=max(300, int(config.get("sync_interval_minutes") or 30) * 60),
            )
            if sync_due:
                if full_sync_active:
                    sync_resource_work_bindings(
                        session,
                        limit=int(config.get("sync_batch_size") or 12),
                        mode="full",
                        operator="system",
                    )
                    session.commit()
                elif bool(config.get("auto_bind_enabled")):
                    sync_resource_work_bindings(
                        session,
                        limit=int(config.get("sync_batch_size") or 12),
                        mode="pending",
                        operator="system",
                    )
                    session.commit()
        except Exception:
            session.rollback()
            logger.exception("Resource ops scheduler tick failed")
        finally:
            _release_scheduler_lock(session)


def _scheduler_loop() -> None:
    while not _scheduler_stop_event.is_set():
        _scheduler_tick()
        _scheduler_stop_event.wait(120)


def start_resource_ops_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_stop_event.clear()
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
        thread = _scheduler_thread
        _scheduler_thread = None

    if thread is not None and thread.is_alive():
        thread.join(timeout=1.0)
