from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

from ..constants import PLATFORM_115
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_share_code_and_password(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    share_code = path_parts[-1] if path_parts else ""
    password = parse_qs(parsed.query).get("password", [""])[0]
    if not password and parsed.fragment:
        password = parse_qs(parsed.fragment).get("password", [""])[0]
    return share_code, password


class Pan115Checker(BaseChecker):
    checker_name = "pan115_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_115, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_code, password = _extract_share_code_and_password(target.resolved_url)
        if not share_code:
            return self.format_error_result(target, error="Unable to extract 115 share code")
        if not password:
            return self.requires_code_result(target, error="Missing extraction code")

        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                "https://115cdn.com/webapi/share/snap"
                f"?share_code={share_code}&offset=0&limit=20&receive_code={password}&cid=",
                headers={
                    "Referer": f"https://115cdn.com/s/{share_code}?password={password}&",
                    "X-Requested-With": "XMLHttpRequest",
                    "Priority": "u=1, i",
                },
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                payload, raw_body = await self.read_json_body(response)
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

                state = payload.get("state")
                errno = payload.get("errno")
                error_message = str(payload.get("error") or payload.get("msg") or "").strip()
                error_lower = error_message.lower()

                if bool(state) or str(errno).strip() in {"0", ""}:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )

                if any(keyword in error_message for keyword in ("提取码", "密码")):
                    return self.requires_code_result(
                        target,
                        error=error_message or "Missing extraction code",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if any(keyword in error_lower for keyword in ("login", "captcha", "risk")):
                    return self.uncertain_result(
                        target,
                        error=error_message,
                        response_time=response_time,
                        status_code=response.status,
                    )

                invalid_markers = ("失效", "不存在", "删除", "取消", "违规", "过期")
                if any(marker in error_message for marker in invalid_markers):
                    return self.invalid_result(
                        target,
                        error=error_message,
                        response_time=response_time,
                        status_code=response.status,
                    )

                if payload:
                    return self.uncertain_result(
                        target,
                        error=error_message or str(errno or "Unexpected 115 response"),
                        response_time=response_time,
                        status_code=response.status,
                        meta={"payload_keys": sorted(payload.keys())},
                    )

                return self.uncertain_result(
                    target,
                    error=raw_body or "Empty 115 response",
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
