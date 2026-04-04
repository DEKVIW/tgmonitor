"""Message parsing helpers for the Telegram monitor."""

from __future__ import annotations

import datetime as dt
import html
import asyncio
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qsl, unquote, urlparse

import aiohttp

from app.core.monitor_rules import load_monitor_rules, resolve_channel_profile

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


@dataclass
class ParseDiagnostics:
    profile_name: str
    raw_url_count: int = 0
    resolved_url_count: int = 0
    redirect_resolved_count: int = 0
    extracted_link_count: int = 0


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


def extract_redirect_urls_from_html(body: str) -> List[str]:
    if not body:
        return []

    candidates = []
    patterns = [
        r"""location(?:\.href|\.replace)?\s*=\s*["']([^"']+)["']""",
        r"""window\.open\(\s*["']([^"']+)["']""",
        r"""content=["'][^"']*url=([^"']+)["']""",
    ]

    for pattern in patterns:
        candidates.extend(re.findall(pattern, body, flags=re.IGNORECASE))

    if not candidates and ("http://" in body or "https://" in body):
        candidates.extend(re.findall(r"""https?://[^\s"'<>]+""", body))

    urls = []
    seen = set()
    for candidate in candidates:
        for candidate_url in extract_urls_from_text_fragment(candidate):
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


async def fetch_redirect_target(url: str, http_session: aiohttp.ClientSession) -> Tuple[str, List[str]]:
    for method_name in ("head", "get"):
        try:
            request = getattr(http_session, method_name)
            async with request(url, allow_redirects=True) as response:
                final_url = normalize_url(str(response.url))
                html_targets: List[str] = []
                content_type = (response.headers.get("Content-Type") or "").lower()
                is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
                if method_name == "get" and is_html:
                    body = await response.text(errors="ignore")
                    html_targets = extract_redirect_urls_from_html(body)
                return final_url or url, html_targets
        except Exception:
            continue

    return url, []


async def resolve_netdisk_url(
    url: str,
    netdisk_map: List[Tuple[List[str], str]],
    redirect_query_keys: Iterable[str],
    http_session: aiohttp.ClientSession,
    depth: int = 0,
    visited: set[str] | None = None,
) -> str:
    normalized_url = normalize_url(url)
    if not normalized_url:
        return ""

    if visited is None:
        visited = set()
    if normalized_url in visited or depth > MAX_URL_RESOLVE_DEPTH:
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
            depth=depth + 1,
            visited=next_visited,
        )
        if get_netdisk_name_for_url(resolved_target, netdisk_map):
            _set_cached_resolution(normalized_url, resolved_target)
            return resolved_target

    final_url, html_targets = await fetch_redirect_target(normalized_url, http_session)
    if final_url and final_url != normalized_url:
        resolved_target = await resolve_netdisk_url(
            final_url,
            netdisk_map,
            redirect_query_keys,
            http_session,
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
) -> Tuple[Dict[str, str], int]:
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

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http_session:
        fetched_results = await asyncio.gather(
            *(
                resolve_netdisk_url(url, netdisk_map, redirect_query_keys, http_session)
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


async def parse_message_content(
    text: str,
    msg_obj: Any = None,
    channel_name: str | None = None,
) -> Tuple[Dict[str, Any], ParseDiagnostics]:
    rules = load_monitor_rules()
    profile = resolve_channel_profile(channel_name, rules)
    netdisk_map = _get_netdisk_map(rules)
    redirect_query_keys = rules.get("redirect_query_keys", [])
    valid_labels = profile.get("valid_labels", [])

    diagnostics = ParseDiagnostics(profile_name=channel_name or "default")
    original_lines = text.split("\n")
    title = ""
    source = ""
    channel = ""
    group = ""
    bot = ""
    desc_lines_buffer: List[str] = []

    all_urls = extract_all_urls(text, msg_obj)
    diagnostics.raw_url_count = len(all_urls)
    resolved_urls, redirect_resolved_count = await resolve_message_urls(all_urls, netdisk_map, redirect_query_keys)
    diagnostics.resolved_url_count = len(resolved_urls)
    diagnostics.redirect_resolved_count = redirect_resolved_count

    links: Dict[str, List[Dict[str, Any]]] = {}
    for raw_url, resolved_url in resolved_urls.items():
        name = get_netdisk_name_for_url(resolved_url, netdisk_map)
        if not name:
            name = get_netdisk_name_for_url(raw_url, netdisk_map)
            resolved_url = raw_url
        if not name:
            continue

        label = find_link_label(original_lines, raw_url, resolved_url, valid_labels)
        links.setdefault(name, [])

        link_item: Dict[str, Any] = {"label": label, "url": resolved_url}
        if resolved_url != raw_url:
            link_item["original_url"] = raw_url

        if not any(item["url"] == resolved_url for item in links[name]):
            links[name].append(link_item)

    diagnostics.extracted_link_count = sum(len(items) for items in links.values())

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

        if cleaned_line_for_check.startswith(ignored_prefixes):
            continue

        if label_pattern.match(cleaned_line_for_check):
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
