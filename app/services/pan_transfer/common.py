from __future__ import annotations

import random
import re
import string
from datetime import datetime
from typing import Any, Iterable


_SLUG_REGEX = re.compile(r"[^a-z0-9]+")
_INVALID_PATH_SEGMENT_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE_REGEX = re.compile(r"[\s\u3000]+")
_MASKED_CN_POOL = tuple(
    "春江花月夜山川云海星河风竹松岚雪影霜华晨暮青玄流光长歌隐岸归舟烟霞澄空静水澜庭初晴寒林青屿遥岑"
    "孤灯听雨疏钟映雪微澜清川朝雾平沙远汀沧浪晚舟苍岚晴峦长汀轻鸿闲庭归梦疏林清霁秋声月白"
)
_DIGIT_TO_CN = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

DEFAULT_TRANSFER_LAYOUT = "independent"
DEFAULT_ITEM_FOLDER_MODE = "auto"
DEFAULT_SHARE_TARGET_MODE = "resource_dir"
TRANSFER_LAYOUT_INDEPENDENT = "independent"
TRANSFER_LAYOUT_BATCH_ARCHIVE = "batch_archive"
ITEM_FOLDER_MODE_AUTO = "auto"
ITEM_FOLDER_MODE_CUSTOM = "custom"
SHARE_TARGET_RESOURCE_DIR = "resource_dir"
SHARE_TARGET_CONTENT_ROOT = "content_root"
PATH_TEMPLATE_UNIQUE_TOKENS = ("{item_id}", "{share_key}")


def utcnow() -> datetime:
    return datetime.utcnow()


def normalize_text(value: Any, *, max_length: int | None = None, allow_empty: bool = True) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    if not text and not allow_empty:
        raise ValueError("value cannot be empty")
    return text


def normalize_positive_int(value: Any, *, default: int | None = None, minimum: int = 1) -> int | None:
    if value in (None, ""):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    if normalized < minimum:
        return default
    return normalized


def normalize_relative_path(path_value: str | None) -> str:
    parts = [part.strip() for part in str(path_value or "").replace("\\", "/").split("/") if part.strip()]
    return "/".join(parts)


def sanitize_path_segment(value: Any, *, fallback: str, max_length: int = 96) -> str:
    text = "" if value is None else str(value).strip()
    text = _INVALID_PATH_SEGMENT_REGEX.sub(" ", text)
    text = _WHITESPACE_REGEX.sub(" ", text).strip(" .-_")
    if not text:
        text = str(fallback).strip() or "item"
    if len(text) > max_length:
        text = text[:max_length].strip(" .-_")
    return text or (str(fallback).strip() or "item")


def build_staging_folder_name(*, batch_id: int, item_id: int, title: str) -> str:
    slug_source = normalize_text(title, max_length=64) or f"item-{int(item_id)}"
    ascii_slug = _SLUG_REGEX.sub("-", slug_source.lower()).strip("-")
    if not ascii_slug:
        ascii_slug = f"item-{int(item_id)}"
    return f"tg-transfer-{int(batch_id)}-{int(item_id)}-{ascii_slug[:40]}".strip("-")


def build_title_slug(value: Any, *, fallback: str) -> str:
    slug_source = normalize_text(value, max_length=80, allow_empty=True) or fallback
    ascii_slug = _SLUG_REGEX.sub("-", slug_source.lower()).strip("-")
    return ascii_slug or fallback


def build_masked_cn_title(value: Any, *, fallback: str) -> str:
    source = sanitize_path_segment(value, fallback=fallback, max_length=80)
    masked_chars: list[str] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        if char.isdigit():
            masked_chars.append(_DIGIT_TO_CN.get(char, "零"))
            continue
        pool_index = (ord(char) + index * 7) % len(_MASKED_CN_POOL)
        masked_chars.append(_MASKED_CN_POOL[pool_index])
    masked = "".join(masked_chars)
    return sanitize_path_segment(masked, fallback=fallback, max_length=80)


