from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies_runtime import get_db, get_optional_current_user
from app.schemas.statistics import (
    ActivityHeatmapCell,
    ActivityHeatmapResponse,
    DailyTrendItem,
    DailyTrendResponse,
    DedupStatsItem,
    DedupStatsResponse,
    NetdiskDistributionItem,
    NetdiskDistributionResponse,
    StatisticsOverview,
)
from app.services.statistics_service import (
    get_activity_heatmap,
    get_daily_trend,
    get_dedup_stats,
    get_netdisk_distribution,
    get_statistics_overview,
)
from app.services.system_config_service import is_public_dashboard_enabled

router = APIRouter(prefix="/api/statistics", tags=["统计"])


def _ensure_public_access_allowed(current_user: Optional[Dict[str, Any]]) -> None:
    if current_user is None and not is_public_dashboard_enabled():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问统计信息",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _is_public_guest(current_user: Optional[Dict[str, Any]]) -> bool:
    return current_user is None and is_public_dashboard_enabled()


@router.get("/overview", response_model=StatisticsOverview, summary="获取总体统计")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> StatisticsOverview:
    _ensure_public_access_allowed(current_user)

    try:
        stats = get_statistics_overview(db)
        return StatisticsOverview(
            total_messages=stats["total_messages"],
            today_messages=stats["today_messages"],
            total_links=stats["total_links"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取总体统计失败: {exc}",
        ) from exc


@router.get("/daily-trend", response_model=DailyTrendResponse, summary="获取最近趋势")
async def get_daily_trend_api(
    days: int = Query(10, ge=1, le=30, description="天数（1-30）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> DailyTrendResponse:
    _ensure_public_access_allowed(current_user)

    if _is_public_guest(current_user):
        days = min(days, 1)

    try:
        trend_data = get_daily_trend(db, days=days)
        return DailyTrendResponse(days=[DailyTrendItem(**item) for item in trend_data])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取每日趋势失败: {exc}",
        ) from exc


@router.get("/dedup-stats", response_model=DedupStatsResponse, summary="获取去重统计")
async def get_dedup_stats_api(
    hours: int = Query(10, ge=1, le=24, description="小时数（1-24）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> DedupStatsResponse:
    _ensure_public_access_allowed(current_user)

    if _is_public_guest(current_user):
        hours = min(hours, 24)

    try:
        stats_data = get_dedup_stats(db, hours=hours)
        return DedupStatsResponse(hours=[DedupStatsItem(**item) for item in stats_data])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取去重统计失败: {exc}",
        ) from exc


@router.get("/netdisk-distribution", response_model=NetdiskDistributionResponse, summary="获取网盘分布")
async def get_netdisk_distribution_api(
    hours: int = Query(24, ge=1, le=168, description="小时数（1-168）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> NetdiskDistributionResponse:
    _ensure_public_access_allowed(current_user)

    if _is_public_guest(current_user):
        hours = min(hours, 24)

    try:
        distribution_data = get_netdisk_distribution(db, hours=hours)
        return NetdiskDistributionResponse(
            distribution=[NetdiskDistributionItem(**item) for item in distribution_data]
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取网盘分布失败: {exc}",
        ) from exc


@router.get("/activity-heatmap", response_model=ActivityHeatmapResponse, summary="获取活跃热力图")
async def get_activity_heatmap_api(
    days: int = Query(7, ge=3, le=14, description="天数（3-14）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> ActivityHeatmapResponse:
    _ensure_public_access_allowed(current_user)

    if _is_public_guest(current_user):
        days = min(days, 7)

    try:
        heatmap_data = get_activity_heatmap(db, days=days)
        return ActivityHeatmapResponse(
            dates=heatmap_data["dates"],
            hours=heatmap_data["hours"],
            cells=[ActivityHeatmapCell(**item) for item in heatmap_data["cells"]],
            max_count=heatmap_data["max_count"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取活跃热力图失败: {exc}",
        ) from exc
