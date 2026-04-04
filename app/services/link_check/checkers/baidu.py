from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, quote, urlparse

import aiohttp

from ..constants import PLATFORM_BAIDU
from ..result import REASON_NETWORK, REASON_TIMEOUT, LinkTarget
from .base import BaseChecker


def _extract_share_id(url: str) -> tuple[str, bool]:
    parsed = urlparse(url)
    path = parsed.path or ""
    if path.startswith("/s/"):
        return path.split("/s/", 1)[1].split("/", 1)[0], True
    if path.startswith("/share/init"):
        return parse_qs(parsed.query).get("surl", [""])[0], False
    return "", False


def _map_errno_message(errno: int, message: str) -> str:
    if message:
        return message
    if errno == -12:
        return "缺少提取码"
    if errno == -9:
        return "提取码错误"
    if errno == -62:
        return "请求受限"
    if errno == -8:
        return "分享已过期"
    if errno == -1:
        return "errno=-1"
    return f"errno={errno}"


def _looks_like_requires_code(message: str) -> bool:
    return "提取码" in (message or "")


class BaiduChecker(BaseChecker):
    checker_name = "baidu_api"

    def __init__(self, *, timeout: float = 15.0):
        super().__init__(PLATFORM_BAIDU, timeout=timeout)

    async def _verify_password(
        self,
        http_session: aiohttp.ClientSession,
        *,
        share_url: str,
        short_url: str,
        password: str,
    ) -> tuple[int, str, str]:
        await self.apply_rate_limit()
        api_url = (
            f"https://pan.baidu.com/share/verify?surl={quote(short_url)}&pwd={quote(password)}"
        )
        async with http_session.post(
            api_url,
            data={"pwd": password, "vcode": "", "vcode_str": ""},
            headers={
                "Referer": share_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            payload, _ = await self.read_json_body(response)
            errno = int(payload.get("errno", -1) or -1)
            message = str(payload.get("errmsg") or payload.get("err_msg") or "")
            cookie = str(payload.get("randsk") or "")
            return errno, message, cookie

    async def _share_list(
        self,
        http_session: aiohttp.ClientSession,
        *,
        short_url: str,
        referer_url: str,
        cookie: str = "",
    ) -> tuple[int, int, str]:
        await self.apply_rate_limit()
        api_url = (
            "https://pan.baidu.com/share/list?"
            "web=1&app_id=250528&desc=1&showempty=0&page=1&num=20&order=time"
            f"&shorturl={quote(short_url)}&root=1&view_mode=1&channel=chunlei&clienttype=0"
        )
        headers = {"Referer": referer_url, "Accept": "application/json, text/plain, */*"}
        cookies = {"BDCLND": cookie} if cookie else None
        async with http_session.get(
            api_url,
            headers=headers,
            cookies=cookies,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            payload, _ = await self.read_json_body(response)
            errno = int(float(payload.get("errno", -1) or -1))
            message = str(payload.get("errmsg") or payload.get("err_msg") or "")
            return response.status, errno, message

    async def check(self, target: LinkTarget, http_session: aiohttp.ClientSession):
        share_id, requires_prefix_strip = _extract_share_id(target.resolved_url)
        if not share_id:
            return self.format_error_result(target, error="Unable to extract Baidu share id")

        started_at = time.perf_counter()
        parsed = urlparse(target.resolved_url)
        password = parse_qs(parsed.query).get("pwd", [""])[0]
        short_url = share_id
        if requires_prefix_strip and share_id.startswith("1") and len(share_id) > 1:
            short_url = share_id[1:]

        try:
            cookie = ""
            verify_errno: int | None = None
            verify_message = ""
            if password:
                verify_errno, verify_message, cookie = await self._verify_password(
                    http_session,
                    share_url=target.resolved_url,
                    short_url=short_url,
                    password=password,
                )
                response_time = time.perf_counter() - started_at
                if verify_errno == -9:
                    return self.invalid_result(
                        target,
                        error=_map_errno_message(verify_errno, verify_message),
                        response_time=response_time,
                    )
                if verify_errno == -12:
                    return self.requires_code_result(
                        target,
                        error=_map_errno_message(verify_errno, verify_message),
                        response_time=response_time,
                    )
                if verify_errno == -62:
                    return self.rate_limited_result(
                        target,
                        error=_map_errno_message(verify_errno, verify_message),
                        response_time=response_time,
                    )
                if verify_errno not in {0, -1}:
                    if verify_message:
                        return self.invalid_result(
                            target,
                            error=_map_errno_message(verify_errno, verify_message),
                            response_time=response_time,
                        )
                    return self.uncertain_result(
                        target,
                        error=_map_errno_message(verify_errno, verify_message),
                        response_time=response_time,
                    )
                if verify_errno == -1:
                    cookie = ""

            status_code, errno, message = await self._share_list(
                http_session,
                short_url=short_url,
                referer_url=target.resolved_url,
                cookie=cookie,
            )
            response_time = time.perf_counter() - started_at
            if status_code == 429 or errno == -62:
                return self.rate_limited_result(
                    target,
                    error=_map_errno_message(errno, message),
                    response_time=response_time,
                    status_code=status_code,
                )
            if errno == 0:
                return self.valid_result(
                    target,
                    response_time=response_time,
                    status_code=status_code,
                )
            if errno == -1:
                return self.uncertain_result(
                    target,
                    error=_map_errno_message(errno, message),
                    response_time=response_time,
                    status_code=status_code,
                    meta={
                        "verify_errno": verify_errno,
                        "verify_message": verify_message,
                    },
                )
            if errno == -12 or (_looks_like_requires_code(message) and not password):
                if password and verify_errno == -1:
                    return self.uncertain_result(
                        target,
                        error=_map_errno_message(errno, message),
                        response_time=response_time,
                        status_code=status_code,
                        meta={
                            "verify_errno": verify_errno,
                            "verify_message": verify_message,
                        },
                    )
                return self.requires_code_result(
                    target,
                    error=_map_errno_message(errno, message),
                    response_time=response_time,
                    status_code=status_code,
                )
            if errno == -8 or errno == -9 or message:
                return self.invalid_result(
                    target,
                    error=_map_errno_message(errno, message),
                    response_time=response_time,
                    status_code=status_code,
                )
            return self.uncertain_result(
                target,
                error=_map_errno_message(errno, message),
                response_time=response_time,
                status_code=status_code,
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
