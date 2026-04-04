from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import aiohttp

from ..constants import PLATFORM_ALIYUN
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_share_id(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    return path_parts[-1] if path_parts else ""


def _is_invalid_error_code(code: str) -> bool:
    return any(token in code for token in ("NotFound", "Cancel", "InvalidParameter", "Forbidden"))


class AliyunChecker(BaseChecker):
    checker_name = "aliyun_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_ALIYUN, timeout=timeout)

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_id = _extract_share_id(target.resolved_url)
        if not share_id:
            return self.format_error_result(target, error="Unable to extract Aliyun share id")

        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.post(
                "https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous",
                json={"share_id": share_id},
                headers={
                    "authorization": "",
                    "content-type": "application/json",
                    "origin": "https://www.alipan.com",
                    "referer": "https://www.alipan.com/",
                    "x-canary": "client=web,app=share,version=v2.3.1",
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
                    if response.status in {400, 404}:
                        return self.invalid_result(
                            target,
                            error=f"HTTP {response.status}",
                            response_time=response_time,
                            status_code=response.status,
                        )
                    return self.uncertain_result(
                        target,
                        reason="状态码错误",
                        error=f"HTTP {response.status}",
                        response_time=response_time,
                        status_code=response.status,
                    )

                error_code = str(payload.get("code") or "")
                if payload.get("share_title") or payload.get("share_name"):
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )
                if error_code:
                    if _is_invalid_error_code(error_code):
                        return self.invalid_result(
                            target,
                            error=error_code,
                            response_time=response_time,
                            status_code=response.status,
                        )
                    if "TooMany" in error_code or "RateLimit" in error_code:
                        return self.rate_limited_result(
                            target,
                            error=error_code,
                            response_time=response_time,
                            status_code=response.status,
                        )
                    return self.uncertain_result(
                        target,
                        error=error_code,
                        response_time=response_time,
                        status_code=response.status,
                    )

                return self.uncertain_result(
                    target,
                    error="Unexpected Aliyun response",
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
