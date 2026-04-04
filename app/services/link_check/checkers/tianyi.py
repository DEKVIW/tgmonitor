from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, quote, urlparse

import aiohttp

from ..constants import PLATFORM_TIANYI
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_code_and_access_code(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    code = parse_qs(parsed.query).get("code", [""])[0]
    access_code = (
        parse_qs(parsed.query).get("accessCode", [""])[0]
        or parse_qs(parsed.query).get("pwd", [""])[0]
    )

    if not code and parsed.path.startswith("/t/"):
        code = parsed.path.split("/t/", 1)[1].split("/", 1)[0]

    if not code and parsed.fragment:
        fragment = parsed.fragment.lstrip("#")
        if fragment.startswith("/t/"):
            code = fragment.split("/t/", 1)[1].split("/", 1)[0]

    return code, access_code


def _extract_share_id(payload: dict) -> str:
    candidates = [
        payload.get("shareId"),
        payload.get("share_id"),
        (payload.get("data") or {}).get("shareId") if isinstance(payload.get("data"), dict) else None,
        (payload.get("shareInfo") or {}).get("shareId") if isinstance(payload.get("shareInfo"), dict) else None,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value != "0":
            return value
    return ""


def _extract_need_access_code(payload: dict) -> int:
    candidates = [
        payload.get("needAccessCode"),
        payload.get("need_access_code"),
        (payload.get("data") or {}).get("needAccessCode") if isinstance(payload.get("data"), dict) else None,
        (payload.get("shareInfo") or {}).get("needAccessCode") if isinstance(payload.get("shareInfo"), dict) else None,
    ]
    for candidate in candidates:
        try:
            return int(candidate or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _extract_message(payload: dict) -> str:
    return str(
        payload.get("res_message")
        or payload.get("message")
        or payload.get("msg")
        or ""
    )


class TianyiChecker(BaseChecker):
    checker_name = "tianyi_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_TIANYI, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        code, access_code = _extract_code_and_access_code(target.resolved_url)
        if not code:
            return self.format_error_result(target, error="Unable to extract Tianyi share code")

        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                "https://cloud.189.cn/api/open/share/getShareInfoByCodeV2.action"
                f"?shareCode={quote(code)}",
                headers={
                    "referer": target.resolved_url,
                    "sign-type": "1",
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                payload, _ = await self.read_json_body(response)
                if response.status == 429:
                    return self.rate_limited_result(
                        target,
                        error="HTTP 429",
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response.status != 200:
                    return self.uncertain_result(
                        target,
                        reason="状态码错误",
                        error=f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )

                share_id = _extract_share_id(payload)
                message = _extract_message(payload)
                need_access_code = _extract_need_access_code(payload)
                response_code = str(
                    payload.get("res_code")
                    or payload.get("resCode")
                    or payload.get("code")
                    or ""
                ).strip()

                if share_id:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )
                if need_access_code == 1 or "访问码" in message or "提取码" in message:
                    return self.requires_code_result(
                        target,
                        error=message or ("Missing access code" if not access_code else "Access code required"),
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response_code in {"429", "-62"}:
                    return self.rate_limited_result(
                        target,
                        error=message or response_code,
                        response_time=response_time,
                        status_code=response.status,
                    )
                if response_code in {"0", "SUCCESS", "success"}:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )
                if message:
                    return self.invalid_result(
                        target,
                        error=message,
                        response_time=response_time,
                        status_code=response.status,
                    )
                return self.uncertain_result(
                    target,
                    error="Unexpected Tianyi response",
                    response_time=response_time,
                    status_code=response.status,
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
