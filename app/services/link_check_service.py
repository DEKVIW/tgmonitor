"""
Link check service used by the admin backend.
"""

import json
import logging
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.models import LinkCheckDetails, LinkCheckStats, Message, engine

logger = logging.getLogger(__name__)

_task_status: Dict[str, Dict[str, Any]] = {}
_task_status_lock = threading.RLock()
TASK_STATUS_DIR = Path(__file__).resolve().parents[2] / "data" / "runtime" / "link_check_tasks"

try:
    from app.scripts.link_validator import LinkValidator

    LINK_VALIDATOR_AVAILABLE = True
except ImportError:
    try:
        from link_validator import LinkValidator

        LINK_VALIDATOR_AVAILABLE = True
    except ImportError:
        LINK_VALIDATOR_AVAILABLE = False
        logger.warning("link_validator.py not found, link check is unavailable")


def extract_urls(links: Any) -> List[str]:
    urls: List[str] = []
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


def parse_time_period(period_str: str) -> Tuple[datetime, datetime, str]:
    now = datetime.now()
    period_str = period_str.lower().strip()

    if period_str == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now
        period_desc = "今天"
    elif period_str == "yesterday":
        yesterday = now - timedelta(days=1)
        start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_desc = "昨天"
    elif period_str == "week":
        start_time = now - timedelta(days=7)
        end_time = now
        period_desc = "最近7天"
    elif period_str == "month":
        start_time = now - timedelta(days=30)
        end_time = now
        period_desc = "最近30天"
    elif period_str == "year":
        start_time = now - timedelta(days=365)
        end_time = now
        period_desc = "最近365天"
    elif ":" in period_str:
        parts = period_str.split(":")
        if len(parts) != 2:
            raise ValueError("日期范围格式错误")
        start_str, end_str = parts
        start_time = datetime.strptime(start_str.strip(), "%Y-%m-%d")
        end_time = datetime.strptime(end_str.strip(), "%Y-%m-%d") + timedelta(days=1)
        period_desc = f"{start_str} 至 {end_str}"
    elif len(period_str) == 10 and "-" in period_str:
        start_time = datetime.strptime(period_str, "%Y-%m-%d")
        end_time = start_time + timedelta(days=1)
        period_desc = period_str
    elif len(period_str) == 7 and "-" in period_str:
        start_time = datetime.strptime(period_str, "%Y-%m")
        if start_time.month == 12:
            end_time = datetime(start_time.year + 1, 1, 1)
        else:
            end_time = datetime(start_time.year, start_time.month + 1, 1)
        period_desc = period_str
    elif len(period_str) == 4:
        start_time = datetime(int(period_str), 1, 1)
        end_time = datetime(int(period_str) + 1, 1, 1)
        period_desc = period_str
    else:
        raise ValueError(f"无法解析时间段: {period_str}")

    return start_time, end_time, period_desc


def check_safety_limits(url_count: int, max_concurrent: int) -> bool:
    max_links = 1000
    max_concurrent_global = 10
    if url_count > max_links:
        return False
    if max_concurrent > max_concurrent_global:
        return False
    return True


def _build_task_status(period_desc: str, max_concurrent: int) -> Dict[str, Any]:
    return {
        "status": "running",
        "progress": 0,
        "period_desc": period_desc,
        "max_concurrent": max_concurrent,
        "total_links": 0,
        "checked_links": 0,
        "valid_links": 0,
        "invalid_links": 0,
        "logs": [],
    }


