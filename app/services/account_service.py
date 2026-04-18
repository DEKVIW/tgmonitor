from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    AccountBatch,
    AuthIdentity,
    AuthSession,
    SystemSettings,
    UserAccount,
    engine,
    ensure_runtime_storage_tables,
)
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
    ensure_runtime_configuration_seeded,
)

logger = logging.getLogger(__name__)

USER_DATA_FILE = Path("users.json")
LOCAL_AUTH_PROVIDER = "local"
ACCOUNT_RUNTIME_EXTRA_KEY = "account_runtime"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
_UNSET = object()

USER_ROLES = {
    "admin": "系统管理员",
    "user": "普通用户",
}

ACCOUNT_STATUSES = {
    "active": "正常",
    "disabled": "已禁用",
    "locked": "已锁定",
}

VALIDITY_UNITS = {"day", "month", "year"}
SORTABLE_USER_FIELDS = {
    "username",
    "name",
    "email",
    "role",
    "account_source",
    "status",
    "effective_status",
    "expires_at",
    "remaining_days",
    "active_session_count",
    "last_login_at",
    "last_seen_at",
    "created_at",
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _utcnow() -> datetime:
    return datetime.utcnow()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:
        logger.warning("Password verification failed: %s", exc)
        return False


def _coerce_text(value: Any, default: str = "", *, max_length: int | None = None) -> str:
    normalized = default if value is None else str(value).strip()
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


def _default_runtime_settings() -> dict[str, Any]:
    return {
        "concurrent_session_limit_enabled": True,
        "max_concurrent_sessions_per_account": 3,
        "session_online_window_minutes": 30,
        "session_absolute_ttl_days": 30,
        "admin_exempt_from_session_limit": False,
        "auto_disable_expired_accounts": False,
        "default_account_validity_mode": "permanent",
        "default_account_validity_unit": "month",
        "default_account_validity_value": 1,
    }


def _normalize_runtime_settings(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    defaults = _default_runtime_settings()
    validity_mode = _coerce_text(payload.get("default_account_validity_mode"), defaults["default_account_validity_mode"])
    validity_unit = _coerce_text(payload.get("default_account_validity_unit"), defaults["default_account_validity_unit"])
    if validity_mode not in {"permanent", "duration"}:
        validity_mode = defaults["default_account_validity_mode"]
    if validity_unit not in VALIDITY_UNITS:
        validity_unit = defaults["default_account_validity_unit"]
    return {
        "concurrent_session_limit_enabled": _coerce_bool(
            payload.get("concurrent_session_limit_enabled"),
            defaults["concurrent_session_limit_enabled"],
        ),
        "max_concurrent_sessions_per_account": _coerce_int(
            payload.get("max_concurrent_sessions_per_account"),
            defaults["max_concurrent_sessions_per_account"],
            minimum=1,
            maximum=32,
        ),
        "session_online_window_minutes": _coerce_int(
            payload.get("session_online_window_minutes"),
            defaults["session_online_window_minutes"],
            minimum=1,
            maximum=1440,
        ),
        "session_absolute_ttl_days": _coerce_int(
            payload.get("session_absolute_ttl_days"),
            defaults["session_absolute_ttl_days"],
            minimum=1,
            maximum=3650,
        ),
        "admin_exempt_from_session_limit": _coerce_bool(
            payload.get("admin_exempt_from_session_limit"),
            defaults["admin_exempt_from_session_limit"],
        ),
        "auto_disable_expired_accounts": _coerce_bool(
            payload.get("auto_disable_expired_accounts"),
            defaults["auto_disable_expired_accounts"],
        ),
        "default_account_validity_mode": validity_mode,
        "default_account_validity_unit": validity_unit,
        "default_account_validity_value": _coerce_int(
            payload.get("default_account_validity_value"),
            defaults["default_account_validity_value"],
            minimum=1,
            maximum=3650,
        ),
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


def _read_runtime_settings(session: Session) -> tuple[SystemSettings, dict[str, Any]]:
    ensure_runtime_configuration_seeded(session=session)
    record = _ensure_system_settings_record(session)
    extra_json = record.extra_json if isinstance(record.extra_json, dict) else {}
    return record, _normalize_runtime_settings(extra_json.get(ACCOUNT_RUNTIME_EXTRA_KEY))


def _write_runtime_settings(
    session: Session,
    record: SystemSettings,
    settings_value: dict[str, Any],
    *,
    updated_by: str | None,
) -> dict[str, Any]:
    extra_json = dict(record.extra_json) if isinstance(record.extra_json, dict) else {}
    extra_json[ACCOUNT_RUNTIME_EXTRA_KEY] = settings_value
    record.extra_json = extra_json
    record.updated_by = updated_by
    session.add(record)
    session.commit()
    session.refresh(record)
    return _normalize_runtime_settings((record.extra_json or {}).get(ACCOUNT_RUNTIME_EXTRA_KEY))


def get_user_runtime_settings(*, session: Session | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    if session is not None:
        _, settings_value = _read_runtime_settings(session)
        return settings_value

    with Session(engine) as owned_session:
        _, settings_value = _read_runtime_settings(owned_session)
        return settings_value


def apply_user_runtime_settings(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    payload = values if isinstance(values, dict) else {}
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        record, current_settings = _read_runtime_settings(session)
        merged = dict(current_settings)
        for key in _default_runtime_settings():
            if key in payload:
                merged[key] = payload[key]
        normalized = _normalize_runtime_settings(merged)
        return _write_runtime_settings(session, record, normalized, updated_by=updated_by)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    last_day_map = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, last_day_map[month - 1])
    return value.replace(year=year, month=month, day=day)


def resolve_expiration(
    *,
    validity_mode: str | None = None,
    validity_unit: str | None = None,
    validity_value: int | None = None,
    fixed_expires_at: datetime | None = None,
    runtime_settings: dict[str, Any] | None = None,
    base_time: datetime | None = None,
) -> datetime | None:
    current_time = base_time or _utcnow()
    settings_value = runtime_settings or get_user_runtime_settings()
    mode = (validity_mode or settings_value["default_account_validity_mode"]).strip().lower()
    unit = (validity_unit or settings_value["default_account_validity_unit"]).strip().lower()
    value = validity_value if validity_value is not None else int(settings_value["default_account_validity_value"])

    if mode == "permanent":
        return None
    if mode == "fixed_at":
        resolved = _coerce_datetime(fixed_expires_at)
        if resolved is None:
            raise ValueError("fixed_expires_at is required when validity_mode is fixed_at")
        return resolved
    if mode != "duration":
        raise ValueError("validity_mode must be permanent, duration or fixed_at")
    if unit not in VALIDITY_UNITS:
        raise ValueError("validity_unit must be day, month or year")

    amount = max(1, int(value))
    if unit == "day":
        return current_time + timedelta(days=amount)
    if unit == "month":
        return _add_months(current_time, amount)
    return _add_months(current_time, amount * 12)


def get_effective_status(account: UserAccount, *, now: datetime | None = None) -> str:
    current_time = now or _utcnow()
    if account.status != "active":
        return account.status
    if account.expires_at is not None and account.expires_at <= current_time:
        return "expired"
    return "active"


def get_remaining_days(expires_at: datetime | None, *, now: datetime | None = None) -> int | None:
    if expires_at is None:
        return None
    current_time = now or _utcnow()
    delta = expires_at - current_time
    total_seconds = delta.total_seconds()
    if total_seconds <= 0:
        return 0
    return int((total_seconds + 86399) // 86400)


def resolve_account_session_limit(
    account: UserAccount,
    runtime_settings: dict[str, Any] | None = None,
) -> int | None:
    settings_value = runtime_settings or get_user_runtime_settings()
    if account.session_limit_override is not None:
        return max(1, int(account.session_limit_override))
    if account.role == "admin" and settings_value["admin_exempt_from_session_limit"]:
        return None
    if not settings_value["concurrent_session_limit_enabled"]:
        return None
    return int(settings_value["max_concurrent_sessions_per_account"])


def _get_local_identity_map(session: Session, account_ids: list[int]) -> dict[int, AuthIdentity]:
    if not account_ids:
        return {}
    identities = (
        session.query(AuthIdentity)
        .filter(
            AuthIdentity.account_id.in_(account_ids),
            AuthIdentity.provider == LOCAL_AUTH_PROVIDER,
        )
        .all()
    )
    return {identity.account_id: identity for identity in identities}


def get_active_session_count_map(
    session: Session,
    account_ids: list[int],
    *,
    runtime_settings: dict[str, Any] | None = None,
) -> dict[int, int]:
    if not account_ids:
        return {}
    settings_value = runtime_settings or get_user_runtime_settings()
    current_time = _utcnow()
    online_after = current_time - timedelta(minutes=int(settings_value["session_online_window_minutes"]))
    rows = (
        session.query(AuthSession.account_id, func.count(AuthSession.id))
        .filter(
            AuthSession.account_id.in_(account_ids),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > current_time,
            AuthSession.last_seen_at >= online_after,
        )
        .group_by(AuthSession.account_id)
        .all()
    )
    return {int(account_id): int(count) for account_id, count in rows}


def serialize_account(
    account: UserAccount,
    *,
    runtime_settings: dict[str, Any] | None = None,
    active_session_count: int = 0,
    local_identity: AuthIdentity | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _utcnow()
    effective_status = get_effective_status(account, now=current_time)
    return {
        "id": account.id,
        "username": account.username,
        "name": account.display_name or account.username,
        "display_name": account.display_name or account.username,
        "email": account.email or "",
        "role": account.role,
        "status": account.status,
        "effective_status": effective_status,
        "account_source": account.account_source,
        "expires_at": account.expires_at,
        "remaining_days": get_remaining_days(account.expires_at, now=current_time),
        "session_limit": resolve_account_session_limit(account, runtime_settings),
        "session_limit_override": account.session_limit_override,
        "active_session_count": int(active_session_count),
        "must_change_password": bool(account.must_change_password),
        "last_login_at": account.last_login_at,
        "last_seen_at": account.last_seen_at,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
        "source_batch_id": account.source_batch_id,
        "status_reason": account.status_reason,
        "identity_status": local_identity.identity_status if local_identity is not None else None,
    }


def _load_legacy_users() -> dict[str, Any]:
    if not USER_DATA_FILE.exists():
        return {}
    try:
        with USER_DATA_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load legacy users.json: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _generate_provider_user_id(account_id: int) -> str:
    return f"local-account-{account_id}"


def _build_local_identity(
    *,
    account_id: int,
    login_name: str,
    password_hash: str,
) -> AuthIdentity:
    return AuthIdentity(
        account_id=account_id,
        provider=LOCAL_AUTH_PROVIDER,
        provider_user_id=_generate_provider_user_id(account_id),
        login_name=login_name,
        password_hash=password_hash,
        identity_status="active",
    )


def _create_account_record(
    session: Session,
    *,
    username: str,
    password: str | None = None,
    password_hash: str | None = None,
    name: str = "",
    email: str = "",
    role: str = "user",
    status: str = "active",
    account_source: str = "local",
    expires_at: datetime | None = None,
    must_change_password: bool = False,
    session_limit_override: int | None = None,
    source_batch_id: int | None = None,
    created_by: str | None = None,
) -> UserAccount:
    normalized_username = _coerce_text(username)
    if not normalized_username:
        raise ValueError("username cannot be empty")
    if any(ch.isspace() for ch in normalized_username):
        raise ValueError("username cannot contain spaces")
    if role not in USER_ROLES:
        raise ValueError("role is invalid")
    if status not in ACCOUNT_STATUSES:
        raise ValueError("status is invalid")
    if session.query(UserAccount).filter(UserAccount.username == normalized_username).first() is not None:
        raise ValueError(f"user {normalized_username} already exists")

    resolved_hash = password_hash or (hash_password(password or ""))
    if not resolved_hash:
        raise ValueError("password is required")

    account = UserAccount(
        username=normalized_username,
        display_name=_coerce_text(name, normalized_username, max_length=128),
        email=_coerce_text(email, "", max_length=255),
        role=role,
        status=status,
        account_source=_coerce_text(account_source, "local", max_length=32),
        source_batch_id=source_batch_id,
        expires_at=expires_at,
        must_change_password=must_change_password,
        session_limit_override=session_limit_override,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(account)
    session.flush()

    identity = _build_local_identity(
        account_id=account.id,
        login_name=normalized_username,
        password_hash=resolved_hash,
    )
    session.add(identity)
    session.flush()
    return account


def _create_default_admin(session: Session) -> UserAccount:
    return _create_account_record(
        session,
        username=DEFAULT_ADMIN_USERNAME,
        password=DEFAULT_ADMIN_PASSWORD,
        name="系统管理员",
        email="admin@example.com",
        role="admin",
        must_change_password=True,
        created_by="bootstrap",
    )


def bootstrap_account_storage() -> None:
    ensure_runtime_configuration_seeded()
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        if session.query(UserAccount.id).first() is not None:
            return

        legacy_users = _load_legacy_users()
        if legacy_users:
            migrated_count = 0
            for username, payload in legacy_users.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    _create_account_record(
                        session,
                        username=username,
                        password_hash=_coerce_text(payload.get("password")),
                        name=_coerce_text(payload.get("name"), username, max_length=128),
                        email=_coerce_text(payload.get("email"), "", max_length=255),
                        role=_coerce_text(payload.get("role"), "user", max_length=32).lower() or "user",
                        created_by="legacy_migration",
                    )
                    migrated_count += 1
                except Exception as exc:
                    logger.warning("Failed to migrate legacy user %s: %s", username, exc)

            if migrated_count:
                session.commit()
                logger.info("Migrated %s users from users.json into database accounts", migrated_count)
                return
            session.rollback()

        _create_default_admin(session)
        session.commit()
        logger.warning(
            "No database accounts found. Bootstrapped default admin account %s / %s",
            DEFAULT_ADMIN_USERNAME,
            DEFAULT_ADMIN_PASSWORD,
        )


def _has_other_effective_local_admin(
    session: Session,
    *,
    exclude_account_id: int | None = None,
    now: datetime | None = None,
) -> bool:
    current_time = now or _utcnow()
    rows = (
        session.query(UserAccount, AuthIdentity)
        .join(
            AuthIdentity,
            (AuthIdentity.account_id == UserAccount.id) & (AuthIdentity.provider == LOCAL_AUTH_PROVIDER),
        )
        .filter(AuthIdentity.identity_status == "active")
        .all()
    )
    for account, _identity in rows:
        if exclude_account_id is not None and account.id == exclude_account_id:
            continue
        if account.role != "admin":
            continue
        if get_effective_status(account, now=current_time) != "active":
            continue
        return True
    return False


def _ensure_admin_not_removed(
    session: Session,
    account: UserAccount,
    *,
    next_role: str | None = None,
    next_status: str | None = None,
    next_expires_at: datetime | None | object = _UNSET,
    deleting: bool = False,
) -> None:
    current_time = _utcnow()
    currently_effective = (
        account.role == "admin" and get_effective_status(account, now=current_time) == "active"
    )
    if not currently_effective:
        return

    will_remain_effective = not deleting
    if will_remain_effective and next_role is not None and next_role != "admin":
        will_remain_effective = False
    if will_remain_effective and next_status is not None and next_status != "active":
        will_remain_effective = False
    if will_remain_effective and next_expires_at is not _UNSET:
        if next_expires_at is not None and next_expires_at <= current_time:
            will_remain_effective = False

    if will_remain_effective:
        return
    if _has_other_effective_local_admin(session, exclude_account_id=account.id, now=current_time):
        return
    raise ValueError("至少需要保留一个可登录的管理员账号")


def _find_account(session: Session, username: str) -> UserAccount | None:
    return session.query(UserAccount).filter(UserAccount.username == username).first()


def _find_local_identity(session: Session, account_id: int) -> AuthIdentity | None:
    return (
        session.query(AuthIdentity)
        .filter(
            AuthIdentity.account_id == account_id,
            AuthIdentity.provider == LOCAL_AUTH_PROVIDER,
        )
        .first()
    )


def _revoke_account_sessions(
    session: Session,
    account_id: int,
    *,
    reason: str,
    except_session_id: str | None = None,
) -> int:
    current_time = _utcnow()
    query = session.query(AuthSession).filter(
        AuthSession.account_id == account_id,
        AuthSession.revoked_at.is_(None),
    )
    if except_session_id:
        query = query.filter(AuthSession.session_id != except_session_id)
    sessions = query.all()
    for item in sessions:
        item.revoked_at = current_time
        item.revoke_reason = reason
        session.add(item)
    return len(sessions)


def get_user_record(username: str) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account = _find_account(session, username)
        if account is None:
            return None
        runtime_settings = get_user_runtime_settings()
        local_identity = _find_local_identity(session, account.id)
        session_counts = get_active_session_count_map(session, [account.id], runtime_settings=runtime_settings)
        return serialize_account(
            account,
            runtime_settings=runtime_settings,
            active_session_count=session_counts.get(account.id, 0),
            local_identity=local_identity,
        )


def create_user_account(
    *,
    username: str,
    password: str,
    name: str = "",
    email: str = "",
    role: str = "user",
    status: str = "active",
    validity_mode: str | None = None,
    validity_unit: str | None = None,
    validity_value: int | None = None,
    fixed_expires_at: datetime | None = None,
    session_limit_override: int | None = None,
    account_source: str = "local",
    source_batch_id: int | None = None,
    must_change_password: bool = False,
    created_by: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        runtime_settings = get_user_runtime_settings()
        expires_at = resolve_expiration(
            validity_mode=validity_mode,
            validity_unit=validity_unit,
            validity_value=validity_value,
            fixed_expires_at=fixed_expires_at,
            runtime_settings=runtime_settings,
        )
        account = _create_account_record(
            session,
            username=username,
            password=password,
            name=name,
            email=email,
            role=role,
            status=status,
            account_source=account_source,
            expires_at=expires_at,
            must_change_password=must_change_password,
            session_limit_override=session_limit_override,
            source_batch_id=source_batch_id,
            created_by=created_by,
        )
        session.commit()
        local_identity = _find_local_identity(session, account.id)
        return serialize_account(account, runtime_settings=runtime_settings, local_identity=local_identity)


def update_user_account(
    username: str,
    *,
    name: str | None = None,
    email: str | None = None,
    role: str | None = None,
    status: str | None = None,
    validity_mode: str | None | object = _UNSET,
    validity_unit: str | None = None,
    validity_value: int | None = None,
    fixed_expires_at: datetime | None | object = _UNSET,
    session_limit_override: int | None | object = _UNSET,
    updated_by: str | None = None,
) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account = _find_account(session, username)
        if account is None:
            return None
        runtime_settings = get_user_runtime_settings()

        next_expires_at: datetime | None | object = _UNSET
        if validity_mode is not _UNSET:
            if validity_mode is None:
                next_expires_at = None
            else:
                next_expires_at = resolve_expiration(
                    validity_mode=str(validity_mode),
                    validity_unit=validity_unit,
                    validity_value=validity_value,
                    fixed_expires_at=_coerce_datetime(None if fixed_expires_at is _UNSET else fixed_expires_at),
                    runtime_settings=runtime_settings,
                )
        elif fixed_expires_at is not _UNSET:
            next_expires_at = _coerce_datetime(fixed_expires_at)

        _ensure_admin_not_removed(
            session,
            account,
            next_role=role,
            next_status=status,
            next_expires_at=next_expires_at,
        )

        if name is not None:
            account.display_name = _coerce_text(name, account.username, max_length=128)
        if email is not None:
            account.email = _coerce_text(email, "", max_length=255)
        if role is not None:
            if role not in USER_ROLES:
                raise ValueError("role is invalid")
            account.role = role
        if status is not None:
            if status not in ACCOUNT_STATUSES:
                raise ValueError("status is invalid")
            account.status = status
        if next_expires_at is not _UNSET:
            account.expires_at = next_expires_at
        if session_limit_override is not _UNSET:
            account.session_limit_override = None if session_limit_override is None else max(1, int(session_limit_override))
        account.updated_by = updated_by
        session.add(account)

        if get_effective_status(account) != "active":
            _revoke_account_sessions(session, account.id, reason="account_restricted")

        session.commit()
        local_identity = _find_local_identity(session, account.id)
        session_counts = get_active_session_count_map(session, [account.id], runtime_settings=runtime_settings)
        return serialize_account(
            account,
            runtime_settings=runtime_settings,
            active_session_count=session_counts.get(account.id, 0),
            local_identity=local_identity,
        )


def change_password_for_account(username: str, new_password: str, *, updated_by: str | None = None) -> bool:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account = _find_account(session, username)
        if account is None:
            return False
        identity = _find_local_identity(session, account.id)
        if identity is None:
            return False
        identity.password_hash = hash_password(new_password)
        identity.identity_status = "active"
        identity.last_login_at = account.last_login_at
        account.must_change_password = False
        account.updated_by = updated_by
        session.add(identity)
        session.add(account)
        _revoke_account_sessions(session, account.id, reason="password_changed")
        session.commit()
        return True


def change_username_for_account(old_username: str, new_username: str, *, updated_by: str | None = None) -> bool:
    normalized_new_username = _coerce_text(new_username)
    if not normalized_new_username or any(ch.isspace() for ch in normalized_new_username):
        raise ValueError("new username is invalid")
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account = _find_account(session, old_username)
        if account is None:
            return False
        if _find_account(session, normalized_new_username) is not None:
            raise ValueError(f"user {normalized_new_username} already exists")
        account.username = normalized_new_username
        account.updated_by = updated_by
        identity = _find_local_identity(session, account.id)
        if identity is not None:
            identity.login_name = normalized_new_username
            session.add(identity)
        session.add(account)
        session.commit()
        return True


def delete_user_account(username: str) -> bool:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account = _find_account(session, username)
        if account is None:
            return False
        _ensure_admin_not_removed(session, account, deleting=True)
        session.query(AuthSession).filter(AuthSession.account_id == account.id).delete()
        session.query(AuthIdentity).filter(AuthIdentity.account_id == account.id).delete()
        session.delete(account)
        session.commit()
        return True


def list_user_accounts(
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    role: str | None = None,
    effective_status: str | None = None,
    account_source: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        runtime_settings = get_user_runtime_settings()
        accounts = session.query(UserAccount).all()
        account_ids = [account.id for account in accounts]
        local_identity_map = _get_local_identity_map(session, account_ids)
        session_counts = get_active_session_count_map(session, account_ids, runtime_settings=runtime_settings)
        rows = [
            serialize_account(
                account,
                runtime_settings=runtime_settings,
                active_session_count=session_counts.get(account.id, 0),
                local_identity=local_identity_map.get(account.id),
            )
            for account in accounts
        ]

    normalized_keyword = keyword.strip().lower()
    if normalized_keyword:
        rows = [
            row for row in rows
            if normalized_keyword in row["username"].lower()
            or normalized_keyword in row["name"].lower()
            or normalized_keyword in row["email"].lower()
        ]
    if role:
        rows = [row for row in rows if row["role"] == role]
    if effective_status:
        rows = [row for row in rows if row["effective_status"] == effective_status]
    if account_source:
        rows = [row for row in rows if row["account_source"] == account_source]

    order_field = sort_by if sort_by in SORTABLE_USER_FIELDS else "created_at"
    reverse = str(sort_order).lower() != "asc"

    def sort_key(row: dict[str, Any]) -> tuple[int, Any]:
        value = row.get(order_field)
        if value is None:
            return (1, "")
        if isinstance(value, str):
            return (0, value.lower())
        return (0, value)

    rows.sort(key=sort_key, reverse=reverse)

    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": rows[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "runtime_settings": runtime_settings,
    }


def list_users_basic() -> list[dict[str, Any]]:
    result = list_user_accounts(page=1, page_size=5000)
    return [
        {
            "username": item["username"],
            "name": item["name"],
            "email": item["email"],
            "role": item["role"],
        }
        for item in result["items"]
    ]


def export_user_accounts() -> list[dict[str, Any]]:
    return list_user_accounts(page=1, page_size=5000)["items"]


def get_available_roles() -> dict[str, str]:
    return USER_ROLES.copy()


def _generate_random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(6, min(length, 64))))


def bulk_create_random_accounts(
    *,
    count: int,
    prefix: str = "user",
    start_index: int = 1,
    role: str = "user",
    password_length: int = 12,
    validity_mode: str | None = None,
    validity_unit: str | None = None,
    validity_value: int | None = None,
    fixed_expires_at: datetime | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    count = max(1, min(count, 500))
    start_index = max(1, start_index)
    successes: list[dict[str, str]] = []
    failures: list[dict[str, Any]] = []
    batch_code = f"batch-{_utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"

    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        runtime_settings = get_user_runtime_settings()
        batch = AccountBatch(
            batch_name=f"批量创建 {batch_code}",
            batch_code=batch_code,
            source_type="admin_bulk",
            provider_scope=LOCAL_AUTH_PROVIDER,
            default_role=role,
            validity_mode=validity_mode or runtime_settings["default_account_validity_mode"],
            validity_unit=validity_unit or runtime_settings["default_account_validity_unit"],
            validity_value=validity_value if validity_value is not None else runtime_settings["default_account_validity_value"],
            fixed_expires_at=fixed_expires_at,
            created_by=created_by,
        )
        session.add(batch)
        session.flush()

        for offset in range(count):
            seed = start_index + offset
            base_username = f"{prefix}{seed}"
            username = base_username
            for _ in range(8):
                if _find_account(session, username) is None:
                    break
                username = f"{base_username}{secrets.choice(string.ascii_lowercase)}{secrets.choice(string.digits)}"
            if _find_account(session, username) is not None:
                failures.append({"username": base_username, "reason": "无法生成可用用户名"})
                continue
            password = _generate_random_password(password_length)
            try:
                expires_at = resolve_expiration(
                    validity_mode=validity_mode,
                    validity_unit=validity_unit,
                    validity_value=validity_value,
                    fixed_expires_at=fixed_expires_at,
                    runtime_settings=runtime_settings,
                )
                _create_account_record(
                    session,
                    username=username,
                    password=password,
                    name=username,
                    role=role,
                    account_source="admin_bulk",
                    expires_at=expires_at,
                    source_batch_id=batch.id,
                    created_by=created_by,
                )
                successes.append({"username": username, "password": password, "role": role})
            except Exception as exc:
                failures.append({"username": username, "reason": str(exc)})

        session.commit()
    return {"successes": successes, "failures": failures}


def bulk_delete_accounts(usernames: list[str]) -> dict[str, Any]:
    successes: list[str] = []
    failures: list[dict[str, str]] = []
    for username in usernames:
        try:
            removed = delete_user_account(username)
            if removed:
                successes.append(username)
            else:
                failures.append({"username": username, "reason": "用户不存在"})
        except Exception as exc:
            failures.append({"username": username, "reason": str(exc)})
    return {"successes": successes, "failures": failures}


def bulk_reset_passwords_for_accounts(usernames: list[str], password_length: int = 12) -> dict[str, Any]:
    successes: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for username in usernames:
        password = _generate_random_password(password_length)
        try:
            changed = change_password_for_account(username, password)
            if changed:
                successes.append({"username": username, "password": password})
            else:
                failures.append({"username": username, "reason": "用户不存在"})
        except Exception as exc:
            failures.append({"username": username, "reason": str(exc)})
    return {"successes": successes, "failures": failures}


def get_account_by_login_name(login_name: str) -> tuple[UserAccount | None, AuthIdentity | None]:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        identity = (
            session.query(AuthIdentity)
            .filter(
                AuthIdentity.provider == LOCAL_AUTH_PROVIDER,
                AuthIdentity.login_name == login_name,
            )
            .first()
        )
        if identity is None:
            return None, None
        account = session.get(UserAccount, identity.account_id)
        return account, identity


def _load_account_for_session(
    session: Session,
    account_id: int,
    *,
    runtime_settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    account = session.get(UserAccount, account_id)
    if account is None:
        return None

    resolved_runtime_settings = runtime_settings or get_user_runtime_settings(session=session)
    local_identity = _find_local_identity(session, account.id)
    session_counts = get_active_session_count_map(session, [account.id], runtime_settings=resolved_runtime_settings)
    return serialize_account(
        account,
        runtime_settings=resolved_runtime_settings,
        active_session_count=session_counts.get(account.id, 0),
        local_identity=local_identity,
    )


def load_account_for_session(
    account_id: int,
    *,
    session: Session | None = None,
    runtime_settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    if session is not None:
        return _load_account_for_session(
            session,
            account_id,
            runtime_settings=runtime_settings,
        )

    with Session(engine) as owned_session:
        return _load_account_for_session(
            owned_session,
            account_id,
            runtime_settings=runtime_settings,
        )
