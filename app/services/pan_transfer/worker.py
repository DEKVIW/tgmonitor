from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import LearningResourceTransferJob, LinkTarget, PanTransferAccount, PanTransferBatch, PanTransferBatchItem, PanTransferSyncTask, ensure_runtime_storage_tables
from app.services.learning_automation import is_learning_target_enabled

from .common import (
    DEFAULT_SHARE_TARGET_MODE,
    SHARE_TARGET_CONTENT_ROOT,
    SHARE_TARGET_RESOURCE_DIR,
    build_staging_folder_name,
    generate_share_passcode,
    normalize_relative_path,
    utcnow,
)
from .constants import (
    PAN_TRANSFER_BATCH_STATUS_CANCELLED,
    PAN_TRANSFER_REPLACEMENT_STATUS_FAILED,
    PAN_TRANSFER_REPLACEMENT_STATUS_PENDING,
    PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED,
    PAN_TRANSFER_SHARE_STATUS_FAILED,
    PAN_TRANSFER_SHARE_STATUS_PENDING,
    PAN_TRANSFER_SHARE_STATUS_SHARED,
    PAN_TRANSFER_VALIDATION_STATUS_INVALID,
    PAN_TRANSFER_VALIDATION_STATUS_PENDING,
)
from .execution_logs import append_pan_transfer_execution_log
from .providers import decrypt_account_credential, get_pan_transfer_provider
from .providers.base import PanTransferProviderError
from .queue import claim_next_pan_transfer_batch_item, mark_pan_transfer_item_error, mark_pan_transfer_item_success, refresh_pan_transfer_batch_summary
from .replacement import replace_pan_transfer_links
from .validation import validate_share_url


def _merge_extra_json(item: PanTransferBatchItem, payload: dict[str, Any]) -> None:
    item.extra_json = {
        **dict(item.extra_json or {}),
        **payload,
    }


def _build_staging_name(item: PanTransferBatchItem) -> str:
    base_name = build_staging_folder_name(
        batch_id=int(item.batch_id),
        item_id=int(item.id),
        title=str(item.short_title or f"item-{int(item.id)}"),
    )
    next_attempt = int(item.attempt_count or 0) + 1
    if next_attempt <= 1:
        return base_name
    return f"{base_name}-r{next_attempt}"


def _pause_learning_item_if_disabled(session: Session, *, item: PanTransferBatchItem) -> bool:
    extra_json = dict(item.extra_json or {})
    if not extra_json.get("learning_resource_job_id"):
        return False
    if is_learning_target_enabled(session, extra_json):
        return False
    item.transfer_status = "paused"
    item.next_retry_at = None
    item.locked_by = None
    item.locked_at = None
    item.started_at = None
    session.add(item)
    job_id = extra_json.get("learning_resource_job_id")
    if job_id:
        job = session.get(LearningResourceTransferJob, int(job_id))
        if job is not None:
            job.status = "paused"
            session.add(job)
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(item.batch_id))
    return True


def _normalize_share_target_mode(value: Any) -> str:
    normalized = str(value or DEFAULT_SHARE_TARGET_MODE).strip().lower() or DEFAULT_SHARE_TARGET_MODE
    if normalized not in {SHARE_TARGET_RESOURCE_DIR, SHARE_TARGET_CONTENT_ROOT}:
        return DEFAULT_SHARE_TARGET_MODE
    return normalized


def _iso_utc_now() -> str:
    return utcnow().isoformat() + "Z"


