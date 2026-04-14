from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import aiohttp

from app.services.link_check.constants import PLATFORM_BAIDU, PLATFORM_QUARK
from app.services.link_check.parser import detect_platform_from_url, normalize_candidate_url


_QUARK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "origin": "https://pan.quark.cn",
    "referer": "https://pan.quark.cn/",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_BAIDU_HEADERS = {
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

_DIRECTORY_PREVIEW_LIMIT = 200


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def _normalize_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000.0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_payload: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    async with session.request(
        method,
        url,
        params=params,
        json=json_payload,
        data=data,
        headers=headers,
        cookies=cookies,
    ) as response:
        body = await response.text()
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ValueError("目录预览接口返回了非 JSON 响应") from exc
        if not isinstance(payload, dict):
            payload = {}
        return response.status, payload


def _build_entry(
    *,
    name: str,
    is_dir: bool,
    size_bytes: int | None = None,
    updated_at: datetime | None = None,
    entry_id: str | None = None,
) -> dict[str, Any]:
    return {
        "name": _normalize_text(name, max_length=255) or "未命名项",
        "is_dir": bool(is_dir),
        "size_bytes": size_bytes,
        "updated_at": updated_at,
        "entry_id": _normalize_text(entry_id, max_length=255) or None,
    }


def _extract_quark_share_id(url: str) -> tuple[str, str | None]:
    parsed = urlparse(str(url or "").strip())
    parts = [part for part in (parsed.path or "").split("/") if part]
    if len(parts) >= 2 and parts[0] == "s" and parts[1]:
        pwd = str((parse_qs(parsed.query).get("pwd") or [""])[0]).strip() or None
        return parts[1], pwd
    raise ValueError("无法解析夸克分享链接")


async def _preview_quark_directory(url: str) -> dict[str, Any]:
    pwd_id, passcode = _extract_quark_share_id(url)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers=_QUARK_HEADERS) as session:
        status_code, token_payload = await _request_json(
            session,
            "POST",
            "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token",
            json_payload={
                "pwd_id": pwd_id,
                "passcode": passcode or "",
                "support_visit_limit_private_share": True,
            },
        )
        token_data = token_payload.get("data") if isinstance(token_payload.get("data"), dict) else {}
        stoken = _normalize_text(token_data.get("stoken"))
        if status_code != 200 or not stoken:
            raise ValueError(_normalize_text(token_payload.get("message")) or "夸克分享访问失败")

        items: list[dict[str, Any]] = []
        page = 1
        total_count = 0
        truncated = False
        while True:
            detail_status, detail_payload = await _request_json(
                session,
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
                    "_sort": "file_type:asc,file_name:asc",
                },
            )
            if detail_status != 200:
                raise ValueError(_normalize_text(detail_payload.get("message")) or "夸克目录读取失败")
            detail_data = detail_payload.get("data") if isinstance(detail_payload.get("data"), dict) else {}
            rows = detail_data.get("list") if isinstance(detail_data.get("list"), list) else []
            metadata = detail_payload.get("metadata") if isinstance(detail_payload.get("metadata"), dict) else {}
            total_count = max(total_count, _normalize_int(metadata.get("_total")) or 0, len(items) + len(rows))
            for row in rows:
                payload = dict(row or {})
                items.append(
                    _build_entry(
                        name=_normalize_text(payload.get("file_name")) or "未命名项",
                        is_dir=bool(payload.get("dir")),
                        size_bytes=_normalize_int(payload.get("size")),
                        updated_at=_normalize_datetime(payload.get("updated_at") or payload.get("obj_update_time")),
                        entry_id=_normalize_text(payload.get("fid")),
                    )
                )
                if len(items) >= _DIRECTORY_PREVIEW_LIMIT:
                    truncated = True
                    break
            if truncated:
                break
            page_size = _normalize_int(metadata.get("_size")) or 50
            page_count = _normalize_int(metadata.get("_count")) or len(rows)
            if page_count < page_size or len(rows) <= 0:
                break
            page += 1
        return {
            "url": url,
            "platform": PLATFORM_QUARK,
            "supported": True,
            "item_count": max(total_count, len(items)),
            "truncated": truncated or max(total_count, len(items)) > len(items),
            "items": items,
            "message": None if items else "目录为空",
        }


