from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.models import (
    LinkTarget,
    Message,
    MessageLinkRef,
    PanTransferFollowTriggerEvent,
    PanTransferSyncTask,
    ensure_runtime_storage_tables,
)
from app.services.resource_identity import compare_follow_candidate, parse_resource_identity

from .common import utcnow
from .follow_tasks import (
    PAN_TRANSFER_SYNC_STATE_CHECKING,
    PAN_TRANSFER_SYNC_STATE_QUEUED,
    PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED,
    PAN_TRANSFER_SYNC_STATUS_ACTIVE,
    _append_follow_task_log,
    _apply_follow_applied_update_state_to_snapshot,
    _apply_follow_materialized_update_state_to_snapshot,
    _apply_follow_snapshot_progress_to_identity,
    _get_task_automation_config,
    _get_task_extra_section,
    _normalize_optional_int,
    _normalize_text,
    _resolve_follow_task_resource_title,
)


FOLLOW_TRIGGER_EVENT_TYPE_MESSAGE_LINK_RECEIVED = "message_link_received"
FOLLOW_TRIGGER_EVENT_STATUS_PENDING = "pending"
FOLLOW_TRIGGER_EVENT_STATUS_PROCESSING = "processing"
FOLLOW_TRIGGER_EVENT_STATUS_DONE = "done"
FOLLOW_TRIGGER_EVENT_STATUS_ERROR = "error"
FOLLOW_TRIGGER_EVENT_DEFAULT_MAX_ATTEMPTS = 5
FOLLOW_TRIGGER_EVENT_RETRY_DELAY = timedelta(minutes=2)
FOLLOW_TRIGGER_EVENT_STALE_PROCESSING_AFTER = timedelta(minutes=15)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + ("Z" if value.tzinfo is None else "")


def _build_event_payload(message: Message, *, identity: Any) -> dict[str, Any]:
    return {
        "message_id": int(message.id),
        "title": _normalize_text(getattr(message, "title", None), max_length=255) or None,
        "channel": _normalize_text(getattr(message, "channel", None), max_length=255) or None,
        "source": _normalize_text(getattr(message, "source", None), max_length=255) or None,
        "timestamp": _serialize_datetime(getattr(message, "timestamp", None)),
        "identity": identity.to_dict(),
        "matched_task_ids": [],
        "queued_task_ids": [],
        "ignored_task_ids": [],
    }


def enqueue_follow_trigger_events_for_message_ids(
    session: Session,
    message_ids: list[int] | tuple[int, ...] | set[int],
) -> dict[str, int]:
    ensure_runtime_storage_tables()
    normalized_ids = sorted({int(message_id) for message_id in message_ids if int(message_id) > 0})
    if not normalized_ids:
        return {"created": 0, "existing": 0, "skipped": 0}

    messages = session.query(Message).filter(Message.id.in_(normalized_ids)).all()
    existing_ids = {
        int(message_id)
        for (message_id,) in session.query(PanTransferFollowTriggerEvent.message_id)
        .filter(
            PanTransferFollowTriggerEvent.message_id.in_(normalized_ids),
            PanTransferFollowTriggerEvent.event_type == FOLLOW_TRIGGER_EVENT_TYPE_MESSAGE_LINK_RECEIVED,
        )
        .all()
    }
    created_count = 0
    skipped_count = 0
    for message in messages:
        message_id = int(message.id)
        if message_id in existing_ids:
            continue
        if not isinstance(getattr(message, "links", None), (dict, list)) or not message.links:
            skipped_count += 1
            continue
        identity = parse_resource_identity(getattr(message, "title", None))
        event = PanTransferFollowTriggerEvent(
            message_id=message_id,
            event_type=FOLLOW_TRIGGER_EVENT_TYPE_MESSAGE_LINK_RECEIVED,
            status=FOLLOW_TRIGGER_EVENT_STATUS_PENDING,
            candidate_title=_normalize_text(getattr(message, "title", None), max_length=255) or None,
            candidate_episode=_normalize_optional_int(getattr(identity, "episode", None)),
            candidate_issue_no=_normalize_text(getattr(identity, "issue_no", None), max_length=32) or None,
            monitor_channel_key=_normalize_text(getattr(message, "monitor_channel_key", None), max_length=255) or None,
            monitor_chat_id=_normalize_optional_int(getattr(message, "monitor_chat_id", None)),
            max_attempts=FOLLOW_TRIGGER_EVENT_DEFAULT_MAX_ATTEMPTS,
            payload=_build_event_payload(message, identity=identity),
        )
        session.add(event)
        existing_ids.add(message_id)
        created_count += 1
    if created_count:
        session.flush()
    return {
        "created": created_count,
        "existing": len(existing_ids) - created_count,
        "skipped": skipped_count,
    }