def _extract_error_payload(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(exc, PanTransferProviderError):
        payload.update(dict(exc.payload or {}))
    payload.setdefault("error_type", type(exc).__name__)
    error_message = _describe_exception(exc)
    if error_message:
        payload.setdefault("error_message", error_message)
    if exc.__cause__ is not None:
        payload.setdefault(
            "error_cause",
            str(exc.__cause__).strip() or type(exc.__cause__).__name__,
        )
    return payload


def _describe_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    if exc.__cause__ is not None:
        cause_message = str(exc.__cause__).strip()
        if cause_message:
            return f"{type(exc).__name__}: {cause_message}"
    return type(exc).__name__


def _commit_before_external_call(session: Session) -> None:
    if session.in_transaction():
        session.commit()


def _get_staging_snapshot(item: PanTransferBatchItem) -> dict[str, Any] | None:
    snapshot = dict(item.extra_json or {}).get("staging_snapshot")
    if not isinstance(snapshot, dict):
        return None
    folder_name = str(snapshot.get("folder_name") or "").strip()
    if not folder_name:
        return None
    return dict(snapshot)


def _get_share_request(item: PanTransferBatchItem) -> dict[str, Any] | None:
    share_request = dict(item.extra_json or {}).get("share_request")
    if not isinstance(share_request, dict):
        return None
    share_mode = str(share_request.get("share_mode") or "").strip().lower()
    if not share_mode and not str(share_request.get("existing_share_task_id") or "").strip():
        return None
    normalized = dict(share_request)
    normalized["share_mode"] = share_mode or "public"
    normalized["share_target_mode"] = _normalize_share_target_mode(normalized.get("share_target_mode"))
    return normalized


def _get_follow_sync_context(session: Session, item: PanTransferBatchItem) -> dict[str, Any] | None:
    extra_json = dict(item.extra_json or {})
    raw_value = extra_json.get("follow_sync_context")
    item_context = dict(raw_value) if isinstance(raw_value, dict) else {}
    batch = session.get(PanTransferBatch, int(item.batch_id))
    if batch is None or str(batch.batch_type or "") != "follow_sync":
        return item_context or None

    request_json = dict(batch.request_json or {})
    merged_context = {
        key: value
        for key, value in request_json.items()
        if key in {
            "follow_task_id",
            "trigger_mode",
            "source_kind",
            "sync_mode",
            "source_link_target_id",
            "source_url",
            "external_source_url",
            "source_link_status",
            "existing_share_url",
            "share_target_mode",
            "reuse_existing_share_if_valid",
            "clear_existing_contents",
            "publish_record_id",
            "update_publish_record",
            "preferred_target_relative_path",
            "target_relative_path_source",
            "selection_target_relative_paths",
            "source_metadata_promotion",
        }
    }
    merged_context.update(item_context)
    follow_task_id = merged_context.get("follow_task_id")
    try:
        normalized_follow_task_id = int(follow_task_id) if follow_task_id is not None else None
    except (TypeError, ValueError):
        normalized_follow_task_id = None
    if normalized_follow_task_id is not None:
        task = session.get(PanTransferSyncTask, normalized_follow_task_id)
        if task is not None:
            merged_context.setdefault("existing_share_url", str(task.current_share_url or "").strip() or None)
            merged_context.setdefault("share_target_mode", str(task.share_target_mode or "resource_dir"))
            merged_context.setdefault("reuse_existing_share_if_valid", True)
    return merged_context or None


def _should_reuse_existing_share(*, follow_sync_context: dict[str, Any] | None, existing_share_url: str | None) -> bool:
    return bool(follow_sync_context is not None and str(existing_share_url or "").strip())


def _share_validation_is_explicitly_invalid(validation_result: dict[str, Any] | None) -> bool:
    return str((validation_result or {}).get("status") or "").strip().lower() == PAN_TRANSFER_VALIDATION_STATUS_INVALID


def _get_source_selection(item: PanTransferBatchItem) -> dict[str, Any] | None:
    raw_value = dict(item.extra_json or {}).get("source_selection")
    if not isinstance(raw_value, dict):
        return None
    raw_groups = raw_value.get("selection_groups")
    if isinstance(raw_groups, list) and raw_groups:
        normalized_groups = [
            {
                "parent_entry_id": str(group.get("parent_entry_id") or "").strip() or None,
                "parent_path": str(group.get("parent_path") or "").strip() or None,
                "parent_name": str(group.get("parent_name") or "").strip() or None,
                "target_relative_path": str(group.get("target_relative_path") or "").strip() or None,
                "selected_entries": [dict(row or {}) for row in list(group.get("selected_entries") or []) if isinstance(row, dict)],
                "selected_count": int(group.get("selected_count") or len(list(group.get("selected_entries") or [])) or 0),
            }
            for group in raw_groups
            if isinstance(group, dict) and isinstance(group.get("selected_entries"), list) and list(group.get("selected_entries") or [])
        ]
        if normalized_groups:
            return {
                "selection_groups": normalized_groups,
                "selected_count": sum(int(group.get("selected_count") or 0) for group in normalized_groups),
            }
    selected_entries = raw_value.get("selected_entries")
    if not isinstance(selected_entries, list) or not selected_entries:
        return None
    return {
        "selection_groups": [
            {
                "parent_entry_id": str(raw_value.get("parent_entry_id") or "").strip() or None,
                "parent_path": str(raw_value.get("parent_path") or "").strip() or None,
                "parent_name": str(raw_value.get("parent_name") or "").strip() or None,
                "target_relative_path": str(raw_value.get("target_relative_path") or "").strip() or None,
                "selected_entries": [dict(row or {}) for row in selected_entries if isinstance(row, dict)],
                "selected_count": int(raw_value.get("selected_count") or len(selected_entries) or 0),
            }
        ],
        "selected_count": int(raw_value.get("selected_count") or len(selected_entries) or 0),
    }


def _get_item_execution_plan(
    *,
    item: PanTransferBatchItem,
    account: PanTransferAccount,
) -> dict[str, Any]:
    extra_json = dict(item.extra_json or {})
    resolved_paths = extra_json.get("resolved_paths")
    path_strategy = extra_json.get("path_strategy")

    if isinstance(resolved_paths, dict):
        staging_root = normalize_relative_path(str(resolved_paths.get("staging_root") or ""))
        staging_folder_name = str(resolved_paths.get("staging_folder_name") or "").strip()
        if staging_folder_name:
            resolved_path = normalize_relative_path(
                str(resolved_paths.get("resolved_path") or "/".join(part for part in (staging_root, staging_folder_name) if part))
            )
            return {
                "staging_root": staging_root,
                "staging_folder_name": staging_folder_name,
                "resolved_path": resolved_path,
                "transfer_layout": str(resolved_paths.get("transfer_layout") or "").strip() or None,
                "batch_folder_name": str(resolved_paths.get("batch_folder_name") or "").strip() or None,
                "share_target_mode": _normalize_share_target_mode(resolved_paths.get("share_target_mode")),
                "source": "resolved_paths",
            }

    fallback_root = normalize_relative_path(str(account.default_save_root or ""))
    fallback_folder = _build_staging_name(item)
    fallback_share_target_mode = DEFAULT_SHARE_TARGET_MODE
    if isinstance(path_strategy, dict):
        fallback_share_target_mode = _normalize_share_target_mode(path_strategy.get("share_target_mode"))
    return {
        "staging_root": fallback_root,
        "staging_folder_name": fallback_folder,
        "resolved_path": normalize_relative_path("/".join(part for part in (fallback_root, fallback_folder) if part)),
        "transfer_layout": None,
        "batch_folder_name": None,
        "share_target_mode": fallback_share_target_mode,
        "source": "legacy_fallback",
    }


def _build_share_request(
    *,
    account: PanTransferAccount,
    item: PanTransferBatchItem,
    staging_root: str,
    staging_folder_name: str,
    share_target_mode: str = DEFAULT_SHARE_TARGET_MODE,
) -> dict[str, Any]:
    share_mode = str(account.default_share_mode or "public").strip().lower() or "public"
    share_passcode = str(account.default_share_passcode or "").strip() or None
    if share_mode == "private" and not share_passcode:
        share_passcode = generate_share_passcode()
    title_hint = str(item.short_title or "").strip() or None
    return {
        "share_mode": share_mode,
        "share_passcode": share_passcode,
        "share_expire_days": int(account.default_share_expire_days) if account.default_share_expire_days is not None else None,
        "title_hint": title_hint,
        "staging_root": staging_root,
        "staging_folder_name": staging_folder_name,
        "share_target_mode": _normalize_share_target_mode(share_target_mode),
    }


def _build_share_request_from_snapshot(
    *,
    account: PanTransferAccount,
    item: PanTransferBatchItem,
    staging_snapshot: dict[str, Any],
    share_target_mode: str = DEFAULT_SHARE_TARGET_MODE,
) -> dict[str, Any]:
    return _build_share_request(
        account=account,
        item=item,
        staging_root=normalize_relative_path(str(staging_snapshot.get("root") or "")),
        staging_folder_name=str(staging_snapshot.get("folder_name") or _build_staging_name(item)),
        share_target_mode=share_target_mode,
    )


def _mark_account_validation(
    account: PanTransferAccount,
    *,
    ok: bool,
    detail_message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    account.last_validated_at = utcnow()
    account.last_error_message = None if ok else str(detail_message or "")[:2000]
    account.extra_json = {
        **dict(account.extra_json or {}),
        "last_validation": {
            "ok": bool(ok),
            "detail_message": str(detail_message or "")[:2000],
            "payload": dict(payload or {}),
            "checked_at": _iso_utc_now(),
        },
    }


async def _process_pan_transfer_item_async(
    session: Session,
    *,
    item: PanTransferBatchItem,
    worker_name: str,
) -> None:
    source_target = session.get(LinkTarget, int(item.link_target_id))
    if source_target is None:
        raise PanTransferProviderError("source link target not found", retryable=False)

    account = session.get(PanTransferAccount, int(item.target_account_id or 0))
    if account is None:
        raise PanTransferProviderError("target account not found", retryable=False)
    if not bool(account.is_enabled):
        raise PanTransferProviderError("target account is disabled", retryable=False)

    credential_value = decrypt_account_credential(account)
    provider = get_pan_transfer_provider(str(item.platform or ""))
    execution_plan = _get_item_execution_plan(item=item, account=account)

    staging_snapshot = _get_staging_snapshot(item)
    share_request = _get_share_request(item)
    follow_sync_context = _get_follow_sync_context(session, item)
    source_selection = _get_source_selection(item)
    selection_groups = list((source_selection or {}).get("selection_groups") or [])
    selection_parent_path = selection_groups[0].get("parent_path") if len(selection_groups) == 1 else None
    sync_mode = str((follow_sync_context or {}).get("sync_mode") or "standard").strip().lower() or "standard"
    clear_existing_contents = bool((follow_sync_context or {}).get("clear_existing_contents"))

    if not str(item.new_share_url or "").strip():
        if staging_snapshot is None:
            staging_root = normalize_relative_path(str(execution_plan.get("staging_root") or ""))
            staging_folder_name = str(execution_plan.get("staging_folder_name") or _build_staging_name(item))
            share_request = _build_share_request(
                account=account,
                item=item,
                staging_root=staging_root,
                staging_folder_name=staging_folder_name,
                share_target_mode=str(execution_plan.get("share_target_mode") or DEFAULT_SHARE_TARGET_MODE),
            )
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="transfer",
                message="Starting transfer to staging directory",
                payload={
                    "account_id": int(account.id),
                    "account_name": str(account.account_name or ""),
                    "staging_root": staging_root,
                    "staging_folder_name": staging_folder_name,
                    "resolved_path": execution_plan.get("resolved_path"),
                    "transfer_layout": execution_plan.get("transfer_layout"),
                    "batch_folder_name": execution_plan.get("batch_folder_name"),
                    "share_target_mode": execution_plan.get("share_target_mode"),
                    "path_source": execution_plan.get("source"),
                    "sync_mode": sync_mode,
                    "selected_entry_count": int((source_selection or {}).get("selected_count") or 0),
                    "selection_group_count": len(selection_groups),
                    "selection_parent_path": selection_parent_path,
                    "clear_existing_contents": clear_existing_contents,
                },
            )
            try:
                _commit_before_external_call(session)
                transfer_source_url = str(
                    (follow_sync_context or {}).get("external_source_url")
                    or (follow_sync_context or {}).get("source_url")
                    or source_target.original_url
                    or item.original_url
                    or ""
                ).strip()
                transfer_source_passcode = (
                    None
                    if (follow_sync_context or {}).get("external_source_url")
                    else str(source_target.passcode or "").strip() or None
                )
                transfer_result = await provider.transfer_to_staging(
                    credential_value=credential_value,
                    account_name=str(account.account_name or ""),
                    original_url=transfer_source_url,
                    original_passcode=transfer_source_passcode,
                    staging_root=staging_root,
                    staging_folder_name=staging_folder_name,
                    title_hint=str(share_request.get("title_hint") or "") or None,
                    source_selection=source_selection,
                    clear_existing_contents=clear_existing_contents,
                )
            except Exception as exc:
                error_detail = _describe_exception(exc)
                error_payload = {
                    "account_id": int(account.id),
                    "account_name": str(account.account_name or ""),
                    "staging_root": staging_root,
                    "staging_folder_name": staging_folder_name,
                    "resolved_path": execution_plan.get("resolved_path"),
                    "transfer_layout": execution_plan.get("transfer_layout"),
                    "batch_folder_name": execution_plan.get("batch_folder_name"),
                    "share_target_mode": execution_plan.get("share_target_mode"),
                    "path_source": execution_plan.get("source"),
                    "sync_mode": sync_mode,
                    "selected_entry_count": int((source_selection or {}).get("selected_count") or 0),
                    "selection_group_count": len(selection_groups),
                    "selection_parent_path": selection_parent_path,
                    "clear_existing_contents": clear_existing_contents,
                    **_extract_error_payload(exc),
                }
                _mark_account_validation(
                    account,
                    ok=False,
                    detail_message=error_detail,
                    payload=error_payload,
                )
                session.add(account)
                session.flush()
                append_pan_transfer_execution_log(
                    session,
                    item=item,
                    stage="transfer",
                    level="error",
                    message=f"Transfer to staging failed: {error_detail}",
                    payload=error_payload,
                )
                raise

            staging_snapshot = {
                "root": normalize_relative_path(str(transfer_result.staging_root or "")),
                "folder_name": str(transfer_result.staging_folder_name or staging_folder_name),
                "folder_id": str(transfer_result.staging_folder_id or "") or None,
                "transferred_at": _iso_utc_now(),
                "payload": dict(transfer_result.payload or {}),
            }
            _mark_account_validation(
                account,
                ok=True,
                detail_message="Validated during staging transfer",
                payload=dict(transfer_result.payload or {}),
            )
            item.share_status = PAN_TRANSFER_SHARE_STATUS_PENDING
            _merge_extra_json(
                item,
                {
                    "staging_snapshot": staging_snapshot,
                    "share_request": share_request,
                    "staging_root": staging_snapshot.get("root"),
                    "staging_folder_name": staging_snapshot.get("folder_name"),
                    "staging_folder_id": staging_snapshot.get("folder_id"),
                    "transfer_payload": dict(transfer_result.payload or {}),
                },
            )
            session.add(account)
            session.add(item)
            session.flush()
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="transfer",
                message="Transfer to staging completed",
                payload={
                    "staging_root": staging_snapshot.get("root"),
                    "staging_folder_name": staging_snapshot.get("folder_name"),
                    "staging_folder_id": staging_snapshot.get("folder_id"),
                    "resolved_path": execution_plan.get("resolved_path"),
                    "transfer_layout": execution_plan.get("transfer_layout"),
                    "batch_folder_name": execution_plan.get("batch_folder_name"),
                    "share_target_mode": execution_plan.get("share_target_mode"),
                    "sync_mode": sync_mode,
                    "selected_entry_count": int((source_selection or {}).get("selected_count") or 0),
                    "selection_group_count": len(selection_groups),
                    "selection_parent_path": selection_parent_path,
                    "clear_existing_contents": clear_existing_contents,
                    "provider_payload": dict(transfer_result.payload or {}),
                },
            )
        else:
            if share_request is None:
                share_request = _build_share_request_from_snapshot(
                    account=account,
                    item=item,
                    staging_snapshot=staging_snapshot,
                    share_target_mode=str(execution_plan.get("share_target_mode") or DEFAULT_SHARE_TARGET_MODE),
                )
                _merge_extra_json(item, {"share_request": share_request})
                session.add(item)
                session.flush()
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="transfer",
                message="Skipping transfer and reusing existing staging snapshot",
                payload={
                    "staging_root": staging_snapshot.get("root"),
                    "staging_folder_name": staging_snapshot.get("folder_name"),
                    "staging_folder_id": staging_snapshot.get("folder_id"),
                    "resolved_path": execution_plan.get("resolved_path"),
                    "transfer_layout": execution_plan.get("transfer_layout"),
                    "batch_folder_name": execution_plan.get("batch_folder_name"),
                    "share_target_mode": execution_plan.get("share_target_mode"),
                    "path_source": execution_plan.get("source"),
                    "sync_mode": sync_mode,
                    "selected_entry_count": int((source_selection or {}).get("selected_count") or 0),
                    "selection_group_count": len(selection_groups),
                    "selection_parent_path": selection_parent_path,
                    "clear_existing_contents": clear_existing_contents,
                },
            )

        item.share_status = PAN_TRANSFER_SHARE_STATUS_PENDING
        session.add(item)
        session.flush()

        requested_share_target_mode = str((share_request or {}).get("share_target_mode") or execution_plan.get("share_target_mode") or DEFAULT_SHARE_TARGET_MODE)
        requested_existing_share_url = (
            str((follow_sync_context or {}).get("existing_share_url") or "").strip() or None
        )
        can_reuse_existing_share = _should_reuse_existing_share(
            follow_sync_context=follow_sync_context,
            existing_share_url=requested_existing_share_url,
        )

        reused_existing_share = False
        if can_reuse_existing_share and requested_existing_share_url:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="share",
                message="Checking whether the existing share URL can be reused",
                payload={
                    "existing_share_url": requested_existing_share_url,
                    "share_target_mode": requested_share_target_mode,
                },
            )
            try:
                _commit_before_external_call(session)
                reuse_validation_result = await validate_share_url(requested_existing_share_url)
            except Exception as exc:
                append_pan_transfer_execution_log(
                    session,
                    item=item,
                    stage="share",
                    level="warning",
                    message=f"Existing share URL check failed; no new share will be created until validation succeeds: {_describe_exception(exc)}",
                    payload={
                        "existing_share_url": requested_existing_share_url,
                        **_extract_error_payload(exc),
                    },
                )
                raise PanTransferProviderError(
                    "Existing share URL validation failed; retrying without creating a new share",
                    retryable=True,
                    payload={
                        "existing_share_url": requested_existing_share_url,
                        **_extract_error_payload(exc),
                    },
                ) from exc
            else:
                reuse_validation_status = str(reuse_validation_result.get("status") or "").strip().lower()
                if not _share_validation_is_explicitly_invalid(reuse_validation_result):
                    item.new_share_url = requested_existing_share_url
                    item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
                    _mark_account_validation(
                        account,
                        ok=True,
                        detail_message="Validated during share reuse",
                        payload=dict(reuse_validation_result or {}),
                    )
                    _merge_extra_json(
                        item,
                        {
                            "share_reuse": {
                                "reused": True,
                                "share_url": requested_existing_share_url,
                                "checked_at": _iso_utc_now(),
                                "validation_result": dict(reuse_validation_result or {}),
                            },
                            "share_snapshot": {
                                "new_share_url": requested_existing_share_url,
                                "share_title": str((share_request or {}).get("title_hint") or item.short_title or ""),
                                "share_passcode": None,
                                "shared_at": _iso_utc_now(),
                                "share_target_mode": requested_share_target_mode,
                                "payload": {
                                    "reused_existing_share": True,
                                },
                            },
                        },
                    )
                    session.add(account)
                    session.add(item)
                    session.flush()
                    append_pan_transfer_execution_log(
                        session,
                        item=item,
                        stage="share",
                        message="Existing share URL is still valid and will be reused",
                        payload={
                            "new_share_url": requested_existing_share_url,
                            "share_target_mode": requested_share_target_mode,
                            "validation_result": dict(reuse_validation_result or {}),
                        },
                    )
                    reused_existing_share = True
                else:
                    append_pan_transfer_execution_log(
                        session,
                        item=item,
                        stage="share",
                        level="warning",
                        message="Existing share URL is not valid and a new share will be created",
                        payload={
                            "existing_share_url": requested_existing_share_url,
                            "validation_result": dict(reuse_validation_result or {}),
                        },
                    )

        if not reused_existing_share:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="share",
                message="Starting share creation for staging directory",
                payload={
                    "staging_root": staging_snapshot.get("root") if staging_snapshot else None,
                    "staging_folder_name": staging_snapshot.get("folder_name") if staging_snapshot else None,
                    "staging_folder_id": staging_snapshot.get("folder_id") if staging_snapshot else None,
                    "share_mode": share_request.get("share_mode") if share_request else None,
                    "share_target_mode": requested_share_target_mode,
                },
            )
            try:
                _commit_before_external_call(session)
                share_result = await provider.share_staging_target(
                    credential_value=credential_value,
                    account_name=str(account.account_name or ""),
                    staging_root=normalize_relative_path(str((staging_snapshot or {}).get("root") or "")),
                    staging_folder_name=str((staging_snapshot or {}).get("folder_name") or ""),
                    staging_folder_id=str((staging_snapshot or {}).get("folder_id") or "") or None,
                    share_target_mode=requested_share_target_mode,
                    share_mode=str((share_request or {}).get("share_mode") or "public"),
                    share_passcode=str((share_request or {}).get("share_passcode") or "").strip() or None,
                    share_expire_days=(share_request or {}).get("share_expire_days"),
                    title_hint=str((share_request or {}).get("title_hint") or "") or None,
                    existing_share_task_id=str((share_request or {}).get("existing_share_task_id") or "").strip() or None,
                )
            except Exception as exc:
                error_detail = _describe_exception(exc)
                error_payload = {
                    "account_id": int(account.id),
                    "account_name": str(account.account_name or ""),
                    "staging_root": (staging_snapshot or {}).get("root"),
                    "staging_folder_name": (staging_snapshot or {}).get("folder_name"),
                    "staging_folder_id": (staging_snapshot or {}).get("folder_id"),
                    "share_mode": (share_request or {}).get("share_mode"),
                    "share_target_mode": requested_share_target_mode,
                    **_extract_error_payload(exc),
                }
                share_task_id = str(error_payload.get("task_id") or "").strip()
                if share_task_id:
                    _merge_extra_json(
                        item,
                        {
                            "share_task_id": share_task_id,
                            "share_request": {
                                **dict(share_request or {}),
                                "existing_share_task_id": share_task_id,
                            },
                        },
                    )
                _mark_account_validation(
                    account,
                    ok=False,
                    detail_message=error_detail,
                    payload=error_payload,
                )
                session.add(account)
                session.flush()
                append_pan_transfer_execution_log(
                    session,
                    item=item,
                    stage="share",
                    level="error",
                    message=f"Share creation failed: {error_detail}",
                    payload=error_payload,
                )
                raise

            item.new_share_url = share_result.new_share_url
            item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
            _mark_account_validation(
                account,
                ok=True,
                detail_message="Validated during share creation",
                payload=dict(share_result.payload or {}),
            )
            _merge_extra_json(
                item,
                {
                    "share_title": share_result.share_title,
                    "share_passcode": share_result.share_passcode,
                    "provider_payload": dict(share_result.payload or {}),
                    "share_payload": dict(share_result.payload or {}),
                    "share_snapshot": {
                        "new_share_url": share_result.new_share_url,
                        "share_title": share_result.share_title,
                        "share_passcode": share_result.share_passcode,
                        "shared_at": _iso_utc_now(),
                        "share_target_mode": requested_share_target_mode,
                        "payload": dict(share_result.payload or {}),
                    },
                },
            )
            session.add(account)
            session.add(item)
            session.flush()
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="share",
                message="Share creation completed",
                payload={
                    "new_share_url": share_result.new_share_url,
                    "share_title": share_result.share_title,
                    "share_passcode": share_result.share_passcode,
                    "share_target_mode": requested_share_target_mode,
                    "provider_payload": dict(share_result.payload or {}),
                },
            )
    elif str(item.share_status or "") != PAN_TRANSFER_SHARE_STATUS_SHARED:
        item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
        session.add(item)
        session.flush()

    append_pan_transfer_execution_log(
        session,
        item=item,
        stage="validate",
        message="Validating newly created share URL",
        payload={"new_share_url": str(item.new_share_url or "")},
    )
    try:
        _commit_before_external_call(session)
        validation_result = await validate_share_url(str(item.new_share_url or ""))
    except Exception as exc:
        error_detail = _describe_exception(exc)
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="validate",
            level="error",
            message=f"Share URL validation failed: {error_detail}",
            payload={
                "new_share_url": str(item.new_share_url or ""),
                **_extract_error_payload(exc),
            },
        )
        raise

    item.last_validated_at = utcnow()
    item.validation_status = str(validation_result.get("status") or "warning")
    _merge_extra_json(item, {"share_validation": validation_result})
    session.add(item)
    session.flush()
    append_pan_transfer_execution_log(
        session,
        item=item,
        stage="validate",
        level="warning" if item.validation_status == PAN_TRANSFER_VALIDATION_STATUS_INVALID else "info",
        message=f"Share URL validation finished with status: {item.validation_status}",
        payload=dict(validation_result),
    )
    if item.validation_status == PAN_TRANSFER_VALIDATION_STATUS_INVALID:
        invalid_share_url = str(item.new_share_url or "").strip() or None
        _merge_extra_json(
            item,
            {
                "invalid_share_snapshot": {
                    "share_url": invalid_share_url,
                    "validation_result": dict(validation_result),
                    "recorded_at": _iso_utc_now(),
                }
            },
        )
        item.new_share_url = None
        item.new_link_target_id = None
        item.share_status = PAN_TRANSFER_SHARE_STATUS_PENDING
        item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_PENDING
        session.add(item)
        session.flush()
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="share",
            level="warning",
            message="Share URL is explicitly invalid; preserved staging directory for share-only retry",
            payload={
                "invalid_share_url": invalid_share_url,
                "validation_result": dict(validation_result),
            },
        )
        raise PanTransferProviderError(
            validation_result.get("detail_message") or "new share URL validation failed",
            retryable=True,
            payload=dict(validation_result),
        )

    skip_link_replacement = bool(dict(item.extra_json or {}).get("skip_link_replacement"))
    if not skip_link_replacement and str(item.replacement_status or "") != PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED:
        item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_PENDING
        session.add(item)
        session.flush()
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="replace",
            message="Replacing old links with the new shared URL",
            payload={"new_share_url": str(item.new_share_url or "")},
        )
        try:
            with session.begin_nested():
                replacement_result = replace_pan_transfer_links(
                    session,
                    batch_item=item,
                    new_share_url=str(item.new_share_url or ""),
                    operator=worker_name,
                )
                item.new_link_target_id = int(replacement_result.get("new_link_target_id") or 0) or None
                item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED
                _merge_extra_json(item, {"replacement": replacement_result})
                session.add(item)
                session.flush()
        except Exception as exc:
            error_detail = _describe_exception(exc)
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="replace",
                level="error",
                message=f"Link replacement failed: {error_detail}",
                payload={
                    "new_share_url": str(item.new_share_url or ""),
                    **_extract_error_payload(exc),
                },
            )
            raise
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="replace",
            message="Link replacement completed",
            payload=dict(replacement_result),
        )


