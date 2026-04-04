from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import aiohttp

from app.core.monitor_parser import (
    extract_embedded_redirect_targets,
    get_netdisk_name_for_url,
    normalize_url,
    resolve_netdisk_url,
)
from app.core.monitor_rules import load_monitor_rules

from .constants import UNKNOWN_PLATFORM
from .platforms import canonicalize_platform_name, detect_extended_platform_from_url


def _build_netdisk_map(rules: Dict[str, Any]) -> List[Tuple[List[str], str]]:
    return [(item["keys"], item["name"]) for item in rules.get("netdisk_map", [])]


class LinkResolver:
    def __init__(self, rules: Dict[str, Any] | None = None):
        self._rules = rules or load_monitor_rules()
        self._redirect_query_keys = tuple(self._rules.get("redirect_query_keys", []))
        self._netdisk_map = _build_netdisk_map(self._rules)

    @property
    def redirect_query_keys(self) -> Iterable[str]:
        return self._redirect_query_keys

    def guess_platform(self, url: str) -> str:
        normalized = normalize_url(url)
        if not normalized:
            return UNKNOWN_PLATFORM

        direct_platform = detect_extended_platform_from_url(normalized)
        if direct_platform != UNKNOWN_PLATFORM:
            return direct_platform

        platform = get_netdisk_name_for_url(normalized, self._netdisk_map)
        if platform:
            return canonicalize_platform_name(platform)

        for target in extract_embedded_redirect_targets(normalized, self._redirect_query_keys):
            target_platform = detect_extended_platform_from_url(target)
            if target_platform != UNKNOWN_PLATFORM:
                return target_platform
            platform = get_netdisk_name_for_url(target, self._netdisk_map)
            if platform:
                return canonicalize_platform_name(platform)

        return UNKNOWN_PLATFORM

    async def resolve(self, url: str, http_session: aiohttp.ClientSession) -> str:
        normalized = normalize_url(url)
        if not normalized:
            return ""

        return await resolve_netdisk_url(
            normalized,
            self._netdisk_map,
            self._redirect_query_keys,
            http_session,
        )
