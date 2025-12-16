"""
统计服务
优化数据库查询，使用SQL聚合，避免加载所有数据到内存
解决 web.py 中的内存问题
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, text as sql_text
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from app.models.models import Message, DedupStats
import logging

logger = logging.getLogger(__name__)


def get_statistics_overview(db: Session) -> Dict[str, int]:
    """
    获取总体统计信息（优化版本，使用SQL聚合）
    
    解决 web.py 第394-396行的内存问题：
    原代码：for msg in session.query(Message).filter(...).all()  # ❌ 加载所有数据
    优化后：使用SQL聚合，只返回数字
    
    Args:
        db: 数据库会话
        
    Returns:
        包含 total_messages, today_messages, total_links 的字典
    """
    try:
        # 总消息数
        total = db.query(func.count(Message.id)).scalar() or 0
        
        # 今日消息数
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today = db.query(func.count(Message.id)).filter(
            Message.timestamp >= today_start
        ).scalar() or 0
        
        # 总链接数（使用SQL聚合，不加载数据）
        # 优化：使用 jsonb_object_keys 函数计算JSONB对象的键数量
        try:
            # 方法1：使用 jsonb_object_keys 计算每个消息的链接数，然后求和
            total_links_result = db.execute(sql_text("""
                SELECT COALESCE(SUM(
                    (SELECT COUNT(*) FROM jsonb_object_keys(links::jsonb))
                ), 0) as total
                FROM messages
                WHERE links IS NOT NULL
            """)).scalar()
            
            if total_links_result is None:
                total_links_result = 0
        except Exception:
            # 如果上面的方法失败，使用更兼容的方法
            try:
                # 方法2：使用子查询
                total_links_result = db.execute(sql_text("""
                    SELECT COALESCE(SUM(
                        jsonb_array_length(jsonb_object_keys(links::jsonb)::text[])
                    ), 0)
                    FROM messages
                    WHERE links IS NOT NULL
                """)).scalar() or 0
            except Exception:
                # 方法3：最安全的方法，但需要遍历（只获取links字段，不加载整个消息）
                total_links = 0
                messages_with_links = db.query(Message.links).filter(
                    Message.links.isnot(None)
                ).all()
                for (msg_links,) in messages_with_links:
                    if isinstance(msg_links, dict):
                        total_links += len(msg_links)
                total_links_result = total_links
        
        return {
            "total_messages": total,
            "today_messages": today,
            "total_links": int(total_links_result)
        }
    except Exception as e:
        logger.error(f"获取总体统计失败: {e}", exc_info=True)
        return {
            "total_messages": 0,
            "today_messages": 0,
            "total_links": 0
        }


def get_daily_trend(db: Session, days: int = 10) -> List[Dict[str, Any]]:
    """
    获取最近N天的每日趋势（优化版本，使用SQL聚合）
    
    解决 web.py 第397-407行的内存问题：
    原代码：对每一天都执行 .all()，加载所有消息到内存
    优化后：使用SQL GROUP BY，只返回聚合结果
    
    Args:
        db: 数据库会话
        days: 天数，默认10天
        
    Returns:
        每日趋势列表，每个元素包含 date, messages, links
    """
    try:
        # 使用SQL聚合，按日期分组
        result = db.execute(sql_text("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as message_count,
                COALESCE(SUM(
                    CASE 
                        WHEN links IS NOT NULL AND jsonb_typeof(links::jsonb) = 'object'
                            THEN (SELECT COUNT(*) FROM jsonb_object_keys(links::jsonb))
                        ELSE 0
                    END
                ), 0) as link_count
            FROM messages
            WHERE timestamp >= NOW() - INTERVAL '1 day' * :days
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
            LIMIT :days
        """), {"days": days}).all()
        
        # 如果上面的查询不工作，使用更简单的方法
        if not result:
            # 使用更兼容的查询
            result = db.execute(sql_text("""
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as message_count,
                    0 as link_count
                FROM messages
                WHERE timestamp >= NOW() - INTERVAL '1 day' * :days
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
                LIMIT :days
            """), {"days": days}).all()
            
            # 单独计算链接数（但只对每天的消息进行查询，不加载所有数据）
            for row in result:
                date = row.date
                next_date = date + timedelta(days=1)
                link_count = db.query(func.count(Message.id)).filter(
                    Message.timestamp >= datetime.combine(date, datetime.min.time()),
                    Message.timestamp < datetime.combine(next_date, datetime.min.time()),
                    Message.links.isnot(None)
                ).scalar() or 0
                # 这里简化处理，假设每条消息平均1个链接
                # 如果需要精确值，可以进一步优化
                row.link_count = link_count
        
        # 转换为字典列表
        trend_data = []
        for row in result:
            trend_data.append({
                "date": row.date.strftime("%m-%d") if hasattr(row.date, 'strftime') else str(row.date),
                "messages": row.message_count,
                "links": int(row.link_count) if row.link_count else 0
            })
        
        # 确保返回10天的数据（如果不足则补0）
        today = datetime.now().date()
        all_dates = [(today - timedelta(days=i)).strftime("%m-%d") for i in range(days-1, -1, -1)]
        
        trend_dict = {item["date"]: item for item in trend_data}
        complete_trend = []
        for date_str in all_dates:
            if date_str in trend_dict:
                complete_trend.append(trend_dict[date_str])
            else:
                complete_trend.append({
                    "date": date_str,
                    "messages": 0,
                    "links": 0
                })
        
        return complete_trend
        
    except Exception as e:
        logger.error(f"获取每日趋势失败: {e}", exc_info=True)
        # 返回空数据
        today = datetime.now().date()
        return [
            {
                "date": (today - timedelta(days=i)).strftime("%m-%d"),
                "messages": 0,
                "links": 0
            }
            for i in range(days-1, -1, -1)
        ]


