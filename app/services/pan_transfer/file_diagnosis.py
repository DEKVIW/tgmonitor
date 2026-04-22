from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import PanTransferAccount, PanTransferSyncTask, ensure_runtime_storage_tables
from app.services.resource_identity import normalize_match_key, parse_resource_identity

from .constants import PLATFORM_BAIDU, PLATFORM_QUARK, normalize_transfer_platform
from .follow_tasks import (
    _append_follow_task_log,
    _build_follow_identity_fallback,
    _get_follow_task,
    _normalize_optional_int,
    _normalize_text,
    _parse_datetime,
)
from .providers import decrypt_account_credential
from .providers.baidu import _BaiduClient, _extract_share_access_context
from .providers.quark import _QuarkClient, _extract_passcode, _extract_pwd_id


_VIDEO_EXTENSIONS = {
    ".3gp",
    ".asf",
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

_RESOLUTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("8K", re.compile(r"\b(?:8K|4320P)\b", re.IGNORECASE)),
    ("4K", re.compile(r"\b(?:4K|2160P|UHD)\b", re.IGNORECASE)),
    ("1080P", re.compile(r"\b1080P\b", re.IGNORECASE)),
    ("720P", re.compile(r"\b720P\b", re.IGNORECASE)),
)
_QUALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DV", re.compile(r"\bDV\b", re.IGNORECASE)),
    ("HDR", re.compile(r"\bHDR(?:10\+?)?\b", re.IGNORECASE)),
    ("60FPS", re.compile(r"\b60FPS\b", re.IGNORECASE)),
    ("H265", re.compile(r"\b(?:H\.?265|HEVC|X265)\b", re.IGNORECASE)),
    ("H264", re.compile(r"\b(?:H\.?264|X264|AVC)\b", re.IGNORECASE)),
    ("10BIT", re.compile(r"\b10BIT\b", re.IGNORECASE)),
    ("FLAC", re.compile(r"\bFLAC\b", re.IGNORECASE)),
    ("HIFI", re.compile(r"\bHIFI\b", re.IGNORECASE)),
    ("DTS", re.compile(r"\bDTS\b", re.IGNORECASE)),
    ("DDP5.1", re.compile(r"\b(?:DDP|DD)\s*5\.1\b", re.IGNORECASE)),
)
_SEASON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9])S(?:EASON\s*)?0*([1-9][0-9]?)(?=E|\b)", re.IGNORECASE),
    re.compile(r"第\s*([零一二三四五六七八九十百两\d]{1,4})\s*季"),
    re.compile(r"年番\s*([0-9]{1,2})", re.IGNORECASE),
)
_EPISODE_RANGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9])S\d{1,2}\s*E0*(\d{1,4})\s*[-~至]\s*E?\s*0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])EP?\s*0*(\d{1,4})\s*[-~至]\s*EP?\s*0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,4})\s*[-~至]\s*0*(\d{1,4})\s*[集话話]"),
)
_EPISODE_SINGLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9])S\d{1,2}E0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])EP?\s*0*(\d{1,4})(?!\d)", re.IGNORECASE),
    re.compile(r"(?:更至|更新至|更新到|更新|更)\s*0*(\d{1,4})\s*/\s*\d{1,4}\s*[集话話]?"),
    re.compile(r"(?:更至|更新至|更新到|更)\s*0*(\d{1,4})\s*[集话話]"),
    re.compile(r"第\s*0*(\d{1,4})\s*[集话話]"),
)
_NO_EPISODE_HINT_PATTERN = re.compile(r"\b(?:预告|花絮|海报|封面|字幕|片头|片尾|ost|mv|合集|全集)\b", re.IGNORECASE)
_DIGIT_AT_END_PATTERN = re.compile(r"(?:^|[^\d])(\d{1,4})(?:\D*)$")

_DEFAULT_NEAR_EPISODE_WINDOW = 5
_DEFAULT_MAX_SCAN_DIRS = 24
_DEFAULT_MAX_SCAN_FILES = 240
_DEFAULT_MAX_RESPONSE_ENTRIES = 160
_DEFAULT_MAX_RECENT_NO_EPISODE_FULL_PARSE = 12
_DEFAULT_FULL_PARSE_BATCH = 48
_WINDOW_EXPANSIONS = (5, 12, 20)


@dataclass(slots=True)
class _DirectoryRef:
    entry_id: str | None
    path: str | None
    name: str | None
    relative_path: str | None
    updated_at: datetime | None
    depth: int = 0


@dataclass(slots=True)
class _FileEntry:
    side: str
    name: str
    entry_id: str | None
    path: str | None
    parent_entry_id: str | None
    parent_path: str | None
    parent_name: str | None
    relative_parent_path: str | None
    updated_at: datetime | None
    size_bytes: int | None
    extension: str | None
    scan_order: int
    is_video: bool = False
    episode_numbers: list[int] = field(default_factory=list)
    quick_episode_numbers: list[int] = field(default_factory=list)
    season: int | None = None
    quick_season: int | None = None
    core_title: str | None = None
    parse_level: str = "quick"
    parse_reason: str = "quick_episode"
    confidence: float = 0.0
    title_match_score: float = 0.0
    quality_tags: list[str] = field(default_factory=list)
    within_window: bool = False
    accepted: bool = False
    selected: bool = False
    target_relative_path: str | None = None

    @property
    def sort_episode(self) -> int:
        if self.episode_numbers:
            return max(self.episode_numbers)
        if self.quick_episode_numbers:
            return max(self.quick_episode_numbers)
        return -1

    @property
    def unique_key(self) -> str:
        return self.entry_id or self.path or f"{self.parent_path or ''}/{self.name}"


@dataclass(slots=True)
class _DiagnosisStats:
    source_dir_count: int = 0
    target_dir_count: int = 0
    source_file_count: int = 0
    target_file_count: int = 0
    source_video_count: int = 0
    target_video_count: int = 0
    quick_parsed_count: int = 0
    full_parsed_count: int = 0
    skipped_outside_window_count: int = 0
    recent_without_episode_full_parse_count: int = 0
    expansions_used: int = 0
    warnings: list[str] = field(default_factory=list)
    stop_reason: str = ""


def _normalize_path_parts(value: str | None) -> list[str]:
    return [part for part in str(value or "").replace("\\", "/").split("/") if part.strip()]


