from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from app.core.monitor_parser import normalize_url

from .constants import PLATFORM_CONFIGS, UNKNOWN_PLATFORM
from .platforms import canonicalize_platform_name, detect_extended_platform_from_url


def normalize_candidate_url(url: str) -> str:
    return normalize_url(url)


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc)


def detect_platform_from_url(url: str) -> str:
    normalized = normalize_candidate_url(url)
    if not normalized:
        return UNKNOWN_PLATFORM

    extended_platform = detect_extended_platform_from_url(normalized)
    if extended_platform != UNKNOWN_PLATFORM:
        return extended_platform

    host = urlparse(normalized).netloc.lower()
    for platform, config in PLATFORM_CONFIGS.items():
        for domain in config.get("domains", ()):
            if domain and domain in host:
                return canonicalize_platform_name(platform)
    return UNKNOWN_PLATFORM


def canonical_target_key(url: str, fallback: Optional[str] = None) -> str:
    normalized = normalize_candidate_url(url)
    if normalized:
        return normalized
    return fallback or ""
