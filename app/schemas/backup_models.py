from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_TARGET_KINDS = {"local", "webdav"}
ALLOWED_BACKUP_MODES = {"full", "media_export"}
ALLOWED_SCHEDULE_KINDS = {"manual", "daily", "weekly", "monthly"}
ALLOWED_EXPORT_RANGE_KINDS = {"all", "days"}


def _normalize_text(value: str, *, allow_empty: bool = False, field_name: str = "value") -> str:
    normalized = (value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class BackupTargetBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_kind: str = Field(default="local", max_length=32)
    provider: str = Field(default="local", max_length=64)
    is_enabled: bool = True
    backup_mode: str = Field(default="full", max_length=32)
    schedule_enabled: bool = False
    schedule_kind: str = Field(default="manual", max_length=32)
    schedule_hour: int = Field(default=3, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)
    schedule_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    schedule_day: Optional[int] = Field(default=None, ge=1, le=31)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    retention_count: int = Field(default=10, ge=0, le=3650)
    retention_days: int = Field(default=30, ge=0, le=3650)
    run_log_retention_days: int = Field(default=0, ge=0, le=3650)
    local_dir: str = Field(default="", max_length=2000)
    webdav_base_url: str = Field(default="", max_length=2000)
    webdav_username: str = Field(default="", max_length=255)
    webdav_password: str = Field(default="", max_length=2000)
    clear_webdav_password: bool = False
    webdav_root_path: str = Field(default="", max_length=2000)
    webdav_timeout_seconds: int = Field(default=60, ge=5, le=600)
    webdav_verify_ssl: bool = True
    include_database: bool = True
    include_users_json: bool = True
    include_env_file: bool = False
    include_runtime_data: bool = True
    export_range_kind: str = Field(default="all", max_length=16)
    export_range_days: Optional[int] = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_text(value, field_name="name")

    @field_validator("target_kind")
    @classmethod
    def validate_target_kind(cls, value: str) -> str:
        normalized = _normalize_text(value, field_name="target_kind").lower()
        if normalized not in ALLOWED_TARGET_KINDS:
            raise ValueError("target_kind must be local or webdav")
        return normalized

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = _normalize_text(value, allow_empty=True, field_name="provider").lower()
        return normalized or "local"

    @field_validator("backup_mode")
    @classmethod
    def validate_backup_mode(cls, value: str) -> str:
        normalized = _normalize_text(value, field_name="backup_mode").lower()
        if normalized not in ALLOWED_BACKUP_MODES:
            raise ValueError("backup_mode must be full or media_export")
        return normalized

    @field_validator("schedule_kind")
    @classmethod
    def validate_schedule_kind(cls, value: str) -> str:
        normalized = _normalize_text(value, field_name="schedule_kind").lower()
        if normalized not in ALLOWED_SCHEDULE_KINDS:
            raise ValueError("schedule_kind must be manual, daily, weekly or monthly")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return _normalize_text(value, field_name="timezone")

    @field_validator(
        "local_dir",
        "webdav_base_url",
        "webdav_username",
        "webdav_password",
        "webdav_root_path",
    )
    @classmethod
    def validate_optional_text_fields(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True)

    @field_validator("export_range_kind")
    @classmethod
    def validate_export_range_kind(cls, value: str) -> str:
        normalized = _normalize_text(value, field_name="export_range_kind").lower()
        if normalized not in ALLOWED_EXPORT_RANGE_KINDS:
            raise ValueError("export_range_kind must be all or days")
        return normalized

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "BackupTargetBase":
        if self.target_kind == "local":
            self.provider = "local"
            if not self.local_dir:
                raise ValueError("local_dir is required for local targets")
        elif not self.webdav_base_url:
            raise ValueError("webdav_base_url is required for webdav targets")

        if self.schedule_enabled:
            if self.schedule_kind == "manual":
                raise ValueError("schedule_kind cannot be manual when schedule_enabled is true")
            if self.schedule_kind == "weekly" and self.schedule_weekday is None:
                raise ValueError("schedule_weekday is required for weekly schedules")
            if self.schedule_kind == "monthly" and self.schedule_day is None:
                raise ValueError("schedule_day is required for monthly schedules")
        else:
            self.schedule_kind = "manual"
            self.schedule_weekday = None
            self.schedule_day = None

        if self.backup_mode == "full":
            if not any(
                (
                    self.include_database,
                    self.include_users_json,
                    self.include_env_file,
                    self.include_runtime_data,
                )
            ):
                raise ValueError("at least one full-backup source must be enabled")
            self.export_range_kind = "all"
            self.export_range_days = None
        else:
            if self.export_range_kind == "days" and self.export_range_days is None:
                raise ValueError("export_range_days is required when export_range_kind is days")
            if self.export_range_kind == "all":
                self.export_range_days = None
            self.include_database = True
            self.include_users_json = True
            self.include_env_file = False
            self.include_runtime_data = True

        if self.clear_webdav_password:
            self.webdav_password = ""

        return self


class BackupTargetCreate(BackupTargetBase):
    pass


class BackupTargetUpdate(BackupTargetBase):
    pass


class BackupTargetResponse(BaseModel):
    id: int
    name: str
    target_kind: str
    provider: str
    is_enabled: bool
    backup_mode: str
    schedule_enabled: bool
    schedule_kind: str
    schedule_hour: int
    schedule_minute: int
    schedule_weekday: Optional[int] = None
    schedule_day: Optional[int] = None
    timezone: str
    retention_count: int
    retention_days: int
    run_log_retention_days: int
    local_dir: str
    webdav_base_url: str
    webdav_username: str
    webdav_root_path: str
    webdav_timeout_seconds: int
    webdav_verify_ssl: bool
    webdav_password_configured: bool
    include_database: bool
    include_users_json: bool
    include_env_file: bool
    include_runtime_data: bool
    export_range_kind: str
    export_range_days: Optional[int] = None
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_status: Optional[str] = None
    last_error_message: Optional[str] = None
    has_active_run: bool = False
    active_run_id: Optional[int] = None
    active_run_status: Optional[str] = None
    extra_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    updated_by: Optional[str] = None


class BackupRunResponse(BaseModel):
    id: int
    target_id: Optional[int] = None
    target_name: str
    target_kind: str
    provider: str
    backup_mode: str
    trigger_source: str
    status: str
    file_name: Optional[str] = None
    file_format: Optional[str] = None
    file_size_bytes: Optional[float] = None
    sha256: Optional[str] = None
    local_path: Optional[str] = None
    remote_path: Optional[str] = None
    remote_url: Optional[str] = None
    item_count: Optional[int] = None
    started_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_by: Optional[str] = None
    error_message: Optional[str] = None
    result_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    reused_existing: bool = False


class BackupTargetTestResult(BaseModel):
    success: bool
    target_kind: str
    message: str
    resolved_path: Optional[str] = None
    remote_path: Optional[str] = None


class BackupRunDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list, min_length=1, max_length=200)


class BackupRunDeleteResponse(BaseModel):
    deleted_count: int
    skipped_active_count: int = 0
    skipped_missing_count: int = 0
    deleted_ids: list[int] = Field(default_factory=list)
