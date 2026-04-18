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
    TRAVERSAL_NEWEST_FIRST,
    TRAVERSAL_OLDEST_FIRST,
    build_plan_batch_selection_snapshot,
    get_latest_message_id_with_links,
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
PLAN_OVERVIEW_CACHE_KEY = "overview_cache"
PLAN_OVERVIEW_CACHE_TTL_SECONDS = 300
PLAN_OVERVIEW_REFRESH_LEASE_SECONDS = 180
DEFAULT_BACKFILL_PLAN_NAME = "补库巡检"
DEFAULT_FRONTIER_PLAN_NAME = "追新巡检"
PLAN_MODE_BACKFILL = "backfill"
PLAN_MODE_FRONTIER = "frontier"
ALLOWED_PLAN_MODES = {PLAN_MODE_BACKFILL, PLAN_MODE_FRONTIER}
LEGACY_PLAN_MIGRATION_MARKER = "multi_plan_migrated"
DEFAULT_FRONTIER_OVERLAP_MESSAGE_COUNT = 200

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


def _default_plan_name(plan_mode: str) -> str:
    return DEFAULT_FRONTIER_PLAN_NAME if plan_mode == PLAN_MODE_FRONTIER else DEFAULT_BACKFILL_PLAN_NAME


def _normalize_plan_mode(value: Any) -> str:
    normalized = str(value or PLAN_MODE_BACKFILL).strip().lower()
    if normalized not in ALLOWED_PLAN_MODES:
        raise ValueError("plan_mode must be backfill or frontier")
    return normalized


def _effective_plan_mode(plan: LinkCheckPlan) -> str:
    raw_mode = str(getattr(plan, "plan_mode", "") or "").strip().lower()
    if raw_mode in ALLOWED_PLAN_MODES:
        return raw_mode

    traversal_order = str(getattr(plan, "traversal_order", "") or "").strip().lower()
    if traversal_order == TRAVERSAL_NEWEST_FIRST:
        return PLAN_MODE_FRONTIER
    return PLAN_MODE_BACKFILL


def _direction_for_plan_mode(plan_mode: str) -> str:
    normalized_mode = _normalize_plan_mode(plan_mode)
    if normalized_mode == PLAN_MODE_FRONTIER:
        return TRAVERSAL_NEWEST_FIRST
    return TRAVERSAL_OLDEST_FIRST


