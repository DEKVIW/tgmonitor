from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ParsedResourceIdentity:
    raw_title: str
    cleaned_title: str
    core_title: str | None
    aliases: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    normalized_keys: list[str] = field(default_factory=list)
    release_year: int | None = None
    season: int | None = None
    episode: int | None = None
    issue_no: str | None = None
    issue_sort_value: int | None = None
    content_type: str | None = None
    is_complete: bool = False
    is_target_work: bool = True
    needs_ai_review: bool = False
    should_skip_ai: bool = False
    confidence: float = 0.0
    reason: str = ""
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_title": self.raw_title,
            "cleaned_title": self.cleaned_title,
            "core_title": self.core_title,
            "aliases": list(self.aliases),
            "search_queries": list(self.search_queries),
            "normalized_keys": list(self.normalized_keys),
            "release_year": self.release_year,
            "season": self.season,
            "episode": self.episode,
            "issue_no": self.issue_no,
            "issue_sort_value": self.issue_sort_value,
            "content_type": self.content_type,
            "is_complete": self.is_complete,
            "is_target_work": self.is_target_work,
            "needs_ai_review": self.needs_ai_review,
            "should_skip_ai": self.should_skip_ai,
            "confidence": self.confidence,
            "reason": self.reason,
            "debug": dict(self.debug),
        }


@dataclass(slots=True)
class FollowCandidateDecision:
    is_same_work: bool
    is_newer: bool
    should_promote: bool
    same_episode_replace: bool = False
    needs_ai_review: bool = False
    confidence: float = 0.0
    reason: str = ""
    current_episode: int | None = None
    candidate_episode: int | None = None
    current_issue_no: str | None = None
    candidate_issue_no: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_same_work": self.is_same_work,
            "is_newer": self.is_newer,
            "should_promote": self.should_promote,
            "same_episode_replace": self.same_episode_replace,
            "needs_ai_review": self.needs_ai_review,
            "confidence": self.confidence,
            "reason": self.reason,
            "current_episode": self.current_episode,
            "candidate_episode": self.candidate_episode,
            "current_issue_no": self.current_issue_no,
            "candidate_issue_no": self.candidate_issue_no,
            "judge_source": "rule",
            "debug": dict(self.debug),
        }
