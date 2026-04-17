from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from .models import ParsedResourceIdentity


TITLE_PREFIX_PATTERNS = (
    re.compile(r"^\s*(?:资源标题|标题|名称)\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:国剧|国漫|国综|动漫|电影|剧集|短剧)\s*[:：]?\s*", re.IGNORECASE),
)
GENERIC_EMPTY_TITLES = {
    "资源标题",
    "标题",
    "名称",
    "未知",
    "无",
    "剧名",
}
DIRECTORY_NOISE_PATTERNS = (
    re.compile(r"(?:今日热门更新目录|短剧更新目录|更新目录)\s*\d*", re.IGNORECASE),
    re.compile(r"^\s*(?:20\d{2}年\d{1,2}月\d{1,2}日)\s*(?:短剧)?更新目录", re.IGNORECASE),
)
COURSE_NOISE_PATTERN = re.compile(
    r"(?:课程|训练营|面试宝典|教资|资料|模板|PPT|课件|教程|实战|学习|知识付费|高薪培养|就业班|宝典)",
    re.IGNORECASE,
)
AUDIO_NOISE_PATTERN = re.compile(r"(?:多人有声剧|广播剧|主播[:：]|在线收听|有声)", re.IGNORECASE)
SOFTWARE_NOISE_PATTERN = re.compile(
    r"(?:Build\.\d+|官方中文|便携版|增强版|全DLC|修改器|浏览器|工具|v\d+\.\d+(?:\.\d+)*|\.(?:7z|zip|rar)\b)",
    re.IGNORECASE,
)
MUSIC_NOISE_PATTERN = re.compile(
    r"(?:FLAC|WAV|APE|SACD|24bit|96kHz|44\.1kHz|无损|单曲|专辑|原抓)",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
SEASON_PATTERNS = (
    re.compile(r"第\s*([零一二三四五六七八九十百两\d]+)\s*季"),
    re.compile(r"\bSeason\s*([0-9]{1,2})\b", re.IGNORECASE),
    re.compile(r"\bS(?:eason\s*)?0*([1-9][0-9]?)(?=E|\b|全)", re.IGNORECASE),
    re.compile(r"年番\s*([0-9]{1,2})", re.IGNORECASE),
)
EPISODE_PATTERNS = (
    re.compile(r"S\d{1,2}\s*E\d{1,4}\s*[-~至]\s*E?\s*0*(\d{1,4})", re.IGNORECASE),
    re.compile(r"第\s*\d{1,4}\s*[-~至]\s*(\d{1,4})\s*集"),
    re.compile(r"\bS\d{1,2}E0*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\bEP?\s*0*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"更新(?:至)?\s*(?:EP|E|第)?\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"更至?\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"更\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,4})\s*集"),
    re.compile(r"全\s*0*(\d{1,4})\s*集"),
    re.compile(r"至\s*0*(\d{1,4})(?!\d)"),
)
ISSUE_PATTERN = re.compile(r"(?:更新)?\s*((?:20\d{2}\s*)?\d{4})\s*期", re.IGNORECASE)
COMPLETE_PATTERN = re.compile(r"(?:全集|全季|完结|超前完结|S\d{1,2}全|全\d{1,4}集|全\d{1,4}期)", re.IGNORECASE)
ONGOING_PATTERN = re.compile(r"更新中", re.IGNORECASE)
META_CUT_PATTERNS = (
    re.compile(r"[\(\[（【]\s*(?:19|20)\d{2}"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
    re.compile(r"第\s*[零一二三四五六七八九十百两\d]+\s*季"),
    re.compile(r"\bSeason\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bS\d{1,2}E\d{1,4}\b", re.IGNORECASE),
    re.compile(r"\bEP?\s*\d+\b", re.IGNORECASE),
    re.compile(r"更新(?:至)?"),
    re.compile(r"更至?"),
    re.compile(r"第\s*\d{1,4}\s*集"),
    re.compile(r"全\d{1,4}集"),
    re.compile(r"\d{4}\s*期"),
    re.compile(r"\b(?:4K|8K|1080P|2160P|HDR|DV|HQ|WEB-?|AMZN|ATVP|HMAX|HIFI|FLAC|HEVC|H\.265)\b", re.IGNORECASE),
    re.compile(r"(?:剧情|爱情|悬疑|犯罪|古装|战争|历史|真人秀|综艺|动画|国漫|国创|奇幻|冒险)"),
)
TRAILING_NOISE_PATTERNS = (
    YEAR_PATTERN,
    re.compile(r"\bS\d{1,2}E\d{1,4}(?:\s*[-~至]\s*E?\d{1,4})?\b", re.IGNORECASE),
    re.compile(r"\bEP?\s*\d+\b", re.IGNORECASE),
    re.compile(r"第\s*[零一二三四五六七八九十百两\d]+\s*季"),
    re.compile(r"年番\s*\d*", re.IGNORECASE),
    re.compile(r"(?:更新(?:至)?|更至?|第)\s*0*\d{1,4}\s*集?"),
    re.compile(r"(?:全集|全季|完结|超前完结|全\d{1,4}集|全\d{1,4}期)", re.IGNORECASE),
    re.compile(r"(?:附第?[一二三四五六七八九十\d]+季|附第一部|附第1部)", re.IGNORECASE),
    re.compile(r"\b(?:4K|8K|1080P|2160P|HDR|DV|HQ|WEB-?|AMZN|ATVP|HMAX|HIFI|FLAC|HEVC|H\.265|60FPS|120FPS|杜比|内封|字幕|高码|臻彩)\b", re.IGNORECASE),
    re.compile(r"(?:剧情|爱情|悬疑|犯罪|古装|战争|历史|真人秀|综艺|动画|国漫|国创|奇幻|冒险)$"),
    re.compile(r"[，,、].*$"),
)
ALIAS_SPLIT_PATTERN = re.compile(r"\s*(?:/|／|｜|\||&|＆|\+)\s*")
ENGLISH_ALIAS_SPLIT_PATTERN = re.compile(r"\s+(?=[A-Za-z][A-Za-z0-9 .:'-]{3,})")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
ASCII_PATTERN = re.compile(r"[A-Za-z]")
META_KEYWORD_PATTERN = re.compile(
    r"(?:更新|更至?|全集|完结|4K|8K|HDR|DV|WEB-?|AMZN|ATVP|HMAX|杜比|内封|字幕|高码|臻彩|剧情|爱情|悬疑|犯罪|国漫|动画|综艺)",
    re.IGNORECASE,
)


def normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200b", " ").replace("\u200c", " ").replace("\u200d", " ").replace("\ufeff", " ")
    text = text.replace("\u200e", " ").replace("\u200f", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def normalize_match_key(value: Any) -> str:
    text = normalize_text(value, max_length=255).lower()
    if not text:
        return ""
    for pattern in TRAILING_NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|season\s*\d+|年番\s*\d*)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text[:255]


def _dedupe_texts(values: Iterable[str], *, max_items: int = 6, max_length: int = 120) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        text = normalize_text(raw_value, max_length=max_length)
        if not text:
            continue
        key = normalize_match_key(text) or text.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(text)
        if len(items) >= max_items:
            break
    return items


def _chinese_number_to_int(value: str) -> int | None:
    text = normalize_text(value, max_length=32)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100}
    total = 0
    current = 0
    has_value = False
    for char in text:
        if char in digits:
            current = digits[char]
            has_value = True
            continue
        unit = units.get(char)
        if unit is None:
            return None
        if current == 0:
            current = 1
        total += current * unit
        current = 0
        has_value = True
    if not has_value:
        return None
    return total + current