def _build_default_plan_values(plan_mode: str = PLAN_MODE_BACKFILL) -> dict[str, Any]:
    normalized_mode = _normalize_plan_mode(plan_mode)
    is_frontier = normalized_mode == PLAN_MODE_FRONTIER
    return {
        "name": _default_plan_name(normalized_mode),
        "plan_mode": normalized_mode,
        "is_enabled": False,
        "schedule_hour": 3 if is_frontier else 1,
        "schedule_minute": 0,
        "schedule_priority": 50 if is_frontier else 100,
        "timezone": "Asia/Shanghai",
        "cycle_days": 7,
        "batch_link_target": 600 if is_frontier else 900,
        "max_batches_per_run": 2 if is_frontier else 3,
        "max_concurrent": 5,
        "traversal_order": _direction_for_plan_mode(normalized_mode),
        "overlap_message_count": DEFAULT_FRONTIER_OVERLAP_MESSAGE_COUNT,
        "cleanup_mode": "none",
        "cleanup_min_consecutive_invalid_runs": 2,
        "next_run_at": None,
        "last_run_at": None,
        "last_status": None,
        "last_error_message": None,
        "cursor_message_id": None,
        "window_lower_message_id": None,
        "window_upper_message_id": None,
        "completed_through_message_id": None,
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


def _clear_plan_window(plan: LinkCheckPlan) -> None:
    plan.cursor_message_id = None
    plan.window_lower_message_id = None
    plan.window_upper_message_id = None
    plan.cycle_started_at = None


def _mark_legacy_plan_migrated(plan: LinkCheckPlan) -> None:
    extra_json = _get_plan_extra_json(plan)
    extra_json[LEGACY_PLAN_MIGRATION_MARKER] = True
    plan.extra_json = extra_json


def _is_legacy_plan_migrated(plan: LinkCheckPlan) -> bool:
    extra_json = _get_plan_extra_json(plan)
    return bool(extra_json.get(LEGACY_PLAN_MIGRATION_MARKER))


def _maybe_migrate_legacy_single_plan(session: Session) -> None:
    plans = session.query(LinkCheckPlan).order_by(LinkCheckPlan.id.asc()).all()
    if len(plans) != 1:
        return

    plan = plans[0]
    if _is_legacy_plan_migrated(plan):
        return

    inferred_mode = (
        PLAN_MODE_FRONTIER
        if str(plan.traversal_order or "").strip().lower() == TRAVERSAL_NEWEST_FIRST
        else PLAN_MODE_BACKFILL
    )
    plan.plan_mode = inferred_mode
    plan.schedule_priority = 50 if inferred_mode == PLAN_MODE_FRONTIER else 100
    if not int(plan.overlap_message_count or 0):
        plan.overlap_message_count = DEFAULT_FRONTIER_OVERLAP_MESSAGE_COUNT
    if not str(plan.name or "").strip() or str(plan.name or "").strip() == DEFAULT_LINK_CHECK_PLAN_NAME:
        plan.name = _default_plan_name(inferred_mode)
    _mark_legacy_plan_migrated(plan)
    session.add(plan)
    session.commit()


def _ensure_default_plan(session: Session) -> LinkCheckPlan:
    ensure_runtime_storage_tables()
    _maybe_migrate_legacy_single_plan(session)
    plan = session.query(LinkCheckPlan).order_by(LinkCheckPlan.id.asc()).first()
    if plan is not None:
        return plan

    plan = LinkCheckPlan(**_build_default_plan_values())
    _mark_legacy_plan_migrated(plan)
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


def _apply_plan_values(
    plan: LinkCheckPlan,
    values: dict[str, Any],
    *,
    runtime_config: dict[str, Any],
    updated_by: str | None = None,
    is_create: bool = False,
) -> None:
    max_links_limit = int(runtime_config["link_check_max_allowed_links"])
    max_concurrent_limit = int(runtime_config["link_check_max_allowed_concurrent"])
    previous_mode = _effective_plan_mode(plan)
    next_mode = _normalize_plan_mode(values.get("plan_mode", previous_mode))

    cleanup_mode = str(values.get("cleanup_mode") or plan.cleanup_mode or "none").strip().lower()
    if cleanup_mode not in ALLOWED_PLAN_CLEANUP_MODES:
        raise ValueError("cleanup_mode must be none, remove_invalid_links or delete_message_if_empty")

    if is_create:
        default_name = _default_plan_name(next_mode)
    else:
        default_name = str(plan.name or "").strip() or _default_plan_name(next_mode)

    plan.name = str(values.get("name") or default_name).strip()[:128] or _default_plan_name(next_mode)
    plan.plan_mode = next_mode
    plan.is_enabled = _coerce_bool(values.get("is_enabled", plan.is_enabled))
    plan.schedule_hour = _coerce_int(
        values.get("schedule_hour", plan.schedule_hour),
        minimum=0,
        maximum=23,
        field_name="schedule_hour",
    )
    plan.schedule_minute = _coerce_int(
        values.get("schedule_minute", plan.schedule_minute),
        minimum=0,
        maximum=59,
        field_name="schedule_minute",
    )
    plan.schedule_priority = _coerce_int(
        values.get("schedule_priority", plan.schedule_priority),
        minimum=1,
        maximum=9999,
        field_name="schedule_priority",
    )
    plan.timezone = str(values.get("timezone") or plan.timezone or "Asia/Shanghai").strip()[:64] or "Asia/Shanghai"
    plan.cycle_days = _coerce_int(
        values.get("cycle_days", plan.cycle_days),
        minimum=1,
        maximum=90,
        field_name="cycle_days",
    )
    plan.batch_link_target = _coerce_int(
        values.get("batch_link_target", plan.batch_link_target),
        minimum=100,
        maximum=max_links_limit,
        field_name="batch_link_target",
    )
    plan.max_batches_per_run = _coerce_int(
        values.get("max_batches_per_run", plan.max_batches_per_run),
        minimum=1,
        maximum=12,
        field_name="max_batches_per_run",
    )
    plan.max_concurrent = _coerce_int(
        values.get("max_concurrent", plan.max_concurrent),
        minimum=1,
        maximum=max_concurrent_limit,
        field_name="max_concurrent",
    )
    plan.traversal_order = _direction_for_plan_mode(next_mode)
    plan.overlap_message_count = _coerce_int(
        values.get("overlap_message_count", plan.overlap_message_count or DEFAULT_FRONTIER_OVERLAP_MESSAGE_COUNT),
        minimum=0,
        maximum=5000,
        field_name="overlap_message_count",
    )
    plan.cleanup_mode = cleanup_mode
    plan.cleanup_min_consecutive_invalid_runs = _coerce_int(
        values.get(
            "cleanup_min_consecutive_invalid_runs",
            plan.cleanup_min_consecutive_invalid_runs,
        ),
        minimum=1,
        maximum=10,
        field_name="cleanup_min_consecutive_invalid_runs",
    )
    plan.updated_by = updated_by
    plan.next_run_at = _compute_next_run_at(plan) if plan.is_enabled else None
    if not plan.is_enabled:
        plan.last_error_message = None
    if is_create or next_mode != previous_mode:
        _clear_plan_window(plan)
        plan.completed_through_message_id = None
        plan.cycle_completed_at = None
    _mark_plan_overview_cache_stale(plan)
    _mark_legacy_plan_migrated(plan)


def _load_plans(session: Session) -> list[LinkCheckPlan]:
    ensure_runtime_storage_tables()
    _maybe_migrate_legacy_single_plan(session)
    plans = session.query(LinkCheckPlan).order_by(LinkCheckPlan.schedule_hour.asc(), LinkCheckPlan.schedule_minute.asc(), LinkCheckPlan.schedule_priority.asc(), LinkCheckPlan.id.asc()).all()
    if plans:
        return plans
    return [_ensure_default_plan(session)]


def _serialize_plan(plan: LinkCheckPlan, overview: dict[str, Any]) -> dict[str, Any]:
    plan_mode = _effective_plan_mode(plan)
    return {
        "id": plan.id,
        "name": plan.name,
        "plan_mode": plan_mode,
        "is_enabled": bool(plan.is_enabled),
        "schedule_hour": plan.schedule_hour,
        "schedule_minute": plan.schedule_minute,
        "schedule_priority": plan.schedule_priority,
        "timezone": plan.timezone,
        "cycle_days": plan.cycle_days,
        "batch_link_target": plan.batch_link_target,
        "max_batches_per_run": plan.max_batches_per_run,
        "max_concurrent": plan.max_concurrent,
        "traversal_order": plan.traversal_order,
        "overlap_message_count": plan.overlap_message_count,
        "cleanup_mode": plan.cleanup_mode,
        "cleanup_min_consecutive_invalid_runs": plan.cleanup_min_consecutive_invalid_runs,
        "next_run_at": _to_iso(plan.next_run_at),
        "last_run_at": _to_iso(plan.last_run_at),
        "last_status": plan.last_status,
        "last_error_message": plan.last_error_message,
        "cursor_message_id": plan.cursor_message_id,
        "window_lower_message_id": plan.window_lower_message_id,
        "window_upper_message_id": plan.window_upper_message_id,
        "completed_through_message_id": plan.completed_through_message_id,
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
    plan_mode = _effective_plan_mode(plan)
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
        "plan_mode": plan_mode,
        "schedule_priority": plan.schedule_priority,
        "cursor_message_id": plan.cursor_message_id,
        "window_lower_message_id": plan.window_lower_message_id,
        "window_upper_message_id": plan.window_upper_message_id,
        "completed_through_message_id": plan.completed_through_message_id,
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


def get_link_check_plans() -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plans = _load_plans(session)
        return [_serialize_plan(plan, _load_plan_overview(plan, refresh_if_needed=True)) for plan in plans]


def create_link_check_plan(values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    runtime_config = get_link_check_runtime_config()
    with Session(engine) as session:
        requested_mode = _normalize_plan_mode(values.get("plan_mode", PLAN_MODE_BACKFILL))
        plan = LinkCheckPlan(**_build_default_plan_values(requested_mode))
        _apply_plan_values(plan, values, runtime_config=runtime_config, updated_by=updated_by, is_create=True)
        session.add(plan)
        session.commit()
        session.refresh(plan)
        overview = _load_plan_overview(plan, refresh_if_needed=True)
        return _serialize_plan(plan, overview)


def update_link_check_plan_by_id(
    plan_id: int,
    values: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    runtime_config = get_link_check_runtime_config()
    with Session(engine) as session:
        plan = session.get(LinkCheckPlan, int(plan_id))
        if plan is None:
            raise LookupError(f"link check plan {plan_id} was not found")
        _apply_plan_values(plan, values, runtime_config=runtime_config, updated_by=updated_by)
        session.add(plan)
        session.commit()
        session.refresh(plan)
        overview = _load_plan_overview(plan, refresh_if_needed=True)
        return _serialize_plan(plan, overview)


def delete_link_check_plan(plan_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plan = session.get(LinkCheckPlan, int(plan_id))
        if plan is None:
            raise LookupError(f"link check plan {plan_id} was not found")

        with _dispatch_lock:
            if int(plan.id) in _active_plan_threads:
                raise ValueError("cannot delete a running plan")

        session.delete(plan)
        session.commit()
        return {"success": True, "deleted_plan_id": int(plan_id)}


def get_link_check_plan() -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plan = _ensure_default_plan(session)
        overview = _load_plan_overview(plan, refresh_if_needed=True)
        return _serialize_plan(plan, overview)


def update_link_check_plan(values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        plan = _ensure_default_plan(session)
        plan_id = int(plan.id)
    return update_link_check_plan_by_id(plan_id, values, updated_by=updated_by)


def mark_link_check_plan_overview_stale(
    plan_id: int | None = None,
    *,
    trigger_refresh: bool = False,
) -> bool:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        if plan_id is None:
            plans = _load_plans(session)
        else:
            plan = session.get(LinkCheckPlan, int(plan_id))
            plans = [plan] if plan is not None else []

        if not plans:
            return False

        target_plan_ids: list[int] = []
        for plan in plans:
            _mark_plan_overview_cache_stale(plan)
            session.add(plan)
            target_plan_ids.append(int(plan.id))
        session.commit()

    if trigger_refresh:
        for target_plan_id in target_plan_ids:
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


def _prepare_backfill_preview(
    session: Session,
    plan: LinkCheckPlan,
    *,
    task_link_limit: int,
) -> dict[str, Any]:
    if plan.cycle_started_at is None or plan.window_upper_message_id is None:
        plan.cycle_started_at = _utc_now()
        plan.cycle_completed_at = None
        plan.window_lower_message_id = None
        plan.window_upper_message_id = get_latest_message_id_with_links(session)
        plan.cursor_message_id = None

    return build_plan_batch_selection_snapshot(
        session,
        batch_link_target=min(int(plan.batch_link_target or 0), task_link_limit),
        direction=TRAVERSAL_OLDEST_FIRST,
        task_link_limit=task_link_limit,
        cursor_message_id=plan.cursor_message_id,
        max_message_id=plan.window_upper_message_id,
    )


def _prepare_frontier_preview(
    session: Session,
    plan: LinkCheckPlan,
    *,
    task_link_limit: int,
) -> dict[str, Any]:
    if plan.cycle_started_at is None or plan.window_upper_message_id is None:
        latest_message_id = get_latest_message_id_with_links(session)
        lower_message_id: int | None = None
        if latest_message_id is not None and plan.completed_through_message_id is not None:
            overlap = max(0, int(plan.overlap_message_count or 0))
            lower_candidate = int(plan.completed_through_message_id) - overlap
            if lower_candidate > 0:
                lower_message_id = lower_candidate

        plan.cycle_started_at = _utc_now()
        plan.cycle_completed_at = None
        plan.window_lower_message_id = lower_message_id
        plan.window_upper_message_id = latest_message_id
        plan.cursor_message_id = None

    return build_plan_batch_selection_snapshot(
        session,
        batch_link_target=min(int(plan.batch_link_target or 0), task_link_limit),
        direction=TRAVERSAL_NEWEST_FIRST,
        task_link_limit=task_link_limit,
        cursor_message_id=plan.cursor_message_id,
        min_message_id=plan.window_lower_message_id,
        max_message_id=plan.window_upper_message_id,
    )


def _prepare_plan_preview(
    session: Session,
    plan: LinkCheckPlan,
    *,
    task_link_limit: int,
) -> tuple[str, dict[str, Any]]:
    plan_mode = _effective_plan_mode(plan)
    if plan_mode == PLAN_MODE_FRONTIER:
        return plan_mode, _prepare_frontier_preview(session, plan, task_link_limit=task_link_limit)
    return plan_mode, _prepare_backfill_preview(session, plan, task_link_limit=task_link_limit)


def _update_plan_after_completed_batch(
    plan: LinkCheckPlan,
    *,
    preview: dict[str, Any],
    plan_mode: str,
) -> None:
    if preview.get("has_more_messages") and preview.get("next_cursor_message_id") is not None:
        plan.cursor_message_id = int(preview["next_cursor_message_id"])
        if plan_mode == PLAN_MODE_BACKFILL:
            plan.completed_through_message_id = plan.cursor_message_id
        return

    if plan.window_upper_message_id is not None:
        plan.completed_through_message_id = int(plan.window_upper_message_id)
    plan.cycle_completed_at = _utc_now()
    _clear_plan_window(plan)


def _run_plan_thread(plan_id: int) -> None:
    try:
        _execute_link_check_plan(plan_id)
    finally:
        with _dispatch_lock:
            _active_plan_threads.discard(plan_id)
        try:
            claim_due_link_check_plan_runs(limit=1)
        except Exception:
            logger.exception("Failed to chain the next due link check plan")


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
    del limit

    with _dispatch_lock:
        if _active_plan_threads:
            return 0

    if get_active_task_snapshot() is not None:
        return 0

    now_utc = _utc_now()
    due_plan_id: int | None = None

    with Session(engine) as session:
        due_plan = (
            session.query(LinkCheckPlan)
            .filter(
                LinkCheckPlan.is_enabled.is_(True),
                LinkCheckPlan.next_run_at.isnot(None),
                LinkCheckPlan.next_run_at <= now_utc,
            )
            .order_by(
                LinkCheckPlan.next_run_at.asc(),
                LinkCheckPlan.schedule_priority.asc(),
                LinkCheckPlan.id.asc(),
            )
            .with_for_update(skip_locked=True)
            .first()
        )

        if due_plan is None:
            return 0

        due_plan.last_status = "pending"
        due_plan.last_error_message = None
        due_plan.next_run_at = _compute_next_run_at(due_plan, now_utc=now_utc)
        due_plan_id = int(due_plan.id)
        session.add(due_plan)
        session.commit()

    if due_plan_id is None:
        return 0
    return 1 if dispatch_link_check_plan(due_plan_id) else 0


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
        plan_mode = PLAN_MODE_BACKFILL
        cleanup_mode = "none"
        cleanup_min_consecutive_invalid_runs = 1

        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is None or not plan.is_enabled:
                return

            if get_active_task_snapshot() is not None:
                plan.last_status = "waiting"
                plan.last_error_message = "Another link check task is still running"
                plan.last_run_at = _utc_now()
                session.add(plan)
                session.commit()
                return

            plan_mode, preview = _prepare_plan_preview(session, plan, task_link_limit=task_link_limit)

            if preview["estimated_links"] <= 0:
                if plan.window_upper_message_id is not None:
                    plan.completed_through_message_id = int(plan.window_upper_message_id)
                _clear_plan_window(plan)
                plan.cycle_completed_at = _utc_now()
                plan.last_status = "idle"
                plan.last_error_message = None
                plan.last_run_at = _utc_now()
                session.add(plan)
                session.commit()
                return

            effective_concurrent = min(int(plan.max_concurrent or 1), max_concurrent_limit)
            cleanup_mode = str(plan.cleanup_mode or "none")
            cleanup_min_consecutive_invalid_runs = int(plan.cleanup_min_consecutive_invalid_runs or 1)

            task_id, _, created = start_or_reuse_task(
                preview["scope_label"],
                effective_concurrent,
                task_metadata={
                    "scope_label": preview["scope_label"],
                    "trigger_source": "scheduled",
                    "task_mode": "scheduled_batch",
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "plan_mode": plan_mode,
                },
            )
            if not created:
                plan.last_status = "waiting"
                plan.last_error_message = "Scheduled plan skipped because another task already claimed the worker"
                plan.last_run_at = _utc_now()
                session.add(plan)
                session.commit()
                return

            payload = {
                **preview,
                "scope_label": preview["scope_label"],
                "selection_mode": "smart_count",
                "task_mode": "scheduled_batch",
                "trigger_source": "scheduled",
                "plan_id": plan.id,
                "plan_name": plan.name,
                "plan_mode": plan_mode,
            }
            dispatch_task(task_id, payload, effective_concurrent)
            session.add(plan)
            session.commit()

        final_status = _wait_for_task_completion(task_id)

        with Session(engine) as session:
            plan = session.get(LinkCheckPlan, plan_id)
            if plan is None:
                return

            plan.last_run_at = _utc_now()
            plan.last_status = str(final_status.get("status") or "failed")
            plan.last_error_message = final_status.get("error")

            if final_status.get("status") == "completed":
                _update_plan_after_completed_batch(plan, preview=preview, plan_mode=plan_mode)
                session.add(plan)
                session.commit()
            else:
                session.add(plan)
                session.commit()
                return

        if cleanup_mode != "none" and final_status.get("check_time"):
            try:
                with Session(engine) as cleanup_session:
                    cleanup_result = apply_link_check_cleanup(
                        cleanup_session,
                        str(final_status["check_time"]),
                        mode=cleanup_mode,
                        dry_run=False,
                        min_consecutive_invalid_runs=cleanup_min_consecutive_invalid_runs,
                    )
                if cleanup_result.get("updated_messages") or cleanup_result.get("deleted_messages"):
                    mark_link_check_plan_overview_stale()
            except Exception:
                logger.exception("Automatic link cleanup failed for plan %s", plan_id)

        if not preview.get("has_more_messages"):
            return

    return
