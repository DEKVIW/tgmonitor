import os

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "test-hash")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-pan-transfer-follow-share-reuse.db")
os.environ.setdefault("DEFAULT_CHANNELS", "[]")
os.environ.setdefault("SECRET_SALT", "test-secret")

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.pan_transfer_models import PanTransferFollowTaskCandidateAssessment, PanTransferFollowTaskSyncRequest
from app.services.pan_transfer.constants import (
    PAN_TRANSFER_ITEM_STATUS_QUEUED,
    PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
    PAN_TRANSFER_VALIDATION_STATUS_PENDING,
)
from app.services.pan_transfer.queue import reset_pan_transfer_batch_items
from app.services.pan_transfer.follow_tasks import (
    _extract_follow_task_trigger_quality_tags,
    _evaluate_follow_candidate_rules,
    _diagnose_follow_external_sources,
    _follow_state_matches_source_origin,
    _validate_follow_external_source_configuration,
)
from app.services.pan_transfer.follow_sync import _resolve_follow_sync_quality_tags
from app.services.pan_transfer.worker import _share_validation_is_explicitly_invalid, _should_reuse_existing_share
from app.services.pan_transfer.providers.quark import _QuarkClient
from app.services.pan_transfer.quality import (
    QUALITY_COMPARISON_SAME,
    compare_quality_profiles,
    is_quality_upgrade,
)
import app.services.learning_resources as learning_resources
from app.services.learning_resources import _group_learning_batch_jobs


def test_follow_state_prefers_persisted_core_title_over_display_title() -> None:
    task = SimpleNamespace(
        extra_json={
            "source_origin": {
                "source_message_snapshot": {
                    "title": "牧神记（2024）高码 更新至104集",
                }
            }
        }
    )

    assert _follow_state_matches_source_origin(
        task,
        {
            "resource_title": "牧神记 无标 更新至107集",
            "core_title": "牧神记",
            "episode": 107,
        },
    )


def _learning_batch_job(job_id: int, resource_title: str, link_target_id: int):
    return (
        SimpleNamespace(id=job_id, source_message_id=1000 + job_id),
        SimpleNamespace(display_title=resource_title),
        SimpleNamespace(id=1),
        SimpleNamespace(id=1),
        SimpleNamespace(id=link_target_id),
        SimpleNamespace(id=2000 + job_id),
    )


def test_learning_batch_groups_resources_by_source_link() -> None:
    groups = _group_learning_batch_jobs(
        [
            _learning_batch_job(1, "2027一级建造师", 10),
            _learning_batch_job(2, "2027监理工程师", 10),
            _learning_batch_job(3, "2027二级建造师", 10),
            _learning_batch_job(4, "2027咨询工程师", 10),
            _learning_batch_job(5, "2027环评工程师", 10),
            _learning_batch_job(6, "另一条来源", 11),
        ]
    )

    assert [[job[0].id for job in group] for group in groups] == [[1, 2, 3, 4, 5], [6]]


def test_shared_batch_item_updates_all_learning_jobs() -> None:
    item = SimpleNamespace(
        id=10,
        extra_json={
            "learning_resource_job_id": 1,
            "learning_resource_job_ids": [1, 2, 3],
        },
    )
    jobs = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    session = Mock()

    with patch.object(learning_resources, "get_learning_resource_jobs_for_batch_item", return_value=jobs), patch.object(
        learning_resources,
        "_sync_learning_resource_after_transfer_single",
    ) as sync_single:
        learning_resources.sync_learning_resource_after_transfer(
            session,
            item=item,
            success=True,
        )

    assert sync_single.call_count == 3
    assert item.extra_json == {
        "learning_resource_job_id": 1,
        "learning_resource_job_ids": [1, 2, 3],
    }


def test_follow_sync_reuses_existing_share_for_both_target_modes() -> None:
    context = {"source_kind": "current", "share_target_mode": "content_root"}

    assert _should_reuse_existing_share(
        follow_sync_context=context,
        existing_share_url="https://pan.quark.cn/s/current-share",
    )

    context["share_target_mode"] = "resource_dir"
    assert _should_reuse_existing_share(
        follow_sync_context=context,
        existing_share_url="https://pan.quark.cn/s/current-share",
    )