def _strip_title_prefixes(text: str) -> str:
    cleaned = normalize_text(text, max_length=255)
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in TITLE_PREFIX_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
    return cleaned


def _detect_non_target_reason(text: str) -> str | None:
    normalized = normalize_text(text, max_length=500)
    if not normalized:
        return "empty_title"
    if any(pattern.search(normalized) for pattern in DIRECTORY_NOISE_PATTERNS):
        return "directory_index"
    if AUDIO_NOISE_PATTERN.search(normalized):
        return "audio_drama"
    if COURSE_NOISE_PATTERN.search(normalized):
        return "course_material"
    if SOFTWARE_NOISE_PATTERN.search(normalized):
        return "software_or_game"
    if MUSIC_NOISE_PATTERN.search(normalized):
        return "music_audio"
    return None


def _extract_year(text: str) -> int | None:
    matched = YEAR_PATTERN.search(text)
    if matched is None:
        return None
    try:
        return int(matched.group(1))
    except (TypeError, ValueError):
        return None


def _extract_season(text: str) -> int | None:
    for pattern in SEASON_PATTERNS:
        matched = pattern.search(text)
        if matched is None:
            continue
        value = _chinese_number_to_int(matched.group(1))
        if value is not None and value > 0:
            return value
    return None


def _extract_episode(text: str) -> int | None:
    matches: list[int] = []
    for pattern in EPISODE_PATTERNS:
        for matched in pattern.findall(text):
            try:
                matches.append(int(matched))
            except (TypeError, ValueError):
                continue
    return max(matches) if matches else None


