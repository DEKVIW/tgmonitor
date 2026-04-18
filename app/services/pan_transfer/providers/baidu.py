from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from app.services.link_check.constants import PLATFORM_BAIDU

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


def _extract_share_access_context(url: str) -> tuple[str, bool, str | None]:
    parsed = urlparse(str(url or "").strip())
    path = parsed.path or ""
    passcode = str((parse_qs(parsed.query).get("pwd") or [""])[0]).strip() or None
    if path.startswith("/s/"):
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return parts[1], True, passcode
    if path.startswith("/share/init"):
        share_key = str((parse_qs(parsed.query).get("surl") or [""])[0]).strip()
        if share_key:
            return share_key, False, passcode
    raise PanTransferProviderError("Unable to parse Baidu share key from URL", retryable=False)


def _build_share_list_short_url(share_key: str, *, requires_prefix_strip: bool) -> str:
    if requires_prefix_strip and share_key.startswith("1") and len(share_key) > 1:
        return share_key[1:]
    return share_key


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
            if normalized_group is not None:
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


def _match_baidu_row(rows: list[dict[str, Any]], *, name: str, is_dir: bool) -> dict[str, Any] | None:
    return next(
        (
            dict(row or {})
            for row in rows
            if str(row.get("server_filename") or "").strip() == name
            and int(row.get("isdir") or 0) == (1 if is_dir else 0)
        ),
        None,
    )


