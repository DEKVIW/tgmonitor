from __future__ import annotations

import re
import unicodedata
from typing import Any


NEW_SOURCE_NOISE_PATTERN = re.compile(
    r"(夸克网盘|百度网盘|阿里云盘|115网盘|迅雷云盘|天翼云盘|uc网盘|网盘|分享链接|提取码|密码|转存|秒传)",
    re.IGNORECASE,
)
NEW_TECH_NOISE_PATTERN = re.compile(
    r"(2160p|1080p|720p|4k|8k|hdr10?\+?|hdr|dv|dovi|hevc|x265|h265|x264|h264|"
    r"web[-\s]?dl|web[-\s]?rip|bluray|blu[-\s]?ray|remux|flac\d*|aac\d*|ddp\d*|atmos|中字|双字|国语|粤语|英语|无字幕)",
    re.IGNORECASE,
)
NEW_UPDATE_NOISE_PATTERN = re.compile(
    r"(更新|更至|更\d+集|连载|日更|周更|追更|持续更新|完结|全集|合集|抢先版|修复版|最终版)",
    re.IGNORECASE,
)
NEW_EPISODE_PATTERN = re.compile(
    r"(第\s*\d{1,4}\s*[集话期章部季]|ep\s*\d{1,4}|e\d{1,4}|全\d{1,4}\s*[集话期章部季])",
    re.IGNORECASE,
)
NEW_SEASON_PATTERN = re.compile(
    r"(?:第\s*(\d{1,2})\s*季|season\s*(\d{1,2})|\bs\s*(\d{1,2})\b)",
    re.IGNORECASE,
)
NEW_YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
NEW_SEPARATOR_PATTERN = re.compile(r"[|丨/\\·•~～:_+=-]+")
NEW_TOPIC_KEY_SANITIZE_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff|:-]+", re.IGNORECASE)
NEW_TITLE_STOP_TOKENS = {
    "年番",
    "剧场版",
    "真人版",
    "特别篇",
    "抢先",
    "更新",
    "合集",
    "全集",
    "资源",
    "分享",
    "链接",
}


def _new_normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _new_extract_season_hint(text: str) -> str | None:
    match = NEW_SEASON_PATTERN.search(text)
    if not match:
        return None
    raw_value = next((group for group in match.groups() if group), None)
    if not raw_value:
        return None
    try:
        return str(int(raw_value))
    except ValueError:
        return None


def _new_extract_year_hint(text: str) -> str | None:
    match = NEW_YEAR_PATTERN.search(text)
    return match.group(1) if match else None


def _new_strip_noise(text: str) -> str:
    current = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
    current = NEW_SOURCE_NOISE_PATTERN.sub(" ", current)
    current = NEW_TECH_NOISE_PATTERN.sub(" ", current)
    current = NEW_UPDATE_NOISE_PATTERN.sub(" ", current)
    current = NEW_EPISODE_PATTERN.sub(" ", current)
    current = re.sub(r"[\[\]【】（）(){}<>《》「」『』“”\"'`]", " ", current)
    current = NEW_SEPARATOR_PATTERN.sub(" ", current)
    current = re.sub(r"\s+", " ", current)
    return current.strip()


def _new_pick_title(source_text: str) -> str:
    raw_tokens = [token for token in _new_strip_noise(source_text).split(" ") if token]
    if not raw_tokens:
        return ""

    title_tokens: list[str] = []
    for token in raw_tokens:
        lower_token = token.lower()
        if NEW_YEAR_PATTERN.fullmatch(token):
            if title_tokens:
                break
            continue
        if NEW_TECH_NOISE_PATTERN.fullmatch(token) or NEW_SOURCE_NOISE_PATTERN.fullmatch(token):
            if title_tokens:
                break
            continue
        if NEW_UPDATE_NOISE_PATTERN.fullmatch(token) or NEW_EPISODE_PATTERN.fullmatch(token):
            if title_tokens:
                break
            continue
        if lower_token in NEW_TITLE_STOP_TOKENS:
            if title_tokens:
                continue
            continue
        if token.isdigit():
            if title_tokens:
                break
            continue
        title_tokens.append(token)
        if len(title_tokens) >= 4:
            break

    cleaned_tokens = [token for token in title_tokens if token.lower() not in NEW_TITLE_STOP_TOKENS]
    title = " ".join(cleaned_tokens).strip(" -_/")
    if title:
        return title[:120]

    fallback = re.split(r"(?:\b(?:19|20)\d{2}\b|第\s*\d+\s*[集话期章部季]|ep\s*\d+|e\d+)", source_text, maxsplit=1)[0]
    fallback = _new_strip_noise(fallback).strip(" -_/")
    return fallback[:120]


