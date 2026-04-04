from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

from ..constants import PLATFORM_QUARK
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_resource_id(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    password = (query.get("pwd") or query.get("passcode") or [""])[0]

    path_segments = [segment for segment in (parsed.path or "").split("/") if segment]
    if len(path_segments) >= 2 and path_segments[0] == "s" and path_segments[1]:
        return path_segments[1], password

    resource_id = (query.get("pwd_id") or [""])[0]
    return resource_id, password


def _looks_like_requires_code(message: str) -> bool:
    lowered = (message or "").lower()
    return "提取码" in (message or "") or "密码" in (message or "") or "passcode" in lowered


def _is_success_flag(value: object) -> bool:
    normalized = str(value if value is not None else "").strip().lower()
    return normalized in {"", "0", "200", "ok", "success"}


class QuarkChecker(BaseChecker):
    checker_name = "quark_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_QUARK, timeout=timeout)

    async def _request_token(
        self,
        http_session: aiohttp.ClientSession,
        *,
        resource_id: str,
        password: str,
    ) -> tuple[int, dict]:
        await self.apply_rate_limit()
        async with http_session.post(
            "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token",
            json={
                "pwd_id": resource_id,
                "passcode": password,
                "support_visit_limit_private_share": True,
            },
            headers={
                "content-type": "application/json",
                "origin": "https://pan.quark.cn",
                "referer": "https://pan.quark.cn/",
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            payload, _ = await self.read_json_body(response)
            return response.status, payload

    async def _request_detail(
        self,
        http_session: aiohttp.ClientSession,
        *,
        resource_id: str,
        stoken: str,
    ) -> tuple[int, dict]:
        await self.apply_rate_limit()
        params = urlencode(
            {
                "pwd_id": resource_id,
                "stoken": stoken,
                "ver": "2",
                "pr": "ucpro",
            }
        )
        async with http_session.get(
            f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail?{params}",
            headers={
                "accept": "application/json, text/plain, */*",
                "origin": "https://pan.quark.cn",
                "referer": "https://pan.quark.cn/",
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            payload, _ = await self.read_json_body(response)
            return response.status, payload

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        resource_id, password = _extract_resource_id(target.resolved_url)
        if not resource_id:
            return self.format_error_result(target, error="Unable to extract Quark resource id")

        started_at = time.perf_counter()
        try:
            status_code, payload = await self._request_token(
                http_session,
                resource_id=resource_id,
                password=password,
            )
            response_time = time.perf_counter() - started_at
            message = str(payload.get("message") or "")
            if status_code == 429:
                return self.rate_limited_result(
                    target,
                    error=message or "HTTP 429",
                    response_time=response_time,
                    status_code=status_code,
                )
            if status_code != 200:
                return self.uncertain_result(
                    target,
                    reason="状态码错误",
                    error=f"HTTP {status_code}",
                    response_time=response_time,
                    status_code=status_code,
                )

            token_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            stoken = str(token_data.get("stoken") or "")
            token_success = _is_success_flag(payload.get("code")) and _is_success_flag(payload.get("status"))
            if not stoken:
                if _looks_like_requires_code(message) and not password:
                    return self.requires_code_result(
                        target,
                        error=message or "Missing passcode",
                        response_time=response_time,
                        status_code=status_code,
                    )
                if token_success and message.lower() == "ok":
                    return self.uncertain_result(
                        target,
                        error="Quark token success response missing stoken",
                        response_time=response_time,
                        status_code=status_code,
                    )
                return self.invalid_result(
                    target,
                    error=message or "Quark token api rejected the link",
                    response_time=response_time,
                    status_code=status_code,
                )

            detail_status, detail_payload = await self._request_detail(
                http_session,
                resource_id=resource_id,
                stoken=stoken,
            )
            response_time = time.perf_counter() - started_at
            detail_message = str(detail_payload.get("message") or "")
            if detail_status == 429:
                return self.rate_limited_result(
                    target,
                    error=detail_message or "HTTP 429",
                    response_time=response_time,
                    status_code=detail_status,
                )
            if detail_status != 200:
                return self.uncertain_result(
                    target,
                    reason="状态码错误",
                    error=f"HTTP {detail_status}",
                    response_time=response_time,
                    status_code=detail_status,
                )

            detail_data = detail_payload.get("data") if isinstance(detail_payload.get("data"), dict) else {}
            file_list = detail_data.get("list")
            detail_success = _is_success_flag(detail_payload.get("code")) and _is_success_flag(detail_payload.get("status"))
            if detail_success and (file_list is not None or detail_message.lower() == "ok"):
                return self.valid_result(
                    target,
                    response_time=response_time,
                    status_code=detail_status,
                )
            if _looks_like_requires_code(detail_message) and not password:
                return self.requires_code_result(
                    target,
                    error=detail_message or "Missing passcode",
                    response_time=response_time,
                    status_code=detail_status,
                )
            return self.invalid_result(
                target,
                error=detail_message or "Quark detail api rejected the link",
                response_time=response_time,
                status_code=detail_status,
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
