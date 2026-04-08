from __future__ import annotations

import logging
import threading

from app.services.backup_service import claim_due_backup_runs


logger = logging.getLogger(__name__)

_scheduler_lock = threading.RLock()
_scheduler_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None


def _scheduler_loop() -> None:
    while not _scheduler_stop_event.is_set():
        try:
            claim_due_backup_runs()
        except Exception:
            logger.exception("Backup scheduler tick failed")
        _scheduler_stop_event.wait(30)


def start_backup_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            daemon=True,
            name="backup-scheduler",
        )
        _scheduler_thread.start()


def stop_backup_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        _scheduler_stop_event.set()
        thread = _scheduler_thread
        _scheduler_thread = None

    if thread is not None and thread.is_alive():
        thread.join(timeout=1.0)
