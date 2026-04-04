"""Lightweight in-process observability helpers for the monitor."""

from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

from app.core.monitor_parser import ParseDiagnostics


def log_monitor_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    parts = [f"event={event}"]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    logger.log(level, " ".join(parts))


class MonitorMetrics:
    def __init__(self, logger: logging.Logger, summary_every: int = 50) -> None:
        self._logger = logger
        self._summary_every = max(1, summary_every)
        self._lock = threading.RLock()
        self._counters: Counter[str] = Counter()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def record_parse(self, diagnostics: ParseDiagnostics, has_links: bool) -> None:
        with self._lock:
            self._counters["messages_processed"] += 1
            self._counters["messages_with_links" if has_links else "messages_without_links"] += 1
            self._counters["raw_urls_seen"] += diagnostics.raw_url_count
            self._counters["resolved_urls_seen"] += diagnostics.resolved_url_count
            self._counters["redirect_urls_resolved"] += diagnostics.redirect_resolved_count
            self._counters["links_extracted"] += diagnostics.extracted_link_count
            should_log = self._counters["messages_processed"] % self._summary_every == 0

        if should_log:
            self.log_summary()

    def record_refresh(self, configured: int, active: int, changed: bool) -> None:
        self.increment("channel_refreshes")
        log_monitor_event(
            self._logger,
            "channel_refresh",
            configured=configured,
            active=active,
            changed=str(changed).lower(),
        )

    def record_failure(self, name: str, **fields: Any) -> None:
        self.increment(f"{name}_failures")
        log_monitor_event(self._logger, f"{name}_failure", level=logging.WARNING, **fields)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def log_summary(self) -> None:
        snapshot = self.snapshot()
        log_monitor_event(self._logger, "monitor_summary", **snapshot)
