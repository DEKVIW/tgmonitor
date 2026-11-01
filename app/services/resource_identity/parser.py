from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from .models import ParsedResourceIdentity


TITLE_PREFIX_PATTERNS = (
    re.compile(r"^\s*(?:资源标题|标题|名称)\s*[:：]\s*", re.IGNORECASE),
    re.compile(
        r"^\s*(?:国剧|国漫|国综|韩剧|日剧|日漫|美剧|英剧|欧美剧|英美剧|美漫|泰剧|港剧|台剧|大陆剧|国产剧|"
        r"动漫|动画|电影|剧集|电视剧|综艺|真人秀|纪录片|短剧)\s*[:：]?\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*[一-鿿]{2,8}(?:连续剧|动漫电影|电影|剧)\s*[:：]?\s*(?=[《【\[:：])",
        re.IGNORECASE,
    ),
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
    r"(?:课程|训练营|面试宝典|教资|资料|模板|PPT|课件|教程|实战|实操课|学习|知识付费|高薪培养|就业班|宝典|套题|考季|教材)",
    re.IGNORECASE,
)
AUDIO_NOISE_PATTERN = re.compile(r"(?:多人有声剧|广播剧|主播[:：]|在线收听|有声|音频|读书)", re.IGNORECASE)
PRINTED_MEDIA_NOISE_PATTERN = re.compile(r"(?:漫画|台版|PDF|电子书|图书)", re.IGNORECASE)
SOFTWARE_NOISE_PATTERN = re.compile(
    r"(?:Build\.\d+|官方中文|便携版|增强版|全DLC|修改器|浏览器|工具|v\d+\.\d+(?:\.\d+)*|\.(?:7z|zip|rar)\b)",
    re.IGNORECASE,
)
MUSIC_NOISE_PATTERN = re.compile(
    r"(?:FLAC|WAV|APE|SACD|24bit|96kHz|44\.1kHz|无损|单曲|专辑|原抓)",
    re.IGNORECASE,
)
PLATFORM_LABEL_PATTERN = re.compile(
    r"^(?:夸克网盘|百度网盘|阿里云盘|阿里网盘|迅雷云盘|115网盘|123云盘|天翼云盘|UC网盘|蓝奏云|移动云盘)$",
    re.IGNORECASE,
)
PLATFORM_TRAILING_PATTERN = re.compile(
    r"(?:夸克网盘|百度网盘|阿里云盘|阿里网盘|迅雷云盘|115网盘|123云盘|天翼云盘|UC网盘|蓝奏云|移动云盘)\s*$",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
SEASON_PATTERNS = (
    re.compile(r"\bSeason\s*([0-9]{1,2})\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])S(?:eason\s*)?0*([1-9][0-9]?)(?=E|\b|全)", re.IGNORECASE),
    re.compile(r"第\s*([零一二三四五六七八九十百两\d]+)\s*季"),
    re.compile(r"年番\s*([0-9]{1,2})(?!\s*[Kk])(?=\s|$|[（(【\[+·•|｜])", re.IGNORECASE),
)
EPISODE_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])S\d{1,2}\s*E\d{1,4}\s*[-~至]\s*E?\s*0*(\d{1,4})", re.IGNORECASE),
    re.compile(r"第\s*\d{1,4}\s*[-~至]\s*(\d{1,4})\s*集"),
    re.compile(r"(?<![A-Za-z0-9])S\d{1,2}E0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])EP?\s*0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"更新(?:至)?\s*(?:EP|E|第)?\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"更至?\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"更\s*0*(\d{1,4})\s*集?", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,4})\s*集"),
    re.compile(r"(?<!\d)0*(\d{1,4})\s*集"),
    re.compile(r"全\s*0*(\d{1,4})\s*集"),
    re.compile(r"至\s*0*(\d{1,4})(?!\d)"),
)
ISSUE_PATTERN = re.compile(r"(?:更新)?\s*((?:20\d{2}\s*)?\d{4})\s*期", re.IGNORECASE)
COMPLETE_PATTERN = re.compile(r"(?:全集|全季|完结|超前完结|S\d{1,2}全|全\d{1,4}集|全\d{1,4}期)", re.IGNORECASE)
ONGOING_PATTERN = re.compile(r"更新中", re.IGNORECASE)
META_CUT_PATTERNS = (
    re.compile(
        r"[\(（]\s*(?:(?:19|20)\d{2}(?:\s*[-~至]\s*(?:19|20)?\d{2})?|"
        r"(?:(?:更新|更至?)\s*)?(?:全|第)?\d{1,4}\s*集|"
        r"(?:两|多)?季合集|\d{1,2}\s*[-~至]\s*\d{1,2}\s*季)"
    ),
    re.compile(r"[\(\[（【]\s*(?:19|20)\d{2}"),
    re.compile(r"(?<!\d)(?:19|20)\d{2}(?=\s|$|[./·•+|｜])"),
    re.compile(
        r"(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|Season\s*\d+|年番\s*\d*)\s*"
        r"(?=(?:19|20)\d{2}|[\(（\[【]|[+·•|｜]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|[\s·•|｜./])(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|Season\s*\d+|S\d{1,2}(?:E\d{1,4})?)", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜./])EP?\s*\d+", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:更新(?:至|到)?|更至?|第\s*\d{1,4}\s*集|全\d{1,4}(?:集|季|期)|\d{1,4}\s*期)"),
    re.compile(r"(?:^|[\s·•|｜])(?:年番\s*\d*|(?:最终|完结)季|\d{1,2}\s*[-~至]\s*\d{1,2}\s*季)"),
    re.compile(
        r"(?:^|[\s·•|｜/+])(?:4K|8K|720P|1080P?|1440P|2160P?|HDR(?:10(?:\+)?|10bit)?|"
        r"DV|HQ|WEB(?:-DL)?|AMZN|ATVP|HMAX|DSNP|HIFI|FLAC|HEVC|H\.265|60FPS|120FPS|"
        r"MAX|杜比|臻彩|高码|内封|外封|内嵌|外挂|字幕|简繁(?:字幕)?|多国字幕)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|[\s·•|｜])\d{1,4}\s*集(?:\s|$|[+&|｜])"),
    re.compile(r"(?:^|[\s·•|｜])(?:类型|主演|演员|导演)\s*[:：]"),
    re.compile(r"(?:^|[\s·•|｜])(?:剧情|爱情|悬疑|犯罪|古装|战争|历史|真人秀|综艺|动画|国漫|国创|奇幻|冒险)(?=\s*[/／|、])"),
)
TRAILING_NOISE_PATTERNS = (
    PLATFORM_TRAILING_PATTERN,
    re.compile(r"(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|Season\s*\d+|年番\s*\d*)\s*$", re.IGNORECASE),
    re.compile(r"(?:最终|完结)季(?=\s|$|19|20|[+&|｜])", re.IGNORECASE),
    re.compile(r"(?:[\s·•|｜])(?:19|20)\d{2}(?=\s|$|[./·•+|｜])"),
    re.compile(r"(?:^|[\s·•|｜])S\d{1,2}E\d{1,4}(?:\s*[-~至]\s*E?\d{1,4})?", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])EP?\s*\d+", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:第\s*[零一二三四五六七八九十百两\d]+\s*季|Season\s*\d+)", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:年番\s*\d*|(?:最终|完结)季|\d{1,2}\s*[-~至]\s*\d{1,2}\s*季)", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:更新(?:至|到)?|更至?|第\s*0*\d{1,4}\s*集|全\s*0*\d{1,4}(?:集|季|期)|完结|超前完结)"),
    re.compile(r"(?:^|[\s·•|｜])(?:AI\s*)?(?:短剧|漫剧)(?=\s|$|[+&|｜])", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:两|多)季合集(?=\s|$|[+&|｜])", re.IGNORECASE),
    re.compile(r"(?:^|[\s·•|｜])(?:附第?[一二三四五六七八九十\d]+季|附第一部|附第1部)", re.IGNORECASE),
    re.compile(
        r"(?:^|[\s·•|｜/+])(?:4K|8K|720P|1080P?|1440P|2160P?|HDR(?:10(?:\+)?|10bit)?|"
        r"DV|HQ|WEB(?:-DL)?|AMZN|ATVP|HMAX|DSNP|HIFI|FLAC|HEVC|H\.265|60FPS|120FPS|"
        r"MAX|杜比|臻彩|高码|内封|外封|内嵌|外挂|字幕|简繁(?:字幕)?|多国字幕)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|[\s·•|｜])(?:经典日漫|日漫|国日|国英|日语|英语|韩语|中字|中英|简繁|简中|繁中|多国字幕)$", re.IGNORECASE),
)
ALIAS_SPLIT_PATTERN = re.compile(r"\s*(?:/|／|｜|\||&|＆|\+)\s*")
ENGLISH_ALIAS_TAIL_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9 .:'-]{2,})$")
ENGLISH_ALIAS_META_PATTERN = re.compile(
    r"\b(?:Season\s*\d+|S\d{1,2}(?:E\d{1,4})?|EP?\s*\d+|WEB-?|HDR(?:10\+?)?|DV|4K|8K|1080P|2160P|60FPS|120FPS|MAX|HIFI|FLAC|HEVC|H\.265|AMZN|ATVP|HMAX)\b.*$",
    re.IGNORECASE,
)
TRAILING_PERSON_LIST_PATTERN = re.compile(
    r"^(.*?)(?:[\s·•.．,:：;；-]\s*)([\u4e00-\u9fff]{2,4}(?:\s*[/／｜|、]\s*[\u4e00-\u9fff]{2,4}){1,})\s*$"
)
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
ASCII_PATTERN = re.compile(r"[A-Za-z]")
META_KEYWORD_PATTERN = re.compile(
    r"(?:更新|更至?|全集|完结|4K|8K|HDR|DV|WEB-?|AMZN|ATVP|HMAX|MAX|杜比|内封|字幕|高码|臻彩|类型|主演|演员|导演|剧情|爱情|悬疑|犯罪|古装|战争|历史|真人秀|综艺|动画|国漫|国创|奇幻|冒险|多国字幕)",
    re.IGNORECASE,
)
GENERIC_METADATA_KEY_PATTERN = re.compile(
    r"^(?:更新|更至?|全集|完结|年番|季|4k|8k|720p|1080p?|1440p|2160p?|hdr|dv|web|amzn|atvp|hmax|dsnp|max|杜比|内封|外封|内嵌|外挂|字幕|简繁|高码|臻彩|类型|主演|演员|导演|剧情|爱情|悬疑|犯罪|古装|战争|历史|真人秀|综艺|动画|国漫|国创|奇幻|冒险|多国字幕)+$",
    re.IGNORECASE,
)
GENERIC_IDENTITY_KEYS = frozenset({
    "集",
    "期",
    "全",
    "全集",
    "全季",
    "更",
    "更新",
    "第",
    "季",
    "episode",
    "episodes",
    "ep",
    "season",
})


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


