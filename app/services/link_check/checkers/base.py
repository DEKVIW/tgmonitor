from __future__ import annotations

import abc
import asyncio
import json
import random
import time
from typing import Any, Dict, Optional

from aiohttp import ClientResponse

from ..constants import get_platform_config
from ..result import (
    CONSERVATIVE_VALID_STATUSES,
    LinkCheckResult,
    LinkTarget,
    REASON_EXCEPTION,
    REASON_FORMAT,
    REASON_INVALID,
    REASON_LIMIT,
    REASON_REQUIRES_CODE,
    REASON_UNSUPPORTED,
    REASON_VALID,
    STATUS_FORMAT_ERROR,
    STATUS_INVALID,
    STATUS_RATE_LIMITED,
    STATUS_REQUIRES_CODE,
    STATUS_UNCERTAIN,
    STATUS_UNSUPPORTED,
    STATUS_VALID,
)


class BaseChecker(abc.ABC):
    checker_name = "base"

    def __init__(self, platform: str, *, timeout: float = 15.0):
        config = get_platform_config(platform)
        self.platform = platform
        self.timeout = timeout
        self.max_concurrent = int(config.get("max_concurrent", 2))
        self.delay_range = tuple(config.get("delay_range", (0.0, 0.0)))
        self.max_requests_per_second = int(config.get("max_requests_per_second", 0) or 0)
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0

    def get_concurrency_limit(self) -> int:
        return self.max_concurrent

    async def apply_rate_limit(self) -> None:
        async with self._rate_lock:
            wait_for = 0.0
            now = time.monotonic()

            if self.max_requests_per_second > 0:
                min_interval = 1.0 / float(self.max_requests_per_second)
                wait_for = max(wait_for, self._last_request_at + min_interval - now)

            low, high = self.delay_range
            if high > 0:
                wait_for += random.uniform(low, high)

            if wait_for > 0:
                await asyncio.sleep(wait_for)

            self._last_request_at = time.monotonic()

    async def read_json_body(self, response: ClientResponse) -> tuple[Dict[str, Any], str]:
        body = await response.text(errors="ignore")
        if not body:
            return {}, ""

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}, body

        if isinstance(payload, dict):
            return payload, body
        return {}, body

    def make_result(
        self,
        target: LinkTarget,
        *,
        status: str,
        reason: str,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return LinkCheckResult(
            url=target.original_url,
            netdisk_type=target.netdisk_type,
            is_valid=status in CONSERVATIVE_VALID_STATUSES,
            status=status,
            response_time=response_time,
            status_code=status_code,
            error=error,
            reason=reason,
            resolved_url=target.resolved_url,
            checker=self.checker_name,
            meta=meta or {},
        )

    def valid_result(
        self,
        target: LinkTarget,
        *,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_VALID,
            reason=REASON_VALID,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def invalid_result(
        self,
        target: LinkTarget,
        *,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_INVALID,
            reason=REASON_INVALID,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def uncertain_result(
        self,
        target: LinkTarget,
        *,
        reason: str = REASON_EXCEPTION,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_UNCERTAIN,
            reason=reason,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def rate_limited_result(
        self,
        target: LinkTarget,
        *,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_RATE_LIMITED,
            reason=REASON_LIMIT,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def format_error_result(
        self,
        target: LinkTarget,
        *,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_FORMAT_ERROR,
            reason=REASON_FORMAT,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def requires_code_result(
        self,
        target: LinkTarget,
        *,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_REQUIRES_CODE,
            reason=REASON_REQUIRES_CODE,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    def unsupported_result(
        self,
        target: LinkTarget,
        *,
        error: Optional[str] = None,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> LinkCheckResult:
        return self.make_result(
            target,
            status=STATUS_UNSUPPORTED,
            reason=REASON_UNSUPPORTED,
            error=error,
            response_time=response_time,
            status_code=status_code,
            meta=meta,
        )

    @abc.abstractmethod
    async def check(self, target: LinkTarget, http_session: Any) -> LinkCheckResult:
        raise NotImplementedError
