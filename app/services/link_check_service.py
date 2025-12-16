"""
链接检测服务
复用 app/scripts/manage.py 和 app/scripts/link_validator.py 中的逻辑
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import Message, LinkCheckStats, LinkCheckDetails, engine
from app.models.config import settings
import logging

logger = logging.getLogger(__name__)

# 任务状态存储（内存，生产环境建议用Redis）
_task_status: Dict[str, Dict[str, Any]] = {}

# 尝试导入LinkValidator
try:
    from app.scripts.link_validator import LinkValidator
    LINK_VALIDATOR_AVAILABLE = True
except ImportError:
    try:
        from link_validator import LinkValidator
        LINK_VALIDATOR_AVAILABLE = True
    except ImportError:
        LINK_VALIDATOR_AVAILABLE = False
        logger.warning("link_validator.py 未找到，链接检测功能不可用")


def extract_urls(links):
    """提取所有URL（复用manage.py中的函数）"""
    urls = []
    if isinstance(links, str):
        urls.append(links)
    elif isinstance(links, dict):
        for v in links.values():
            urls.extend(extract_urls(v))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and 'url' in item:
                urls.append(item['url'])
            else:
                urls.extend(extract_urls(item))
    return urls


def parse_time_period(period_str: str) -> tuple:
    """解析时间段字符串，返回开始和结束时间"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    period_str = period_str.lower().strip()
    
    if period_str == 'today':
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now
        period_desc = '今天'
    elif period_str == 'yesterday':
        yesterday = now - timedelta(days=1)
        start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_desc = '昨天'
    elif period_str == 'week':
        start_time = now - timedelta(days=7)
        end_time = now
        period_desc = '最近7天'
    elif period_str == 'month':
        start_time = now - timedelta(days=30)
        end_time = now
        period_desc = '最近30天'
    elif period_str == 'year':
        start_time = now - timedelta(days=365)
        end_time = now
        period_desc = '最近365天'
    elif ':' in period_str:
        # 日期范围格式：2024-01-15:2024-01-20
        parts = period_str.split(':')
        if len(parts) == 2:
            start_str, end_str = parts
            start_time = datetime.strptime(start_str.strip(), '%Y-%m-%d')
            end_time = datetime.strptime(end_str.strip(), '%Y-%m-%d') + timedelta(days=1)
            period_desc = f'{start_str} 至 {end_str}'
        else:
            raise ValueError("日期范围格式错误")
    elif len(period_str) == 10 and '-' in period_str:
        # 单个日期：2024-01-15
        start_time = datetime.strptime(period_str, '%Y-%m-%d')
        end_time = start_time + timedelta(days=1)
        period_desc = period_str
    elif len(period_str) == 7 and '-' in period_str:
        # 月份：2024-01
        start_time = datetime.strptime(period_str, '%Y-%m')
        if start_time.month == 12:
            end_time = datetime(start_time.year + 1, 1, 1)
        else:
            end_time = datetime(start_time.year, start_time.month + 1, 1)
        period_desc = period_str
    elif len(period_str) == 4:
        # 年份：2024
        start_time = datetime(int(period_str), 1, 1)
        end_time = datetime(int(period_str) + 1, 1, 1)
        period_desc = period_str
    else:
        raise ValueError(f"无法解析时间段: {period_str}")
    
    return start_time, end_time, period_desc


def check_safety_limits(url_count: int, max_concurrent: int) -> bool:
    """检查安全限制"""
    max_links = 1000
    max_concurrent_global = 10
    
    if url_count > max_links:
        return False
    if max_concurrent > max_concurrent_global:
        return False
    return True