def _clone_task_status(status: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(status)


def _get_task_status_path(task_id: str) -> Path:
    return TASK_STATUS_DIR / f"{task_id}.json"


def _persist_task_status(task_id: str, status: Dict[str, Any]) -> None:
    path = _get_task_status_path(task_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        payload = json.dumps(status, ensure_ascii=False, separators=(",", ":"))
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, path)
    except OSError as exc:
        logger.warning("Failed to persist link check task status for %s: %s", task_id, exc)


def _load_persisted_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    path = _get_task_status_path(task_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read persisted link check task status for %s: %s", task_id, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Ignoring invalid persisted link check task status for %s", task_id)
        return None
    return payload


def _ensure_task_status(task_id: str, period_str: str, max_concurrent: int) -> Dict[str, Any]:
    with _task_status_lock:
        status = _task_status.get(task_id)
        if status is None:
            status = _load_persisted_task_status(task_id)
        if status is None:
            try:
                _, _, period_desc = parse_time_period(period_str)
            except Exception:
                period_desc = period_str
            status = _build_task_status(period_desc, max_concurrent)
            _task_status[task_id] = status
            _persist_task_status(task_id, status)
        elif task_id not in _task_status:
            _task_status[task_id] = status
        return _clone_task_status(status)


def _update_task_status(task_id: str, **fields: Any) -> Dict[str, Any]:
    with _task_status_lock:
        status = _task_status.get(task_id) or _load_persisted_task_status(task_id) or {}
        status.update(fields)
        _task_status[task_id] = status
        snapshot = _clone_task_status(status)
        _persist_task_status(task_id, snapshot)
        return snapshot


def init_task_status(task_id: str, period_str: str, max_concurrent: int) -> Dict[str, Any]:
    try:
        _, _, period_desc = parse_time_period(period_str)
    except Exception:
        period_desc = period_str

    status = _build_task_status(period_desc, max_concurrent)
    with _task_status_lock:
        _task_status[task_id] = status
        snapshot = _clone_task_status(status)
        _persist_task_status(task_id, snapshot)
        return snapshot


async def run_link_check_task(task_id: str, period_str: str, max_concurrent: int):
    _ensure_task_status(task_id, period_str, max_concurrent)

    if not LINK_VALIDATOR_AVAILABLE:
        _update_task_status(
            task_id,
            status="failed",
            error="链接检测功能不可用，请确认 link_validator.py 存在",
            progress=0,
        )
        return

    try:
        start_time, end_time, period_desc = parse_time_period(period_str)
        _update_task_status(
            task_id,
            status="running",
            period_desc=period_desc,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            max_concurrent=max_concurrent,
            logs=[],
        )

        with Session(engine) as session:
            messages = (
                session.query(Message)
                .filter(
                    Message.timestamp >= start_time,
                    Message.timestamp < end_time,
                    Message.links.isnot(None),
                )
                .all()
            )

        if not messages:
            _update_task_status(
                task_id,
                status="completed",
                progress=100,
                error="没有找到需要检测的消息",
                total_links=0,
                checked_links=0,
                valid_links=0,
                invalid_links=0,
            )
            return

        link_records: List[Dict[str, Any]] = []
        for msg in messages:
            for url in extract_urls(msg.links):
                if isinstance(url, str) and url.strip():
                    link_records.append({"message_id": msg.id, "url": url.strip()})

        if not link_records:
            _update_task_status(
                task_id,
                status="completed",
                progress=100,
                error="没有找到需要检测的链接",
                total_links=0,
                checked_links=0,
                valid_links=0,
                invalid_links=0,
            )
            return

        all_urls = [record["url"] for record in link_records]
        if not check_safety_limits(len(all_urls), max_concurrent):
            _update_task_status(
                task_id,
                status="failed",
                error=f"链接数量 ({len(all_urls)}) 或并发数 ({max_concurrent}) 超过安全限制",
                progress=0,
            )
            return

        _update_task_status(
            task_id,
            total_links=len(all_urls),
            logs=[f"开始检测 {len(all_urls)} 个链接"],
        )

        validator = LinkValidator()
        validator.result_cache.clear()
        check_start_time = time.time()

        async def progress_callback(checked: int, total: int, valid: int, invalid: int) -> None:
            progress = int((checked / total) * 100) if total > 0 else 0
            _update_task_status(
                task_id,
                progress=progress,
                checked_links=checked,
                valid_links=valid,
                invalid_links=invalid,
            )

        if hasattr(validator, "check_multiple_links_with_progress"):
            results = await validator.check_multiple_links_with_progress(
                all_urls,
                max_concurrent=max_concurrent,
                progress_callback=progress_callback,
            )
        else:
            results = await validator.check_multiple_links(all_urls, max_concurrent)
            await progress_callback(
                len(results),
                len(results),
                sum(1 for result in results if result.get("is_valid")),
                sum(1 for result in results if not result.get("is_valid")),
            )

        summary = validator.get_summary(results)
        check_duration = time.time() - check_start_time
        check_time = datetime.now()

        with Session(engine) as session:
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary["valid_links"],
                invalid_links=summary["invalid_links"],
                netdisk_stats=summary["netdisk_stats"],
                check_duration=check_duration,
                status="completed",
            )
            session.add(stats)
            session.commit()

            for record, result in zip(link_records, results):
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=record["message_id"],
                    netdisk_type=result.get("netdisk_type", "unknown"),
                    url=result.get("url", record["url"]),
                    is_valid=result.get("is_valid", False),
                    response_time=result.get("response_time", 0),
                    error_reason=result.get("error") or result.get("reason"),
                    action_taken=result.get("status", "none"),
                )
                session.add(detail)

            session.commit()

        current_status = get_task_status(task_id) or {}
        logs = list(current_status.get("logs") or [])
        logs.append(f"检测完成，有效 {summary['valid_links']}，无效 {summary['invalid_links']}")
        _update_task_status(
            task_id,
            status="completed",
            progress=100,
            checked_links=len(all_urls),
            valid_links=summary["valid_links"],
            invalid_links=summary["invalid_links"],
            check_time=check_time.isoformat(),
            duration=check_duration,
            logs=logs,
        )
    except Exception as e:
        logger.error(f"链接检测任务失败: {e}", exc_info=True)
        current_status = get_task_status(task_id) or {}
        _update_task_status(
            task_id,
            status="failed",
            error=str(e),
            progress=current_status.get("progress", 0),
        )


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    persisted_status = _load_persisted_task_status(task_id)
    with _task_status_lock:
        if persisted_status is not None:
            _task_status[task_id] = persisted_status
            return _clone_task_status(persisted_status)

        status = _task_status.get(task_id)
        return _clone_task_status(status) if status is not None else None


