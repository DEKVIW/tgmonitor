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
                if bool(payload.get("state")) and int(payload.get("errno", -1) or -1) == 0:
                    return self.valid_result(
                        target,
                        response_time=response_time,
                        status_code=response.status,
                    )
                error_message = str(payload.get("error") or "115 share is invalid")
                return self.invalid_result(
                    target,
                    error=error_message,
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


from .pan115_runtime import Pan115Checker  # noqa: E402,F401
