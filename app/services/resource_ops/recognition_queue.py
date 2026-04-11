from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.models import ResourceRecognitionTask, ResourceWorkBinding, ensure_runtime_storage_tables


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_RETRY_WAIT = "retry_wait"
TASK_STATUS_DONE = "done"
TASK_STATUS_FAILED = "failed"

ACTIVE_TASK_STATUSES = {
    TASK_STATUS_QUEUED,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_RETRY_WAIT,
}

DEFAULT_RECOGNITION_PRIORITY = 100
CLICK_RECOGNITION_PRIORITY = 300
FULL_SCAN_RECOGNITION_PRIORITY = 50
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 15 * 60
STALE_LOCK_SECONDS = 15 * 60


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_positive_ids(values: Iterable[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_value in values:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _matched_link_target_ids(session: Session, *, link_target_ids: list[int]) -> set[int]:
    if not link_target_ids:
        return set()
    return {
        int(link_target_id)
        for (link_target_id,) in (
            session.query(ResourceWorkBinding.link_target_id)
            .filter(
                ResourceWorkBinding.link_target_id.in_(link_target_ids),
                ResourceWorkBinding.work_id.isnot(None),
                ResourceWorkBinding.match_status == "matched",
            )
            .all()
        )
        if link_target_id is not None
    }


def enqueue_recognition_tasks(
    session: Session,
    *,
    link_target_ids: Iterable[int],
    source: str,
    priority: int = DEFAULT_RECOGNITION_PRIORITY,
    skip_matched: bool = False,
) -> dict[str, int]:
    ensure_runtime_storage_tables()
    normalized_ids = _normalize_positive_ids(link_target_ids)
    if not normalized_ids:
        return {
            "requested_count": 0,
            "accepted_count": 0,
            "skipped_matched_count": 0,
            "processing_count": 0,
        }

    matched_ids = _matched_link_target_ids(session, link_target_ids=normalized_ids) if skip_matched else set()
    target_ids = [link_target_id for link_target_id in normalized_ids if link_target_id not in matched_ids]
    if not target_ids:
        return {
            "requested_count": len(normalized_ids),
            "accepted_count": 0,
            "skipped_matched_count": len(matched_ids),
            "processing_count": 0,
        }

    existing_rows = (
        session.query(ResourceRecognitionTask)
        .filter(ResourceRecognitionTask.link_target_id.in_(target_ids))
        .all()
    )
    existing_by_target = {int(row.link_target_id): row for row in existing_rows if row.link_target_id is not None}
    now = _utcnow()
    accepted_count = 0
    processing_count = 0

    for link_target_id in target_ids:
        row = existing_by_target.get(link_target_id)
        if row is None:
            row = ResourceRecognitionTask(
                link_target_id=link_target_id,
                status=TASK_STATUS_QUEUED,
                source=source[:32] if source else "manual",
                priority=max(1, int(priority or DEFAULT_RECOGNITION_PRIORITY)),
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                attempt_count=0,
                next_retry_at=None,
                locked_by=None,
                locked_at=None,
                started_at=None,
                finished_at=None,
                last_error=None,
                last_enqueued_at=now,
                last_processed_at=None,
            )
            session.add(row)
            accepted_count += 1
            continue

        if row.status == TASK_STATUS_PROCESSING:
            row.priority = max(int(row.priority or 0), int(priority or DEFAULT_RECOGNITION_PRIORITY))
            row.source = source[:32] if source else (row.source or "manual")
            row.last_enqueued_at = now
            session.add(row)
            processing_count += 1
            continue

        row.status = TASK_STATUS_QUEUED
        row.source = source[:32] if source else (row.source or "manual")
        row.priority = max(int(row.priority or 0), int(priority or DEFAULT_RECOGNITION_PRIORITY))
        row.attempt_count = 0
        row.next_retry_at = None
        row.locked_by = None
        row.locked_at = None
        row.started_at = None
        row.finished_at = None
        row.last_error = None
        row.last_enqueued_at = now
        session.add(row)
        accepted_count += 1

    session.flush()
    return {
        "requested_count": len(normalized_ids),
        "accepted_count": accepted_count,
        "skipped_matched_count": len(matched_ids),
        "processing_count": processing_count,
    }


def get_recognition_queue_summary(session: Session) -> dict[str, int]:
    ensure_runtime_storage_tables()
    rows = (
        session.query(
            ResourceRecognitionTask.status,
            func.count(ResourceRecognitionTask.id),
        )
        .group_by(ResourceRecognitionTask.status)
        .all()
    )
    counts = {str(status or ""): int(total or 0) for status, total in rows}
    queued_count = counts.get(TASK_STATUS_QUEUED, 0)
    processing_count = counts.get(TASK_STATUS_PROCESSING, 0)
    retry_wait_count = counts.get(TASK_STATUS_RETRY_WAIT, 0)
    done_count = counts.get(TASK_STATUS_DONE, 0)
    failed_count = counts.get(TASK_STATUS_FAILED, 0)
    pending_count = queued_count + processing_count + retry_wait_count
    return {
        "queued_count": queued_count,
        "processing_count": processing_count,
        "retry_wait_count": retry_wait_count,
        "done_count": done_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
    }


def recycle_stale_processing_tasks(session: Session, *, stale_seconds: int = STALE_LOCK_SECONDS) -> int:
    ensure_runtime_storage_tables()
    stale_before = _utcnow() - timedelta(seconds=max(60, int(stale_seconds or STALE_LOCK_SECONDS)))
    rows = (
        session.query(ResourceRecognitionTask)
        .filter(
            ResourceRecognitionTask.status == TASK_STATUS_PROCESSING,
            ResourceRecognitionTask.locked_at.isnot(None),
            ResourceRecognitionTask.locked_at < stale_before,
        )
        .all()
    )
    recycled = 0
    for row in rows:
        row.status = TASK_STATUS_QUEUED
        row.locked_by = None
        row.locked_at = None
        row.started_at = None
        row.finished_at = None
        row.last_error = "Worker exited before finishing the task"
        row.last_enqueued_at = _utcnow()
        session.add(row)
        recycled += 1
    if recycled:
        session.flush()
    return recycled


def claim_next_recognition_task(session: Session, *, worker_name: str) -> ResourceRecognitionTask | None:
    ensure_runtime_storage_tables()
    now = _utcnow()
    recycle_stale_processing_tasks(session)
    candidate = (
        session.query(ResourceRecognitionTask)
        .filter(
            or_(
                ResourceRecognitionTask.status == TASK_STATUS_QUEUED,
                and_(
                    ResourceRecognitionTask.status == TASK_STATUS_RETRY_WAIT,
                    ResourceRecognitionTask.next_retry_at.isnot(None),
                    ResourceRecognitionTask.next_retry_at <= now,
                ),
            )
        )
        .order_by(
            case((ResourceRecognitionTask.status == TASK_STATUS_QUEUED, 0), else_=1),
            ResourceRecognitionTask.priority.desc(),
            ResourceRecognitionTask.last_enqueued_at.asc(),
            ResourceRecognitionTask.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if candidate is None:
        return None

    candidate.status = TASK_STATUS_PROCESSING
    candidate.locked_by = (worker_name or "resource-worker")[:128]
    candidate.locked_at = now
    candidate.started_at = now
    candidate.finished_at = None
    session.add(candidate)
    session.flush()
    return candidate


def mark_recognition_task_success(
    session: Session,
    *,
    task: ResourceRecognitionTask,
    recognized_title: str | None = None,
) -> None:
    now = _utcnow()
    task.status = TASK_STATUS_DONE
    task.attempt_count = max(1, int(task.attempt_count or 0) + 1)
    task.next_retry_at = None
    task.locked_by = None
    task.locked_at = None
    task.finished_at = now
    task.last_processed_at = now
    task.last_error = None
    if recognized_title:
        task.last_result_title = str(recognized_title).strip()[:255]
    session.add(task)
    session.flush()


def mark_recognition_task_error(
    session: Session,
    *,
    task: ResourceRecognitionTask,
    error_message: str,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
) -> None:
    now = _utcnow()
    task.attempt_count = max(1, int(task.attempt_count or 0) + 1)
    task.last_error = str(error_message or "AI recognition failed").strip()[:2000]
    task.locked_by = None
    task.locked_at = None
    task.finished_at = now
    task.last_processed_at = now
    if int(task.attempt_count or 0) >= max(1, int(task.max_attempts or DEFAULT_MAX_ATTEMPTS)):
        task.status = TASK_STATUS_FAILED
        task.next_retry_at = None
    else:
        task.status = TASK_STATUS_RETRY_WAIT
        task.next_retry_at = now + timedelta(seconds=max(60, int(retry_delay_seconds or DEFAULT_RETRY_DELAY_SECONDS)))
    session.add(task)
    session.flush()


def reset_failed_recognition_tasks(
    session: Session,
    *,
    link_target_ids: Iterable[int],
) -> int:
    normalized_ids = _normalize_positive_ids(link_target_ids)
    if not normalized_ids:
        return 0
    rows = (
        session.query(ResourceRecognitionTask)
        .filter(
            ResourceRecognitionTask.link_target_id.in_(normalized_ids),
            ResourceRecognitionTask.status == TASK_STATUS_FAILED,
        )
        .all()
    )
    now = _utcnow()
    reset_count = 0
    for row in rows:
        row.status = TASK_STATUS_QUEUED
        row.attempt_count = 0
        row.next_retry_at = None
        row.locked_by = None
        row.locked_at = None
        row.started_at = None
        row.finished_at = None
        row.last_error = None
        row.last_enqueued_at = now
        session.add(row)
        reset_count += 1
    if reset_count:
        session.flush()
    return reset_count
