from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

from ..constants import PLATFORM_XUNLEI
from ..result import REASON_HTTP, REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker

_API_URL = "https://api-pan.xunlei.com/drive/v1/share"
_PASSCODE_KEYS = ("pwd", "pass_code", "passcode", "code")
_INVALID_SHARE_STATUSES = {
    "DELETED",
    "EXPIRED",
    "REMOVED",
    "FORBIDDEN",
    "ILLEGAL",
    "INVALID",
    "CANCELLED",
}
_INVALID_MARKERS = (
    "\u4e0d\u5b58\u5728",
    "\u5df2\u5931\u6548",
    "\u5df2\u5220\u9664",
    "\u8fdd\u89c4",
    "\u8fc7\u671f",
    "not found",
    "invalid share",
)
_REQUIRES_CODE_MARKERS = (
    "\u63d0\u53d6\u7801",
    "\u8bbf\u95ee\u7801",
    "\u5bc6\u7801",
    "pass_code",
    "passcode",
)
_RATE_LIMIT_MARKERS = (
    "\u9891\u7e41",
    "\u9650\u5236",
    "\u98ce\u63a7",
    "captcha",
    "verify",
    "shield",
    "rate limit",
)


def _extract_share_id(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "s":
        return path_parts[1]
    return ""


def _extract_passcode(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    for key in _PASSCODE_KEYS:
        value = query.get(key, [""])[0]
        if value:
            return value
    return ""


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _payload_text(payload: dict, raw_text: str) -> str:
    if raw_text:
        return raw_text
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)


class XunleiChecker(BaseChecker):
    checker_name = "xunlei_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_XUNLEI, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_id = _extract_share_id(target.resolved_url)
        if not share_id:
            return self.format_error_result(target, error="Unable to extract Xunlei share id")

        passcode = _extract_passcode(target.resolved_url)
        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                _API_URL,
                params={
                    "share_id": share_id,
                    "pass_code": passcode,
                    "limit": 20,
                    "pass_code_token": "",
                    "page_token": "",
                    "thumbnail_size": "SIZE_SMALL",
                },
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://pan.xunlei.com",
                    "referer": "https://pan.xunlei.com/",
                    "x-client-id": "ZUBzD9J_XPXfn7f7",
                    "x-device-id": "5505bd0cab8c9469b98e5891d9fb3e0d",
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                payload, raw_body = await self.read_json_body(response)
                response_text = _payload_text(payload, raw_body)
                message = str(
                    payload.get("error")
                    or payload.get("message")
                    or payload.get("share_status_text")
                    or ""
                )
                error_code = str(payload.get("error_code") or payload.get("code") or "")
                share_status = str(payload.get("share_status") or "").upper()

                if response.status == 429 or error_code == "9":
                    return self.rate_limited_result(
                        target,
                        error=message or error_code or "Xunlei API rate limited",
                        response_time=response_time,
                        status_code=response.status,
                    )
                if _contains_marker(response_text, _RATE_LIMIT_MARKERS) and response.status != 200:
                    return self.rate_limited_result(
                        target,
                        error=message or response_text[:120],
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response.status in {404, 410}:
                    return self.invalid_result(
                        target,
                        error=f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response.status in {401, 403}:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=message or f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response.status != 200:
                    if _contains_marker(response_text, _REQUIRES_CODE_MARKERS):
                        if not passcode:
                            return self.requires_code_result(
                                target,
                                error=message or "Xunlei share requires passcode",
                                response_time=response_time,
                                status_code=response.status,
                            )
                        return self.uncertain_result(
                            target,
                            error=message or "Xunlei share still requires passcode",
                            response_time=response_time,
                            status_code=response.status,
                        )
                    if share_status in _INVALID_SHARE_STATUSES or _contains_marker(response_text, _INVALID_MARKERS):
                        return self.invalid_result(
                            target,
                            error=message or response_text[:120],
                            response_time=response_time,
                            status_code=response.status,
                        )
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=message or f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if share_status == "OK":
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                        meta={"share_id": share_id},
                    )

                if _contains_marker(response_text, _REQUIRES_CODE_MARKERS):
                    if not passcode:
                        return self.requires_code_result(
                            target,
                            error=message or "Xunlei share requires passcode",
                            response_time=response_time,
                            status_code=response.status,
                        )
                    return self.uncertain_result(
                        target,
                        error=message or "Xunlei share still requires passcode",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if share_status in _INVALID_SHARE_STATUSES or _contains_marker(response_text, _INVALID_MARKERS):
                    return self.invalid_result(
                        target,
                        error=message or response_text[:120],
                        response_time=response_time,
                        status_code=response.status,
                    )

                if _contains_marker(response_text, _RATE_LIMIT_MARKERS):
                    return self.uncertain_result(
                        target,
                        error=message or response_text[:120],
                        response_time=response_time,
                        status_code=response.status,
                    )

                return self.uncertain_result(
                    target,
                    error=message or "Unexpected Xunlei response",
                    response_time=response_time,
                    status_code=response.status,
                    meta={"share_id": share_id, "share_status": share_status or None},
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
