import re
from typing import Iterable


_QUALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("8K", re.compile(r"(?<![A-Za-z0-9])(?:8K|4320P?)", re.IGNORECASE)),
    ("4K", re.compile(r"(?<![A-Za-z0-9])(?:4K|2160P?|UHD)", re.IGNORECASE)),
    ("2K", re.compile(r"(?<![A-Za-z0-9])2K", re.IGNORECASE)),
    ("1080P", re.compile(r"(?<![A-Za-z0-9])1080P?", re.IGNORECASE)),
    ("720P", re.compile(r"(?<![A-Za-z0-9])720P?", re.IGNORECASE)),
    ("REMUX", re.compile(r"(?<![A-Za-z0-9])REMUX(?![A-Za-z0-9])", re.IGNORECASE)),
    ("BLURAY", re.compile(r"(?<![A-Za-z0-9])(?:BLU[- ]?RAY|BDMV)(?![A-Za-z0-9])", re.IGNORECASE)),
    ("WEB-DL", re.compile(r"(?<![A-Za-z0-9])WEB[- ]?DL(?![A-Za-z0-9])", re.IGNORECASE)),
    ("WEBRIP", re.compile(r"(?<![A-Za-z0-9])WEB[- ]?RIP(?![A-Za-z0-9])", re.IGNORECASE)),
    ("HDTV", re.compile(r"(?<![A-Za-z0-9])HDTV(?![A-Za-z0-9])", re.IGNORECASE)),
    ("DV", re.compile(r"(?<![A-Za-z0-9])DV(?![A-Za-z0-9])", re.IGNORECASE)),
    ("HDR", re.compile(r"(?<![A-Za-z0-9])HDR(?:10\+?)?(?![A-Za-z0-9])", re.IGNORECASE)),
    ("120FPS", re.compile(r"(?<!\d)120\s*FPS|120\s*帧", re.IGNORECASE)),
    ("60FPS", re.compile(r"(?<!\d)60\s*FPS|60\s*帧", re.IGNORECASE)),
    ("H265", re.compile(r"(?<![A-Za-z0-9])(?:H\.?265|HEVC|X265)(?![A-Za-z0-9])", re.IGNORECASE)),
    ("H264", re.compile(r"(?<![A-Za-z0-9])(?:H\.?264|AVC|X264)(?![A-Za-z0-9])", re.IGNORECASE)),
    ("10BIT", re.compile(r"(?<![A-Za-z0-9])10\s*BIT(?![A-Za-z0-9])", re.IGNORECASE)),
    ("FLAC", re.compile(r"(?<![A-Za-z0-9])FLAC(?![A-Za-z0-9])", re.IGNORECASE)),
    ("HIFI", re.compile(r"(?<![A-Za-z0-9])HIFI(?![A-Za-z0-9])", re.IGNORECASE)),
    ("DTS", re.compile(r"(?<![A-Za-z0-9])DTS(?![A-Za-z0-9])", re.IGNORECASE)),
    ("DDP5.1", re.compile(r"(?<![A-Za-z0-9])(?:DDP|DD)\s*5\.1(?![A-Za-z0-9])", re.IGNORECASE)),
)


def extract_quality_tags(text: str | None) -> list[str]:
    normalized = str(text or "")[:500]
    return [label for label, pattern in _QUALITY_PATTERNS if pattern.search(normalized)]


def quality_sort_key(value: str | Iterable[str] | None) -> tuple[int, int, int, int, int, int]:
    tags = set(extract_quality_tags(value) if isinstance(value, str) or value is None else value)
    resolution_rank = (
        5 if "8K" in tags else
        4 if "4K" in tags else
        3 if "2K" in tags else
        2 if "1080P" in tags else
        1 if "720P" in tags else
        0
    )
    source_rank = (
        4 if "REMUX" in tags else
        3 if "BLURAY" in tags else
        2 if "WEB-DL" in tags else
        1 if "WEBRIP" in tags or "HDTV" in tags else
        0
    )
    dynamic_range_rank = 3 if "DV" in tags else 2 if "HDR" in tags else 0
    frame_rate_rank = 2 if "120FPS" in tags else 1 if "60FPS" in tags else 0
    codec_rank = 2 if "H265" in tags else 1 if "H264" in tags else 0
    audio_rank = 2 if "FLAC" in tags or "DTS" in tags else 1 if "HIFI" in tags or "DDP5.1" in tags else 0
    return (resolution_rank, source_rank, dynamic_range_rank, frame_rate_rank, codec_rank, audio_rank)
