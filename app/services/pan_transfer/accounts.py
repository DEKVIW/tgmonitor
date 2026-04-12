from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import PanTransferAccount, PanTransferBatchItem
from app.services.secret_codec import encrypt_secret

from .constants import (
    ALLOWED_TRANSFER_ACCOUNT_AUTH_TYPES,
    ALLOWED_TRANSFER_SHARE_MODES,
    normalize_transfer_platform,
)


def _normalize_text(value: Any, *, field_name: str, allow_empty: bool = False, max_length: int | None = None) -> str:
    normalized = "" if value is None else str(value).strip()
    if max_length is not None and len(normalized) > max_length:
        raise ValueError(f"{field_name} is too long")
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_optional_int(value: Any, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


def _serialize_account(account: PanTransferAccount) -> dict[str, Any]:
    return {
        "id": int(account.id),
        "platform": str(account.platform or ""),
        "account_name": str(account.account_name or ""),
        "auth_type": str(account.auth_type or "cookie"),
        "default_save_root": str(account.default_save_root or ""),
        "default_share_mode": str(account.default_share_mode or "public"),
        "default_share_passcode": str(account.default_share_passcode or "") or None,
        "default_share_expire_days": account.default_share_expire_days,
        "is_enabled": bool(account.is_enabled),
        "is_default": bool(account.is_default),
        "credential_configured": bool(str(account.credential_encrypted or "").strip()),
        "last_validated_at": account.last_validated_at,
        "last_error_message": str(account.last_error_message or "") or None,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def _normalize_auth_type(value: Any) -> str:
    normalized = _normalize_text(value or "cookie", field_name="auth_type", max_length=32).lower()
    if normalized not in ALLOWED_TRANSFER_ACCOUNT_AUTH_TYPES:
        raise ValueError("auth_type must be cookie")
    return normalized


def _normalize_share_mode(value: Any) -> str:
    normalized = _normalize_text(value or "public", field_name="default_share_mode", max_length=32).lower()
    if normalized not in ALLOWED_TRANSFER_SHARE_MODES:
        raise ValueError("default_share_mode must be private or public")
    return normalized


def _clear_default_flag_for_platform(session: Session, *, platform: str, exclude_account_id: int | None = None) -> None:
    query = session.query(PanTransferAccount).filter(PanTransferAccount.platform == platform)
    if exclude_account_id is not None:
        query = query.filter(PanTransferAccount.id != int(exclude_account_id))
    query.update({"is_default": False}, synchronize_session=False)


def _assign_fallback_default(session: Session, *, platform: str) -> None:
    fallback = (
        session.query(PanTransferAccount)
        .filter(
            PanTransferAccount.platform == platform,
            PanTransferAccount.is_enabled.is_(True),
        )
        .order_by(PanTransferAccount.updated_at.desc(), PanTransferAccount.id.desc())
        .first()
    )
    if fallback is not None:
        fallback.is_default = True


def list_pan_transfer_accounts(session: Session, *, platform: str | None = None) -> list[dict[str, Any]]:
    query = session.query(PanTransferAccount)
    if platform:
        query = query.filter(PanTransferAccount.platform == normalize_transfer_platform(platform))
    rows = (
        query.order_by(
            PanTransferAccount.platform.asc(),
            PanTransferAccount.is_default.desc(),
            PanTransferAccount.is_enabled.desc(),
            PanTransferAccount.account_name.asc(),
            PanTransferAccount.id.desc(),
        )
        .all()
    )
    return [_serialize_account(row) for row in rows]


def get_recommended_accounts_by_platform(session: Session) -> dict[str, dict[str, Any]]:
    recommended: dict[str, dict[str, Any]] = {}
    rows = (
        session.query(PanTransferAccount)
        .filter(PanTransferAccount.is_enabled.is_(True))
        .order_by(
            PanTransferAccount.platform.asc(),
            PanTransferAccount.is_default.desc(),
            PanTransferAccount.updated_at.desc(),
            PanTransferAccount.id.desc(),
        )
        .all()
    )
    for row in rows:
        if row.platform in recommended:
            continue
        recommended[row.platform] = _serialize_account(row)
    return recommended


def create_pan_transfer_account(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    platform = normalize_transfer_platform(payload.get("platform"))
    account_name = _normalize_text(payload.get("account_name"), field_name="account_name", max_length=128)
    auth_type = _normalize_auth_type(payload.get("auth_type"))
    credential_value = _normalize_text(payload.get("credential_value"), field_name="credential_value", max_length=20000)
    default_save_root = _normalize_text(
        payload.get("default_save_root"),
        field_name="default_save_root",
        allow_empty=True,
        max_length=255,
    )
    default_share_mode = _normalize_share_mode(payload.get("default_share_mode"))
    default_share_passcode = _normalize_text(
        payload.get("default_share_passcode"),
        field_name="default_share_passcode",
        allow_empty=True,
        max_length=32,
    ) or None
    default_share_expire_days = _normalize_optional_int(
        payload.get("default_share_expire_days"),
        field_name="default_share_expire_days",
    )
    is_enabled = bool(payload.get("is_enabled", True))
    is_default = bool(payload.get("is_default", False))

    if is_default and not is_enabled:
        raise ValueError("default account must be enabled")

    existing = (
        session.query(PanTransferAccount)
        .filter(
            PanTransferAccount.platform == platform,
            PanTransferAccount.account_name == account_name,
        )
        .first()
    )
    if existing is not None:
        raise ValueError("account_name already exists on this platform")

    has_default = bool(
        session.query(PanTransferAccount.id)
        .filter(
            PanTransferAccount.platform == platform,
            PanTransferAccount.is_default.is_(True),
            PanTransferAccount.is_enabled.is_(True),
        )
        .first()
    )
    if is_enabled and not has_default:
        is_default = True

    if is_default:
        _clear_default_flag_for_platform(session, platform=platform)

    row = PanTransferAccount(
        platform=platform,
        account_name=account_name,
        auth_type=auth_type,
        credential_encrypted=encrypt_secret(credential_value),
        default_save_root=default_save_root,
        default_share_mode=default_share_mode,
        default_share_passcode=default_share_passcode,
        default_share_expire_days=default_share_expire_days,
        is_enabled=is_enabled,
        is_default=is_default,
    )
    session.add(row)
    session.flush()
    return _serialize_account(row)


def update_pan_transfer_account(session: Session, account_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = session.get(PanTransferAccount, int(account_id))
    if row is None:
        raise LookupError("account not found")

    if "platform" in payload:
        row.platform = normalize_transfer_platform(payload.get("platform"))
    if "account_name" in payload:
        row.account_name = _normalize_text(payload.get("account_name"), field_name="account_name", max_length=128)
    if "auth_type" in payload:
        row.auth_type = _normalize_auth_type(payload.get("auth_type"))
    if "default_save_root" in payload:
        row.default_save_root = _normalize_text(
            payload.get("default_save_root"),
            field_name="default_save_root",
            allow_empty=True,
            max_length=255,
        )
    if "default_share_mode" in payload:
        row.default_share_mode = _normalize_share_mode(payload.get("default_share_mode"))
    if "default_share_passcode" in payload:
        row.default_share_passcode = (
            _normalize_text(
                payload.get("default_share_passcode"),
                field_name="default_share_passcode",
                allow_empty=True,
                max_length=32,
            )
            or None
        )
    if "default_share_expire_days" in payload:
        row.default_share_expire_days = _normalize_optional_int(
            payload.get("default_share_expire_days"),
            field_name="default_share_expire_days",
        )
    if "is_enabled" in payload:
        row.is_enabled = bool(payload.get("is_enabled"))
    if "credential_value" in payload and payload.get("credential_value") not in (None, ""):
        row.credential_encrypted = encrypt_secret(
            _normalize_text(payload.get("credential_value"), field_name="credential_value", max_length=20000)
        )
    if bool(payload.get("clear_credential")):
        row.credential_encrypted = ""

    requested_default = bool(payload.get("is_default", row.is_default))
    if requested_default and not row.is_enabled:
        raise ValueError("default account must be enabled")

    duplicate = (
        session.query(PanTransferAccount)
        .filter(
            PanTransferAccount.platform == row.platform,
            PanTransferAccount.account_name == row.account_name,
            PanTransferAccount.id != row.id,
        )
        .first()
    )
    if duplicate is not None:
        raise ValueError("account_name already exists on this platform")

    if requested_default:
        _clear_default_flag_for_platform(session, platform=row.platform, exclude_account_id=int(row.id))
        row.is_default = True
    else:
        row.is_default = False

    session.flush()

    has_enabled_default = bool(
        session.query(PanTransferAccount.id)
        .filter(
            PanTransferAccount.platform == row.platform,
            PanTransferAccount.is_enabled.is_(True),
            PanTransferAccount.is_default.is_(True),
        )
        .first()
    )
    if not has_enabled_default:
        _assign_fallback_default(session, platform=row.platform)
        session.flush()

    return _serialize_account(row)


def delete_pan_transfer_account(session: Session, account_id: int) -> dict[str, Any]:
    row = session.get(PanTransferAccount, int(account_id))
    if row is None:
        raise LookupError("account not found")

    in_use = bool(
        session.query(PanTransferBatchItem.id)
        .filter(PanTransferBatchItem.target_account_id == int(account_id))
        .first()
    )
    if in_use:
        raise ValueError("account is referenced by pan transfer batches; delete related batches first")

    platform = str(row.platform or "")
    was_default = bool(row.is_default)
    deleted_id = int(row.id)
    session.delete(row)
    session.flush()

    if was_default and platform:
        _assign_fallback_default(session, platform=platform)
        session.flush()

    return {
        "id": deleted_id,
        "platform": platform,
        "deleted": True,
    }
