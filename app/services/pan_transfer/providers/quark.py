from __future__ import annotations

import asyncio
import json
import random
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from app.services.link_check.constants import PLATFORM_QUARK

from .base import (
    PanTransferAccountValidationResult,
    PanTransferExecutionResult,
    PanTransferProvider,
    PanTransferProviderError,
)


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "origin": "https://pan.quark.cn",
    "referer": "https://pan.quark.cn/",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _normalize_cookie(cookie_value: str) -> str:
    normalized = str(cookie_value or "").strip()
    if not normalized:
        raise PanTransferProviderError("Quark cookie cannot be empty", retryable=False)
    return normalized


def _extract_pwd_id(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    parts = [part for part in (parsed.path or "").split("/") if part]
    if len(parts) >= 2 and parts[0] == "s":
        return parts[1]
    raise PanTransferProviderError("Unable to parse Quark share id from URL", retryable=False)


def _extract_passcode(url: str, fallback: str | None = None) -> str | None:
    parsed = urlparse(str(url or "").strip())
    query = parse_qs(parsed.query)
    return str((query.get("pwd") or [fallback or ""])[0]).strip() or None


def _map_share_expire_days(days: int | None) -> int:
    if days is None or int(days) <= 0:
        return 1
    if int(days) <= 1:
        return 2
    if int(days) <= 7:
        return 3
    return 4


class _QuarkClient:
    def __init__(self, cookie_value: str) -> None:
        self.cookie_value = _normalize_cookie(cookie_value)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "_QuarkClient":
        timeout = aiohttp.ClientTimeout(total=60)
        headers = dict(_DEFAULT_HEADERS)
        headers["cookie"] = self.cookie_value
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if self.session is not None:
            await self.session.close()
            self.session = None

    @property
    def _session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise RuntimeError("Quark client session is not initialized")
        return self.session

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._session.request(
            method,
            url,
            params=params,
            json=json_payload,
        ) as response:
            body = await response.text()
            if response.status >= 400:
                raise PanTransferProviderError(f"Quark request failed with HTTP {response.status}")
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise PanTransferProviderError("Quark returned a non-JSON response") from exc

    async def get_user_info(self) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            "https://pan.quark.cn/account/info",
            params={
                "fr": "pc",
                "platform": "pc",
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not data:
            raise PanTransferProviderError("Quark credential validation failed", retryable=False, payload=payload)
        return data

    async def list_dir(self, *, parent_id: str) -> list[dict[str, Any]]:
        payload = await self._request_json(
            "GET",
            "https://drive-pc.quark.cn/1/clouddrive/file/sort",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "pdir_fid": parent_id,
                "_page": "1",
                "_size": "200",
                "_fetch_total": "false",
                "_fetch_sub_dirs": "1",
                "_sort": "file_type:asc,file_name:asc",
                "__dt": str(random.randint(100, 9999)),
                "__t": str(int(random.random() * 10000000000000)),
            },
        )
        data = payload.get("data") or {}
        rows = data.get("list")
        if not isinstance(rows, list):
            return []
        return [dict(row or {}) for row in rows]

    async def create_dir(self, *, parent_id: str, folder_name: str) -> dict[str, Any]:
        payload = await self._request_json(
            "POST",
            "https://drive-pc.quark.cn/1/clouddrive/file",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "__dt": str(random.randint(100, 9999)),
                "__t": str(int(random.random() * 10000000000000)),
            },
            json_payload={
                "pdir_fid": parent_id,
                "file_name": folder_name,
                "dir_path": "",
                "dir_init_lock": False,
            },
        )
        code = int(payload.get("code") or 0)
        if code not in {0, 23008}:
            raise PanTransferProviderError(
                f"Quark failed to create directory: code {code}",
                payload=payload,
            )
        return payload

    async def get_stoken(self, *, pwd_id: str, passcode: str | None) -> str:
        payload = await self._request_json(
            "POST",
            "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "__dt": str(random.randint(100, 9999)),
                "__t": str(int(random.random() * 10000000000000)),
            },
            json_payload={
                "pwd_id": pwd_id,
                "passcode": passcode or "",
            },
        )
        data = payload.get("data") or {}
        token = str(data.get("stoken") or "").strip()
        if int(payload.get("status") or 0) != 200 or not token:
            raise PanTransferProviderError(
                f"Quark share access failed: {payload.get('message') or 'missing stoken'}",
                retryable=False,
                payload=payload,
            )
        return token

    async def get_share_detail(self, *, pwd_id: str, stoken: str) -> list[dict[str, Any]]:
        page = 1
        file_list: list[dict[str, Any]] = []
        while True:
            payload = await self._request_json(
                "GET",
                "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail",
                params={
                    "pr": "ucpro",
                    "fr": "pc",
                    "uc_param_str": "",
                    "pwd_id": pwd_id,
                    "stoken": stoken,
                    "pdir_fid": "0",
                    "force": "0",
                    "_page": str(page),
                    "_size": "50",
                    "_sort": "file_type:asc,updated_at:desc",
                    "__dt": str(random.randint(200, 9999)),
                    "__t": str(int(random.random() * 10000000000000)),
                },
            )
            data = payload.get("data") or {}
            rows = data.get("list") or []
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                file_list.append(dict(row or {}))

            metadata = payload.get("metadata") or {}
            total = int(metadata.get("_total") or 0)
            size = int(metadata.get("_size") or 0)
            count = int(metadata.get("_count") or 0)
            if total <= size or count < size:
                return file_list
            page += 1

    async def get_share_save_task_id(
        self,
        *,
        pwd_id: str,
        stoken: str,
        fid_list: list[str],
        fid_token_list: list[str],
        target_parent_id: str,
    ) -> str:
        payload = await self._request_json(
            "POST",
            "https://drive.quark.cn/1/clouddrive/share/sharepage/save",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "__dt": str(random.randint(600, 9999)),
                "__t": str(int(random.random() * 10000000000000)),
            },
            json_payload={
                "fid_list": fid_list,
                "fid_token_list": fid_token_list,
                "to_pdir_fid": target_parent_id,
                "pwd_id": pwd_id,
                "stoken": stoken,
                "pdir_fid": "0",
                "scene": "link",
            },
        )
        task_id = str((payload.get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            raise PanTransferProviderError("Quark transfer task creation failed", payload=payload)
        return task_id

    async def wait_task(self, *, task_id: str, retries: int = 50) -> dict[str, Any]:
        for retry_index in range(retries):
            payload = await self._request_json(
                "GET",
                "https://drive-pc.quark.cn/1/clouddrive/task",
                params={
                    "pr": "ucpro",
                    "fr": "pc",
                    "uc_param_str": "",
                    "task_id": task_id,
                    "retry_index": str(retry_index),
                    "__dt": "21192",
                    "__t": str(int(random.random() * 10000000000000)),
                },
            )
            if str(payload.get("message") or "").lower() == "ok" and int((payload.get("data") or {}).get("status") or 0) == 2:
                return payload
            await asyncio.sleep(0.8)
        raise PanTransferProviderError("Quark transfer task did not finish in time")

    async def create_share_task(
        self,
        *,
        fid: str,
        title: str,
        share_mode: str,
        share_passcode: str | None,
        share_expire_days: int | None,
    ) -> str:
        payload_data = {
            "fid_list": [fid],
            "title": title,
            "url_type": 2 if share_mode == "private" else 1,
            "expired_type": _map_share_expire_days(share_expire_days),
        }
        if share_mode == "private":
            payload_data["passcode"] = share_passcode or ""
        payload = await self._request_json(
            "POST",
            "https://drive-pc.quark.cn/1/clouddrive/share",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
            },
            json_payload=payload_data,
        )
        task_id = str((payload.get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            raise PanTransferProviderError("Quark share task creation failed", payload=payload)
        return task_id

    async def get_share_id(self, *, task_id: str) -> str:
        payload = await self._request_json(
            "GET",
            "https://drive-pc.quark.cn/1/clouddrive/task",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "task_id": task_id,
                "retry_index": "0",
            },
        )
        share_id = str((payload.get("data") or {}).get("share_id") or "").strip()
        if not share_id:
            raise PanTransferProviderError("Quark share task did not return share_id", payload=payload)
        return share_id

    async def publish_share(self, *, share_id: str) -> tuple[str, str | None]:
        payload = await self._request_json(
            "POST",
            "https://drive-pc.quark.cn/1/clouddrive/share/password",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
            },
            json_payload={
                "share_id": share_id,
            },
        )
        data = payload.get("data") or {}
        share_url = str(data.get("share_url") or "").strip()
        if not share_url:
            raise PanTransferProviderError("Quark share publish did not return URL", payload=payload)
        passcode = str(data.get("passcode") or "").strip() or None
        return (f"{share_url}?pwd={passcode}" if passcode else share_url), passcode


class QuarkPanTransferProvider(PanTransferProvider):
    platform = PLATFORM_QUARK

    async def validate_account(self, *, credential_value: str, account_name: str) -> PanTransferAccountValidationResult:
        del account_name
        async with _QuarkClient(credential_value) as client:
            user_info = await client.get_user_info()
        return PanTransferAccountValidationResult(
            ok=True,
            detail_message="Quark account is available",
            remote_user=str(user_info.get("nickname") or "").strip() or None,
            payload=user_info,
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
        del account_name
        async with _QuarkClient(credential_value) as client:
            validation_payload = await client.get_user_info()
            parent_id = "0"
            parent_path = "/"
            for segment in [part for part in str(staging_root or "").split("/") if part]:
                rows = await client.list_dir(parent_id=parent_id)
                matched = next(
                    (
                        row
                        for row in rows
                        if str(row.get("file_name") or "") == segment and bool(row.get("dir"))
                    ),
                    None,
                )
                if matched is None:
                    await client.create_dir(parent_id=parent_id, folder_name=segment)
                    rows = await client.list_dir(parent_id=parent_id)
                    matched = next(
                        (
                            row
                            for row in rows
                            if str(row.get("file_name") or "") == segment and bool(row.get("dir"))
                        ),
                        None,
                    )
                if matched is None:
                    raise PanTransferProviderError(f"Quark staging path segment not found: {segment}")
                parent_id = str(matched.get("fid") or "")
                parent_path = f"{parent_path.rstrip('/')}/{segment}"

            await client.create_dir(parent_id=parent_id, folder_name=staging_folder_name)
            staging_rows = await client.list_dir(parent_id=parent_id)
            staging_folder = next(
                (
                    row
                    for row in staging_rows
                    if str(row.get("file_name") or "") == staging_folder_name and bool(row.get("dir"))
                ),
                None,
            )
            if staging_folder is None:
                raise PanTransferProviderError("Quark staging directory was not found after creation")

            pwd_id = _extract_pwd_id(original_url)
            passcode = _extract_passcode(original_url, fallback=original_passcode)
            stoken = await client.get_stoken(pwd_id=pwd_id, passcode=passcode)
            share_items = await client.get_share_detail(pwd_id=pwd_id, stoken=stoken)
            if not share_items:
                raise PanTransferProviderError("Quark share has no transferable content", retryable=False)

            fid_list = [str(item.get("fid") or "") for item in share_items if str(item.get("fid") or "").strip()]
            fid_token_list = [
                str(item.get("share_fid_token") or "")
                for item in share_items
                if str(item.get("share_fid_token") or "").strip()
            ]
            if not fid_list or len(fid_list) != len(fid_token_list):
                raise PanTransferProviderError("Quark share detail is missing required transfer identifiers", retryable=False)

            save_task_id = await client.get_share_save_task_id(
                pwd_id=pwd_id,
                stoken=stoken,
                fid_list=fid_list,
                fid_token_list=fid_token_list,
                target_parent_id=str(staging_folder.get("fid") or ""),
            )
            await client.wait_task(task_id=save_task_id)

            share_task_id = await client.create_share_task(
                fid=str(staging_folder.get("fid") or ""),
                title=str(title_hint or staging_folder_name),
                share_mode=share_mode,
                share_passcode=share_passcode,
                share_expire_days=share_expire_days,
            )
            share_id = await client.get_share_id(task_id=share_task_id)
            new_share_url, resolved_passcode = await client.publish_share(share_id=share_id)
            return PanTransferExecutionResult(
                new_share_url=new_share_url,
                share_title=str(title_hint or staging_folder_name),
                share_passcode=resolved_passcode if share_mode == "private" else None,
                staging_root=parent_path,
                staging_folder_name=staging_folder_name,
                staging_folder_id=str(staging_folder.get("fid") or "") or None,
                payload={
                    "validation": validation_payload,
                    "pwd_id": pwd_id,
                    "saved_item_count": len(fid_list),
                    "save_task_id": save_task_id,
                    "share_task_id": share_task_id,
                    "share_id": share_id,
                },
            )