def is_meaningful_identity_key(value: Any) -> bool:
    key = normalize_match_key(value)
    return bool(
        key
        and key not in GENERIC_IDENTITY_KEYS
        and not GENERIC_METADATA_KEY_PATTERN.fullmatch(key)
    )


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
    cleaned = re.sub(r"^\s*[📺🎬🎞️]\s*", "", cleaned)
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in TITLE_PREFIX_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
    return cleaned


LEADING_BRACKET_BLOCK_PATTERN = re.compile(r"^\s*[\[【]\s*([^\]】]+?)\s*[\]】]\s*")
OUTER_TITLE_WRAPPER_PATTERN = re.compile(r"^[《〈「『]\s*(.*?)\s*[》〉」』]")
LEADING_METADATA_PATTERN = re.compile(
    r"^\s*(?:"
    r"[\(（]\s*(?:19|20)\d{2}(?:\s*[-~至]\s*(?:19|20)?\d{2})?\s*[\)）]"
    r"|(?:19|20)\d{2}\s+(?=\S)"
    r"|(?:更新(?:至|到)?\s*(?:EP|E|第)?\s*\d{1,4}\s*集?"
    r"|更至?\s*\d{1,4}\s*集?"
    r"|第\s*\d{1,4}\s*集"
    r"|全\s*\d{1,4}(?:集|季|期)"
    r"|至\s*\d{1,4})"
    r"\s*"
    r")",
    re.IGNORECASE,
)
BRACKET_METADATA_PATTERN = re.compile(
    r"^(?:"
    r"更新(?:至|到)?\s*(?:EP|E|第)?\s*\d{1,4}\s*集?"
    r"|更至?\s*\d{1,4}\s*集?"
    r"|第\s*\d{1,4}\s*集"
    r"|全\s*\d{1,4}(?:集|季|期)"
    r"|至\s*\d{1,4}"
    r"|(?:19|20)\d{2}(?:\s*[-~至]\s*(?:19|20)?\d{2})?"
    r"|(?:4K|8K|720P|1080P?|1440P|2160P?|HDR|DV|WEB(?:-DL)?|DSNP|60FPS|120FPS|MAX|臻彩|内封|字幕)"
    r")$",
    re.IGNORECASE,
)
NON_CJK_ALIAS_TAIL_PATTERN = re.compile(
    r"^(?P<prefix>.*[\u4e00-\u9fff])\s+(?P<alias>"
    r"[A-Za-z\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f]"
    r"[A-Za-z0-9\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f\u4e00-\u9fff\s.'·・:：\-—_]*"
    r")$"
)
JAPANESE_ALIAS_TAIL_PATTERN = re.compile(
    r"^(?P<prefix>.*[\u4e00-\u9fff])\s+(?P<alias>"
    r"[\u4e00-\u9fff\u3040-\u30ff\s.'·・:：\-—_]*"
    r"[\u3041-\u3096\u30a1-\u30fa]"
    r"[\u4e00-\u9fff\u3040-\u30ff\s.'·・:：\-—_]*"
    r")$"
)
METADATA_LABEL_PATTERN = re.compile(
    r"^(?:国剧|国漫|国综|韩剧|日剧|日漫|美剧|英剧|欧美剧|英美剧|美漫|泰剧|港剧|台剧|大陆剧|国产剧|动漫|动画|电影|剧集|电视剧|"
    r"综艺|真人秀|纪录片|短剧|欧美剧|华剧|全\s*\d{1,4}(?:集|季|期)|\d{1,2}\s*[-~至]\s*\d{1,2}\s*季|"
    r"英语中字|简繁中字|内封.*字幕|外挂.*字幕|(?:4K|8K|1080P|2160P|HDR|DV|WEB|60FPS).*)$",
    re.IGNORECASE,
)


