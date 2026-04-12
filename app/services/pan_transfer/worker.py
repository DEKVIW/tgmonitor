from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import LinkTarget, PanTransferAccount, PanTransferBatchItem, ensure_runtime_storage_tables

from .common import build_staging_folder_name, generate_share_passcode, normalize_relative_path, utcnow
from .constants import (
    PAN_TRANSFER_REPLACEMENT_STATUS_FAILED,
    PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED,
    PAN_TRANSFER_SHARE_STATUS_FAILED,
    PAN_TRANSFER_SHARE_STATUS_SHARED,
    PAN_TRANSFER_VALIDATION_STATUS_INVALID,
)
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


async def _process_pan_transfer_item_async(
    session: Session,
    *,
    item: PanTransferBatchItem,
    worker_name: str,
) -> None:
    source_target = session.get(LinkTarget, int(item.link_target_id))
    if source_target is None:
        raise PanTransferProviderError("source link target not found", retryable=False)

    if not item.new_share_url:
        account = session.get(PanTransferAccount, int(item.target_account_id or 0))
        if account is None:
            raise PanTransferProviderError("target account not found", retryable=False)
        if not bool(account.is_enabled):
            raise PanTransferProviderError("target account is disabled", retryable=False)

        credential_value = decrypt_account_credential(account)
        provider = get_pan_transfer_provider(str(item.platform or ""))
        staging_root = normalize_relative_path(str(account.default_save_root or ""))
        staging_folder_name = _build_staging_name(item)
        share_mode = str(account.default_share_mode or "public").strip().lower() or "public"
        share_passcode = str(account.default_share_passcode or "").strip() or None
        if share_mode == "private" and not share_passcode:
            share_passcode = generate_share_passcode()
        share_expire_days = account.default_share_expire_days

        try:
            execution_result = await provider.transfer_and_share(
                credential_value=credential_value,
                account_name=str(account.account_name or ""),
                original_url=str(source_target.original_url or item.original_url or ""),
                original_passcode=str(source_target.passcode or "").strip() or None,
                staging_root=staging_root,
                staging_folder_name=staging_folder_name,
                share_mode=share_mode,
                share_passcode=share_passcode,
                share_expire_days=share_expire_days,
                title_hint=str(item.short_title or "") or None,
            )
            account.last_validated_at = utcnow()
            account.last_error_message = None
            account.extra_json = {
                **dict(account.extra_json or {}),
                "last_validation": {
                    "ok": True,
                    "detail_message": "Validated during transfer execution",
                    "payload": execution_result.payload,
                },
            }
            session.add(account)
            item.new_share_url = execution_result.new_share_url
            item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
            _merge_extra_json(
                item,
                {
                    "provider_payload": execution_result.payload,
                    "share_title": execution_result.share_title,
                    "share_passcode": execution_result.share_passcode,
                    "staging_root": execution_result.staging_root,
                    "staging_folder_name": execution_result.staging_folder_name,
                    "staging_folder_id": execution_result.staging_folder_id,
                },
            )
            session.add(item)
            session.flush()
        except Exception as exc:
            account.last_validated_at = utcnow()
            account.last_error_message = str(exc)[:2000]
            account.extra_json = {
                **dict(account.extra_json or {}),
                "last_validation": {
                    "ok": False,
                    "detail_message": str(exc),
                },
            }
            session.add(account)
            session.flush()
            raise

    validation_result = await validate_share_url(str(item.new_share_url or ""))
    item.last_validated_at = utcnow()
    item.validation_status = str(validation_result.get("status") or "warning")
    _merge_extra_json(
        item,
        {
            "share_validation": validation_result,
        },
    )
    session.add(item)
    session.flush()
    if item.validation_status == PAN_TRANSFER_VALIDATION_STATUS_INVALID:
        raise PanTransferProviderError(
            validation_result.get("detail_message") or "new share URL validation failed",
            retryable=True,
        )

    if str(item.replacement_status or "") != PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED:
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


def process_next_pan_transfer_item(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    item = claim_next_pan_transfer_batch_item(session, worker_name=worker_name)
    if item is None:
        return False

    try:
        asyncio.run(_process_pan_transfer_item_async(session, item=item, worker_name=worker_name))
        mark_pan_transfer_item_success(session, item=item)
        return True
    except Exception as exc:
        if str(item.new_share_url or "").strip() and str(item.share_status or "") != PAN_TRANSFER_SHARE_STATUS_SHARED:
            item.share_status = PAN_TRANSFER_SHARE_STATUS_SHARED
        if not str(item.new_share_url or "").strip():
            item.share_status = PAN_TRANSFER_SHARE_STATUS_FAILED
        if str(item.new_share_url or "").strip() and str(item.replacement_status or "") != PAN_TRANSFER_REPLACEMENT_STATUS_REPLACED:
            item.replacement_status = PAN_TRANSFER_REPLACEMENT_STATUS_FAILED
        session.add(item)
        session.flush()
        retryable = True
        if isinstance(exc, PanTransferProviderError):
            retryable = bool(exc.retryable)
        mark_pan_transfer_item_error(
            session,
            item=item,
            error_message=str(exc),
            retryable=retryable,
        )
        return True
