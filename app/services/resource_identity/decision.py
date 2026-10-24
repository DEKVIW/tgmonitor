from __future__ import annotations

from datetime import datetime

from .models import FollowCandidateDecision, ParsedResourceIdentity
from .parser import is_meaningful_identity_key, normalize_match_key


def _core_title_key(identity: ParsedResourceIdentity | None) -> str:
    if identity is None or not identity.is_target_work:
        return ""
    core_title = identity.core_title
    if not core_title or not is_meaningful_identity_key(core_title):
        return ""
    return normalize_match_key(core_title)


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

    tracked_core_title = _core_title_key(tracked)
    candidate_core_title = _core_title_key(candidate)
    if not tracked_core_title or not candidate_core_title or tracked_core_title != candidate_core_title:
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.99 if tracked_core_title and candidate_core_title else 0.25,
            reason="rule_core_title_mismatch" if tracked_core_title and candidate_core_title else "rule_core_title_missing",
            debug={"tracked": tracked.to_dict(), "candidate": candidate.to_dict()},
        )

    release_year_compatible = (
        tracked.release_year is None
        or candidate.release_year is None
        or tracked.release_year == candidate.release_year
    )
    season_compatible = (
        tracked.season is None
        or candidate.season is None
        or tracked.season == candidate.season
    )

    if not release_year_compatible:
        return FollowCandidateDecision(
            is_same_work=False,
            is_newer=False,
            should_promote=False,
            confidence=0.97,
            reason="rule_release_year_mismatch",
            current_episode=tracked.episode,
            candidate_episode=candidate.episode,
            current_issue_no=tracked.issue_no,
            candidate_issue_no=candidate.issue_no,
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

    needs_ai_review = tracked.needs_ai_review or candidate.needs_ai_review
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
