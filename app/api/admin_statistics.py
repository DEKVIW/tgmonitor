from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_admin_user, get_db
from app.schemas.statistics import AdminChannelMatrixResponse, AdminChannelMatrixRow
from app.services.admin_statistics_service import get_admin_channel_matrix

router = APIRouter(prefix="/api/admin/statistics", tags=["admin-statistics"])


@router.get(
    "/channel-matrix",
    response_model=AdminChannelMatrixResponse,
    summary="Get admin channel message matrix",
)
async def get_admin_channel_matrix_api(
    days: int = Query(7, ge=7, le=30, description="Lookback days"),
    _: dict = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminChannelMatrixResponse:
    try:
        payload = get_admin_channel_matrix(db, days=days)
        return AdminChannelMatrixResponse(
            days=int(payload.get("days") or days),
            dates=list(payload.get("dates") or []),
            rows=[AdminChannelMatrixRow(**row) for row in payload.get("rows") or []],
            available_since=payload.get("available_since"),
            max_daily_messages=int(payload.get("max_daily_messages") or 0),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load admin channel matrix: {exc}",
        ) from exc
