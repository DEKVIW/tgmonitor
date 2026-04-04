"""
User management service backed by users.json.
"""

import json
import logging
import os
import secrets
import string
import threading
from typing import Any, Dict, List, Optional

from passlib.context import CryptContext

logger = logging.getLogger(__name__)

USER_DATA_FILE = "users.json"

USER_ROLES = {
    "admin": "系统管理员",
    "user": "普通用户",
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_file_lock = threading.RLock()


def _load_users_unlocked() -> Dict[str, Any]:
    if not os.path.exists(USER_DATA_FILE):
        return {}

    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception as e:
        logger.error(f"读取用户文件失败: {e}")
        return {}

    return users if isinstance(users, dict) else {}


def _save_users_unlocked(users: Dict[str, Any]) -> bool:
    temp_file = f"{USER_DATA_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, USER_DATA_FILE)
        return True
    except Exception as e:
        logger.error(f"保存用户数据失败: {e}")
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        return False


def _count_admin_users(users: Dict[str, Any]) -> int:
    return sum(1 for user in users.values() if user.get("role", "user") == "admin")


def _is_last_admin(users: Dict[str, Any], username: str) -> bool:
    user = users.get(username)
    if not user:
        return False
    if user.get("role", "user") != "admin":
        return False
    return _count_admin_users(users) <= 1


def load_existing_users() -> Dict[str, Any]:
    with _file_lock:
        return _load_users_unlocked()


def save_users(users: Dict[str, Any]) -> bool:
    with _file_lock:
        return _save_users_unlocked(users)


def list_users() -> List[Dict[str, Any]]:
    users = load_existing_users()
    result = []
    for username, user_info in users.items():
        result.append(
            {
                "username": username,
                "name": user_info.get("name", username),
                "email": user_info.get("email", ""),
                "role": user_info.get("role", "user"),
            }
        )
    return result


def get_user(username: str) -> Optional[Dict[str, Any]]:
    users = load_existing_users()
    if username not in users:
        return None

    user_info = users[username]
    return {
        "username": username,
        "name": user_info.get("name", username),
        "email": user_info.get("email", ""),
        "role": user_info.get("role", "user"),
    }


def add_user(
    username: str,
    password: str,
    name: str = "",
    email: str = "",
    role: str = "user",
) -> bool:
    with _file_lock:
        users = _load_users_unlocked()

        if username in users:
            return False
        if role not in USER_ROLES:
            return False

        users[username] = {
            "password": pwd_context.hash(password),
            "name": name or username,
            "email": email,
            "role": role,
        }
        return _save_users_unlocked(users)


def update_user(
    username: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
) -> bool:
    with _file_lock:
        users = _load_users_unlocked()

        if username not in users:
            return False
        if role is not None and role not in USER_ROLES:
            return False
        if username == "admin" and role is not None and role != "admin":
            return False
        if role is not None and role != "admin" and _is_last_admin(users, username):
            return False

        if name is not None:
            users[username]["name"] = name
        if email is not None:
            users[username]["email"] = email
        if role is not None:
            users[username]["role"] = role

        return _save_users_unlocked(users)


def change_password(username: str, new_password: str) -> bool:
    with _file_lock:
        users = _load_users_unlocked()
        if username not in users:
            return False

        users[username]["password"] = pwd_context.hash(new_password)
        return _save_users_unlocked(users)


def change_username(old_username: str, new_username: str) -> bool:
    with _file_lock:
        users = _load_users_unlocked()

        if old_username not in users:
            return False
        if old_username == "admin":
            return False
        if new_username in users:
            return False

        users[new_username] = users.pop(old_username)
        return _save_users_unlocked(users)


def change_user_role(username: str, new_role: str) -> bool:
    with _file_lock:
        users = _load_users_unlocked()

        if username not in users:
            return False
        if new_role not in USER_ROLES:
            return False
        if username == "admin" and new_role != "admin":
            return False
        if new_role != "admin" and _is_last_admin(users, username):
            return False

        users[username]["role"] = new_role
        return _save_users_unlocked(users)


def remove_user(username: str) -> bool:
    with _file_lock:
        users = _load_users_unlocked()

        if username not in users:
            return False
        if username == "admin":
            return False
        if _is_last_admin(users, username):
            return False

        del users[username]
        return _save_users_unlocked(users)


def get_available_roles() -> Dict[str, str]:
    return USER_ROLES.copy()


def _generate_random_password(length: int = 12) -> str:
    length = max(6, min(length, 32))
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def bulk_create_random_users(
    count: int,
    prefix: str = "user",
    start_index: int = 1,
    role: str = "user",
    password_length: int = 12,
) -> Dict[str, Any]:
    if role not in USER_ROLES:
        return {"successes": [], "failures": [{"username": None, "reason": "角色无效"}]}

    count = max(1, min(count, 500))
    start_index = max(1, start_index)

    with _file_lock:
        users = _load_users_unlocked()
        successes: List[Dict[str, str]] = []
        failures: List[Dict[str, Any]] = []

        for i in range(count):
            seq = start_index + i
            base_username = f"{prefix}{seq}"

            attempts = 0
            username = ""
            while attempts < 5:
                suffix = secrets.choice(string.ascii_lowercase) + secrets.choice(string.digits)
                candidate = f"{base_username}{suffix}"
                if candidate not in users:
                    username = candidate
                    break
                attempts += 1

            if not username:
                failures.append({"username": base_username, "reason": "多次尝试后仍然冲突"})
                continue

            password = _generate_random_password(password_length)
            users[username] = {
                "password": pwd_context.hash(password),
                "name": username,
                "email": "",
                "role": role,
            }
            successes.append({"username": username, "password": password, "role": role})

        if not _save_users_unlocked(users):
            return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

        return {"successes": successes, "failures": failures}


def bulk_remove_users(usernames: List[str]) -> Dict[str, Any]:
    with _file_lock:
        users = _load_users_unlocked()
        successes: List[str] = []
        failures: List[Dict[str, str]] = []
        remaining_admins = _count_admin_users(users)

        for username in usernames:
            if username == "admin":
                failures.append({"username": username, "reason": "不能删除管理员"})
                continue
            if username not in users:
                failures.append({"username": username, "reason": "用户不存在"})
                continue

            if users[username].get("role", "user") == "admin":
                if remaining_admins <= 1:
                    failures.append({"username": username, "reason": "至少需要保留一个管理员"})
                    continue
                remaining_admins -= 1

            del users[username]
            successes.append(username)

        if not _save_users_unlocked(users):
            return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

        return {"successes": successes, "failures": failures}


def bulk_reset_passwords(usernames: List[str], password_length: int = 12) -> Dict[str, Any]:
    with _file_lock:
        users = _load_users_unlocked()
        successes: List[Dict[str, str]] = []
        failures: List[Dict[str, str]] = []

        for username in usernames:
            if username == "admin":
                failures.append({"username": username, "reason": "不能重置管理员密码"})
                continue
            if username not in users:
                failures.append({"username": username, "reason": "用户不存在"})
                continue

            password = _generate_random_password(password_length)
            users[username]["password"] = pwd_context.hash(password)
            successes.append({"username": username, "password": password})

        if not _save_users_unlocked(users):
            return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

        return {"successes": successes, "failures": failures}


def export_users() -> List[Dict[str, Any]]:
    return list_users()