def process_next_pan_transfer_item(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    item = claim_next_pan_transfer_batch_item(session, worker_name=worker_name)
    if item is None:
        return False
    if _pause_learning_item_if_disabled(session, item=item):
        return True

    previous_expire_on_commit = session.expire_on_commit
    session.expire_on_commit = False
    try:
        asyncio.run(_process_pan_transfer_item_async(session, item=item, worker_name=worker_name))
        mark_pan_transfer_item_success(session, item=item)
        try:
            from app.services.learning_resources import sync_learning_resource_after_transfer

            with session.begin_nested():
                sync_learning_resource_after_transfer(session, item=item, success=True)
        except Exception as exc:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="learning_resource",
                level="warning",
                message=f"Learning resource post-processing failed: {_describe_exception(exc)}",
                payload=_extract_error_payload(exc),
            )
        try:
            from .follow_sync import handle_follow_sync_item_success

            with session.begin_nested():
                handle_follow_sync_item_success(session, item=item, worker_name=worker_name)
        except Exception as exc:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="follow",
                level="warning",
                message=f"Follow-sync post-processing failed: {_describe_exception(exc)}",
                payload=_extract_error_payload(exc),
            )
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="finish",
            message="Pan transfer item completed successfully",
        )
        return True
    except Exception as exc:
        error_detail = _describe_exception(exc)
        batch = session.get(PanTransferBatch, int(item.batch_id))
        batch_cancelled = batch is not None and str(batch.status or "") == PAN_TRANSFER_BATCH_STATUS_CANCELLED
        batch_retry_delay_seconds = int(batch.retry_delay_seconds or 0) if batch is not None else 0
        if str(item.new_share_url or "").strip() and str(item.share_status or "") != PAN_TRANSFER_SHARE_STATUS_SHARED:
            item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
        if not str(item.new_share_url or "").strip():
            item.share_status = PAN_TRANSFER_SHARE_STATUS_FAILED
        if str(item.new_share_url or "").strip() and str(item.replacement_status or "") != PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED:
            item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_FAILED
        if not str(item.new_share_url or "").strip():
            item.validation_status = PAN_TRANSFER_VALIDATION_STATUS_PENDING
            item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_PENDING
        session.add(item)
        session.flush()
        retryable = True
        if isinstance(exc, PanTransferProviderError):
            retryable = bool(exc.retryable)
        retryable = retryable and not batch_cancelled
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="finish",
            level="error",
            message=f"Pan transfer item failed: {error_detail}",
            payload={
                "retryable": retryable,
                "batch_cancelled": batch_cancelled,
                "batch_id": int(item.batch_id),
                "batch_item_id": int(item.id),
                "retry_delay_seconds": batch_retry_delay_seconds,
                **_extract_error_payload(exc),
            },
        )
        mark_pan_transfer_item_error(
            session,
            item=item,
            error_message=error_detail,
            retryable=retryable,
        )
        try:
            from app.services.learning_resources import sync_learning_resource_after_transfer

            with session.begin_nested():
                sync_learning_resource_after_transfer(
                    session,
                    item=item,
                    success=False,
                    error_message=error_detail,
                )
        except Exception as learning_exc:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="learning_resource",
                level="warning",
                message=f"Learning resource failure hook failed: {_describe_exception(learning_exc)}",
                payload=_extract_error_payload(learning_exc),
            )
        try:
            from .follow_sync import handle_follow_sync_item_failure

            with session.begin_nested():
                handle_follow_sync_item_failure(
                    session,
                    item=item,
                    worker_name=worker_name,
                    error_message=error_detail,
                )
        except Exception as follow_exc:
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="follow",
                level="warning",
                message=f"Follow-sync failure hook failed: {_describe_exception(follow_exc)}",
                payload=_extract_error_payload(follow_exc),
            )
        return True
    finally:
        session.expire_on_commit = previous_expire_on_commit
