"""
统计相关的 Pydantic Schema
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class StatisticsOverview(BaseModel):
    """总体统计"""
    total_messages: int
    today_messages: int
    total_links: int


class DailyTrendItem(BaseModel):
    """每日趋势项"""
    date: str  # 格式：MM-DD
    messages: int
    links: int


class DailyTrendResponse(BaseModel):
    """最近10天趋势"""
    days: List[DailyTrendItem]


class DedupStatsItem(BaseModel):
    """去重统计项"""
    hour: datetime
    deleted_count: int


class DedupStatsResponse(BaseModel):
    """最近10小时去重统计"""
    hours: List[DedupStatsItem]


class NetdiskDistributionItem(BaseModel):
    """网盘分布项"""
    netdisk_name: str
    link_count: int
    percentage: float


class NetdiskDistributionResponse(BaseModel):
    """最近24小时网盘分布"""
    distribution: List[NetdiskDistributionItem]


class ActivityHeatmapCell(BaseModel):
    """活跃热力图单元格"""
    date: str  # 格式：YYYY-MM-DD
    hour: int  # 0-23
    message_count: int


class ActivityHeatmapResponse(BaseModel):
    """最近N天的活跃热力图"""
    dates: List[str]
    hours: List[int]
    cells: List[ActivityHeatmapCell]
    max_count: int