def test_follow_sync_requires_a_share_url_before_reuse() -> None:
    assert not _should_reuse_existing_share(
        follow_sync_context={"source_kind": "current"},
        existing_share_url=None,
    )


def test_only_explicitly_invalid_share_validation_allows_new_share() -> None:
    assert _share_validation_is_explicitly_invalid({"status": "invalid"})
    assert not _share_validation_is_explicitly_invalid({"status": "warning"})
    assert not _share_validation_is_explicitly_invalid({"status": "error"})
    assert not _should_reuse_existing_share(
        follow_sync_context=None,
        existing_share_url="https://pan.quark.cn/s/current-share",
    )


def test_external_source_is_allowed_for_incremental_and_full_replace() -> None:
    payload = {
        "source_kind": "external",
        "sync_mode": "replace_all",
        "external_source_url": "https://pan.quark.cn/s/external-share",
        "confirm_full_replace": True,
        "selected_entries": [{"name": "episode-01.mp4", "is_dir": False}],
    }
    request = PanTransferFollowTaskSyncRequest(**payload)
    assert request.external_source_url == payload["external_source_url"]

    incremental_request = PanTransferFollowTaskSyncRequest(
        **{
            **payload,
            "sync_mode": "incremental",
            "confirm_full_replace": False,
            "selected_entries": [],
            "selection_groups": [
                {
                    "selected_entries": [{"name": "episode-01-4k.mkv", "is_dir": False}],
                    "replace_existing_entry_ids": ["old-file-1"],
                    "replace_existing_names": ["episode-01.mkv"],
                }
            ],
        }
    )
    assert incremental_request.source_kind == "external"
    assert incremental_request.selection_groups[0].replace_existing_entry_ids == ["old-file-1"]
    assert incremental_request.selection_groups[0].replace_existing_names == ["episode-01.mkv"]

    with pytest.raises(ValueError, match="source_kind"):
        PanTransferFollowTaskSyncRequest(
            **{
                **payload,
                "source_kind": "current",
            }
        )


def test_external_source_configuration_requires_matching_platform() -> None:
    config = {
        "source_mode": "external_preferred",
        "external_sources": [{"url": "https://pan.quark.cn/s/example", "priority": 1, "enabled": True}],
    }

    _validate_follow_external_source_configuration(task_platform="夸克网盘", automation=config)

    with pytest.raises(ValueError, match="platform"):
        _validate_follow_external_source_configuration(task_platform="百度网盘", automation=config)

    with pytest.raises(ValueError, match="at least one"):
        _validate_follow_external_source_configuration(
            task_platform="夸克网盘",
            automation={"source_mode": "external_preferred", "external_sources": []},
        )


def test_candidate_assessment_preserves_quality_upgrade_flag() -> None:
    assessment = PanTransferFollowTaskCandidateAssessment(quality_upgrade=True)

    assert assessment.quality_upgrade is True


def test_external_follow_sync_reads_quality_from_realtime_trigger_title() -> None:
    task = SimpleNamespace(
        extra_json={
            "realtime_trigger": {
                "candidate_title": "吞噬星空 4K 更新至247集",
            },
        }
    )

    assert _extract_follow_task_trigger_quality_tags(task) == ["4K"]


def test_external_follow_sync_does_not_infer_quality_from_external_files() -> None:
    assert _resolve_follow_sync_quality_tags(
        source_kind="external",
        trigger_mode="automation",
        trigger_quality_tags=[],
        materialized_quality_tags=["4K"],
    ) == []

    assert _resolve_follow_sync_quality_tags(
        source_kind="external",
        trigger_mode="automation",
        trigger_quality_tags=["4K"],
        materialized_quality_tags=[],
    ) == ["4K"]


