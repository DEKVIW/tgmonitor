from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from app.services.link_check.constants import PLATFORM_BAIDU

from .base import (
    PanTransferAccountValidationResult,
    PanTransferExecutionResult,
    PanTransferProvider,
    PanTransferProviderError,
)


_DEFAULT_HEADERS = {
    "Host": "pan.baidu.com",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Referer": "https://pan.baidu.com",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
}

_SHARE_ID_REGEX = re.compile(r'"shareid":(\d+?),"')
_USER_ID_REGEX = re.compile(r'"share_uk":"(\d+?)","')
_FS_ID_REGEX = re.compile(r'"fs_id":(\d+?),"')


def _normalize_cookie(cookie_value: str) -> str:
    normalized = str(cookie_value or "").strip()
    if "BAIDUID=" not in normalized:
        raise PanTransferProviderError("Baidu cookie is missing BAIDUID", retryable=False)
    return normalized


def _update_cookie_value(cookie_value: str, *, key: str, value: str) -> str:
    cookie_map: dict[str, str] = {}
    for chunk in str(cookie_value or "").split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        cookie_key, cookie_val = part.split("=", 1)
        cookie_map[cookie_key.strip()] = cookie_val.strip()
    cookie_map[key] = value
    return "; ".join(f"{cookie_key}={cookie_val}" for cookie_key, cookie_val in cookie_map.items())


