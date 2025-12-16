"""
消息服务
处理消息查询、筛选等业务逻辑
优化数据库查询，避免加载所有数据到内存
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_, func, text
from sqlalchemy.sql import text as sql_text
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
import json
from app.models.models import Message
import logging

logger = logging.getLogger(__name__)


def get_filtered_messages(
    db: Session,
    search_query: Optional[str] = None,
    time_range: str = "最近24小时",
    selected_tags: Optional[List[str]] = None,
    selected_netdisks: Optional[List[str]] = None,
    min_content_length: int = 0,
    has_links_only: bool = False,
    page: int = 1,
    page_size: int = 100
) -> Tuple[List[Message], int, int]:
    """
    获取筛选后的消息列表（支持分页）
    
    完全兼容 web.py 中的查询逻辑，但优化了性能
    
    Args:
        db: 数据库会话
        search_query: 搜索关键词（支持多关键词，空格分隔）
        time_range: 时间范围（最近1小时、最近24小时、最近7天、最近30天、全部）
        selected_tags: 选中的标签列表
        selected_netdisks: 选中的网盘类型列表
        min_content_length: 最小内容长度
        has_links_only: 是否只显示有链接的消息
        page: 页码（从1开始）
        page_size: 每页数量
        
    Returns:
        (消息列表, 总数量, 最大页码)
    """
    try:
        query = db.query(Message)
        
        # 搜索关键词筛选
        if search_query:
            search_terms = [term.strip() for term in search_query.split() if term.strip()]
            if search_terms:
                search_filters = []
                for term in search_terms:
                    # 兼容 web.py 的搜索逻辑
                    search_filters.extend([
                        Message.title.ilike(f'%{term}%'),
                        Message.description.ilike(f'%{term}%'),
                        Message.tags.any(term)  # 标签搜索
                    ])
                query = query.filter(or_(*search_filters))
        
        # 时间范围筛选
        time_deltas = {
            "最近1小时": timedelta(hours=1),
            "最近24小时": timedelta(days=1),
            "最近7天": timedelta(days=7),
            "最近30天": timedelta(days=30)
        }
        if time_range in time_deltas:
            query = query.filter(Message.timestamp >= datetime.now() - time_deltas[time_range])
        # 如果 time_range 是 "全部"，则不添加时间筛选
        
        # 标签筛选
        if selected_tags:
            filters = [Message.tags.any(tag) for tag in selected_tags]
            query = query.filter(or_(*filters))
        
        # 网盘类型筛选
        if selected_netdisks:
            filters = []
            for nd in selected_netdisks:
                # 兼容 web.py 的网盘筛选逻辑
                filter_expr = sql_text("netdisk_types @> :netdisk_type")
                filters.append(filter_expr.bindparams(netdisk_type=json.dumps([nd])))
            query = query.filter(or_(*filters))
        
        # 最小内容长度筛选
        if min_content_length > 0:
            query = query.filter(
                (func.length(Message.title) + func.length(Message.description)) >= min_content_length
            )
        
        # 只显示有链接的消息
        if has_links_only:
            query = query.filter(Message.links.isnot(None))
        
        # 分页处理（完全兼容 web.py 的逻辑）
        start_idx = (page - 1) * page_size
        
        # 先获取当前页的数据（使用索引列排序）
        # 尝试多取一条数据来判断是否还有下一页
        messages_page = query.order_by(Message.timestamp.desc()).offset(start_idx).limit(page_size + 1).all()
        
        # 判断是否还有更多数据
        has_more = len(messages_page) > page_size
        if has_more:
            # 如果有多余的数据，说明不是最后一页，只保留 page_size 条
            messages_page = messages_page[:page_size]
            # 需要计算总数以显示准确的分页信息
            total_count = query.count()
        else:
            # 如果没有多余的数据，说明已经是最后一页，可以直接计算总数
            total_count = start_idx + len(messages_page)
        
        max_page = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        # 如果页码超出范围，返回第一页
        if page > max_page and max_page > 0:
            messages_page = query.order_by(Message.timestamp.desc()).offset(0).limit(page_size).all()
            page = 1
        
        return messages_page, total_count, max_page
        
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}", exc_info=True)
        raise


def get_message_by_id(db: Session, message_id: int) -> Optional[Message]:
    """
    根据ID获取单条消息
    
    Args:
        db: 数据库会话
        message_id: 消息ID
        
    Returns:
        Message对象，如果不存在则返回None
    """
    try:
        return db.query(Message).filter(Message.id == message_id).first()
    except Exception as e:
        logger.error(f"获取消息 {message_id} 失败: {e}", exc_info=True)
        return None


def get_tag_stats(db: Session, limit: int = 50) -> List[Tuple[str, int]]:
    """
    获取标签统计（按数量排序）
    
    使用SQL聚合，不加载所有数据到内存
    
    Args:
        db: 数据库会话
        limit: 返回的标签数量限制
        
    Returns:
        标签和数量的元组列表
    """
    try:
        result = db.execute(sql_text("""
            SELECT unnest(tags) as tag, COUNT(*) as count 
            FROM messages 
            WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
            GROUP BY tag 
            ORDER BY count DESC
            LIMIT :limit
        """), {"limit": limit}).all()
        
        return [(tag, count) for tag, count in result]
    except Exception as e:
        logger.error(f"获取标签统计失败: {e}", exc_info=True)
        return []

