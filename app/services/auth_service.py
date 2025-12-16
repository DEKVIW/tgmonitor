"""
认证服务
兼容现有的 users.json 文件和 streamlit-authenticator 的 bcrypt 密码哈希
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.models.config import settings
import logging

logger = logging.getLogger(__name__)

# 密码加密上下文，兼容 streamlit-authenticator 的 bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
SECRET_KEY = settings.SECRET_SALT
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30天，与 streamlit-authenticator 保持一致

# 用户数据文件路径
USER_DATA_FILE = "users.json"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码（兼容 streamlit-authenticator 的 bcrypt 格式）
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码
        
    Returns:
        验证是否通过
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


def load_users() -> Dict[str, Any]:
    """
    从 users.json 加载用户数据
    
    Returns:
        用户数据字典
    """
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
                return users
        else:
            logger.warning(f"用户数据文件 {USER_DATA_FILE} 不存在")
            return {}
    except Exception as e:
        logger.error(f"加载用户数据失败: {e}")
        return {}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    验证用户身份
    
    Args:
        username: 用户名
        password: 密码
        
    Returns:
        如果验证成功，返回用户信息字典；否则返回 None
    """
    users = load_users()
    
    if username not in users:
        logger.warning(f"用户 {username} 不存在")
        return None
    
    user_info = users[username]
    hashed_password = user_info.get("password")
    
    if not hashed_password:
        logger.error(f"用户 {username} 没有密码哈希")
        return None
    
    # 验证密码（兼容 streamlit-authenticator 的 bcrypt）
    if verify_password(password, hashed_password):
        return {
            "username": username,
            "name": user_info.get("name", username),
            "email": user_info.get("email", ""),
            "role": user_info.get("role", "user")
        }
    else:
        logger.warning(f"用户 {username} 密码验证失败")
        return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌
    
    Args:
        data: 要编码到 token 中的数据
        expires_delta: 过期时间增量，如果为 None 则使用默认值
        
    Returns:
        JWT token 字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证 JWT token
    
    Args:
        token: JWT token 字符串
        
    Returns:
        如果验证成功，返回解码后的数据；否则返回 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return {"username": username, "payload": payload}
    except JWTError as e:
        logger.error(f"Token 验证失败: {e}")
        return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    根据用户名获取用户信息（不验证密码）
    
    Args:
        username: 用户名
        
    Returns:
        用户信息字典，如果用户不存在则返回 None
    """
    users = load_users()
    
    if username not in users:
        return None
    
    user_info = users[username]
    return {
        "username": username,
        "name": user_info.get("name", username),
        "email": user_info.get("email", ""),
        "role": user_info.get("role", "user")
    }

