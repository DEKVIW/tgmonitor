"""
认证相关的 Pydantic Schema
"""

from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    """用户信息"""
    username: str
    name: str
    email: Optional[str] = None
    role: str = "user"


class ChangePasswordRequest(BaseModel):
    """修改密码请求（自助）"""
    old_password: str
    new_password: str


class TokenData(BaseModel):
    """Token数据"""
    username: Optional[str] = None


# 更新前向引用
LoginResponse.model_rebuild()