def _extract_issue(text: str) -> tuple[str | None, int | None]:
    matched = ISSUE_PATTERN.search(text)
    if matched is None:
        return None, None
    issue_no = re.sub(r"\s+", "", matched.group(1) or "")
    issue_no = issue_no[-4:] if len(issue_no) > 4 else issue_no
    if not issue_no:
        return None, None
    try:
        sort_value = int(issue_no)
    except (TypeError, ValueError):
        sort_value = None
    return issue_no, sort_value


def _detect_complete(text: str) -> bool:
    return bool(COMPLETE_PATTERN.search(text) and not ONGOING_PATTERN.search(text))


def _guess_content_type(text: str, *, episode: int | None, issue_no: str | None) -> str | None:
    normalized = normalize_text(text, max_length=500)
    if not normalized:
        return None
    if issue_no or re.search(r"(?:综艺|真人秀|\d{4}\s*期)", normalized, re.IGNORECASE):
        return "variety"
    if re.search(r"(?:国漫|动画|动漫|年番|国创)", normalized, re.IGNORECASE):
        return "anime"
    if episode is not None or re.search(r"(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|\bS\d{1,2}\b)", normalized, re.IGNORECASE):
        return "tv_series"
    if re.search(r"(?:电影|劇場版|剧场版)", normalized, re.IGNORECASE):
        return "movie"
    return "movie"


def _find_meta_cut_index(text: str) -> int | None:
    indexes = [matched.start() for pattern in META_CUT_PATTERNS for matched in [pattern.search(text)] if matched and matched.start() > 0]
    if not indexes:
        return None
    return min(indexes)


def _trim_repeated_tail(text: str) -> str:
    candidate = normalize_text(text, max_length=255)
    if not candidate:
        return ""
    repeated_match = re.match(r"^(.+?)\s+\1$", candidate)
    if repeated_match is not None:
        return normalize_text(repeated_match.group(1), max_length=255)

    parts = candidate.split()
    if len(parts) >= 2:
        first_key = normalize_match_key(parts[0])
        last_key = normalize_match_key(parts[-1])
        if first_key and first_key == last_key and len(parts) > 1:
            return normalize_text(" ".join(parts[:-1]), max_length=255)
    return candidate


def _clean_title_candidate(text: str) -> str:
    candidate = _strip_title_prefixes(text)
    if not candidate:
        return ""
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        for pattern in TRAILING_NOISE_PATTERNS:
            candidate = pattern.sub(" ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -_|/,.，。:：;；[]【】()（）<>《》")
        candidate = _trim_repeated_tail(candidate)
    if not candidate:
        return ""
    if candidate in GENERIC_EMPTY_TITLES:
        return ""
    if META_KEYWORD_PATTERN.search(candidate):
        return ""
    return normalize_text(candidate, max_length=255)


def _split_alias_candidates(base_title: str) -> list[str]:
    parts = [base_title]
    parts.extend(ALIAS_SPLIT_PATTERN.split(base_title))

    if CJK_PATTERN.search(base_title) and " " in base_title:
        parts.append(base_title.split(" ", 1)[0])

    if CJK_PATTERN.search(base_title) and ASCII_PATTERN.search(base_title):
        parts.extend(ENGLISH_ALIAS_SPLIT_PATTERN.split(base_title))

    return [normalize_text(part, max_length=255) for part in parts if normalize_text(part, max_length=255)]


def _score_title_candidate(title: str, *, source_index: int, full_title: str) -> float:
    normalized_key = normalize_match_key(title)
    if not normalized_key:
        return 0.0
    score = 0.4
    key_length = len(normalized_key)
    if 2 <= key_length <= 18:
        score += 0.2
    elif key_length <= 32:
        score += 0.1
    if not META_KEYWORD_PATTERN.search(title):
        score += 0.15
    if full_title.startswith(title):
        score += 0.12
    if source_index == 0:
        score += 0.08
    if CJK_PATTERN.search(title):
        score += 0.03
    if len(title.split()) <= 4:
        score += 0.04
    if len(title) > 48:
        score -= 0.1
    return max(0.0, min(score, 0.98))


