from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


SearchChallengeScope = Literal["guest_only", "all_users"]
DomainChallengeAction = Literal["managed_challenge", "js_challenge", "challenge"]
DomainChallengeExpressionMode = Literal["recommended", "custom"]
DomainChallengeSyncStatus = Literal["never", "success", "error"]


def _normalize_text(value: str, *, allow_empty: bool = False, field_name: str = "value") -> str:
    normalized = (value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class PublicSecurityConfigResponse(BaseModel):
    turnstile_ready: bool = False
    turnstile_site_key: str = ""
    login_challenge_enabled: bool = False
    search_challenge_enabled: bool = False
    search_challenge_scope: SearchChallengeScope = "guest_only"
    search_challenge_clearance_ttl_seconds: int = 1800


class SecurityConfigResponse(PublicSecurityConfigResponse):
    turnstile_secret_configured: bool = False
    cloudflare_zone_id: str = ""
    cloudflare_api_token_configured: bool = False
    domain_access_challenge_enabled: bool = False
    domain_access_challenge_action: DomainChallengeAction = "managed_challenge"
    domain_access_challenge_expression_mode: DomainChallengeExpressionMode = "recommended"
    domain_access_challenge_expression_custom: str = ""
    domain_access_recommended_expression: str = ""
    domain_access_rule_id: str = ""
    domain_access_ruleset_id: str = ""
    domain_access_last_synced_at: Optional[str] = None
    domain_access_last_sync_status: DomainChallengeSyncStatus = "never"
    domain_access_last_sync_message: str = ""


class SecurityConfigUpdate(BaseModel):
    turnstile_site_key: str = Field(default="", max_length=512)
    turnstile_secret: str = Field(default="", max_length=4000)
    clear_turnstile_secret: bool = False
    login_challenge_enabled: bool = False
    search_challenge_enabled: bool = False
    search_challenge_scope: SearchChallengeScope = "guest_only"
    search_challenge_clearance_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    cloudflare_zone_id: str = Field(default="", max_length=128)
    cloudflare_api_token: str = Field(default="", max_length=4000)
    clear_cloudflare_api_token: bool = False
    domain_access_challenge_enabled: bool = False
    domain_access_challenge_action: DomainChallengeAction = "managed_challenge"
    domain_access_challenge_expression_mode: DomainChallengeExpressionMode = "recommended"
    domain_access_challenge_expression_custom: str = Field(default="", max_length=4000)

    @field_validator(
        "turnstile_site_key",
        "turnstile_secret",
        "cloudflare_zone_id",
        "cloudflare_api_token",
        "domain_access_challenge_expression_custom",
    )
    @classmethod
    def validate_text_fields(cls, value: str, info) -> str:
        return _normalize_text(value, allow_empty=True, field_name=info.field_name)


class SecurityChallengeVerifyRequest(BaseModel):
    action: Literal["search"] = "search"
    turnstile_token: str = Field(min_length=1, max_length=4000)

    @field_validator("turnstile_token")
    @classmethod
    def validate_turnstile_token(cls, value: str) -> str:
        return _normalize_text(value, field_name="turnstile_token")


class SecurityChallengeVerifyResponse(BaseModel):
    clearance_token: str
    expires_at: str
    ttl_seconds: int


class DomainChallengeSyncResponse(BaseModel):
    success: bool
    status: DomainChallengeSyncStatus
    message: str
    synced_at: Optional[str] = None
    ruleset_id: str = ""
    rule_id: str = ""
    config: SecurityConfigResponse
