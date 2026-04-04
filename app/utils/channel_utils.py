"""Utilities for normalizing Telegram channel identifiers."""

from __future__ import annotations

from typing import Iterable, List
from urllib.parse import urlparse


TELEGRAM_HOSTS = {
    "t.me",
    "www.t.me",
    "telegram.me",
    "www.telegram.me",
}


def normalize_channel_username(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("channel username cannot be empty")

    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        if parsed.netloc.lower() not in TELEGRAM_HOSTS:
            raise ValueError("only Telegram channel URLs are supported")
        text = parsed.path.strip("/")

    text = text.strip().strip("/")
    if text.startswith("@"):
        text = text[1:]

    lowered = text.lower()
    if lowered.startswith("joinchat/"):
        text = "+" + text.split("/", 1)[1]

    if "?" in text:
        text = text.split("?", 1)[0]
    if "#" in text:
        text = text.split("#", 1)[0]

    text = text.strip()
    if not text:
        raise ValueError("channel username cannot be empty")
    if " " in text:
        raise ValueError("channel username cannot contain spaces")

    return text


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result