def _extract_title_candidates(raw_title: str, *, source_index: int) -> list[tuple[str, float]]:
    cleaned = _strip_title_prefixes(raw_title)
    if not cleaned:
        return []

    variants = [cleaned]
    cut_index = _find_meta_cut_index(cleaned)
    if cut_index is not None:
        variants.append(cleaned[:cut_index])

    candidates: list[tuple[str, float]] = []
    for variant in variants:
        variant = normalize_text(variant, max_length=255)
        if not variant:
            continue
        for part in _split_alias_candidates(variant):
            cleaned_part = _clean_title_candidate(part)
            if not cleaned_part:
                continue
            score = _score_title_candidate(cleaned_part, source_index=source_index, full_title=cleaned)
            candidates.append((cleaned_part, score))
    return candidates


def _build_search_queries(
    *,
    core_title: str | None,
    aliases: list[str],
    release_year: int | None,
    season: int | None,
) -> list[str]:
    if not core_title:
        return []
    queries: list[str] = [core_title]
    if season is not None:
        queries.append(f"{core_title} 第{season}季")
        queries.append(f"{core_title} S{season:02d}")
    if release_year is not None:
        queries.append(f"{core_title} {release_year}")
    queries.extend(aliases)
    return _dedupe_texts(queries, max_items=4, max_length=80)


def parse_resource_identity(
    primary_title: Any,
    *,
    alternate_titles: Iterable[Any] | None = None,
) -> ParsedResourceIdentity:
    normalized_primary = _strip_title_prefixes(normalize_text(primary_title, max_length=255))
    titles = [normalized_primary]
    titles.extend(normalize_text(item, max_length=255) for item in list(alternate_titles or []))
    titles = [title for title in titles if title]

    raw_title = normalized_primary or (titles[0] if titles else "")
    non_target_reason = _detect_non_target_reason(raw_title)
    if non_target_reason is not None:
        return ParsedResourceIdentity(
            raw_title=raw_title,
            cleaned_title=raw_title,
            core_title=None,
            aliases=[],
            search_queries=[],
            normalized_keys=[],
            content_type=None,
            is_target_work=False,
            needs_ai_review=False,
            should_skip_ai=True,
            confidence=0.98,
            reason=non_target_reason,
            debug={"source_titles": titles[:4]},
        )

    candidate_scores: dict[str, float] = {}
    for index, title in enumerate(titles):
        for candidate, score in _extract_title_candidates(title, source_index=index):
            current = candidate_scores.get(candidate)
            if current is None or score > current:
                candidate_scores[candidate] = score

    sorted_candidates = sorted(candidate_scores.items(), key=lambda item: (-item[1], len(normalize_match_key(item[0])), item[0]))
    core_title = sorted_candidates[0][0] if sorted_candidates else None
    aliases = _dedupe_texts(
        [candidate for candidate, _ in sorted_candidates],
        max_items=6,
        max_length=255,
    )

    release_year = _extract_year(raw_title)
    season = _extract_season(raw_title)
    episode = _extract_episode(raw_title)
    issue_no, issue_sort_value = _extract_issue(raw_title)
    is_complete = _detect_complete(raw_title)
    content_type = _guess_content_type(raw_title, episode=episode, issue_no=issue_no)
    search_queries = _build_search_queries(
        core_title=core_title,
        aliases=aliases,
        release_year=release_year,
        season=season,
    )
    normalized_keys = _dedupe_texts(
        [normalize_match_key(item) for item in [core_title, *aliases] if item],
        max_items=6,
        max_length=255,
    )

    confidence = sorted_candidates[0][1] if sorted_candidates else 0.0
    needs_ai_review = not core_title or confidence < 0.72
    if core_title and len(normalize_match_key(core_title)) < 2:
        needs_ai_review = True

    return ParsedResourceIdentity(
        raw_title=raw_title,
        cleaned_title=raw_title,
        core_title=core_title,
        aliases=aliases,
        search_queries=search_queries,
        normalized_keys=normalized_keys,
        release_year=release_year,
        season=season,
        episode=episode,
        issue_no=issue_no,
        issue_sort_value=issue_sort_value,
        content_type=content_type,
        is_complete=is_complete,
        is_target_work=True,
        needs_ai_review=needs_ai_review,
        should_skip_ai=False,
        confidence=confidence,
        reason="rule_title_parse" if core_title else "rule_title_ambiguous",
        debug={
            "source_titles": titles[:4],
            "candidates": [
                {"title": title, "score": round(score, 3)}
                for title, score in sorted_candidates[:6]
            ],
        },
    )