def _build_tracked_identity(task: PanTransferSyncTask) -> Any:
    snapshot = dict(_get_task_extra_section(task, "identity_snapshot") or {})
    snapshot = _apply_follow_materialized_update_state_to_snapshot(
        task,
        _apply_follow_applied_update_state_to_snapshot(task, snapshot),
    )
    resource_title = _resolve_follow_task_resource_title(task) or _normalize_text(
        snapshot.get("resource_title"),
        max_length=255,
    )
    identity = parse_resource_identity(resource_title)
    return _apply_follow_snapshot_progress_to_identity(identity, snapshot=snapshot)


def evaluate_follow_trigger(
    task: PanTransferSyncTask,
    *,
    candidate_title: str,
    candidate_message_time: datetime | None = None,
) -> dict[str, Any]:
    tracked_identity = _build_tracked_identity(task)
    candidate_identity = parse_resource_identity(candidate_title)
    decision = compare_follow_candidate(
        tracked_identity,
        candidate_identity,
        candidate_message_time=candidate_message_time,
    )
    result = decision.to_dict()
    result["tracked_identity"] = tracked_identity.to_dict()
    result["candidate_identity"] = candidate_identity.to_dict()
    result["triggerable"] = bool(
        decision.should_promote
        and not decision.needs_ai_review
        and not tracked_identity.needs_ai_review
        and not candidate_identity.needs_ai_review
    )
    if decision.should_promote and not result["triggerable"]:
        result["reason"] = "rule_trigger_requires_unambiguous_identity"
    return result


def _list_message_candidates(
    session: Session,
    *,
    message: Message,
    task: PanTransferSyncTask,
) -> list[dict[str, Any]]:
    query = (
        session.query(MessageLinkRef, LinkTarget)
        .join(LinkTarget, LinkTarget.id == MessageLinkRef.link_target_id)
        .filter(MessageLinkRef.message_id == int(message.id))
        .order_by(MessageLinkRef.link_index.asc(), LinkTarget.id.asc())
    )
    task_platform = _normalize_text(task.platform, max_length=64).lower()
    if task_platform:
        query = query.filter(LinkTarget.platform == task_platform)
    candidates: list[dict[str, Any]] = []
    for link_ref, link_target in query.all():
        url = _normalize_text(getattr(link_target, "original_url", None), max_length=2048)
        if not url:
            continue
        candidates.append(
            {
                "link_target_id": int(link_target.id),
                "message_id": int(message.id),
                "link_ref_id": int(link_ref.id),
                "link_index": int(link_ref.link_index),
                "url": url,
                "title": _normalize_text(getattr(message, "title", None), max_length=255) or "",
                "display_text": _normalize_text(getattr(link_ref, "display_text", None), max_length=255) or None,
                "latest_message_time": getattr(message, "timestamp", None),
            }
        )
    return candidates


def _pending_candidate_blocks_trigger(
    task: PanTransferSyncTask,
    *,
    candidate: Mapping[str, Any],
) -> bool:
    candidate_link_target_id = _normalize_optional_int(candidate.get("link_target_id"))
    if candidate_link_target_id is not None and candidate_link_target_id == _normalize_optional_int(task.last_candidate_link_target_id):
        return True
    pending_title = _normalize_text(task.last_candidate_title, max_length=255)
    candidate_title = _normalize_text(candidate.get("title"), max_length=255)
    if not pending_title or not candidate_title:
        return False
    pending_identity = parse_resource_identity(pending_title)
    candidate_identity = parse_resource_identity(candidate_title)
    if not pending_identity.is_target_work or not candidate_identity.is_target_work:
        return False
    if not any(
        left and right and (left == right or left in right or right in left)
        for left in pending_identity.normalized_keys
        for right in candidate_identity.normalized_keys
    ):
        return False
    if pending_identity.season is not None and candidate_identity.season is not None:
        if pending_identity.season != candidate_identity.season:
            return False
    if pending_identity.episode is not None and candidate_identity.episode is not None:
        return candidate_identity.episode <= pending_identity.episode
    if pending_identity.issue_sort_value is not None and candidate_identity.issue_sort_value is not None:
        return candidate_identity.issue_sort_value <= pending_identity.issue_sort_value
    return False


