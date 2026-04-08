"""Runtime auth schemas used by current API routes."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UserInfo(BaseModel):
    username: str
    name: str
    email: Optional[str] = None
    role: str = "user"


class LoginRequest(BaseModel):
    username: str
    password: str
    turnstile_token: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ChangeUsernameRequest(BaseModel):
    new_username: str


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
