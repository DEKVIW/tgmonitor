"""
Maintenance helpers used by the admin backend.
"""

import ast
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.models import LinkCheckDetails, LinkCheckStats, Message

logger = logging.getLogger(__name__)


def extract_urls(links: Any):
    urls = []
    if isinstance(links, str):
        urls.append(links)
    elif isinstance(links, dict):
        for value in links.values():
            urls.extend(extract_urls(value))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and "url" in item:
                urls.append(item["url"])
            else:
                urls.extend(extract_urls(item))
    return urls


def normalize_links(links: Any) -> Any:
    if isinstance(links, str):
        try:
            return json.loads(links)
        except Exception:
            return links
    return links


def fix_tags(db: Session) -> Dict[str, Any]:
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
        return {"success": True, "fixed_count": fixed, "errors": errors}
    except Exception as e:
        db.rollback()
        logger.error(f"修复 tags 失败: {e}")
        return {"success": False, "error": str(e)}


def dedup_links(db: Session) -> Dict[str, Any]:
    try:
        all_msgs = db.query(Message).order_by(Message.timestamp.desc()).all()
        link_to_id = {}
        id_to_delete = set()
        id_to_msg = {}

        for msg in all_msgs:
            links = normalize_links(msg.links)
            if isinstance(links, str) or not links:
                continue

            current_urls = extract_urls(links)
            for url in current_urls:
                if not isinstance(url, str):
                    continue
                normalized_url = url.strip().lower()

                if normalized_url in link_to_id:
                    old_id = link_to_id[normalized_url]
                    old_msg = id_to_msg[old_id]
                    old_links = normalize_links(old_msg.links)
                    old_urls = extract_urls(old_links)
                    time_diff = abs((msg.timestamp - old_msg.timestamp).total_seconds())

                    if time_diff < 300:
                        if len(current_urls) > len(old_urls):
                            id_to_delete.add(old_id)
                            link_to_id[normalized_url] = msg.id
                            id_to_msg[msg.id] = msg
                        else:
                            id_to_delete.add(msg.id)
                    else:
                        id_to_delete.add(msg.id)
                else:
                    link_to_id[normalized_url] = msg.id
                    id_to_msg[msg.id] = msg

        deleted_count = 0
        if id_to_delete:
            deleted_count = (
                db.query(Message)
                .filter(Message.id.in_(id_to_delete))
                .delete(synchronize_session=False)
            )
            db.commit()

        return {"success": True, "deleted_count": deleted_count}
    except Exception as e:
        db.rollback()
        logger.error(f"链接去重失败: {e}")
        return {"success": False, "error": str(e)}


def clear_link_check_data(db: Session) -> Dict[str, Any]:
    try:
        details_count = db.query(LinkCheckDetails).delete()
        stats_count = db.query(LinkCheckStats).delete()
        db.commit()
        return {
            "success": True,
            "deleted_details": details_count,
            "deleted_stats": stats_count,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"清空链接检测数据失败: {e}")
        return {"success": False, "error": str(e)}


def clear_old_link_check_data(db: Session, days: int = 30) -> Dict[str, Any]:
    try:
        cutoff_time = datetime.now() - timedelta(days=days)
        details_count = (
            db.query(LinkCheckDetails)
            .filter(LinkCheckDetails.check_time < cutoff_time)
            .delete()
        )
        stats_count = (
            db.query(LinkCheckStats)
            .filter(LinkCheckStats.check_time < cutoff_time)
            .delete()
        )
        db.commit()
        return {
            "success": True,
            "deleted_details": details_count,
            "deleted_stats": stats_count,
            "cutoff_time": cutoff_time.isoformat(),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"清空旧链接检测数据失败: {e}")
        return {"success": False, "error": str(e)}