def _queue_task_from_trigger(
    session: Session,
    *,
    task: PanTransferSyncTask,
    candidate: Mapping[str, Any],
    assessment: Mapping[str, Any],
    event: PanTransferFollowTriggerEvent,
    now: datetime,
) -> None:
    extra_json = dict(task.extra_json or {})
    candidate_snapshot = dict(candidate)
    candidate_snapshot["latest_message_time"] = _serialize_datetime(candidate.get("latest_message_time"))
    extra_json["candidate_assessment"] = dict(assessment)
    extra_json["candidate_recall"] = {
        "queries": ["realtime_message_title"],
        "recall_count": 1,
        "evaluated_count": 1,
        "selected_candidate_title": candidate.get("title"),
        "selected_result": "realtime_trigger",
        "items": [
            {
                **candidate_snapshot,
                "decision": "realtime_trigger",
                "assessment": dict(assessment),
            }
        ],
    }
    extra_json["realtime_trigger"] = {
        "event_id": int(event.id),
        "message_id": int(event.message_id),
        "candidate_title": candidate.get("title"),
        "candidate_episode": assessment.get("candidate_episode"),
        "triggered_at": _serialize_datetime(now),
    }
    task.extra_json = extra_json
    task.task_state = PAN_TRANSFER_SYNC_STATE_QUEUED
    task.next_check_at = now
    task.last_change_type = "realtime_trigger"
    task.last_candidate_link_target_id = int(candidate["link_target_id"])
    task.last_candidate_url = str(candidate["url"])
    task.last_candidate_title = str(candidate.get("title") or "")
    task.last_candidate_message_time = candidate.get("latest_message_time")
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="realtime_trigger",
        message="A newer resource message triggered an immediate follow check",
        payload={
            "event_id": int(event.id),
            "message_id": int(event.message_id),
            "candidate": candidate_snapshot,
            "assessment": dict(assessment),
        },
    )


