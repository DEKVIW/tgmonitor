from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _serialize_ai_center_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


class AiCenterBaseModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: _serialize_ai_center_datetime,
        }
    )


class AiCenterOverviewResponse(AiCenterBaseModel):
    total_providers: int = 0
    enabled_providers: int = 0
    default_provider_id: int | None = None
    default_provider_label: str | None = None
    total_routes: int = 0
    ready_routes: int = 0
    recent_success_count_24h: int = 0
    recent_failure_count_24h: int = 0
    legacy_migration_applied: bool = False
    generated_at: datetime


class AiCenterProviderModelItem(AiCenterBaseModel):
    id: int
    provider_id: int
    model_id: str
    label: str
    owned_by: str | None = None
    is_enabled: bool = True
    is_preferred: bool = False
    last_refreshed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AiCenterProviderItem(AiCenterBaseModel):
    id: int
    provider_key: str
    display_name: str
    provider_type: str
    base_url: str
    api_mode: str
    is_enabled: bool = True
    is_default: bool = False
    priority: int = 100
    timeout_seconds: int = 25
    max_retries: int = 1
    cooldown_seconds: int = 300
    cooldown_until: datetime | None = None
    health_status: str = "unknown"
    consecutive_failures: int = 0
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_message: str | None = None
    has_api_key: bool = False
    model_count: int = 0
    enabled_model_count: int = 0
    preferred_model_id: str | None = None
    updated_by: str | None = None
    extra_json: dict[str, Any] = Field(default_factory=dict)
    models: list[AiCenterProviderModelItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AiCenterProviderListResponse(AiCenterBaseModel):
    items: list[AiCenterProviderItem] = Field(default_factory=list)
    total: int = 0


class AiCenterProviderUpsertRequest(AiCenterBaseModel):
    provider_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=128)
    base_url: str = Field(default="", max_length=512)
    api_mode: str = Field(default="auto", max_length=32)
    api_key: str | None = Field(default=None, max_length=8000)
    clear_api_key: bool = False
    is_enabled: bool = True
    is_default: bool = False
    priority: int = Field(default=100, ge=0, le=100000)
    timeout_seconds: int = Field(default=25, ge=5, le=120)
    max_retries: int = Field(default=1, ge=0, le=5)
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    extra_json: dict[str, Any] = Field(default_factory=dict)


class AiCenterProviderTestRequest(AiCenterBaseModel):
    model_id: str | None = Field(default=None, max_length=255)
    sample_text: str | None = Field(default=None, max_length=500)


class AiCenterProviderTestResponse(AiCenterBaseModel):
    provider_id: int
    provider_label: str | None = None
    model_id: str | None = None
    used_api_mode: str | None = None
    text: str = ""
    ok: bool = True


class AiCenterRouteStepItem(AiCenterBaseModel):
    id: int
    step_index: int
    provider_id: int
    provider_key: str | None = None
    provider_label: str | None = None
    provider_enabled: bool = False
    provider_health_status: str = "unknown"
    model_id: str | None = None
    model_label: str | None = None
    is_enabled: bool = True
    extra_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AiCenterRouteItem(AiCenterBaseModel):
    id: int
    route_key: str
    display_name: str
    description: str = ""
    output_mode: str = "text"
    is_enabled: bool = True
    max_attempts: int = 3
    updated_by: str | None = None
    extra_json: dict[str, Any] = Field(default_factory=dict)
    steps: list[AiCenterRouteStepItem] = Field(default_factory=list)
    configured_step_count: int = 0
    enabled_step_count: int = 0
    is_ready: bool = False
    ready_reason: str | None = None
    ready_provider_label: str | None = None
    ready_model_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AiCenterRouteListResponse(AiCenterBaseModel):
    items: list[AiCenterRouteItem] = Field(default_factory=list)
    total: int = 0


class AiCenterRouteStepUpsertRequest(AiCenterBaseModel):
    id: int | None = None
    provider_id: int = Field(ge=1)
    model_id: str | None = Field(default=None, max_length=255)
    is_enabled: bool = True
    extra_json: dict[str, Any] = Field(default_factory=dict)


class AiCenterRouteUpsertRequest(AiCenterBaseModel):
    display_name: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=2000)
    output_mode: str = Field(default="text", max_length=32)
    is_enabled: bool = True
    max_attempts: int = Field(default=3, ge=1, le=10)
    extra_json: dict[str, Any] = Field(default_factory=dict)
    steps: list[AiCenterRouteStepUpsertRequest] = Field(default_factory=list)


class AiCenterRouteReadinessResponse(AiCenterBaseModel):
    route_key: str
    is_ready: bool = False
    reason: str | None = None
    provider_label: str | None = None
    model_id: str | None = None
    step_count: int = 0
    enabled_step_count: int = 0


class AiCenterRouteTestRequest(AiCenterBaseModel):
    system_prompt: str = Field(min_length=1, max_length=12000)
    user_prompt: str = Field(min_length=1, max_length=12000)


class AiCenterRouteTestResponse(AiCenterBaseModel):
    route_key: str
    provider_id: int | None = None
    provider_label: str | None = None
    model_id: str | None = None
    used_api_mode: str | None = None
    duration_ms: int | None = None
    text: str = ""
    event_id: int | None = None
    ok: bool = True


class AiCenterCallEventItem(AiCenterBaseModel):
    id: int
    route_key: str
    route_profile_id: int | None = None
    route_step_id: int | None = None
    provider_id: int | None = None
    provider_label: str | None = None
    model_id: str | None = None
    status: str
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    extra_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AiCenterCallEventListResponse(AiCenterBaseModel):
    items: list[AiCenterCallEventItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50


class AiCenterDeleteResponse(AiCenterBaseModel):
    id: int
    deleted: bool = True
