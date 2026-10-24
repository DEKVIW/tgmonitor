import os

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "test-hash")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-pan-transfer-follow-share-reuse.db")
os.environ.setdefault("DEFAULT_CHANNELS", "[]")
os.environ.setdefault("SECRET_SALT", "test-secret")

import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.pan_transfer_models import PanTransferFollowTaskSyncRequest
from app.services.pan_transfer.constants import (
    PAN_TRANSFER_ITEM_STATUS_QUEUED,
    PAN_TRANSFER_ITEM_STATUS_RETRY_WAIT,
    PAN_TRANSFER_VALIDATION_STATUS_PENDING,
)
from app.services.pan_transfer.queue import reset_pan_transfer_batch_items
from app.services.pan_transfer.worker import _share_validation_is_explicitly_invalid, _should_reuse_existing_share


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


def test_external_source_is_only_allowed_for_full_replace() -> None:
    payload = {
        "source_kind": "current",
        "sync_mode": "replace_all",
        "external_source_url": "https://pan.quark.cn/s/external-share",
        "confirm_full_replace": True,
        "selected_entries": [{"name": "episode-01.mp4", "is_dir": False}],
    }
    request = PanTransferFollowTaskSyncRequest(**payload)
    assert request.external_source_url == payload["external_source_url"]

    with pytest.raises(ValueError, match="external_source_url"):
        PanTransferFollowTaskSyncRequest(
            **{
                **payload,
                "sync_mode": "incremental",
                "confirm_full_replace": False,
            }
        )


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
