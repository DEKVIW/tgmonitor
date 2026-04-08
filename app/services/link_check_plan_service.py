from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import LinkCheckPlan, Message, engine, ensure_runtime_storage_tables
from app.services.link_check_selection_service import (
    ALLOWED_TRAVERSAL_ORDERS,
    build_plan_batch_selection_snapshot,
    get_link_check_dataset_summary,
)
from app.services.link_check_runtime import (
    dispatch_task,
    get_active_task_snapshot,
    get_task_status,
    start_or_reuse_task,
)
from app.services.link_cleanup_service import apply_link_check_cleanup
from app.services.system_config_service import get_link_check_runtime_config


logger = logging.getLogger(__name__)

DEFAULT_LINK_CHECK_PLAN_NAME = "默认巡检"
ALLOWED_PLAN_CLEANUP_MODES = {"none", "remove_invalid_links", "delete_message_if_empty"}
PLAN_WAIT_WHEN_BLOCKED_MINUTES = 30
PLAN_OVERVIEW_CACHE_KEY = "overview_cache"
PLAN_OVERVIEW_CACHE_TTL_SECONDS = 300
PLAN_OVERVIEW_REFRESH_LEASE_SECONDS = 180

_dispatch_lock = threading.RLock()
_active_plan_threads: set[int] = set()
_overview_refresh_lock = threading.RLock()
_active_overview_refresh_threads: set[int] = set()