def _build_external_preferred_follow_task(*, external_result: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        task_name="玉簟秋追更",
        topic_title="玉簟秋",
        work_title="玉簟秋",
        source_url="https://pan.quark.cn/s/system-source",
        current_share_url="https://pan.quark.cn/s/current-share",
        current_share_status="valid",
        extra_json={
            "identity_snapshot": {
                "resource_title": "玉簟秋 (2026) 更新34集",
                "core_title": "玉簟秋",
                "latest_episode": 34,
            },
            "applied_update_state": {
                "resource_title": "玉簟秋 (2026) 更新34集",
                "core_title": "玉簟秋",
                "episode": 34,
            },
            "automation": {
                "enabled": True,
                "mode": "auto_incremental",
                "source_mode": "external_preferred",
                "external_sources": [
                    {"url": "https://pan.quark.cn/s/external", "priority": 1}
                ],
                "last_external_result": external_result,
                "external_source_statuses": [
                    {
                        "url": "https://pan.quark.cn/s/external",
                        "status": "valid" if external_result == "valid" else "invalid",
                    }
                ],
            },
        },
    )


def test_external_source_authority_rejects_same_episode_candidate() -> None:
    assessment = _evaluate_follow_candidate_rules(
        _build_external_preferred_follow_task(external_result="valid"),
        snapshot={"resource_title": "玉簟秋 (2026) 更新34集"},
        candidate={"title": "玉簟秋 (2026) 4K50FPS 更新34集"},
    )

    assert assessment["external_source_authoritative"] is True
    assert assessment["source_recovery"] is False
    assert assessment["quality_upgrade"] is False
    assert assessment["should_promote"] is False
    assert assessment["reason"] == "external_source_authoritative_same_episode"


def test_external_source_fallback_keeps_system_quality_judgement() -> None:
    assessment = _evaluate_follow_candidate_rules(
        _build_external_preferred_follow_task(external_result="fallback_system"),
        snapshot={"resource_title": "玉簟秋 (2026) 更新34集"},
        candidate={"title": "玉簟秋 (2026) 4K50FPS 更新34集"},
    )

    assert assessment["external_source_authoritative"] is False
    assert assessment["quality_upgrade"] is True
    assert assessment["should_promote"] is True


def test_same_episode_quality_upgrade_uses_resolution_only() -> None:
    assert compare_quality_profiles(["2160P"], ["4K"]) == QUALITY_COMPARISON_SAME
    assert is_quality_upgrade(["60FPS", "HIFI"], ["4K", "60FPS"]) is False
    assert is_quality_upgrade(["1080P"], ["720P"]) is True


def test_same_episode_without_resolution_does_not_promote() -> None:
    assessment = _evaluate_follow_candidate_rules(
        _build_external_preferred_follow_task(external_result="fallback_system"),
        snapshot={"resource_title": "玉簟秋 (2026) 更新34集"},
        candidate={"title": "玉簟秋 (2026) 60FPS HIFI 更新34集"},
    )

    assert assessment["quality_upgrade"] is False
    assert assessment["format_upgrade"] is False
    assert assessment["should_promote"] is False


def test_external_quality_trigger_keeps_system_fallback_candidate_during_check() -> None:
    task = _build_external_preferred_follow_task(external_result="valid")
    task.task_state = "checking"
    task.extra_json["realtime_trigger"] = {"source_mode": "external_preferred"}

    assessment = _evaluate_follow_candidate_rules(
        task,
        snapshot={"resource_title": "玉簟秋 (2026) 更新34集"},
        candidate={"title": "玉簟秋 (2026) 4K 更新34集"},
    )

    assert assessment["external_source_authoritative"] is False
    assert assessment["quality_upgrade"] is True
    assert assessment["should_promote"] is True


