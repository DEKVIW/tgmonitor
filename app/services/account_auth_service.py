from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import AuthIdentity, AuthSession, UserAccount, engine, ensure_runtime_storage_tables
from app.services.account_service import (
    LOCAL_AUTH_PROVIDER,
    bootstrap_account_storage,
    get_effective_status,
    get_user_record,
    get_user_runtime_settings,
    load_account_for_session,
    resolve_account_session_limit,
    verify_password,
)

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_SALT
ALGORITHM = "HS256"


def _utcnow() -> datetime:
    return datetime.utcnow()


def generate_client_instance_id() -> str:
    return secrets.token_urlsafe(24)


def hash_client_instance_id(client_instance_id: str | None) -> str | None:
    normalized = (client_instance_id or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    payload["exp"] = _utcnow() + (expires_delta or timedelta(days=30))
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        logger.warning("Token verification failed: %s", exc)
        return None
    if not payload.get("sub"):
        return None
    return payload


def _find_identity_for_login(session: Session, username: str) -> tuple[UserAccount | None, AuthIdentity | None]:
    identity = (
        session.query(AuthIdentity)
        .filter(
            AuthIdentity.provider == LOCAL_AUTH_PROVIDER,
            AuthIdentity.login_name == username,
        )
        .first()
    )
    if identity is None:
        return None, None
    account = session.get(UserAccount, identity.account_id)
    return account, identity


def _find_identity_by_provider(session: Session, provider: str, provider_user_id: str) -> tuple[UserAccount | None, AuthIdentity | None]:
    identity = (
        session.query(AuthIdentity)
        .filter(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == provider_user_id,
        )
        .first()
    )
    if identity is None:
        return None, None
    account = session.get(UserAccount, identity.account_id)
    return account, identity


def _get_active_sessions_for_limit(
    session: Session,
    *,
    account_id: int,
    online_window_minutes: int,
) -> list[AuthSession]:
    current_time = _utcnow()
    online_after = current_time - timedelta(minutes=online_window_minutes)
    return (
        session.query(AuthSession)
        .filter(
            AuthSession.account_id == account_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > current_time,
            AuthSession.last_seen_at >= online_after,
        )
        .order_by(AuthSession.last_seen_at.asc(), AuthSession.created_at.asc())
        .all()
    )


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    with Session(engine) as session:
        account, identity = _find_identity_for_login(session, username)
        if account is None or identity is None:
            return None
        if identity.identity_status != "active":
            return None
        if get_effective_status(account) != "active":
            return None
        if not verify_password(password, identity.password_hash or ""):
            return None
    return get_user_record(username)


def create_login_session(
    *,
    username: str,
    password: str,
    client_instance_id: str | None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    runtime_settings = get_user_runtime_settings()
    current_time = _utcnow()

    with Session(engine) as session:
        account, identity = _find_identity_for_login(session, username)
        if account is None or identity is None:
            return None
        if identity.identity_status != "active":
            return None
        if get_effective_status(account, now=current_time) != "active":
            return None
        if not verify_password(password, identity.password_hash or ""):
            return None

        client_hash = hash_client_instance_id(client_instance_id)
        if client_hash:
            duplicate_sessions = (
                session.query(AuthSession)
                .filter(
                    AuthSession.account_id == account.id,
                    AuthSession.client_instance_hash == client_hash,
                    AuthSession.revoked_at.is_(None),
                )
                .all()
            )
            for existing in duplicate_sessions:
                existing.revoked_at = current_time
                existing.revoke_reason = "session_replaced"
                session.add(existing)

        active_limit = resolve_account_session_limit(account, runtime_settings)
        if active_limit is not None:
            active_sessions = _get_active_sessions_for_limit(
                session,
                account_id=account.id,
                online_window_minutes=int(runtime_settings["session_online_window_minutes"]),
            )
            while len(active_sessions) >= int(active_limit):
                oldest = active_sessions.pop(0)
                oldest.revoked_at = current_time
                oldest.revoke_reason = "session_limit_replaced"
                session.add(oldest)

        session_id = secrets.token_urlsafe(32)
        expires_delta = timedelta(days=int(runtime_settings["session_absolute_ttl_days"]))
        db_session = AuthSession(
            session_id=session_id,
            account_id=account.id,
            identity_id=identity.id,
            client_instance_hash=client_hash,
            login_provider=LOCAL_AUTH_PROVIDER,
            user_agent=(user_agent or "")[:4000] or None,
            ip_address=(ip_address or "")[:64] or None,
            created_at=current_time,
            last_seen_at=current_time,
            expires_at=current_time + expires_delta,
        )
        account.last_login_at = current_time
        account.last_seen_at = current_time
        identity.last_login_at = current_time
        session.add(db_session)
        session.add(account)
        session.add(identity)
        session.commit()

        user = load_account_for_session(account.id)
        if user is None:
            return None
        return {
            "access_token": create_access_token(
                {
                    "sub": account.username,
                    "sid": session_id,
                    "aid": account.id,
                    "role": account.role,
                },
                expires_delta=expires_delta,
            ),
            "token_type": "bearer",
            "user": user,
            "session_id": session_id,
        }


def create_provider_login_session(
    *,
    provider: str,
    provider_user_id: str,
    client_instance_id: str | None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    bootstrap_account_storage()
    runtime_settings = get_user_runtime_settings()
    current_time = _utcnow()

    with Session(engine) as session:
        account, identity = _find_identity_by_provider(session, provider, provider_user_id)
        if account is None or identity is None:
            return None
        if identity.identity_status != "active":
            return None
        if get_effective_status(account, now=current_time) != "active":
            return None

        client_hash = hash_client_instance_id(client_instance_id)
        if client_hash:
            duplicate_sessions = (
                session.query(AuthSession)
                .filter(
                    AuthSession.account_id == account.id,
                    AuthSession.client_instance_hash == client_hash,
                    AuthSession.revoked_at.is_(None),
                )
                .all()
            )
            for existing in duplicate_sessions:
                existing.revoked_at = current_time
                existing.revoke_reason = "session_replaced"
                session.add(existing)

        active_limit = resolve_account_session_limit(account, runtime_settings)
        if active_limit is not None:
            active_sessions = _get_active_sessions_for_limit(
                session,
                account_id=account.id,
                online_window_minutes=int(runtime_settings["session_online_window_minutes"]),
            )
            while len(active_sessions) >= int(active_limit):
                oldest = active_sessions.pop(0)
                oldest.revoked_at = current_time
                oldest.revoke_reason = "session_limit_replaced"
                session.add(oldest)

        session_id = secrets.token_urlsafe(32)
        expires_delta = timedelta(days=int(runtime_settings["session_absolute_ttl_days"]))
        db_session = AuthSession(
            session_id=session_id,
            account_id=account.id,
            identity_id=identity.id,
            client_instance_hash=client_hash,
            login_provider=provider,
            user_agent=(user_agent or "")[:4000] or None,
            ip_address=(ip_address or "")[:64] or None,
            created_at=current_time,
            last_seen_at=current_time,
            expires_at=current_time + expires_delta,
        )
        account.last_login_at = current_time
        account.last_seen_at = current_time
        identity.last_login_at = current_time
        session.add(db_session)
        session.add(account)
        session.add(identity)
        session.commit()

        user = load_account_for_session(account.id)
        if user is None:
            return None
        return {
            "access_token": create_access_token(
                {
                    "sub": account.username,
                    "sid": session_id,
                    "aid": account.id,
                    "role": account.role,
                },
                expires_delta=expires_delta,
            ),
            "token_type": "bearer",
            "user": user,
            "session_id": session_id,
        }


def resolve_current_user_from_token(token: str, *, touch: bool = True) -> dict[str, Any] | None:
    payload = verify_token(token)
    if payload is None:
        return None
    session_id = payload.get("sid")
    account_id = payload.get("aid")
    if not session_id or account_id is None:
        return None

    ensure_runtime_storage_tables()
    current_time = _utcnow()
    with Session(engine) as session:
        db_session = session.query(AuthSession).filter(AuthSession.session_id == session_id).first()
        if db_session is None or db_session.revoked_at is not None or db_session.expires_at <= current_time:
            return None
        account = session.get(UserAccount, int(account_id))
        if account is None or get_effective_status(account, now=current_time) != "active":
            db_session.revoked_at = current_time
            db_session.revoke_reason = "account_unavailable"
            session.add(db_session)
            session.commit()
            return None
        if touch and (current_time - db_session.last_seen_at) >= timedelta(seconds=45):
            db_session.last_seen_at = current_time
            account.last_seen_at = current_time
            session.add(db_session)
            session.add(account)
            session.commit()

    user = load_account_for_session(int(account_id))
    if user is None:
        return None
    user["session_id"] = session_id
    user["account_id"] = int(account_id)
    return user


def revoke_session(session_id: str, *, reason: str = "logout") -> bool:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        db_session = session.query(AuthSession).filter(AuthSession.session_id == session_id).first()
        if db_session is None or db_session.revoked_at is not None:
            return False
        db_session.revoked_at = _utcnow()
        db_session.revoke_reason = reason
        session.add(db_session)
        session.commit()
        return True


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return get_user_record(username)


def load_users() -> dict[str, Any]:
    result: dict[str, Any] = {}
    admin = get_user_record("admin")
    if admin is not None:
        result[admin["username"]] = admin
    return result