def _join_relative_path(base_path: str | None, child_name: str) -> str | None:
    parts = [part for part in [base_path, _normalize_text(child_name, max_length=255)] if part]
    return "/".join(parts) or None


def _split_name_and_extension(name: str) -> tuple[str, str | None]:
    stem, extension = os.path.splitext(str(name or "").strip())
    normalized_extension = extension.lower() or None
    return stem or str(name or "").strip(), normalized_extension


def _chinese_number_to_int(value: str | None) -> int | None:
    text = _normalize_text(value, max_length=32)
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


def _is_video_name(name: str) -> bool:
    _, extension = _split_name_and_extension(name)
    if extension in _VIDEO_EXTENSIONS:
        return True
    normalized = _normalize_text(name, max_length=255)
    if not normalized or _NO_EPISODE_HINT_PATTERN.search(normalized):
        return False
    if any(pattern.search(normalized) for pattern in _EPISODE_RANGE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in _EPISODE_SINGLE_PATTERNS):
        return True
    return bool(_extract_quality_tags(normalized))


def _extract_quality_tags(text: str) -> list[str]:
    tags: list[str] = []
    normalized = _normalize_text(text, max_length=500)
    for label, pattern in _RESOLUTION_PATTERNS + _QUALITY_PATTERNS:
        if pattern.search(normalized):
            tags.append(label)
    return tags


def _extract_season_quick(text: str) -> int | None:
    normalized = _normalize_text(text, max_length=500)
    for pattern in _SEASON_PATTERNS:
        matched = pattern.search(normalized)
        if matched is None:
            continue
        value = _chinese_number_to_int(matched.group(1))
        if value > 0:
            return value
    return None


def _expand_episode_range(start: int, end: int) -> list[int]:
    lower = min(start, end)
    upper = max(start, end)
    if lower <= 0 or upper <= 0 or upper - lower > 20:
        return [upper]
    return list(range(lower, upper + 1))


def _extract_episode_numbers_quick(text: str) -> list[int]:
    normalized = _normalize_text(text, max_length=500)
    if not normalized or _NO_EPISODE_HINT_PATTERN.search(normalized):
        return []
    for pattern in _EPISODE_RANGE_PATTERNS:
        matched = pattern.search(normalized)
        if matched is None:
            continue
        try:
            start = int(matched.group(1))
            end = int(matched.group(2))
        except (TypeError, ValueError):
            continue
        return _expand_episode_range(start, end)
    values: list[int] = []
    for pattern in _EPISODE_SINGLE_PATTERNS:
        for matched in pattern.findall(normalized):
            try:
                values.append(int(matched))
            except (TypeError, ValueError):
                continue
    positive_values = [value for value in values if value > 0]
    if positive_values:
        highest = max(positive_values)
        return [highest] if highest > 0 else []
    if any(char.isdigit() for char in normalized):
        trailing = _DIGIT_AT_END_PATTERN.search(normalized)
        if trailing is not None:
            try:
                guessed = int(trailing.group(1))
            except (TypeError, ValueError):
                guessed = 0
            if 0 < guessed <= 500:
                return [guessed]
    return []


def _build_parse_title(entry: _FileEntry) -> str:
    stem, _extension = _split_name_and_extension(entry.name)
    parent_context = []
    if entry.parent_name:
        parent_context.append(entry.parent_name)
    if entry.relative_parent_path:
        parts = [part for part in entry.relative_parent_path.split("/") if part]
        parent_context.extend(parts[-2:])
    return " / ".join([*parent_context, stem]) if parent_context else stem


def _score_title_match(entry: _FileEntry, *, tracked_keys: set[str]) -> float:
    if not tracked_keys:
        return 0.0
    path_key = normalize_match_key(" ".join(filter(None, [entry.parent_name, entry.relative_parent_path, entry.name])))
    if any(key and key in path_key for key in tracked_keys):
        return 1.0
    return 0.0


def _full_parse_entry(entry: _FileEntry, *, tracked_keys: set[str], tracked_season: int | None) -> None:
    identity = parse_resource_identity(_build_parse_title(entry))
    resolved_episodes = list(entry.quick_episode_numbers)
    if identity.episode and identity.episode not in resolved_episodes:
        resolved_episodes.append(int(identity.episode))
    resolved_episodes = sorted({int(value) for value in resolved_episodes if int(value) > 0})
    match_score = _score_title_match(entry, tracked_keys=tracked_keys)
    if identity.core_title and identity.normalized_keys:
        if any(key in tracked_keys for key in identity.normalized_keys if key):
            match_score = max(match_score, 1.0)
        elif match_score <= 0:
            match_score = 0.25
    entry.parse_level = "full"
    entry.core_title = identity.core_title
    entry.confidence = float(identity.confidence or 0.0)
    entry.title_match_score = float(match_score)
    entry.quick_season = entry.quick_season or identity.season
    entry.season = identity.season or entry.quick_season
    entry.quick_episode_numbers = list(entry.quick_episode_numbers or resolved_episodes)
    entry.episode_numbers = resolved_episodes
    if not entry.quality_tags:
        entry.quality_tags = _extract_quality_tags(identity.raw_title)
    season_value = entry.season or tracked_season
    if tracked_season is not None and season_value is not None and season_value != tracked_season:
        entry.accepted = False
        entry.parse_reason = "season_mismatch"
        return
    if entry.episode_numbers:
        if match_score >= 0.55 or not tracked_keys:
            entry.accepted = True
            entry.parse_reason = "full_match"
            return
        if match_score > 0 and entry.parent_name:
            entry.accepted = True
            entry.parse_reason = "parent_context_match"
            return
    entry.accepted = False
    entry.parse_reason = "full_unmatched"


def _serialize_file_entry(entry: _FileEntry) -> dict[str, Any]:
    return {
        "side": entry.side,
        "name": entry.name,
        "entry_id": entry.entry_id,
        "path": entry.path,
        "parent_entry_id": entry.parent_entry_id,
        "parent_path": entry.parent_path,
        "parent_name": entry.parent_name,
        "relative_parent_path": entry.relative_parent_path,
        "updated_at": entry.updated_at,
        "size_bytes": entry.size_bytes,
        "extension": entry.extension,
        "episode_numbers": list(entry.episode_numbers or entry.quick_episode_numbers),
        "season": entry.season or entry.quick_season,
        "core_title": entry.core_title,
        "parse_level": entry.parse_level,
        "parse_reason": entry.parse_reason,
        "confidence": entry.confidence,
        "title_match_score": entry.title_match_score,
        "quality_tags": list(entry.quality_tags),
        "within_window": entry.within_window,
        "accepted": entry.accepted,
        "selected": entry.selected,
        "target_relative_path": entry.target_relative_path,
    }


