from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import ForegroundLinkHealthCandidate, Message
from app.services.channel_daily_stats_service import rebuild_channel_daily_stats_for_pairs
from app.services.link_check.cache import CACHE_TTLS_SECONDS, LinkCheckResultCache
from app.services.link_check.parser import (
    canonical_target_key,
    normalize_candidate_url,
)
from app.services.link_check.result import STATUS_INVALID
from app.services.link_check.validator import LinkValidator
from app.services.resource_ops import (
    delete_message_resource_data,
    ensure_message_link_refs_for_message_ids,
)

logger = logging.getLogger(__name__)

_FOREGROUND_CACHEABLE_STATUSES = frozenset(CACHE_TTLS_SECONDS)
_CANDIDATE_STATUS_PENDING = "pending"
_CANDIDATE_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ForegroundLinkInput:
    message_id: int
    url: str
    normalized_url: str
    normalized_url_hash: str


@dataclass(slots=True)
class ForegroundSearchCheck:
    invalid_by_message: Dict[int, set[str]]
    network_observations: List[Dict[str, Any]]
    checked_links: int
    truncated: bool


def _normalize_links_payload(links: Any) -> Any:
    if isinstance(links, str):
        try:
            return json.loads(links)
        except Exception:
            return links
    return links


def _canonical_url(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    normalized = normalize_candidate_url(url)
    return canonical_target_key(normalized) if normalized else ""


def _url_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _iter_urls(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and _canonical_url(url):
            yield url
            return
        for child in value.values():
            yield from _iter_urls(child)
        return

    if isinstance(value, list):
        for child in value:
            yield from _iter_urls(child)
        return

    if isinstance(value, str) and _canonical_url(value):
        yield value


def _build_link_key(url: Any) -> str:
    return _canonical_url(url)


def _extract_message_inputs(messages: Iterable[Message], limit: int) -> tuple[List[ForegroundLinkInput], bool]:
    inputs: List[ForegroundLinkInput] = []
    seen: set[tuple[int, str]] = set()
    truncated = False

    for message in messages:
        message_id = int(getattr(message, "id", 0) or 0)
        if message_id <= 0:
            continue

        for raw_url in _iter_urls(_normalize_links_payload(getattr(message, "links", None))):
            normalized_url = _build_link_key(raw_url)
            if not normalized_url or (message_id, normalized_url) in seen:
                continue
            if len(inputs) >= limit:
                truncated = True
                return inputs, truncated
            seen.add((message_id, normalized_url))
            inputs.append(
                ForegroundLinkInput(
                    message_id=message_id,
                    url=raw_url,
                    normalized_url=normalized_url,
                    normalized_url_hash=_url_hash(normalized_url),
                )
            )

    return inputs, truncated


def _is_empty_container(value: Any) -> bool:
    return value is None or value == {} or value == []


def filter_link_payload(value: Any, invalid_urls: set[str]) -> Any:
    if not invalid_urls:
        return value

    if isinstance(value, dict):
        link_url = value.get("url")
        if isinstance(link_url, str):
            if _build_link_key(link_url) in invalid_urls:
                return None
            cleaned: Dict[str, Any] = {}
            for key, child in value.items():
                if key == "url":
                    cleaned[key] = child
                    continue
                cleaned_child = filter_link_payload(child, invalid_urls)
                if cleaned_child is None and isinstance(child, (dict, list)):
                    continue
                cleaned[key] = cleaned_child
            return cleaned

        cleaned_dict: Dict[str, Any] = {}
        for key, child in value.items():
            cleaned_child = filter_link_payload(child, invalid_urls)
            if _is_empty_container(cleaned_child):
                continue
            cleaned_dict[key] = cleaned_child
        return cleaned_dict or None

    if isinstance(value, list):
        cleaned_list = []
        for child in value:
            cleaned_child = filter_link_payload(child, invalid_urls)
            if _is_empty_container(cleaned_child):
                continue
            cleaned_list.append(cleaned_child)
        return cleaned_list or None

    if isinstance(value, str) and _build_link_key(value) in invalid_urls:
        return None
    return value


def filter_tracked_links(payloads: Optional[List[Dict[str, Any]]], invalid_urls: set[str]) -> Optional[List[Dict[str, Any]]]:
    if not payloads:
        return None
    filtered = [
        payload
        for payload in payloads
        if _build_link_key(payload.get("target_url")) not in invalid_urls
    ]
    return filtered or None


def extract_netdisk_types(links: Any) -> List[str]:
    if isinstance(links, dict):
        return [key for key, value in links.items() if not _is_empty_container(value)]
    return []


def _message_channel_stat_pair(message: Message) -> Optional[Tuple[date, str]]:
    timestamp = getattr(message, "timestamp", None)
    channel_key = str(getattr(message, "monitor_channel_key", None) or "").strip()
    if not isinstance(timestamp, datetime) or not channel_key:
        return None
    return timestamp.date(), channel_key


def contains_any_link(value: Any) -> bool:
    return any(True for _ in _iter_urls(value))


class ForegroundLinkHealthService:
    def __init__(self) -> None:
        cache_limit = int(getattr(settings, "FOREGROUND_LINK_CHECK_CACHE_MAX_ENTRIES", 30000) or 30000)
        timeout = float(getattr(settings, "FOREGROUND_LINK_CHECK_TIMEOUT_SECONDS", 15) or 15)
        self.max_links = max(1, int(getattr(settings, "FOREGROUND_LINK_CHECK_MAX_LINKS", 40) or 40))
        self.max_concurrent = max(
            1,
            int(getattr(settings, "FOREGROUND_LINK_CHECK_MAX_CONCURRENT", 5) or 5),
        )
        self.min_invalid_confirmations = max(
            1,
            int(getattr(settings, "FOREGROUND_LINK_CHECK_MIN_INVALID_CONFIRMATIONS", 2) or 2),
        )
        self.candidate_retention_days = max(
            1,
            int(getattr(settings, "FOREGROUND_LINK_CHECK_CANDIDATE_RETENTION_DAYS", 30) or 30),
        )
        self.validator = LinkValidator(
            timeout=timeout,
            result_cache=LinkCheckResultCache(
                cacheable_statuses=_FOREGROUND_CACHEABLE_STATUSES,
                max_entries=cache_limit,
            ),
            use_history=False,
            enable_inflight=True,
        )

    async def check_messages(self, messages: Iterable[Message]) -> ForegroundSearchCheck:
        inputs, truncated = _extract_message_inputs(messages, self.max_links)
        if not inputs:
            return ForegroundSearchCheck({}, [], 0, truncated)

        network_observations: List[Dict[str, Any]] = []

        async def on_result(event: Dict[str, Any]) -> None:
            if event.get("source") != "network":
                return
            input_index = int(event.get("input_index", -1))
            if input_index < 0 or input_index >= len(inputs):
                return
            link_input = inputs[input_index]
            network_observations.append(
                {
                    "message_id": link_input.message_id,
                    "url": link_input.url,
                    "normalized_url": link_input.normalized_url,
                    "normalized_url_hash": link_input.normalized_url_hash,
                    "netdisk_type": str(event.get("platform") or "未知网盘"),
                    "status": str(event.get("status") or "uncertain"),
                    "reason": event.get("reason") or event.get("error"),
                    "checker": event.get("checker"),
                    "response_time": event.get("response_time"),
                }
            )

        results = await self.validator.check_multiple_links_with_progress(
            [item.url for item in inputs],
            max_concurrent=self.max_concurrent,
            result_callback=on_result,
        )

        invalid_by_message: Dict[int, set[str]] = defaultdict(set)
        for index, result in enumerate(results):
            if index >= len(inputs) or result.get("status") != STATUS_INVALID:
                continue
            invalid_by_message[inputs[index].message_id].add(inputs[index].normalized_url)

        return ForegroundSearchCheck(
            invalid_by_message=dict(invalid_by_message),
            network_observations=network_observations,
            checked_links=len(results),
            truncated=truncated,
        )

    def record_observations(self, db: Session, observations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        unique_observations: Dict[tuple[int, str, str], Dict[str, Any]] = {}
        for observation in observations:
            message_id = int(observation.get("message_id") or 0)
            normalized_url = str(observation.get("normalized_url") or "").strip()
            if message_id > 0 and normalized_url:
                netdisk_type = str(observation.get("netdisk_type") or "未知网盘")
                normalized_url_hash = str(observation.get("normalized_url_hash") or "").strip()
                if not normalized_url_hash:
                    normalized_url_hash = _url_hash(normalized_url)
                unique_observations[(message_id, netdisk_type, normalized_url_hash)] = observation

        if not unique_observations:
            return {
                "updated_candidates": 0,
                "resolved_candidates": 0,
                "removed_links": 0,
                "deleted_messages": 0,
                "deleted_message_ids": [],
            }

        now = datetime.utcnow()
        changed = False
        try:
            with _CANDIDATE_WRITE_LOCK:
                stale_cutoff = now - timedelta(days=self.candidate_retention_days)
                stale_deleted = db.query(ForegroundLinkHealthCandidate).filter(
                    ForegroundLinkHealthCandidate.last_checked_at < stale_cutoff,
                ).delete(synchronize_session=False)
                changed = bool(stale_deleted)
                candidate_ids: set[int] = set()

                for (message_id, netdisk_type, _normalized_url_hash), observation in unique_observations.items():
                    normalized_url = str(observation.get("normalized_url") or "").strip()
                    netdisk_type = str(observation.get("netdisk_type") or "未知网盘")
                    normalized_url_hash = str(observation.get("normalized_url_hash") or "").strip()
                    if not normalized_url_hash:
                        normalized_url_hash = _url_hash(normalized_url)
                    query = db.query(ForegroundLinkHealthCandidate).filter(
                        ForegroundLinkHealthCandidate.message_id == message_id,
                        ForegroundLinkHealthCandidate.netdisk_type == netdisk_type,
                        ForegroundLinkHealthCandidate.normalized_url_hash == normalized_url_hash,
                    )
                    candidate = query.with_for_update().first()
                    if observation.get("status") == STATUS_INVALID:
                        created = False
                        if candidate is None:
                            try:
                                with db.begin_nested():
                                    candidate = ForegroundLinkHealthCandidate(
                                        message_id=message_id,
                                        netdisk_type=netdisk_type,
                                        url=str(observation.get("url") or normalized_url),
                                        normalized_url=normalized_url,
                                        normalized_url_hash=normalized_url_hash,
                                        candidate_status=_CANDIDATE_STATUS_PENDING,
                                        invalid_observations=1,
                                        first_invalid_at=now,
                                        last_checked_at=now,
                                        last_reason=observation.get("reason"),
                                        last_checker=observation.get("checker"),
                                        last_response_time=observation.get("response_time"),
                                    )
                                    db.add(candidate)
                                    db.flush()
                                created = True
                            except IntegrityError:
                                candidate = query.with_for_update().first()
                                if candidate is None:
                                    raise
                        else:
                            candidate.invalid_observations = int(candidate.invalid_observations or 0) + 1

                        if not created:
                            candidate.candidate_status = _CANDIDATE_STATUS_PENDING
                            candidate.last_checked_at = now
                            candidate.last_reason = observation.get("reason")
                            candidate.last_checker = observation.get("checker")
                            candidate.last_response_time = observation.get("response_time")
                        if getattr(candidate, "id", None):
                            candidate_ids.add(int(candidate.id))
                        changed = True
                    else:
                        deleted = query.delete(synchronize_session=False)
                        changed = changed or bool(deleted)

                if changed:
                    db.flush()

                cleanup_result = self._cleanup_confirmed_candidates(db, candidate_ids)
                if changed or cleanup_result["removed_links"] or cleanup_result["deleted_messages"]:
                    db.commit()
        except Exception:
            db.rollback()
            logger.exception("failed to record foreground link health observations")
            return {
                "updated_candidates": 0,
                "resolved_candidates": 0,
                "removed_links": 0,
                "deleted_messages": 0,
                "deleted_message_ids": [],
            }

        return {
            "updated_candidates": sum(
                1 for observation in unique_observations.values() if observation.get("status") == STATUS_INVALID
            ),
            "resolved_candidates": sum(
                1 for observation in unique_observations.values() if observation.get("status") != STATUS_INVALID
            ),
            **cleanup_result,
        }

    def _cleanup_confirmed_candidates(
        self,
        db: Session,
        candidate_ids: Iterable[int],
    ) -> Dict[str, Any]:
        normalized_candidate_ids = sorted({int(candidate_id) for candidate_id in candidate_ids if int(candidate_id) > 0})
        if not normalized_candidate_ids:
            return {"removed_links": 0, "deleted_messages": 0, "deleted_message_ids": []}

        candidates = (
            db.query(ForegroundLinkHealthCandidate)
            .filter(
                ForegroundLinkHealthCandidate.id.in_(normalized_candidate_ids),
                ForegroundLinkHealthCandidate.candidate_status == _CANDIDATE_STATUS_PENDING,
                ForegroundLinkHealthCandidate.invalid_observations >= self.min_invalid_confirmations,
            )
            .order_by(ForegroundLinkHealthCandidate.id.asc())
            .all()
        )
        if not candidates:
            return {"removed_links": 0, "deleted_messages": 0, "deleted_message_ids": []}

        invalid_by_message: Dict[int, set[str]] = defaultdict(set)
        for candidate in candidates:
            invalid_by_message[int(candidate.message_id)].add(candidate.normalized_url)

        messages = db.query(Message).filter(Message.id.in_(list(invalid_by_message))).all()
        messages_by_id = {int(message.id): message for message in messages}
        updated_ids: List[int] = []
        deleted_ids: List[int] = []
        deleted_messages: List[Message] = []
        affected_pairs: set[Tuple[date, str]] = set()
        removed_links = 0

        for message_id, invalid_urls in invalid_by_message.items():
            message = messages_by_id.get(message_id)
            if message is None:
                continue

            original_links = _normalize_links_payload(message.links)
            cleaned_links = filter_link_payload(original_links, invalid_urls)
            cleaned_links = None if _is_empty_container(cleaned_links) else cleaned_links
            removed_count = sum(
                1
                for url in _iter_urls(original_links)
                if _build_link_key(url) in invalid_urls
            )
            if removed_count <= 0:
                continue

            removed_links += removed_count
            if not contains_any_link(cleaned_links):
                deleted_ids.append(message_id)
                deleted_messages.append(message)
            else:
                message.links = cleaned_links
                message.netdisk_types = extract_netdisk_types(cleaned_links)
                updated_ids.append(message_id)

            stat_pair = _message_channel_stat_pair(message)
            if stat_pair is not None:
                affected_pairs.add(stat_pair)

        if updated_ids:
            ensure_message_link_refs_for_message_ids(db, updated_ids)
        if deleted_ids:
            delete_message_resource_data(db, deleted_ids)
            for message in deleted_messages:
                db.delete(message)

        if affected_pairs:
            try:
                with db.begin_nested():
                    rebuild_channel_daily_stats_for_pairs(db, affected_pairs)
            except Exception:
                logger.exception("failed to rebuild channel daily stats after foreground cleanup")

        candidate_ids = [int(candidate.id) for candidate in candidates if getattr(candidate, "id", None)]
        if candidate_ids:
            db.query(ForegroundLinkHealthCandidate).filter(
                ForegroundLinkHealthCandidate.id.in_(candidate_ids)
            ).delete(synchronize_session=False)

        return {
            "removed_links": removed_links,
            "deleted_messages": len(deleted_ids),
            "deleted_message_ids": deleted_ids,
        }

    def list_candidates(self, db: Session, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        query = db.query(ForegroundLinkHealthCandidate).filter(
            ForegroundLinkHealthCandidate.candidate_status == _CANDIDATE_STATUS_PENDING
        )
        total = query.count()
        rows = (
            query.outerjoin(Message, Message.id == ForegroundLinkHealthCandidate.message_id)
            .with_entities(
                ForegroundLinkHealthCandidate,
                Message.title,
                Message.timestamp,
            )
            .order_by(
                ForegroundLinkHealthCandidate.invalid_observations.desc(),
                ForegroundLinkHealthCandidate.last_checked_at.desc(),
                ForegroundLinkHealthCandidate.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "items": [
                {
                    "id": int(candidate.id),
                    "message_id": int(candidate.message_id),
                    "message_title": message_title,
                    "message_timestamp": message_timestamp,
                    "netdisk_type": candidate.netdisk_type,
                    "url": candidate.url,
                    "invalid_observations": int(candidate.invalid_observations or 0),
                    "first_invalid_at": candidate.first_invalid_at,
                    "last_checked_at": candidate.last_checked_at,
                    "last_reason": candidate.last_reason,
                    "last_checker": candidate.last_checker,
                }
                for candidate, message_title, message_timestamp in rows
            ],
        }


FOREGROUND_LINK_HEALTH = ForegroundLinkHealthService()
