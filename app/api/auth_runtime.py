from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies_runtime import get_current_user
from app.schemas.auth import ChangePasswordRequest, LoginResponse, UserInfo
from app.services.account_auth_service import (
    authenticate_user,
    create_login_session,
    generate_client_instance_id,
    revoke_session,
)
from app.services.account_service import change_password_for_account, change_username_for_account
from app.services.security_service import ensure_login_challenge_passed

CLIENT_INSTANCE_COOKIE = "tg_client_instance_id"


class LoginRequest(BaseModel):
    username: str
    password: str
    turnstile_token: Optional[str] = None


class ChangeUsernameRequest(BaseModel):
    new_username: str


router = APIRouter(prefix="/api/auth", tags=["认证"])


def _build_user_info(user: Dict[str, Any]) -> UserInfo:
    return UserInfo(
        username=user["username"],
        name=user["name"],
        email=user.get("email"),
        role=user.get("role", "user"),
    )


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(login_data: LoginRequest, request: Request, response: Response) -> LoginResponse:
    try:
        ensure_login_challenge_passed(
            login_data.turnstile_token,
            remote_ip=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    client_instance_id = request.cookies.get(CLIENT_INSTANCE_COOKIE) or generate_client_instance_id()
    login_result = create_login_session(
        username=login_data.username,
        password=login_data.password,
        client_instance_id=client_instance_id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if login_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误，或账号已被禁用/过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response.set_cookie(
        key=CLIENT_INSTANCE_COOKIE,
        value=client_instance_id,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return LoginResponse(
        access_token=login_result["access_token"],
        token_type="bearer",
        user=_build_user_info(login_result["user"]),
    )


@router.get("/me", response_model=UserInfo, summary="获取当前用户信息")
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> UserInfo:
    return _build_user_info(current_user)


@router.post("/ping", response_model=UserInfo, summary="刷新当前会话活跃时间")
async def ping_current_session(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> UserInfo:
    return _build_user_info(current_user)


@router.post("/logout", summary="用户登出")
async def logout(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    session_id = current_user.get("session_id")
    if session_id:
        revoke_session(str(session_id), reason="logout")
    return {"message": "登出成功", "username": current_user["username"]}


@router.post("/me/password", summary="修改当前用户密码")
async def change_my_password(
    password_data: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    username = current_user["username"]
    if authenticate_user(username, password_data.old_password) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误")
    if not change_password_for_account(username, password_data.new_password, updated_by=username):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="修改密码失败")
    session_id = current_user.get("session_id")
    if session_id:
        revoke_session(str(session_id), reason="password_changed")
    return {"message": "密码修改成功", "username": username}


@router.post("/me/username", summary="修改当前用户名")
async def change_my_username(
    payload: ChangeUsernameRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    username = current_user["username"]
    try:
        changed = change_username_for_account(username, payload.new_username, updated_by=username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前用户不存在")
    return {"message": "用户名修改成功", "old_username": username, "new_username": payload.new_username}