def _is_metadata_label(value: Any) -> bool:
    normalized = normalize_text(value, max_length=120)
    if not normalized:
        return True
    if METADATA_LABEL_PATTERN.fullmatch(normalized):
        return True
    if BRACKET_METADATA_PATTERN.fullmatch(normalized):
        return True
    return bool(GENERIC_METADATA_KEY_PATTERN.fullmatch(normalized))


def _extract_leading_bracket_title(text: str) -> str:
    candidate = normalize_text(text, max_length=255)
    while candidate:
        matched = LEADING_BRACKET_BLOCK_PATTERN.match(candidate)
        if matched is None:
            break
        label = normalize_text(matched.group(1), max_length=120)
        if not _is_metadata_label(label):
            return label
        candidate = candidate[matched.end() :].strip()
    return candidate


def _strip_outer_title_wrappers(text: str) -> str:
    candidate = normalize_text(text, max_length=255)
    while candidate:
        matched = OUTER_TITLE_WRAPPER_PATTERN.match(candidate)
        if matched is None:
            break
        candidate = normalize_text(matched.group(1), max_length=255)
    return candidate


def _strip_non_cjk_alias_tail(text: str) -> str:
    candidate = normalize_text(text, max_length=255)
    if not candidate or not CJK_PATTERN.search(candidate):
        return candidate
    japanese_match = JAPANESE_ALIAS_TAIL_PATTERN.match(candidate)
    if japanese_match is not None:
        prefix = normalize_text(japanese_match.group("prefix"), max_length=255)
        if prefix:
            return prefix
    script_transition = re.search(
        r"(?<=[\u4e00-\u9fff])(?=[\uac00-\ud7af\u0e00-\u0e7f])",
        candidate,
    )
    if script_transition is not None:
        prefix = normalize_text(candidate[: script_transition.start()], max_length=255)
        if prefix:
            return prefix
    matched = NON_CJK_ALIAS_TAIL_PATTERN.match(candidate)
    if matched is None:
        alias_start = None
        for whitespace in re.finditer(r"\s+", candidate):
            suffix = candidate[whitespace.end() :]
            first_token = re.split(r"\s+", suffix, maxsplit=1)[0]
            if re.search(r"[A-Za-z\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f]", first_token):
                alias_start = whitespace
                break
        if alias_start is None:
            return candidate
        prefix = normalize_text(candidate[: alias_start.start()], max_length=255)
        return prefix or candidate
    prefix = normalize_text(matched.group("prefix"), max_length=255)
    return prefix or candidate