def _pick_best_entry(entries: list[_FileEntry]) -> _FileEntry:
    def sort_key(item: _FileEntry) -> tuple[int, int, int, float, float, float, int]:
        resolution_rank = 0
        if "8K" in item.quality_tags:
            resolution_rank = 4
        elif "4K" in item.quality_tags:
            resolution_rank = 3
        elif "1080P" in item.quality_tags:
            resolution_rank = 2
        elif "720P" in item.quality_tags:
            resolution_rank = 1
        updated_ts = int(item.updated_at.timestamp()) if item.updated_at is not None else 0
        return (
            1 if item.parse_level == "full" else 0,
            1 if item.accepted else 0,
            resolution_rank,
            float(item.title_match_score or 0.0),
            float(item.confidence or 0.0),
            float(item.size_bytes or 0),
            updated_ts,
        )

    return max(entries, key=sort_key)


def _infer_target_relative_path(target_entries: list[_FileEntry], *, anchor_episode: int | None) -> str | None:
    scores: dict[str, float] = {}
    for entry in target_entries:
        if not entry.quick_episode_numbers and not entry.episode_numbers:
            continue
        relative_parent_path = entry.relative_parent_path or ""
        episode_numbers = entry.episode_numbers or entry.quick_episode_numbers
        if not episode_numbers:
            continue
        score = 1.0
        if anchor_episode is not None:
            score = max(0.5, 10.0 - min(abs(max(episode_numbers) - anchor_episode), 9))
        scores[relative_parent_path] = scores.get(relative_parent_path, 0.0) + score
    if not scores:
        return None
    best_path, best_score = max(scores.items(), key=lambda item: item[1])
    return best_path or None if best_score > 0 else None


