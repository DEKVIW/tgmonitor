from __future__ import annotations

import logging
import signal
import time
from threading import Event

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import engine, ensure_runtime_storage_tables
from app.services.link_check_scheduler import start_link_check_scheduler, stop_link_check_scheduler
from app.services.pan_transfer import (
    process_next_pan_transfer_follow_task,
    process_next_pan_transfer_item,
    process_next_pan_transfer_publish_rule,
)
from app.services.pan_transfer.maintenance import run_pan_transfer_log_retention_if_due
from app.services.resource_ops.recognition_worker import (
    process_next_recognition_task,
    run_resource_ops_maintenance_if_due,
)
from app.services.resource_ops.settings import update_resource_ops_worker_state


logger = logging.getLogger(__name__)

WORKER_NAME = "tg-worker"
WORKER_LOCK_KEY = 42025092
IDLE_SLEEP_SECONDS = 3
BUSY_SLEEP_SECONDS = 0.2
LOCK_WAIT_SECONDS = 5

_stop_event = Event()


def _handle_stop_signal(signum, frame) -> None:  # type: ignore[no-untyped-def]
    del signum, frame
    _stop_event.set()


def _try_claim_worker_lock(session: Session) -> bool:
    return bool(
        session.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": WORKER_LOCK_KEY},
        ).scalar()
    )


def _release_worker_lock(session: Session) -> None:
    session.execute(
        text("SELECT pg_advisory_unlock(:lock_key)"),
        {"lock_key": WORKER_LOCK_KEY},
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGINT, _handle_stop_signal)
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    ensure_runtime_storage_tables()
    start_link_check_scheduler()

    try:
        while not _stop_event.is_set():
            lock_session = Session(engine)
            has_lock = False
            try:
                has_lock = _try_claim_worker_lock(lock_session)
                if not has_lock:
                    logger.info("resource worker lock not available, retrying in %s seconds", LOCK_WAIT_SECONDS)
                    lock_session.close()
                    if _stop_event.wait(LOCK_WAIT_SECONDS):
                        break
                    continue

                logger.info("resource worker started")
                lock_session.commit()
                while not _stop_event.is_set():
                    processed_recognition = False
                    processed_transfer = False
                    processed_follow_task = False
                    processed_publish_rule = False
                    with Session(engine) as session:
                        try:
                            run_resource_ops_maintenance_if_due(session, worker_name=WORKER_NAME)
                            run_pan_transfer_log_retention_if_due(session, worker_name=WORKER_NAME)
                            processed_recognition = process_next_recognition_task(session, worker_name=WORKER_NAME)
                            session.commit()
                        except Exception:
                            session.rollback()
                            logger.exception("resource worker iteration failed")
                            update_resource_ops_worker_state(
                                session,
                                {
                                    "worker_state": "idle",
                                    "worker_last_error": "worker iteration failed",
                                },
                                updated_by=WORKER_NAME,
                            )
                            session.commit()
                            processed_recognition = False

                    with Session(engine) as session:
                        try:
                            processed_transfer = process_next_pan_transfer_item(session, worker_name=WORKER_NAME)
                            session.commit()
                        except Exception:
                            session.rollback()
                            logger.exception("pan transfer worker iteration failed")
                            processed_transfer = False

                    with Session(engine) as session:
                        try:
                            processed_follow_task = process_next_pan_transfer_follow_task(session, worker_name=WORKER_NAME)
                            session.commit()
                        except Exception:
                            session.rollback()
                            logger.exception("pan transfer follow-task worker iteration failed")
                            processed_follow_task = False

                    with Session(engine) as session:
                        try:
                            processed_publish_rule = process_next_pan_transfer_publish_rule(session, worker_name=WORKER_NAME)
                            session.commit()
                        except Exception:
                            session.rollback()
                            logger.exception("pan transfer publish-rule worker iteration failed")
                            processed_publish_rule = False

                    processed = bool(processed_recognition or processed_transfer or processed_follow_task or processed_publish_rule)

                    if _stop_event.wait(BUSY_SLEEP_SECONDS if processed else IDLE_SLEEP_SECONDS):
                        break
            except Exception:
                logger.exception("resource worker crashed before next retry")
                time.sleep(LOCK_WAIT_SECONDS)
            finally:
                try:
                    if has_lock:
                        with Session(engine) as session:
                            update_resource_ops_worker_state(
                                session,
                                {
                                    "worker_state": "idle",
                                    "worker_current_link_target_id": None,
                                    "worker_current_title": "",
                                    "worker_current_source": "",
                                },
                                updated_by=WORKER_NAME,
                            )
                            session.commit()
                        _release_worker_lock(lock_session)
                        lock_session.commit()
                except Exception:
                    logger.exception("failed to release resource worker lock cleanly")
                lock_session.close()
    finally:
        stop_link_check_scheduler()


if __name__ == "__main__":
    main()
