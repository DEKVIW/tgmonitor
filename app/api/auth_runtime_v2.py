from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies_runtime_v2 import get_current_user
from app.schemas.auth_runtime_models import (
    ChangePasswordRequest,
    ChangeUsernameRequest,
    LinuxDoLoginExchangeRequest,
    LinuxDoLoginStartRequest,
    LinuxDoLoginStartResponse,
    LinuxDoPublicAuthConfig,
    LoginRequest,
    LoginResponse,
    PublicAuthProvidersResponse,
    UserInfo,
)
from app.services.account_auth_service import (
    authenticate_user,
    create_login_session,
    generate_client_instance_id,
    revoke_session,
)
from app.services.account_service import change_password_for_account, change_username_for_account
from app.services.linuxdo_auth_service import (
    build_linuxdo_authorize_url,
    exchange_linuxdo_code_for_login,
    get_linuxdo_public_state,
)
from app.services.security_service import ensure_login_challenge_passed

CLIENT_INSTANCE_COOKIE = "tg_client_instance_id"

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_user_info(user: dict[str, Any]) -> UserInfo:
    return UserInfo(
        username=user["username"],
        name=user["name"],
        email=user.get("email"),
        role=user.get("role", "user"),
    )


def _set_client_instance_cookie(response: Response, request: Request, client_instance_id: str) -> None:
    response.set_cookie(
        key=CLIENT_INSTANCE_COOKIE,
        value=client_instance_id,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


@router.get("/providers/public", response_model=PublicAuthProvidersResponse, summary="Get public login providers")
async def get_public_auth_providers() -> PublicAuthProvidersResponse:
    linuxdo_state = get_linuxdo_public_state()
    return PublicAuthProvidersResponse(linuxdo=LinuxDoPublicAuthConfig(**linuxdo_state))


@router.post("/login", response_model=LoginResponse, summary="Log in with local account")
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
            detail="Invalid username or password, or the account is disabled/expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _set_client_instance_cookie(response, request, client_instance_id)
    return LoginResponse(
        access_token=login_result["access_token"],
        token_type="bearer",
        user=_build_user_info(login_result["user"]),
    )


@router.post("/linuxdo/start", response_model=LinuxDoLoginStartResponse, summary="Start LinuxDo login")
async def start_linuxdo_login(
    payload: LinuxDoLoginStartRequest,
    request: Request,
) -> LinuxDoLoginStartResponse:
    try:
        ensure_login_challenge_passed(
            payload.turnstile_token,
            remote_ip=request.client.host if request.client else None,
        )
        authorize_url = build_linuxdo_authorize_url(redirect_uri=payload.redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return LinuxDoLoginStartResponse(authorize_url=authorize_url)


@router.post("/linuxdo/exchange", response_model=LoginResponse, summary="Exchange LinuxDo OAuth code")
async def exchange_linuxdo_login(
    payload: LinuxDoLoginExchangeRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    client_instance_id = request.cookies.get(CLIENT_INSTANCE_COOKIE) or generate_client_instance_id()
    try:
        login_result = exchange_linuxdo_code_for_login(
            code=payload.code,
            state_token=payload.state,
            redirect_uri=payload.redirect_uri,
            client_instance_id=client_instance_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    _set_client_instance_cookie(response, request, client_instance_id)
    return LoginResponse(
        access_token=login_result["access_token"],
        token_type="bearer",
        user=_build_user_info(login_result["user"]),
    )


@router.get("/me", response_model=UserInfo, summary="Get current user")
async def get_current_user_info(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserInfo:
    return _build_user_info(current_user)


@router.post("/ping", response_model=UserInfo, summary="Refresh current session heartbeat")
async def ping_current_session(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserInfo:
    return _build_user_info(current_user)


@router.post("/logout", summary="Log out current user")
async def logout(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    session_id = current_user.get("session_id")
    if session_id:
        revoke_session(str(session_id), reason="logout")
    return {"message": "Logged out successfully", "username": current_user["username"]}


@router.post("/me/password", summary="Change current user password")
async def change_my_password(
    password_data: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    username = current_user["username"]
    if authenticate_user(username, password_data.old_password) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if not change_password_for_account(username, password_data.new_password, updated_by=username):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to change password")
    session_id = current_user.get("session_id")
    if session_id:
        revoke_session(str(session_id), reason="password_changed")
    return {"message": "Password updated successfully", "username": username}


@router.post("/me/username", summary="Change current username")
async def change_my_username(
    payload: ChangeUsernameRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    username = current_user["username"]
    try:
        changed = change_username_for_account(username, payload.new_username, updated_by=username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Current user does not exist")
    return {
        "message": "Username updated successfully",
        "old_username": username,
        "new_username": payload.new_username,
    }