def _extract_share_key(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    parts = [part for part in (parsed.path or "").split("/") if part]
    if parsed.path.startswith("/s/") and len(parts) >= 2:
        return parts[1]
    if parsed.path.startswith("/share/init"):
        return (parse_qs(parsed.query).get("surl") or [""])[0]
    raise PanTransferProviderError("Unable to parse Baidu share key from URL", retryable=False)


def _map_share_expire_days(days: int | None) -> int:
    if days is None or int(days) <= 0:
        return 0
    if int(days) <= 1:
        return 1
    if int(days) <= 7:
        return 7
    if int(days) <= 30:
        return 30
    return 0


def _parse_transfer_payload(response_text: str) -> tuple[str, str, list[str]]:
    share_ids = _SHARE_ID_REGEX.findall(response_text or "")
    user_ids = _USER_ID_REGEX.findall(response_text or "")
    fs_ids = _FS_ID_REGEX.findall(response_text or "")
    if not share_ids or not user_ids or not fs_ids:
        raise PanTransferProviderError("Unable to parse transfer parameters from Baidu share page", retryable=False)
    return share_ids[0], user_ids[0], fs_ids


class _BaiduClient:
    def __init__(self, cookie_value: str) -> None:
        self.cookie_value = _normalize_cookie(cookie_value)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "_BaiduClient":
        timeout = aiohttp.ClientTimeout(total=60)
        headers = dict(_DEFAULT_HEADERS)
        headers["Cookie"] = self.cookie_value
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if self.session is not None:
            await self.session.close()
            self.session = None

    @property
    def _session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise RuntimeError("Baidu client session is not initialized")
        return self.session

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        allow_redirects: bool = False,
    ) -> dict[str, Any]:
        async with self._session.request(
            method,
            url,
            params=params,
            data=data,
            allow_redirects=allow_redirects,
        ) as response:
            body = await response.text()
            if response.status >= 400:
                raise PanTransferProviderError(f"Baidu request failed with HTTP {response.status}")
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise PanTransferProviderError("Baidu returned a non-JSON response") from exc

    async def get_bdstoken(self) -> tuple[str, dict[str, Any]]:
        payload = await self._request_json(
            "GET",
            "https://pan.baidu.com/api/gettemplatevariable",
            params={
                "clienttype": "0",
                "app_id": "38824127",
                "web": "1",
                "fields": '["bdstoken","token","uk","isdocuser","servertime"]',
            },
        )
        if int(payload.get("errno") or 0) != 0:
            raise PanTransferProviderError(
                f"Baidu credential validation failed: errno {payload.get('errno')}",
                retryable=False,
                payload=payload,
            )
        result = dict(payload.get("result") or {})
        token = str(result.get("bdstoken") or "").strip()
        if not token:
            raise PanTransferProviderError("Baidu validation did not return bdstoken", retryable=False)
        return token, result

    async def verify_pass_code(self, *, share_key: str, passcode: str, bdstoken: str) -> str:
        payload = await self._request_json(
            "POST",
            "https://pan.baidu.com/share/verify",
            params={
                "surl": share_key,
                "bdstoken": bdstoken,
                "t": str(int(round(time.time() * 1000))),
                "channel": "chunlei",
                "web": "1",
                "clienttype": "0",
            },
            data={
                "pwd": passcode,
                "vcode": "",
                "vcode_str": "",
            },
        )
        if int(payload.get("errno") or 0) != 0:
            raise PanTransferProviderError(
                f"Baidu share passcode validation failed: errno {payload.get('errno')}",
                retryable=False,
                payload=payload,
            )
        randsk = str(payload.get("randsk") or "").strip()
        if not randsk:
            raise PanTransferProviderError("Baidu share passcode validation did not return BDCLND", retryable=False)
        self.cookie_value = _update_cookie_value(self.cookie_value, key="BDCLND", value=randsk)
        self._session.headers["Cookie"] = self.cookie_value
        return randsk

    async def get_transfer_page(self, *, url: str) -> str:
        async with self._session.get(url, allow_redirects=True) as response:
            body = await response.text()
            if response.status >= 400:
                raise PanTransferProviderError(f"Baidu share page request failed with HTTP {response.status}")
            return body

    async def list_dir(self, path: str, *, bdstoken: str) -> list[dict[str, Any]] | int:
        payload = await self._request_json(
            "GET",
            "https://pan.baidu.com/api/list",
            params={
                "order": "time",
                "desc": "1",
                "showempty": "0",
                "web": "1",
                "page": "1",
                "num": "1000",
                "dir": path,
                "bdstoken": bdstoken,
            },
        )
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            return errno
        rows = payload.get("list")
        if isinstance(rows, list):
            return [dict(row or {}) for row in rows]
        return []

    async def create_dir(self, path: str, *, bdstoken: str) -> int:
        payload = await self._request_json(
            "POST",
            "https://pan.baidu.com/api/create",
            params={
                "a": "commit",
                "bdstoken": bdstoken,
            },
            data={
                "path": path,
                "isdir": "1",
                "block_list": "[]",
            },
        )
        return int(payload.get("errno") or 0)

    async def transfer_file(
        self,
        *,
        share_id: str,
        share_user_id: str,
        fs_ids: list[str],
        target_path: str,
        bdstoken: str,
    ) -> dict[str, Any]:
        payload = await self._request_json(
            "POST",
            "https://pan.baidu.com/share/transfer",
            params={
                "shareid": share_id,
                "from": share_user_id,
                "bdstoken": bdstoken,
                "channel": "chunlei",
                "web": "1",
                "clienttype": "0",
            },
            data={
                "fsidlist": f"[{','.join(fs_ids)}]",
                "path": target_path,
            },
        )
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            raise PanTransferProviderError(
                f"Baidu transfer failed: errno {errno}",
                payload=payload,
            )
        return payload

    async def create_share(
        self,
        *,
        fs_id: str,
        bdstoken: str,
        expire_days: int | None,
        passcode: str | None,
    ) -> str:
        payload = await self._request_json(
            "POST",
            "https://pan.baidu.com/share/set",
            params={
                "channel": "chunlei",
                "bdstoken": bdstoken,
                "clienttype": "0",
                "app_id": "250528",
                "web": "1",
            },
            data={
                "period": str(_map_share_expire_days(expire_days)),
                "pwd": passcode or "",
                "eflag_disable": "true",
                "channel_list": "[]",
                "schannel": "4",
                "fid_list": f"[{fs_id}]",
            },
        )
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            raise PanTransferProviderError(
                f"Baidu share creation failed: errno {errno}",
                payload=payload,
            )
        link = str(payload.get("link") or "").strip()
        if not link:
            raise PanTransferProviderError("Baidu share creation did not return link")
        return f"{link}?pwd={passcode}" if passcode else link


