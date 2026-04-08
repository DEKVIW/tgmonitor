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
 
 
class LinuxDoPublicAuthConfig(BaseModel):
     visible: bool
     mode: str
     status_summary: str
     batch_name: Optional[str] = None
     remaining_accounts: Optional[int] = None
 
 
class PublicAuthProvidersResponse(BaseModel):
     linuxdo: LinuxDoPublicAuthConfig
 
 
class LinuxDoLoginStartRequest(BaseModel):
     redirect_uri: str
     turnstile_token: Optional[str] = None
 
 
class LinuxDoLoginStartResponse(BaseModel):
     authorize_url: str
 
 
class LinuxDoLoginExchangeRequest(BaseModel):
     code: str
     state: str
     redirect_uri: str
 
 
class TokenData(BaseModel):
    """Token数据"""
    username: Optional[str] = None


# 更新前向引用
LoginResponse.model_rebuild()

