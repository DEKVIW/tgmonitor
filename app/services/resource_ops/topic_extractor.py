from __future__ import annotations

import re
import unicodedata
from typing import Any


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
