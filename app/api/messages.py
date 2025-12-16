"""
消息相关 API 路由
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.schemas.message import (
    MessageResponse,
    MessageListResponse,
    MessageFilters,
    TagStatsResponse
)
from app.services.message_service import (
    get_filtered_messages,
    get_message_by_id,
    get_tag_stats
)
from app.api.dependencies import get_db, get_current_user, get_optional_current_user
from app.models.config import settings
from typing import Dict, Any, Optional

router = APIRouter(prefix="/api/messages", tags=["消息"])


@router.get("", response_model=MessageListResponse, summary="获取消息列表")
async def get_messages(
    search_query: Optional[str] = Query(None, description="搜索关键词（支持多关键词，空格分隔）"),
    time_range: str = Query("最近24小时", description="时间范围：最近1小时、最近24小时、最近7天、最近30天、全部"),
    selected_tags: Optional[List[str]] = Query(None, description="选中的标签列表"),
    selected_netdisks: Optional[List[str]] = Query(None, description="选中的网盘类型列表"),
    min_content_length: int = Query(0, description="最小内容长度"),
    has_links_only: bool = Query(False, description="是否只显示有链接的消息"),
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(100, ge=1, le=200, description="每页数量（1-200）"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> MessageListResponse:
    """
    获取消息列表（支持筛选和分页）
    
    - 支持多关键词搜索
    - 支持时间范围筛选
    - 支持标签筛选
    - 支持网盘类型筛选
    - 支持分页
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问消息列表",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 游客模式限制：只读，固定时间范围，禁用筛选，但允许翻页
    is_guest = current_user is None and settings.PUBLIC_DASHBOARD_ENABLED
    if is_guest:
        # 强制最近24小时
        time_range = "最近24小时"
        # 禁用搜索和筛选
        search_query = None
        selected_tags = []
        selected_netdisks = []
        min_content_length = 0
        has_links_only = False
        # 限制分页大小（最多100条/页），但允许翻页
        page_size = min(page_size, 100)
        # 允许翻页，不限制页码
    
    try:
        messages, total, max_page = get_filtered_messages(
            db=db,
            search_query=search_query,
            time_range=time_range,
            selected_tags=selected_tags or [],
            selected_netdisks=selected_netdisks or [],
            min_content_length=min_content_length,
            has_links_only=has_links_only,
            page=page,
            page_size=page_size
        )
        
        return MessageListResponse(
            messages=[MessageResponse.from_orm(msg) for msg in messages],
            total=total,
            page=page,
            page_size=page_size,
            max_page=max_page
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取消息列表失败: {str(e)}"
        )


@router.get("/{message_id}", response_model=MessageResponse, summary="获取单条消息详情")
async def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> MessageResponse:
    """
    根据ID获取单条消息详情
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问消息详情",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    message = get_message_by_id(db, message_id)
    
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"消息 {message_id} 不存在"
        )
    
    return MessageResponse.from_orm(message)


@router.get("/tags/stats", response_model=List[TagStatsResponse], summary="获取标签统计")
async def get_tags_stats(
    limit: int = Query(50, ge=1, le=100, description="返回的标签数量限制"),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
) -> List[TagStatsResponse]:
    """
    获取标签统计信息（按数量排序）
    
    使用SQL聚合，性能优化
    
    认证：如果启用了游客模式（PUBLIC_DASHBOARD_ENABLED），则无需认证；否则需要 Bearer Token
    """
    # 检查是否需要认证
    if not settings.PUBLIC_DASHBOARD_ENABLED and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录才能访问标签统计",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        tag_stats = get_tag_stats(db, limit=limit)
        return [TagStatsResponse(tag=tag, count=count) for tag, count in tag_stats]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取标签统计失败: {str(e)}"
        )