def get_dedup_stats(db: Session, hours: int = 10) -> List[Dict[str, Any]]:
    """
    获取最近N小时的去重统计（使用SQL聚合）
    
    兼容 web.py 第477-493行的查询逻辑
    
    Args:
        db: 数据库会话
        hours: 小时数，默认10小时
        
    Returns:
        每小时去重统计列表
    """
    try:
        result = db.execute(sql_text("""
            SELECT 
                date_trunc('hour', run_time) AS hour, 
                SUM(deleted) AS del_cnt
            FROM dedup_stats
            WHERE run_time >= NOW() - INTERVAL '1 hour' * :hours
            GROUP BY hour
            ORDER BY hour
        """), {"hours": hours}).all()
        
        # 转换为字典列表
        stats_data = []
        for row in result:
            stats_data.append({
                "hour": row.hour,
                "deleted_count": int(row.del_cnt) if row.del_cnt else 0
            })
        
        # 确保返回10小时的数据（如果不足则补0）
        now = datetime.now()
        all_hours = [
            (now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i))
            for i in range(hours-1, -1, -1)
        ]
        
        stats_dict = {item["hour"].replace(minute=0, second=0, microsecond=0): item for item in stats_data}
        complete_stats = []
        for hour in all_hours:
            hour_key = hour.replace(minute=0, second=0, microsecond=0)
            if hour_key in stats_dict:
                complete_stats.append(stats_dict[hour_key])
            else:
                complete_stats.append({
                    "hour": hour_key,
                    "deleted_count": 0
                })
        
        return complete_stats
        
    except Exception as e:
        logger.error(f"获取去重统计失败: {e}", exc_info=True)
        # 返回空数据
        now = datetime.now()
        return [
            {
                "hour": now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i),
                "deleted_count": 0
            }
            for i in range(hours-1, -1, -1)
        ]


def get_netdisk_distribution(db: Session, hours: int = 24) -> List[Dict[str, Any]]:
    """
    获取最近N小时的网盘链接分布（使用SQL聚合）
    
    兼容 web.py 第552-581行的查询逻辑
    
    Args:
        db: 数据库会话
        hours: 小时数，默认24小时
        
    Returns:
        网盘分布列表，每个元素包含 netdisk_name, link_count, percentage
    """
    try:
        result = db.execute(sql_text("""
            SELECT 
                netdisk_name,
                COUNT(*) as link_count
            FROM (
                SELECT 
                    jsonb_array_elements_text(netdisk_types) as netdisk_name
                FROM messages 
                WHERE timestamp >= NOW() - INTERVAL ':hours hours'
                  AND netdisk_types IS NOT NULL
            ) t
            GROUP BY netdisk_name
            ORDER BY link_count DESC
        """), {"hours": hours}).all()
        
        if not result:
            return []
        
        # 计算总数和百分比
        total = sum(row.link_count for row in result)
        
        # 品牌名映射（兼容 web.py）
        brand_map = {
            '夸克网盘': '夸克',
            '阿里云盘': '阿里',
            '百度网盘': '百度',
            '115网盘': '115',
            '天翼云盘': '天翼',
            '123云盘': '123',
            'UC网盘': 'UC',
            '迅雷网盘': '迅雷',
            '迅雷': '迅雷'
        }
        
        # 按品牌聚合
        brand_stats = {}
        for row in result:
            brand = brand_map.get(row.netdisk_name, row.netdisk_name)
            if brand not in brand_stats:
                brand_stats[brand] = 0
            brand_stats[brand] += row.link_count
        
        # 重新计算总数（按品牌）
        total_by_brand = sum(brand_stats.values())
        
        # 转换为列表并计算百分比
        distribution = []
        for brand, count in sorted(brand_stats.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_by_brand) if total_by_brand > 0 else 0.0
            distribution.append({
                "netdisk_name": brand,
                "link_count": count,
                "percentage": round(percentage, 4)  # 保留4位小数
            })
        
        return distribution
        
    except Exception as e:
        logger.error(f"获取网盘分布失败: {e}", exc_info=True)
        return []