def normalize_batch_path_strategy(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    transfer_layout = str(raw.get("transfer_layout") or DEFAULT_TRANSFER_LAYOUT).strip().lower()
    if transfer_layout not in {TRANSFER_LAYOUT_INDEPENDENT, TRANSFER_LAYOUT_BATCH_ARCHIVE}:
        transfer_layout = DEFAULT_TRANSFER_LAYOUT

    item_folder_mode = str(raw.get("item_folder_mode") or DEFAULT_ITEM_FOLDER_MODE).strip().lower()
    if item_folder_mode not in {ITEM_FOLDER_MODE_AUTO, ITEM_FOLDER_MODE_CUSTOM}:
        item_folder_mode = DEFAULT_ITEM_FOLDER_MODE

    share_target_mode = str(raw.get("share_target_mode") or DEFAULT_SHARE_TARGET_MODE).strip().lower()
    if share_target_mode not in {SHARE_TARGET_RESOURCE_DIR, SHARE_TARGET_CONTENT_ROOT}:
        share_target_mode = DEFAULT_SHARE_TARGET_MODE

    batch_folder_name = normalize_text(raw.get("batch_folder_name"), max_length=120, allow_empty=True)
    item_folder_template = normalize_text(raw.get("item_folder_template"), max_length=120, allow_empty=True)
    if item_folder_mode != ITEM_FOLDER_MODE_CUSTOM:
        item_folder_template = ""

    return {
        "transfer_layout": transfer_layout,
        "batch_folder_name": batch_folder_name,
        "item_folder_mode": item_folder_mode,
        "item_folder_template": item_folder_template,
        "share_target_mode": share_target_mode,
    }


def build_batch_archive_folder_name(*, batch_id: int, strategy: dict[str, Any] | None = None) -> str:
    normalized = normalize_batch_path_strategy(strategy)
    requested = normalized.get("batch_folder_name")
    fallback = f"batch-{int(batch_id)}"
    return sanitize_path_segment(requested, fallback=fallback, max_length=96)


def render_item_folder_template(
    template: str | None,
    *,
    batch_id: int,
    item_id: int,
    title: str,
    platform: str,
    share_key: str | None,
    now: datetime | None = None,
) -> str:
    current = now or datetime.utcnow()
    safe_title = sanitize_path_segment(title, fallback=f"item-{int(item_id)}", max_length=80)
    title_slug = build_title_slug(title, fallback=f"item-{int(item_id)}")
    context = {
        "title": safe_title,
        "title_slug": title_slug,
        "title_masked_cn": build_masked_cn_title(title, fallback=f"资源{int(item_id)}"),
        "platform": sanitize_path_segment(platform, fallback="disk", max_length=32),
        "batch_id": str(int(batch_id)),
        "item_id": str(int(item_id)),
        "share_key": sanitize_path_segment(share_key, fallback="", max_length=32),
        "date": current.strftime("%Y%m%d"),
    }
    rendered = str(template or "")
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return sanitize_path_segment(rendered, fallback=safe_title, max_length=96)


def build_item_folder_name(
    *,
    batch_id: int,
    item_id: int,
    title: str,
    platform: str,
    share_key: str | None,
    strategy: dict[str, Any] | None = None,
) -> str:
    normalized = normalize_batch_path_strategy(strategy)
    if normalized["item_folder_mode"] != ITEM_FOLDER_MODE_CUSTOM:
        return build_staging_folder_name(batch_id=batch_id, item_id=item_id, title=title)

    template = str(normalized.get("item_folder_template") or "").strip()
    rendered = render_item_folder_template(
        template,
        batch_id=batch_id,
        item_id=item_id,
        title=title,
        platform=platform,
        share_key=share_key,
    )
    if any(token in template for token in PATH_TEMPLATE_UNIQUE_TOKENS):
        return rendered
    suffix = f"__i{int(item_id)}"
    available_length = max(16, 96 - len(suffix))
    return f"{rendered[:available_length].rstrip(' .-_')}{suffix}".strip()


def resolve_batch_item_storage_plan(
    *,
    default_save_root: str,
    batch_id: int,
    item_id: int,
    title: str,
    platform: str,
    share_key: str | None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_batch_path_strategy(strategy)
    staging_root = normalize_relative_path(default_save_root)
    batch_folder_name = None
    if normalized["transfer_layout"] == TRANSFER_LAYOUT_BATCH_ARCHIVE:
        batch_folder_name = build_batch_archive_folder_name(batch_id=batch_id, strategy=normalized)
        staging_root = normalize_relative_path("/".join(part for part in (staging_root, batch_folder_name) if part))

    staging_folder_name = build_item_folder_name(
        batch_id=batch_id,
        item_id=item_id,
        title=title,
        platform=platform,
        share_key=share_key,
        strategy=normalized,
    )
    resolved_path = "/".join(part for part in (staging_root, staging_folder_name) if part)
    return {
        "transfer_layout": normalized["transfer_layout"],
        "batch_folder_name": batch_folder_name,
        "staging_root": staging_root,
        "staging_folder_name": staging_folder_name,
        "resolved_path": resolved_path,
        "share_target_mode": normalized["share_target_mode"],
    }


def generate_share_passcode(length: int = 4) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(max(4, int(length or 4))))


def dedupe_ints(values: Iterable[Any]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_value in values:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
