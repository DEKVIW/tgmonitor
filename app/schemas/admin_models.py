"""Pydantic models used by admin endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.channel_utils import dedupe_preserve_order, normalize_channel_username


def _normalize_text(value: str, *, allow_empty: bool = False, field_name: str = "value") -> str:
    normalized = (value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_usernames(values: List[str]) -> List[str]:
    cleaned = []
    for value in values:
        username = _normalize_text(value, field_name="username")
        if any(ch.isspace() for ch in username):
            raise ValueError("username cannot contain spaces")
        cleaned.append(username)
    cleaned = dedupe_preserve_order(cleaned)
    if not cleaned:
        raise ValueError("at least one username is required")
    return cleaned


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CredentialResponse(ORMModel):
    id: int
    api_id: str
    api_hash: str


class CredentialCreate(BaseModel):
    api_id: str = Field(min_length=1, max_length=64)
    api_hash: str = Field(min_length=1, max_length=256)

    @field_validator("api_id", "api_hash")
    @classmethod
    def validate_credential_fields(cls, value: str) -> str:
        return _normalize_text(value)


class ChannelResponse(ORMModel):
    id: int
    username: str


class ChannelCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_channel_username(value)


class SystemConfigResponse(BaseModel):
    public_dashboard_enabled: bool


class SystemConfigUpdate(BaseModel):
    public_dashboard_enabled: bool


class UserResponse(BaseModel):
    username: str
    name: str
    email: str
    role: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(default="", max_length=128)
    email: str = Field(default="", max_length=255)
    role: str = Field(default="user")

    @field_validator("username")
    @classmethod
    def validate_user_username(cls, value: str) -> str:
        username = _normalize_text(value, field_name="username")
        if any(ch.isspace() for ch in username):
            raise ValueError("username cannot contain spaces")
        return username

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _normalize_text(value, field_name="password")

    @field_validator("name", "email")
    @classmethod
    def validate_optional_text_fields(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = None

    @field_validator("name", "email")
    @classmethod
    def validate_update_text_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_text(value, allow_empty=True)

    @field_validator("role")
    @classmethod
    def validate_update_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class PasswordChange(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _normalize_text(value, field_name="new_password")


class UsernameChange(BaseModel):
    new_username: str = Field(min_length=1, max_length=64)

    @field_validator("new_username")
    @classmethod
    def validate_new_username(cls, value: str) -> str:
        username = _normalize_text(value, field_name="new_username")
        if any(ch.isspace() for ch in username):
            raise ValueError("new_username cannot contain spaces")
        return username


class RoleChange(BaseModel):
    new_role: str

    @field_validator("new_role")
    @classmethod
    def validate_new_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="new_role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("new_role must be admin or user")
        return role


class BulkRandomCreateRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=500)
    prefix: str = Field(default="user", min_length=1, max_length=32)
    start_index: int = Field(default=1, ge=1)
    role: str = Field(default="user")
    password_length: int = Field(default=12, ge=6, le=32)

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        prefix = _normalize_text(value, field_name="prefix")
        if any(ch.isspace() for ch in prefix):
            raise ValueError("prefix cannot contain spaces")
        return prefix

    @field_validator("role")
    @classmethod
    def validate_bulk_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class BulkRandomCreateResult(BaseModel):
    username: str
    password: str
    role: str


class BulkFailure(BaseModel):
    username: Optional[str] = None
    reason: str


class BulkCreateResponse(BaseModel):
    successes: List[BulkRandomCreateResult]
    failures: List[BulkFailure]


class BulkUsernamesRequest(BaseModel):
    usernames: List[str]
    password_length: Optional[int] = Field(default=12, ge=6, le=32)

    @model_validator(mode="after")
    def normalize_usernames_list(self) -> "BulkUsernamesRequest":
        self.usernames = _normalize_usernames(self.usernames)
        return self


class BulkResetResult(BaseModel):
    username: str
    password: str


class BulkSimpleResponse(BaseModel):
    successes: List[Any]
    failures: List[BulkFailure]


class MaintenanceResult(BaseModel):
    success: bool
    fixed_count: Optional[int] = None
    deleted_count: Optional[int] = None
    deleted_details: Optional[int] = None
    deleted_stats: Optional[int] = None
    cutoff_time: Optional[str] = None
    errors: Optional[List[str]] = None
    error: Optional[str] = None


class ClearOldDataRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)


class ChannelDiagnosisResult(BaseModel):
    valid_channels: List[Dict[str, Any]]
    invalid_channels: List[Dict[str, Any]]


class MonitorTestResult(BaseModel):
    success: bool
    channels_tested: Optional[int] = None
    message_received: Optional[bool] = None
    message: Optional[str] = None
    error: Optional[str] = None


class LinkCheckTaskCreate(BaseModel):
    period: str = Field(min_length=1, max_length=128)
    max_concurrent: int = Field(default=5, ge=1, le=10)

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        return _normalize_text(value, field_name="period")


class LinkCheckTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    period_desc: Optional[str] = None
    total_links: Optional[int] = None
    checked_links: Optional[int] = None
    valid_links: Optional[int] = None
    invalid_links: Optional[int] = None
    check_time: Optional[str] = None
    duration: Optional[float] = None
    logs: Optional[List[str]] = None
    error: Optional[str] = None


class LinkCheckTaskHistory(BaseModel):
    id: int
    check_time: str
    total_messages: int
    total_links: int
    valid_links: int
    invalid_links: int
    status: str
    duration: Optional[float] = None


class LinkCheckTaskResult(BaseModel):
    stats: Dict[str, Any]
    details: List[Dict[str, Any]]