class BaiduPanTransferProvider(PanTransferProvider):
    platform = PLATFORM_BAIDU

    async def validate_account(self, *, credential_value: str, account_name: str) -> PanTransferAccountValidationResult:
        del account_name
        async with _BaiduClient(credential_value) as client:
            _, result = await client.get_bdstoken()
        return PanTransferAccountValidationResult(
            ok=True,
            detail_message="Baidu account is available",
            remote_user=str(result.get("uk") or "").strip() or None,
            payload=result,
        )

    async def transfer_and_share(
        self,
        *,
        credential_value: str,
        account_name: str,
        original_url: str,
        original_passcode: str | None,
        staging_root: str,
        staging_folder_name: str,
        share_mode: str,
        share_passcode: str | None,
        share_expire_days: int | None,
        title_hint: str | None,
    ) -> PanTransferExecutionResult:
        del account_name, title_hint
        async with _BaiduClient(credential_value) as client:
            bdstoken, validation_payload = await client.get_bdstoken()
            share_key = _extract_share_key(original_url)
            if original_passcode:
                await client.verify_pass_code(share_key=share_key, passcode=original_passcode, bdstoken=bdstoken)

            response_text = await client.get_transfer_page(url=original_url)
            share_id, share_user_id, fs_ids = _parse_transfer_payload(response_text)
            parent_path = "/" + "/".join(part for part in str(staging_root or "").split("/") if part)
            parent_path = parent_path if parent_path != "/" else ""

            current_path = ""
            if parent_path:
                for segment in [part for part in parent_path.split("/") if part]:
                    current_path = f"{current_path}/{segment}" if current_path else f"/{segment}"
                    listing = await client.list_dir(current_path, bdstoken=bdstoken)
                    if isinstance(listing, int):
                        errno = await client.create_dir(current_path, bdstoken=bdstoken)
                        if errno not in {0, -8}:
                            raise PanTransferProviderError(f"Baidu failed to create directory {current_path}: errno {errno}")

            target_path = f"{parent_path}/{staging_folder_name}" if parent_path else f"/{staging_folder_name}"
            errno = await client.create_dir(target_path, bdstoken=bdstoken)
            if errno not in {0, -8}:
                raise PanTransferProviderError(f"Baidu failed to prepare staging directory: errno {errno}")

            await client.transfer_file(
                share_id=share_id,
                share_user_id=share_user_id,
                fs_ids=fs_ids,
                target_path=target_path,
                bdstoken=bdstoken,
            )

            list_parent_path = parent_path or "/"
            rows = await client.list_dir(list_parent_path, bdstoken=bdstoken)
            if isinstance(rows, int):
                raise PanTransferProviderError(f"Baidu failed to inspect staging directory: errno {rows}")
            folder_entry = next(
                (
                    row
                    for row in rows
                    if str(row.get("server_filename") or "") == staging_folder_name
                    and int(row.get("isdir") or 0) == 1
                ),
                None,
            )
            if folder_entry is None:
                raise PanTransferProviderError("Baidu staging directory was not found after transfer")

            final_share_passcode = share_passcode if share_mode == "private" else None
            new_share_url = await client.create_share(
                fs_id=str(folder_entry.get("fs_id") or ""),
                bdstoken=bdstoken,
                expire_days=share_expire_days,
                passcode=final_share_passcode,
            )
            return PanTransferExecutionResult(
                new_share_url=new_share_url,
                share_title=staging_folder_name,
                share_passcode=final_share_passcode,
                staging_root=parent_path or "/",
                staging_folder_name=staging_folder_name,
                staging_folder_id=str(folder_entry.get("fs_id") or "") or None,
                payload={
                    "validation": validation_payload,
                    "share_key": share_key,
                    "share_id": share_id,
                    "share_user_id": share_user_id,
                    "source_fs_id_count": len(fs_ids),
                    "transfer_target_path": target_path,
                },
            )