@pytest.mark.asyncio
async def test_external_sources_skip_stale_source_until_actionable_source() -> None:
    stale_diagnosis = {
        "summary": {
            "recommended_episode_numbers": [],
            "stop_reason": "gap_before_next_episode",
        },
        "recommended_selection_groups": [],
        "full_selection_groups": [],
    }
    actionable_diagnosis = {
        "summary": {
            "recommended_episode_numbers": [35],
            "stop_reason": "contiguous_window_hit",
        },
        "recommended_selection_groups": [{"selected_entries": [{"name": "35.mkv"}]}],
        "full_selection_groups": [],
    }

    with patch(
        "app.services.pan_transfer.file_diagnosis.diagnose_pan_transfer_follow_task_files",
        new=AsyncMock(side_effect=[stale_diagnosis, actionable_diagnosis]),
    ) as diagnose:
        result = await _diagnose_follow_external_sources(
            Mock(),
            task=SimpleNamespace(id=1),
            sources=[
                {"url": "https://pan.quark.cn/s/stale", "priority": 1},
                {"url": "https://pan.quark.cn/s/actionable", "priority": 2},
            ],
            worker_name="test",
        )

    assert result["source_url"] == "https://pan.quark.cn/s/actionable"
    assert result["diagnosis"] == actionable_diagnosis
    assert [item["status"] for item in result["statuses"]] == ["stale", "actionable"]
    assert diagnose.await_count == 2


@pytest.mark.asyncio
async def test_external_source_failure_falls_back_without_retry_error() -> None:
    with patch(
        "app.services.pan_transfer.file_diagnosis.diagnose_pan_transfer_follow_task_files",
        new=AsyncMock(side_effect=ConnectionError("temporary source failure")),
    ):
        result = await _diagnose_follow_external_sources(
            Mock(),
            task=SimpleNamespace(id=1),
            sources=[{"url": "https://pan.quark.cn/s/unavailable", "priority": 1}],
            worker_name="test",
        )

    assert result["fallback"] is True
    assert result["retry_error"] is None
    assert result["statuses"][0]["status"] == "transient_error"


def test_retry_reset_keeps_staging_snapshot_for_share_only_recovery() -> None:
    row = SimpleNamespace(
        id=12,
        batch_id=314,
        transfer_status=PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
        validation_status="invalid",
        new_share_url="https://pan.quark.cn/s/invalid-new-share",
        new_link_target_id=99,
        share_status="shared",
        replacement_status="failed",
        extra_json={
            "staging_snapshot": {
                "root": "影视",
                "folder_name": "小城良方",
                "folder_id": "folder-314-12",
            }
        },
        next_retry_at="later",
        locked_by="worker",
        locked_at="now",
        started_at="started",
        finished_at="finished",
        error_message="new share invalid",
        updated_at=None,
    )
    query = Mock()
    query.filter.return_value = query
    query.all.return_value = [row]
    session = Mock()
    session.query.return_value = query

    with patch("app.services.pan_transfer.queue.ensure_runtime_storage_tables"), patch(
        "app.services.pan_transfer.queue.refresh_pan_transfer_batch_summary"
    ):
        reset_count = reset_pan_transfer_batch_items(session, batch_id=314)

    assert reset_count == 1
    assert row.transfer_status == PAN_TRANSFER_ITEM_STATUS_QUEUED
    assert row.new_share_url is None
    assert row.new_link_target_id is None
    assert row.validation_status == PAN_TRANSFER_VALIDATION_STATUS_PENDING
    assert row.extra_json["staging_snapshot"]["folder_id"] == "folder-314-12"
    assert row.extra_json["share_retry_reset"]["previous_share_url"] == "https://pan.quark.cn/s/invalid-new-share"


@pytest.mark.asyncio
async def test_quark_task_terminal_failure_does_not_wait_until_timeout() -> None:
    client = _QuarkClient("cookie")

    async def request_json(*args, **kwargs):
        return {
            "code": 41026,
            "message": "没有可分享的文件",
            "data": {"status": 3, "task_id": "task-1"},
        }

    client._request_json = request_json
    with pytest.raises(Exception) as exc_info:
        await client.wait_task(task_id="task-1", retries=180)

    assert "没有可分享的文件" in str(exc_info.value)
    assert getattr(exc_info.value, "retryable", True) is False