def get_task_history(limit: int = 20) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        stats = (
            session.query(LinkCheckStats)
            .order_by(LinkCheckStats.check_time.desc())
            .limit(limit)
            .all()
        )

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


def get_link_check_date_range() -> Dict[str, Optional[str]]:
    with Session(engine) as session:
        earliest_message = (
            session.query(Message)
            .order_by(Message.timestamp.asc())
            .first()
        )
        latest_message = (
            session.query(Message)
            .order_by(Message.timestamp.desc())
            .first()
        )

    return {
        "min_date": earliest_message.timestamp.date().isoformat() if earliest_message else None,
        "max_date": datetime.now().date().isoformat(),
        "latest_message_date": latest_message.timestamp.date().isoformat() if latest_message else None,
    }


def get_task_result(check_time_str: str) -> Dict[str, Any]:
    check_time = datetime.fromisoformat(check_time_str)

    with Session(engine) as session:
        stats = session.query(LinkCheckStats).filter(LinkCheckStats.check_time == check_time).first()
        if not stats:
            return {"error": "检测记录不存在"}

        details = (
            session.query(LinkCheckDetails)
            .filter(LinkCheckDetails.check_time == check_time)
            .limit(1000)
            .all()
        )

        return {
            "stats": {
                "check_time": stats.check_time.isoformat(),
                "total_messages": stats.total_messages,
                "total_links": stats.total_links,
                "valid_links": stats.valid_links,
                "invalid_links": stats.invalid_links,
                "updated_messages": stats.updated_messages,
                "deleted_messages": stats.deleted_messages,
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
                    "status": detail.action_taken,
                }
                for detail in details
            ],
        }


from app.services import link_check_runtime as _runtime
from app.services.link_check_runtime import (  # noqa: E402,F401
    ACTIVE_TASK_FILE,
    FINAL_TASK_STATUSES,
    LINK_VALIDATOR_AVAILABLE,
    MAX_LOG_LINES,
    RUNNING_TASK_STATUSES,
    TASK_STATUS_DIR,
    check_safety_limits,
    delete_task_history_entries,
    delete_task_history_entry,
    extract_urls,
    get_active_task_snapshot,
    get_link_check_date_range,
    get_task_history,
    get_task_result,
    get_task_status,
    init_task_status,
    parse_time_period,
    request_task_stop,
    run_link_check_task,
    should_stop_task,
    start_or_reuse_task,
)

_task_status = _runtime._task_status
_task_status_lock = _runtime._task_status_lock
