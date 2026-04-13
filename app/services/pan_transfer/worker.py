from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import LinkTarget, PanTransferAccount, PanTransferBatch, PanTransferBatchItem, ensure_runtime_storage_tables

from .common import build_staging_folder_name, generate_share_passcode, normalize_relative_path, utcnow
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
from .queue import claim_next_pan_transfer_batch_item, mark_pan_transfer_item_error, mark_pan_transfer_item_success
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


def _iso_utc_now() -> str:
    return utcnow().isoformat() + "Z"


def _extract_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PanTransferProviderError):
        return dict(exc.payload or {})
    return {}


def _is_batch_cancelled(session: Session, *, batch_id: int) -> bool:
    batch = session.get(PanTransferBatch, int(batch_id))
    return batch is not None and str(batch.status or "") == PAN_TRANSFER_BATCH_STATUS_CANCELLED


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
    if not share_mode:
        return None
    return dict(share_request)


def _build_share_request(
    *,
    account: PanTransferAccount,
    item: PanTransferBatchItem,
    staging_root: str,
    staging_folder_name: str,
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
    }


def _build_share_request_from_snapshot(
    *,
    account: PanTransferAccount,
    item: PanTransferBatchItem,
    staging_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return _build_share_request(
        account=account,
        item=item,
        staging_root=normalize_relative_path(str(staging_snapshot.get("root") or "")),
        staging_folder_name=str(staging_snapshot.get("folder_name") or _build_staging_name(item)),
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

    staging_snapshot = _get_staging_snapshot(item)
    share_request = _get_share_request(item)

    if not str(item.new_share_url or "").strip():
        if staging_snapshot is None:
            staging_root = normalize_relative_path(str(account.default_save_root or ""))
            staging_folder_name = _build_staging_name(item)
            share_request = _build_share_request(
                account=account,
                item=item,
                staging_root=staging_root,
                staging_folder_name=staging_folder_name,
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
                },
            )
            try:
                transfer_result = await provider.transfer_to_staging(
                    credential_value=credential_value,
                    account_name=str(account.account_name or ""),
                    original_url=str(source_target.original_url or item.original_url or ""),
                    original_passcode=str(source_target.passcode or "").strip() or None,
                    staging_root=staging_root,
                    staging_folder_name=staging_folder_name,
                    title_hint=str(share_request.get("title_hint") or "") or None,
                )
            except Exception as exc:
                _mark_account_validation(
                    account,
                    ok=False,
                    detail_message=str(exc),
                    payload=_extract_error_payload(exc),
                )
                session.add(account)
                session.flush()
                append_pan_transfer_execution_log(
                    session,
                    item=item,
                    stage="transfer",
                    level="error",
                    message=f"Transfer to staging failed: {exc}",
                    payload=_extract_error_payload(exc),
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
                    "provider_payload": dict(transfer_result.payload or {}),
                },
            )
        else:
            if share_request is None:
                share_request = _build_share_request_from_snapshot(
                    account=account,
                    item=item,
                    staging_snapshot=staging_snapshot,
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
                },
            )

        item.share_status = PAN_TRANSFER_SHARE_STATUS_PENDING
        session.add(item)
        session.flush()
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
            },
        )
        try:
            share_result = await provider.share_staging_target(
                credential_value=credential_value,
                account_name=str(account.account_name or ""),
                staging_root=normalize_relative_path(str((staging_snapshot or {}).get("root") or "")),
                staging_folder_name=str((staging_snapshot or {}).get("folder_name") or ""),
                staging_folder_id=str((staging_snapshot or {}).get("folder_id") or "") or None,
                share_mode=str((share_request or {}).get("share_mode") or "public"),
                share_passcode=str((share_request or {}).get("share_passcode") or "").strip() or None,
                share_expire_days=(share_request or {}).get("share_expire_days"),
                title_hint=str((share_request or {}).get("title_hint") or "") or None,
            )
        except Exception as exc:
            _mark_account_validation(
                account,
                ok=False,
                detail_message=str(exc),
                payload=_extract_error_payload(exc),
            )
            session.add(account)
            session.flush()
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="share",
                level="error",
                message=f"Share creation failed: {exc}",
                payload=_extract_error_payload(exc),
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
        validation_result = await validate_share_url(str(item.new_share_url or ""))
    except Exception as exc:
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="validate",
            level="error",
            message=f"Share URL validation failed: {exc}",
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
        raise PanTransferProviderError(
            validation_result.get("detail_message") or "new share URL validation failed",
            retryable=True,
            payload=dict(validation_result),
        )

    if str(item.replacement_status or "") != PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED:
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
            append_pan_transfer_execution_log(
                session,
                item=item,
                stage="replace",
                level="error",
                message=f"Link replacement failed: {exc}",
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

    try:
        asyncio.run(_process_pan_transfer_item_async(session, item=item, worker_name=worker_name))
        mark_pan_transfer_item_success(session, item=item)
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="finish",
            message="Pan transfer item completed successfully",
        )
        return True
    except Exception as exc:
        batch_cancelled = _is_batch_cancelled(session, batch_id=int(item.batch_id))
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
            message=f"Pan transfer item failed: {exc}",
            payload={
                "retryable": retryable,
                "batch_cancelled": batch_cancelled,
                **_extract_error_payload(exc),
            },
        )
        mark_pan_transfer_item_error(
            session,
            item=item,
            error_message=str(exc),
            retryable=retryable,
        )
        return True