def _detect_non_target_reason(text: str) -> str | None:
    normalized = normalize_text(text, max_length=500)
    if not normalized:
        return "empty_title"
    if PLATFORM_LABEL_PATTERN.fullmatch(normalized):
        return "link_platform_label"
    if any(pattern.search(normalized) for pattern in DIRECTORY_NOISE_PATTERNS):
        return "directory_index"
    if AUDIO_NOISE_PATTERN.search(normalized):
        return "audio_drama"
    if PRINTED_MEDIA_NOISE_PATTERN.search(normalized):
        return "printed_media"
    if COURSE_NOISE_PATTERN.search(normalized):
        return "course_material"
    if SOFTWARE_NOISE_PATTERN.search(normalized):
        return "software_or_game"
    if MUSIC_NOISE_PATTERN.search(normalized) and not _looks_like_structured_video_title(normalized):
        return "music_audio"
    return None


def _looks_like_structured_video_title(text: str) -> bool:
    normalized = normalize_text(text, max_length=500)
    if not normalized:
        return False
    if _extract_season(normalized) is not None:
        return True
    if _extract_episode(normalized) is not None:
        return True
    issue_no, _issue_sort_value = _extract_issue(normalized)
    if issue_no is not None:
        return True
    return False


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


def _strip_trailing_person_list(text: str) -> str:
    candidate = normalize_text(text, max_length=255)
    if not candidate:
        return ""
    matched = TRAILING_PERSON_LIST_PATTERN.match(candidate)
    if matched is None:
        return candidate
    prefix = normalize_text(matched.group(1), max_length=255)
    return prefix or candidate


