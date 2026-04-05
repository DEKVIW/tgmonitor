"""Message parsing helpers for the Telegram monitor."""

from __future__ import annotations

import datetime as dt
import html
import asyncio
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qsl, unquote, urljoin, urlparse

import aiohttp

from app.core.monitor_rules import load_monitor_rules, resolve_channel_profile, resolve_channel_profile_name

try:
    from telethon.tl.types import KeyboardButtonUrl, MessageEntityTextUrl, MessageEntityUrl
except ImportError:  # pragma: no cover - optional for tests
    MessageEntityTextUrl = MessageEntityUrl = KeyboardButtonUrl = object

try:
    from urlextract import URLExtract as _URLExtract
except ImportError:  # pragma: no cover - fallback used in local validation
    _URLExtract = None


URL_RESOLVE_TIMEOUT_SECONDS = 6
MAX_URL_RESOLVE_DEPTH = 4
URL_RESOLUTION_CACHE_TTL_SECONDS = 6 * 60 * 60
HASHTAG_PATTERN = re.compile(r"#([\u4e00-\u9fa5A-Za-z0-9_+\-]+)")
BRACKET_TAG_PATTERN = re.compile(r"[【\[]([^】\]]{1,20})[】\]]")


class _FallbackURLExtract:
    _pattern = re.compile(r"(?:https?://|www\.)[^\s\"'<>]+", re.IGNORECASE)

    def find_urls(self, text: str) -> List[str]:
        return self._pattern.findall(text or "")

    def has_urls(self, text: str) -> bool:
        return bool(self._pattern.search(text or ""))


URL_EXTRACTOR = _URLExtract() if _URLExtract is not None else _FallbackURLExtract()
_url_cache_lock = threading.RLock()
_url_resolution_cache: Dict[str, Dict[str, Any]] = {}
LINE_MESSAGE_MODE_PER_LINK = "per_link_line"
DEFAULT_HTTP_REDIRECT_MAX_HOPS = 8
DEFAULT_NETDISK_HINT_ALIASES: Dict[str, List[str]] = {
    "\u767e\u5ea6\u7f51\u76d8": ["BD", "baidu", "\u767e\u5ea6", "\u767e\u5ea6\u76d8"],
    "\u5938\u514b\u7f51\u76d8": ["QK", "quark", "\u5938\u514b"],
    "\u963f\u91cc\u4e91\u76d8": ["AL", "ALI", "alipan", "aliyun", "\u963f\u91cc", "\u963f\u91cc\u4e91"],
    "\u5929\u7ffc\u4e91\u76d8": ["TY", "189", "\u5929\u7ffc", "\u5929\u7ffc\u4e91"],
    "115\u7f51\u76d8": ["115", "115pan", "115.com"],
    "123\u4e91\u76d8": ["123", "123pan", "123912"],
    "UC\u7f51\u76d8": ["UC", "ucdrive", "ucdisk"],
    "\u8fc5\u96f7": ["XL", "xunlei", "thunder", "\u8fc5\u96f7"],
    "139\u4e91\u76d8": ["139", "139yun", "\u79fb\u52a8\u4e91", "caiyun"],
}
DEFAULT_REDIRECT_RESOLVER_CONFIG: Dict[str, Any] = {
    "max_depth": MAX_URL_RESOLVE_DEPTH,
    "max_redirect_hops": DEFAULT_HTTP_REDIRECT_MAX_HOPS,
    "force_get_domains": [
        "t.cn",
        "weibo.cn",
        "weibo.com",
        "t.co",
        "x.com",
        "url.cn",
        "bit.ly",
        "telegra.ph",
    ],
}
COURSE_LIST_CONTENT_MODE = "course_list"
MOVIE_CONTENT_MODE = "movie"
MOVIE_SIZE_PATTERN = re.compile(
    r"(?P<size>\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB|K|M|G|T))\b",
    re.IGNORECASE,
)
MOVIE_PROGRESS_PATTERN = re.compile(
    r"(S\d{1,2}(?:E\d{1,3}(?:-E?\d{1,3})?)?|全\d+集|\d+集全|更至EP\d+|更新至\s*\d+集|首更\s*\d+集?)",
    re.IGNORECASE,
)
MOVIE_VARIANT_START_PATTERN = re.compile(
    r"\b(?:4K|2160P|1080P|720P|WEB[-\s]?DL|WEBRIP|BLURAY|REMUX|HDR10\+?|HDR|SDR|DV|HQ|NF|S\d{1,2}(?:E\d{1,3}(?:-E?\d{1,3})?)?|全\d+集|\d+集全|更至EP\d+|更新至\s*\d+集|首更\s*\d+集?)\b",
    re.IGNORECASE,
)
MOVIE_YEAR_PATTERN = re.compile(r"[（(](\d{4})[)）]")
MOVIE_TITLE_TECH_PATTERNS = [
    re.compile(r"\b(?:4K|2160P|1080P|720P|WEB[-\s]?DL|WEBRIP|BLURAY|REMUX|NF|HDR10\+?|HDR|SDR|DV|HQ|EDR)\b", re.IGNORECASE),
    re.compile(r"\b(?:DDP(?:[.\d]+)?|DTS(?:[.\dA-Z+-]+)?|AAC(?:[.\d]+)?|ATMOS)\b", re.IGNORECASE),
    re.compile(r"(?:高码率|原盘REMUX|杜比视界|杜比全景声|内封简繁英|内封简中|内封中字|内嵌简中|简繁英字幕|简中字幕|中文字幕|中字|双版本|修复版|正式版|完整版|无广告|无台标|国语|英语|国粤双语|双语|HiveWeb)", re.IGNORECASE),
]
MOVIE_TITLE_CATEGORY_PATTERN = re.compile(r"\s*[|｜]\s*(电影|剧集|电视剧|短剧|综艺|动漫|动画|国漫|纪录片)\s*$", re.IGNORECASE)
MOVIE_ACTOR_SUFFIX_PATTERN = re.compile(
    r"\s+(?P<actors>[\u4e00-\u9fa5A-Za-z0-9]{1,10}(?:[&＆/／][\u4e00-\u9fa5A-Za-z0-9]{1,10}){1,4})\s*$"
)
MOVIE_NOISE_PATTERNS = [
    re.compile(r"最新热门抖音快手百度番茄红果等付费短剧推荐", re.IGNORECASE),
    re.compile(r"每日同步更新", re.IGNORECASE),
    re.compile(r"云盘合作播放器", re.IGNORECASE),
    re.compile(r"播放器.*字幕问题", re.IGNORECASE),
    re.compile(r"版权.*DMCA", re.IGNORECASE),
    re.compile(r"版权反馈", re.IGNORECASE),
    re.compile(r"\bDMCA\b", re.IGNORECASE),
    re.compile(r"频道.*群组.*投稿.*搜索", re.IGNORECASE),
    re.compile(r"社区.*点击查看", re.IGNORECASE),
    re.compile(r"资源搜索机器人", re.IGNORECASE),
    re.compile(r"点击搜索", re.IGNORECASE),
    re.compile(r"国外影视发布频道", re.IGNORECASE),
    re.compile(r"此频道只发", re.IGNORECASE),
    re.compile(r"VidHub", re.IGNORECASE),
    re.compile(r"播放神器", re.IGNORECASE),
    re.compile(r"自研后端", re.IGNORECASE),
    re.compile(r"大带宽", re.IGNORECASE),
]
MOVIE_RESOURCE_FIELD_ALIASES = [
    "链接",
    "下载地址",
    "主链",
    "备用",
    "网址",
    "夸克",
    "百度",
    "阿里",
    "迅雷",
    "天翼",
    "115",
    "123",
    "UC",
]
MOVIE_EXTRA_NOISE_ALIASES = [
    "来自",
    "来源",
    "频道",
    "群组",
    "投稿",
    "投稿人",
    "搜索",
    "搜资源",
    "资源搜索机器人",
    "社区",
    "机场",
    "公费服",
    "分享",
    "链接",
    "下载地址",
    "网址",
    "版权",
]
MOVIE_FALLBACK_META_ALIASES = [
    "评分",
    "TMDB评分",
    "豆瓣评分",
    "类型",
    "地区",
    "语言",
    "主演",
    "导演",
    "更新",
    "集数",
    "片长",
]
MOVIE_TECH_LINE_TOKENS = re.compile(
    r"(?:4K|2160P|1080P|720P|WEB[-\s]?DL|WEBRIP|BLURAY|REMUX|HDR10\+?|HDR|SDR|DV|HQ|NF|EDR|"
    r"DDP(?:[.\d]+)?|DTS(?:[.\dA-Z+-]+)?|AAC(?:[.\d]+)?|ATMOS|FLAC|MAXPLUS|60FPS|120FPS|"
    r"S\d{1,2}(?:E\d{1,3}(?:-E?\d{1,3})?)?|全\d+集|\d+集全|更至EP\d+|更新至\s*\d+集|首更\s*\d+集?|"
    r"高码率|原盘REMUX|杜比视界|杜比全景声|内封简繁英|内封简中|内封中字|内嵌简中|简繁英字幕|简中字幕|"
    r"中文字幕|中字|双版本|修复版|正式版|完整版|无广告|无台标|国语|英语|国粤双语|双语|HiveWeb)",
    re.IGNORECASE,
)
MOVIE_FIELD_WRAPPER_CHARS = " \t\u3000[]【】()（）<>《》「」『』"
MOVIE_CATEGORY_HINTS = [
    "电影",
    "剧集",
    "电视剧",
    "短剧",
    "综艺",
    "动漫",
    "动画",
    "国漫",
    "国产",
    "国产剧",
    "纪录片",
]


@dataclass
class ParseDiagnostics:
    profile_name: str
    raw_url_count: int = 0
    resolved_url_count: int = 0
    redirect_resolved_count: int = 0
    extracted_link_count: int = 0
    raw_url_samples: List[str] = field(default_factory=list)
    resolved_url_samples: List[str] = field(default_factory=list)


def _get_netdisk_map(rules: Dict[str, Any]) -> List[Tuple[List[str], str]]:
    return [(item["keys"], item["name"]) for item in rules.get("netdisk_map", [])]


