from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_optional_current_user
from app.schemas.security_models import (
    PublicSecurityConfigResponse,
    SecurityChallengeVerifyRequest,
    SecurityChallengeVerifyResponse,
)
from app.services.security_service import get_public_security_config_values, verify_and_issue_search_clearance


router = APIRouter(prefix="/api/security", tags=["安全防护"])


@router.get("/public", response_model=PublicSecurityConfigResponse, summary="获取公开安全配置")
async def get_public_security_config() -> PublicSecurityConfigResponse:
    return PublicSecurityConfigResponse(**get_public_security_config_values())


@router.post("/turnstile/verify", response_model=SecurityChallengeVerifyResponse, summary="校验搜索 Turnstile")
async def verify_search_turnstile(
    payload: SecurityChallengeVerifyRequest,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> SecurityChallengeVerifyResponse:
    try:
        return verify_and_issue_search_clearance(
            payload.turnstile_token,
            current_user=current_user,
            remote_ip=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
