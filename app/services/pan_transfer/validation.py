from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import PanTransferAccount
from app.services.link_check.validator import LinkValidator

from .common import utcnow
from .providers import decrypt_account_credential, get_pan_transfer_provider
from .providers.base import PanTransferAccountValidationResult, PanTransferProviderError


async def validate_pan_transfer_account_credentials(
    *,
    account: PanTransferAccount,
) -> PanTransferAccountValidationResult:
    provider = get_pan_transfer_provider(str(account.platform or "").strip())
    credential_value = decrypt_account_credential(account)
    return await provider.validate_account(
        credential_value=credential_value,
        account_name=str(account.account_name or ""),
    )


async def validate_pan_transfer_account(
    session: Session,
    *,
    account_id: int,
) -> dict[str, Any]:
    account = session.get(PanTransferAccount, int(account_id))
    if account is None:
        raise LookupError("account not found")

    checked_at = utcnow()
    try:
        result = await validate_pan_transfer_account_credentials(account=account)
        account.last_validated_at = checked_at
        account.last_error_message = None
        account.extra_json = {
            **dict(account.extra_json or {}),
            "last_validation": {
                "ok": True,
                "detail_message": result.detail_message,
                "remote_user": result.remote_user,
                "payload": result.payload,
            },
        }
        session.add(account)
        session.flush()
        return {
            "account_id": int(account.id),
            "platform": str(account.platform or ""),
            "account_name": str(account.account_name or ""),
            "ok": True,
            "checked_at": checked_at,
            "detail_message": result.detail_message,
            "remote_user": result.remote_user,
            "payload": result.payload,
        }
    except Exception as exc:
        account.last_validated_at = checked_at
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
        if isinstance(exc, PanTransferProviderError):
            return {
                "account_id": int(account.id),
                "platform": str(account.platform or ""),
                "account_name": str(account.account_name or ""),
                "ok": False,
                "checked_at": checked_at,
                "detail_message": str(exc),
                "remote_user": None,
                "payload": dict(exc.payload or {}),
            }
        raise


async def validate_share_url(url: str) -> dict[str, Any]:
    validator = LinkValidator()
    result = await validator.check_single_link(url)
    is_valid = result.get("is_valid")
    if is_valid is True:
        status = "valid"
    elif is_valid is False:
        status = "invalid"
    else:
        status = "warning"
    return {
        "status": status,
        "detail_message": str(result.get("error_reason") or result.get("status") or "").strip() or None,
        "result": result,
    }