def normalize_url(url: str) -> str:
    if not url:
        return ""

    normalized = html.unescape(url).strip().strip("'\"<>[]()")
    if not normalized:
        return ""

    if normalized.startswith("//"):
        normalized = f"https:{normalized}"

    parsed = urlparse(normalized)
    if not parsed.scheme and re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}([/:?#].*)?$", normalized):
        normalized = f"https://{normalized}"

    return unquote(normalized)


def iterate_decoded_values(value: str, max_rounds: int = 3) -> Iterable[str]:
    current = value
    seen = set()

    for _ in range(max_rounds):
        if not current or current in seen:
            break

        seen.add(current)
        yield current

        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded


def extract_urls_from_text_fragment(text: str) -> List[str]:
    if not text:
        return []

    urls = []
    seen = set()
    candidates: List[str] = []

    for candidate in iterate_decoded_values(text):
        stripped = candidate.strip().strip("'\"<>[]()")
        if stripped:
            candidates.append(stripped)

        for found_url in URL_EXTRACTOR.find_urls(candidate):
            candidates.append(found_url)

    for candidate in candidates:
        normalized = normalize_url(candidate)
        parsed = urlparse(normalized)
        if (
            normalized
            and parsed.scheme in {"http", "https"}
            and parsed.netloc
            and normalized not in seen
        ):
            seen.add(normalized)
            urls.append(normalized)

    return urls


def get_netdisk_name_for_url(url: str, netdisk_map: List[Tuple[List[str], str]]) -> str | None:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if not netloc:
        return None

    for keys, name in netdisk_map:
        if any(str(key).lower() in netloc for key in keys):
            return name

    return None


def get_profile_netdisk_name_for_url(url: str, domain_map: Dict[str, List[str]] | None) -> str | None:
    if not domain_map:
        return None

    parsed = urlparse(url)
    netloc = parsed.netloc.lower().strip(".")
    if not netloc:
        return None

    for netdisk_name, domains in domain_map.items():
        for domain in domains or []:
            normalized_domain = str(domain).lower().strip().strip(".")
            if not normalized_domain:
                continue
            if netloc == normalized_domain or netloc.endswith(f".{normalized_domain}"):
                return netdisk_name

    return None


def get_redirect_resolver_config(rules: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(DEFAULT_REDIRECT_RESOLVER_CONFIG)
    config.update(rules.get("redirect_resolver", {}) or {})
    return config


def get_url_hostname(url: str) -> str:
    return urlparse(url).netloc.lower().strip(".")


def hostname_matches(hostname: str, domain: str) -> bool:
    normalized_host = (hostname or "").lower().strip(".")
    normalized_domain = (domain or "").lower().strip(".")
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def url_matches_domains(url: str, domains: Iterable[str]) -> bool:
    hostname = get_url_hostname(url)
    return any(hostname_matches(hostname, domain) for domain in domains)


def get_netdisk_hint_aliases(profile: Dict[str, Any]) -> List[Tuple[str, str]]:
    merged_aliases: Dict[str, List[str]] = {
        name: list(aliases) for name, aliases in DEFAULT_NETDISK_HINT_ALIASES.items()
    }
    for netdisk_name, aliases in (profile.get("netdisk_hint_aliases") or {}).items():
        bucket = merged_aliases.setdefault(netdisk_name, [])
        for alias in aliases or []:
            normalized_alias = str(alias).strip()
            if normalized_alias and normalized_alias not in bucket:
                bucket.append(normalized_alias)

    ordered_aliases: List[Tuple[str, str]] = []
    for netdisk_name, aliases in merged_aliases.items():
        for alias in aliases:
            ordered_aliases.append((netdisk_name, alias))

    ordered_aliases.sort(key=lambda item: len(item[1]), reverse=True)
    return ordered_aliases


def _normalize_hint_token(text: str) -> str:
    normalized = remove_urls_from_text(text or "")
    normalized = HASHTAG_PATTERN.sub(" ", normalized)
    normalized = re.sub(r"@[A-Za-z0-9_]+", " ", normalized)
    normalized = re.sub(r"[\s#@|:：,，;；.。!！?？、/\-_=+()（）\[\]{}]+", "", normalized)
    return normalized.strip().casefold()


def _hint_alias_to_pattern(alias: str) -> re.Pattern[str]:
    if re.fullmatch(r"[A-Za-z0-9.]+", alias):
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(alias), re.IGNORECASE)


def infer_netdisk_name_from_text(text: str, hint_aliases: List[Tuple[str, str]]) -> str | None:
    cleaned_text = remove_urls_from_text(text or "")
    if not cleaned_text.strip():
        return None

    for netdisk_name, alias in hint_aliases:
        if _hint_alias_to_pattern(alias).search(cleaned_text):
            return netdisk_name

    return None


def is_hint_only_line(text: str, hint_aliases: List[Tuple[str, str]]) -> bool:
    normalized_text = _normalize_hint_token(text)
    if not normalized_text:
        return False

    for _, alias in hint_aliases:
        if normalized_text == _normalize_hint_token(alias):
            return True

    return False


def extract_embedded_redirect_targets(url: str, redirect_query_keys: Iterable[str]) -> List[str]:
    parsed = urlparse(url)
    candidate_fragments = []
    redirect_keys = {key.lower() for key in redirect_query_keys}

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        value_lower = value.lower()
        if (
            key_lower in redirect_keys
            or "http://" in value_lower
            or "https://" in value_lower
            or "%3a%2f%2f" in value_lower
        ):
            candidate_fragments.append(value)

    if parsed.fragment:
        candidate_fragments.append(parsed.fragment)

    targets = []
    seen = set()
    for fragment in candidate_fragments:
        for candidate_url in extract_urls_from_text_fragment(fragment):
            if candidate_url not in seen:
                seen.add(candidate_url)
                targets.append(candidate_url)

    return targets


def extract_redirect_urls_from_html(body: str, base_url: str = "") -> List[str]:
    if not body:
        return []

    candidates = []
    patterns = [
        r"""location(?:\.href|\.replace)?\s*=\s*["']([^"']+)["']""",
        r"""location(?:\.assign)?\(\s*["']([^"']+)["']\s*\)""",
        r"""(?:top|self|parent)\.location(?:\.href)?\s*=\s*["']([^"']+)["']""",
        r"""window\.open\(\s*["']([^"']+)["']""",
        r"""content=["'][^"']*url=([^"']+)["']""",
    ]

    for pattern in patterns:
        candidates.extend(re.findall(pattern, body, flags=re.IGNORECASE))

    candidates.extend(
        match.group(1)
        for match in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", body, flags=re.IGNORECASE)
    )

    if not candidates and ("http://" in body or "https://" in body):
        candidates.extend(re.findall(r"""https?://[^\s"'<>]+""", body))

    urls = []
    seen = set()
    for candidate in candidates:
        normalized_candidate = normalize_url(urljoin(base_url, html.unescape(candidate))) if base_url else normalize_url(candidate)
        candidate_urls = extract_urls_from_text_fragment(normalized_candidate or candidate)
        if normalized_candidate and normalized_candidate not in candidate_urls:
            candidate_urls.insert(0, normalized_candidate)
        for candidate_url in candidate_urls:
            if candidate_url not in seen:
                seen.add(candidate_url)
                urls.append(candidate_url)

    return urls


def extract_redirect_urls_from_refresh_header(refresh_header: str | None, base_url: str = "") -> List[str]:
    if not refresh_header:
        return []

    candidates = []
    match = re.search(r"""url\s*=\s*['"]?([^'";]+)""", refresh_header, flags=re.IGNORECASE)
    if match:
        candidates.append(match.group(1))

    urls = []
    seen = set()
    for candidate in candidates:
        normalized_candidate = normalize_url(urljoin(base_url, html.unescape(candidate))) if base_url else normalize_url(candidate)
        candidate_urls = extract_urls_from_text_fragment(normalized_candidate or candidate)
        if normalized_candidate and normalized_candidate not in candidate_urls:
            candidate_urls.insert(0, normalized_candidate)
        for candidate_url in candidate_urls:
            if candidate_url not in seen:
                seen.add(candidate_url)
                urls.append(candidate_url)

    return urls


def _get_cached_resolution(url: str) -> str | None:
    with _url_cache_lock:
        cache_entry = _url_resolution_cache.get(url)
        if not cache_entry:
            return None

        if dt.datetime.now().timestamp() - cache_entry["timestamp"] > URL_RESOLUTION_CACHE_TTL_SECONDS:
            _url_resolution_cache.pop(url, None)
            return None

        return cache_entry["resolved_url"]


def _set_cached_resolution(url: str, resolved_url: str) -> None:
    with _url_cache_lock:
        _url_resolution_cache[url] = {
            "resolved_url": resolved_url,
            "timestamp": dt.datetime.now().timestamp(),
        }


async def fetch_redirect_target(
    url: str,
    http_session: aiohttp.ClientSession,
    resolver_config: Dict[str, Any] | None = None,
) -> Tuple[str, List[str]]:
    config = resolver_config or DEFAULT_REDIRECT_RESOLVER_CONFIG
    max_redirect_hops = int(config.get("max_redirect_hops", DEFAULT_HTTP_REDIRECT_MAX_HOPS))
    methods = ("get", "head") if url_matches_domains(url, config.get("force_get_domains", [])) else ("head", "get")

    for method_name in methods:
        try:
            request = getattr(http_session, method_name)
            async with request(url, allow_redirects=True, max_redirects=max_redirect_hops) as response:
                final_url = normalize_url(str(response.url))
                history_targets = [
                    normalize_url(str(history_item.url))
                    for history_item in getattr(response, "history", [])
                    if normalize_url(str(history_item.url))
                ]
                refresh_targets = extract_redirect_urls_from_refresh_header(
                    response.headers.get("Refresh"),
                    final_url or url,
                )
                html_targets: List[str] = []
                content_type = (response.headers.get("Content-Type") or "").lower()
                is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
                if method_name == "get" and is_html:
                    body = await response.text(errors="ignore")
                    html_targets = extract_redirect_urls_from_html(body, base_url=final_url or url)
                all_targets = list(
                    dict.fromkeys(
                        candidate
                        for candidate in history_targets + refresh_targets + html_targets
                        if candidate and candidate != final_url
                    )
                )
                return final_url or url, all_targets
        except Exception:
            continue

    return url, []


async def resolve_netdisk_url(
    url: str,
    netdisk_map: List[Tuple[List[str], str]],
    redirect_query_keys: Iterable[str],
    http_session: aiohttp.ClientSession,
    resolver_config: Dict[str, Any] | None = None,
    depth: int = 0,
    visited: set[str] | None = None,
) -> str:
    config = resolver_config or DEFAULT_REDIRECT_RESOLVER_CONFIG
    normalized_url = normalize_url(url)
    if not normalized_url:
        return ""

    if visited is None:
        visited = set()
    max_depth = int(config.get("max_depth", MAX_URL_RESOLVE_DEPTH))
    if normalized_url in visited or depth > max_depth:
        return normalized_url

    cached_url = _get_cached_resolution(normalized_url)
    if cached_url:
        return cached_url

    if get_netdisk_name_for_url(normalized_url, netdisk_map):
        _set_cached_resolution(normalized_url, normalized_url)
        return normalized_url

    next_visited = set(visited)
    next_visited.add(normalized_url)

    for embedded_target in extract_embedded_redirect_targets(normalized_url, redirect_query_keys):
        resolved_target = await resolve_netdisk_url(
            embedded_target,
            netdisk_map,
            redirect_query_keys,
            http_session,
            resolver_config=config,
            depth=depth + 1,
            visited=next_visited,
        )
        if get_netdisk_name_for_url(resolved_target, netdisk_map):
            _set_cached_resolution(normalized_url, resolved_target)
            return resolved_target

    final_url, html_targets = await fetch_redirect_target(normalized_url, http_session, resolver_config=config)
    if final_url and final_url != normalized_url:
        resolved_target = await resolve_netdisk_url(
            final_url,
            netdisk_map,
            redirect_query_keys,
            http_session,
            resolver_config=config,
            depth=depth + 1,
            visited=next_visited,
        )
        _set_cached_resolution(normalized_url, resolved_target)
        return resolved_target

    for html_target in html_targets:
        resolved_target = await resolve_netdisk_url(
            html_target,
            netdisk_map,
            redirect_query_keys,
            http_session,
            resolver_config=config,
            depth=depth + 1,
            visited=next_visited,
        )
        if get_netdisk_name_for_url(resolved_target, netdisk_map):
            _set_cached_resolution(normalized_url, resolved_target)
            return resolved_target

    _set_cached_resolution(normalized_url, normalized_url)
    return normalized_url


async def resolve_message_urls(
    all_urls: Iterable[str],
    netdisk_map: List[Tuple[List[str], str]],
    redirect_query_keys: Iterable[str],
    resolver_config: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, str], int]:
    config = resolver_config or DEFAULT_REDIRECT_RESOLVER_CONFIG
    normalized_urls = []
    for raw_url in all_urls:
        normalized_url = normalize_url(raw_url)
        if normalized_url:
            normalized_urls.append(normalized_url)

    if not normalized_urls:
        return {}, 0

    resolved_results: Dict[str, str] = {}
    pending_urls = []
    redirect_resolved_count = 0

    for url in normalized_urls:
        if get_netdisk_name_for_url(url, netdisk_map):
            resolved_results[url] = url
        else:
            embedded_targets = extract_embedded_redirect_targets(url, redirect_query_keys)
            if embedded_targets:
                for embedded_target in embedded_targets:
                    normalized_target = normalize_url(embedded_target)
                    if get_netdisk_name_for_url(normalized_target, netdisk_map):
                        resolved_results[url] = normalized_target
                        redirect_resolved_count += int(normalized_target != url)
                        break
                else:
                    pending_urls.append(url)
            else:
                pending_urls.append(url)

    if not pending_urls:
        return resolved_results, redirect_resolved_count

    timeout = aiohttp.ClientTimeout(total=URL_RESOLVE_TIMEOUT_SECONDS)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers, cookie_jar=cookie_jar) as http_session:
        fetched_results = await asyncio.gather(
            *(
                resolve_netdisk_url(
                    url,
                    netdisk_map,
                    redirect_query_keys,
                    http_session,
                    resolver_config=config,
                )
                for url in pending_urls
            ),
            return_exceptions=True,
        )

    for original_url, resolved_url in zip(pending_urls, fetched_results):
        if isinstance(resolved_url, Exception):
            resolved_results[original_url] = original_url
        else:
            final_url = resolved_url or original_url
            resolved_results[original_url] = final_url
            redirect_resolved_count += int(final_url != original_url)

    return resolved_results, redirect_resolved_count


