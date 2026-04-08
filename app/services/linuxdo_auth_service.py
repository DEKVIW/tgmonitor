from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import parse, request

from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import AccountBatch, AuthIdentity, SystemSettings, UserAccount, engine, ensure_runtime_storage_tables
from app.services.account_auth_service import create_provider_login_session
from app.services.account_service import bootstrap_account_storage, get_user_runtime_settings, resolve_expiration
from app.services.secret_codec import decrypt_secret, encrypt_secret
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
    ensure_runtime_configuration_seeded,
)

logger = logging.getLogger(__name__)

LINUXDO_AUTH_PROVIDER = "linuxdo"
LINUXDO_EXTRA_KEY = "linuxdo_auth"
LINUXDO_BATCH_SOURCE_TYPE = "oauth_open"
LINUXDO_STATE_ALGORITHM = "HS256"
LINUXDO_STATE_TTL_SECONDS = 600
LINUXDO_AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
LINUXDO_TOKEN_URLS = (
    "https://connect.linux.do/oauth2/token",
    "https://connect.linuxdo.org/oauth2/token",
)
LINUXDO_USERINFO_URLS = (
    "https://connect.linux.do/api/user",
    "https://connect.linuxdo.org/api/user",
)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _coerce_text(value: Any, default: str = "", *, max_length: int | None = None) -> str:
    normalized = default if value is None else str(value).strip()
    if not normalized:
        normalized = default
    if max_length is not None:
        normalized = normalized[:max_length]
    return normalized


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _require_url(value: str, field_name: str) -> str:
    normalized = _coerce_text(value, "", max_length=2000)
    if not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return normalized


def _default_storage_values() -> dict[str, Any]:
    return {
        "enabled": False,
        "allow_new_accounts": False,
        "client_id": "",
        "client_secret_encrypted": "",
    }


