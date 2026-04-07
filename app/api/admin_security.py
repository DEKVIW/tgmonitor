from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies_runtime import get_admin_user
from app.schemas.security_models import DomainChallengeSyncResponse, SecurityConfigResponse, SecurityConfigUpdate
from app.services.security_service import (
    SecuritySyncError,
    apply_security_config,
    get_security_config_values,
    sync_domain_access_challenge,
)


router = APIRouter(prefix="/api/admin/security", tags=["安全防护"])


@router.get("", response_model=SecurityConfigResponse, summary="获取安全配置")
async def get_security_config(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> SecurityConfigResponse:
    return SecurityConfigResponse(**get_security_config_values())


@router.put("", response_model=SecurityConfigResponse, summary="更新安全配置")
async def update_security_config(
    payload: SecurityConfigUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> SecurityConfigResponse:
    try:
        return SecurityConfigResponse(
            **apply_security_config(payload.model_dump(), updated_by=current_user.get("username"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新安全配置失败: {exc}",
        ) from exc


@router.post("/domain-access/sync", response_model=DomainChallengeSyncResponse, summary="同步域名访问质询规则")
async def sync_domain_access_challenge_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> DomainChallengeSyncResponse:
    try:
        result = sync_domain_access_challenge(updated_by=current_user.get("username"))
        return DomainChallengeSyncResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SecuritySyncError as exc:
        return DomainChallengeSyncResponse(
            success=False,
            status="error",
            message=exc.message,
            synced_at=exc.synced_at,
            ruleset_id=exc.ruleset_id,
            rule_id=exc.rule_id,
            config=SecurityConfigResponse(**exc.config),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步域名访问质询规则失败: {exc}",
        ) from exc