def extract_all_urls(text: str, msg_obj: Any = None) -> set[str]:
    all_urls = set()
    if msg_obj is not None and hasattr(msg_obj, "get_entities_text"):
        for ent, text_part in msg_obj.get_entities_text():
            if isinstance(ent, MessageEntityTextUrl):
                all_urls.add(unquote(ent.url))
            elif isinstance(ent, MessageEntityUrl):
                all_urls.add(unquote(text_part))

        reply_markup = getattr(msg_obj, "reply_markup", None)
        if reply_markup:
            for row in getattr(reply_markup, "rows", []):
                for button in getattr(row, "buttons", []):
                    if isinstance(button, KeyboardButtonUrl):
                        all_urls.add(unquote(button.url))

        media = getattr(msg_obj, "media", None)
        webpage = getattr(media, "webpage", None)
        if webpage and getattr(webpage, "url", None):
            all_urls.add(unquote(webpage.url))

    for url in URL_EXTRACTOR.find_urls(text or ""):
        all_urls.add(unquote(url))

    return all_urls


def remove_urls_from_text(text: str) -> str:
    cleaned = text
    url_candidates = set(extract_urls_from_text_fragment(text))
    url_candidates.update(re.findall(r"https?://[^\s]+", text))

    for candidate in sorted(url_candidates, key=len, reverse=True):
        cleaned = cleaned.replace(candidate, " ")
        cleaned = cleaned.replace(unquote(candidate), " ")

    return cleaned


def resolve_netdisk_links(
    original_lines: List[str],
    resolved_urls: Dict[str, str],
    netdisk_map: List[Tuple[List[str], str]],
    valid_labels: List[str],
    intermediate_netdisk_domains: Dict[str, List[str]],
    hint_name: str | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    links: Dict[str, List[Dict[str, Any]]] = {}

    for raw_url, resolved_url in resolved_urls.items():
        name = get_netdisk_name_for_url(resolved_url, netdisk_map)
        link_url = resolved_url
        if not name:
            name = get_netdisk_name_for_url(raw_url, netdisk_map)
            link_url = raw_url
        if not name:
            name = get_profile_netdisk_name_for_url(resolved_url, intermediate_netdisk_domains)
            link_url = resolved_url
        if not name:
            name = get_profile_netdisk_name_for_url(raw_url, intermediate_netdisk_domains)
            link_url = raw_url
        if not name and hint_name:
            name = hint_name
            link_url = raw_url
        if not name:
            continue

        label = _sanitize_link_label(
            find_link_label(original_lines, raw_url, resolved_url, valid_labels),
            netdisk_name=name,
        )
        links.setdefault(name, [])

        link_item: Dict[str, Any] = {"label": label, "url": link_url}
        if link_url != raw_url:
            link_item["original_url"] = raw_url

        if not any(item["url"] == link_url for item in links[name]):
            links[name].append(link_item)

    return links


def normalize_tag_text(tag: str) -> str | None:
    cleaned = remove_urls_from_text(tag)
    cleaned = cleaned.strip().strip("#").strip("[]【】()（）")
    cleaned = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", cleaned)

    if not cleaned:
        return None
    if cleaned.lower().startswith(("http://", "https://", "www.")):
        return None
    if len(cleaned) > 20:
        return None
    if re.fullmatch(r"\d{4,}", cleaned):
        return None

    return cleaned


def append_tag(tags: List[str], tag: str) -> None:
    normalized = normalize_tag_text(tag)
    if normalized and normalized not in tags:
        tags.append(normalized)


def add_keyword_tags(tags: List[str], text: str, profile: Dict[str, Any]) -> None:
    for region in profile.get("regions", []):
        if region in text:
            append_tag(tags, region)

    for keyword in profile.get("course_keywords", []):
        if keyword in text:
            append_tag(tags, keyword)

    for category in profile.get("categories", []):
        if category in text:
            append_tag(tags, category)


def extract_message_tags(text: str, profile: Dict[str, Any]) -> List[str]:
    tags: List[str] = []

    for hashtag in HASHTAG_PATTERN.findall(text):
        append_tag(tags, hashtag)

    for block in BRACKET_TAG_PATTERN.findall(text):
        cleaned_block = normalize_tag_text(block)
        if not cleaned_block:
            continue

        parts = [part for part in re.split(r"[、,，/|｜+＋&＆·\s]+", cleaned_block) if part.strip()]
        if len(parts) > 1:
            for part in parts:
                append_tag(tags, part)
        else:
            append_tag(tags, cleaned_block)

    add_keyword_tags(tags, text, profile)
    return tags


def clean_title_text(title: str) -> str:
    cleaned = remove_urls_from_text(title)
    cleaned = HASHTAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"@[A-Za-z0-9_]+", " ", cleaned)

    while True:
        updated = re.sub(r"^[【\[]([A-Za-z0-9]{1,6})[】\]]\s*", "", cleaned)
        if updated == cleaned:
            break
        cleaned = updated

    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", cleaned)
    return cleaned.strip()


def find_link_label(original_lines: List[str], raw_url: str, resolved_url: str, valid_labels: List[str]) -> str | None:
    for index, line in enumerate(original_lines):
        stripped = line.strip()
        direct_label_match = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9\s]+)\s*[:：]\s*https?://", stripped)
        if direct_label_match:
            extracted_label = direct_label_match.group(1).strip()
            longest_label = None
            for valid_label in valid_labels:
                if valid_label in extracted_label:
                    if longest_label is None or len(valid_label) > len(longest_label):
                        longest_label = valid_label
            if longest_label:
                return longest_label

        matched_link_text = None
        if raw_url and raw_url in line:
            matched_link_text = raw_url
        elif resolved_url and resolved_url in line:
            matched_link_text = resolved_url

        if not matched_link_text:
            continue

        label_match = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9]+)\s*[:：]", stripped)
        if label_match:
            extracted_label = label_match.group(1)
            longest_label = None
            for valid_label in valid_labels:
                if valid_label in extracted_label:
                    if longest_label is None or len(valid_label) > len(longest_label):
                        longest_label = valid_label
            if longest_label:
                return longest_label

        url_index = line.find(matched_link_text)
        if url_index > 0:
            before_url = line[:url_index].strip()
            for valid_label in valid_labels:
                if before_url.endswith(valid_label):
                    return valid_label

        if index > 0:
            previous_line = original_lines[index - 1].strip()
            if len(previous_line) < 10:
                for valid_label in valid_labels:
                    if valid_label in previous_line:
                        return valid_label

    return None