async def infer_follow_task_target_relative_path(
    session: Session,
    *,
    task_id: int,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)

    account = session.get(PanTransferAccount, int(task.target_account_id or 0))
    if account is None:
        raise LookupError("target account not found")
    credential_value = decrypt_account_credential(account)
    if not credential_value:
        raise ValueError("target account credential is empty")

    snapshot = _collect_tracked_snapshot(task)
    tracked_episode = _normalize_optional_int(snapshot.get("latest_episode"))
    tracked_season = _normalize_optional_int(snapshot.get("season"))
    tracked_keys = _build_tracked_keys(snapshot)

    stats = _DiagnosisStats()
    platform = normalize_transfer_platform(_normalize_text(task.platform, max_length=64))
    if platform == PLATFORM_QUARK:
        target_entries, stats.target_dir_count = await _scan_quark_target_entries(
            credential_value=credential_value,
            fixed_save_path=task.fixed_save_path,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
    elif platform == PLATFORM_BAIDU:
        target_entries, stats.target_dir_count = await _scan_baidu_target_entries(
            credential_value=credential_value,
            fixed_save_path=task.fixed_save_path,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
    else:
        raise ValueError(f"unsupported follow diagnosis platform: {task.platform}")

    stats.target_file_count = len(target_entries)
    target_video_entries = _prepare_quick_entries(target_entries, stats=stats)
    stats.target_video_count = len(target_video_entries)

    latest_target_episode = _collect_latest_target_episode(
        target_video_entries,
        tracked_season=tracked_season,
    )
    anchor_episode = _resolve_anchor_episode(
        tracked_episode=tracked_episode,
        latest_target_episode=latest_target_episode,
    )

    target_full_parse_candidates = _select_full_parse_candidates(
        target_video_entries,
        tracked_episode=anchor_episode,
        near_episode_window=max(2, _DEFAULT_NEAR_EPISODE_WINDOW // 2),
        stats=stats,
    )
    for entry in target_full_parse_candidates:
        _full_parse_entry(entry, tracked_keys=tracked_keys, tracked_season=tracked_season)
        stats.full_parsed_count += 1

    _apply_target_quick_acceptance(target_video_entries, tracked_season=tracked_season)
    latest_target_episode = _collect_latest_target_episode(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=True,
    ) or latest_target_episode
    anchor_episode = _resolve_anchor_episode(
        tracked_episode=tracked_episode,
        latest_target_episode=latest_target_episode,
    )

    relevant_target_entries = _select_target_anchor_entries(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=True,
    ) or _select_target_anchor_entries(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=False,
    )
    inferred_target_relative_path = _infer_target_relative_path(relevant_target_entries, anchor_episode=anchor_episode)
    return {
        "preferred_target_relative_path": inferred_target_relative_path,
        "tracked_episode": tracked_episode,
        "latest_target_episode": latest_target_episode,
        "target_dir_count": stats.target_dir_count,
        "target_file_count": stats.target_file_count,
        "target_video_count": stats.target_video_count,
        "quick_parsed_count": stats.quick_parsed_count,
        "full_parsed_count": stats.full_parsed_count,
    }


def _build_sync_selection_groups(entries: list[_FileEntry], *, target_relative_path: str | None) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str | None, str | None, str | None], list[_FileEntry]] = {}
    for entry in entries:
        group_key = (
            entry.parent_entry_id,
            entry.parent_path,
            entry.parent_name,
            target_relative_path,
        )
        grouped.setdefault(group_key, []).append(entry)
    selection_groups: list[dict[str, Any]] = []
    for (parent_entry_id, parent_path, parent_name, relative_path), group_entries in grouped.items():
        normalized_entries: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in sorted(group_entries, key=lambda item: (item.sort_episode, item.name)):
            dedupe_key = (entry.entry_id or "", entry.path or "", entry.name)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_entries.append(
                {
                    "name": entry.name,
                    "is_dir": False,
                    "entry_id": entry.entry_id,
                    "path": entry.path,
                }
            )
        if not normalized_entries:
            continue
        selection_groups.append(
            {
                "parent_entry_id": parent_entry_id,
                "parent_path": parent_path,
                "parent_name": parent_name,
                "target_relative_path": relative_path,
                "selected_entries": normalized_entries,
                "selected_count": len(normalized_entries),
            }
        )
    selection_groups.sort(
        key=lambda item: (
            _normalize_text(item.get("target_relative_path")),
            _normalize_text(item.get("parent_path")),
            _normalize_text(item.get("parent_entry_id")),
        )
    )
    return selection_groups


def _build_plan_preview(entries: list[_FileEntry], *, target_relative_path: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.unique_key in seen:
            continue
        seen.add(entry.unique_key)
        items.append(
            {
                "name": entry.name,
                "path": entry.path,
                "parent_path": entry.parent_path,
                "episodes": list(entry.episode_numbers or entry.quick_episode_numbers),
                "season": entry.season or entry.quick_season,
                "updated_at": entry.updated_at,
                "size_bytes": entry.size_bytes,
                "quality_tags": list(entry.quality_tags),
                "parse_level": entry.parse_level,
                "parse_reason": entry.parse_reason,
                "target_relative_path": entry.target_relative_path or target_relative_path,
            }
        )
    return items


def _collect_episode_numbers(entries: list[_FileEntry], *, accepted_only: bool = False) -> list[int]:
    values: set[int] = set()
    for entry in entries:
        if accepted_only and not entry.accepted:
            continue
        for episode in entry.episode_numbers or entry.quick_episode_numbers:
            if int(episode) > 0:
                values.add(int(episode))
    return sorted(values)


def _build_full_replace_entries(source_entries: list[_FileEntry]) -> tuple[list[_FileEntry], list[int]]:
    grouped: dict[int, list[_FileEntry]] = {}
    for entry in source_entries:
        if not entry.accepted:
            continue
        for episode in entry.episode_numbers or entry.quick_episode_numbers:
            if int(episode) <= 0:
                continue
            grouped.setdefault(int(episode), []).append(entry)
    if not grouped:
        return [], []

    selected_entries: list[_FileEntry] = []
    selected_keys: set[str] = set()
    selected_episode_numbers: list[int] = []
    for episode in sorted(grouped):
        best_entry = _pick_best_entry(grouped[episode])
        if best_entry.unique_key not in selected_keys:
            selected_entries.append(best_entry)
            selected_keys.add(best_entry.unique_key)
        selected_episode_numbers.append(int(episode))
    return selected_entries, selected_episode_numbers


async def _scan_quark_source_entries(
    *,
    credential_value: str,
    source_url: str,
    max_scan_dirs: int,
    max_scan_files: int,
) -> tuple[list[_FileEntry], int]:
    async with _QuarkClient(credential_value) as client:
        pwd_id = _extract_pwd_id(source_url)
        stoken = await client.get_stoken(pwd_id=pwd_id, passcode=_extract_passcode(source_url))
        queue: list[_DirectoryRef] = [
            _DirectoryRef(entry_id="0", path=None, name=None, relative_path=None, updated_at=None, depth=0)
        ]
        results: list[_FileEntry] = []
        visited_dir_count = 0
        scan_order = 0
        while queue and visited_dir_count < max_scan_dirs and len(results) < max_scan_files:
            current = queue.pop(0)
            rows = await client.get_share_detail(pwd_id=pwd_id, stoken=stoken, parent_id=str(current.entry_id or "0"))
            visited_dir_count += 1
            normalized_dirs: list[_DirectoryRef] = []
            for row in rows:
                name = _normalize_text(row.get("file_name"), max_length=255)
                if not name:
                    continue
                entry_id = _normalize_text(row.get("fid"), max_length=255) or None
                updated_at = _parse_datetime(row.get("updated_at") or row.get("obj_update_time"))
                relative_parent_path = current.relative_path
                parent_path = f"/{relative_parent_path}" if relative_parent_path else None
                if bool(row.get("dir")):
                    normalized_dirs.append(
                        _DirectoryRef(
                            entry_id=entry_id,
                            path=_join_relative_path(parent_path, name),
                            name=name,
                            relative_path=_join_relative_path(relative_parent_path, name),
                            updated_at=updated_at,
                            depth=current.depth + 1,
                        )
                    )
                    continue
                scan_order += 1
                results.append(
                    _FileEntry(
                        side="source",
                        name=name,
                        entry_id=entry_id,
                        path=_join_relative_path(relative_parent_path, name) and f"/{_join_relative_path(relative_parent_path, name)}",
                        parent_entry_id=current.entry_id if current.entry_id != "0" else None,
                        parent_path=parent_path,
                        parent_name=current.name,
                        relative_parent_path=relative_parent_path,
                        updated_at=updated_at,
                        size_bytes=_normalize_optional_int(row.get("size")),
                        extension=_split_name_and_extension(name)[1],
                        scan_order=scan_order,
                    )
                )
                if len(results) >= max_scan_files:
                    break
            normalized_dirs.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
            queue = sorted([*queue, *normalized_dirs], key=lambda item: item.updated_at or datetime.min, reverse=True)
    return results, visited_dir_count


async def _scan_quark_target_entries(
    *,
    credential_value: str,
    fixed_save_path: str,
    max_scan_dirs: int,
    max_scan_files: int,
) -> tuple[list[_FileEntry], int]:
    async with _QuarkClient(credential_value) as client:
        parent_id = "0"
        current_relative_path: str | None = None
        current_name: str | None = None
        for segment in _normalize_path_parts(fixed_save_path):
            rows = await client.list_dir_all(parent_id=parent_id)
            matched = next(
                (
                    row
                    for row in rows
                    if str(row.get("file_name") or "").strip() == segment and bool(row.get("dir"))
                ),
                None,
            )
            if matched is None:
                raise ValueError(f"resource directory segment not found: {segment}")
            parent_id = _normalize_text(matched.get("fid"), max_length=255) or ""
            if not parent_id:
                raise ValueError(f"resource directory segment is missing fid: {segment}")
            current_relative_path = _join_relative_path(current_relative_path, segment)
            current_name = segment

        queue: list[_DirectoryRef] = [
            _DirectoryRef(
                entry_id=parent_id,
                path=f"/{current_relative_path}" if current_relative_path else None,
                name=current_name,
                relative_path=None,
                updated_at=None,
                depth=0,
            )
        ]
        results: list[_FileEntry] = []
        visited_dir_count = 0
        scan_order = 0
        while queue and visited_dir_count < max_scan_dirs and len(results) < max_scan_files:
            current = queue.pop(0)
            rows = await client.list_dir_all(parent_id=str(current.entry_id or "0"))
            visited_dir_count += 1
            normalized_dirs: list[_DirectoryRef] = []
            for row in rows:
                name = _normalize_text(row.get("file_name"), max_length=255)
                if not name:
                    continue
                entry_id = _normalize_text(row.get("fid"), max_length=255) or None
                updated_at = _parse_datetime(row.get("updated_at") or row.get("obj_update_time"))
                relative_parent_path = current.relative_path
                if bool(row.get("dir")):
                    normalized_dirs.append(
                        _DirectoryRef(
                            entry_id=entry_id,
                            path=_join_relative_path(current.path, name),
                            name=name,
                            relative_path=_join_relative_path(relative_parent_path, name),
                            updated_at=updated_at,
                            depth=current.depth + 1,
                        )
                    )
                    continue
                scan_order += 1
                results.append(
                    _FileEntry(
                        side="target",
                        name=name,
                        entry_id=entry_id,
                        path=_join_relative_path(current.path, name),
                        parent_entry_id=current.entry_id,
                        parent_path=current.path,
                        parent_name=current.name,
                        relative_parent_path=relative_parent_path,
                        updated_at=updated_at,
                        size_bytes=_normalize_optional_int(row.get("size")),
                        extension=_split_name_and_extension(name)[1],
                        scan_order=scan_order,
                    )
                )
                if len(results) >= max_scan_files:
                    break
            normalized_dirs.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
            queue = sorted([*queue, *normalized_dirs], key=lambda item: item.updated_at or datetime.min, reverse=True)
    return results, visited_dir_count


async def _scan_baidu_source_entries(
    *,
    credential_value: str,
    source_url: str,
    max_scan_dirs: int,
    max_scan_files: int,
) -> tuple[list[_FileEntry], int]:
    async with _BaiduClient(credential_value) as client:
        bdstoken, _validation = await client.get_bdstoken()
        share_key, requires_prefix_strip, url_passcode = _extract_share_access_context(source_url)
        if url_passcode:
            await client.verify_pass_code(share_key=share_key, passcode=url_passcode, bdstoken=bdstoken)
        queue: list[_DirectoryRef] = [
            _DirectoryRef(entry_id=None, path=None, name=None, relative_path=None, updated_at=None, depth=0)
        ]
        results: list[_FileEntry] = []
        visited_dir_count = 0
        scan_order = 0
        while queue and visited_dir_count < max_scan_dirs and len(results) < max_scan_files:
            current = queue.pop(0)
            rows = await client.list_share_dir(
                share_key=share_key,
                requires_prefix_strip=requires_prefix_strip,
                dir_path=current.path,
            )
            visited_dir_count += 1
            normalized_dirs: list[_DirectoryRef] = []
            for row in rows:
                name = _normalize_text(row.get("server_filename"), max_length=255)
                if not name:
                    continue
                entry_id = _normalize_text(row.get("fs_id"), max_length=255) or None
                row_path = _normalize_text(row.get("path"), max_length=1024) or None
                updated_at = _parse_datetime(row.get("server_mtime"))
                relative_parent_path = current.relative_path
                if int(row.get("isdir") or 0) == 1:
                    normalized_dirs.append(
                        _DirectoryRef(
                            entry_id=entry_id,
                            path=row_path,
                            name=name,
                            relative_path=_join_relative_path(relative_parent_path, name),
                            updated_at=updated_at,
                            depth=current.depth + 1,
                        )
                    )
                    continue
                scan_order += 1
                results.append(
                    _FileEntry(
                        side="source",
                        name=name,
                        entry_id=entry_id,
                        path=row_path,
                        parent_entry_id=None,
                        parent_path=current.path,
                        parent_name=current.name,
                        relative_parent_path=relative_parent_path,
                        updated_at=updated_at,
                        size_bytes=_normalize_optional_int(row.get("size")),
                        extension=_split_name_and_extension(name)[1],
                        scan_order=scan_order,
                    )
                )
                if len(results) >= max_scan_files:
                    break
            normalized_dirs.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
            queue = sorted([*queue, *normalized_dirs], key=lambda item: item.updated_at or datetime.min, reverse=True)
    return results, visited_dir_count


async def _scan_baidu_target_entries(
    *,
    credential_value: str,
    fixed_save_path: str,
    max_scan_dirs: int,
    max_scan_files: int,
) -> tuple[list[_FileEntry], int]:
    target_path = "/" + "/".join(_normalize_path_parts(fixed_save_path))
    target_path = target_path if target_path != "/" else "/"
    async with _BaiduClient(credential_value) as client:
        bdstoken, _validation = await client.get_bdstoken()
        root_rows = await client.list_dir(target_path, bdstoken=bdstoken)
        if isinstance(root_rows, int):
            raise ValueError(f"resource directory not found: errno {root_rows}")
        queue: list[_DirectoryRef] = [
            _DirectoryRef(
                entry_id=None,
                path=target_path,
                name=_normalize_path_parts(fixed_save_path)[-1] if _normalize_path_parts(fixed_save_path) else None,
                relative_path=None,
                updated_at=None,
                depth=0,
            )
        ]
        results: list[_FileEntry] = []
        visited_dir_count = 0
        scan_order = 0
        while queue and visited_dir_count < max_scan_dirs and len(results) < max_scan_files:
            current = queue.pop(0)
            rows = await client.list_dir(str(current.path or "/"), bdstoken=bdstoken)
            if isinstance(rows, int):
                raise ValueError(f"resource directory scan failed: errno {rows}")
            visited_dir_count += 1
            normalized_dirs: list[_DirectoryRef] = []
            for row in rows:
                name = _normalize_text(row.get("server_filename"), max_length=255)
                if not name:
                    continue
                entry_id = _normalize_text(row.get("fs_id"), max_length=255) or None
                row_path = _normalize_text(row.get("path"), max_length=1024) or None
                updated_at = _parse_datetime(row.get("server_mtime"))
                relative_parent_path = current.relative_path
                if int(row.get("isdir") or 0) == 1:
                    normalized_dirs.append(
                        _DirectoryRef(
                            entry_id=entry_id,
                            path=row_path,
                            name=name,
                            relative_path=_join_relative_path(relative_parent_path, name),
                            updated_at=updated_at,
                            depth=current.depth + 1,
                        )
                    )
                    continue
                scan_order += 1
                results.append(
                    _FileEntry(
                        side="target",
                        name=name,
                        entry_id=entry_id,
                        path=row_path,
                        parent_entry_id=None,
                        parent_path=current.path,
                        parent_name=current.name,
                        relative_parent_path=relative_parent_path,
                        updated_at=updated_at,
                        size_bytes=_normalize_optional_int(row.get("size")),
                        extension=_split_name_and_extension(name)[1],
                        scan_order=scan_order,
                    )
                )
                if len(results) >= max_scan_files:
                    break
            normalized_dirs.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
            queue = sorted([*queue, *normalized_dirs], key=lambda item: item.updated_at or datetime.min, reverse=True)
    return results, visited_dir_count


def _prepare_quick_entries(entries: list[_FileEntry], *, stats: _DiagnosisStats) -> list[_FileEntry]:
    videos: list[_FileEntry] = []
    for entry in entries:
        if not _is_video_name(entry.name):
            continue
        quick_parse_title = _build_parse_title(entry)
        entry.is_video = True
        entry.quick_episode_numbers = _extract_episode_numbers_quick(quick_parse_title)
        entry.quick_season = _extract_season_quick(quick_parse_title)
        entry.quality_tags = _extract_quality_tags(entry.name)
        if entry.quick_episode_numbers:
            entry.accepted = True
        stats.quick_parsed_count += 1
        videos.append(entry)
    videos.sort(
        key=lambda item: (
            item.updated_at or datetime.min,
            item.sort_episode,
            -item.scan_order,
        ),
        reverse=True,
    )
    for index, entry in enumerate(videos, start=1):
        entry.scan_order = index
    return videos


def _collect_tracked_snapshot(task: PanTransferSyncTask) -> dict[str, Any]:
    extra_json = dict(task.extra_json or {})
    existing_snapshot = dict(extra_json.get("identity_snapshot") or {})
    if existing_snapshot.get("core_title"):
        return existing_snapshot
    return _build_follow_identity_fallback(task)


def _build_tracked_keys(snapshot: dict[str, Any]) -> set[str]:
    values = [
        _normalize_text(snapshot.get("core_title"), max_length=255),
        *[_normalize_text(item, max_length=255) for item in list(snapshot.get("aliases") or [])[:8]],
        _normalize_text(snapshot.get("resource_title"), max_length=255),
    ]
    return {normalize_match_key(item) for item in values if normalize_match_key(item)}


def _entry_episode_numbers(entry: _FileEntry) -> list[int]:
    return [int(value) for value in (entry.episode_numbers or entry.quick_episode_numbers) if int(value) > 0]


def _entry_season_value(entry: _FileEntry) -> int | None:
    return _normalize_optional_int(entry.season or entry.quick_season)


def _filter_entries_by_tracked_season(entries: list[_FileEntry], *, tracked_season: int | None) -> list[_FileEntry]:
    if tracked_season is None:
        return list(entries)
    exact_entries = [entry for entry in entries if _entry_season_value(entry) == tracked_season]
    if exact_entries:
        return exact_entries
    seasonless_entries = [entry for entry in entries if _entry_season_value(entry) is None]
    return seasonless_entries or list(entries)


def _select_target_anchor_entries(
    entries: list[_FileEntry],
    *,
    tracked_season: int | None,
    accepted_only: bool = False,
) -> list[_FileEntry]:
    filtered = [
        entry
        for entry in entries
        if (not accepted_only or entry.accepted) and _entry_episode_numbers(entry)
    ]
    if not filtered:
        return []
    return _filter_entries_by_tracked_season(filtered, tracked_season=tracked_season)


def _collect_latest_target_episode(
    entries: list[_FileEntry],
    *,
    tracked_season: int | None,
    accepted_only: bool = False,
) -> int | None:
    relevant_entries = _select_target_anchor_entries(
        entries,
        tracked_season=tracked_season,
        accepted_only=accepted_only,
    )
    return max((max(_entry_episode_numbers(entry)) for entry in relevant_entries), default=None)


def _resolve_anchor_episode(*, tracked_episode: int | None, latest_target_episode: int | None) -> int | None:
    return max([value for value in [tracked_episode, latest_target_episode] if value is not None], default=None)


def _apply_target_quick_acceptance(entries: list[_FileEntry], *, tracked_season: int | None) -> None:
    for entry in entries:
        if entry.parse_level == "full":
            continue
        entry.accepted = False
        if tracked_season is not None and entry.quick_season is not None and entry.quick_season != tracked_season:
            entry.parse_reason = "season_mismatch"
            continue
        if entry.quick_episode_numbers:
            entry.accepted = True
            entry.parse_reason = "target_quick_episode"


def _select_full_parse_candidates(
    entries: list[_FileEntry],
    *,
    tracked_episode: int | None,
    near_episode_window: int,
    stats: _DiagnosisStats,
) -> list[_FileEntry]:
    selected: list[_FileEntry] = []
    parsed_keys: set[str] = set()

    def add_entries(predicate: Any, reason: str) -> None:
        for entry in entries:
            if entry.unique_key in parsed_keys:
                continue
            if not predicate(entry):
                continue
            entry.within_window = reason.startswith("window")
            if reason == "recent_no_episode":
                stats.recent_without_episode_full_parse_count += 1
            entry.parse_reason = reason
            selected.append(entry)
            parsed_keys.add(entry.unique_key)
            if len(selected) >= _DEFAULT_FULL_PARSE_BATCH:
                return

    if tracked_episode is None:
        add_entries(lambda entry: True, "no_anchor_recent")
        return selected

    expansions = [near_episode_window]
    for value in _WINDOW_EXPANSIONS:
        if value > near_episode_window:
            expansions.append(value)

    for index, window in enumerate(expansions):
        add_entries(
            lambda entry, window=window: bool(entry.quick_episode_numbers)
            and min(entry.quick_episode_numbers) <= tracked_episode + window
            and max(entry.quick_episode_numbers) >= max(1, tracked_episode - 1),
            f"window_{window}",
        )
        if selected:
            stats.expansions_used = index
            break

    if len(selected) < _DEFAULT_FULL_PARSE_BATCH:
        add_entries(
            lambda entry: not entry.quick_episode_numbers and entry.scan_order <= _DEFAULT_MAX_RECENT_NO_EPISODE_FULL_PARSE,
            "recent_no_episode",
        )

    higher_entries = [
        entry
        for entry in entries
        if entry.unique_key not in parsed_keys and entry.quick_episode_numbers and max(entry.quick_episode_numbers) > tracked_episode
    ]
    higher_entries.sort(key=lambda entry: max(entry.quick_episode_numbers))
    for entry in higher_entries[: max(0, _DEFAULT_FULL_PARSE_BATCH - len(selected))]:
        entry.parse_reason = "closest_higher"
        selected.append(entry)
        parsed_keys.add(entry.unique_key)

    stats.skipped_outside_window_count += max(0, len(entries) - len(selected))
    return selected


def _build_recommended_entries(
    source_entries: list[_FileEntry],
    *,
    anchor_episode: int | None,
    inferred_target_relative_path: str | None,
) -> tuple[list[_FileEntry], list[int], str]:
    if not source_entries:
        return [], [], "no_source_video"

    grouped: dict[int, list[_FileEntry]] = {}
    for entry in source_entries:
        if not entry.accepted:
            continue
        for episode in entry.episode_numbers or entry.quick_episode_numbers:
            if episode <= 0:
                continue
            grouped.setdefault(int(episode), []).append(entry)
    if not grouped:
        return [], [], "no_accepted_episode"

    start_episode = min(grouped) if anchor_episode is None else max(1, int(anchor_episode) + 1)
    expected = start_episode
    selected_entries: list[_FileEntry] = []
    selected_keys: set[str] = set()
    covered_episodes: set[int] = set()
    recommended_episode_numbers: list[int] = []
    while expected in grouped:
        best_entry = _pick_best_entry(grouped[expected])
        if best_entry.unique_key not in selected_keys:
            best_entry.selected = True
            best_entry.target_relative_path = inferred_target_relative_path
            selected_entries.append(best_entry)
            selected_keys.add(best_entry.unique_key)
        for episode in best_entry.episode_numbers or best_entry.quick_episode_numbers:
            covered_episodes.add(int(episode))
        recommended_episode_numbers.append(expected)
        expected += 1
        while expected in covered_episodes:
            recommended_episode_numbers.append(expected)
            expected += 1
    return selected_entries, sorted({int(value) for value in recommended_episode_numbers}), (
        "contiguous_window_hit" if recommended_episode_numbers else "gap_before_next_episode"
    )


def _build_diagnosis_summary(
    *,
    task: PanTransferSyncTask,
    source_kind: str,
    snapshot: dict[str, Any],
    anchor_episode: int | None,
    latest_target_episode: int | None,
    near_episode_window: int,
    stats: _DiagnosisStats,
    recommended_entries: list[_FileEntry],
    recommended_episode_numbers: list[int],
    inferred_target_relative_path: str | None,
    selection_groups: list[dict[str, Any]],
    full_entries: list[_FileEntry],
    full_episode_numbers: list[int],
    full_selection_groups: list[dict[str, Any]],
    target_entries: list[_FileEntry],
) -> dict[str, Any]:
    target_episode_numbers = _collect_episode_numbers(target_entries, accepted_only=True)
    return {
        "source_kind": source_kind,
        "tracked_resource_title": _normalize_text(snapshot.get("resource_title"), max_length=255)
        or _normalize_text(task.work_title, max_length=255)
        or _normalize_text(task.topic_title, max_length=255)
        or f"task_{int(task.id)}",
        "tracked_core_title": _normalize_text(snapshot.get("core_title"), max_length=255) or None,
        "tracked_season": _normalize_optional_int(snapshot.get("season")),
        "tracked_episode": _normalize_optional_int(snapshot.get("latest_episode")),
        "anchor_episode": anchor_episode,
        "latest_target_episode": latest_target_episode,
        "near_episode_window": int(near_episode_window),
        "source_dir_count": int(stats.source_dir_count),
        "target_dir_count": int(stats.target_dir_count),
        "source_file_count": int(stats.source_file_count),
        "target_file_count": int(stats.target_file_count),
        "source_video_count": int(stats.source_video_count),
        "target_video_count": int(stats.target_video_count),
        "quick_parsed_count": int(stats.quick_parsed_count),
        "full_parsed_count": int(stats.full_parsed_count),
        "skipped_outside_window_count": int(stats.skipped_outside_window_count),
        "recent_without_episode_full_parse_count": int(stats.recent_without_episode_full_parse_count),
        "expansions_used": int(stats.expansions_used),
        "recommended_entry_count": len(recommended_entries),
        "recommended_episode_numbers": list(recommended_episode_numbers),
        "selection_group_count": len(selection_groups),
        "source_latest_episode": max(full_episode_numbers, default=None),
        "source_episode_numbers": list(full_episode_numbers),
        "target_episode_numbers": target_episode_numbers,
        "full_entry_count": len(full_entries),
        "full_selection_group_count": len(full_selection_groups),
        "inferred_target_relative_path": inferred_target_relative_path,
        "warnings": list(stats.warnings),
        "stop_reason": stats.stop_reason,
    }


async def diagnose_pan_transfer_follow_task_files(
    session: Session,
    *,
    task_id: int,
    source_kind: str = "candidate",
    near_episode_window: int = _DEFAULT_NEAR_EPISODE_WINDOW,
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    normalized_source_kind = _normalize_text(source_kind, max_length=32).lower() or "candidate"
    if normalized_source_kind not in {"current", "candidate"}:
        raise ValueError("source_kind must be current or candidate")
    if normalized_source_kind == "candidate" and not _normalize_text(task.last_candidate_url):
        raise ValueError("current task has no candidate source to diagnose")
    normalized_window = int(max(1, min(int(near_episode_window or _DEFAULT_NEAR_EPISODE_WINDOW), 30)))

    account = session.get(PanTransferAccount, int(task.target_account_id or 0))
    if account is None:
        raise LookupError("target account not found")
    credential_value = decrypt_account_credential(account)
    if not credential_value:
        raise ValueError("target account credential is empty")

    snapshot = _collect_tracked_snapshot(task)
    tracked_episode = _normalize_optional_int(snapshot.get("latest_episode"))
    tracked_season = _normalize_optional_int(snapshot.get("season"))
    tracked_keys = _build_tracked_keys(snapshot)
    source_url = _normalize_text(task.last_candidate_url if normalized_source_kind == "candidate" else task.source_url)
    if not source_url:
        raise ValueError("source url is empty")

    stats = _DiagnosisStats()
    platform = normalize_transfer_platform(_normalize_text(task.platform, max_length=64))
    if platform == PLATFORM_QUARK:
        source_entries, stats.source_dir_count = await _scan_quark_source_entries(
            credential_value=credential_value,
            source_url=source_url,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
        target_entries, stats.target_dir_count = await _scan_quark_target_entries(
            credential_value=credential_value,
            fixed_save_path=task.fixed_save_path,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
    elif platform == PLATFORM_BAIDU:
        source_entries, stats.source_dir_count = await _scan_baidu_source_entries(
            credential_value=credential_value,
            source_url=source_url,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
        target_entries, stats.target_dir_count = await _scan_baidu_target_entries(
            credential_value=credential_value,
            fixed_save_path=task.fixed_save_path,
            max_scan_dirs=_DEFAULT_MAX_SCAN_DIRS,
            max_scan_files=_DEFAULT_MAX_SCAN_FILES,
        )
    else:
        raise ValueError(f"unsupported follow diagnosis platform: {task.platform}")

    stats.source_file_count = len(source_entries)
    stats.target_file_count = len(target_entries)
    source_video_entries = _prepare_quick_entries(source_entries, stats=stats)
    target_video_entries = _prepare_quick_entries(target_entries, stats=stats)
    stats.source_video_count = len(source_video_entries)
    stats.target_video_count = len(target_video_entries)

    latest_target_episode = _collect_latest_target_episode(
        target_video_entries,
        tracked_season=tracked_season,
    )
    anchor_episode = _resolve_anchor_episode(
        tracked_episode=tracked_episode,
        latest_target_episode=latest_target_episode,
    )

    source_full_parse_candidates = _select_full_parse_candidates(
        source_video_entries,
        tracked_episode=anchor_episode,
        near_episode_window=normalized_window,
        stats=stats,
    )
    target_full_parse_candidates = _select_full_parse_candidates(
        target_video_entries,
        tracked_episode=anchor_episode,
        near_episode_window=max(2, normalized_window // 2),
        stats=stats,
    )
    for entry in [*source_full_parse_candidates, *target_full_parse_candidates]:
        _full_parse_entry(entry, tracked_keys=tracked_keys, tracked_season=tracked_season)
        stats.full_parsed_count += 1

    _apply_target_quick_acceptance(target_video_entries, tracked_season=tracked_season)
    latest_target_episode = _collect_latest_target_episode(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=True,
    ) or latest_target_episode
    anchor_episode = _resolve_anchor_episode(
        tracked_episode=tracked_episode,
        latest_target_episode=latest_target_episode,
    )

    relevant_target_entries = _select_target_anchor_entries(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=True,
    ) or _select_target_anchor_entries(
        target_video_entries,
        tracked_season=tracked_season,
        accepted_only=False,
    )
    inferred_target_relative_path = _infer_target_relative_path(relevant_target_entries, anchor_episode=anchor_episode)
    recommended_entries, recommended_episode_numbers, stop_reason = _build_recommended_entries(
        source_video_entries,
        anchor_episode=anchor_episode,
        inferred_target_relative_path=inferred_target_relative_path,
    )
    stats.stop_reason = stop_reason
    selection_groups = _build_sync_selection_groups(
        recommended_entries,
        target_relative_path=inferred_target_relative_path,
    )
    plan_preview = _build_plan_preview(
        recommended_entries,
        target_relative_path=inferred_target_relative_path,
    )
    full_entries, full_episode_numbers = _build_full_replace_entries(source_video_entries)
    full_selection_groups = _build_sync_selection_groups(
        full_entries,
        target_relative_path=inferred_target_relative_path,
    )
    full_plan_preview = _build_plan_preview(
        full_entries,
        target_relative_path=inferred_target_relative_path,
    )
    summary = _build_diagnosis_summary(
        task=task,
        source_kind=normalized_source_kind,
        snapshot=snapshot,
        anchor_episode=anchor_episode,
        latest_target_episode=latest_target_episode,
        near_episode_window=normalized_window,
        stats=stats,
        recommended_entries=recommended_entries,
        recommended_episode_numbers=recommended_episode_numbers,
        inferred_target_relative_path=inferred_target_relative_path,
        selection_groups=selection_groups,
        full_entries=full_entries,
        full_episode_numbers=full_episode_numbers,
        full_selection_groups=full_selection_groups,
        target_entries=target_video_entries,
    )

    extra_json = dict(task.extra_json or {})
    extra_json["last_file_diagnosis"] = {
        **summary,
        "diagnosed_at": datetime.utcnow().isoformat() + "Z",
        "operator": _normalize_text(operator, max_length=128) or None,
    }
    task.extra_json = extra_json
    session.add(task)
    session.flush()

    _append_follow_task_log(
        session,
        task=task,
        stage="diagnosis",
        message="Built follow task file diagnosis plan",
        payload={
            "source_kind": normalized_source_kind,
            "tracked_episode": tracked_episode,
            "anchor_episode": anchor_episode,
            "latest_target_episode": latest_target_episode,
            "recommended_episode_numbers": recommended_episode_numbers,
            "recommended_entry_count": len(recommended_entries),
            "selection_group_count": len(selection_groups),
            "full_episode_numbers": full_episode_numbers,
            "full_entry_count": len(full_entries),
            "full_selection_group_count": len(full_selection_groups),
            "full_parsed_count": stats.full_parsed_count,
            "quick_parsed_count": stats.quick_parsed_count,
            "stop_reason": stop_reason,
        },
    )

    return {
        "summary": summary,
        "recommended_selection_groups": selection_groups,
        "recommended_plan_items": plan_preview,
        "full_selection_groups": full_selection_groups,
        "full_plan_items": full_plan_preview,
        "source_entries": [
            _serialize_file_entry(entry)
            for entry in sorted(
                source_video_entries,
                key=lambda item: (item.selected, item.sort_episode, item.updated_at or datetime.min, -item.scan_order),
                reverse=True,
            )[:_DEFAULT_MAX_RESPONSE_ENTRIES]
        ],
        "target_entries": [
            _serialize_file_entry(entry)
            for entry in sorted(
                target_video_entries,
                key=lambda item: (item.accepted, item.sort_episode, item.updated_at or datetime.min, -item.scan_order),
                reverse=True,
            )[:_DEFAULT_MAX_RESPONSE_ENTRIES]
        ],
    }
