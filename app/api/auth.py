"""
认证相关 API 路由
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo, ChangePasswordRequest
from app.services.auth_service import authenticate_user, create_access_token, verify_password, get_user_by_username, load_users
from app.services.user_service import change_password
from app.api.dependencies import get_current_user
from typing import Dict, Any

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(login_data: LoginRequest) -> LoginResponse:
    """
    用户登录接口
    
    - 验证用户名和密码
    - 返回 JWT token 和用户信息
    - 兼容现有的 users.json 和 bcrypt 密码哈希
    """
    user = authenticate_user(login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 创建访问令牌
    access_token = create_access_token(data={"sub": user["username"]})
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserInfo(
            username=user["username"],
            name=user["name"],
            email=user.get("email"),
            role=user.get("role", "user")
        )
    )


@router.get("/me", response_model=UserInfo, summary="获取当前用户信息")
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> UserInfo:
    """
    获取当前登录用户的信息
    
    需要 Bearer Token 认证
    """
    return UserInfo(
        username=current_user["username"],
        name=current_user["name"],
        email=current_user.get("email"),
        role=current_user.get("role", "user")
    )


@router.post("/logout", summary="用户登出")
async def logout(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """
    用户登出接口
    
    注意：由于 JWT 是无状态的，客户端需要删除本地存储的 token
    这里只是返回成功响应，实际的登出由客户端完成
    """
    return {"message": "登出成功", "username": current_user["username"]}


@router.post("/me/password", summary="修改当前用户密码")
async def change_my_password(
    password_data: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """
    修改当前登录用户的密码（自助改密码）
    
    需要 Bearer Token 认证
    需要提供旧密码进行验证
    """
    username = current_user["username"]
    
    # 获取用户信息（包含密码哈希）
    users = load_users()
    if username not in users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user_info = users[username]
    hashed_password = user_info.get("password")
    if not hashed_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户密码数据异常"
        )
    
    # 验证旧密码
    if not verify_password(password_data.old_password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 修改密码
    if not change_password(username, password_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改密码失败"
        )
    
    return {"message": "密码修改成功", "username": username}

