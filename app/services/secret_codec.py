from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.models.config import settings


SECRET_VERSION_PREFIX = "v1:"


def _build_fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_SALT.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    token = _build_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")
    return f"{SECRET_VERSION_PREFIX}{token}"


def decrypt_secret(value: str, *, error_message: str = "Unable to decrypt secret; please verify SECRET_SALT") -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if not normalized.startswith(SECRET_VERSION_PREFIX):
        return normalized
    try:
        return _build_fernet().decrypt(normalized[len(SECRET_VERSION_PREFIX) :].encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(error_message) from exc