def _finish_event(
    event: PanTransferFollowTriggerEvent,
    *,
    status: str,
    now: datetime,
    payload: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    event.status = status
    event.processed_at = now if status == FOLLOW_TRIGGER_EVENT_STATUS_DONE else None
    event.next_retry_at = None
    event.last_error = _normalize_text(error, max_length=2000) or None
    if payload is not None:
        event.payload = dict(payload)


def process_next_pan_transfer_follow_trigger_event(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    now = utcnow()
    stale_cutoff = now - FOLLOW_TRIGGER_EVENT_STALE_PROCESSING_AFTER
    session.query(PanTransferFollowTriggerEvent).filter(
        PanTransferFollowTriggerEvent.status == FOLLOW_TRIGGER_EVENT_STATUS_PROCESSING,
        PanTransferFollowTriggerEvent.updated_at < stale_cutoff,
    ).update(
        {
            PanTransferFollowTriggerEvent.status: FOLLOW_TRIGGER_EVENT_STATUS_PENDING,
            PanTransferFollowTriggerEvent.next_retry_at: now,
            PanTransferFollowTriggerEvent.last_error: "stale processing event reclaimed",
        },
        synchronize_session=False,
    )
    event = (
        session.query(PanTransferFollowTriggerEvent)
        .filter(
            or_(
                PanTransferFollowTriggerEvent.status == FOLLOW_TRIGGER_EVENT_STATUS_PENDING,
                and_(
                    PanTransferFollowTriggerEvent.status == FOLLOW_TRIGGER_EVENT_STATUS_ERROR,
                    PanTransferFollowTriggerEvent.next_retry_at.isnot(None),
                    PanTransferFollowTriggerEvent.next_retry_at <= now,
                    PanTransferFollowTriggerEvent.attempt_count < PanTransferFollowTriggerEvent.max_attempts,
                ),
            )
        )
        .order_by(PanTransferFollowTriggerEvent.created_at.asc(), PanTransferFollowTriggerEvent.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if event is None:
        return False

    previous_attempt_count = int(event.attempt_count or 0)
    event.status = FOLLOW_TRIGGER_EVENT_STATUS_PROCESSING
    event.attempt_count = previous_attempt_count + 1
    event.last_error = None
    session.add(event)
    session.flush()
    try:
        message = session.get(Message, int(event.message_id))
        if message is None:
            _finish_event(event, status=FOLLOW_TRIGGER_EVENT_STATUS_DONE, now=now, payload={"reason": "message_missing"})
            session.flush()
            return True
        candidate_title = _normalize_text(getattr(message, "title", None), max_length=255)
        if not candidate_title:
            _finish_event(event, status=FOLLOW_TRIGGER_EVENT_STATUS_DONE, now=now, payload={"reason": "title_missing"})
            session.flush()
            return True

        event_payload = dict(event.payload or {})
        matched_task_ids: list[int] = []
        queued_task_ids: list[int] = []
        ignored_task_ids: list[int] = []
        deferred_task_ids: list[int] = []
        for task in (
            session.query(PanTransferSyncTask)
            .filter(PanTransferSyncTask.status == PAN_TRANSFER_SYNC_STATUS_ACTIVE)
            .order_by(PanTransferSyncTask.id.asc())
            .all()
        ):
            automation = _get_task_automation_config(task)
            if not bool(automation.get("enabled")):
                continue
            assessment = evaluate_follow_trigger(
                task,
                candidate_title=candidate_title,
                candidate_message_time=getattr(message, "timestamp", None),
            )
            if not assessment.get("is_same_work"):
                continue
            task_id = int(task.id)
            matched_task_ids.append(task_id)
            if not assessment.get("triggerable"):
                ignored_task_ids.append(task_id)
                continue
            if str(task.task_state or "") in {
                PAN_TRANSFER_SYNC_STATE_CHECKING,
                PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED,
            }:
                deferred_task_ids.append(task_id)
                continue
            candidates = _list_message_candidates(session, message=message, task=task)
            if not candidates:
                ignored_task_ids.append(task_id)
                continue
            if _pending_candidate_blocks_trigger(task, candidate=candidates[0]):
                ignored_task_ids.append(task_id)
                continue
            _queue_task_from_trigger(
                session,
                task=task,
                candidate=candidates[0],
                assessment=assessment,
                event=event,
                now=now,
            )
            queued_task_ids.append(task_id)

        event_payload.update(
            {
                "worker_name": _normalize_text(worker_name, max_length=128) or None,
                "message_title": candidate_title,
                "matched_task_ids": matched_task_ids,
                "queued_task_ids": queued_task_ids,
                "ignored_task_ids": ignored_task_ids,
                "deferred_task_ids": deferred_task_ids,
                "processed_at": _serialize_datetime(now),
            }
        )
        if deferred_task_ids:
            event.attempt_count = previous_attempt_count
            event.status = FOLLOW_TRIGGER_EVENT_STATUS_ERROR
            event.next_retry_at = now + FOLLOW_TRIGGER_EVENT_RETRY_DELAY
            event.last_error = "matched follow task is busy; trigger deferred"
            event.processed_at = None
            event.payload = event_payload
        else:
            _finish_event(event, status=FOLLOW_TRIGGER_EVENT_STATUS_DONE, now=now, payload=event_payload)
        session.flush()
        return True
    except Exception as exc:
        error_message = _normalize_text(exc, max_length=2000) or type(exc).__name__
        max_attempts = max(1, int(event.max_attempts or FOLLOW_TRIGGER_EVENT_DEFAULT_MAX_ATTEMPTS))
        retryable = int(event.attempt_count or 0) < max_attempts
        event.status = FOLLOW_TRIGGER_EVENT_STATUS_ERROR
        event.last_error = error_message
        event.next_retry_at = now + FOLLOW_TRIGGER_EVENT_RETRY_DELAY if retryable else None
        event.processed_at = None
        session.add(event)
        session.flush()
        return True
