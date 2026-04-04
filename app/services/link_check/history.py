from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable

from sqlalchemy.orm import Session

from app.models.models import LinkCheckDetails, engine

from .cache import get_cache_ttl_for_status, should_cache_status
from .constants import UNKNOWN_PLATFORM
from .result import LinkCheckResult, REASON_VALID, STATUS_INVALID, STATUS_VALID

logger = logging.getLogger(__name__)


def _normalize_history_status(action_taken: str | None, is_valid: bool) -> str:
    normalized = (action_taken or "").strip().lower()
    if normalized and normalized != "none":
        return normalized
    return STATUS_VALID if is_valid else STATUS_INVALID


class LinkCheckHistoryProvider:
    def get_recent_results(self, urls: Iterable[str]) -> Dict[str, LinkCheckResult]:
        normalized_urls = [url for url in dict.fromkeys(urls) if url]
        if not normalized_urls:
            return {}

        try:
            with Session(engine) as session:
                rows = (
                    session.query(LinkCheckDetails)
                    .filter(LinkCheckDetails.url.in_(normalized_urls))
                    .order_by(LinkCheckDetails.check_time.desc(), LinkCheckDetails.id.desc())
                    .all()
                )
        except Exception as exc:  # pragma: no cover - depends on runtime DB
            logger.warning("failed to load link check history for reuse: %s", exc)
            return {}

        now = datetime.now()
        results: Dict[str, LinkCheckResult] = {}
        for row in rows:
            if row.url in results:
                continue

            status = _normalize_history_status(row.action_taken, bool(row.is_valid))
            if not should_cache_status(status):
                continue

            ttl_seconds = get_cache_ttl_for_status(status)
            if row.check_time and now - row.check_time > timedelta(seconds=ttl_seconds):
                continue

            results[row.url] = LinkCheckResult(
                url=row.url,
                netdisk_type=row.netdisk_type or UNKNOWN_PLATFORM,
                is_valid=bool(row.is_valid),
                status=status,
                response_time=row.response_time,
                error=row.error_reason,
                reason=row.error_reason or (REASON_VALID if row.is_valid else "网盘链接失效"),
                checker="history",
                meta={
                    "history_check_time": row.check_time.isoformat() if row.check_time else None,
                },
            )

        return results
