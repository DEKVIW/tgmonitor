"""
FastAPI 依赖项
用于认证和数据库会话管理
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.models.models import engine
from app.services.auth_service import verify_token, get_user_by_username
from typing import Optional

# HTTP Bearer Token 安全方案
security = HTTPBearer()


def get_db():
    """
    获取数据库会话（依赖注入）
    
    Yields:
        Session: SQLAlchemy 数据库会话
    """
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    """
    获取当前认证用户（依赖注入）
    
    Args:
        credentials: HTTP Bearer Token 凭证
        db: 数据库会话
        
    Returns:
        当前用户信息字典
        
    Raises:
        HTTPException: 如果认证失败
    """
    token = credentials.credentials
    token_data = verify_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username = token_data.get("username")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证用户身份",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[dict]:
    """
    获取当前用户（可选，用于某些不需要强制认证的端点）
    
    Args:
        credentials: HTTP Bearer Token 凭证（可选）
        
    Returns:
        用户信息字典，如果未提供 token 则返回 None
    """
    if credentials is None:
        return None
    
    token = credentials.credentials
    token_data = verify_token(token)
    
    if token_data is None:
        return None
    
    username = token_data.get("username")
    if username is None:
        return None
    
    return get_user_by_username(username)


def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    获取当前管理员用户（依赖注入）
    
    必须在 get_current_user 基础上，额外检查用户角色是否为 admin
    
    Args:
        current_user: 当前用户信息（来自 get_current_user）
        
    Returns:
        管理员用户信息字典
        
    Raises:
        HTTPException: 如果用户不是管理员（403 Forbidden）
    """
    user_role = current_user.get("role", "").lower()
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user

