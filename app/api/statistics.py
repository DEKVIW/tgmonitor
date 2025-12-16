"""
统计相关 API 路由
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.schemas.statistics import (
    StatisticsOverview,
    DailyTrendResponse,
    DailyTrendItem,
    DedupStatsResponse,
    DedupStatsItem,
    NetdiskDistributionResponse,
    NetdiskDistributionItem
)
from app.services.statistics_service import (
    get_statistics_overview,
    get_daily_trend,
    get_dedup_stats,
    get_netdisk_distribution
)
from app.api.dependencies import get_db, get_current_user, get_optional_current_user
from app.models.config import settings
from typing import Dict, Any, Optional

router = APIRouter(prefix="/api/statistics", tags=["统计"])


@router.get("/overview", response_model=StatisticsOverview, summary="获取总体统计")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> StatisticsOverview:
    """
    获取总体统计信息
    
    - 总消息数
    - 今日消息数
    - 总链接数
    
    使用SQL聚合优化，不加载所有数据到内存
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问统计信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        stats = get_statistics_overview(db)
        return StatisticsOverview(
            total_messages=stats["total_messages"],
            today_messages=stats["today_messages"],
            total_links=stats["total_links"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取总体统计失败: {str(e)}"
        )


@router.get("/daily-trend", response_model=DailyTrendResponse, summary="获取最近10天趋势")
async def get_daily_trend_api(
    days: int = Query(10, ge=1, le=30, description="天数（1-30）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> DailyTrendResponse:
    """
    获取最近N天的每日消息和链接趋势
    
    使用SQL聚合优化，按日期分组，不加载所有数据到内存
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问统计信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 游客模式限制：固定时间范围
    is_guest = current_user is None and settings.PUBLIC_DASHBOARD_ENABLED
    if is_guest:
        days = min(days, 1)  # 最多1天
    
    try:
        trend_data = get_daily_trend(db, days=days)
        return DailyTrendResponse(
            days=[DailyTrendItem(**item) for item in trend_data]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取每日趋势失败: {str(e)}"
        )


@router.get("/dedup-stats", response_model=DedupStatsResponse, summary="获取去重统计")
async def get_dedup_stats_api(
    hours: int = Query(10, ge=1, le=24, description="小时数（1-24）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> DedupStatsResponse:
    """
    获取最近N小时的去重删除统计
    
    使用SQL聚合，按小时分组
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问统计信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 游客模式限制：固定时间范围
    is_guest = current_user is None and settings.PUBLIC_DASHBOARD_ENABLED
    if is_guest:
        hours = min(hours, 24)  # 最多24小时
    
    try:
        stats_data = get_dedup_stats(db, hours=hours)
        return DedupStatsResponse(
            hours=[DedupStatsItem(**item) for item in stats_data]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取去重统计失败: {str(e)}"
        )


@router.get("/netdisk-distribution", response_model=NetdiskDistributionResponse, summary="获取网盘分布")
async def get_netdisk_distribution_api(
    hours: int = Query(24, ge=1, le=168, description="小时数（1-168，即最多7天）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> NetdiskDistributionResponse:
    """
    获取最近N小时的网盘链接分布
    
    使用SQL聚合，按网盘类型分组
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问统计信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 游客模式限制：固定时间范围
    is_guest = current_user is None and settings.PUBLIC_DASHBOARD_ENABLED
    if is_guest:
        hours = min(hours, 24)  # 最多24小时
    
    try:
        distribution_data = get_netdisk_distribution(db, hours=hours)
        return NetdiskDistributionResponse(
            distribution=[NetdiskDistributionItem(**item) for item in distribution_data]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取网盘分布失败: {str(e)}"
        )