def clean_description_text(description: str) -> str:
    seen = set()
    lines = []

    for raw_line in description.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        line = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", line)
        if not line or re.fullmatch(r"[.。,，:：;；|/\-]+", line):
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)

    return "\n".join(lines)


def _strip_leading_text_markers(line: str) -> str:
    cleaned = re.sub(r"^[^\u4e00-\u9fa5A-Za-z0-9@#]+", "", line or "")
    return cleaned.strip()


@lru_cache(maxsize=256)
def _field_prefix_pattern(alias_text: str) -> re.Pattern[str] | None:
    cleaned_alias = "".join(char for char in str(alias_text or "").strip() if not char.isspace())
    if not cleaned_alias:
        return None

    joined_alias = r"[\s\u3000]*".join(re.escape(char) for char in cleaned_alias)
    wrapper = re.escape(MOVIE_FIELD_WRAPPER_CHARS)
    return re.compile(
        rf"^(?:[{wrapper}]*){joined_alias}(?:[{wrapper}]*)"
        rf"(?:(?:[:：])\s*(?P<value>.*)|(?P<marker>[^\u4e00-\u9fa5A-Za-z0-9]+)?$)",
        re.IGNORECASE,
    )


def _find_prefixed_alias(line: str, aliases: List[str]) -> Tuple[str | None, str | None]:
    candidate = _strip_leading_text_markers(line)
    if not candidate:
        return None, None

    for alias in aliases:
        alias_text = str(alias or "").strip()
        if not alias_text:
            continue

        pattern = _field_prefix_pattern(alias_text)
        if pattern is None:
            continue

        match = pattern.match(candidate)
        if match:
            return alias_text, (match.group("value") or "").strip()

    return None, None


def _match_prefixed_field(line: str, aliases: List[str]) -> str | None:
    _, value = _find_prefixed_alias(line, aliases)
    return value


def _profile_aliases(profile: Dict[str, Any], key: str, default: List[str]) -> List[str]:
    aliases = profile.get(key)
    if not aliases:
        return list(default)
    return [str(alias).strip() for alias in aliases if str(alias).strip()]


def _merge_alias_lists(*alias_groups: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()

    for aliases in alias_groups:
        for alias in aliases:
            normalized = str(alias or "").strip()
            if not normalized:
                continue
            marker = normalized.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(normalized)

    return merged


def _clean_metadata_value(field_name: str, value: str) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_leading_text_markers(value or "")).strip()
    if field_name in {"channel", "group", "bot"} and cleaned.startswith("@"):
        return cleaned
    return clean_title_text(cleaned)


def _extract_movie_category_tags(text: str) -> List[str]:
    tags: List[str] = []
    for keyword in MOVIE_CATEGORY_HINTS:
        if keyword in text:
            append_tag(tags, keyword)
    return tags


def _normalize_movie_identity(text: str) -> str:
    cleaned = clean_title_text(text)
    cleaned = MOVIE_YEAR_PATTERN.sub(" ", cleaned)
    cleaned = MOVIE_PROGRESS_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"[（(]\d+\s*集[)）]", " ", cleaned)
    cleaned = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", cleaned)
    return cleaned.casefold()


def _extract_movie_size(line: str) -> str | None:
    size_match = MOVIE_SIZE_PATTERN.search(line or "")
    if not size_match:
        return None
    return re.sub(r"\s+", " ", size_match.group("size")).strip()


def _clean_movie_title_candidate(raw_title: str) -> Tuple[str, List[str], List[str]]:
    title_text = clean_title_text(_strip_leading_text_markers(raw_title))
    title_text = remove_urls_from_text(title_text)
    title_text = re.sub(r"\s+", " ", title_text).strip()

    description_lines: List[str] = []
    title_tags: List[str] = []

    category_match = MOVIE_TITLE_CATEGORY_PATTERN.search(title_text)
    if category_match:
        append_tag(title_tags, category_match.group(1))
        title_text = title_text[: category_match.start()].strip()

    actor_match = MOVIE_ACTOR_SUFFIX_PATTERN.search(title_text)
    if actor_match and re.search(r"(\(\d+\s*集\)|（\d+\s*集）|短剧|S\d{1,2}E\d{1,3})", raw_title, re.IGNORECASE):
        actors = actor_match.group("actors").replace("＆", "&").replace("／", "/")
        actors = re.sub(r"\s*[&/]\s*", " / ", actors)
        description_lines.append(f"主演: {actors}")
        title_text = title_text[: actor_match.start()].strip()

    for pattern in MOVIE_TITLE_TECH_PATTERNS:
        title_text = pattern.sub(" ", title_text)
    title_text = MOVIE_SIZE_PATTERN.sub(" ", title_text)
    title_text = re.sub(r"[【】\[\]]", " ", title_text)
    title_text = re.sub(r"\s+", " ", title_text).strip()
    title_text = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", title_text)

    return title_text.strip(), description_lines, title_tags


def _extract_movie_tags_from_line(line: str, title: str) -> List[str]:
    tags = extract_message_tags(line, {"regions": [], "course_keywords": [], "categories": []})
    for category_tag in _extract_movie_category_tags(line):
        append_tag(tags, category_tag)

    title_identity = _normalize_movie_identity(title)
    filtered_tags: List[str] = []
    for tag in tags:
        normalized_tag = normalize_tag_text(tag)
        if not normalized_tag:
            continue
        tag_identity = _normalize_movie_identity(normalized_tag)
        if title_identity and tag_identity and tag_identity == title_identity:
            continue
        append_tag(filtered_tags, normalized_tag)
    return filtered_tags


def _find_movie_title_line(
    original_lines: List[str],
    profile: Dict[str, Any],
    noise_aliases: List[str],
    description_aliases: List[str],
    tag_aliases: List[str],
    size_aliases: List[str],
) -> Tuple[int | None, str]:
    title_aliases = _profile_aliases(profile, "title_fields", ["名称", "标题", "片名", "剧名"])

    for index, raw_line in enumerate(original_lines):
        line = raw_line.strip()
        if not line:
            continue
        explicit_title = _match_prefixed_field(line, title_aliases)
        if explicit_title:
            return index, explicit_title

    for index, raw_line in enumerate(original_lines):
        line = _strip_leading_text_markers(raw_line.strip())
        if not line:
            continue
        if extract_urls_from_text_fragment(line):
            continue
        if _match_prefixed_field(line, description_aliases) is not None:
            continue
        if _match_prefixed_field(line, tag_aliases) is not None:
            continue
        if _match_prefixed_field(line, size_aliases) is not None:
            continue
        if _match_prefixed_field(line, noise_aliases) is not None:
            continue
        return index, line

    return None, ""


def _is_movie_noise_line(line: str, noise_aliases: List[str], filter_patterns: List[str]) -> bool:
    candidate = _strip_leading_text_markers(line)
    if not candidate:
        return True
    if _match_prefixed_field(candidate, noise_aliases) is not None:
        return True
    if candidate.startswith("@") and " " not in candidate:
        return True
    if any(re.search(pattern, candidate, re.IGNORECASE) for pattern in filter_patterns):
        return True
    return any(pattern.search(candidate) for pattern in MOVIE_NOISE_PATTERNS)


def _normalize_movie_description_line(line: str) -> str:
    cleaned = remove_urls_from_text(line)
    cleaned = HASHTAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"@[A-Za-z0-9_]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", cleaned)
    return cleaned.strip()


def _append_movie_line(lines: List[str], line: str) -> None:
    normalized = _normalize_movie_description_line(line)
    if normalized and normalized not in lines:
        lines.append(normalized)


def _is_movie_tech_line(line: str) -> bool:
    candidate = _normalize_movie_description_line(line)
    if not candidate or len(candidate) > 120:
        return False

    matches = MOVIE_TECH_LINE_TOKENS.findall(candidate)
    if len(matches) < 2:
        return False

    remainder = MOVIE_TECH_LINE_TOKENS.sub(" ", candidate)
    remainder = MOVIE_SIZE_PATTERN.sub(" ", remainder)
    remainder = re.sub(r"[\s\-|:：,，;；·+&/（）()【】\[\].]+", "", remainder)
    return len(remainder) <= 12


def _matches_prefixed_aliases(line: str, *alias_groups: List[str]) -> bool:
    for aliases in alias_groups:
        if aliases and _match_prefixed_field(line, aliases) is not None:
            return True
    return False


def _is_movie_variant_descriptor_line(original_lines: List[str], line_index: int, title_line_index: int | None) -> bool:
    if line_index < 0 or line_index >= len(original_lines):
        return False
    if line_index == title_line_index:
        return False

    line = original_lines[line_index].strip()
    if not line or extract_urls_from_text_fragment(line):
        return False

    previous_has_url = line_index > 0 and bool(extract_urls_from_text_fragment(original_lines[line_index - 1]))
    next_has_url = line_index + 1 < len(original_lines) and bool(
        extract_urls_from_text_fragment(original_lines[line_index + 1])
    )
    if not previous_has_url and not next_has_url:
        return False

    candidate = _normalize_movie_description_line(line)
    if not candidate:
        return False
    if MOVIE_VARIANT_START_PATTERN.search(candidate):
        return True
    if _extract_movie_size(candidate) and len(candidate) <= 48:
        return True
    return False


def _find_link_line_index(original_lines: List[str], link_item: Dict[str, Any]) -> int | None:
    url_candidates = [str(link_item.get("original_url") or "").strip(), str(link_item.get("url") or "").strip()]
    for index, line in enumerate(original_lines):
        if any(candidate and candidate in line for candidate in url_candidates):
            return index
    return None