def _extract_baidu_share_key(url: str) -> tuple[str, bool, str | None]:
    parsed = urlparse(str(url or "").strip())
    path = parsed.path or ""
    pwd = str((parse_qs(parsed.query).get("pwd") or [""])[0]).strip() or None
    if path.startswith("/s/"):
        share_key = path.split("/s/", 1)[1].split("/", 1)[0]
        return share_key, True, pwd
    if path.startswith("/share/init"):
        share_key = str((parse_qs(parsed.query).get("surl") or [""])[0]).strip()
        return share_key, False, pwd
    raise ValueError("无法解析百度分享链接")


async def _preview_baidu_directory(url: str) -> dict[str, Any]:
    share_key, requires_prefix_strip, passcode = _extract_baidu_share_key(url)
    short_url = share_key[1:] if requires_prefix_strip and share_key.startswith("1") and len(share_key) > 1 else share_key
    cookies: dict[str, str] | None = None
    referer_headers = dict(_BAIDU_HEADERS)
    referer_headers["Referer"] = url
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers=referer_headers) as session:
        if passcode:
            verify_status, verify_payload = await _request_json(
                session,
                "POST",
                f"https://pan.baidu.com/share/verify?surl={quote(short_url)}&pwd={quote(passcode)}",
                data={"pwd": passcode, "vcode": "", "vcode_str": ""},
                headers={
                    "Referer": url,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if verify_status != 200 or int(verify_payload.get("errno", -1) or -1) != 0:
                raise ValueError(_normalize_text(verify_payload.get("errmsg")) or "百度提取码校验失败")
            randsk = _normalize_text(verify_payload.get("randsk"))
            if randsk:
                cookies = {"BDCLND": randsk}

        list_status, list_payload = await _request_json(
            session,
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
                "root": "1",
                "view_mode": "1",
                "channel": "chunlei",
                "clienttype": "0",
            },
            cookies=cookies,
        )
        errno = int(list_payload.get("errno", -1) or -1)
        if list_status != 200 or errno != 0:
            raise ValueError(
                _normalize_text(list_payload.get("errmsg"))
                or _normalize_text(list_payload.get("show_msg"))
                or "百度目录读取失败"
            )
        rows = list_payload.get("list") if isinstance(list_payload.get("list"), list) else []
        items = [
            _build_entry(
                name=_normalize_text(row.get("server_filename")) or "未命名项",
                is_dir=int(row.get("isdir") or 0) == 1,
                size_bytes=_normalize_int(row.get("size")),
                updated_at=_normalize_datetime(row.get("server_mtime")),
                entry_id=_normalize_text(row.get("fs_id")),
            )
            for row in rows[:_DIRECTORY_PREVIEW_LIMIT]
        ]
        return {
            "url": url,
            "platform": PLATFORM_BAIDU,
            "supported": True,
            "item_count": len(rows),
            "truncated": len(rows) > len(items),
            "items": items,
            "message": None if items else "目录为空",
        }


async def preview_pan_transfer_link_directory(*, url: str) -> dict[str, Any]:
    normalized_url = normalize_candidate_url(str(url or "").strip())
    if not normalized_url:
        raise ValueError("链接不能为空")
    platform = detect_platform_from_url(normalized_url)
    if platform == PLATFORM_QUARK:
        return await _preview_quark_directory(normalized_url)
    if platform == PLATFORM_BAIDU:
        return await _preview_baidu_directory(normalized_url)
    raise ValueError("当前仅支持夸克和百度链接目录预览")
