from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.models.models import (
    LinkClickEvent,
    LinkTargetDailyStat,
    ResourceCandidateLog,
    ResourceWork,
    ResourceWorkAlias,
    ResourceWorkBinding,
    ensure_runtime_storage_tables,
)
from app.services.resource_ops.settings import get_resource_ops_runtime_config, update_resource_ops_runtime_meta


def run_resource_ops_retention(
    session: Session,
    *,
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)

    click_event_cutoff = date.today() - timedelta(days=max(1, int(config.get("retention_click_event_days") or 90)))
    daily_stat_cutoff = date.today() - timedelta(days=max(1, int(config.get("retention_daily_stat_days") or 365)))
    candidate_log_cutoff = date.today() - timedelta(days=max(1, int(config.get("retention_candidate_log_days") or 180)))

    deleted_click_events = (
        session.query(LinkClickEvent)
        .filter(LinkClickEvent.stat_date < click_event_cutoff)
        .delete(synchronize_session=False)
    )
    deleted_daily_stats = (
        session.query(LinkTargetDailyStat)
        .filter(LinkTargetDailyStat.stat_date < daily_stat_cutoff)
        .delete(synchronize_session=False)
    )
    deleted_candidate_logs = (
        session.query(ResourceCandidateLog)
        .filter(ResourceCandidateLog.created_at < candidate_log_cutoff)
        .delete(synchronize_session=False)
    )

    orphan_work_ids = [
        int(work_id)
        for (work_id,) in (
            session.query(ResourceWork.id)
            .filter(~exists().where(ResourceWorkBinding.work_id == ResourceWork.id))
            .all()
        )
        if work_id is not None
    ]
    deleted_orphan_aliases = 0
    deleted_orphan_works = 0
    if orphan_work_ids:
        deleted_orphan_aliases = (
            session.query(ResourceWorkAlias)
            .filter(ResourceWorkAlias.work_id.in_(orphan_work_ids))
            .delete(synchronize_session=False)
        )
        deleted_orphan_works = (
            session.query(ResourceWork)
            .filter(ResourceWork.id.in_(orphan_work_ids))
            .delete(synchronize_session=False)
        )

    summary = {
        "deleted_click_events": int(deleted_click_events or 0),
        "deleted_daily_stats": int(deleted_daily_stats or 0),
        "deleted_candidate_logs": int(deleted_candidate_logs or 0),
        "deleted_orphan_aliases": int(deleted_orphan_aliases or 0),
        "deleted_orphan_works": int(deleted_orphan_works or 0),
        "retention_click_event_days": int(config.get("retention_click_event_days") or 90),
        "retention_daily_stat_days": int(config.get("retention_daily_stat_days") or 365),
        "retention_candidate_log_days": int(config.get("retention_candidate_log_days") or 180),
    }
    update_resource_ops_runtime_meta(session, last_cleanup_summary=summary, updated_by=operator or "system")
    return summary