def _clean_title_candidate(text: str) -> str:
    candidate = _extract_leading_bracket_title(_strip_title_prefixes(text))
    candidate = _strip_outer_title_wrappers(candidate)
    if not candidate:
        return ""
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        candidate = LEADING_METADATA_PATTERN.sub("", candidate, count=1).strip()
    cut_index = _find_meta_cut_index(candidate)
    if cut_index is not None and cut_index > 0:
        candidate = candidate[:cut_index].strip()
    candidate = _strip_outer_title_wrappers(candidate)
    candidate = _strip_non_cjk_alias_tail(candidate)
    candidate = _strip_trailing_person_list(candidate)
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        for pattern in TRAILING_NOISE_PATTERNS:
            candidate = pattern.sub(" ", candidate)
        candidate = re.sub(
            r"\s*[（(](?:原版|重制版|导演剪辑版|加长版|特别版)\s*[）)]\s*$",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s+", " ", candidate).strip(" -_|/,.，。:：;；[]【】()（）<>《》")
        candidate = _strip_non_cjk_alias_tail(candidate)
        candidate = _trim_repeated_tail(candidate)
    if not candidate:
        return ""
    if PLATFORM_LABEL_PATTERN.fullmatch(candidate):
        return ""
    if candidate in GENERIC_EMPTY_TITLES:
        return ""
    if not is_meaningful_identity_key(candidate):
        return ""
    return normalize_text(candidate, max_length=255)


def _extract_english_alias_candidates(base_title: str) -> list[str]:
    normalized = normalize_text(base_title, max_length=255)
    if not normalized or not CJK_PATTERN.search(normalized) or not ASCII_PATTERN.search(normalized):
        return []
    english_start = re.search(r"(?:^|\s)([A-Za-z][A-Za-z0-9 .:'-]{2,})", normalized)
    if english_start is None:
        return []
    english_tail = normalize_text(english_start.group(1), max_length=255)
    english_tail = ENGLISH_ALIAS_META_PATTERN.sub("", english_tail).strip(" -_|/,.;:[](){}")
    if not english_tail or not ASCII_PATTERN.search(english_tail):
        return []
    if len(english_tail.split()) == 1 and len(english_tail) <= 4:
        return []
    matched_tail = ENGLISH_ALIAS_TAIL_PATTERN.search(english_tail)
    if matched_tail is None:
        return []
    candidate = normalize_text(matched_tail.group(1), max_length=255)
    return [candidate] if candidate else []


def _split_alias_candidates(base_title: str) -> list[str]:
    normalized = _strip_trailing_person_list(base_title)
    split_parts = [
        part
        for part in ALIAS_SPLIT_PATTERN.split(normalized)
        if normalize_text(part, max_length=255)
    ]
    parts = split_parts or [normalized]

    parts.extend(_extract_english_alias_candidates(normalized))

    return [normalize_text(part, max_length=255) for part in parts if normalize_text(part, max_length=255)]


def _score_title_candidate(
    title: str,
    *,
    source_index: int,
    full_title: str,
    candidate_index: int = 0,
) -> float:
    normalized_key = normalize_match_key(title)
    if not normalized_key:
        return 0.0
    score = 0.4
    key_length = len(normalized_key)
    if 2 <= key_length <= 18:
        score += 0.2
    elif key_length <= 32:
        score += 0.1
    if not GENERIC_METADATA_KEY_PATTERN.fullmatch(normalized_key):
        score += 0.15
    if full_title.startswith(title):
        score += 0.12
    if source_index == 0:
        score += 0.08
    if candidate_index == 0:
        score += 0.22
    if CJK_PATTERN.search(title):
        score += 0.03
    if len(title.split()) <= 4:
        score += 0.04
    if len(title) > 48:
        score -= 0.1
    return max(0.0, min(score, 0.999))


def _extract_title_candidates(raw_title: str, *, source_index: int) -> list[tuple[str, float]]:
    cleaned = _extract_leading_bracket_title(_strip_title_prefixes(raw_title))
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
        for candidate_index, part in enumerate(_split_alias_candidates(variant)):
            cleaned_part = _clean_title_candidate(part)
            if not cleaned_part:
                continue
            score = _score_title_candidate(
                cleaned_part,
                source_index=source_index,
                full_title=cleaned,
                candidate_index=candidate_index,
            )
            candidates.append((cleaned_part, score))
    return candidates


def _build_search_queries(
    *,
    core_title: str | None,
    aliases: list[str],
    release_year: int | None,
    season: int | None,
) -> list[str]:
    if not core_title or not is_meaningful_identity_key(core_title):
        return []
    queries: list[str] = [core_title]
    if season is not None:
        queries.append(f"{core_title} 第{season}季")
        queries.append(f"{core_title} S{season:02d}")
    if release_year is not None:
        queries.append(f"{core_title} {release_year}")
    queries.extend(aliases)
    return _dedupe_texts(
        [item for item in queries if is_meaningful_identity_key(item)],
        max_items=4,
        max_length=80,
    )


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
    aliases = [alias for alias in aliases if is_meaningful_identity_key(alias)]

    release_year = _extract_year(raw_title)
    season = _extract_season(raw_title)
    episode = _extract_episode(raw_title)
    issue_no, issue_sort_value = _extract_issue(raw_title)
    is_complete = _detect_complete(raw_title)
    content_type = _guess_content_type(raw_title, episode=episode, issue_no=issue_no)
    if core_title and re.fullmatch(r"(?:19|20)\d{2}", normalize_text(core_title)):
        if episode is not None or issue_no is not None or re.search(r"(?:更新|更至?|第\s*\d+\s*集)", raw_title):
            core_title = None
            aliases = []
    search_queries = _build_search_queries(
        core_title=core_title,
        aliases=aliases,
        release_year=release_year,
        season=season,
    )
    normalized_keys = _dedupe_texts(
        [
            normalize_match_key(item)
            for item in [core_title, *aliases]
            if item and is_meaningful_identity_key(item)
        ],
        max_items=6,
        max_length=255,
    )

    confidence = sorted_candidates[0][1] if sorted_candidates else 0.0
    needs_ai_review = not core_title or confidence < 0.72
    if core_title and len(normalize_match_key(core_title)) < 2:
        has_structured_title_signal = any(
            value is not None
            for value in (release_year, season, episode, issue_no)
        )
        needs_ai_review = not (confidence >= 0.95 and has_structured_title_signal)

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
