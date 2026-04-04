from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

from ..constants import GENERAL_INVALID_PATTERNS, PLATFORM_INVALID_PATTERNS, PLATFORM_UC
from ..result import REASON_HTTP, REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker

_PASSCODE_KEYS = ("pwd", "passcode", "code", "password", "share_pwd", "sharepwd")
_REQUIRES_CODE_MARKERS = (
    "\u63d0\u53d6\u7801",
    "\u8bbf\u95ee\u7801",
    "\u5bc6\u7801",
    "passcode",
    "share_pwd",
)
_VALID_PAGE_MARKERS = (
    "__NUXT__",
    "share_title",
    "shareTitle",
    "shareInfo",
    "\u5206\u4eab\u6587\u4ef6",
    "\u6587\u4ef6\u5217\u8868",
)


def _extract_share_id(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "s":
        return path_parts[1]
    return ""


def _extract_passcode(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in _PASSCODE_KEYS:
        value = query.get(key, [""])[0]
        if value:
            return value
    return ""


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


class UCChecker(BaseChecker):
    checker_name = "uc_html"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_UC, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_id = _extract_share_id(target.resolved_url)
        if not share_id:
            return self.format_error_result(target, error="Unable to extract UC share id")

        passcode = _extract_passcode(target.resolved_url)
        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                target.resolved_url,
                allow_redirects=True,
                headers={"referer": "https://drive.uc.cn/"},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                status_code = response.status

                if status_code == 429:
                    return self.rate_limited_result(
                        target,
                        error="HTTP 429",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if status_code in {404, 410}:
                    return self.invalid_result(
                        target,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if status_code in {401, 403} or status_code >= 500:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if status_code != 200:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )

                body = await response.text(errors="ignore")
                for pattern in PLATFORM_INVALID_PATTERNS.get(PLATFORM_UC, ()):
                    if pattern.search(body):
                        return self.invalid_result(
                            target,
                            error=f"Matched invalid pattern: {pattern.pattern}",
                            response_time=response_time,
                            status_code=status_code,
                        )

                for pattern in GENERAL_INVALID_PATTERNS:
                    if pattern.search(body):
                        return self.invalid_result(
                            target,
                            error=f"Matched generic invalid pattern: {pattern.pattern}",
                            response_time=response_time,
                            status_code=status_code,
                        )

                if _contains_marker(body, _REQUIRES_CODE_MARKERS):
                    if not passcode:
                        return self.requires_code_result(
                            target,
                            error="UC share requires passcode",
                            response_time=response_time,
                            status_code=status_code,
                        )
                    return self.uncertain_result(
                        target,
                        error="UC share still requests passcode after applying one",
                        response_time=response_time,
                        status_code=status_code,
                    )

                if _contains_marker(body, _VALID_PAGE_MARKERS):
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=status_code,
                        meta={"final_url": str(response.url), "share_id": share_id},
                    )

                return self.uncertain_result(
                    target,
                    error="Unable to confidently classify UC share page",
                    response_time=response_time,
                    status_code=status_code,
                    meta={"final_url": str(response.url), "share_id": share_id},
                )
        except asyncio.TimeoutError:
            return self.uncertain_result(
                target,
                reason=REASON_TIMEOUT,
                error="Request timeout",
                response_time=time.perf_counter() - started_at,
            )
        except aiohttp.ClientError as exc:
            return self.uncertain_result(
                target,
                reason=REASON_NETWORK,
                error=str(exc),
                response_time=time.perf_counter() - started_at,
            )