def extract_resource_topic_v2(
    *parts: Any,
    share_key: str | None = None,
    fallback_id: int | None = None,
) -> dict[str, str | None]:
    sources = [_new_normalize_text(part) for part in parts if _new_normalize_text(part)]
    source_text = next((value for value in sources if len(value) >= 2), "")
    season_hint = _new_extract_season_hint(source_text) if source_text else None
    year_hint = _new_extract_year_hint(source_text) if source_text else None

    topic_title = _new_pick_title(source_text) if source_text else ""
    if not topic_title:
        if share_key:
            topic_title = f"资源 {share_key}"
        elif source_text:
            topic_title = source_text[:80]
        elif fallback_id is not None:
            topic_title = f"资源 {fallback_id}"
        else:
            topic_title = "未命名资源"

    topic_title = re.sub(r"\s+", " ", topic_title).strip(" -_/")[:120]
    key_source = topic_title.lower()
    topic_key = NEW_TOPIC_KEY_SANITIZE_PATTERN.sub("", key_source.replace(" ", "-"))
    if season_hint:
        topic_key = f"{topic_key}|season:{season_hint}"
    if year_hint:
        topic_key = f"{topic_key}|year:{year_hint}"
    if len(topic_key) < 2:
        if share_key:
            topic_key = f"share:{share_key.lower()}"
        elif fallback_id is not None:
            topic_key = f"link:{fallback_id}"
        else:
            topic_key = "unknown"

    return {
        "topic_title": topic_title or "未命名资源",
        "topic_key": topic_key[:160],
        "topic_source_text": source_text[:255] or None,
        "season_hint": season_hint,
        "year_hint": year_hint,
    }


URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
SEASON_PATTERN = re.compile(r"(?:第\s*(\d{1,2})\s*季|season\s*(\d{1,2})|s\s*(\d{1,2})(?!\d))", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
EPISODE_PATTERN = re.compile(
    r"(?:第\s*\d{1,4}\s*[集话期章卷部篇]|ep\s*\d{1,4}\b|e\d{1,4}\b|第\s*\d{1,4}\s*弹)",
    re.IGNORECASE,
)
UPDATE_PATTERN = re.compile(
    r"(?:持续更新|更新至|更新到|更新中|更新|更至|连载中?|追更|日更|周更|月更|完结篇?|修复版|最终版)",
    re.IGNORECASE,
)
QUALITY_PATTERN = re.compile(
    r"(?:2160p|1080p|720p|4k|8k|hdr10?\+?|hdr|hevc|x265|h265|x264|h264|"
    r"蓝光|bluray|web[-\s]?dl|web[-\s]?rip|remux|dvdrip|中字|双字|国语|粤语|英语|"
    r"简中|繁中|无删减|高码率|杜比视界|杜比全景声)",
    re.IGNORECASE,
)
SOURCE_PATTERN = re.compile(
    r"(?:夸克网盘|夸克|百度网盘|百度盘|阿里云盘|阿里盘|115网盘|115|迅雷云盘|迅雷|"
    r"天翼云盘|天翼|uc网盘|uc|网盘资源|网盘|分享链接|链接|提取码|密码|秒传|转存)",
    re.IGNORECASE,
)
BRACKET_PATTERN = re.compile(r"[\[\]【】()（）{}<>《》「」『』“”\"'`]")
SEPARATOR_PATTERN = re.compile(r"[|·•,，.。:：;；!！?？/\\_+=~\-]+")
TOPIC_KEY_SANITIZE_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff|:-]+", re.IGNORECASE)

