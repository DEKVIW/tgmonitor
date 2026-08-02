"""Runtime service helpers for admin link check tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.monitor_parser import normalize_url
from app.models.models import LinkCheckDetails, LinkCheckPlan, LinkCheckStats, Message, engine
from app.services.system_config_service import get_link_check_runtime_config

logger = logging.getLogger(__name__)

TASK_STATUS_DIR = Path(__file__).resolve().parents[2] / "data" / "runtime" / "link_check_tasks"
ACTIVE_TASK_FILE = TASK_STATUS_DIR / "_active_task.json"
MAX_LOG_LINES = 800
DEFAULT_MAX_LINKS_PER_TASK = 5000
DEFAULT_MAX_CONCURRENT_PER_TASK = 10
MAX_URL_LOG_LENGTH = 96
ACTIVE_TASK_STALE_SECONDS = 30 * 60
RUNNING_TASK_STATUSES = {"running", "stopping"}
FINAL_TASK_STATUSES = {"completed", "failed", "stopped"}

_task_status: Dict[str, Dict[str, Any]] = {}
_task_status_lock = threading.RLock()
_dispatch_lock = threading.RLock()
_active_task_threads: set[str] = set()

try:
    from app.services.link_check.validator import LinkCheckStopped, LinkValidator

    LINK_VALIDATOR_AVAILABLE = True
except ImportError:
    try:
        from app.scripts.link_validator import LinkValidator  # type: ignore

        class LinkCheckStopped(RuntimeError):
            """Fallback stop exception used by the legacy validator."""

        LINK_VALIDATOR_AVAILABLE = True
    except ImportError:
        LINK_VALIDATOR_AVAILABLE = False
        logger.warning("link validator is unavailable")


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
    period_str = (period_str or "").lower().strip()

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
        start_str, end_str = [part.strip() for part in period_str.split(":", 1)]
        if not start_str or not end_str:
            raise ValueError("日期范围格式错误")
        start_time = datetime.strptime(start_str, "%Y-%m-%d")
        end_time = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
        if end_time <= start_time:
            raise ValueError("结束日期必须晚于开始日期")
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
    elif len(period_str) == 4 and period_str.isdigit():
        year = int(period_str)
        start_time = datetime(year, 1, 1)
        end_time = datetime(year + 1, 1, 1)
        period_desc = period_str
    else:
        raise ValueError(f"无法解析时间段: {period_str}")

    return start_time, end_time, period_desc


def check_safety_limits(url_count: int, max_concurrent: int) -> bool:
    return get_safety_limit_error(url_count, max_concurrent) is None


def get_safety_limit_error(url_count: int, max_concurrent: int) -> Optional[str]:
    runtime_config = get_link_check_runtime_config()
    max_links_per_task = max(
        100,
        int(runtime_config["link_check_max_allowed_links"] or DEFAULT_MAX_LINKS_PER_TASK),
    )
    max_concurrent_per_task = max(
        1,
        int(runtime_config["link_check_max_allowed_concurrent"] or DEFAULT_MAX_CONCURRENT_PER_TASK),
    )
    violations: List[str] = []
    if url_count > max_links_per_task:
        violations.append(
            f"链接数量 {url_count} 超过安全上限 {max_links_per_task}，请缩小时间范围后重试"
        )
    if max_concurrent > max_concurrent_per_task:
        violations.append(
            f"并发数 {max_concurrent} 超过安全上限 {max_concurrent_per_task}，请降低并发后重试"
        )
    if not violations:
        return None
    return "；".join(violations)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _make_log_line(message: str) -> str:
    return f"[{datetime.now().strftime('%H:%M:%S')}] {message}"


def _truncate_url(url: Optional[str], max_length: int = MAX_URL_LOG_LENGTH) -> str:
    value = str(url or "").strip()
    if not value:
        return "-"
    if len(value) <= max_length:
        return value
    keep = max(12, (max_length - 3) // 2)
    return f"{value[:keep]}...{value[-keep:]}"


def _describe_result_status(status: Optional[str], is_valid: bool) -> str:
    status_key = str(status or "").strip().lower()
    mapping = {
        "valid": "有效",
        "invalid": "失效",
        "uncertain": "结果不确定",
        "rate_limited": "被限流",
        "requires_code": "需要提取码",
        "format_error": "格式错误",
        "unsupported": "暂不支持",
    }
    if status_key in mapping:
        return mapping[status_key]
    return "有效" if is_valid else "失效"


def _format_link_result_log(event: Dict[str, Any]) -> str:
    source_label = {
        "network": "实测",
        "cache": "缓存",
        "history": "历史复用",
    }.get(str(event.get("source") or ""), "检测")
    platform = str(event.get("platform") or "未知网盘")
    checked = int(event.get("checked") or 0)
    total = int(event.get("total") or 0)
    verdict = _describe_result_status(
        str(event.get("status") or ""),
        bool(event.get("is_valid")),
    )
    url = _truncate_url(event.get("url"))

    response_time = event.get("response_time")
    response_text = ""
    if isinstance(response_time, (int, float)) and response_time > 0:
        response_text = f"，{response_time:.2f} 秒"

    reason = str(event.get("error") or event.get("reason") or "").strip()
    reason_text = f"，{reason}" if reason and verdict != "有效" else ""

    return f"[{source_label}] {checked}/{total} {platform} {url} -> {verdict}{response_text}{reason_text}"


def _build_task_status(
    period_desc: str,
    max_concurrent: int,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now_iso = _now_iso()
    metadata = dict(task_metadata or {})
    return {
        "status": "running",
        "progress": 0,
        "period_desc": period_desc,
        "scope_label": str(metadata.get("scope_label") or period_desc),
        "trigger_source": str(metadata.get("trigger_source") or "manual"),
        "task_mode": str(metadata.get("task_mode") or "time_range"),
        "plan_id": metadata.get("plan_id"),
        "plan_name": metadata.get("plan_name"),
        "plan_mode": metadata.get("plan_mode"),
        "max_concurrent": max_concurrent,
        "total_messages": 0,
        "total_links": 0,
        "checked_links": 0,
        "valid_links": 0,
        "invalid_links": 0,
        "started_at": now_iso,
        "updated_at": now_iso,
        "current_phase": "queued",
        "current_platform": None,
        "stop_requested": False,
        "status_counts": {},
        "logs": [_make_log_line("任务已创建，等待开始检测")],
        "error": None,
    }


def _clone_task_status(status: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(status)


def _get_task_status_path(task_id: str) -> Path:
    return TASK_STATUS_DIR / f"{task_id}.json"


def _persist_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _persist_task_status(task_id: str, status: Dict[str, Any]) -> None:
    try:
        _persist_json(_get_task_status_path(task_id), status)
    except OSError as exc:
        logger.warning("failed to persist task status for %s: %s", task_id, exc)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to load json file %s: %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _load_persisted_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    return _load_json(_get_task_status_path(task_id))


def _persist_active_task(task_id: str) -> None:
    try:
        _persist_json(
            ACTIVE_TASK_FILE,
            {
                "task_id": task_id,
                "updated_at": _now_iso(),
                "owner_pid": os.getpid(),
            },
        )
    except OSError as exc:
        logger.warning("failed to persist active task: %s", exc)


def _load_active_task_payload() -> Optional[Dict[str, Any]]:
    payload = _load_json(ACTIVE_TASK_FILE)
    if not payload:
        return None
    return payload


def _load_active_task_id() -> Optional[str]:
    payload = _load_active_task_payload()
    if not payload:
        return None
    task_id = str(payload.get("task_id") or "").strip()
    return task_id or None


def _clear_active_task(task_id: Optional[str] = None) -> None:
    payload = _load_active_task_payload()
    current_task_id = str((payload or {}).get("task_id") or "").strip()
    if task_id is not None and current_task_id and current_task_id != task_id:
        return
    try:
        ACTIVE_TASK_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("failed to clear active task marker: %s", exc)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_active_task_stale(status: Dict[str, Any]) -> bool:
    timestamp = _parse_iso_datetime(status.get("updated_at")) or _parse_iso_datetime(status.get("started_at"))
    if timestamp is None:
        return True
    return datetime.now() - timestamp > timedelta(seconds=ACTIVE_TASK_STALE_SECONDS)


def _recover_stale_active_task(
    task_id: str,
    status: Dict[str, Any],
    active_payload: Optional[Dict[str, Any]],
) -> bool:
    if task_id in _active_task_threads:
        return False

    owner_pid: Optional[int] = None
    raw_owner_pid = (active_payload or {}).get("owner_pid")
    try:
        owner_pid = int(raw_owner_pid) if raw_owner_pid is not None else None
    except (TypeError, ValueError):
        owner_pid = None

    owner_missing = owner_pid is not None and not _pid_exists(owner_pid)
    status_stale = _is_active_task_stale(status)
    legacy_stale = owner_pid is None and status_stale
    if not owner_missing and not legacy_stale:
        return False

    reason = "owner process is gone" if owner_missing else "legacy status heartbeat is stale"
    logger.warning("recovering stale link check task task_id=%s reason=%s", task_id, reason)
    _update_task_status(
        task_id,
        status="stopped",
        current_phase="stopped",
        stop_requested=True,
        error=f"stale active task recovered: {reason}",
        append_log=f"[system] Stale active task recovered: {reason}",
    )
    _clear_active_task(task_id)
    return True


def _normalize_logs(logs: Optional[List[str]]) -> List[str]:
    normalized = [str(item) for item in (logs or []) if str(item).strip()]
    if len(normalized) > MAX_LOG_LINES:
        return normalized[-MAX_LOG_LINES:]
    return normalized


def _ensure_task_status(
    task_id: str,
    period_str: str,
    max_concurrent: int,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    with _task_status_lock:
        status = _task_status.get(task_id) or _load_persisted_task_status(task_id)
        if status is None:
            status = _build_task_status(period_str, max_concurrent, task_metadata=task_metadata)
            _task_status[task_id] = status
            _persist_task_status(task_id, status)
        elif task_id not in _task_status:
            _task_status[task_id] = status
        return _clone_task_status(status)


def _update_task_status(task_id: str, append_log: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
    with _task_status_lock:
        status = _task_status.get(task_id) or _load_persisted_task_status(task_id) or {}
        logs = _normalize_logs(status.get("logs"))
        if append_log:
            logs.append(_make_log_line(append_log))
            logs = _normalize_logs(logs)
        status.update(fields)
        status["logs"] = logs
        status["updated_at"] = _now_iso()
        _task_status[task_id] = status
        snapshot = _clone_task_status(status)
        _persist_task_status(task_id, snapshot)
        return snapshot


def init_task_status(
    task_id: str,
    period_str: str,
    max_concurrent: int,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status = _build_task_status(period_str, max_concurrent, task_metadata=task_metadata)
    with _task_status_lock:
        _task_status[task_id] = status
        snapshot = _clone_task_status(status)
        _persist_task_status(task_id, snapshot)
        return snapshot


def start_or_reuse_task(
    period_str: str,
    max_concurrent: int,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], bool]:
    active_snapshot = get_active_task_snapshot()
    if active_snapshot is not None:
        task_id, status = active_snapshot
        status["reused_existing"] = True
        return task_id, status, False

    task_id = str(uuid.uuid4())
    initial_status = init_task_status(task_id, period_str, max_concurrent, task_metadata=task_metadata)
    _persist_active_task(task_id)
    return task_id, initial_status, True


def dispatch_task(task_id: str, task_payload: Any, max_concurrent: int) -> bool:
    with _dispatch_lock:
        if task_id in _active_task_threads:
            return False
        _active_task_threads.add(task_id)

    worker = threading.Thread(
        target=_run_task_thread,
        args=(task_id, task_payload, max_concurrent),
        daemon=True,
        name=f"link-check-{task_id[:8]}",
    )
    worker.start()
    return True


def _run_task_thread(task_id: str, task_payload: Any, max_concurrent: int) -> None:
    try:
        if isinstance(task_payload, dict):
            asyncio.run(run_link_check_payload_task(task_id, task_payload, max_concurrent))
        else:
            asyncio.run(run_link_check_task(task_id, task_payload, max_concurrent))
    finally:
        with _dispatch_lock:
            _active_task_threads.discard(task_id)


def get_active_task_snapshot() -> Optional[Tuple[str, Dict[str, Any]]]:
    active_payload = _load_active_task_payload()
    task_id = str((active_payload or {}).get("task_id") or "").strip()
    if not task_id:
        return None

    status = get_task_status(task_id)
    if not status:
        _clear_active_task(task_id)
        return None

    if status.get("status") not in RUNNING_TASK_STATUSES:
        _clear_active_task(task_id)
        return None

    if _recover_stale_active_task(task_id, status, active_payload):
        return None

    return task_id, status


def request_task_stop(task_id: str) -> Optional[Dict[str, Any]]:
    current = get_task_status(task_id)
    if current is None:
        return None
    if current.get("status") in FINAL_TASK_STATUSES:
        return current
    return _update_task_status(
        task_id,
        status="stopping",
        stop_requested=True,
        current_phase=current.get("current_phase") or "stopping",
        append_log="收到停止请求，正在等待当前批次安全结束",
    )


def should_stop_task(task_id: str) -> bool:
    status = get_task_status(task_id) or {}
    return bool(status.get("stop_requested"))


def delete_task_history_entry(check_time_str: str) -> Dict[str, Any]:
    check_time = datetime.fromisoformat(check_time_str)
    with Session(engine) as session:
        details_deleted = (
            session.query(LinkCheckDetails)
            .filter(LinkCheckDetails.check_time == check_time)
            .delete(synchronize_session=False)
        )
        stats_deleted = (
            session.query(LinkCheckStats)
            .filter(LinkCheckStats.check_time == check_time)
            .delete(synchronize_session=False)
        )
        session.commit()

    if not details_deleted and not stats_deleted:
        raise LookupError("链接检测记录不存在")

    return {
        "success": True,
        "check_time": check_time.isoformat(),
        "deleted_details": int(details_deleted or 0),
        "deleted_stats": int(stats_deleted or 0),
    }


def delete_task_history_entries(check_time_strs: List[str]) -> Dict[str, Any]:
    normalized_check_times: List[str] = []
    seen: set[str] = set()
    for raw_value in check_time_strs:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        datetime.fromisoformat(value)
        normalized_check_times.append(value)
        seen.add(value)

    if not normalized_check_times:
        raise ValueError("至少提供一条检测历史时间")

    deleted_runs = 0
    deleted_details = 0
    deleted_stats = 0
    missing_check_times: List[str] = []

    with Session(engine) as session:
        for check_time_str in normalized_check_times:
            check_time = datetime.fromisoformat(check_time_str)
            current_deleted_details = (
                session.query(LinkCheckDetails)
                .filter(LinkCheckDetails.check_time == check_time)
                .delete(synchronize_session=False)
            )
            current_deleted_stats = (
                session.query(LinkCheckStats)
                .filter(LinkCheckStats.check_time == check_time)
                .delete(synchronize_session=False)
            )

            if current_deleted_details or current_deleted_stats:
                deleted_runs += 1
                deleted_details += int(current_deleted_details or 0)
                deleted_stats += int(current_deleted_stats or 0)
            else:
                missing_check_times.append(check_time_str)

        session.commit()

    if deleted_runs == 0:
        raise LookupError("链接检测记录不存在")

    return {
        "success": True,
        "requested_count": len(normalized_check_times),
        "deleted_runs": deleted_runs,
        "deleted_details": deleted_details,
        "deleted_stats": deleted_stats,
        "missing_check_times": missing_check_times,
    }


def _platform_counts(urls: List[str], validator: LinkValidator) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for url in urls:
        platform = validator.get_netdisk_type(url)
        counts[platform] = counts.get(platform, 0) + 1
    return counts


def _format_platform_counts(counts: Dict[str, int]) -> str:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return "，".join(f"{platform} {count}" for platform, count in ordered)


def _save_link_check_rows(
    *,
    check_time: datetime,
    message_count: int,
    link_records: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    summary: Dict[str, Any],
    check_duration: float,
    status: str,
    trigger_source: str,
    task_mode: str,
    scope_label: str,
    plan_id: Optional[int] = None,
) -> None:
    with Session(engine) as session:
        stats = LinkCheckStats(
            check_time=check_time,
            total_messages=message_count,
            total_links=len(link_records),
            valid_links=summary["valid_links"],
            invalid_links=summary["invalid_links"],
            netdisk_stats=summary["netdisk_stats"],
            check_duration=check_duration,
            status=status,
            trigger_source=trigger_source,
            task_mode=task_mode,
            scope_label=scope_label,
            plan_id=plan_id,
        )
        session.add(stats)
        session.commit()

        for record, result in zip(link_records, results):
            result_url = str(result.get("url", record["url"]) or record["url"]).strip()
            session.add(
                LinkCheckDetails(
                    check_time=check_time,
                    message_id=int(record["message_id"]),
                    netdisk_type=result.get("netdisk_type", "unknown"),
                    url=result_url,
                    normalized_url=normalize_url(result_url) or None,
                    is_valid=bool(result.get("is_valid", False)),
                    response_time=result.get("response_time", 0),
                    error_reason=result.get("error") or result.get("reason"),
                    action_taken=result.get("status", "none"),
                )
            )
        session.commit()


async def run_link_check_payload_task(task_id: str, task_request: Dict[str, Any], max_concurrent: int) -> None:
    scope_label = str(task_request.get("scope_label") or task_request.get("period_desc") or "自定义检测")
    trigger_source = str(task_request.get("trigger_source") or "manual")
    task_mode = str(task_request.get("task_mode") or task_request.get("selection_mode") or "smart_count")
    plan_id = int(task_request["plan_id"]) if task_request.get("plan_id") is not None else None
    link_records = [
        {
            "message_id": int(record["message_id"]),
            "url": str(record["url"]).strip(),
        }
        for record in list(task_request.get("link_records") or [])
        if str(record.get("url") or "").strip()
    ]
    message_count = int(task_request.get("total_messages") or len({record["message_id"] for record in link_records}))

    _ensure_task_status(
        task_id,
        scope_label,
        max_concurrent,
        task_metadata={
            "scope_label": scope_label,
            "trigger_source": trigger_source,
            "task_mode": task_mode,
        },
    )

    if not LINK_VALIDATOR_AVAILABLE:
        _update_task_status(
            task_id,
            status="failed",
            progress=0,
            current_phase="failed",
            error="链接检测组件不可用",
            append_log="链接检测组件加载失败",
        )
        _clear_active_task(task_id)
        return

    try:
        _persist_active_task(task_id)
        _update_task_status(
            task_id,
            status="running",
            period_desc=scope_label,
            scope_label=scope_label,
            trigger_source=trigger_source,
            task_mode=task_mode,
            start_time=task_request.get("start_time"),
            end_time=task_request.get("end_time"),
            max_concurrent=max_concurrent,
            current_phase="loading_messages",
            error=None,
            append_log=f"开始检测，范围：{scope_label}，并发：{max_concurrent}",
        )

        if should_stop_task(task_id):
            raise LinkCheckStopped("任务已停止")

        if not link_records:
            _update_task_status(
                task_id,
                status="completed",
                progress=100,
                current_phase="completed",
                total_messages=message_count,
                total_links=0,
                checked_links=0,
                valid_links=0,
                invalid_links=0,
                error="当前范围内没有可检测的网盘链接",
                append_log="没有找到可检测的网盘链接，任务结束",
            )
            _clear_active_task(task_id)
            return

        all_urls = [record["url"] for record in link_records]
        safety_limit_error = get_safety_limit_error(len(all_urls), max_concurrent)
        if safety_limit_error is not None:
            _update_task_status(
                task_id,
                status="failed",
                progress=0,
                current_phase="failed",
                error=safety_limit_error,
                append_log=f"任务被安全阈值阻止：{safety_limit_error}",
            )
            _clear_active_task(task_id)
            return

        validator = LinkValidator()
        validator.result_cache.clear()
        platform_counts = _platform_counts(all_urls, validator)
        _update_task_status(
            task_id,
            total_messages=message_count,
            total_links=len(all_urls),
            current_phase="checking_links",
            append_log=f"已命中 {message_count} 条消息，共提取 {len(all_urls)} 个链接",
        )
        if platform_counts:
            _update_task_status(task_id, append_log=f"平台分布：{_format_platform_counts(platform_counts)}")

        check_started_at = time.time()
        last_logged_checked = 0
        total_links = len(all_urls)

        async def result_callback(event: Dict[str, Any]) -> None:
            if should_stop_task(task_id):
                raise LinkCheckStopped("任务已停止")
            _update_task_status(
                task_id,
                current_phase="checking_links",
                current_platform=str(event.get("platform") or "未知平台"),
                append_log=_format_link_result_log(event),
            )

        async def progress_callback(checked: int, total: int, valid: int, invalid: int) -> None:
            nonlocal last_logged_checked
            if should_stop_task(task_id):
                raise LinkCheckStopped("任务已停止")

            progress = int((checked / total) * 100) if total > 0 else 0
            append_log = None
            if checked == total:
                append_log = f"检测完成，已处理 {checked}/{total} 个链接"
            elif checked - last_logged_checked >= max(10, total_links // 10):
                last_logged_checked = checked
                append_log = f"进度 {checked}/{total}，有效 {valid}，失效 {invalid}"

            _update_task_status(
                task_id,
                append_log=append_log,
                progress=progress,
                checked_links=checked,
                valid_links=valid,
                invalid_links=invalid,
                current_phase="checking_links",
            )

        results = await validator.check_multiple_links_with_progress(
            all_urls,
            max_concurrent=max_concurrent,
            progress_callback=progress_callback,
            result_callback=result_callback,
            should_stop=lambda: should_stop_task(task_id),
        )

        if should_stop_task(task_id):
            raise LinkCheckStopped("任务已停止")

        summary = validator.get_summary(results)
        check_duration = time.time() - check_started_at
        check_time = datetime.now()
        status_counts = summary.get("status_counts") or {}
        top_errors = Counter(
            (result.get("error") or result.get("reason") or "EMPTY")
            for result in results
            if not result.get("is_valid")
        ).most_common(8)

        _update_task_status(
            task_id,
            current_phase="saving_results",
            status_counts=status_counts,
            append_log=f"状态分布：{', '.join(f'{key}={value}' for key, value in sorted(status_counts.items())) or '无'}",
        )
        if top_errors:
            _update_task_status(
                task_id,
                append_log="主要失败原因：" + "，".join(f"{reason} x{count}" for reason, count in top_errors),
            )

        _save_link_check_rows(
            check_time=check_time,
            message_count=message_count,
            link_records=link_records,
            results=results,
            summary=summary,
            check_duration=check_duration,
            status="completed",
            trigger_source=trigger_source,
            task_mode=task_mode,
            scope_label=scope_label,
            plan_id=plan_id,
        )

        _update_task_status(
            task_id,
            status="completed",
            progress=100,
            current_phase="completed",
            checked_links=len(all_urls),
            valid_links=summary["valid_links"],
            invalid_links=summary["invalid_links"],
            check_time=check_time.isoformat(),
            duration=check_duration,
            status_counts=status_counts,
            append_log=f"任务完成，有效 {summary['valid_links']}，失效 {summary['invalid_links']}，耗时 {check_duration:.1f} 秒",
        )
    except LinkCheckStopped as exc:
        current_status = get_task_status(task_id) or {}
        _update_task_status(
            task_id,
            status="stopped",
            current_phase="stopped",
            error=str(exc),
            progress=current_status.get("progress", 0),
            append_log="任务已停止，未继续写入检测结果",
        )
    except Exception as exc:
        logger.error("custom link check task %s failed: %s", task_id, exc, exc_info=True)
        current_status = get_task_status(task_id) or {}
        _update_task_status(
            task_id,
            status="failed",
            current_phase="failed",
            error=str(exc),
            progress=current_status.get("progress", 0),
            append_log=f"任务失败：{exc}",
        )
    finally:
        final_status = get_task_status(task_id) or {}
        if final_status.get("status") in FINAL_TASK_STATUSES:
            _clear_active_task(task_id)


async def run_link_check_task(task_id: str, period_str: str, max_concurrent: int) -> None:
    _ensure_task_status(task_id, period_str, max_concurrent)

    if not LINK_VALIDATOR_AVAILABLE:
        _update_task_status(
            task_id,
            status="failed",
            progress=0,
            current_phase="failed",
            error="链接检测组件不可用",
            append_log="链接检测组件加载失败",
        )
        _clear_active_task(task_id)
        return

    try:
        start_time, end_time, period_desc = parse_time_period(period_str)
        _persist_active_task(task_id)
        _update_task_status(
            task_id,
            status="running",
            period_desc=period_desc,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            max_concurrent=max_concurrent,
            current_phase="loading_messages",
            error=None,
            append_log=f"开始检测，范围：{period_desc}，并发：{max_concurrent}",
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

        if should_stop_task(task_id):
            raise LinkCheckStopped("任务已停止")

        if not messages:
            _update_task_status(
                task_id,
                status="completed",
                progress=100,
                current_phase="completed",
                total_messages=0,
                total_links=0,
                checked_links=0,
                valid_links=0,
                invalid_links=0,
                error="没有找到需要检测的消息",
                append_log="未找到带链接的消息，任务结束",
            )
            _clear_active_task(task_id)
            return

        link_records: List[Dict[str, Any]] = []
        message_count = 0
        for msg in messages:
            urls = [url.strip() for url in extract_urls(msg.links) if isinstance(url, str) and url.strip()]
            if not urls:
                continue
            message_count += 1
            for url in urls:
                link_records.append({"message_id": msg.id, "url": url})

        if not link_records:
            _update_task_status(
                task_id,
                status="completed",
                progress=100,
                current_phase="completed",
                total_messages=message_count,
                total_links=0,
                checked_links=0,
                valid_links=0,
                invalid_links=0,
                error="没有提取到可检测链接",
                append_log="消息存在 links 字段，但未提取出有效 URL",
            )
            _clear_active_task(task_id)
            return

        all_urls = [record["url"] for record in link_records]
        safety_limit_error = get_safety_limit_error(len(all_urls), max_concurrent)
        if safety_limit_error is not None:
            _update_task_status(
                task_id,
                status="failed",
                progress=0,
                current_phase="failed",
                error=safety_limit_error,
                append_log=f"任务被安全限制拦截：{safety_limit_error}",
            )
            _clear_active_task(task_id)
            return

        validator = LinkValidator()
        validator.result_cache.clear()
        platform_counts = _platform_counts(all_urls, validator)
        _update_task_status(
            task_id,
            total_messages=message_count,
            total_links=len(all_urls),
            current_phase="checking_links",
            append_log=f"已命中 {message_count} 条消息，共提取 {len(all_urls)} 个链接",
        )
        if platform_counts:
            _update_task_status(
                task_id,
                append_log=f"按网盘分组：{_format_platform_counts(platform_counts)}",
            )

        check_started_at = time.time()
        last_logged_checked = 0
        total_links = len(all_urls)

        async def result_callback(event: Dict[str, Any]) -> None:
            if should_stop_task(task_id):
                raise LinkCheckStopped("任务已停止")

            _update_task_status(
                task_id,
                current_phase="checking_links",
                current_platform=str(event.get("platform") or "未知网盘"),
                append_log=_format_link_result_log(event),
            )

        async def progress_callback(checked: int, total: int, valid: int, invalid: int) -> None:
            nonlocal last_logged_checked
            if should_stop_task(task_id):
                raise LinkCheckStopped("任务已停止")

            progress = int((checked / total) * 100) if total > 0 else 0
            update_fields: Dict[str, Any] = {
                "progress": progress,
                "checked_links": checked,
                "valid_links": valid,
                "invalid_links": invalid,
                "current_phase": "checking_links",
            }
            append_log = None
            if checked == total:
                append_log = f"检测完成，已处理 {checked}/{total} 个链接"
            elif checked - last_logged_checked >= max(10, total_links // 10):
                last_logged_checked = checked
                append_log = (
                    f"进度 {checked}/{total}，有效 {valid}，失效 {invalid}"
                )
            _update_task_status(task_id, append_log=append_log, **update_fields)

        results = await validator.check_multiple_links_with_progress(
            all_urls,
            max_concurrent=max_concurrent,
            progress_callback=progress_callback,
            result_callback=result_callback,
            should_stop=lambda: should_stop_task(task_id),
        )

        if should_stop_task(task_id):
            raise LinkCheckStopped("任务已停止")

        summary = validator.get_summary(results)
        check_duration = time.time() - check_started_at
        check_time = datetime.now()
        status_counts = summary.get("status_counts") or {}
        top_errors = Counter(
            (result.get("error") or result.get("reason") or "EMPTY")
            for result in results
            if not result.get("is_valid")
        ).most_common(8)

        _update_task_status(
            task_id,
            current_phase="saving_results",
            status_counts=status_counts,
            append_log=f"状态分布：{', '.join(f'{key}={value}' for key, value in sorted(status_counts.items())) or '无'}",
        )
        if top_errors:
            _update_task_status(
                task_id,
                append_log="主要失败原因：" + "，".join(f"{reason} x{count}" for reason, count in top_errors),
            )

        with Session(engine) as session:
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=message_count,
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

        _update_task_status(
            task_id,
            status="completed",
            progress=100,
            current_phase="completed",
            checked_links=len(all_urls),
            valid_links=summary["valid_links"],
            invalid_links=summary["invalid_links"],
            check_time=check_time.isoformat(),
            duration=check_duration,
            status_counts=status_counts,
            append_log=f"任务完成，有效 {summary['valid_links']}，失效 {summary['invalid_links']}，耗时 {check_duration:.1f} 秒",
        )
    except LinkCheckStopped as exc:
        current_status = get_task_status(task_id) or {}
        _update_task_status(
            task_id,
            status="stopped",
            current_phase="stopped",
            error=str(exc),
            progress=current_status.get("progress", 0),
            append_log="任务已停止，未继续写入检测结果",
        )
    except Exception as exc:
        logger.error("link check task %s failed: %s", task_id, exc, exc_info=True)
        current_status = get_task_status(task_id) or {}
        _update_task_status(
            task_id,
            status="failed",
            current_phase="failed",
            error=str(exc),
            progress=current_status.get("progress", 0),
            append_log=f"任务失败：{exc}",
        )
    finally:
        final_status = get_task_status(task_id) or {}
        if final_status.get("status") in FINAL_TASK_STATUSES:
            _clear_active_task(task_id)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    persisted_status = _load_persisted_task_status(task_id)
    with _task_status_lock:
        if persisted_status is not None:
            persisted_status["logs"] = _normalize_logs(persisted_status.get("logs"))
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
        plan_ids = {int(stat.plan_id) for stat in stats if stat.plan_id is not None}
        plans_by_id = (
            {
                int(plan.id): plan
                for plan in session.query(LinkCheckPlan).filter(LinkCheckPlan.id.in_(plan_ids)).all()
            }
            if plan_ids
            else {}
        )
        return [
            {
                "id": stat.id,
                "check_time": stat.check_time.isoformat(),
                "total_messages": stat.total_messages,
                "total_links": stat.total_links,
                "valid_links": stat.valid_links,
                "invalid_links": stat.invalid_links,
                "updated_messages": stat.updated_messages,
                "deleted_messages": stat.deleted_messages,
                "status": stat.status,
                "duration": stat.check_duration,
                "trigger_source": stat.trigger_source,
                "task_mode": stat.task_mode,
                "scope_label": stat.scope_label,
                "plan_id": stat.plan_id,
                "plan_name": plans_by_id.get(int(stat.plan_id)).name if stat.plan_id is not None and int(stat.plan_id) in plans_by_id else None,
                "plan_mode": plans_by_id.get(int(stat.plan_id)).plan_mode if stat.plan_id is not None and int(stat.plan_id) in plans_by_id else None,
            }
            for stat in stats
        ]


def get_link_check_date_range() -> Dict[str, Optional[str]]:
    with Session(engine) as session:
        earliest_message = session.query(Message).order_by(Message.timestamp.asc()).first()
        latest_message = session.query(Message).order_by(Message.timestamp.desc()).first()

    return {
        "min_date": earliest_message.timestamp.date().isoformat() if earliest_message else None,
        "max_date": datetime.now().date().isoformat(),
        "latest_message_date": latest_message.timestamp.date().isoformat() if latest_message else None,
    }


def get_task_result(check_time_str: str) -> Dict[str, Any]:
    check_time = datetime.fromisoformat(check_time_str)
    with Session(engine) as session:
        stats = session.query(LinkCheckStats).filter(LinkCheckStats.check_time == check_time).first()
        if stats is None:
            return {"error": "检测记录不存在"}

        plan = session.get(LinkCheckPlan, stats.plan_id) if stats.plan_id is not None else None

        details = (
            session.query(LinkCheckDetails)
            .filter(LinkCheckDetails.check_time == check_time)
            .order_by(LinkCheckDetails.id.asc())
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
            "trigger_source": stats.trigger_source,
            "task_mode": stats.task_mode,
            "scope_label": stats.scope_label,
            "plan_id": stats.plan_id,
            "plan_name": plan.name if plan is not None else None,
            "plan_mode": plan.plan_mode if plan is not None else None,
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