async def run_link_check_task(
    task_id: str,
    period_str: str,
    max_concurrent: int
):
    """
    运行链接检测任务（异步）
    
    Args:
        task_id: 任务ID
        period_str: 时间段字符串
        max_concurrent: 最大并发数
    """
    if not LINK_VALIDATOR_AVAILABLE:
        _task_status[task_id] = {
            "status": "failed",
            "error": "链接检测功能不可用，请确保 link_validator.py 存在",
            "progress": 0
        }
        return
    
    try:
        # 解析时间段
        start_time, end_time, period_desc = parse_time_period(period_str)
        
        # 更新任务状态
        _task_status[task_id] = {
            "status": "running",
            "progress": 0,
            "period_desc": period_desc,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "max_concurrent": max_concurrent,
            "total_links": 0,
            "checked_links": 0,
            "valid_links": 0,
            "invalid_links": 0,
            "logs": []
        }
        
        # 获取消息
        with Session(engine) as session:
            messages = session.query(Message).filter(
                Message.timestamp >= start_time,
                Message.timestamp < end_time,
                Message.links.isnot(None)
            ).all()
        
        if not messages:
            _task_status[task_id] = {
                "status": "completed",
                "progress": 100,
                "error": "没有找到需要检测的消息",
                "total_links": 0
            }
            return
        
        # 提取链接
        all_urls = []
        for msg in messages:
            urls = extract_urls(msg.links)
            if urls:
                all_urls.extend(urls)
        
        if not all_urls:
            _task_status[task_id] = {
                "status": "completed",
                "progress": 100,
                "error": "没有找到需要检测的链接",
                "total_links": 0
            }
            return
        
        # 安全检查
        if not check_safety_limits(len(all_urls), max_concurrent):
            _task_status[task_id] = {
                "status": "failed",
                "error": f"链接数量 ({len(all_urls)}) 或并发数 ({max_concurrent}) 超过安全限制",
                "progress": 0
            }
            return
        
        # 更新任务状态
        _task_status[task_id]["total_links"] = len(all_urls)
        _task_status[task_id]["logs"].append(f"开始检测 {len(all_urls)} 个链接...")
        
        # 开始检测
        validator = LinkValidator()
        check_start_time = time.time()
        
        # 使用回调更新进度
        async def progress_callback(checked: int, total: int, valid: int, invalid: int):
            progress = int((checked / total) * 100) if total > 0 else 0
            _task_status[task_id].update({
                "progress": progress,
                "checked_links": checked,
                "valid_links": valid,
                "invalid_links": invalid,
            })
        
        # 检测链接（简化版，实际需要修改LinkValidator支持进度回调）
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 计算统计
        summary = validator.get_summary(results)
        check_duration = time.time() - check_start_time
        
        # 保存结果到数据库
        check_time = datetime.now()
        with Session(engine) as session:
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=check_duration,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,
                    netdisk_type=result.get('netdisk_type', 'unknown'),
                    url=result.get('url', ''),
                    is_valid=result.get('is_valid', False),
                    response_time=result.get('response_time', 0),
                    error_reason=result.get('error')
                )
                session.add(detail)
            
            session.commit()
        
        # 更新任务状态
        _task_status[task_id].update({
            "status": "completed",
            "progress": 100,
            "checked_links": len(all_urls),
            "valid_links": summary['valid_links'],
            "invalid_links": summary['invalid_links'],
            "check_time": check_time.isoformat(),
            "duration": check_duration,
            "logs": _task_status[task_id]["logs"] + [f"检测完成！有效: {summary['valid_links']}, 无效: {summary['invalid_links']}"]
        })
        
    except Exception as e:
        logger.error(f"链接检测任务失败: {e}", exc_info=True)
        _task_status[task_id] = {
            "status": "failed",
            "error": str(e),
            "progress": _task_status.get(task_id, {}).get("progress", 0)
        }


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务状态"""
    return _task_status.get(task_id)


def get_task_history(limit: int = 20) -> List[Dict[str, Any]]:
    """获取任务历史（从数据库）"""
    with Session(engine) as session:
        stats = session.query(LinkCheckStats).order_by(
            LinkCheckStats.check_time.desc()
        ).limit(limit).all()
        
        return [
            {
                "id": stat.id,
                "check_time": stat.check_time.isoformat(),
                "total_messages": stat.total_messages,
                "total_links": stat.total_links,
                "valid_links": stat.valid_links,
                "invalid_links": stat.invalid_links,
                "status": stat.status,
                "duration": stat.check_duration,
            }
            for stat in stats
        ]


def get_task_result(check_time_str: str) -> Dict[str, Any]:
    """获取检测结果详情"""
    check_time = datetime.fromisoformat(check_time_str)
    
    with Session(engine) as session:
        # 获取统计
        stats = session.query(LinkCheckStats).filter(
            LinkCheckStats.check_time == check_time
        ).first()
        
        if not stats:
            return {"error": "检测记录不存在"}
        
        # 获取详细结果
        details = session.query(LinkCheckDetails).filter(
            LinkCheckDetails.check_time == check_time
        ).limit(1000).all()
        
        return {
            "stats": {
                "check_time": stats.check_time.isoformat(),
                "total_messages": stats.total_messages,
                "total_links": stats.total_links,
                "valid_links": stats.valid_links,
                "invalid_links": stats.invalid_links,
                "netdisk_stats": stats.netdisk_stats,
                "duration": stats.check_duration,
                "status": stats.status,
            },
            "details": [
                {
                    "url": detail.url,
                    "netdisk_type": detail.netdisk_type,
                    "is_valid": detail.is_valid,
                    "response_time": detail.response_time,
                    "error_reason": detail.error_reason,
                }
                for detail in details
            ]
        }