def _utc_now() -> datetime:
    return datetime.utcnow()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_utc_storage(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


def _to_utc_storage(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _get_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _overview_timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_cache_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_plan_extra_json(plan: LinkCheckPlan) -> dict[str, Any]:
    if isinstance(plan.extra_json, dict):
        return dict(plan.extra_json)
    return {}


def _get_plan_overview_cache(plan: LinkCheckPlan) -> dict[str, Any]:
    cache = _get_plan_extra_json(plan).get(PLAN_OVERVIEW_CACHE_KEY)
    return dict(cache) if isinstance(cache, dict) else {}


def _set_plan_overview_cache(plan: LinkCheckPlan, cache: dict[str, Any]) -> None:
    extra_json = _get_plan_extra_json(plan)
    extra_json[PLAN_OVERVIEW_CACHE_KEY] = cache
    plan.extra_json = extra_json


def _build_empty_dataset_summary() -> dict[str, Any]:
    return {
        "total_messages_with_links": 0,
        "total_links": 0,
        "first_message_time": None,
        "last_message_time": None,
    }


def _normalize_dataset_summary(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    return {
        "total_messages_with_links": int(summary.get("total_messages_with_links") or 0),
        "total_links": int(summary.get("total_links") or 0),
        "first_message_time": summary.get("first_message_time"),
        "last_message_time": summary.get("last_message_time"),
    }


def _is_plan_overview_cache_stale(plan: LinkCheckPlan) -> bool:
    cache = _get_plan_overview_cache(plan)
    if bool(cache.get("stale")):
        return True
    generated_at = _parse_cache_datetime(cache.get("generated_at"))
    if generated_at is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    return age_seconds >= PLAN_OVERVIEW_CACHE_TTL_SECONDS


def _is_plan_overview_refreshing(plan: LinkCheckPlan) -> bool:
    cache = _get_plan_overview_cache(plan)
    requested_at = _parse_cache_datetime(cache.get("refresh_requested_at"))
    if requested_at is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - requested_at).total_seconds()
    return age_seconds < PLAN_OVERVIEW_REFRESH_LEASE_SECONDS


def _mark_plan_overview_cache_stale(plan: LinkCheckPlan) -> None:
    cache = _get_plan_overview_cache(plan)
    cache["stale"] = True
    cache["refresh_requested_at"] = None
    _set_plan_overview_cache(plan, cache)


def _store_plan_overview_cache(
    plan: LinkCheckPlan,
    dataset_summary: dict[str, Any],
    *,
    generated_at: str,
) -> None:
    cache = _get_plan_overview_cache(plan)
    cache["dataset_summary"] = _normalize_dataset_summary(dataset_summary) or _build_empty_dataset_summary()
    cache["generated_at"] = generated_at
    cache["stale"] = False
    cache["refresh_requested_at"] = None
    _set_plan_overview_cache(plan, cache)


def _build_default_plan_values() -> dict[str, Any]:
    return {
        "name": DEFAULT_LINK_CHECK_PLAN_NAME,
        "is_enabled": False,
        "schedule_hour": 1,
        "schedule_minute": 0,
        "timezone": "Asia/Shanghai",
        "cycle_days": 7,
        "batch_link_target": 900,
        "max_batches_per_run": 3,
        "max_concurrent": 5,
        "traversal_order": "newest_first",
        "cleanup_mode": "none",
        "cleanup_min_consecutive_invalid_runs": 2,
        "next_run_at": None,
        "last_run_at": None,
        "last_status": None,
        "last_error_message": None,
        "cursor_message_id": None,
        "cycle_started_at": None,
        "cycle_completed_at": None,
        "extra_json": {},
    }


def _compute_next_run_at(plan: LinkCheckPlan, *, now_utc: datetime | None = None) -> datetime | None:
    if not plan.is_enabled:
        return None

    current_utc = _from_utc_storage(now_utc or _utc_now()) or datetime.now(timezone.utc)
    timezone_info = _get_timezone(plan.timezone)
    local_now = current_utc.astimezone(timezone_info)
    candidate = local_now.replace(
        hour=int(plan.schedule_hour),
        minute=int(plan.schedule_minute),
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return _to_utc_storage(candidate.astimezone(timezone.utc))


def _ensure_plan(session: Session) -> LinkCheckPlan:
    ensure_runtime_storage_tables()
    plan = session.query(LinkCheckPlan).order_by(LinkCheckPlan.id.asc()).first()
    if plan is not None:
        return plan

    plan = LinkCheckPlan(**_build_default_plan_values())
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def _coerce_int(value: Any, *, minimum: int, maximum: int, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if normalized < minimum or normalized > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return normalized


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _serialize_plan(plan: LinkCheckPlan, overview: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": plan.id,
        "name": plan.name,
        "is_enabled": bool(plan.is_enabled),
        "schedule_hour": plan.schedule_hour,
        "schedule_minute": plan.schedule_minute,
        "timezone": plan.timezone,
        "cycle_days": plan.cycle_days,
        "batch_link_target": plan.batch_link_target,
        "max_batches_per_run": plan.max_batches_per_run,
        "max_concurrent": plan.max_concurrent,
        "traversal_order": plan.traversal_order,
        "cleanup_mode": plan.cleanup_mode,
        "cleanup_min_consecutive_invalid_runs": plan.cleanup_min_consecutive_invalid_runs,
        "next_run_at": _to_iso(plan.next_run_at),
        "last_run_at": _to_iso(plan.last_run_at),
        "last_status": plan.last_status,
        "last_error_message": plan.last_error_message,
        "cursor_message_id": plan.cursor_message_id,
        "cycle_started_at": _to_iso(plan.cycle_started_at),
        "cycle_completed_at": _to_iso(plan.cycle_completed_at),
        "created_at": _to_iso(plan.created_at),
        "updated_at": _to_iso(plan.updated_at),
        "updated_by": plan.updated_by,
        "overview": overview,
    }


def _compose_plan_overview(
    plan: LinkCheckPlan,
    dataset_summary: dict[str, Any],
    *,
    runtime_config: dict[str, Any],
    generated_at: str | None = None,
    stale: bool = False,
    refreshing: bool = False,
    placeholder: bool = False,
) -> dict[str, Any]:
    dataset_summary = _normalize_dataset_summary(dataset_summary) or _build_empty_dataset_summary()
    total_links = int(dataset_summary["total_links"] or 0)
    total_messages = int(dataset_summary["total_messages_with_links"] or 0)
    links_per_run = int(plan.batch_link_target or 0) * int(plan.max_batches_per_run or 0)
    estimated_batches_per_cycle = math.ceil(total_links / plan.batch_link_target) if total_links and plan.batch_link_target else 0
    estimated_days_to_complete_cycle = (total_links / links_per_run) if total_links and links_per_run else 0.0
    can_finish_within_cycle = bool(plan.cycle_days and estimated_days_to_complete_cycle <= plan.cycle_days) if total_links else True

    warnings: list[str] = []
    if total_links and not links_per_run:
        warnings.append("当前每次执行处理量为 0，无法推进巡检计划。")
    elif total_links and not can_finish_within_cycle:
        warnings.append("按当前配置无法在一个覆盖周期内跑完全部链接，建议提高单批链接数或增加每次批次数。")
    if plan.cleanup_mode != "none" and plan.cleanup_min_consecutive_invalid_runs <= 1:
        warnings.append("自动清理当前会在首次判定失效后立即执行，风险较高。")

    if placeholder:
        summary = "正在后台统计链接库存，完成后会自动刷新概览。"
        warnings.insert(0, "首次统计会扫描全部带链接消息，耗时取决于库存体量。")
    else:
        summary = "当前暂无可巡检链接"
    if total_links and links_per_run:
        summary = f"按当前配置预计 {estimated_days_to_complete_cycle:.1f} 天跑完一轮"
    if stale and not placeholder:
        warnings.insert(0, "当前概览基于缓存数据，系统正在后台刷新最新库存。")

    return {
        "total_messages_with_links": total_messages,
        "total_links": total_links,
        "first_message_time": dataset_summary["first_message_time"],
        "last_message_time": dataset_summary["last_message_time"],
        "estimated_links_per_run": links_per_run,
        "estimated_batches_per_cycle": estimated_batches_per_cycle,
        "estimated_days_to_complete_cycle": round(estimated_days_to_complete_cycle, 2),
        "can_finish_within_cycle": can_finish_within_cycle,
        "warnings": warnings,
        "summary": summary,
        "next_run_at": _to_iso(plan.next_run_at),
        "last_run_at": _to_iso(plan.last_run_at),
        "cursor_message_id": plan.cursor_message_id,
        "cycle_started_at": _to_iso(plan.cycle_started_at),
        "cycle_completed_at": _to_iso(plan.cycle_completed_at),
        "task_link_limit": int(runtime_config["link_check_max_allowed_links"]),
        "task_concurrency_limit": int(runtime_config["link_check_max_allowed_concurrent"]),
        "generated_at": generated_at,
        "stale": stale,
        "refreshing": refreshing,
    }


def _build_plan_overview(session: Session, plan: LinkCheckPlan) -> tuple[dict[str, Any], dict[str, Any], str]:
    runtime_config = get_link_check_runtime_config()
    dataset_summary = get_link_check_dataset_summary(session)
    generated_at = _overview_timestamp_now()
    overview = _compose_plan_overview(
        plan,
        dataset_summary,
        runtime_config=runtime_config,
        generated_at=generated_at,
    )
    return overview, dataset_summary, generated_at


def _run_plan_overview_refresh_thread(plan_id: int) -> None:
    try:
        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is None:
                return
            _, dataset_summary, generated_at = _build_plan_overview(session, plan)
            _store_plan_overview_cache(plan, dataset_summary, generated_at=generated_at)
            session.add(plan)
            session.commit()
    except Exception:
        logger.exception("Failed to refresh link check overview for plan %s", plan_id)
        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is not None:
                _mark_plan_overview_cache_stale(plan)
                session.add(plan)
                session.commit()
    finally:
        with _overview_refresh_lock:
            _active_overview_refresh_threads.discard(plan_id)


def _schedule_plan_overview_refresh(plan_id: int) -> bool:
    with _overview_refresh_lock:
        if plan_id in _active_overview_refresh_threads:
            return False

    with Session(engine) as session:
        plan = session.get(LinkCheckPlan, plan_id)
        if plan is None:
            return False
        if _is_plan_overview_refreshing(plan):
            return False

        cache = _get_plan_overview_cache(plan)
        cache["refresh_requested_at"] = _overview_timestamp_now()
        _set_plan_overview_cache(plan, cache)
        session.add(plan)
        session.commit()

    with _overview_refresh_lock:
        if plan_id in _active_overview_refresh_threads:
            return False
        _active_overview_refresh_threads.add(plan_id)

    worker = threading.Thread(
        target=_run_plan_overview_refresh_thread,
        args=(plan_id,),
        daemon=True,
        name=f"link-check-overview-{plan_id}",
    )
    try:
        worker.start()
    except Exception:
        with _overview_refresh_lock:
            _active_overview_refresh_threads.discard(plan_id)
        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is not None:
                _mark_plan_overview_cache_stale(plan)
                session.add(plan)
                session.commit()
        logger.exception("Failed to start link check overview refresh thread for plan %s", plan_id)
        return False
    return True


def _load_plan_overview(plan: LinkCheckPlan, *, refresh_if_needed: bool) -> dict[str, Any]:
    runtime_config = get_link_check_runtime_config()
    cache = _get_plan_overview_cache(plan)
    dataset_summary = _normalize_dataset_summary(cache.get("dataset_summary"))
    generated_at = str(cache.get("generated_at") or "").strip() or None
    stale = _is_plan_overview_cache_stale(plan)
    refreshing = _is_plan_overview_refreshing(plan)

    should_refresh = dataset_summary is None or stale
    if refresh_if_needed and should_refresh and not refreshing:
        refreshing = _schedule_plan_overview_refresh(plan.id) or refreshing or dataset_summary is None

    if dataset_summary is None:
        return _compose_plan_overview(
            plan,
            _build_empty_dataset_summary(),
            runtime_config=runtime_config,
            generated_at=generated_at,
            stale=True,
            refreshing=refreshing,
            placeholder=True,
        )

    return _compose_plan_overview(
        plan,
        dataset_summary,
        runtime_config=runtime_config,
        generated_at=generated_at,
        stale=stale,
        refreshing=refreshing,
    )


def get_link_check_plan() -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plan = _ensure_plan(session)
        overview = _load_plan_overview(plan, refresh_if_needed=True)
        return _serialize_plan(plan, overview)


def update_link_check_plan(values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    runtime_config = get_link_check_runtime_config()
    max_links_limit = int(runtime_config["link_check_max_allowed_links"])
    max_concurrent_limit = int(runtime_config["link_check_max_allowed_concurrent"])

    with Session(engine) as session:
        plan = _ensure_plan(session)
        traversal_order = str(values.get("traversal_order") or plan.traversal_order).strip().lower()
        if traversal_order not in ALLOWED_TRAVERSAL_ORDERS:
            raise ValueError("traversal_order must be newest_first or oldest_first")

        cleanup_mode = str(values.get("cleanup_mode") or plan.cleanup_mode).strip().lower()
        if cleanup_mode not in ALLOWED_PLAN_CLEANUP_MODES:
            raise ValueError("cleanup_mode must be none, remove_invalid_links or delete_message_if_empty")

        plan.name = str(values.get("name") or plan.name or DEFAULT_LINK_CHECK_PLAN_NAME).strip()[:128] or DEFAULT_LINK_CHECK_PLAN_NAME
        plan.is_enabled = _coerce_bool(values.get("is_enabled", plan.is_enabled))
        plan.schedule_hour = _coerce_int(values.get("schedule_hour", plan.schedule_hour), minimum=0, maximum=23, field_name="schedule_hour")
        plan.schedule_minute = _coerce_int(values.get("schedule_minute", plan.schedule_minute), minimum=0, maximum=59, field_name="schedule_minute")
        plan.timezone = str(values.get("timezone") or plan.timezone or "Asia/Shanghai").strip()[:64] or "Asia/Shanghai"
        plan.cycle_days = _coerce_int(values.get("cycle_days", plan.cycle_days), minimum=1, maximum=90, field_name="cycle_days")
        plan.batch_link_target = _coerce_int(values.get("batch_link_target", plan.batch_link_target), minimum=100, maximum=max_links_limit, field_name="batch_link_target")
        plan.max_batches_per_run = _coerce_int(values.get("max_batches_per_run", plan.max_batches_per_run), minimum=1, maximum=12, field_name="max_batches_per_run")
        plan.max_concurrent = _coerce_int(values.get("max_concurrent", plan.max_concurrent), minimum=1, maximum=max_concurrent_limit, field_name="max_concurrent")
        plan.traversal_order = traversal_order
        plan.cleanup_mode = cleanup_mode
        plan.cleanup_min_consecutive_invalid_runs = _coerce_int(
            values.get("cleanup_min_consecutive_invalid_runs", plan.cleanup_min_consecutive_invalid_runs),
            minimum=1,
            maximum=10,
            field_name="cleanup_min_consecutive_invalid_runs",
        )
        plan.updated_by = updated_by
        plan.next_run_at = _compute_next_run_at(plan) if plan.is_enabled else None
        if not plan.is_enabled:
            plan.last_error_message = None
        _mark_plan_overview_cache_stale(plan)

        session.add(plan)
        session.commit()
        session.refresh(plan)
        overview = _load_plan_overview(plan, refresh_if_needed=True)
        return _serialize_plan(plan, overview)


def mark_link_check_plan_overview_stale(
    plan_id: int | None = None,
    *,
    trigger_refresh: bool = False,
) -> bool:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plan = session.get(LinkCheckPlan, plan_id) if plan_id is not None else _ensure_plan(session)
        if plan is None:
            return False
        _mark_plan_overview_cache_stale(plan)
        session.add(plan)
        session.commit()
        target_plan_id = int(plan.id)

    if trigger_refresh:
        _schedule_plan_overview_refresh(target_plan_id)
    return True


def _wait_for_task_completion(task_id: str, *, timeout_seconds: int = 6 * 3600) -> dict[str, Any]:
    deadline = time.time() + max(30, timeout_seconds)
    last_status: dict[str, Any] = {}
    while time.time() < deadline:
        last_status = get_task_status(task_id) or {}
        if last_status.get("status") in {"completed", "failed", "stopped"}:
            return last_status
        time.sleep(1.0)
    return last_status


def _run_plan_thread(plan_id: int) -> None:
    try:
        _execute_link_check_plan(plan_id)
    finally:
        with _dispatch_lock:
            _active_plan_threads.discard(plan_id)


def dispatch_link_check_plan(plan_id: int) -> bool:
    with _dispatch_lock:
        if plan_id in _active_plan_threads:
            return False
        _active_plan_threads.add(plan_id)

    worker = threading.Thread(
        target=_run_plan_thread,
        args=(plan_id,),
        daemon=True,
        name=f"link-check-plan-{plan_id}",
    )
    worker.start()
    return True


def claim_due_link_check_plan_runs(*, limit: int = 1) -> int:
    ensure_runtime_storage_tables()
    now_utc = _utc_now()
    due_plan_ids: list[int] = []

    with Session(engine) as session:
        due_plans = (
            session.query(LinkCheckPlan)
            .filter(
                LinkCheckPlan.is_enabled.is_(True),
                LinkCheckPlan.next_run_at.isnot(None),
                LinkCheckPlan.next_run_at <= now_utc,
            )
            .order_by(LinkCheckPlan.next_run_at.asc(), LinkCheckPlan.id.asc())
            .with_for_update(skip_locked=True)
            .limit(max(1, limit))
            .all()
        )

        for plan in due_plans:
            if get_active_task_snapshot() is not None:
                plan.last_status = "waiting"
                plan.last_error_message = "已有链接检测任务在运行，计划已顺延"
                plan.next_run_at = now_utc + timedelta(minutes=PLAN_WAIT_WHEN_BLOCKED_MINUTES)
                continue

            plan.last_status = "pending"
            plan.last_error_message = None
            plan.next_run_at = _compute_next_run_at(plan, now_utc=now_utc)
            due_plan_ids.append(plan.id)

        session.commit()

    for plan_id in due_plan_ids:
        dispatch_link_check_plan(plan_id)
    return len(due_plan_ids)


def _execute_link_check_plan(plan_id: int) -> None:
    runtime_config = get_link_check_runtime_config()
    task_link_limit = int(runtime_config["link_check_max_allowed_links"])
    max_concurrent_limit = int(runtime_config["link_check_max_allowed_concurrent"])

    with Session(engine) as session:
        plan = session.get(LinkCheckPlan, plan_id)
        if plan is None or not plan.is_enabled:
            return
        max_batches_per_run = int(plan.max_batches_per_run or 1)

    for _ in range(max(1, max_batches_per_run)):
        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is None or not plan.is_enabled:
                return

            if get_active_task_snapshot() is not None:
                plan.last_status = "waiting"
                plan.last_error_message = "已有链接检测任务在运行，已终止本轮批次"
                plan.last_run_at = _utc_now()
                session.commit()
                return

            if plan.cycle_started_at is None:
                plan.cycle_started_at = _utc_now()
                plan.cycle_completed_at = None
                session.commit()

            preview = build_plan_batch_selection_snapshot(
                session,
                batch_link_target=min(plan.batch_link_target, task_link_limit),
                direction=plan.traversal_order,
                task_link_limit=task_link_limit,
                cursor_message_id=plan.cursor_message_id,
            )

            if preview["estimated_links"] <= 0:
                plan.cursor_message_id = None
                plan.cycle_started_at = None
                plan.cycle_completed_at = _utc_now()
                plan.last_status = "idle"
                plan.last_error_message = None
                plan.last_run_at = _utc_now()
                session.commit()
                return

            task_id, _, created = start_or_reuse_task(
                preview["scope_label"],
                min(plan.max_concurrent, max_concurrent_limit),
                task_metadata={
                    "scope_label": preview["scope_label"],
                    "trigger_source": "scheduled",
                    "task_mode": "scheduled_batch",
                },
            )
            if not created:
                plan.last_status = "waiting"
                plan.last_error_message = "自动巡检与其他检测任务冲突，本轮已跳过"
                plan.last_run_at = _utc_now()
                session.commit()
                return

            payload = {
                **preview,
                "scope_label": preview["scope_label"],
                "selection_mode": "smart_count",
                "task_mode": "scheduled_batch",
                "trigger_source": "scheduled",
                "plan_id": plan.id,
            }
            dispatch_task(task_id, payload, min(plan.max_concurrent, max_concurrent_limit))

        final_status = _wait_for_task_completion(task_id)

        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is None:
                return

            plan.last_run_at = _utc_now()
            plan.last_status = str(final_status.get("status") or "failed")
            plan.last_error_message = final_status.get("error")

            if final_status.get("status") == "completed":
                if preview["has_more_messages"] and preview.get("next_cursor_message_id") is not None:
                    plan.cursor_message_id = int(preview["next_cursor_message_id"])
                else:
                    plan.cursor_message_id = None
                    plan.cycle_started_at = None
                    plan.cycle_completed_at = _utc_now()
                session.commit()
            else:
                session.commit()
                return

        if plan.cleanup_mode != "none" and final_status.get("check_time"):
            try:
                with Session(engine) as cleanup_session:
                    cleanup_result = apply_link_check_cleanup(
                        cleanup_session,
                        str(final_status["check_time"]),
                        mode=plan.cleanup_mode,
                        dry_run=False,
                        min_consecutive_invalid_runs=plan.cleanup_min_consecutive_invalid_runs,
                    )
                if cleanup_result.get("updated_messages") or cleanup_result.get("deleted_messages"):
                    mark_link_check_plan_overview_stale(plan.id)
            except Exception:
                logger.exception("Automatic link cleanup failed for plan %s", plan_id)

        if not preview["has_more_messages"]:
            return