STOP_WORDS = {
    "资源",
    "分享",
    "链接",
    "网盘",
    "提取码",
    "密码",
    "转存",
    "秒传",
    "下载",
    "合集",
    "全",
    "最新",
    "已",
    "可",
    "看",
    "版",
    "the",
    "a",
}


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_season_hint(text: str) -> str | None:
    match = SEASON_PATTERN.search(text)
    if not match:
        return None
    season_value = next((group for group in match.groups() if group), None)
    if not season_value:
        return None
    try:
        return str(int(season_value))
    except ValueError:
        return None


def _extract_year_hint(text: str) -> str | None:
    match = YEAR_PATTERN.search(text)
    if not match:
        return None
    return match.group(1)


def _clean_topic_text(text: str) -> str:
    current = URL_PATTERN.sub(" ", text)
    current = SOURCE_PATTERN.sub(" ", current)
    current = UPDATE_PATTERN.sub(" ", current)
    current = EPISODE_PATTERN.sub(" ", current)
    current = QUALITY_PATTERN.sub(" ", current)
    current = BRACKET_PATTERN.sub(" ", current)
    current = SEPARATOR_PATTERN.sub(" ", current)
    current = re.sub(r"\s+", " ", current).strip()
    if not current:
        return ""

    tokens: list[str] = []
    for token in current.split():
        normalized = token.strip()
        if not normalized:
            continue
        normalized_lower = normalized.lower()
        if normalized_lower in STOP_WORDS:
            continue
        if normalized.isdigit() and len(normalized) <= 2:
            continue
        if len(normalized) == 1 and not re.search(r"[\u4e00-\u9fff]", normalized):
            continue
        tokens.append(normalized)

    return " ".join(tokens[:10]).strip()


def _is_generic_topic(topic_title: str) -> bool:
    if not topic_title or len(topic_title) < 2:
        return True
    compact = topic_title.replace(" ", "").lower()
    if compact in {"资源", "链接", "分享", "网盘", "资源链接"}:
        return True
    return False


def extract_resource_topic(
    *parts: Any,
    share_key: str | None = None,
    fallback_id: int | None = None,
) -> dict[str, str | None]:
    sources = [_normalize_text(part) for part in parts if _normalize_text(part)]
    source_text = next((value for value in sources if len(value) >= 2), "")
    season_hint = _extract_season_hint(source_text) if source_text else None
    year_hint = _extract_year_hint(source_text) if source_text else None

    topic_title = _clean_topic_text(source_text) if source_text else ""
    if season_hint and topic_title and f"S{season_hint}".lower() not in topic_title.lower():
        topic_title = f"{topic_title} S{season_hint}"
    if year_hint and topic_title and year_hint not in topic_title:
        topic_title = f"{topic_title} {year_hint}"

    if _is_generic_topic(topic_title):
        if share_key:
            topic_title = f"资源 {share_key}"
        elif source_text:
            topic_title = source_text[:80]
        elif fallback_id is not None:
            topic_title = f"资源 {fallback_id}"
        else:
            topic_title = "未命名资源"

    topic_title = re.sub(r"\s+", " ", topic_title).strip(" -_/")[:120]

    key_source = topic_title.lower()
    topic_key = TOPIC_KEY_SANITIZE_PATTERN.sub("", key_source.replace(" ", "-"))
    if season_hint:
        topic_key = f"{topic_key}|season:{season_hint}"
    if year_hint:
        topic_key = f"{topic_key}|year:{year_hint}"
    if len(topic_key) < 2:
        if share_key:
            topic_key = f"share:{share_key.lower()}"
        elif fallback_id is not None:
            topic_key = f"link:{fallback_id}"
        else:
            topic_key = "unknown"

    return {
        "topic_title": topic_title or "未命名资源",
        "topic_key": topic_key[:160],
        "topic_source_text": source_text[:255] or None,
        "season_hint": season_hint,
        "year_hint": year_hint,
    }
