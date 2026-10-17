from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import Argon2Error


_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password cannot be empty")
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not isinstance(plain_password, str) or not plain_password:
        return False
    if not isinstance(hashed_password, str) or not hashed_password.startswith("$argon2id$"):
        return False
    try:
        return bool(_password_hasher.verify(hashed_password, plain_password))
    except (Argon2Error, TypeError, ValueError):
        return False


def is_argon2id_hash(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith("$argon2id$")
