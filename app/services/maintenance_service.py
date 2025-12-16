"""
数据维护服务
复用 app/scripts/manage.py 中的逻辑
"""

import ast
import json
from sqlalchemy.orm import Session
from sqlalchemy import update, delete
from app.models.models import Message, LinkCheckStats, LinkCheckDetails, engine
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def extract_urls(links):
    """提取所有URL（复用manage.py中的函数）"""
    urls = []
    if isinstance(links, str):
        # 兼容老数据
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


def fix_tags(db: Session) -> Dict[str, Any]:
    """
    修复tags字段脏数据
    
    将字符串格式的tags转换为list格式
    """
    try:
        msgs = db.query(Message).all()
        fixed = 0
        errors = []
        
        for msg in msgs:
            if msg.tags is not None and not isinstance(msg.tags, list):
                try:
                    tags_fixed = ast.literal_eval(msg.tags)
                    if isinstance(tags_fixed, list):
                        db.execute(update(Message).where(Message.id == msg.id).values(tags=tags_fixed))
                        fixed += 1
                except Exception as e:
                    errors.append(f"ID={msg.id}: {str(e)}")
                    logger.error(f"ID={msg.id} tags修复失败: {e}")
        
        db.commit()
        
        return {
            "success": True,
            "fixed_count": fixed,
            "errors": errors
        }
    except Exception as e:
        db.rollback()
        logger.error(f"修复tags失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def dedup_links(db: Session) -> Dict[str, Any]:
    """
    链接去重
    
    相同链接且时间间隔5分钟内，优先保留网盘链接多的，否则保留最新的
    """
    try:
        all_msgs = db.query(Message).order_by(Message.timestamp.desc()).all()
        link_to_id = {}  # {url: 最新消息id}
        id_to_delete = set()
        id_to_msg = {}  # {id: msg对象}
        
        for msg in all_msgs:
            links = msg.links
            if isinstance(links, str):
                try:
                    links = json.loads(links)
                except Exception as e:
                    logger.error(f"ID={msg.id} links解析失败: {e}")
                    continue
            
            if not links:
                continue
            
            for url in extract_urls(links):
                if not isinstance(url, str):
                    continue
                url = url.strip().lower()
                
                if url in link_to_id:
                    old_id = link_to_id[url]
                    old_msg = id_to_msg[old_id]
                    time_diff = abs((msg.timestamp - old_msg.timestamp).total_seconds())
                    
                    if time_diff < 300:  # 5分钟内
                        # 优先保留links多的
                        if len(extract_urls(links)) > len(extract_urls(old_msg.links)):
                            id_to_delete.add(old_id)
                            link_to_id[url] = msg.id
                            id_to_msg[msg.id] = msg
                        else:
                            id_to_delete.add(msg.id)
                    else:
                        # 超过5分钟，保留最新的
                        id_to_delete.add(msg.id)
                else:
                    link_to_id[url] = msg.id
                    id_to_msg[msg.id] = msg
        
        deleted_count = 0
        if id_to_delete:
            deleted_count = db.query(Message).filter(Message.id.in_(id_to_delete)).delete(synchronize_session=False)
            db.commit()
        
        return {
            "success": True,
            "deleted_count": deleted_count
        }
    except Exception as e:
        db.rollback()
        logger.error(f"链接去重失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def clear_link_check_data(db: Session) -> Dict[str, Any]:
    """
    清空所有链接检测数据
    """
    try:
        # 删除详细记录
        details_count = db.query(LinkCheckDetails).delete()
        # 删除统计记录
        stats_count = db.query(LinkCheckStats).delete()
        
        db.commit()
        
        return {
            "success": True,
            "deleted_details": details_count,
            "deleted_stats": stats_count
        }
    except Exception as e:
        db.rollback()
        logger.error(f"清空链接检测数据失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def clear_old_link_check_data(db: Session, days: int = 30) -> Dict[str, Any]:
    """
    清空指定天数之前的链接检测数据
    """
    try:
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 删除详细记录
        details_count = db.query(LinkCheckDetails).filter(
            LinkCheckDetails.check_time < cutoff_time
        ).delete()
        
        # 删除统计记录
        stats_count = db.query(LinkCheckStats).filter(
            LinkCheckStats.check_time < cutoff_time
        ).delete()
        
        db.commit()
        
        return {
            "success": True,
            "deleted_details": details_count,
            "deleted_stats": stats_count,
            "cutoff_time": cutoff_time.isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"清空旧链接检测数据失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }

