from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    LinkClickEvent,
    LinkTarget,
    Message,
    MessageLinkRef,
    PanTransferBatchItem,
    PanTransferReplacementLog,
    ResourceCandidateLog,
    ResourceCandidateProfile,
    ResourceRecognitionTask,
    ResourceWorkBinding,
)
from app.services.link_check.parser import canonical_target_key
from app.services.resource_ops.catalog import (
    _refresh_link_target_daily_stats,
    flatten_message_links,
)

from .common import utcnow


def _normalize_links_payload(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_netdisk_types(links: Any) -> list[str]:
    if isinstance(links, dict):
        return [key for key, item in links.items() if item not in (None, {}, [], "")]
    return []


def _matches_old_url(value: str, *, old_normalized_url: str) -> bool:
    return canonical_target_key(str(value or "").strip()) == old_normalized_url


def _replace_urls_in_links(value: Any, *, old_normalized_url: str, new_url: str) -> tuple[Any, int]:
    replaced = 0
    if isinstance(value, dict):
        if isinstance(value.get("url"), str):
            copied = dict(value)
            if _matches_old_url(str(copied.get("url") or ""), old_normalized_url=old_normalized_url):
                copied["url"] = new_url
                replaced += 1
            return copied, replaced

        copied: dict[str, Any] = {}
        for key, item in value.items():
            next_item, child_count = _replace_urls_in_links(item, old_normalized_url=old_normalized_url, new_url=new_url)
            copied[key] = next_item
            replaced += child_count
        return copied, replaced

    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            next_item, child_count = _replace_urls_in_links(item, old_normalized_url=old_normalized_url, new_url=new_url)
            items.append(next_item)
            replaced += child_count
        return items, replaced

    if isinstance(value, str):
        if _matches_old_url(str(value), old_normalized_url=old_normalized_url):
            return new_url, 1
        return value, 0

    return value, 0


def _ensure_link_target_for_url(session: Session, *, url: str, observed_at: datetime | None = None) -> LinkTarget:
    flattened = flatten_message_links({"url": url})
    if not flattened:
        raise ValueError("unable to parse new share url")
    item = flattened[0]
    target = (
        session.query(LinkTarget)
        .filter(
            LinkTarget.platform == item.platform,
            LinkTarget.normalized_url_hash == item.normalized_url_hash,
        )
        .first()
    )
    observed_time = observed_at or utcnow()
    if target is None:
        target = LinkTarget(
            platform=item.platform,
            original_url=item.target_url,
            normalized_url=item.normalized_url,
            normalized_url_hash=item.normalized_url_hash,
            share_key=item.share_key,
            passcode=item.passcode,
            first_seen_at=observed_time,
            last_seen_at=observed_time,
        )
        session.add(target)
        session.flush()
        return target

    target.original_url = item.target_url
    target.normalized_url = item.normalized_url
    target.share_key = item.share_key
    target.passcode = item.passcode
    if target.first_seen_at is None or observed_time < target.first_seen_at:
        target.first_seen_at = observed_time
    if target.last_seen_at is None or observed_time > target.last_seen_at:
        target.last_seen_at = observed_time
    session.add(target)
    session.flush()
    return target


def _merge_binding(session: Session, *, old_target_id: int, new_target_id: int) -> None:
    old_binding = session.query(ResourceWorkBinding).filter(ResourceWorkBinding.link_target_id == int(old_target_id)).first()
    new_binding = session.query(ResourceWorkBinding).filter(ResourceWorkBinding.link_target_id == int(new_target_id)).first()
    if old_binding is None:
        return
    if new_binding is None:
        old_binding.link_target_id = int(new_target_id)
        session.add(old_binding)
        session.flush()
        return

    if new_binding.work_id is None and old_binding.work_id is not None:
        new_binding.work_id = old_binding.work_id
        new_binding.match_status = old_binding.match_status
        new_binding.provider = old_binding.provider
        new_binding.provider_work_id = old_binding.provider_work_id
        new_binding.confidence = old_binding.confidence
        new_binding.match_source = old_binding.match_source
        new_binding.query_title = old_binding.query_title
        new_binding.candidate_title = old_binding.candidate_title
        new_binding.reason = old_binding.reason
        new_binding.last_attempted_at = old_binding.last_attempted_at
        new_binding.matched_at = old_binding.matched_at
        new_binding.error_message = old_binding.error_message
    new_binding.extra_json = {
        **dict(old_binding.extra_json or {}),
        **dict(new_binding.extra_json or {}),
    }
    session.add(new_binding)
    session.delete(old_binding)
    session.flush()


def _merge_candidate_profile(session: Session, *, old_target_id: int, new_target_id: int) -> None:
    old_profile = session.query(ResourceCandidateProfile).filter(ResourceCandidateProfile.link_target_id == int(old_target_id)).first()
    new_profile = session.query(ResourceCandidateProfile).filter(ResourceCandidateProfile.link_target_id == int(new_target_id)).first()
    if old_profile is None:
        return
    if new_profile is None:
        old_profile.link_target_id = int(new_target_id)
        session.add(old_profile)
        session.flush()
        return

    if str(new_profile.operation_status or "pending_review") == "pending_review" and str(old_profile.operation_status or ""):
        new_profile.operation_status = old_profile.operation_status
    if str(new_profile.value_status or "unreviewed") == "unreviewed" and str(old_profile.value_status or ""):
        new_profile.value_status = old_profile.value_status
    if not new_profile.manual_resource_kind and old_profile.manual_resource_kind:
        new_profile.manual_resource_kind = old_profile.manual_resource_kind
    if not str(new_profile.note or "").strip() and str(old_profile.note or "").strip():
        new_profile.note = old_profile.note
    new_profile.extra_json = {
        **dict(old_profile.extra_json or {}),
        **dict(new_profile.extra_json or {}),
    }
    if not new_profile.updated_by and old_profile.updated_by:
        new_profile.updated_by = old_profile.updated_by
    session.add(new_profile)
    session.delete(old_profile)
    session.flush()


def _merge_recognition_task(session: Session, *, old_target_id: int, new_target_id: int) -> None:
    old_task = session.query(ResourceRecognitionTask).filter(ResourceRecognitionTask.link_target_id == int(old_target_id)).first()
    new_task = session.query(ResourceRecognitionTask).filter(ResourceRecognitionTask.link_target_id == int(new_target_id)).first()
    if old_task is None:
        return
    if new_task is None:
        old_task.link_target_id = int(new_target_id)
        session.add(old_task)
        session.flush()
        return

    active_statuses = {"queued", "processing", "retry_wait"}
    preferred = old_task if str(old_task.status or "") in active_statuses and str(new_task.status or "") not in active_statuses else new_task
    secondary = new_task if preferred is old_task else old_task
    preferred.attempt_count = max(int(preferred.attempt_count or 0), int(secondary.attempt_count or 0))
    preferred.max_attempts = max(int(preferred.max_attempts or 0), int(secondary.max_attempts or 0))
    preferred.priority = max(int(preferred.priority or 0), int(secondary.priority or 0))
    if not preferred.last_error and secondary.last_error:
        preferred.last_error = secondary.last_error
    if preferred.link_target_id != int(new_target_id):
        preferred.link_target_id = int(new_target_id)
    session.add(preferred)
    session.delete(secondary)
    session.flush()


def replace_pan_transfer_links(
    session: Session,
    *,
    batch_item: PanTransferBatchItem,
    new_share_url: str,
    operator: str | None,
) -> dict[str, Any]:
    old_target = session.get(LinkTarget, int(batch_item.link_target_id))
    if old_target is None:
        raise LookupError("source link target not found")

    new_target = _ensure_link_target_for_url(session, url=new_share_url, observed_at=utcnow())
    if int(new_target.id) == int(old_target.id):
        log_row = PanTransferReplacementLog(
            batch_item_id=int(batch_item.id),
            old_link_target_id=int(old_target.id),
            new_link_target_id=int(new_target.id),
            old_url=str(old_target.original_url or ""),
            new_url=str(new_share_url or ""),
            affected_message_count=0,
            status="skipped",
            operator=operator,
            payload={"reason": "same_target"},
        )
        session.add(log_row)
        session.flush()
        return {
            "new_link_target_id": int(new_target.id),
            "affected_message_count": 0,
            "affected_ref_count": 0,
            "status": "skipped",
        }

    refs = (
        session.query(MessageLinkRef)
        .filter(MessageLinkRef.link_target_id == int(old_target.id))
        .order_by(MessageLinkRef.message_id.asc(), MessageLinkRef.link_index.asc())
        .all()
    )
    message_ids = sorted({int(ref.message_id) for ref in refs if ref.message_id is not None})
    messages = (
        session.query(Message)
        .filter(Message.id.in_(message_ids))
        .all()
        if message_ids
        else []
    )
    message_by_id = {int(message.id): message for message in messages if message.id is not None}

    affected_message_count = 0
    for message_id in message_ids:
        message = message_by_id.get(int(message_id))
        if message is None:
            continue
        normalized_links = _normalize_links_payload(message.links)
        next_links, replaced_count = _replace_urls_in_links(
            normalized_links,
            old_normalized_url=str(old_target.normalized_url or ""),
            new_url=str(new_share_url or ""),
        )
        if replaced_count <= 0:
            continue
        message.links = next_links
        message.netdisk_types = _extract_netdisk_types(next_links)
        session.add(message)
        affected_message_count += 1

    affected_ref_ids = [int(ref.id) for ref in refs if ref.id is not None]
    if affected_ref_ids:
        (
            session.query(MessageLinkRef)
            .filter(MessageLinkRef.id.in_(affected_ref_ids))
            .update(
                {
                    "link_target_id": int(new_target.id),
                    "target_url": str(new_share_url or ""),
                },
                synchronize_session=False,
            )
        )
        (
            session.query(LinkClickEvent)
            .filter(LinkClickEvent.link_ref_id.in_(affected_ref_ids))
            .update({"link_target_id": int(new_target.id)}, synchronize_session=False)
        )

    _merge_binding(session, old_target_id=int(old_target.id), new_target_id=int(new_target.id))
    _merge_candidate_profile(session, old_target_id=int(old_target.id), new_target_id=int(new_target.id))
    (
        session.query(ResourceCandidateLog)
        .filter(ResourceCandidateLog.link_target_id == int(old_target.id))
        .update({"link_target_id": int(new_target.id)}, synchronize_session=False)
    )
    _merge_recognition_task(session, old_target_id=int(old_target.id), new_target_id=int(new_target.id))

    log_row = PanTransferReplacementLog(
        batch_item_id=int(batch_item.id),
        old_link_target_id=int(old_target.id),
        new_link_target_id=int(new_target.id),
        old_url=str(old_target.original_url or ""),
        new_url=str(new_share_url or ""),
        affected_message_count=affected_message_count,
        status="replaced",
        operator=operator,
        payload={
            "affected_ref_count": len(affected_ref_ids),
        },
    )
    session.add(log_row)
    session.flush()
    _refresh_link_target_daily_stats(session, [int(old_target.id), int(new_target.id)])
    return {
        "new_link_target_id": int(new_target.id),
        "affected_message_count": affected_message_count,
        "affected_ref_count": len(affected_ref_ids),
        "status": "replaced",
    }
