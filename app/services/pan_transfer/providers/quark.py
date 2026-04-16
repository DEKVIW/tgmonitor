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
    PanTransferDeleteResult,
    PanTransferIncrementalPlanResult,
    PanTransferProvider,
    PanTransferProviderError,
    PanTransferShareResult,
    PanTransferTransferResult,
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


def _normalize_target_relative_path(value: Any) -> str | None:
    parts = [part for part in str(value or "").replace("\\", "/").split("/") if part.strip()]
    if not parts:
        return None
    return "/".join(parts)


def _join_target_relative_path(base_path: str | None, child_name: str) -> str:
    parts = [part for part in [base_path, str(child_name or "").strip()] if part]
    return "/".join(parts)


def _normalize_selection_group(raw_value: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = dict(raw_value or {})
    selected_entries = raw.get("selected_entries")
    if not isinstance(selected_entries, list) or not selected_entries:
        return None
    normalized_entries: list[dict[str, Any]] = []
    for row in selected_entries:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        normalized_entries.append(
            {
                "name": name,
                "is_dir": bool(row.get("is_dir")),
                "entry_id": str(row.get("entry_id") or "").strip() or None,
                "path": str(row.get("path") or "").strip() or None,
            }
        )
    if not normalized_entries:
        return None
    return {
        "parent_entry_id": str(raw.get("parent_entry_id") or "").strip() or None,
        "parent_path": str(raw.get("parent_path") or "").strip() or None,
        "parent_name": str(raw.get("parent_name") or "").strip() or None,
        "target_relative_path": _normalize_target_relative_path(raw.get("target_relative_path")),
        "selected_entries": normalized_entries,
        "selected_count": len(normalized_entries),
    }


def _normalize_source_selection(raw_value: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = dict(raw_value or {})
    normalized_groups: list[dict[str, Any]] = []
    raw_groups = raw.get("selection_groups")
    if isinstance(raw_groups, list):
        for row in raw_groups:
            if not isinstance(row, dict):
                continue
            normalized_group = _normalize_selection_group(row)
            if normalized_group is None:
                continue
            normalized_groups.append(normalized_group)
    if not normalized_groups:
        fallback_group = _normalize_selection_group(raw)
        if fallback_group is not None:
            normalized_groups.append(fallback_group)
    if not normalized_groups:
        return None
    return {
        "selection_groups": normalized_groups,
        "selected_count": sum(int(group.get("selected_count") or 0) for group in normalized_groups),
    }


def _match_quark_row(rows: list[dict[str, Any]], *, name: str, is_dir: bool) -> dict[str, Any] | None:
    return next(
        (
            dict(row or {})
            for row in rows
            if str(row.get("file_name") or "").strip() == name and bool(row.get("dir")) == is_dir
        ),
        None,
    )


def _select_quark_share_items(
    rows: list[dict[str, Any]],
    *,
    selection_group: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    selection = _normalize_selection_group(selection_group)
    if selection is None:
        return [dict(row or {}) for row in rows if str(row.get("fid") or "").strip()]

    selected_rows: list[dict[str, Any]] = []
    missing_entries: list[str] = []
    available_rows = [dict(row or {}) for row in rows if str(row.get("fid") or "").strip()]
    for entry in selection["selected_entries"]:
        entry_id = str(entry.get("entry_id") or "").strip()
        entry_name = str(entry.get("name") or "").strip()
        entry_is_dir = bool(entry.get("is_dir"))
        matched = next(
            (row for row in available_rows if entry_id and str(row.get("fid") or "").strip() == entry_id),
            None,
        )
        if matched is None:
            matched = _match_quark_row(available_rows, name=entry_name, is_dir=entry_is_dir)
        if matched is None:
            missing_entries.append(entry_name or entry_id or "unknown")
            continue
        selected_rows.append(matched)

    if missing_entries:
        raise PanTransferProviderError(
            "Selected Quark share entries were not found in the current directory",
            retryable=False,
            payload={
                "missing_entries": missing_entries,
                "available_entries": [str(row.get("file_name") or "") for row in available_rows[:50]],
            },
        )

    return selected_rows


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

    async def list_dir(self, *, parent_id: str, page: int = 1, page_size: int = 200) -> list[dict[str, Any]]:
        payload = await self._request_json(
            "GET",
            "https://drive-pc.quark.cn/1/clouddrive/file/sort",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "pdir_fid": parent_id,
                "_page": str(max(1, int(page))),
                "_size": str(max(1, min(int(page_size or 200), 200))),
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

    async def list_dir_all(self, *, parent_id: str, page_size: int = 200) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            current_rows = await self.list_dir(parent_id=parent_id, page=page, page_size=page_size)
            if not current_rows:
                break
            rows.extend(current_rows)
            if len(current_rows) < max(1, min(int(page_size or 200), 200)):
                break
            page += 1
        return rows

    @staticmethod
    def _match_dir(rows: list[dict[str, Any]], *, folder_name: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in rows
                if str(row.get("file_name") or "") == folder_name and bool(row.get("dir"))
            ),
            None,
        )

    @staticmethod
    def _resolve_content_root(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
        candidates = [dict(row or {}) for row in rows if str(row.get("fid") or "").strip()]
        if not candidates:
            return None, "staging directory is empty"
        if len(candidates) != 1:
            return None, f"found {len(candidates)} top-level items"
        return candidates[0], None

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

    async def ensure_dir(
        self,
        *,
        parent_id: str,
        folder_name: str,
        lookup_retries: int = 8,
    ) -> dict[str, Any]:
        existing_rows = await self.list_dir_all(parent_id=parent_id)
        existing_match = self._match_dir(existing_rows, folder_name=folder_name)
        if existing_match is not None:
            return existing_match

        payload = await self.create_dir(parent_id=parent_id, folder_name=folder_name)
        data = payload.get("data") or {}
        if isinstance(data, dict):
            created_fid = str(data.get("fid") or data.get("file_id") or "").strip()
            if created_fid:
                return {
                    "fid": created_fid,
                    "file_name": str(data.get("file_name") or folder_name),
                    "dir": True,
                }

        last_rows: list[dict[str, Any]] = []
        for _ in range(max(1, int(lookup_retries or 8))):
            await asyncio.sleep(0.6)
            rows = await self.list_dir_all(parent_id=parent_id)
            last_rows = rows
            matched = self._match_dir(rows, folder_name=folder_name)
            if matched is not None:
                return matched

        raise PanTransferProviderError(
            "Quark staging directory was not found after creation",
            payload={
                "parent_id": parent_id,
                "folder_name": folder_name,
                "create_payload": payload,
                "visible_children": [str(row.get("file_name") or "") for row in last_rows[:20]],
            },
        )

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

    async def get_share_detail(self, *, pwd_id: str, stoken: str, parent_id: str = "0") -> list[dict[str, Any]]:
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
                    "pdir_fid": parent_id,
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
        source_parent_id: str = "0",
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
                "pdir_fid": source_parent_id,
                "scene": "link",
            },
        )
        task_id = str((payload.get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            raise PanTransferProviderError("Quark transfer task creation failed", payload=payload)
        return task_id

    async def delete_entries(self, *, file_ids: list[str]) -> dict[str, Any]:
        normalized_ids = [str(file_id or "").strip() for file_id in file_ids if str(file_id or "").strip()]
        if not normalized_ids:
            return {}
        payload = await self._request_json(
            "POST",
            "https://drive-pc.quark.cn/1/clouddrive/file/delete",
            params={
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
            },
            json_payload={
                "action_type": 2,
                "filelist": normalized_ids,
                "exclude_fids": [],
            },
        )
        code = int(payload.get("code") or 0)
        if code != 0:
            raise PanTransferProviderError(
                f"Quark failed to delete existing contents: code {code}",
                payload=payload,
            )
        return payload

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
            data = payload.get("data") or {}
            status = int(data.get("status") or 0)
            share_id = str(data.get("share_id") or "").strip()
            if str(payload.get("message") or "").lower() == "ok" and (status == 2 or bool(share_id)):
                return payload
            await asyncio.sleep(0.8)
        raise PanTransferProviderError("Quark task did not finish in time")

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

    async def get_share_id(self, *, task_id: str, retries: int = 10) -> str:
        last_payload: dict[str, Any] = {}
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
                },
            )
            last_payload = payload
            share_id = str((payload.get("data") or {}).get("share_id") or "").strip()
            if share_id:
                return share_id
            await asyncio.sleep(0.8)
        raise PanTransferProviderError("Quark share task did not return share_id", payload=last_payload)

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

    async def build_incremental_source_plan(
        self,
        *,
        credential_value: str,
        account_name: str,
        original_url: str,
        original_passcode: str | None,
        staging_root: str,
        staging_folder_name: str,
        staging_folder_id: str | None = None,
    ) -> PanTransferIncrementalPlanResult:
        del account_name

        async def collect_incremental_groups(
            client: _QuarkClient,
            *,
            pwd_id: str,
            stoken: str,
            share_parent_id: str,
            share_parent_path: str | None,
            target_parent_id: str,
            target_relative_path: str | None,
        ) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
            share_rows = await client.get_share_detail(pwd_id=pwd_id, stoken=stoken, parent_id=share_parent_id)
            if not share_rows:
                return [], 0, []
            target_rows = await client.list_dir_all(parent_id=target_parent_id)
            groups: list[dict[str, Any]] = []
            selected_entries: list[dict[str, Any]] = []
            conflicts: list[dict[str, Any]] = []
            selected_count = 0
            for share_row in share_rows:
                entry_id = str(share_row.get("fid") or "").strip()
                entry_name = str(share_row.get("file_name") or "").strip()
                if not entry_id or not entry_name:
                    continue
                entry_is_dir = bool(share_row.get("dir"))
                matched_same_type = _match_quark_row(target_rows, name=entry_name, is_dir=entry_is_dir)
                matched_other_type = None if matched_same_type is not None else _match_quark_row(target_rows, name=entry_name, is_dir=not entry_is_dir)
                if matched_other_type is not None:
                    conflicts.append(
                        {
                            "name": entry_name,
                            "share_is_dir": entry_is_dir,
                            "target_is_dir": bool(matched_other_type.get("dir")),
                            "target_relative_path": target_relative_path,
                        }
                    )
                    continue
                if matched_same_type is None:
                    entry_path = _join_target_relative_path(share_parent_path, entry_name)
                    selected_entries.append(
                        {
                            "name": entry_name,
                            "is_dir": entry_is_dir,
                            "entry_id": entry_id,
                            "path": f"/{entry_path}" if entry_path else f"/{entry_name}",
                        }
                    )
                    selected_count += 1
                    continue
                if not entry_is_dir:
                    continue
                child_groups, child_count, child_conflicts = await collect_incremental_groups(
                    client,
                    pwd_id=pwd_id,
                    stoken=stoken,
                    share_parent_id=entry_id,
                    share_parent_path=f"{share_parent_path.rstrip('/')}/{entry_name}" if share_parent_path else f"/{entry_name}",
                    target_parent_id=str(matched_same_type.get("fid") or "").strip(),
                    target_relative_path=_join_target_relative_path(target_relative_path, entry_name),
                )
                groups.extend(child_groups)
                conflicts.extend(child_conflicts)
                selected_count += child_count
            if selected_entries:
                groups.insert(
                    0,
                    {
                        "parent_entry_id": None if share_parent_id == "0" else share_parent_id,
                        "parent_path": share_parent_path,
                        "parent_name": share_parent_path.split("/")[-1] if share_parent_path else None,
                        "target_relative_path": target_relative_path,
                        "selected_entries": selected_entries,
                        "selected_count": len(selected_entries),
                    },
                )
            return groups, selected_count, conflicts

        async with _QuarkClient(credential_value) as client:
            parent_id = "0"
            for segment in [part for part in str(staging_root or "").split("/") if part]:
                matched = await client.ensure_dir(parent_id=parent_id, folder_name=segment)
                parent_id = str(matched.get("fid") or "").strip()
                if not parent_id:
                    raise PanTransferProviderError("Quark staging root is missing fid", retryable=False)

            folder_id = str(staging_folder_id or "").strip()
            if not folder_id:
                staging_folder = await client.ensure_dir(parent_id=parent_id, folder_name=staging_folder_name)
                folder_id = str(staging_folder.get("fid") or "").strip()
            if not folder_id:
                raise PanTransferProviderError("Quark staging directory is missing fid", retryable=False)

            pwd_id = _extract_pwd_id(original_url)
            passcode = _extract_passcode(original_url, fallback=original_passcode)
            stoken = await client.get_stoken(pwd_id=pwd_id, passcode=passcode)
            selection_groups, selected_count, conflicts = await collect_incremental_groups(
                client,
                pwd_id=pwd_id,
                stoken=stoken,
                share_parent_id="0",
                share_parent_path=None,
                target_parent_id=folder_id,
                target_relative_path=None,
            )
            return PanTransferIncrementalPlanResult(
                selection_groups=selection_groups,
                selected_count=selected_count,
                payload={
                    "pwd_id": pwd_id,
                    "selection_group_count": len(selection_groups),
                    "selected_count": selected_count,
                    "conflict_count": len(conflicts),
                    "conflicts": conflicts[:20],
                },
            )

    async def transfer_to_staging(
        self,
        *,
        credential_value: str,
        account_name: str,
        original_url: str,
        original_passcode: str | None,
        staging_root: str,
        staging_folder_name: str,
        title_hint: str | None,
        source_selection: dict[str, Any] | None = None,
        clear_existing_contents: bool = False,
    ) -> PanTransferTransferResult:
        del account_name
        async with _QuarkClient(credential_value) as client:
            validation_payload = await client.get_user_info()
            parent_id = "0"
            parent_path = "/"
            for segment in [part for part in str(staging_root or "").split("/") if part]:
                matched = await client.ensure_dir(parent_id=parent_id, folder_name=segment)
                parent_id = str(matched.get("fid") or "")
                parent_path = f"{parent_path.rstrip('/')}/{segment}"

            staging_folder = await client.ensure_dir(parent_id=parent_id, folder_name=staging_folder_name)
            staging_folder_id = str(staging_folder.get("fid") or "").strip()
            if not staging_folder_id:
                raise PanTransferProviderError("Quark staging directory is missing fid", retryable=False)

            pwd_id = _extract_pwd_id(original_url)
            passcode = _extract_passcode(original_url, fallback=original_passcode)
            stoken = await client.get_stoken(pwd_id=pwd_id, passcode=passcode)
            normalized_selection = _normalize_source_selection(source_selection)
            if clear_existing_contents:
                existing_rows = await client.list_dir_all(parent_id=staging_folder_id)
                existing_ids = [str(row.get("fid") or "").strip() for row in existing_rows if str(row.get("fid") or "").strip()]
                if existing_ids:
                    await client.delete_entries(file_ids=existing_ids)
                    for _ in range(12):
                        await asyncio.sleep(0.8)
                        remaining_rows = await client.list_dir_all(parent_id=staging_folder_id)
                        remaining_ids = {
                            str(row.get("fid") or "").strip()
                            for row in remaining_rows
                            if str(row.get("fid") or "").strip()
                        }
                        if not remaining_ids.intersection(existing_ids):
                            break
                    else:
                        raise PanTransferProviderError(
                            "Quark existing staging contents were not cleared in time",
                            payload={
                                "staging_folder_id": staging_folder_id,
                                "staging_folder_name": staging_folder_name,
                                "remaining_entry_count": len(existing_ids),
                            },
                        )

            selection_groups = list((normalized_selection or {}).get("selection_groups") or [])
            if not selection_groups:
                selection_groups = [
                    {
                        "parent_entry_id": None,
                        "parent_path": None,
                        "parent_name": None,
                        "target_relative_path": None,
                        "selected_entries": [],
                        "selected_count": 0,
                    }
                ]

            async def ensure_target_parent_id(target_relative_path: str | None) -> str:
                parent_id = staging_folder_id
                for segment in [part for part in str(target_relative_path or "").split("/") if part]:
                    matched = await client.ensure_dir(parent_id=parent_id, folder_name=segment)
                    parent_id = str(matched.get("fid") or "").strip()
                    if not parent_id:
                        raise PanTransferProviderError("Quark target directory is missing fid", retryable=False)
                return parent_id

            total_selected_count = 0
            save_task_ids: list[str] = []
            applied_groups: list[dict[str, Any]] = []
            for selection_group in selection_groups:
                selection_parent_id = str(selection_group.get("parent_entry_id") or "").strip() or "0"
                share_items = await client.get_share_detail(pwd_id=pwd_id, stoken=stoken, parent_id=selection_parent_id)
                if not share_items:
                    raise PanTransferProviderError("Quark share has no transferable content", retryable=False)
                selected_share_items = _select_quark_share_items(share_items, selection_group=selection_group)
                if not selected_share_items:
                    continue
                fid_list = [str(item.get("fid") or "") for item in selected_share_items if str(item.get("fid") or "").strip()]
                fid_token_list = [
                    str(item.get("share_fid_token") or "")
                    for item in selected_share_items
                    if str(item.get("share_fid_token") or "").strip()
                ]
                if not fid_list or len(fid_list) != len(fid_token_list):
                    raise PanTransferProviderError("Quark share detail is missing required transfer identifiers", retryable=False)
                target_relative_path = _normalize_target_relative_path(selection_group.get("target_relative_path"))
                target_parent_id = await ensure_target_parent_id(target_relative_path)
                save_task_id = await client.get_share_save_task_id(
                    pwd_id=pwd_id,
                    stoken=stoken,
                    fid_list=fid_list,
                    fid_token_list=fid_token_list,
                    target_parent_id=target_parent_id,
                    source_parent_id=selection_parent_id,
                )
                await client.wait_task(task_id=save_task_id)
                total_selected_count += len(fid_list)
                save_task_ids.append(save_task_id)
                applied_groups.append(
                    {
                        "parent_entry_id": None if selection_parent_id == "0" else selection_parent_id,
                        "parent_path": selection_group.get("parent_path"),
                        "target_relative_path": target_relative_path,
                        "selected_count": len(fid_list),
                    }
                )
            if total_selected_count <= 0:
                raise PanTransferProviderError("Quark share has no transferable content", retryable=False)
            return PanTransferTransferResult(
                staging_root=parent_path,
                staging_folder_name=staging_folder_name,
                staging_folder_id=staging_folder_id or None,
                payload={
                    "validation": validation_payload,
                    "pwd_id": pwd_id,
                    "saved_item_count": total_selected_count,
                    "save_task_id": save_task_ids[-1] if save_task_ids else None,
                    "save_task_ids": save_task_ids,
                    "title_hint": str(title_hint or staging_folder_name),
                    "selection_applied": normalized_selection is not None,
                    "selection_parent_id": applied_groups[0].get("parent_entry_id") if len(applied_groups) == 1 else None,
                    "selection_group_count": len(applied_groups),
                    "selection_groups": applied_groups,
                    "selected_entry_count": total_selected_count,
                    "clear_existing_contents": bool(clear_existing_contents),
                },
            )

    async def share_staging_target(
        self,
        *,
        credential_value: str,
        account_name: str,
        staging_root: str,
        staging_folder_name: str,
        staging_folder_id: str | None,
        share_target_mode: str,
        share_mode: str,
        share_passcode: str | None,
        share_expire_days: int | None,
        title_hint: str | None,
    ) -> PanTransferShareResult:
        del account_name
        async with _QuarkClient(credential_value) as client:
            validation_payload = await client.get_user_info()
            folder_id = str(staging_folder_id or "").strip()
            if not folder_id:
                parent_id = "0"
                for segment in [part for part in str(staging_root or "").split("/") if part]:
                    rows = await client.list_dir_all(parent_id=parent_id)
                    matched = client._match_dir(rows, folder_name=segment)
                    if matched is None:
                        raise PanTransferProviderError(f"Quark staging path segment not found: {segment}", retryable=False)
                    parent_id = str(matched.get("fid") or "")
                rows = await client.list_dir_all(parent_id=parent_id)
                folder = client._match_dir(rows, folder_name=staging_folder_name)
                if folder is None:
                    raise PanTransferProviderError("Quark staging directory is missing", retryable=False)
                folder_id = str(folder.get("fid") or "").strip()
            if not folder_id:
                raise PanTransferProviderError("Quark staging directory is missing fid", retryable=False)

            resolved_share_target_mode = "resource_dir"
            share_target_id = folder_id
            share_target_name = str(title_hint or staging_folder_name)
            share_target_fallback_reason = None
            if str(share_target_mode or "").strip().lower() == "content_root":
                rows = await client.list_dir_all(parent_id=folder_id)
                content_root, fallback_reason = client._resolve_content_root(rows)
                if content_root is not None:
                    share_target_id = str(content_root.get("fid") or "").strip() or folder_id
                    share_target_name = str(content_root.get("file_name") or staging_folder_name).strip() or staging_folder_name
                    resolved_share_target_mode = "content_root"
                else:
                    share_target_fallback_reason = fallback_reason or "unique content root was not found"

            share_task_id = await client.create_share_task(
                fid=share_target_id,
                title=share_target_name,
                share_mode=share_mode,
                share_passcode=share_passcode,
                share_expire_days=share_expire_days,
            )
            task_payload = await client.wait_task(task_id=share_task_id, retries=60)
            share_id = str((task_payload.get("data") or {}).get("share_id") or "").strip()
            if not share_id:
                share_id = await client.get_share_id(task_id=share_task_id, retries=12)
            new_share_url, resolved_passcode = await client.publish_share(share_id=share_id)
            return PanTransferShareResult(
                new_share_url=new_share_url,
                share_title=share_target_name,
                share_passcode=resolved_passcode if share_mode == "private" else None,
                staging_root=staging_root,
                staging_folder_name=staging_folder_name,
                staging_folder_id=folder_id,
                payload={
                    "validation": validation_payload,
                    "share_task_id": share_task_id,
                    "share_id": share_id,
                    "task_payload": task_payload,
                    "share_target_mode_requested": share_target_mode,
                    "share_target_mode_resolved": resolved_share_target_mode,
                    "share_target_id": share_target_id,
                    "share_target_name": share_target_name,
                    "share_target_fallback_reason": share_target_fallback_reason,
                },
            )

    async def delete_staging_target(
        self,
        *,
        credential_value: str,
        account_name: str,
        staging_root: str,
        staging_folder_name: str,
        staging_folder_id: str | None,
    ) -> PanTransferDeleteResult:
        del account_name
        async with _QuarkClient(credential_value) as client:
            validation_payload = await client.get_user_info()
            parent_id = "0"
            parent_path = "/"
            for segment in [part for part in str(staging_root or "").split("/") if part]:
                rows = await client.list_dir_all(parent_id=parent_id)
                matched = client._match_dir(rows, folder_name=segment)
                if matched is None:
                    return PanTransferDeleteResult(
                        deleted=False,
                        already_missing=True,
                        staging_root=parent_path,
                        staging_folder_name=staging_folder_name,
                        staging_folder_id=None,
                        payload={
                            "validation": validation_payload,
                            "missing_segment": segment,
                        },
                    )
                parent_id = str(matched.get("fid") or "").strip()
                parent_path = f"{parent_path.rstrip('/')}/{segment}"

            folder_id = str(staging_folder_id or "").strip()
            folder = None
            rows = await client.list_dir_all(parent_id=parent_id)
            if folder_id:
                folder = next(
                    (row for row in rows if str(row.get("fid") or "").strip() == folder_id),
                    None,
                )
            if folder is None:
                folder = client._match_dir(rows, folder_name=staging_folder_name)
            if folder is None:
                return PanTransferDeleteResult(
                    deleted=False,
                    already_missing=True,
                    staging_root=parent_path,
                    staging_folder_name=staging_folder_name,
                    staging_folder_id=folder_id or None,
                    payload={
                        "validation": validation_payload,
                        "missing_folder_name": staging_folder_name,
                    },
                )

            folder_id = str(folder.get("fid") or "").strip()
            await client.delete_entries(file_ids=[folder_id])
            for _ in range(12):
                await asyncio.sleep(0.8)
                rows = await client.list_dir_all(parent_id=parent_id)
                still_exists = any(str(row.get("fid") or "").strip() == folder_id for row in rows)
                if not still_exists:
                    return PanTransferDeleteResult(
                        deleted=True,
                        already_missing=False,
                        staging_root=parent_path,
                        staging_folder_name=staging_folder_name,
                        staging_folder_id=folder_id or None,
                        payload={
                            "validation": validation_payload,
                        },
                    )

            raise PanTransferProviderError(
                "Quark staging directory was not deleted in time",
                payload={
                    "staging_root": parent_path,
                    "staging_folder_name": staging_folder_name,
                    "staging_folder_id": folder_id,
                },
            )
