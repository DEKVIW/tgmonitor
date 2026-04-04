from __future__ import annotations

import asyncio
import time

import aiohttp

from ..constants import GENERAL_INVALID_PATTERNS, PLATFORM_INVALID_PATTERNS
from ..result import REASON_EXCEPTION, REASON_HTTP, REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


class GenericLinkChecker(BaseChecker):
    checker_name = "generic_html"

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        if not target.resolved_url:
            return self.format_error_result(target, error="Empty url")

        started_at = time.perf_counter()
        try:
            await self.apply_rate_limit()
            async with http_session.get(
                target.resolved_url,
                allow_redirects=True,
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
                if status_code in {401, 403}:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if status_code >= 500:
                    return self.uncertain_result(
                        target,
                        reason=REASON_HTTP,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if status_code != 200:
                    return self.invalid_result(
                        target,
                        error=f"HTTP {status_code}",
                        response_time=response_time,
                        status_code=status_code,
                    )

                body = await response.text(errors="ignore")
                for pattern in PLATFORM_INVALID_PATTERNS.get(target.netdisk_type, ()):
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

                return self.valid_result(
                    target,
                    response_time=response_time,
                    status_code=status_code,
                    meta={"final_url": str(response.url)},
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
        except Exception as exc:  # pragma: no cover
            return self.uncertain_result(
                target,
                reason=REASON_EXCEPTION,
                error=str(exc),
                response_time=time.perf_counter() - started_at,
            )