def _select_baidu_share_items(
    rows: list[dict[str, Any]],
    *,
    selection_group: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    selection = _normalize_selection_group(selection_group)
    if selection is None:
        return [dict(row or {}) for row in rows if str(row.get("fs_id") or "").strip()]

    available_rows = [dict(row or {}) for row in rows if str(row.get("fs_id") or "").strip()]
    selected_rows: list[dict[str, Any]] = []
    missing_entries: list[str] = []
    for entry in selection["selected_entries"]:
        entry_id = str(entry.get("entry_id") or "").strip()
        entry_path = str(entry.get("path") or "").strip()
        entry_name = str(entry.get("name") or "").strip()
        entry_is_dir = bool(entry.get("is_dir"))
        matched = next(
            (row for row in available_rows if entry_id and str(row.get("fs_id") or "").strip() == entry_id),
            None,
        )
        if matched is None:
            matched = next(
                (row for row in available_rows if entry_path and str(row.get("path") or "").strip() == entry_path),
                None,
            )
        if matched is None:
            matched = _match_baidu_row(available_rows, name=entry_name, is_dir=entry_is_dir)
        if matched is None:
            missing_entries.append(entry_name or entry_path or entry_id or "unknown")
            continue
        selected_rows.append(matched)

    if missing_entries:
        raise PanTransferProviderError(
            "Selected Baidu share entries were not found in the current directory",
            retryable=False,
            payload={
                "missing_entries": missing_entries,
                "available_entries": [str(row.get("server_filename") or "") for row in available_rows[:50]],
            },
        )

    return selected_rows


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

    async def list_share_dir(
        self,
        *,
        share_key: str,
        requires_prefix_strip: bool,
        dir_path: str | None,
    ) -> list[dict[str, Any]]:
        short_url = _build_share_list_short_url(share_key, requires_prefix_strip=requires_prefix_strip)
        payload = await self._request_json(
            "GET",
            "https://pan.baidu.com/share/list",
            params={
                "web": "1",
                "app_id": "250528",
                "desc": "1",
                "showempty": "0",
                "page": "1",
                "num": "200",
                "order": "time",
                "shorturl": short_url,
                "root": "0" if dir_path else "1",
                "dir": dir_path or "",
                "view_mode": "1",
                "channel": "chunlei",
                "clienttype": "0",
            },
        )
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            raise PanTransferProviderError(
                f"Baidu share directory read failed: errno {errno}",
                retryable=False,
                payload=payload,
            )
        rows = payload.get("list")
        if isinstance(rows, list):
            return [dict(row or {}) for row in rows]
        return []

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

    async def delete_files(self, *, paths: list[str], bdstoken: str) -> dict[str, Any]:
        normalized_paths = [str(path or "").strip() for path in paths if str(path or "").strip()]
        if not normalized_paths:
            return {}
        payload = await self._request_json(
            "POST",
            "https://pan.baidu.com/api/filemanager",
            params={
                "opera": "delete",
                "async": "2",
                "onnest": "fail",
                "bdstoken": bdstoken,
                "channel": "chunlei",
                "web": "1",
                "clienttype": "0",
                "app_id": "250528",
            },
            data={
                "filelist": json.dumps(normalized_paths, ensure_ascii=False),
            },
        )
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            raise PanTransferProviderError(
                f"Baidu failed to delete existing contents: errno {errno}",
                payload=payload,
            )
        return payload

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
        preferred_target_relative_path: str | None = None,
    ) -> PanTransferIncrementalPlanResult:
        del account_name, staging_folder_id

        async def ensure_path_exists(client: _BaiduClient, *, path: str, bdstoken: str) -> None:
            current_path = ""
            for segment in [part for part in str(path or "").split("/") if part]:
                current_path = f"{current_path}/{segment}" if current_path else f"/{segment}"
                listing = await client.list_dir(current_path, bdstoken=bdstoken)
                if isinstance(listing, int):
                    errno = await client.create_dir(current_path, bdstoken=bdstoken)
                    if errno not in {0, -8}:
                        raise PanTransferProviderError(f"Baidu failed to create directory {current_path}: errno {errno}")

        async def collect_incremental_groups(
            client: _BaiduClient,
            *,
            share_key: str,
            requires_prefix_strip: bool,
            share_dir_path: str | None,
            target_dir_path: str,
            target_relative_path: str | None,
            bdstoken: str,
        ) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
            share_rows = await client.list_share_dir(
                share_key=share_key,
                requires_prefix_strip=requires_prefix_strip,
                dir_path=share_dir_path,
            )
            if not share_rows:
                return [], 0, []
            target_rows = await client.list_dir(target_dir_path, bdstoken=bdstoken)
            if isinstance(target_rows, int):
                raise PanTransferProviderError(
                    f"Baidu failed to inspect target directory {target_dir_path}: errno {target_rows}"
                )
            groups: list[dict[str, Any]] = []
            selected_entries: list[dict[str, Any]] = []
            conflicts: list[dict[str, Any]] = []
            selected_count = 0
            for share_row in share_rows:
                entry_id = str(share_row.get("fs_id") or "").strip()
                entry_name = str(share_row.get("server_filename") or "").strip()
                if not entry_id or not entry_name:
                    continue
                entry_is_dir = int(share_row.get("isdir") or 0) == 1
                matched_same_type = _match_baidu_row(target_rows, name=entry_name, is_dir=entry_is_dir)
                matched_other_type = None if matched_same_type is not None else _match_baidu_row(target_rows, name=entry_name, is_dir=not entry_is_dir)
                if matched_other_type is not None:
                    conflicts.append(
                        {
                            "name": entry_name,
                            "share_is_dir": entry_is_dir,
                            "target_is_dir": int(matched_other_type.get("isdir") or 0) == 1,
                            "target_relative_path": target_relative_path,
                        }
                    )
                    continue
                if matched_same_type is None:
                    entry_path = str(share_row.get("path") or "").strip() or (
                        f"{share_dir_path.rstrip('/')}/{entry_name}" if share_dir_path else f"/{entry_name}"
                    )
                    selected_entries.append(
                        {
                            "name": entry_name,
                            "is_dir": entry_is_dir,
                            "entry_id": entry_id,
                            "path": entry_path,
                        }
                    )
                    selected_count += 1
                    continue
                if not entry_is_dir:
                    continue
                child_share_dir_path = str(share_row.get("path") or "").strip() or (
                    f"{share_dir_path.rstrip('/')}/{entry_name}" if share_dir_path else f"/{entry_name}"
                )
                child_target_dir_path = str(matched_same_type.get("path") or "").strip() or (
                    f"{target_dir_path.rstrip('/')}/{entry_name}"
                )
                child_groups, child_count, child_conflicts = await collect_incremental_groups(
                    client,
                    share_key=share_key,
                    requires_prefix_strip=requires_prefix_strip,
                    share_dir_path=child_share_dir_path,
                    target_dir_path=child_target_dir_path,
                    target_relative_path=_join_target_relative_path(target_relative_path, entry_name),
                    bdstoken=bdstoken,
                )
                groups.extend(child_groups)
                conflicts.extend(child_conflicts)
                selected_count += child_count
            if selected_entries:
                groups.insert(
                    0,
                    {
                        "parent_entry_id": None,
                        "parent_path": share_dir_path,
                        "parent_name": share_dir_path.split("/")[-1] if share_dir_path else None,
                        "target_relative_path": target_relative_path,
                        "selected_entries": selected_entries,
                        "selected_count": len(selected_entries),
                    },
                )
            return groups, selected_count, conflicts

        async with _BaiduClient(credential_value) as client:
            bdstoken, validation_payload = await client.get_bdstoken()
            share_key = _extract_share_key(original_url)
            share_access_key, requires_prefix_strip, url_passcode = _extract_share_access_context(original_url)
            resolved_passcode = original_passcode or url_passcode
            if resolved_passcode:
                await client.verify_pass_code(share_key=share_key, passcode=resolved_passcode, bdstoken=bdstoken)

            parent_path = "/" + "/".join(part for part in str(staging_root or "").split("/") if part)
            parent_path = parent_path if parent_path != "/" else ""
            if parent_path:
                await ensure_path_exists(client, path=parent_path, bdstoken=bdstoken)
            target_path = f"{parent_path}/{staging_folder_name}" if parent_path else f"/{staging_folder_name}"
            errno = await client.create_dir(target_path, bdstoken=bdstoken)
            if errno not in {0, -8}:
                raise PanTransferProviderError(f"Baidu failed to prepare staging directory: errno {errno}")

            normalized_preferred_target_relative_path = _normalize_target_relative_path(preferred_target_relative_path)
            applied_target_relative_path: str | None = None
            target_plan_path = target_path
            if normalized_preferred_target_relative_path:
                resolved_target_path = target_path
                for segment in [part for part in normalized_preferred_target_relative_path.split("/") if part]:
                    rows = await client.list_dir(resolved_target_path, bdstoken=bdstoken)
                    if isinstance(rows, int):
                        raise PanTransferProviderError(
                            f"Baidu failed to inspect target directory {resolved_target_path}: errno {rows}"
                        )
                    matched = next(
                        (
                            row
                            for row in rows
                            if str(row.get("server_filename") or "").strip() == segment
                            and int(row.get("isdir") or 0) == 1
                        ),
                        None,
                    )
                    if matched is None:
                        resolved_target_path = ""
                        break
                    resolved_target_path = str(matched.get("path") or "").strip() or (
                        f"{resolved_target_path.rstrip('/')}/{segment}"
                    )
                if resolved_target_path:
                    target_plan_path = resolved_target_path
                    applied_target_relative_path = normalized_preferred_target_relative_path

            selection_groups, selected_count, conflicts = await collect_incremental_groups(
                client,
                share_key=share_access_key,
                requires_prefix_strip=requires_prefix_strip,
                share_dir_path=None,
                target_dir_path=target_plan_path,
                target_relative_path=applied_target_relative_path,
                bdstoken=bdstoken,
            )
            return PanTransferIncrementalPlanResult(
                selection_groups=selection_groups,
                selected_count=selected_count,
                payload={
                    "validation": validation_payload,
                    "share_key": share_key,
                    "selection_group_count": len(selection_groups),
                    "selected_count": selected_count,
                    "conflict_count": len(conflicts),
                    "conflicts": conflicts[:20],
                    "preferred_target_relative_path_requested": normalized_preferred_target_relative_path,
                    "preferred_target_relative_path_applied": applied_target_relative_path,
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
        del account_name, title_hint
        async with _BaiduClient(credential_value) as client:
            bdstoken, validation_payload = await client.get_bdstoken()
            share_key = _extract_share_key(original_url)
            share_access_key, requires_prefix_strip, url_passcode = _extract_share_access_context(original_url)
            resolved_passcode = original_passcode or url_passcode
            if resolved_passcode:
                await client.verify_pass_code(share_key=share_key, passcode=resolved_passcode, bdstoken=bdstoken)

            response_text = await client.get_transfer_page(url=original_url)
            share_id, share_user_id, _ = _parse_transfer_payload(response_text)
            normalized_selection = _normalize_source_selection(source_selection)

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

            if clear_existing_contents:
                existing_rows = await client.list_dir(target_path, bdstoken=bdstoken)
                if isinstance(existing_rows, int):
                    raise PanTransferProviderError(
                        f"Baidu failed to inspect staging contents before replacement: errno {existing_rows}"
                    )
                existing_paths = [
                    str(row.get("path") or "").strip()
                    for row in existing_rows
                    if str(row.get("path") or "").strip()
                ]
                if existing_paths:
                    await client.delete_files(paths=existing_paths, bdstoken=bdstoken)
                    for _ in range(12):
                        await asyncio.sleep(0.8)
                        remaining_rows = await client.list_dir(target_path, bdstoken=bdstoken)
                        if isinstance(remaining_rows, int):
                            raise PanTransferProviderError(
                                f"Baidu failed to verify staging cleanup: errno {remaining_rows}"
                            )
                        remaining_paths = {
                            str(row.get("path") or "").strip()
                            for row in remaining_rows
                            if str(row.get("path") or "").strip()
                        }
                        if not remaining_paths.intersection(existing_paths):
                            break
                    else:
                        raise PanTransferProviderError(
                            "Baidu existing staging contents were not cleared in time",
                            payload={
                                "target_path": target_path,
                                "remaining_entry_count": len(existing_paths),
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

            async def ensure_path_exists(path: str) -> None:
                current_path = ""
                for segment in [part for part in str(path or "").split("/") if part]:
                    current_path = f"{current_path}/{segment}" if current_path else f"/{segment}"
                    listing = await client.list_dir(current_path, bdstoken=bdstoken)
                    if isinstance(listing, int):
                        errno = await client.create_dir(current_path, bdstoken=bdstoken)
                        if errno not in {0, -8}:
                            raise PanTransferProviderError(f"Baidu failed to create directory {current_path}: errno {errno}")

            total_selected_count = 0
            applied_groups: list[dict[str, Any]] = []
            for selection_group in selection_groups:
                selection_parent_path = str(selection_group.get("parent_path") or "").strip() or None
                share_rows = await client.list_share_dir(
                    share_key=share_access_key,
                    requires_prefix_strip=requires_prefix_strip,
                    dir_path=selection_parent_path,
                )
                selected_rows = _select_baidu_share_items(share_rows, selection_group=selection_group)
                if not selected_rows:
                    continue
                group_fs_ids = [
                    str(row.get("fs_id") or "").strip()
                    for row in selected_rows
                    if str(row.get("fs_id") or "").strip()
                ]
                if not group_fs_ids:
                    continue
                target_relative_path = _normalize_target_relative_path(selection_group.get("target_relative_path"))
                group_target_path = target_path
                if target_relative_path:
                    group_target_path = f"{target_path.rstrip('/')}/{target_relative_path}"
                    await ensure_path_exists(group_target_path)
                await client.transfer_file(
                    share_id=share_id,
                    share_user_id=share_user_id,
                    fs_ids=group_fs_ids,
                    target_path=group_target_path,
                    bdstoken=bdstoken,
                )
                total_selected_count += len(group_fs_ids)
                applied_groups.append(
                    {
                        "parent_path": selection_parent_path,
                        "target_relative_path": target_relative_path,
                        "selected_count": len(group_fs_ids),
                    }
                )
            if total_selected_count <= 0:
                raise PanTransferProviderError("Baidu share has no transferable content", retryable=False)

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

            return PanTransferTransferResult(
                staging_root=parent_path or "/",
                staging_folder_name=staging_folder_name,
                staging_folder_id=str(folder_entry.get("fs_id") or "") or None,
                payload={
                    "validation": validation_payload,
                    "share_key": share_key,
                    "share_id": share_id,
                    "share_user_id": share_user_id,
                    "source_fs_id_count": total_selected_count,
                    "transfer_target_path": target_path,
                    "selection_applied": normalized_selection is not None,
                    "selection_parent_path": applied_groups[0].get("parent_path") if len(applied_groups) == 1 else None,
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
        final_share_passcode = share_passcode if share_mode == "private" else None
        async with _BaiduClient(credential_value) as client:
            bdstoken, validation_payload = await client.get_bdstoken()
            folder_id = str(staging_folder_id or "").strip()
            if not folder_id:
                parent_path = "/" + "/".join(part for part in str(staging_root or "").split("/") if part)
                parent_path = parent_path if parent_path != "/" else "/"
                rows = await client.list_dir(parent_path, bdstoken=bdstoken)
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
                    raise PanTransferProviderError("Baidu staging directory is missing", retryable=False)
                folder_id = str(folder_entry.get("fs_id") or "").strip()
            if not folder_id:
                raise PanTransferProviderError("Baidu staging directory is missing fs_id", retryable=False)

            resolved_share_target_mode = "resource_dir"
            share_target_id = folder_id
            share_target_name = str(title_hint or staging_folder_name or "").strip() or staging_folder_name
            share_target_fallback_reason = None
            if str(share_target_mode or "").strip().lower() == "content_root":
                staging_path = "/" + "/".join(part for part in str(staging_root or "").split("/") if part)
                staging_path = f"{staging_path}/{staging_folder_name}" if staging_path and staging_path != "/" else f"/{staging_folder_name}"
                child_rows = await client.list_dir(staging_path, bdstoken=bdstoken)
                if isinstance(child_rows, int):
                    share_target_fallback_reason = f"inspect content root failed: errno {child_rows}"
                elif len(child_rows) == 1:
                    child = dict(child_rows[0] or {})
                    share_target_id = str(child.get("fs_id") or "").strip() or folder_id
                    share_target_name = str(child.get("server_filename") or share_target_name).strip() or share_target_name
                    resolved_share_target_mode = "content_root"
                elif not child_rows:
                    share_target_fallback_reason = "staging directory is empty"
                else:
                    share_target_fallback_reason = f"found {len(child_rows)} top-level items"

            new_share_url = await client.create_share(
                fs_id=share_target_id,
                bdstoken=bdstoken,
                expire_days=share_expire_days,
                passcode=final_share_passcode,
            )
            return PanTransferShareResult(
                new_share_url=new_share_url,
                share_title=share_target_name,
                share_passcode=final_share_passcode,
                staging_root=staging_root,
                staging_folder_name=staging_folder_name,
                staging_folder_id=folder_id,
                payload={
                    "validation": validation_payload,
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
        del account_name, staging_folder_id
        async with _BaiduClient(credential_value) as client:
            bdstoken, validation_payload = await client.get_bdstoken()
            parent_path = "/" + "/".join(part for part in str(staging_root or "").split("/") if part)
            parent_path = parent_path if parent_path != "/" else "/"
            target_path = f"{parent_path.rstrip('/')}/{staging_folder_name}" if parent_path != "/" else f"/{staging_folder_name}"
            rows = await client.list_dir(parent_path, bdstoken=bdstoken)
            if isinstance(rows, int):
                raise PanTransferProviderError(
                    f"Baidu failed to inspect staging directory before deletion: errno {rows}"
                )
            target_exists = any(
                str(row.get("path") or "").strip() == target_path
                or (
                    str(row.get("server_filename") or "").strip() == staging_folder_name
                    and int(row.get("isdir") or 0) == 1
                )
                for row in rows
            )
            if not target_exists:
                return PanTransferDeleteResult(
                    deleted=False,
                    already_missing=True,
                    staging_root=parent_path,
                    staging_folder_name=staging_folder_name,
                    staging_folder_id=None,
                    payload={
                        "validation": validation_payload,
                        "target_path": target_path,
                    },
                )

            await client.delete_files(paths=[target_path], bdstoken=bdstoken)
            for _ in range(12):
                await asyncio.sleep(0.8)
                rows = await client.list_dir(parent_path, bdstoken=bdstoken)
                if isinstance(rows, int):
                    raise PanTransferProviderError(
                        f"Baidu failed to verify staging deletion: errno {rows}"
                    )
                still_exists = any(str(row.get("path") or "").strip() == target_path for row in rows)
                if not still_exists:
                    return PanTransferDeleteResult(
                        deleted=True,
                        already_missing=False,
                        staging_root=parent_path,
                        staging_folder_name=staging_folder_name,
                        staging_folder_id=None,
                        payload={
                            "validation": validation_payload,
                            "target_path": target_path,
                        },
                    )

            raise PanTransferProviderError(
                "Baidu staging directory was not deleted in time",
                payload={
                    "staging_root": parent_path,
                    "staging_folder_name": staging_folder_name,
                    "target_path": target_path,
                },
            )
