from __future__ import annotations

from datetime import datetime

from .models import FollowCandidateDecision, ParsedResourceIdentity
from .parser import normalize_match_key


def _identity_keys(identity: ParsedResourceIdentity | None) -> list[str]:
    if identity is None:
        return []
    keys = [key for key in identity.normalized_keys if key]
    if not keys and identity.core_title:
        keys.append(normalize_match_key(identity.core_title))
    return [key for key in keys if key]


def _keys_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < 3:
        return False
    return shorter in longer


def compare_follow_candidate(
    tracked: ParsedResourceIdentity,
    candidate: ParsedResourceIdentity,
    *,
    tracked_message_time: datetime | None = None,
    candidate_message_time: datetime | None = None,
) -> FollowCandidateDecision:
    if not tracked.is_target_work:
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.3,
            reason="rule_tracked_title_non_target",
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    if not candidate.is_target_work:
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.92,
            reason="rule_candidate_non_target",
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    tracked_keys = _identity_keys(tracked)
    candidate_keys = _identity_keys(candidate)
    key_match = any(_keys_match(left, right) for left in tracked_keys for right in candidate_keys)
    season_compatible = (
        tracked.season is None
        or candidate.season is None
        or tracked.season == candidate.season
    )

    if not key_match:
        if tracked.needs_ai_review or candidate.needs_ai_review:
            return FollowCandidateDecision(
                is_same_work=False,
                is_newer=False,
                should_promote=False,
                needs_ai_review=True,
                confidence=0.45,
                reason="rule_core_title_mismatch_needs_ai",
                debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
            )
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.25,
            reason="rule_core_title_mismatch",
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    if not season_compatible:
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.82,
            reason="rule_season_mismatch",
            current_episode=tracked.episode,
            candidate_episode=candidate.episode,
            current_issue_no=tracked.issue_no,
            candidate_issue_no=candidate.issue_no,
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    if tracked.episode is not None and candidate.episode is not None:
        if candidate.episode > tracked.episode:
            return FollowCandidateDecision(
                is_same_work=True,
                is_newer=True,
                should_promote=True,
                confidence=0.95,
                reason="rule_episode_newer",
                current_episode=tracked.episode,
                candidate_episode=candidate.episode,
                debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
            )
        if candidate.episode == tracked.episode:
            return FollowCandidateDecision(
                is_same_work=True,
                is_newer=False,
                should_promote=False,
                same_episode_replace=True,
                confidence=0.91,
                reason="rule_same_episode",
                current_episode=tracked.episode,
                candidate_episode=candidate.episode,
                debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
            )
        return FollowCandidateDecision(
            is_same_work=True,
            is_newer=False,
            should_promote=False,
            confidence=0.88,
            reason="rule_candidate_episode_not_newer",
            current_episode=tracked.episode,
            candidate_episode=candidate.episode,
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    if tracked.issue_sort_value is not None and candidate.issue_sort_value is not None:
        if candidate.issue_sort_value > tracked.issue_sort_value:
            return FollowCandidateDecision(
                is_same_work=True,
                is_newer=True,
                should_promote=True,
                confidence=0.94,
                reason="rule_issue_newer",
                current_episode=tracked.episode,
                candidate_episode=candidate.episode,
                current_issue_no=tracked.issue_no,
                candidate_issue_no=candidate.issue_no,
                debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
            )
        if candidate.issue_sort_value == tracked.issue_sort_value:
            return FollowCandidateDecision(
                is_same_work=True,
                is_newer=False,
                should_promote=False,
                same_episode_replace=True,
                confidence=0.9,
                reason="rule_same_issue",
                current_episode=tracked.episode,
                candidate_episode=candidate.episode,
                current_issue_no=tracked.issue_no,
                candidate_issue_no=candidate.issue_no,
                debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
            )
        return FollowCandidateDecision(
            is_same_work=True,
            is_newer=False,
            should_promote=False,
            confidence=0.86,
            reason="rule_candidate_issue_not_newer",
            current_episode=tracked.episode,
            candidate_episode=candidate.episode,
            current_issue_no=tracked.issue_no,
            candidate_issue_no=candidate.issue_no,
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    message_time_is_newer = bool(
        tracked_message_time is not None
        and candidate_message_time is not None
        and candidate_message_time > tracked_message_time
    )
    needs_ai_review = tracked.needs_ai_review or candidate.needs_ai_review or message_time_is_newer
    return FollowCandidateDecision(
        is_same_work=True,
        is_newer=False,
        should_promote=False,
        same_episode_replace=False,
        needs_ai_review=needs_ai_review,
        confidence=0.6 if needs_ai_review else 0.78,
        reason="rule_same_work_progress_ambiguous" if needs_ai_review else "rule_same_work_without_progress",
        current_episode=tracked.episode,
        candidate_episode=candidate.episode,
        current_issue_no=tracked.issue_no,
        candidate_issue_no=candidate.issue_no,
        debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
    )
