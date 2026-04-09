from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from app.models.config import settings

from .result import (
    LinkCheckResult,
    STATUS_FORMAT_ERROR,
    STATUS_INVALID,
    STATUS_RATE_LIMITED,
    STATUS_REQUIRES_CODE,
    STATUS_UNCERTAIN,
    STATUS_UNSUPPORTED,
    STATUS_VALID,
)

CACHE_TTLS_SECONDS = {
    STATUS_VALID: 15 * 60,
    STATUS_INVALID: 6 * 60 * 60,
    STATUS_REQUIRES_CODE: 6 * 60 * 60,
    STATUS_RATE_LIMITED: 5 * 60,
    STATUS_UNCERTAIN: 3 * 60,
    STATUS_UNSUPPORTED: 30 * 60,
    STATUS_FORMAT_ERROR: 10 * 60,
}

CACHEABLE_STATUSES = {
    STATUS_VALID,
    STATUS_REQUIRES_CODE,
    STATUS_RATE_LIMITED,
    STATUS_UNSUPPORTED,
}
MAX_CACHE_ENTRIES = max(1000, int(getattr(settings, "LINK_CHECK_RESULT_CACHE_MAX_ENTRIES", 30000) or 30000))
PRUNE_BATCH_SIZE = max(256, MAX_CACHE_ENTRIES // 10)


def get_cache_ttl_for_status(status: str) -> int:
    return CACHE_TTLS_SECONDS.get(status, 5 * 60)


def should_cache_status(status: str) -> bool:
    return status in CACHEABLE_STATUSES


@dataclass(slots=True)
class _CacheEntry:
    result: LinkCheckResult
    expires_at: float
    created_at: float


class LinkCheckResultCache:
    def __init__(self) -> None:
        self._entries: Dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()

    def _prune_locked(self, now: float) -> None:
        expired_keys = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._entries.pop(key, None)

        overflow = len(self._entries) - MAX_CACHE_ENTRIES
        if overflow <= 0:
            return

        prune_count = max(overflow, PRUNE_BATCH_SIZE)
        oldest_keys = [
            key
            for key, _entry in sorted(
                self._entries.items(),
                key=lambda item: (item[1].expires_at, item[1].created_at, item[0]),
            )[:prune_count]
        ]
        for key in oldest_keys:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get(self, key: str) -> Optional[LinkCheckResult]:
        if not key:
            return None

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            return entry.result

    def set(
        self,
        keys: Iterable[str],
        result: LinkCheckResult,
        *,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        if not should_cache_status(result.status):
            return

        unique_keys = [key for key in dict.fromkeys(keys) if key]
        if not unique_keys:
            return

        ttl = ttl_seconds if ttl_seconds is not None else get_cache_ttl_for_status(result.status)
        now = time.monotonic()
        expires_at = now + max(ttl, 1)
        entry = _CacheEntry(result=result, expires_at=expires_at, created_at=now)

        with self._lock:
            for key in unique_keys:
                self._entries[key] = entry
            if len(self._entries) > MAX_CACHE_ENTRIES:
                self._prune_locked(now)


LINK_RESULT_CACHE = LinkCheckResultCache()