def _normalize_storage_values(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return {
        "enabled": _coerce_bool(payload.get("enabled"), False),
        "allow_new_accounts": _coerce_bool(payload.get("allow_new_accounts"), False),
        "client_id": _coerce_text(payload.get("client_id"), "", max_length=512),
        "client_secret_encrypted": _coerce_text(payload.get("client_secret_encrypted"), "", max_length=8000),
    }


def _ensure_system_settings_record(session: Session) -> SystemSettings:
    record = session.get(SystemSettings, SYSTEM_SETTINGS_SINGLETON_ID)
    if record is not None:
        return record
    record = SystemSettings(id=SYSTEM_SETTINGS_SINGLETON_ID, **build_default_system_settings_values())
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _read_storage_values(session: Session) -> tuple[SystemSettings, dict[str, Any]]:
    ensure_runtime_configuration_seeded()
    record = _ensure_system_settings_record(session)
    extra_json = record.extra_json if isinstance(record.extra_json, dict) else {}
    return record, _normalize_storage_values(extra_json.get(LINUXDO_EXTRA_KEY))


def _write_storage_values(
    session: Session,
    record: SystemSettings,
    storage_values: dict[str, Any],
    *,
    updated_by: str | None,
) -> dict[str, Any]:
    extra_json = dict(record.extra_json) if isinstance(record.extra_json, dict) else {}
    extra_json[LINUXDO_EXTRA_KEY] = storage_values
    record.extra_json = extra_json
    record.updated_by = updated_by
    session.add(record)
    session.commit()
    session.refresh(record)
    return _normalize_storage_values((record.extra_json or {}).get(LINUXDO_EXTRA_KEY))


def _count_batch_accounts(session: Session, batch_ids: list[int]) -> dict[int, int]:
    if not batch_ids:
        return {}
    rows = (
        session.query(UserAccount.source_batch_id, func.count(UserAccount.id))
        .filter(UserAccount.source_batch_id.in_(batch_ids))
        .group_by(UserAccount.source_batch_id)
        .all()
    )
    return {int(batch_id): int(count) for batch_id, count in rows if batch_id is not None}


def _get_linuxdo_batches(session: Session) -> list[AccountBatch]:
    return (
        session.query(AccountBatch)
        .filter(AccountBatch.provider_scope == LINUXDO_AUTH_PROVIDER)
        .order_by(AccountBatch.created_at.desc(), AccountBatch.id.desc())
        .all()
    )


def _is_batch_in_window(batch: AccountBatch, *, now: datetime) -> bool:
    if not batch.is_enabled:
        return False
    if batch.starts_at is not None and batch.starts_at > now:
        return False
    if batch.ends_at is not None and batch.ends_at <= now:
        return False
    return True


def _serialize_batch(batch: AccountBatch, *, allocated_accounts: int, now: datetime) -> dict[str, Any]:
    max_accounts = int(batch.max_accounts or 0) if batch.max_accounts is not None else None
    remaining_accounts = None if max_accounts is None else max(0, max_accounts - allocated_accounts)
    is_full = max_accounts is not None and allocated_accounts >= max_accounts
    in_window = _is_batch_in_window(batch, now=now)
    admission_open = in_window and not is_full
    if admission_open:
        status = "open"
    elif is_full:
        status = "full"
    elif batch.is_enabled and batch.starts_at is not None and batch.starts_at > now:
        status = "scheduled"
    elif batch.is_enabled and batch.ends_at is not None and batch.ends_at <= now:
        status = "ended"
    elif batch.is_enabled:
        status = "paused"
    else:
        status = "disabled"

    return {
        "id": batch.id,
        "batch_name": batch.batch_name,
        "batch_code": batch.batch_code,
        "is_enabled": bool(batch.is_enabled),
        "default_role": batch.default_role,
        "validity_mode": batch.validity_mode,
        "validity_unit": batch.validity_unit,
        "validity_value": batch.validity_value,
        "fixed_expires_at": _to_iso(batch.fixed_expires_at),
        "starts_at": _to_iso(batch.starts_at),
        "ends_at": _to_iso(batch.ends_at),
        "max_accounts": max_accounts,
        "allocated_accounts": allocated_accounts,
        "remaining_accounts": remaining_accounts,
        "admission_open": admission_open,
        "status": status,
        "notes": batch.notes or "",
        "created_at": _to_iso(batch.created_at),
        "created_by": batch.created_by,
    }


def _build_mode_summary(mode: str, batch: dict[str, Any] | None) -> str:
    if mode == "hidden":
        return "LinuxDo login is hidden on the login page"
    if batch and batch.get("status") == "full":
        return "Only previously bound LinuxDo accounts can sign in because the current batch is full"
    if batch and batch.get("status") == "scheduled":
        return "LinuxDo login is visible, but new-account admission will open when the batch start time is reached"
    if batch and batch.get("status") == "ended":
        return "LinuxDo login is visible, but new-account admission has ended for the current batch"
    if mode == "open" and batch:
        remaining = batch.get("remaining_accounts")
        if remaining is None:
            return "LinuxDo login is open and the current batch has no seat limit"
        return f"LinuxDo login is open and the current batch still has {remaining} seats"
    return "LinuxDo login is visible, but only previously bound accounts can sign in"


def _build_response_values(
    storage_values: dict[str, Any],
    *,
    current_batch: dict[str, Any] | None,
    recent_batches: list[dict[str, Any]],
    bound_account_count: int,
) -> dict[str, Any]:
    client_secret_configured = bool(storage_values["client_secret_encrypted"])
    configured = bool(storage_values["client_id"] and client_secret_configured)
    if not storage_values["enabled"] or not configured:
        login_mode = "hidden"
    elif storage_values["allow_new_accounts"] and current_batch and current_batch.get("admission_open"):
        login_mode = "open"
    else:
        login_mode = "existing_only"

    return {
        "enabled": bool(storage_values["enabled"]),
        "allow_new_accounts": bool(storage_values["allow_new_accounts"]),
        "client_id": storage_values["client_id"],
        "client_secret_configured": client_secret_configured,
        "configured": configured,
        "login_mode": login_mode,
        "status_summary": _build_mode_summary(login_mode, current_batch),
        "bound_account_count": bound_account_count,
        "current_batch": current_batch,
        "recent_batches": recent_batches,
    }


def _build_public_response_values(storage_values: dict[str, Any], *, current_batch: dict[str, Any] | None) -> dict[str, Any]:
    client_secret_configured = bool(storage_values["client_secret_encrypted"])
    configured = bool(storage_values["client_id"] and client_secret_configured)
    if not storage_values["enabled"] or not configured:
        mode = "hidden"
    elif storage_values["allow_new_accounts"] and current_batch and current_batch.get("admission_open"):
        mode = "open"
    else:
        mode = "existing_only"

    remaining_accounts = current_batch.get("remaining_accounts") if current_batch else None
    return {
        "visible": mode != "hidden",
        "mode": mode,
        "status_summary": _build_mode_summary(mode, current_batch),
        "batch_name": current_batch.get("batch_name") if current_batch else None,
        "remaining_accounts": remaining_accounts,
    }


def _load_state_snapshot(session: Session) -> dict[str, Any]:
    storage_values = _read_storage_values(session)[1]
    now = _utc_now()
    batches = _get_linuxdo_batches(session)
    counts = _count_batch_accounts(session, [batch.id for batch in batches])
    serialized_batches = [_serialize_batch(batch, allocated_accounts=counts.get(batch.id, 0), now=now) for batch in batches]
    current_batch = next((item for item in serialized_batches if item["is_enabled"]), None)
    bound_account_count = (
        session.query(func.count(AuthIdentity.id))
        .filter(AuthIdentity.provider == LINUXDO_AUTH_PROVIDER)
        .scalar()
        or 0
    )
    return _build_response_values(
        storage_values,
        current_batch=current_batch,
        recent_batches=serialized_batches[:8],
        bound_account_count=int(bound_account_count),
    )


def get_linuxdo_admin_state() -> dict[str, Any]:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        return _load_state_snapshot(session)


def get_linuxdo_public_state() -> dict[str, Any]:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        storage_values = _read_storage_values(session)[1]
        now = _utc_now()
        batches = _get_linuxdo_batches(session)
        counts = _count_batch_accounts(session, [batch.id for batch in batches])
        serialized_batches = [_serialize_batch(batch, allocated_accounts=counts.get(batch.id, 0), now=now) for batch in batches]
        current_batch = next((item for item in serialized_batches if item["is_enabled"]), None)
        return _build_public_response_values(storage_values, current_batch=current_batch)


def apply_linuxdo_config(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    payload = values if isinstance(values, dict) else {}
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        record, current_storage = _read_storage_values(session)
        merged = dict(current_storage)
        merged["enabled"] = _coerce_bool(payload.get("enabled"), merged["enabled"])
        merged["allow_new_accounts"] = _coerce_bool(payload.get("allow_new_accounts"), merged["allow_new_accounts"])
        merged["client_id"] = _coerce_text(payload.get("client_id"), "", max_length=512)

        if _coerce_bool(payload.get("clear_client_secret"), False):
            merged["client_secret_encrypted"] = ""
        else:
            client_secret = _coerce_text(payload.get("client_secret"), "", max_length=4000)
            if client_secret:
                merged["client_secret_encrypted"] = encrypt_secret(client_secret)

        storage_values = _write_storage_values(session, record, merged, updated_by=updated_by)
        now = _utc_now()
        batches = _get_linuxdo_batches(session)
        counts = _count_batch_accounts(session, [batch.id for batch in batches])
        serialized_batches = [_serialize_batch(batch, allocated_accounts=counts.get(batch.id, 0), now=now) for batch in batches]
        current_batch = next((item for item in serialized_batches if item["is_enabled"]), None)
        bound_account_count = (
            session.query(func.count(AuthIdentity.id))
            .filter(AuthIdentity.provider == LINUXDO_AUTH_PROVIDER)
            .scalar()
            or 0
        )
        return _build_response_values(
            storage_values,
            current_batch=current_batch,
            recent_batches=serialized_batches[:8],
            bound_account_count=int(bound_account_count),
        )


def _disable_other_batches(session: Session, *, active_batch_id: int) -> None:
    rows = (
        session.query(AccountBatch)
        .filter(
            AccountBatch.provider_scope == LINUXDO_AUTH_PROVIDER,
            AccountBatch.id != active_batch_id,
            AccountBatch.is_enabled.is_(True),
        )
        .all()
    )
    for batch in rows:
        batch.is_enabled = False
        session.add(batch)


def _build_batch_code() -> str:
    return f"linuxdo-{_utc_now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"


def _validate_batch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    batch_name = _coerce_text(payload.get("batch_name"), "", max_length=128)
    if not batch_name:
        raise ValueError("batch_name is required")
    default_role = _coerce_text(payload.get("default_role"), "user", max_length=32).lower()
    if default_role not in {"admin", "user"}:
        raise ValueError("default_role must be admin or user")
    validity_mode = _coerce_text(payload.get("validity_mode"), "duration", max_length=32).lower()
    if validity_mode not in {"permanent", "duration", "fixed_at"}:
        raise ValueError("validity_mode must be permanent, duration or fixed_at")
    validity_unit = _coerce_text(payload.get("validity_unit"), "month", max_length=16).lower()
    if validity_unit not in {"day", "month", "year"}:
        raise ValueError("validity_unit must be day, month or year")
    validity_value = _coerce_int(payload.get("validity_value"), 1, minimum=1, maximum=3650)
    fixed_expires_at = _coerce_datetime(payload.get("fixed_expires_at"))
    if validity_mode == "fixed_at" and fixed_expires_at is None:
        raise ValueError("fixed_expires_at is required when validity_mode is fixed_at")
    starts_at = _coerce_datetime(payload.get("starts_at"))
    ends_at = _coerce_datetime(payload.get("ends_at"))
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise ValueError("ends_at must be later than starts_at")
    max_accounts = _coerce_int(payload.get("max_accounts"), 1, minimum=1, maximum=100000)
    return {
        "batch_name": batch_name,
        "default_role": default_role,
        "validity_mode": validity_mode,
        "validity_unit": validity_unit,
        "validity_value": validity_value,
        "fixed_expires_at": fixed_expires_at,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "is_enabled": _coerce_bool(payload.get("is_enabled"), True),
        "max_accounts": max_accounts,
        "notes": _coerce_text(payload.get("notes"), "", max_length=2000),
    }


def create_linuxdo_batch(values: dict[str, Any], *, created_by: str | None = None) -> dict[str, Any]:
    payload = _validate_batch_payload(values)
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        batch = AccountBatch(
            batch_name=payload["batch_name"],
            batch_code=_build_batch_code(),
            source_type=LINUXDO_BATCH_SOURCE_TYPE,
            provider_scope=LINUXDO_AUTH_PROVIDER,
            default_role=payload["default_role"],
            validity_mode=payload["validity_mode"],
            validity_unit=payload["validity_unit"],
            validity_value=payload["validity_value"],
            fixed_expires_at=payload["fixed_expires_at"],
            is_enabled=payload["is_enabled"],
            starts_at=payload["starts_at"],
            ends_at=payload["ends_at"],
            max_accounts=payload["max_accounts"],
            notes=payload["notes"],
            created_by=created_by,
        )
        session.add(batch)
        session.flush()
        if batch.is_enabled:
            _disable_other_batches(session, active_batch_id=batch.id)
        session.commit()
        return _load_state_snapshot(session)


def update_linuxdo_batch(batch_id: int, values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    payload = _validate_batch_payload(values)
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        batch = (
            session.query(AccountBatch)
            .filter(
                AccountBatch.id == batch_id,
                AccountBatch.provider_scope == LINUXDO_AUTH_PROVIDER,
            )
            .first()
        )
        if batch is None:
            raise ValueError(f"linuxdo batch {batch_id} does not exist")
        batch.batch_name = payload["batch_name"]
        batch.default_role = payload["default_role"]
        batch.validity_mode = payload["validity_mode"]
        batch.validity_unit = payload["validity_unit"]
        batch.validity_value = payload["validity_value"]
        batch.fixed_expires_at = payload["fixed_expires_at"]
        batch.is_enabled = payload["is_enabled"]
        batch.starts_at = payload["starts_at"]
        batch.ends_at = payload["ends_at"]
        batch.max_accounts = payload["max_accounts"]
        batch.notes = payload["notes"]
        batch.created_by = updated_by or batch.created_by
        session.add(batch)
        session.flush()
        if batch.is_enabled:
            _disable_other_batches(session, active_batch_id=batch.id)
        session.commit()
        return _load_state_snapshot(session)


def _get_configured_storage_values(session: Session) -> dict[str, Any]:
    storage_values = _read_storage_values(session)[1]
    if not storage_values["enabled"]:
        raise ValueError("LinuxDo login is disabled")
    if not storage_values["client_id"] or not storage_values["client_secret_encrypted"]:
        raise ValueError("LinuxDo login is not fully configured")
    return storage_values


def _build_state_token(*, redirect_uri: str) -> str:
    payload = {
        "purpose": "linuxdo_oauth_state",
        "provider": LINUXDO_AUTH_PROVIDER,
        "redirect_uri": redirect_uri,
        "nonce": secrets.token_urlsafe(12),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=LINUXDO_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.SECRET_SALT, algorithm=LINUXDO_STATE_ALGORITHM)


def _decode_state_token(state_token: str, *, redirect_uri: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(state_token, settings.SECRET_SALT, algorithms=[LINUXDO_STATE_ALGORITHM])
    except JWTError as exc:
        raise ValueError("LinuxDo login state is invalid or expired") from exc
    if payload.get("purpose") != "linuxdo_oauth_state" or payload.get("provider") != LINUXDO_AUTH_PROVIDER:
        raise ValueError("LinuxDo login state is invalid")
    if _coerce_text(payload.get("redirect_uri")) != redirect_uri:
        raise ValueError("LinuxDo login redirect URI does not match")
    return payload


def build_linuxdo_authorize_url(*, redirect_uri: str) -> str:
    normalized_redirect_uri = _require_url(redirect_uri, "redirect_uri")
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        storage_values = _get_configured_storage_values(session)
    state_token = _build_state_token(redirect_uri=normalized_redirect_uri)
    query = parse.urlencode(
        {
            "client_id": storage_values["client_id"],
            "response_type": "code",
            "redirect_uri": normalized_redirect_uri,
            "state": state_token,
        }
    )
    return f"{LINUXDO_AUTHORIZE_URL}?{query}"


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    form_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: bytes | None = None
    request_headers = dict(headers or {})
    if form_data is not None:
        body = parse.urlencode({key: value for key, value in form_data.items() if value is not None}).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url, data=body, headers=request_headers, method=method)
    with request.urlopen(req, timeout=20) as response:
        raw_body = response.read().decode("utf-8")
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise RuntimeError("LinuxDo upstream returned an invalid payload")
    return payload


def _request_json_with_fallback(
    *,
    method: str,
    urls: tuple[str, ...],
    headers: dict[str, str] | None = None,
    form_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for url in urls:
        try:
            return _request_json(method=method, url=url, headers=headers, form_data=form_data)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("LinuxDo upstream request failed for %s: %s", url, exc)
    raise RuntimeError("LinuxDo upstream is unavailable") from last_error


def _exchange_code_for_access_token(*, code: str, redirect_uri: str, storage_values: dict[str, Any]) -> str:
    client_secret = decrypt_secret(
        storage_values["client_secret_encrypted"],
        error_message="Unable to decrypt LinuxDo client secret; please verify SECRET_SALT",
    )
    token_payload = _request_json_with_fallback(
        method="POST",
        urls=LINUXDO_TOKEN_URLS,
        form_data={
            "grant_type": "authorization_code",
            "client_id": storage_values["client_id"],
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    access_token = _coerce_text(token_payload.get("access_token"), "", max_length=4000)
    if not access_token:
        raise RuntimeError("LinuxDo token exchange did not return an access token")
    return access_token


def _fetch_linuxdo_userinfo(*, access_token: str) -> dict[str, Any]:
    payload = _request_json_with_fallback(
        method="GET",
        urls=LINUXDO_USERINFO_URLS,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_payload = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    if not isinstance(user_payload, dict):
        raise RuntimeError("LinuxDo userinfo response is invalid")
    user_id = _coerce_text(user_payload.get("id"), "", max_length=255)
    username = _coerce_text(user_payload.get("username"), "", max_length=255)
    if not user_id or not username:
        raise RuntimeError("LinuxDo userinfo is missing id or username")
    if not _coerce_bool(user_payload.get("active"), True):
        raise ValueError("LinuxDo account is not active")
    if _coerce_bool(user_payload.get("silenced"), False):
        raise ValueError("LinuxDo account is silenced and cannot sign in")
    return user_payload


def _find_linuxdo_identity(session: Session, provider_user_id: str) -> AuthIdentity | None:
    return (
        session.query(AuthIdentity)
        .filter(
            AuthIdentity.provider == LINUXDO_AUTH_PROVIDER,
            AuthIdentity.provider_user_id == provider_user_id,
        )
        .first()
    )


def _build_linuxdo_identity_extra(userinfo: dict[str, Any]) -> dict[str, Any]:
    return {
        "linuxdo_username": _coerce_text(userinfo.get("username"), "", max_length=255),
        "linuxdo_name": _coerce_text(userinfo.get("name"), "", max_length=255),
        "avatar_template": _coerce_text(userinfo.get("avatar_template"), "", max_length=1000),
        "trust_level": userinfo.get("trust_level"),
        "active": _coerce_bool(userinfo.get("active"), True),
        "silenced": _coerce_bool(userinfo.get("silenced"), False),
    }


def _sanitize_username_candidate(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", _coerce_text(value, "", max_length=64)).strip("._-")
    return normalized[:64]


def _generate_account_username(session: Session, *, remote_username: str, provider_user_id: str) -> str:
    base_candidate = _sanitize_username_candidate(remote_username) or f"linuxdo_{provider_user_id}"
    base_candidate = base_candidate[:64]
    candidates = [base_candidate]
    prefixed = f"linuxdo_{base_candidate}"[:64]
    if prefixed not in candidates:
        candidates.append(prefixed)
    candidates.append(f"linuxdo_{provider_user_id}"[:64])

    for candidate in candidates:
        exists = session.query(UserAccount.id).filter(UserAccount.username == candidate).first()
        if exists is None:
            return candidate

    suffix_seed = provider_user_id[-6:] if provider_user_id else secrets.token_hex(3)
    candidate = f"{prefixed[: max(1, 64 - len(suffix_seed) - 1)]}_{suffix_seed}"[:64]
    if session.query(UserAccount.id).filter(UserAccount.username == candidate).first() is None:
        return candidate

    while True:
        token = secrets.token_hex(2)
        candidate = f"{prefixed[: max(1, 64 - len(token) - 1)]}_{token}"[:64]
        if session.query(UserAccount.id).filter(UserAccount.username == candidate).first() is None:
            return candidate


def _resolve_admission_batch_for_update(session: Session, *, now: datetime) -> tuple[AccountBatch | None, dict[int, int]]:
    batches = (
        session.query(AccountBatch)
        .filter(AccountBatch.provider_scope == LINUXDO_AUTH_PROVIDER)
        .order_by(AccountBatch.created_at.desc(), AccountBatch.id.desc())
        .with_for_update()
        .all()
    )
    counts = _count_batch_accounts(session, [batch.id for batch in batches])
    for batch in batches:
        if not _is_batch_in_window(batch, now=now):
            continue
        max_accounts = batch.max_accounts
        allocated = counts.get(batch.id, 0)
        if max_accounts is not None and allocated >= int(max_accounts):
            continue
        return batch, counts
    return None, counts


def _provision_linuxdo_account(
    session: Session,
    *,
    batch: AccountBatch,
    userinfo: dict[str, Any],
    now: datetime,
) -> AuthIdentity:
    runtime_settings = get_user_runtime_settings()
    username = _generate_account_username(
        session,
        remote_username=_coerce_text(userinfo.get("username"), "", max_length=255),
        provider_user_id=_coerce_text(userinfo.get("id"), "", max_length=255),
    )
    expires_at = resolve_expiration(
        validity_mode=batch.validity_mode,
        validity_unit=batch.validity_unit,
        validity_value=batch.validity_value,
        fixed_expires_at=batch.fixed_expires_at,
        runtime_settings=runtime_settings,
    )
    display_name = _coerce_text(userinfo.get("name"), _coerce_text(userinfo.get("username"), username), max_length=128)
    account = UserAccount(
        username=username,
        display_name=display_name,
        email="",
        role=batch.default_role if batch.default_role in {"admin", "user"} else "user",
        status="active",
        account_source=LINUXDO_AUTH_PROVIDER,
        source_batch_id=batch.id,
        expires_at=expires_at,
        must_change_password=False,
        session_limit_override=batch.default_session_limit_override,
        created_at=now,
        updated_at=now,
        created_by=LINUXDO_AUTH_PROVIDER,
        updated_by=LINUXDO_AUTH_PROVIDER,
    )
    session.add(account)
    session.flush()
    identity = AuthIdentity(
        account_id=account.id,
        provider=LINUXDO_AUTH_PROVIDER,
        provider_user_id=_coerce_text(userinfo.get("id"), "", max_length=255),
        login_name=_coerce_text(userinfo.get("username"), "", max_length=255) or username,
        password_hash=None,
        identity_status="active",
        linked_at=now,
        extra_json=_build_linuxdo_identity_extra(userinfo),
    )
    session.add(identity)
    session.flush()
    return identity


def exchange_linuxdo_code_for_login(
    *,
    code: str,
    state_token: str,
    redirect_uri: str,
    client_instance_id: str | None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    normalized_code = _coerce_text(code, "", max_length=2048)
    if not normalized_code:
        raise ValueError("code is required")
    normalized_redirect_uri = _require_url(redirect_uri, "redirect_uri")
    _decode_state_token(state_token, redirect_uri=normalized_redirect_uri)

    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        storage_values = _get_configured_storage_values(session)
    access_token = _exchange_code_for_access_token(
        code=normalized_code,
        redirect_uri=normalized_redirect_uri,
        storage_values=storage_values,
    )
    userinfo = _fetch_linuxdo_userinfo(access_token=access_token)
    provider_user_id = _coerce_text(userinfo.get("id"), "", max_length=255)
    remote_username = _coerce_text(userinfo.get("username"), "", max_length=255)
    current_time = _utc_now()

    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        storage_values = _get_configured_storage_values(session)
        identity = _find_linuxdo_identity(session, provider_user_id)
        if identity is None:
            if not storage_values["allow_new_accounts"]:
                raise ValueError("LinuxDo login currently only allows previously bound accounts")
            batch, counts = _resolve_admission_batch_for_update(session, now=current_time)
            if batch is None:
                raise ValueError("No LinuxDo admission batch is currently available")
            allocated = counts.get(batch.id, 0)
            if batch.max_accounts is not None and allocated >= int(batch.max_accounts):
                raise ValueError("The current LinuxDo admission batch is already full")
            identity = _provision_linuxdo_account(session, batch=batch, userinfo=userinfo, now=current_time)
        else:
            identity.login_name = remote_username or identity.login_name
            identity.identity_status = "active"
            identity.extra_json = {
                **(identity.extra_json if isinstance(identity.extra_json, dict) else {}),
                **_build_linuxdo_identity_extra(userinfo),
            }
            identity.last_login_at = current_time
            session.add(identity)

        session.commit()

    login_result = create_provider_login_session(
        provider=LINUXDO_AUTH_PROVIDER,
        provider_user_id=provider_user_id,
        client_instance_id=client_instance_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    if login_result is None:
        raise ValueError("The bound account is disabled, expired, or unavailable")
    return login_result
