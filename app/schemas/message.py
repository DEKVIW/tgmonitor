"""
消息相关的 Pydantic Schema
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class MessageResponse(BaseModel):
    """消息响应模型"""
    id: int
    timestamp: datetime
    title: Optional[str] = None
    description: Optional[str] = None
    links: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    channel: Optional[str] = None
    group_name: Optional[str] = None
    bot: Optional[str] = None
    created_at: datetime
    netdisk_types: Optional[List[str]] = None

    class Config:
        from_attributes = True  # 允许从ORM模型创建


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int
    max_page: int


class MessageFilters(BaseModel):
    """消息筛选参数"""
    search_query: Optional[str] = None
    time_range: Optional[str] = "最近24小时"  # 最近1小时、最近24小时、最近7天、最近30天、全部
    selected_tags: Optional[List[str]] = None
    selected_netdisks: Optional[List[str]] = None
    min_content_length: Optional[int] = 0
    has_links_only: Optional[bool] = False
    page: Optional[int] = 1
    page_size: Optional[int] = 100


class TagStatsResponse(BaseModel):
    """标签统计响应"""
    tag: str
    count: int