def _normalize_netdisk_label_marker(value: str) -> str:
    cleaned = clean_title_text(value or "")
    cleaned = re.sub(r"[\s\-_./]+", "", cleaned)
    cleaned = re.sub(r"(?:网盘|云盘)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"盘$", "", cleaned)
    return cleaned.casefold()


def _get_netdisk_label_markers(netdisk_name: str) -> set[str]:
    aliases = {netdisk_name}
    aliases.update(DEFAULT_NETDISK_HINT_ALIASES.get(netdisk_name, []))

    base_name = re.sub(r"(?:网盘|云盘)$", "", netdisk_name or "", flags=re.IGNORECASE)
    if base_name:
        aliases.add(base_name)

    markers = {
        _normalize_netdisk_label_marker(alias)
        for alias in aliases
        if _normalize_netdisk_label_marker(alias)
    }
    return markers


def _is_redundant_netdisk_label(label: str, netdisk_name: str | None) -> bool:
    if not netdisk_name:
        return False
    normalized_label = _normalize_netdisk_label_marker(label)
    if not normalized_label:
        return True
    return normalized_label in _get_netdisk_label_markers(netdisk_name)


def _looks_like_sentence_link_label(label: str) -> bool:
    candidate = _normalize_movie_description_line(label)
    if not candidate:
        return False
    if _extract_movie_size(candidate) and len(candidate) <= 24:
        return False
    if _is_movie_tech_line(candidate):
        return False
    if MOVIE_VARIANT_START_PATTERN.search(candidate):
        return False
    if len(candidate) >= 18 and re.search(r"[，。；！？]", candidate):
        return True
    if len(candidate) >= 32 and re.search(r"[：:]", candidate):
        return True
    return len(candidate) >= 36 and candidate.count("，") >= 1


def _sanitize_link_label(
    label: str | None,
    *,
    netdisk_name: str | None = None,
    noise_aliases: List[str] | None = None,
    filter_patterns: List[str] | None = None,
    reject_sentence_like: bool = False,
) -> str | None:
    candidate = _normalize_movie_description_line(label or "")
    if not candidate:
        return None
    if netdisk_name and _is_redundant_netdisk_label(candidate, netdisk_name):
        return None
    if noise_aliases is not None and _is_movie_noise_line(candidate, noise_aliases, filter_patterns or []):
        return None
    if reject_sentence_like and _looks_like_sentence_link_label(candidate):
        return None
    return candidate


def _filter_movie_description_groups(
    *,
    synopsis_lines: List[str],
    freeform_description_lines: List[str],
    fallback_description_lines: List[str],
    noise_aliases: List[str],
    filter_patterns: List[str],
) -> List[str]:
    for group in (synopsis_lines, freeform_description_lines, fallback_description_lines):
        if not group:
            continue
        filtered_lines = [
            _normalize_movie_description_line(line)
            for line in group
            if _normalize_movie_description_line(line)
            and not _is_movie_noise_line(_normalize_movie_description_line(line), noise_aliases, filter_patterns)
        ]
        if filtered_lines:
            return filtered_lines
    return []


def _derive_movie_link_label(
    original_lines: List[str],
    *,
    netdisk_name: str,
    title: str,
    title_line_index: int | None,
    link_index: int,
    description_aliases: List[str],
    tag_aliases: List[str],
    size_aliases: List[str],
    noise_aliases: List[str],
    filter_patterns: List[str],
) -> str | None:
    link_aliases = MOVIE_RESOURCE_FIELD_ALIASES
    line = original_lines[link_index].strip()
    inline_label = None
    if not _matches_prefixed_aliases(line, link_aliases):
        inline_label = _normalize_movie_description_line(remove_urls_from_text(line))
    if inline_label and inline_label not in set(link_aliases):
        sanitized_inline_label = _sanitize_link_label(
            inline_label,
            netdisk_name=netdisk_name,
            noise_aliases=noise_aliases,
            filter_patterns=filter_patterns,
            reject_sentence_like=True,
        )
        if sanitized_inline_label:
            return sanitized_inline_label

    for offset in (1, 2):
        previous_index = link_index - offset
        if previous_index < 0:
            break
        previous_line = original_lines[previous_index].strip()
        if not previous_line or extract_urls_from_text_fragment(previous_line):
            continue
        if _matches_prefixed_aliases(
            previous_line,
            link_aliases,
            description_aliases,
            tag_aliases,
            size_aliases,
            noise_aliases,
        ):
            continue

        candidate = _normalize_movie_description_line(previous_line)
        if not candidate:
            continue
        if previous_index == title_line_index:
            variant_match = MOVIE_VARIANT_START_PATTERN.search(candidate)
            if variant_match:
                candidate = _normalize_movie_description_line(candidate[variant_match.start() :].strip())
                if candidate:
                    return candidate
            candidate_title, _, _ = _clean_movie_title_candidate(candidate)
            if candidate_title and candidate.startswith(candidate_title):
                candidate = _normalize_movie_description_line(candidate[len(candidate_title) :].strip())
        if candidate:
            sanitized_candidate = _sanitize_link_label(
                candidate,
                netdisk_name=netdisk_name,
                noise_aliases=noise_aliases,
                filter_patterns=filter_patterns,
                reject_sentence_like=True,
            )
            if sanitized_candidate:
                return sanitized_candidate

    return None


def _enrich_movie_links(
    links: Dict[str, List[Dict[str, Any]]],
    *,
    original_lines: List[str],
    title: str,
    title_line_index: int | None,
    message_size: str | None,
    description_aliases: List[str],
    tag_aliases: List[str],
    size_aliases: List[str],
    noise_aliases: List[str],
    filter_patterns: List[str],
) -> None:
    total_links = sum(len(items) for items in links.values())
    for name, link_items in links.items():
        for link_item in link_items:
            existing_label = _sanitize_link_label(
                link_item.get("label"),
                netdisk_name=name,
                noise_aliases=noise_aliases,
                filter_patterns=filter_patterns,
            )
            link_item["label"] = existing_label
            if existing_label:
                continue
            link_index = _find_link_line_index(original_lines, link_item)
            if link_index is None:
                continue
            variant_label = _derive_movie_link_label(
                original_lines,
                netdisk_name=name,
                title=title,
                title_line_index=title_line_index,
                link_index=link_index,
                description_aliases=description_aliases,
                tag_aliases=tag_aliases,
                size_aliases=size_aliases,
                noise_aliases=noise_aliases,
                filter_patterns=filter_patterns,
            )
            if variant_label:
                link_item["label"] = variant_label

    if total_links == 1 and message_size:
        for name, link_items in links.items():
            for link_item in link_items:
                link_item["label"] = _sanitize_link_label(message_size, netdisk_name=name) or message_size


def _parse_movie_message_fields(
    text: str,
    original_lines: List[str],
    profile: Dict[str, Any],
    links: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    metadata_aliases = profile.get("metadata", {})
    description_aliases = _merge_alias_lists(
        _profile_aliases(profile, "movie_description_fields", ["描述", "简介", "剧情", "介绍"]),
        ["描述", "简介", "剧情", "介绍"],
    )
    tag_aliases = _merge_alias_lists(
        _profile_aliases(profile, "movie_tag_fields", ["标签"]),
        ["标签"],
    )
    size_aliases = _merge_alias_lists(
        _profile_aliases(profile, "movie_size_fields", ["大小"]),
        ["大小"],
    )
    noise_aliases = _merge_alias_lists(
        _profile_aliases(
            profile,
            "movie_noise_fields",
            ["来自", "来源", "频道", "群组", "投稿", "投稿人", "搜索", "搜资源", "社区", "机场", "公费服"],
        ),
        MOVIE_EXTRA_NOISE_ALIASES,
    )
    movie_meta_aliases = _merge_alias_lists(
        _profile_aliases(
            profile,
            "movie_meta_fields",
            ["评分", "TMDB评分", "豆瓣评分", "类型", "地区", "语言", "画质", "质量", "片长", "主演", "导演", "更新", "集数"],
        ),
        MOVIE_FALLBACK_META_ALIASES,
        ["画质", "质量"],
    )
    fallback_meta_aliases = _merge_alias_lists(
        _profile_aliases(profile, "movie_fallback_meta_fields", MOVIE_FALLBACK_META_ALIASES),
        MOVIE_FALLBACK_META_ALIASES,
    )
    filter_patterns = profile.get("filter_patterns", [])

    title_line_index, raw_title = _find_movie_title_line(
        original_lines,
        profile,
        noise_aliases,
        description_aliases,
        tag_aliases,
        size_aliases,
    )
    title, title_fallback_lines, title_tags = _clean_movie_title_candidate(raw_title)
    if not title and raw_title:
        title = clean_title_text(raw_title)

    source = ""
    channel = ""
    group = ""
    bot = ""
    message_size: str | None = None
    synopsis_lines: List[str] = []
    freeform_description_lines: List[str] = []
    fallback_description_lines: List[str] = list(title_fallback_lines)
    explicit_description_found = False
    collecting_description = False
    tags = extract_message_tags(text, {"regions": [], "course_keywords": [], "categories": profile.get("categories", [])})
    for title_tag in title_tags:
        append_tag(tags, title_tag)

    for index, raw_line in enumerate(original_lines):
        line = raw_line.strip()
        if not line or index == title_line_index:
            continue

        stripped_line = _strip_leading_text_markers(line)
        if not stripped_line:
            continue

        metadata_handled = False
        for field_name, aliases in metadata_aliases.items():
            field_value = _match_prefixed_field(stripped_line, aliases)
            if field_value is None:
                continue
            cleaned_value = _clean_metadata_value(field_name, field_value)
            if field_name == "source":
                source = cleaned_value
            elif field_name == "channel":
                channel = cleaned_value
            elif field_name == "group":
                group = cleaned_value
            elif field_name == "bot":
                bot = cleaned_value
            metadata_handled = True
            break
        if metadata_handled:
            continue

        size_value = _match_prefixed_field(stripped_line, size_aliases)
        if size_value is not None:
            message_size = _extract_movie_size(size_value) or _extract_movie_size(stripped_line) or message_size
            collecting_description = False
            continue

        matched_tag_alias, tag_value = _find_prefixed_alias(stripped_line, tag_aliases)
        if matched_tag_alias is not None:
            for tag in _extract_movie_tags_from_line(tag_value or "", title):
                append_tag(tags, tag)
            collecting_description = False
            continue

        if _match_prefixed_field(stripped_line, MOVIE_RESOURCE_FIELD_ALIASES) is not None:
            collecting_description = False
            continue
        if extract_urls_from_text_fragment(stripped_line):
            collecting_description = False
            continue
        if _is_movie_noise_line(stripped_line, noise_aliases, filter_patterns):
            collecting_description = False
            continue

        matched_description_alias, description_value = _find_prefixed_alias(stripped_line, description_aliases)
        if matched_description_alias is not None:
            explicit_description_found = True
            collecting_description = True
            if description_value and not _is_movie_noise_line(description_value, noise_aliases, filter_patterns):
                cleaned_description = _normalize_movie_description_line(description_value)
                if cleaned_description and not _is_movie_tech_line(cleaned_description):
                    if not title or _normalize_movie_identity(cleaned_description) != _normalize_movie_identity(title):
                        _append_movie_line(synopsis_lines, cleaned_description)
            continue

        kept_meta_alias, kept_meta_value = _find_prefixed_alias(stripped_line, movie_meta_aliases)
        if kept_meta_alias is not None:
            collecting_description = False
            normalized_value = _normalize_movie_description_line(kept_meta_value or "")
            if normalized_value:
                if kept_meta_alias in fallback_meta_aliases:
                    _append_movie_line(fallback_description_lines, f"{kept_meta_alias}: {normalized_value}")
                if kept_meta_alias == "类型":
                    for tag in _extract_movie_category_tags(normalized_value):
                        append_tag(tags, tag)
            continue

        if _is_movie_variant_descriptor_line(original_lines, index, title_line_index) or _is_movie_tech_line(stripped_line):
            collecting_description = False
            continue

        normalized_line = _normalize_movie_description_line(stripped_line)
        if not normalized_line:
            continue
        if title and _normalize_movie_identity(normalized_line) == _normalize_movie_identity(title):
            continue

        if collecting_description:
            _append_movie_line(synopsis_lines, normalized_line)
            continue
        if explicit_description_found:
            continue

        _append_movie_line(freeform_description_lines, normalized_line)

    _enrich_movie_links(
        links,
        original_lines=original_lines,
        title=title,
        title_line_index=title_line_index,
        message_size=message_size,
        description_aliases=description_aliases,
        tag_aliases=tag_aliases,
        size_aliases=size_aliases,
        noise_aliases=noise_aliases,
        filter_patterns=filter_patterns,
    )

    filtered_tags: List[str] = []
    title_identity = _normalize_movie_identity(title)
    for tag in tags:
        normalized_tag = normalize_tag_text(tag)
        if not normalized_tag:
            continue
        tag_identity = _normalize_movie_identity(normalized_tag)
        if title_identity and tag_identity and tag_identity == title_identity:
            continue
        append_tag(filtered_tags, normalized_tag)

    description_lines = _filter_movie_description_groups(
        synopsis_lines=synopsis_lines,
        freeform_description_lines=freeform_description_lines,
        fallback_description_lines=fallback_description_lines,
        noise_aliases=noise_aliases,
        filter_patterns=filter_patterns,
    )
    description = clean_description_text("\n".join(description_lines))
    add_keyword_tags(filtered_tags, f"{title}\n{description}", profile)

    return {
        "title": title,
        "description": description,
        "links": links,
        "tags": filtered_tags,
        "source": source,
        "channel": channel,
        "group_name": group,
        "bot": bot,
    }


def _parse_movie_message_fields_legacy(
    text: str,
    original_lines: List[str],
    profile: Dict[str, Any],
    links: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return _parse_movie_message_fields(text, original_lines, profile, links)

    metadata_aliases = profile.get("metadata", {})
    description_aliases = _profile_aliases(profile, "movie_description_fields", ["描述", "简介", "剧情", "介绍"])
    tag_aliases = _profile_aliases(profile, "movie_tag_fields", ["标签"])
    size_aliases = _profile_aliases(profile, "movie_size_fields", ["大小"])
    noise_aliases = _profile_aliases(profile, "movie_noise_fields", ["来自", "频道", "群组", "投稿", "搜索", "机场", "公费服"])
    movie_meta_aliases = _profile_aliases(
        profile,
        "movie_meta_fields",
        ["评分", "TMDB评分", "豆瓣评分", "类型", "地区", "语言", "画质", "质量", "片长", "主演", "导演", "更新", "简介"],
    )
    filter_patterns = profile.get("filter_patterns", [])

    title_line_index, raw_title = _find_movie_title_line(
        original_lines,
        profile,
        noise_aliases,
        description_aliases,
        tag_aliases,
        size_aliases,
    )
    title, title_description_lines, title_tags = _clean_movie_title_candidate(raw_title)
    if not title and raw_title:
        title = clean_title_text(raw_title)
    source = ""
    channel = ""
    group = ""
    bot = ""
    message_size: str | None = None
    description_lines: List[str] = list(title_description_lines)
    tags = extract_message_tags(text, {"regions": [], "course_keywords": [], "categories": profile.get("categories", [])})
    for title_tag in title_tags:
        append_tag(tags, title_tag)

    for index, raw_line in enumerate(original_lines):
        line = raw_line.strip()
        if not line:
            continue
        if index == title_line_index:
            continue

        stripped_line = _strip_leading_text_markers(line)
        if not stripped_line:
            continue

        metadata_handled = False
        for field_name, aliases in metadata_aliases.items():
            field_value = _match_prefixed_field(stripped_line, aliases)
            if field_value is None:
                continue
            cleaned_value = _clean_metadata_value(field_name, field_value)
            if field_name == "source":
                source = cleaned_value
            elif field_name == "channel":
                channel = cleaned_value
            elif field_name == "group":
                group = cleaned_value
            elif field_name == "bot":
                bot = cleaned_value
            metadata_handled = True
            break
        if metadata_handled:
            continue

        size_value = _match_prefixed_field(stripped_line, size_aliases)
        if size_value is not None:
            message_size = _extract_movie_size(size_value) or _extract_movie_size(stripped_line) or message_size
            continue

        tag_value = None
        for alias in tag_aliases:
            tag_value = _match_prefixed_field(stripped_line, [alias])
            if tag_value is not None:
                break
        if tag_value is not None:
            for tag in _extract_movie_tags_from_line(tag_value, title):
                append_tag(tags, tag)
            continue

        if extract_urls_from_text_fragment(stripped_line):
            continue
        if _is_movie_noise_line(stripped_line, noise_aliases, filter_patterns):
            continue

        description_value = None
        for alias in description_aliases:
            description_value = _match_prefixed_field(stripped_line, [alias])
            if description_value is not None:
                break
        if description_value is not None:
            if not _is_movie_noise_line(description_value, noise_aliases, filter_patterns):
                cleaned_description = _normalize_movie_description_line(description_value)
                if cleaned_description:
                    description_lines.append(cleaned_description)
            continue

        kept_meta_value = None
        kept_meta_alias = None
        for alias in movie_meta_aliases:
            field_value = _match_prefixed_field(stripped_line, [alias])
            if field_value is not None:
                kept_meta_alias = alias
                kept_meta_value = field_value
                break
        if kept_meta_value is not None:
            normalized_value = _normalize_movie_description_line(kept_meta_value)
            if normalized_value:
                description_lines.append(f"{kept_meta_alias}: {normalized_value}")
                if kept_meta_alias == "类型":
                    for tag in _extract_movie_category_tags(normalized_value):
                        append_tag(tags, tag)
            continue

        if _is_movie_variant_descriptor_line(original_lines, index, title_line_index):
            continue

        normalized_line = _normalize_movie_description_line(stripped_line)
        if not normalized_line:
            continue
        if title and _normalize_movie_identity(normalized_line) == _normalize_movie_identity(title):
            continue
        description_lines.append(normalized_line)

    _enrich_movie_links(
        links,
        original_lines=original_lines,
        title=title,
        title_line_index=title_line_index,
        message_size=message_size,
        description_aliases=description_aliases,
        tag_aliases=tag_aliases,
        size_aliases=size_aliases,
        noise_aliases=noise_aliases,
        filter_patterns=filter_patterns,
    )

    filtered_tags: List[str] = []
    title_identity = _normalize_movie_identity(title)
    for tag in tags:
        normalized_tag = normalize_tag_text(tag)
        if not normalized_tag:
            continue
        tag_identity = _normalize_movie_identity(normalized_tag)
        if title_identity and tag_identity and tag_identity == title_identity:
            continue
        append_tag(filtered_tags, normalized_tag)

    add_keyword_tags(filtered_tags, f"{title}\n" + "\n".join(description_lines), profile)
    description = clean_description_text("\n".join(description_lines))

    return {
        "title": title,
        "description": description,
        "links": links,
        "tags": filtered_tags,
        "source": source,
        "channel": channel,
        "group_name": group,
        "bot": bot,
    }


def infer_message_level_netdisk_name(original_lines: List[str], hint_aliases: List[Tuple[str, str]]) -> str | None:
    for raw_line in reversed(original_lines):
        line = raw_line.strip()
        if not line or extract_urls_from_text_fragment(line):
            continue
        if not is_hint_only_line(line, hint_aliases):
            continue

        inferred_name = infer_netdisk_name_from_text(line, hint_aliases)
        if inferred_name:
            return inferred_name

    return None


def is_line_message_title_candidate(
    title: str,
    valid_labels: List[str],
    hint_aliases: List[Tuple[str, str]],
) -> bool:
    normalized_title = clean_title_text(title)
    if not normalized_title:
        return False
    if any(normalized_title.casefold() == label.casefold() for label in valid_labels):
        return False
    if is_hint_only_line(normalized_title, hint_aliases):
        return False
    if len(normalized_title) >= 4:
        return True
    return bool(re.search(r"[\u4e00-\u9fa5]{2,}", normalized_title))


def extract_shared_message_fields(
    original_lines: List[str],
    profile: Dict[str, Any],
    excluded_line_indexes: set[int],
    hint_aliases: List[Tuple[str, str]],
) -> Tuple[str, str, str, str, str]:
    source = ""
    channel = ""
    group = ""
    bot = ""
    desc_lines_buffer: List[str] = []

    metadata_patterns = _build_metadata_patterns(profile.get("metadata", {}))
    ignored_prefixes = tuple(profile.get("ignored_line_prefixes", []))
    filter_patterns = profile.get("filter_patterns", [])
    label_pattern = re.compile(
        r"^(?:\u4e3b\u94fe|\u5907\u7528|\u666e\u7801|\u9ad8\u6e05|HDR|\u675c\u6bd4|IQ|[A-Za-z0-9]{1,10}\u7801?)$",
        re.IGNORECASE,
    )

    for index, raw_line in enumerate(original_lines):
        if index in excluded_line_indexes:
            continue

        line = raw_line.strip()
        if not line:
            continue

        cleaned_line_for_check = re.sub(r"^(?:\* |\- |\+ |> |>> |• |▪ |◉ |◆ )+", "", line).strip()
        if not cleaned_line_for_check:
            continue

        metadata_handled = False
        for pattern, field_name in metadata_patterns:
            match = pattern.match(cleaned_line_for_check)
            if not match:
                continue

            value = _clean_metadata_value(field_name, match.group(1))
            if field_name == "source":
                source = value
            elif field_name == "channel":
                channel = value
            elif field_name == "group":
                group = value
            elif field_name == "bot":
                bot = value
            metadata_handled = True
            break

        if metadata_handled:
            continue

        size_match = re.match(r"^[^\u4e00-\u9fa5A-Za-z0-9]*大小\s*[:：]?\s*(.+)$", cleaned_line_for_check)
        if size_match:
            size_info = size_match.group(1).strip()
            if re.search(r"(\d+\s*(GB|MB|TB|KB|G|M|T|K|B|字节|每集|单集|左右))", size_info, re.IGNORECASE):
                desc_lines_buffer.append(f"大小: {size_info}")
            continue

        if ignored_prefixes and cleaned_line_for_check.startswith(ignored_prefixes):
            continue
        if label_pattern.match(cleaned_line_for_check):
            continue
        if is_hint_only_line(cleaned_line_for_check, hint_aliases):
            continue

        cleaned_line = HASHTAG_PATTERN.sub("", cleaned_line_for_check)
        cleaned_line = re.sub(r"\bvia\s*\S+", " ", cleaned_line, flags=re.IGNORECASE)
        cleaned_line = re.sub(r"\bvia\s*$", " ", cleaned_line, flags=re.IGNORECASE)
        cleaned_line = re.sub(r"@[A-Za-z0-9_]+", " ", cleaned_line)
        cleaned_line = remove_urls_from_text(cleaned_line)
        cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip()
        cleaned_line = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", cleaned_line)

        if not cleaned_line:
            continue
        if any(re.search(pattern, cleaned_line, re.IGNORECASE) for pattern in filter_patterns):
            continue

        desc_lines_buffer.append(cleaned_line)

    description = clean_description_text("\n".join(desc_lines_buffer))
    return source, channel, group, bot, description


def _extract_hashtag_tags(text: str) -> List[str]:
    tags: List[str] = []
    for hashtag in HASHTAG_PATTERN.findall(text or ""):
        append_tag(tags, hashtag)
    return tags


def _get_platform_marker_tags(profile: Dict[str, Any]) -> set[str]:
    markers: set[str] = set()
    for _, alias in get_netdisk_hint_aliases(profile):
        normalized = normalize_tag_text(alias)
        if not normalized:
            continue
        if re.fullmatch(r"[A-Za-z0-9]{1,4}", normalized):
            markers.add(normalized.casefold())
    return markers


def _extract_course_list_platform_token(line: str) -> str | None:
    candidate = _strip_leading_text_markers(line)
    bracket_match = re.match(r"^[【\[](?P<token>[A-Za-z0-9]{1,4})[】\]]", candidate)
    if bracket_match:
        return bracket_match.group("token")

    plain_match = re.match(r"^(?P<token>[A-Za-z]{2,4})\b", candidate)
    if plain_match:
        return plain_match.group("token")

    return None


def _infer_course_list_line_hint(line: str, hint_aliases: List[Tuple[str, str]]) -> str | None:
    platform_token = _extract_course_list_platform_token(line)
    if not platform_token:
        return None
    return infer_netdisk_name_from_text(platform_token, hint_aliases)


def _clean_course_list_title(line: str, profile: Dict[str, Any]) -> str:
    title = clean_title_text(remove_urls_from_text(line))
    platform_token = _extract_course_list_platform_token(line)
    if platform_token:
        title = re.sub(rf"^{re.escape(platform_token)}\s+", "", title, flags=re.IGNORECASE)

    title = re.sub(r"[\u200b-\u200d\ufeff]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", title)

    platform_markers = _get_platform_marker_tags(profile)
    if title.casefold() in platform_markers:
        return ""
    return title


def _extract_course_list_title_tags(title: str, profile: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    excluded_markers = _get_platform_marker_tags(profile)

    for block in BRACKET_TAG_PATTERN.findall(title or ""):
        cleaned_block = normalize_tag_text(block)
        if not cleaned_block or cleaned_block.casefold() in excluded_markers:
            continue

        parts = [part for part in re.split(r"[、,，/|｜+＋&＆·\s]+", cleaned_block) if part.strip()]
        if len(parts) > 1:
            for part in parts:
                normalized_part = normalize_tag_text(part)
                if normalized_part and normalized_part.casefold() not in excluded_markers:
                    append_tag(tags, normalized_part)
        else:
            append_tag(tags, cleaned_block)

    add_keyword_tags(tags, title, profile)
    return tags


def _normalize_course_list_identity(title: str) -> str:
    cleaned = clean_title_text(title)
    cleaned = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", cleaned)
    return cleaned.casefold()


def _merge_links(
    existing_links: Dict[str, List[Dict[str, Any]]],
    incoming_links: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    merged = {name: [dict(item) for item in items] for name, items in existing_links.items()}
    for name, items in incoming_links.items():
        bucket = merged.setdefault(name, [])
        for item in items:
            if not any(existing.get("url") == item.get("url") for existing in bucket):
                bucket.append(dict(item))
    return merged


def _build_course_list_message_records(
    text: str,
    original_lines: List[str],
    profile: Dict[str, Any],
    netdisk_map: List[Tuple[List[str], str]],
    valid_labels: List[str],
    intermediate_netdisk_domains: Dict[str, List[str]],
    resolved_urls: Dict[str, str],
) -> List[Dict[str, Any]]:
    hint_aliases = get_netdisk_hint_aliases(profile)
    message_hint = infer_message_level_netdisk_name(original_lines, hint_aliases)
    global_tags = _extract_hashtag_tags(text)
    metadata_patterns = _build_metadata_patterns(profile.get("metadata", {}))

    source = ""
    channel = ""
    group = ""
    bot = ""
    merged_records: Dict[str, Dict[str, Any]] = {}
    record_order: List[str] = []

    for raw_line in original_lines:
        line = raw_line.strip()
        if not line:
            continue

        metadata_handled = False
        for pattern, field_name in metadata_patterns:
            match = pattern.match(line)
            if not match:
                continue

            value = _clean_metadata_value(field_name, match.group(1))
            if field_name == "source":
                source = value
            elif field_name == "channel":
                channel = value
            elif field_name == "group":
                group = value
            elif field_name == "bot":
                bot = value
            metadata_handled = True
            break
        if metadata_handled:
            continue

        line_urls = extract_urls_from_text_fragment(line)
        if not line_urls:
            continue

        title = _clean_course_list_title(line, profile)
        if not is_line_message_title_candidate(title, valid_labels, hint_aliases):
            continue

        line_resolved_urls = {
            normalized_url: resolved_urls.get(normalized_url, normalized_url)
            for normalized_url in (normalize_url(url) for url in line_urls)
            if normalized_url
        }
        line_hint = _infer_course_list_line_hint(line, hint_aliases) or message_hint
        line_links = resolve_netdisk_links(
            [line],
            line_resolved_urls,
            netdisk_map,
            valid_labels,
            intermediate_netdisk_domains,
            hint_name=line_hint,
        )
        if not line_links:
            continue

        record_tags = list(global_tags)
        for tag in _extract_course_list_title_tags(title, profile):
            append_tag(record_tags, tag)

        identity = _normalize_course_list_identity(title) or title
        record = {
            "title": title,
            "description": "",
            "links": line_links,
            "tags": record_tags,
            "source": source,
            "channel": channel,
            "group_name": group,
            "bot": bot,
        }
        existing_record = merged_records.get(identity)
        if existing_record is None:
            merged_records[identity] = record
            record_order.append(identity)
            continue

        existing_record["links"] = _merge_links(existing_record.get("links", {}), record["links"])
        for tag in record_tags:
            append_tag(existing_record["tags"], tag)
        for field_name, field_value in (
            ("source", source),
            ("channel", channel),
            ("group_name", group),
            ("bot", bot),
        ):
            if field_value and not existing_record.get(field_name):
                existing_record[field_name] = field_value

    return [merged_records[identity] for identity in record_order]


def build_line_message_records(
    text: str,
    original_lines: List[str],
    profile: Dict[str, Any],
    netdisk_map: List[Tuple[List[str], str]],
    valid_labels: List[str],
    intermediate_netdisk_domains: Dict[str, List[str]],
    resolved_urls: Dict[str, str],
) -> List[Dict[str, Any]]:
    if profile.get("content_mode") == COURSE_LIST_CONTENT_MODE:
        return _build_course_list_message_records(
            text,
            original_lines,
            profile,
            netdisk_map,
            valid_labels,
            intermediate_netdisk_domains,
            resolved_urls,
        )

    hint_aliases = get_netdisk_hint_aliases(profile)
    message_hint = infer_message_level_netdisk_name(original_lines, hint_aliases)
    line_records: List[Tuple[int, str, Dict[str, List[Dict[str, Any]]]]] = []

    for index, raw_line in enumerate(original_lines):
        line = raw_line.strip()
        if not line:
            continue

        line_urls = extract_urls_from_text_fragment(line)
        if not line_urls:
            continue

        title = clean_title_text(remove_urls_from_text(line))
        if not is_line_message_title_candidate(title, valid_labels, hint_aliases):
            continue

        line_resolved_urls = {
            normalized_url: resolved_urls.get(normalized_url, normalized_url)
            for normalized_url in (normalize_url(url) for url in line_urls)
            if normalized_url
        }
        line_links = resolve_netdisk_links(
            [line],
            line_resolved_urls,
            netdisk_map,
            valid_labels,
            intermediate_netdisk_domains,
            hint_name=message_hint,
        )
        if not line_links:
            continue

        line_records.append((index, title, line_links))

    if not line_records:
        return []

    excluded_line_indexes = {index for index, _, _ in line_records}
    source, channel, group, bot, shared_description = extract_shared_message_fields(
        original_lines,
        profile,
        excluded_line_indexes=excluded_line_indexes,
        hint_aliases=hint_aliases,
    )
    shared_tags = extract_message_tags(text, profile)

    parsed_records: List[Dict[str, Any]] = []
    for _, title, links in line_records:
        record_tags = list(shared_tags)
        add_keyword_tags(record_tags, f"{title}\n{shared_description}", profile)
        parsed_records.append(
            {
                "title": title,
                "description": shared_description,
                "links": links,
                "tags": record_tags,
                "source": source,
                "channel": channel,
                "group_name": group,
                "bot": bot,
            }
        )

    return parsed_records


def _build_title_pattern(title_fields: List[str]) -> re.Pattern[str]:
    return re.compile(rf"^(?:{'|'.join(re.escape(field) for field in title_fields)})\s*[:：]\s*(.+)$")


def _build_metadata_patterns(metadata_rules: Dict[str, List[str]]) -> List[Tuple[re.Pattern[str], str]]:
    patterns = []
    for field_name, aliases in metadata_rules.items():
        if not aliases:
            continue
        alias_group = "|".join(re.escape(alias) for alias in aliases)
        pattern = re.compile(rf"^(?:[^\u4e00-\u9fa5A-Za-z0-9]*\s*)?(?:{alias_group})\s*[:：]?\s*(.+)$")
        patterns.append((pattern, field_name))
    return patterns


async def parse_message_records(
    text: str,
    msg_obj: Any = None,
    channel_name: str | None = None,
    channel_id: int | None = None,
    parser_profile: str | None = None,
) -> Tuple[List[Dict[str, Any]], ParseDiagnostics]:
    rules = load_monitor_rules()
    profile_name = resolve_channel_profile_name(
        channel_name,
        rules,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    profile = resolve_channel_profile(
        channel_name,
        rules,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    resolver_config = get_redirect_resolver_config(rules)

    if profile.get("line_message_mode") != LINE_MESSAGE_MODE_PER_LINK:
        parsed_data, diagnostics = await parse_message_content(
            text,
            msg_obj=msg_obj,
            channel_name=channel_name,
            channel_id=channel_id,
            parser_profile=parser_profile,
        )
        return [parsed_data], diagnostics

    netdisk_map = _get_netdisk_map(rules)
    redirect_query_keys = rules.get("redirect_query_keys", [])
    valid_labels = profile.get("valid_labels", [])
    intermediate_netdisk_domains = profile.get("intermediate_netdisk_domains", {})
    original_lines = text.split("\n")

    diagnostics = ParseDiagnostics(profile_name=profile_name)
    all_urls = extract_all_urls(text, msg_obj)
    diagnostics.raw_url_count = len(all_urls)
    diagnostics.raw_url_samples = sorted(all_urls)[:3]
    resolved_urls, redirect_resolved_count = await resolve_message_urls(
        all_urls,
        netdisk_map,
        redirect_query_keys,
        resolver_config=resolver_config,
    )
    diagnostics.resolved_url_count = len(resolved_urls)
    diagnostics.redirect_resolved_count = redirect_resolved_count
    diagnostics.resolved_url_samples = list(dict.fromkeys(resolved_urls.values()))[:3]

    parsed_records = build_line_message_records(
        text,
        original_lines,
        profile,
        netdisk_map,
        valid_labels,
        intermediate_netdisk_domains,
        resolved_urls,
    )
    if parsed_records:
        diagnostics.extracted_link_count = sum(
            len(link_items)
            for record in parsed_records
            for link_items in record.get("links", {}).values()
        )
        return parsed_records, diagnostics

    parsed_data, diagnostics = await parse_message_content(
        text,
        msg_obj=msg_obj,
        channel_name=channel_name,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    return [parsed_data], diagnostics


async def parse_message_content(
    text: str,
    msg_obj: Any = None,
    channel_name: str | None = None,
    channel_id: int | None = None,
    parser_profile: str | None = None,
) -> Tuple[Dict[str, Any], ParseDiagnostics]:
    rules = load_monitor_rules()
    profile_name = resolve_channel_profile_name(
        channel_name,
        rules,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    profile = resolve_channel_profile(
        channel_name,
        rules,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    resolver_config = get_redirect_resolver_config(rules)
    netdisk_map = _get_netdisk_map(rules)
    redirect_query_keys = rules.get("redirect_query_keys", [])
    valid_labels = profile.get("valid_labels", [])
    intermediate_netdisk_domains = profile.get("intermediate_netdisk_domains", {})

    diagnostics = ParseDiagnostics(profile_name=profile_name)
    original_lines = text.split("\n")
    hint_aliases = get_netdisk_hint_aliases(profile)
    title = ""
    source = ""
    channel = ""
    group = ""
    bot = ""
    desc_lines_buffer: List[str] = []

    all_urls = extract_all_urls(text, msg_obj)
    diagnostics.raw_url_count = len(all_urls)
    diagnostics.raw_url_samples = sorted(all_urls)[:3]
    resolved_urls, redirect_resolved_count = await resolve_message_urls(
        all_urls,
        netdisk_map,
        redirect_query_keys,
        resolver_config=resolver_config,
    )
    diagnostics.resolved_url_count = len(resolved_urls)
    diagnostics.redirect_resolved_count = redirect_resolved_count
    diagnostics.resolved_url_samples = list(dict.fromkeys(resolved_urls.values()))[:3]
    message_hint = infer_message_level_netdisk_name(original_lines, hint_aliases)
    links = resolve_netdisk_links(
        original_lines,
        resolved_urls,
        netdisk_map,
        valid_labels,
        intermediate_netdisk_domains,
        hint_name=message_hint,
    )

    diagnostics.extracted_link_count = sum(len(items) for items in links.values())

    if profile.get("content_mode") == MOVIE_CONTENT_MODE:
        parsed_movie_data = _parse_movie_message_fields(
            text,
            original_lines,
            profile,
            links,
        )
        return parsed_movie_data, diagnostics

    title_pattern = _build_title_pattern(profile.get("title_fields", ["名称", "标题"]))
    title_line_index = None
    for index, raw_line in enumerate(original_lines):
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        title_match = title_pattern.match(stripped_line)
        if title_match:
            title = title_match.group(1).strip()
            title_line_index = index
            break

        title = stripped_line
        title_line_index = index
        break

    if title_line_index is None:
        return {
            "title": "",
            "description": "",
            "links": {},
            "tags": [],
            "source": "",
            "channel": "",
            "group_name": "",
            "bot": "",
        }, diagnostics

    lines_to_process = original_lines[:title_line_index] + original_lines[title_line_index + 1 :]
    tags = extract_message_tags("\n".join(original_lines), profile)
    title = clean_title_text(title)
    if not title:
        title = clean_title_text(original_lines[title_line_index]) or original_lines[title_line_index].strip()

    metadata_patterns = _build_metadata_patterns(profile.get("metadata", {}))
    ignored_prefixes = tuple(profile.get("ignored_line_prefixes", []))
    filter_patterns = profile.get("filter_patterns", [])
    label_pattern = re.compile(r"^(主链|备用|普码|高清|HDR|杜比|IQ|[A-Za-z0-9]{1,10}码)$", re.IGNORECASE)

    for raw_line in lines_to_process:
        line = raw_line.strip()
        if not line:
            continue

        cleaned_line_for_check = re.sub(r"^(?:\* |\- |\+ |> |>> |• |▪ |► |◆ )+", "", line).strip()
        if not cleaned_line_for_check:
            continue

        metadata_handled = False
        for pattern, field_name in metadata_patterns:
            match = pattern.match(cleaned_line_for_check)
            if not match:
                continue

            value = clean_title_text(match.group(1))
            if field_name == "source":
                source = value
            elif field_name == "channel":
                channel = value
            elif field_name == "group":
                group = value
            elif field_name == "bot":
                bot = value
            metadata_handled = True
            break

        if metadata_handled:
            continue

        size_match = re.match(r"^[^\u4e00-\u9fa5A-Za-z0-9]*大小\s*[:：]?\s*(.+)$", cleaned_line_for_check)
        if size_match:
            size_info = size_match.group(1).strip()
            if re.search(r"(\d+\s*(GB|MB|TB|KB|G|M|T|K|B|字节|每集|单集|左右))", size_info, re.IGNORECASE):
                desc_lines_buffer.append(f"大小: {size_info}")
            continue

        if ignored_prefixes and cleaned_line_for_check.startswith(ignored_prefixes):
            continue

        if label_pattern.match(cleaned_line_for_check):
            continue
        if is_hint_only_line(cleaned_line_for_check, hint_aliases):
            continue

        for hashtag in HASHTAG_PATTERN.findall(cleaned_line_for_check):
            append_tag(tags, hashtag)

        cleaned_line = HASHTAG_PATTERN.sub("", cleaned_line_for_check)
        cleaned_line = re.sub(r"\bvia\s*\S+", " ", cleaned_line, flags=re.IGNORECASE)
        cleaned_line = re.sub(r"\bvia\s*$", " ", cleaned_line, flags=re.IGNORECASE)
        cleaned_line = re.sub(r"@[A-Za-z0-9_]+", " ", cleaned_line)
        cleaned_line = remove_urls_from_text(cleaned_line)
        cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip()
        cleaned_line = re.sub(r"^[\-\|:：,，;；·\s]+|[\-\|:：,，;；·\s]+$", "", cleaned_line)

        if not cleaned_line:
            continue
        if clean_title_text(cleaned_line) == title:
            continue
        if any(re.search(pattern, cleaned_line, re.IGNORECASE) for pattern in filter_patterns):
            continue

        desc_lines_buffer.append(cleaned_line)

    description = clean_description_text("\n".join(desc_lines_buffer))
    add_keyword_tags(tags, f"{title}\n{description}", profile)

    return {
        "title": title,
        "description": description,
        "links": links,
        "tags": tags,
        "source": source,
        "channel": channel,
        "group_name": group,
        "bot": bot,
    }, diagnostics
