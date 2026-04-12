from __future__ import annotations

import random
import re
import string
from datetime import datetime
from typing import Any, Iterable


_SLUG_REGEX = re.compile(r"[^a-z0-9]+")


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


def build_staging_folder_name(*, batch_id: int, item_id: int, title: str) -> str:
    slug_source = normalize_text(title, max_length=64) or f"item-{int(item_id)}"
    ascii_slug = _SLUG_REGEX.sub("-", slug_source.lower()).strip("-")
    if not ascii_slug:
        ascii_slug = f"item-{int(item_id)}"
    return f"tg-transfer-{int(batch_id)}-{int(item_id)}-{ascii_slug[:40]}".strip("-")


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
