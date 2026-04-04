from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import aiohttp

from ..constants import PLATFORM_123
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_share_key(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "s":
        return path_parts[1]
    return path_parts[-1] if path_parts else ""


class Pan123Checker(BaseChecker):
    checker_name = "pan123_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_123, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_key = _extract_share_key(target.resolved_url)
        if not share_key:
            return self.format_error_result(target, error="Unable to extract 123Pan share key")

        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                f"https://www.123pan.com/api/share/info?shareKey={share_key}",
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                response_time = time.perf_counter() - started_at
                if response.status == 403:
                    return self.uncertain_result(
                        target,
                        error="HTTP 403",
                        response_time=response_time,
                        status_code=response.status,
                    )

                payload, _ = await self.read_json_body(response)
                if response.status != 200:
                    return self.uncertain_result(
                        target,
                        reason="状态码错误",
                        error=f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )

                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                message = str(payload.get("message") or payload.get("msg") or "").strip()
                message_lower = message.lower()
                code_value = payload.get("code")

                if bool(data.get("HasPwd")) or "提取码" in message or "password" in message_lower:
                    return self.requires_code_result(
                        target,
                        error="Missing extraction code",
                        response_time=response_time,
                        status_code=response.status,
                    )

                if str(code_value).strip() in {"0", ""} and payload:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )

                if message_lower in {"ok", "success"}:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )

                invalid_markers = ("失效", "不存在", "删除", "取消", "违规", "过期")
                if any(marker in message for marker in invalid_markers):
                    return self.invalid_result(
                        target,
                        error=message or str(code_value or "Invalid share"),
                        response_time=response_time,
                        status_code=response.status,
                    )

                return self.uncertain_result(
                    target,
                    error=message or str(code_value or "Unexpected 123Pan response"),
                    response_time=response_time,
                    status_code=response.status,
                    meta={"payload_keys": sorted(payload.keys())},
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
