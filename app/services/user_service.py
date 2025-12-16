"""
用户管理服务
复用 app/scripts/init_users.py 中的逻辑，但提供线程安全的文件操作
"""

import json
import os
import threading
from typing import Dict, Any, Optional, List
from passlib.context import CryptContext
import logging
import secrets
import string

logger = logging.getLogger(__name__)

# 用户数据文件路径
USER_DATA_FILE = "users.json"

# 用户角色定义
USER_ROLES = {
    "admin": "系统管理员",
    "user": "普通用户"
}

# 与后端 app.services.auth_service 使用的配置保持一致
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 文件锁，确保线程安全
_file_lock = threading.Lock()


def load_existing_users() -> Dict[str, Any]:
    """加载现有用户（线程安全）"""
    with _file_lock:
        if os.path.exists(USER_DATA_FILE):
            try:
                with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取用户文件失败: {e}")
                return {}
        return {}


def save_users(users: Dict[str, Any]) -> bool:
    """保存用户数据（线程安全）"""
    with _file_lock:
        try:
            with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")
            return False


def list_users() -> List[Dict[str, Any]]:
    """列出所有用户"""
    users = load_existing_users()
    result = []
    for username, user_info in users.items():
        result.append({
            "username": username,
            "name": user_info.get("name", username),
            "email": user_info.get("email", ""),
            "role": user_info.get("role", "user")
        })
    return result


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """获取单个用户信息"""
    users = load_existing_users()
    if username not in users:
        return None
    
    user_info = users[username]
    return {
        "username": username,
        "name": user_info.get("name", username),
        "email": user_info.get("email", ""),
        "role": user_info.get("role", "user")
    }


def add_user(
    username: str,
    password: str,
    name: str = "",
    email: str = "",
    role: str = "user"
) -> bool:
    """添加新用户"""
    users = load_existing_users()
    
    if username in users:
        return False
    
    # 验证角色
    if role not in USER_ROLES:
        return False
    
    # 生成密码哈希（与后端一致）
    hashed_password = pwd_context.hash(password)
    
    # 添加用户
    users[username] = {
        "password": hashed_password,
        "name": name or username,
        "email": email,
        "role": role
    }
    
    return save_users(users)


def update_user(
    username: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None
) -> bool:
    """更新用户信息"""
    users = load_existing_users()
    
    if username not in users:
        return False
    
    # 验证角色
    if role is not None and role not in USER_ROLES:
        return False
    
    # 更新信息
    if name is not None:
        users[username]["name"] = name
    if email is not None:
        users[username]["email"] = email
    if role is not None:
        users[username]["role"] = role
    
    return save_users(users)


def change_password(username: str, new_password: str) -> bool:
    """修改用户密码"""
    users = load_existing_users()
    
    if username not in users:
        return False
    
    # 生成新密码哈希（与后端一致）
    hashed_password = pwd_context.hash(new_password)
    
    # 更新密码
    users[username]["password"] = hashed_password
    
    return save_users(users)


def change_username(old_username: str, new_username: str) -> bool:
    """修改用户名"""
    users = load_existing_users()
    
    if old_username not in users:
        return False
    
    if new_username in users:
        return False
    
    # 移动用户数据
    users[new_username] = users.pop(old_username)
    
    return save_users(users)


def change_user_role(username: str, new_role: str) -> bool:
    """修改用户角色"""
    users = load_existing_users()
    
    if username not in users:
        return False
    
    if new_role not in USER_ROLES:
        return False
    
    # 更新角色
    users[username]["role"] = new_role
    
    return save_users(users)


def remove_user(username: str) -> bool:
    """删除用户"""
    users = load_existing_users()
    
    if username not in users:
        return False
    
    if username == "admin":
        return False  # 不能删除管理员用户
    
    del users[username]
    
    return save_users(users)


def get_available_roles() -> Dict[str, str]:
    """获取可用角色列表"""
    return USER_ROLES.copy()


# ========== 批量与随机工具 ==========

def _generate_random_password(length: int = 12) -> str:
    """生成随机密码，包含字母与数字"""
    length = max(6, min(length, 32))  # 合理限制
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def bulk_create_random_users(
    count: int,
    prefix: str = "user",
    start_index: int = 1,
    role: str = "user",
    password_length: int = 12
) -> Dict[str, Any]:
    """
    批量随机创建用户
    返回 successes[{username,password}] 和 failures[{username, reason}]
    """
    if role not in USER_ROLES:
        return {"successes": [], "failures": [{"username": None, "reason": "角色无效"}]}
    count = max(1, min(count, 500))
    start_index = max(1, start_index)

    users = load_existing_users()
    successes: List[Dict[str, str]] = []
    failures: List[Dict[str, Any]] = []

    for i in range(count):
        seq = start_index + i
        base_username = f"{prefix}{seq}"

        # 始终使用短随机后缀，避免过于单调，同时降低冲突概率
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
            failures.append({"username": base_username, "reason": "多次尝试仍存在冲突"})
            continue

        password = _generate_random_password(password_length)
        hashed_password = pwd_context.hash(password)
        users[username] = {
            "password": hashed_password,
            "name": username,
            "email": "",
            "role": role
        }
        successes.append({"username": username, "password": password, "role": role})

    saved = save_users(users)
    if not saved:
        return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

    return {"successes": successes, "failures": failures}


def bulk_remove_users(usernames: List[str]) -> Dict[str, Any]:
    """批量删除用户，保护 admin"""
    users = load_existing_users()
    successes: List[str] = []
    failures: List[Dict[str, str]] = []

    for username in usernames:
        if username == "admin":
            failures.append({"username": username, "reason": "不能删除管理员"})
            continue
        if username not in users:
            failures.append({"username": username, "reason": "用户不存在"})
            continue
        del users[username]
        successes.append(username)

    saved = save_users(users)
    if not saved:
        return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

    return {"successes": successes, "failures": failures}


def bulk_reset_passwords(usernames: List[str], password_length: int = 12) -> Dict[str, Any]:
    """批量重置密码，保护 admin"""
    users = load_existing_users()
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

    saved = save_users(users)
    if not saved:
        return {"successes": [], "failures": [{"username": None, "reason": "写入用户文件失败"}]}

    return {"successes": successes, "failures": failures}


def export_users() -> List[Dict[str, Any]]:
    """导出用户列表（不含密码）"""
    return list_users()

