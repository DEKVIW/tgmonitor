from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.models import (
    Channel,
    LearningChannelConfig,
    LearningResourceProcessLog,
    LearningResourceSupplementRun,
    LearningResourceTransferJob,
    LearningResourceAutomationTask,
    LearningResourceAutomationTaskChannel,
    LearningResourceAutomationTaskTarget,
    LinkTarget,
    MonitorRawMessage,
    Message,
    PanTransferAccount,
    PanTransferBatch,
    PanTransferBatchItem,
    engine,
    ensure_runtime_storage_tables,
)
from app.services.link_check.constants import PLATFORM_QUARK
from app.utils.channel_utils import normalize_channel_username


ACTIVE_LEARNING_JOB_STATUSES = {"queued", "transferring", "retry_wait"}
FAILED_LEARNING_JOB_STATUSES = {"failed"}


def _normalize_learning_root(value: Any) -> str:
    parts = [part.strip() for part in str(value or "").replace("\\", "/").split("/")]
    return "/".join(part for part in parts if part and part not in {".", ".."})[:255]


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_learning_filter_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def is_learning_target_enabled(session: Session, extra_json: dict[str, Any]) -> bool:
    """Check the target before a worker starts a network request.

    Pausing a task stops new messages from entering the queue. Jobs that were
    already queued (including a manual catch-up run) are allowed to finish.
    Target removal, account disablement, or task deletion still stops them.
    """
    task_id = extra_json.get("learning_task_id")
    target_id = extra_json.get("learning_target_id")
    if task_id and target_id:
        task = session.get(LearningResourceAutomationTask, int(task_id))
        target = session.get(LearningResourceAutomationTaskTarget, int(target_id))
        if task is None or str(getattr(task, "status", "") or "") == "deleted" or target is None or str(task.transfer_policy or "automatic") != "automatic" or not bool(target.is_enabled):
            return False
        account = session.get(PanTransferAccount, int(target.target_account_id))
        return bool(
            account
            and account.is_enabled
            and str(account.platform or "") == PLATFORM_QUARK
            and bool(target.save_root_name or account.default_save_root)
        )

    channel_key = str(extra_json.get("learning_channel_key") or "").strip()
    if not channel_key:
        return True
    config = (
        session.query(LearningChannelConfig)
        .filter(LearningChannelConfig.channel_key == channel_key)
        .first()
    )
    return bool(config and config.is_enabled)


def refresh_learning_automation_task_health(session: Session, task_id: int) -> LearningResourceAutomationTask | None:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None:
        return None
    if str(task.status or "") == "deleted":
        return task
    pending_count = int(
        session.query(func.count(LearningResourceTransferJob.id))
        .filter(
            LearningResourceTransferJob.task_id == int(task.id),
            LearningResourceTransferJob.status.in_(sorted(ACTIVE_LEARNING_JOB_STATUSES)),
        )
        .scalar()
        or 0
    )
    failed_count = int(
        session.query(func.count(LearningResourceTransferJob.id))
        .filter(
            LearningResourceTransferJob.task_id == int(task.id),
            LearningResourceTransferJob.status.in_(sorted(FAILED_LEARNING_JOB_STATUSES)),
        )
        .scalar()
        or 0
    )
    for target in session.query(LearningResourceAutomationTaskTarget).filter(
        LearningResourceAutomationTaskTarget.task_id == int(task.id),
    ).all():
        account = session.get(PanTransferAccount, int(target.target_account_id))
        root = _normalize_learning_root(str(target.save_root_name or (account.default_save_root if account else "") or ""))
        if account is None or not bool(account.is_enabled) or str(account.platform or "") != PLATFORM_QUARK:
            target.status = "waiting_account"
        elif not root:
            target.status = "waiting_root"
        else:
            target.status = "ready"
        session.add(target)

    enabled_channel = (
        session.query(LearningResourceAutomationTaskChannel.id)
        .filter(
            LearningResourceAutomationTaskChannel.task_id == int(task.id),
            LearningResourceAutomationTaskChannel.is_enabled.is_(True),
        )
        .first()
    )
    enabled_target = (
        session.query(LearningResourceAutomationTaskTarget.id)
        .filter(
            LearningResourceAutomationTaskTarget.task_id == int(task.id),
            LearningResourceAutomationTaskTarget.is_enabled.is_(True),
            LearningResourceAutomationTaskTarget.status == "ready",
        )
        .first()
    )
    task.pending_count = pending_count
    task.failed_count = failed_count
    if failed_count:
        latest_failed = session.query(LearningResourceTransferJob).filter(
            LearningResourceTransferJob.task_id == int(task.id),
            LearningResourceTransferJob.status.in_(sorted(FAILED_LEARNING_JOB_STATUSES)),
        ).order_by(LearningResourceTransferJob.updated_at.desc(), LearningResourceTransferJob.id.desc()).first()
        task.last_error_message = str(latest_failed.last_error_message or "存在失败的学习资料转存任务") if latest_failed else task.last_error_message
    if not bool(task.is_enabled):
        task.status = "paused"
    elif enabled_channel is None or enabled_target is None:
        task.status = "invalid"
    elif failed_count:
        task.status = "degraded"
    elif pending_count:
        task.status = "running"
    else:
        task.status = "waiting"
    session.add(task)
    return task


def _channel_key(channel: Channel) -> str:
    try:
        return normalize_channel_username(channel.username)
    except ValueError:
        return str(channel.username or "").strip()[:255]


def _serialize_task_channel(session: Session, row: LearningResourceAutomationTaskChannel) -> dict[str, Any]:
    channel = session.get(Channel, int(row.channel_id))
    config = None
    if channel is not None:
        config = (
            session.query(LearningChannelConfig)
            .filter(LearningChannelConfig.channel_key == _channel_key(channel))
            .first()
        )
    return {
        "id": int(row.id),
        "channel_id": int(row.channel_id),
        "channel_key": _channel_key(channel) if channel is not None else "",
        "channel_title": str((config.channel_title if config else None) or (channel.username if channel else "")),
        "is_enabled": bool(row.is_enabled),
        "default_category_id": int(row.default_category_id) if row.default_category_id else None,
        "last_processed_message_id": int(row.last_processed_message_id) if row.last_processed_message_id else None,
        "last_processed_telegram_message_id": int(row.last_processed_telegram_message_id) if row.last_processed_telegram_message_id else None,
    }


def _serialize_task_target(session: Session, row: LearningResourceAutomationTaskTarget) -> dict[str, Any]:
    account = session.get(PanTransferAccount, int(row.target_account_id))
    return {
        "id": int(row.id),
        "target_account_id": int(row.target_account_id),
        "account_name": str(account.account_name or "") if account else "",
        "platform": str(account.platform or "") if account else "",
        "save_root_id": str(row.save_root_id or "0"),
        "save_root_name": str(row.save_root_name or ""),
        "auto_create_category_dirs": bool(row.auto_create_category_dirs),
        "is_enabled": bool(row.is_enabled),
        "status": str(row.status or "waiting_account"),
        "last_success_at": row.last_success_at,
        "last_error_message": str(row.last_error_message or "") or None,
    }


def _serialize_learning_task(session: Session, task: LearningResourceAutomationTask) -> dict[str, Any]:
    return {
        "id": int(task.id),
        "name": str(task.name or ""),
        "is_enabled": bool(task.is_enabled),
        "transfer_policy": str(task.transfer_policy or "automatic"),
        "backfill_policy": str(task.backfill_policy or "new_messages_only"),
        "status": str(task.status or "paused"),
        "pending_count": int(task.pending_count or 0),
        "failed_count": int(task.failed_count or 0),
        "last_enqueued_at": task.last_enqueued_at,
        "last_success_at": task.last_success_at,
        "last_error_message": str(task.last_error_message or "") or None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "channels": [
            _serialize_task_channel(session, row)
            for row in session.query(LearningResourceAutomationTaskChannel)
            .filter(LearningResourceAutomationTaskChannel.task_id == int(task.id))
            .order_by(LearningResourceAutomationTaskChannel.id.asc())
            .all()
        ],
        "targets": [
            _serialize_task_target(session, row)
            for row in session.query(LearningResourceAutomationTaskTarget)
            .filter(LearningResourceAutomationTaskTarget.task_id == int(task.id))
            .order_by(LearningResourceAutomationTaskTarget.id.asc())
            .all()
        ],
    }


def list_learning_automation_tasks(session: Session) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    tasks = session.query(LearningResourceAutomationTask).filter(
        LearningResourceAutomationTask.status != "deleted",
    ).order_by(
        LearningResourceAutomationTask.updated_at.desc(),
        LearningResourceAutomationTask.id.desc(),
    ).all()
    for task in tasks:
        refresh_learning_automation_task_health(session, int(task.id))
    session.flush()
    return [_serialize_learning_task(session, task) for task in tasks]


def get_learning_automation_task(session: Session, task_id: int) -> dict[str, Any] | None:
    ensure_runtime_storage_tables()
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        return None
    refresh_learning_automation_task_health(session, int(task.id))
    session.flush()
    return _serialize_learning_task(session, task)


def _validate_task_channels(session: Session, channel_specs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in channel_specs:
        channel_id = int(raw.get("channel_id") or 0)
        if channel_id <= 0 or channel_id in seen:
            continue
        channel = session.get(Channel, channel_id)
        if channel is None:
            raise ValueError(f"监听频道不存在：{channel_id}")
        seen.add(channel_id)
        normalized.append({
            "id": int(raw.get("id") or 0) or None,
            "channel_id": channel_id,
            "is_enabled": bool(raw.get("is_enabled", True)),
            "default_category_id": int(raw.get("default_category_id") or 0) or None,
        })
    if not normalized:
        raise ValueError("至少选择一个监听频道")
    return normalized


def _validate_task_targets(session: Session, target_specs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for raw in target_specs:
        account_id = int(raw.get("target_account_id") or 0)
        if account_id <= 0:
            raise ValueError("每个转存目标都必须选择网盘账号")
        account = session.get(PanTransferAccount, account_id)
        if account is None or not bool(account.is_enabled) or str(account.platform or "") != PLATFORM_QUARK:
            raise ValueError("转存目标必须是已启用的夸克网盘账号")
        root_id = str(raw.get("save_root_id") or "0").strip()[:255] or "0"
        root_name = _normalize_learning_root(str(raw.get("save_root_name") or ""))
        if not root_name:
            root_name = _normalize_learning_root(str(account.default_save_root or ""))
        if not root_name:
            raise ValueError(f"账号“{account.account_name}”没有配置默认保存目录，请选择目录")
        scope = (account_id, root_id)
        if scope in seen:
            continue
        seen.add(scope)
        normalized.append({
            "id": int(raw.get("id") or 0) or None,
            "target_account_id": account_id,
            "save_root_id": root_id,
            "save_root_name": root_name,
            "auto_create_category_dirs": bool(raw.get("auto_create_category_dirs", True)),
            "is_enabled": bool(raw.get("is_enabled", True)),
        })
    if not normalized:
        raise ValueError("至少配置一个转存目标")
    return normalized


def _pause_task_jobs(session: Session, task_id: int, target_ids: set[int] | None = None) -> int:
    from app.services.pan_transfer.queue import refresh_pan_transfer_batch_summary

    query = session.query(LearningResourceTransferJob).filter(
        LearningResourceTransferJob.task_id == int(task_id),
        LearningResourceTransferJob.status == "queued",
    )
    jobs = query.all()
    changed = 0
    for job in jobs:
        if target_ids:
            item = session.get(PanTransferBatchItem, int(job.batch_item_id)) if job.batch_item_id else None
            job_target_id = dict(item.extra_json or {}).get("learning_target_id") if item is not None else None
            if job_target_id is None or int(job_target_id) not in target_ids:
                continue
        if job.batch_item_id:
            item = session.get(PanTransferBatchItem, int(job.batch_item_id))
            if item is not None and item.transfer_status == "queued":
                item.transfer_status = "paused"
                item.next_retry_at = None
                session.add(item)
                refresh_pan_transfer_batch_summary(session, batch_id=int(item.batch_id))
        job.status = "paused"
        session.add(job)
        changed += 1
    session.flush()
    return changed


def _resume_task_jobs(session: Session, task_id: int, target_ids: set[int] | None = None) -> int:
    allowed_target_ids = target_ids or {
        int(row.id)
        for row in session.query(LearningResourceAutomationTaskTarget).filter(
            LearningResourceAutomationTaskTarget.task_id == int(task_id),
            LearningResourceAutomationTaskTarget.is_enabled.is_(True),
            LearningResourceAutomationTaskTarget.status == "ready",
        ).all()
    }
    jobs = session.query(LearningResourceTransferJob).filter(
        LearningResourceTransferJob.task_id == int(task_id),
        LearningResourceTransferJob.status == "paused",
    ).all()
    changed = 0
    for job in jobs:
        item = session.get(PanTransferBatchItem, int(job.batch_item_id)) if job.batch_item_id else None
        job_target_id = dict(item.extra_json or {}).get("learning_target_id") if item is not None else None
        if job_target_id is not None and int(job_target_id) not in allowed_target_ids:
            continue
        if job_target_id is None and len(allowed_target_ids) != 1:
            continue
        if job.batch_item_id:
            item = session.get(PanTransferBatchItem, int(job.batch_item_id))
            if item is not None and item.transfer_status == "paused":
                item.transfer_status = "queued"
                item.next_retry_at = None
                item.error_message = None
                session.add(item)
                batch = session.get(PanTransferBatch, int(item.batch_id))
                if batch is not None:
                    batch.status = "running"
                    batch.finished_at = None
                    session.add(batch)
        job.status = "queued"
        job.last_error_message = None
        session.add(job)
        changed += 1
    session.flush()
    return changed


def save_learning_automation_task(
    session: Session,
    *,
    task_id: int | None,
    payload: dict[str, Any],
    operator: str,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = session.get(LearningResourceAutomationTask, int(task_id)) if task_id else None
    if task_id and (task is None or str(task.status or "") == "deleted"):
        raise LookupError("学习资料自动任务不存在")
    channel_specs = _validate_task_channels(payload.get("channels") or [])
    target_specs = _validate_task_targets(payload.get("targets") or [])
    is_enabled = bool(payload.get("is_enabled", task.is_enabled if task is not None else False))
    name = str(payload.get("name") or (task.name if task is not None else "学习资料自动转存")).strip()[:255]
    if not name:
        raise ValueError("任务名称不能为空")
    if task is None:
        task = LearningResourceAutomationTask(
            name=name,
            is_enabled=is_enabled,
            transfer_policy="automatic",
            backfill_policy="new_messages_only",
            status="paused",
            created_by=operator,
        )
        session.add(task)
        session.flush()
    task.name = name
    task.is_enabled = is_enabled
    task.transfer_policy = "automatic"
    task.backfill_policy = str(payload.get("backfill_policy") or task.backfill_policy or "new_messages_only")[:32]
    task.updated_by = operator
    task.last_error_message = None
    session.add(task)
    if task.legacy_config_id:
        legacy_config = session.get(LearningChannelConfig, int(task.legacy_config_id))
        if legacy_config is not None:
            legacy_config.is_enabled = is_enabled
            session.add(legacy_config)
    session.flush()

    existing_channels = {
        int(row.id): row
        for row in session.query(LearningResourceAutomationTaskChannel)
        .filter(LearningResourceAutomationTaskChannel.task_id == int(task.id))
        .all()
    }
    kept_channel_ids: set[int] = set()
    for spec in channel_specs:
        row = existing_channels.get(spec["id"]) if spec["id"] else None
        if row is None:
            row = LearningResourceAutomationTaskChannel(task_id=int(task.id), channel_id=spec["channel_id"])
        row.channel_id = spec["channel_id"]
        row.is_enabled = spec["is_enabled"]
        row.default_category_id = spec["default_category_id"]
        session.add(row)
        session.flush()
        kept_channel_ids.add(int(row.id))
    for row_id, row in existing_channels.items():
        if row_id not in kept_channel_ids:
            session.delete(row)

    existing_targets = {
        int(row.id): row
        for row in session.query(LearningResourceAutomationTaskTarget)
        .filter(LearningResourceAutomationTaskTarget.task_id == int(task.id))
        .all()
    }
    kept_target_ids: set[int] = set()
    for spec in target_specs:
        row = existing_targets.get(spec["id"]) if spec["id"] else None
        if row is None:
            row = LearningResourceAutomationTaskTarget(task_id=int(task.id), target_account_id=spec["target_account_id"])
        row.target_account_id = spec["target_account_id"]
        row.save_root_id = spec["save_root_id"]
        row.save_root_name = spec["save_root_name"]
        row.auto_create_category_dirs = spec["auto_create_category_dirs"]
        row.is_enabled = spec["is_enabled"]
        session.add(row)
        session.flush()
        kept_target_ids.add(int(row.id))
    removed_targets = set(existing_targets) - kept_target_ids
    if removed_targets:
        _pause_task_jobs(session, int(task.id), removed_targets)
        for row_id in removed_targets:
            session.delete(existing_targets[row_id])

    session.flush()
    if is_enabled:
        refreshed = refresh_learning_automation_task_health(session, int(task.id))
        if refreshed is None or refreshed.status == "invalid":
            raise ValueError("任务开启前必须至少有一个启用频道和一个可用转存目标")
        _resume_task_jobs(session, int(task.id))
    refresh_learning_automation_task_health(session, int(task.id))
    from app.services.learning_resources import _record_learning_process_log

    _record_learning_process_log(
        session,
        stage="config",
        message=f"已保存自动任务配置：{'已启动' if task.is_enabled else '已暂停'}",
        task_id=int(task.id),
        details={
            "operator": operator,
            "enabled": bool(task.is_enabled),
            "channel_count": len(channel_specs),
            "target_count": len(target_specs),
        },
    )
    session.flush()
    return _serialize_learning_task(session, task)


def set_learning_automation_task_enabled(session: Session, *, task_id: int, enabled: bool) -> dict[str, Any]:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    if enabled:
        task.is_enabled = True
        refresh_learning_automation_task_health(session, int(task.id))
        if task.status == "invalid":
            task.is_enabled = False
            refresh_learning_automation_task_health(session, int(task.id))
            raise ValueError("任务配置不完整，无法启动")
        _resume_task_jobs(session, int(task.id))
    else:
        task.is_enabled = False
    if task.legacy_config_id:
        legacy_config = session.get(LearningChannelConfig, int(task.legacy_config_id))
        if legacy_config is not None:
            legacy_config.is_enabled = bool(enabled)
            session.add(legacy_config)
    session.add(task)
    refresh_learning_automation_task_health(session, int(task.id))
    from app.services.learning_resources import _record_learning_process_log

    _record_learning_process_log(
        session,
        stage="config",
        message=f"自动任务已{'恢复' if enabled else '暂停'}",
        task_id=int(task.id),
        details={"enabled": bool(enabled)},
    )
    session.flush()
    return _serialize_learning_task(session, task)


def delete_learning_automation_task(session: Session, *, task_id: int) -> dict[str, Any]:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    unfinished_count = int(
        session.query(func.count(LearningResourceTransferJob.id))
        .filter(
            LearningResourceTransferJob.task_id == int(task.id),
            LearningResourceTransferJob.status.in_(sorted(ACTIVE_LEARNING_JOB_STATUSES | {"paused"})),
        )
        .scalar()
        or 0
    )
    if unfinished_count:
        raise ValueError(f"任务还有 {unfinished_count} 个未完成转存项，请先等待处理完成或清理补处理批次")

    session.query(LearningResourceProcessLog).filter(
        LearningResourceProcessLog.task_id == int(task.id),
    ).delete(synchronize_session=False)
    session.query(LearningResourceAutomationTaskChannel).filter(
        LearningResourceAutomationTaskChannel.task_id == int(task.id),
    ).delete(synchronize_session=False)
    session.query(LearningResourceAutomationTaskTarget).filter(
        LearningResourceAutomationTaskTarget.task_id == int(task.id),
    ).delete(synchronize_session=False)

    if task.legacy_config_id:
        # Keep a tombstone so the compatibility migration cannot recreate the task.
        legacy_config = session.get(LearningChannelConfig, int(task.legacy_config_id))
        if legacy_config is not None:
            legacy_config.is_enabled = False
            session.add(legacy_config)
        task.is_enabled = False
        task.status = "deleted"
        task.pending_count = 0
        task.failed_count = 0
        task.last_error_message = None
        session.add(task)
    else:
        session.delete(task)
    session.flush()
    return {
        "task_id": int(task_id),
        "deleted": True,
        "preserved_resources": True,
        "preserved_remote_files": True,
    }


def _ensure_task_channel_checkpoint(session: Session, row: LearningResourceAutomationTaskChannel) -> int | None:
    if row.last_processed_telegram_message_id is not None:
        return int(row.last_processed_telegram_message_id)

    if row.last_processed_message_id is not None:
        legacy_message = session.get(Message, int(row.last_processed_message_id))
        if legacy_message is not None and legacy_message.monitor_message_id is not None:
            row.last_processed_telegram_message_id = int(legacy_message.monitor_message_id)
            session.add(row)
            session.flush()
            return int(row.last_processed_telegram_message_id)
        return None

    channel = session.get(Channel, int(row.channel_id))
    if channel is None:
        return None
    channel_key = _channel_key(channel)
    legacy_config = session.query(LearningChannelConfig).filter(
        LearningChannelConfig.channel_key == channel_key,
    ).first()
    legacy_checkpoint = int(legacy_config.last_processed_message_id or 0) if legacy_config else 0
    if legacy_checkpoint > 0:
        row.last_processed_message_id = legacy_checkpoint
    else:
        channel_keys = {channel_key, f"@{channel_key}"}
        latest_raw_message = session.query(MonitorRawMessage).filter(
            or_(
                MonitorRawMessage.monitor_channel_config_id == int(row.channel_id),
                MonitorRawMessage.monitor_channel_key.in_(sorted(channel_keys)),
            )
        ).order_by(MonitorRawMessage.monitor_message_id.desc()).first()
        latest_message = session.query(Message).filter(
            or_(
                Message.monitor_channel_config_id == int(row.channel_id),
                Message.monitor_channel_key.in_(sorted(channel_keys)),
            )
        ).order_by(Message.id.desc()).first()
        row.last_processed_message_id = int(latest_message.id) if latest_message is not None else None
        row.last_processed_telegram_message_id = (
            int(latest_raw_message.monitor_message_id)
            if latest_raw_message is not None
            else int(latest_message.monitor_message_id)
            if latest_message is not None and latest_message.monitor_message_id is not None
            else None
        )
    session.add(row)
    session.flush()
    return int(row.last_processed_telegram_message_id) if row.last_processed_telegram_message_id else None


def sync_legacy_learning_channel_config(
    session: Session,
    *,
    config: LearningChannelConfig,
    channel_id: int,
    operator: str,
) -> None:
    """Keep the deprecated one-channel endpoint compatible after migration."""
    task = session.query(LearningResourceAutomationTask).filter(
        LearningResourceAutomationTask.legacy_config_id == int(config.id),
    ).first()
    if task is None or str(task.status or "") == "deleted":
        return
    task.name = str(config.channel_title or config.channel_key or task.name)[:255]
    task.is_enabled = bool(config.is_enabled)
    task.backfill_policy = str(config.backfill_policy or "new_messages_only")[:32]
    task.updated_by = operator
    session.add(task)
    channel_row = session.query(LearningResourceAutomationTaskChannel).filter(
        LearningResourceAutomationTaskChannel.task_id == int(task.id),
        LearningResourceAutomationTaskChannel.channel_id == int(channel_id),
    ).first()
    if channel_row is None:
        channel_row = LearningResourceAutomationTaskChannel(
            task_id=int(task.id),
            channel_id=int(channel_id),
        )
    channel_row.is_enabled = bool(config.is_enabled)
    session.add(channel_row)

    desired_account_id = int(config.target_account_id) if config.target_account_id else None
    account = session.get(PanTransferAccount, desired_account_id) if desired_account_id else None
    desired_root = _normalize_learning_root(str(config.save_root or (account.default_save_root if account else "") or ""))
    targets = session.query(LearningResourceAutomationTaskTarget).filter(
        LearningResourceAutomationTaskTarget.task_id == int(task.id),
    ).all()
    matched = None
    for target in targets:
        same_scope = desired_account_id is not None and int(target.target_account_id) == desired_account_id and str(target.save_root_name or "") == desired_root
        target.is_enabled = bool(config.is_enabled and same_scope)
        if same_scope:
            matched = target
        session.add(target)
    if desired_account_id is not None and desired_root and matched is None:
        matched = LearningResourceAutomationTaskTarget(
            task_id=int(task.id),
            target_account_id=desired_account_id,
            save_root_id=f"path:{desired_root}",
            save_root_name=desired_root,
            is_enabled=bool(config.is_enabled),
            status="ready" if account is not None and bool(account.is_enabled) else "waiting_account",
        )
        session.add(matched)
    session.flush()
    refresh_learning_automation_task_health(session, int(task.id))


def _message_source_key(message: Message) -> tuple[str, int | str]:
    return (
        str(message.monitor_channel_key or "").strip(),
        int(message.monitor_message_id)
        if message.monitor_message_id is not None
        else f"db:{int(message.id)}",
    )


def _load_learning_source_groups(
    session: Session,
    *,
    task_channels: list[LearningResourceAutomationTaskChannel],
    mode: str,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    recent_limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load parsed rows grouped by their original Telegram message.

    ``messages.id`` identifies a parsed row. ``monitor_message_id`` identifies
    the original Telegram message and is the only cursor used for checkpoint
    scans. Older imported rows without that field remain addressable through
    the legacy explicit-ID endpoint.
    """
    from app.services.learning_resources import _display_title, _find_quark_refs

    grouped: dict[tuple[str, int | str], dict[str, Any]] = {}
    for channel_row in task_channels:
        channel = session.get(Channel, int(channel_row.channel_id))
        channel_key = _channel_key(channel) if channel is not None else ""
        row_channel_keys = {channel_key, f"@{channel_key}"} if channel_key else set()
        checkpoint = _ensure_task_channel_checkpoint(session, channel_row)

        raw_query = session.query(MonitorRawMessage).filter(
            or_(
                MonitorRawMessage.monitor_channel_config_id == int(channel_row.channel_id),
                MonitorRawMessage.monitor_channel_key.in_(sorted(row_channel_keys)) if row_channel_keys else False,
            )
        )
        if mode == "checkpoint":
            if checkpoint is not None:
                raw_query = raw_query.filter(MonitorRawMessage.monitor_message_id > int(checkpoint))
        elif mode == "date_range":
            if from_at is not None:
                raw_query = raw_query.filter(MonitorRawMessage.timestamp >= from_at)
            if to_at is not None:
                raw_query = raw_query.filter(MonitorRawMessage.timestamp <= to_at)
        raw_order = (
            MonitorRawMessage.monitor_message_id.desc()
            if mode == "recent"
            else MonitorRawMessage.monitor_message_id.asc()
        )
        raw_rows = raw_query.order_by(raw_order).limit(20000).all()
        for raw_message in raw_rows:
            source_key = (str(raw_message.monitor_channel_key or "").strip(), int(raw_message.monitor_message_id))
            message_query = session.query(Message).filter(
                Message.monitor_message_id == int(raw_message.monitor_message_id),
                or_(
                    Message.monitor_chat_id == int(raw_message.monitor_chat_id),
                    Message.monitor_channel_key == str(raw_message.monitor_channel_key or "").strip(),
                ),
            )
            grouped[source_key] = {
                "channel_id": int(channel_row.channel_id),
                "rows": message_query.order_by(Message.id.asc()).all(),
                "raw": raw_message,
            }

        # Backward compatibility for messages saved before monitor_raw_messages
        # existed. New messages are represented by the raw table above, while
        # these rows fill only source messages that have no raw snapshot yet.
        message_query = session.query(Message).filter(
            or_(
                Message.monitor_channel_config_id == int(channel_row.channel_id),
                Message.monitor_channel_key.in_(sorted(row_channel_keys)) if row_channel_keys else False,
            ),
            Message.monitor_message_id.isnot(None),
        )
        if mode == "checkpoint":
            if checkpoint is not None:
                message_query = message_query.filter(Message.monitor_message_id > int(checkpoint))
            elif channel_row.last_processed_message_id is not None:
                message_query = message_query.filter(Message.id > int(channel_row.last_processed_message_id))
        elif mode == "date_range":
            if from_at is not None:
                message_query = message_query.filter(Message.timestamp >= from_at)
            if to_at is not None:
                message_query = message_query.filter(Message.timestamp <= to_at)
        message_order = (
            Message.monitor_message_id.desc()
            if mode == "recent"
            else Message.monitor_message_id.asc()
        )
        message_rows = message_query.order_by(message_order, Message.id.asc()).limit(20000).all()
        for message in message_rows:
            source_key = _message_source_key(message)
            entry = grouped.setdefault(
                source_key,
                {"channel_id": int(channel_row.channel_id), "rows": [], "raw": None},
            )
            existing_ids = {int(row.id) for row in entry["rows"]}
            if int(message.id) not in existing_ids:
                entry["rows"].append(message)

    groups: list[dict[str, Any]] = []
    for source_key, entry in grouped.items():
        rows = list(entry["rows"])
        raw_message = entry.get("raw")
        rows.sort(key=lambda item: int(item.id))
        refs: list[tuple[Message, LinkTarget]] = []
        for message in rows:
            refs.extend(
                (message, target)
                for _, target in _find_quark_refs(session, int(message.id))
            )
        raw_text = str(raw_message.raw_text or "").strip() if raw_message is not None else ""
        if not raw_text:
            raw_text = next((str(row.monitor_raw_text or "").strip() for row in rows if row.monitor_raw_text), "")
        titles = []
        for row in rows:
            title = _display_title(row)
            if title and title not in titles:
                titles.append(title)
        timestamp = raw_message.timestamp if raw_message is not None else max(
            (row.timestamp for row in rows if row.timestamp is not None),
            default=None,
        )
        groups.append({
            "source_key": source_key,
            "channel_id": int(entry["channel_id"]),
            "rows": rows,
            "refs": refs,
            "monitor_message_id": int(raw_message.monitor_message_id)
            if raw_message is not None
            else int(rows[0].monitor_message_id)
            if rows and rows[0].monitor_message_id is not None
            else None,
            "channel_key": str(raw_message.monitor_channel_key or "").strip()
            if raw_message is not None
            else str(rows[0].monitor_channel_key or "").strip()
            if rows
            else str(source_key[0] or ""),
            "timestamp": timestamp,
            "raw_text": raw_text,
            "titles": titles,
            "valid_row_ids": {int(message.id) for message, _ in refs},
            "valid": bool(refs),
        })

    groups.sort(key=lambda group: (
        group["timestamp"] or datetime.min,
        int(group["monitor_message_id"] or 0),
    ))
    if mode == "recent":
        selected: list[dict[str, Any]] = []
        valid_count = 0
        for group in reversed(groups):
            selected.append(group)
            if group["valid"]:
                valid_count += 1
            if valid_count >= max(1, min(int(recent_limit or 10), 5000)):
                break
        groups = list(reversed(selected))
    elif mode == "checkpoint":
        groups = groups[:5000]
    else:
        groups = groups[:5000]
    return groups


def _serialize_learning_source_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "channel": str(group["channel_key"] or ""),
        "monitor_message_id": group["monitor_message_id"],
        "message_time": group["timestamp"],
        "raw_text": str(group["raw_text"] or "") or None,
        "raw_text_available": bool(group["raw_text"]),
        "resource_titles": list(group["titles"]),
        "resource_count": len(group["valid_row_ids"]),
        "link_count": len(group["refs"]),
        "valid": bool(group["valid"]),
    }


def _build_learning_supplement_plan(
    session: Session,
    *,
    task_id: int,
    mode: str = "checkpoint",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    recent_limit: int | None = None,
) -> dict[str, Any]:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    refresh_learning_automation_task_health(session, int(task.id))
    if task.status == "invalid":
        raise ValueError("任务配置不完整，请先修正频道或转存目标")
    normalized_mode = str(mode or "checkpoint").strip().lower()
    from_at = _normalize_learning_filter_datetime(from_at)
    to_at = _normalize_learning_filter_datetime(to_at)
    if normalized_mode not in {"checkpoint", "date_range", "recent"}:
        raise ValueError("补充更新方式不正确")
    if normalized_mode == "date_range" and from_at is None and to_at is None:
        raise ValueError("按日期范围补充时必须选择时间范围")
    if normalized_mode == "date_range" and from_at is not None and to_at is not None and from_at > to_at:
        raise ValueError("补充更新的开始时间不能晚于结束时间")
    channel_rows = session.query(LearningResourceAutomationTaskChannel).filter(
        LearningResourceAutomationTaskChannel.task_id == int(task.id),
        LearningResourceAutomationTaskChannel.is_enabled.is_(True),
    ).all()
    if not channel_rows:
        raise ValueError("任务没有启用的监听频道")
    groups = _load_learning_source_groups(
        session,
        task_channels=channel_rows,
        mode=normalized_mode,
        from_at=from_at,
        to_at=to_at,
        recent_limit=recent_limit,
    )
    selected_groups = [group for group in groups if group["valid"]]
    selected_ids = [int(row.id) for group in groups for row in group["rows"]]
    valid_message_count = len(selected_groups)
    skipped_message_count = len(groups) - valid_message_count
    resource_count = sum(len(group["valid_row_ids"]) for group in selected_groups)
    link_count = sum(len(group["refs"]) for group in selected_groups)
    return {
        "task_id": int(task.id),
        "mode": normalized_mode,
        "groups": groups,
        "source_groups": [
            {
                "channel_id": int(group["channel_id"]),
                "channel_key": str(group["channel_key"] or ""),
                "monitor_message_id": int(group["monitor_message_id"]),
                "message_ids": [int(row.id) for row in group["rows"]],
            }
            for group in groups
            if group["monitor_message_id"] is not None
        ],
        "selected_ids": selected_ids,
        "scanned_messages": len(groups),
        "selected_messages": valid_message_count,
        "valid_messages": valid_message_count,
        "skipped_messages": skipped_message_count,
        "resources": resource_count,
        "links": link_count,
        "message_previews": [_serialize_learning_source_group(group) for group in groups[:50]],
    }


def process_learning_automation_task_now(
    session: Session,
    *,
    task_id: int,
    message_ids: Iterable[int] | None = None,
    from_message_id: int | None = None,
    to_message_id: int | None = None,
    mode: str = "checkpoint",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    recent_limit: int | None = None,
    dry_run: bool = False,
    operator: str = "admin",
    supplement_run_id: int | None = None,
    allow_paused_task: bool = True,
) -> dict[str, Any]:
    from app.services.learning_resources import (
        _record_learning_process_log,
        enqueue_learning_resources_for_message_ids,
    )

    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    normalized_ids = sorted({int(value) for value in (message_ids or []) if int(value) > 0})
    plan: dict[str, Any]
    if normalized_ids or from_message_id is not None or to_message_id is not None:
        channel_rows = session.query(LearningResourceAutomationTaskChannel).filter(
            LearningResourceAutomationTaskChannel.task_id == int(task.id),
            LearningResourceAutomationTaskChannel.is_enabled.is_(True),
        ).all()
        channel_ids = {int(row.channel_id) for row in channel_rows}
        channel_keys: set[str] = set()
        for channel_row in channel_rows:
            channel = session.get(Channel, int(channel_row.channel_id))
            channel_key = _channel_key(channel) if channel is not None else ""
            if channel_key:
                channel_keys.update({channel_key, f"@{channel_key}"})
        channel_filter = or_(
            Message.monitor_channel_config_id.in_(sorted(channel_ids)),
            Message.monitor_channel_key.in_(sorted(channel_keys)) if channel_keys else False,
        )
        query = session.query(Message).filter(
            channel_filter,
            Message.id.in_(normalized_ids) if normalized_ids else True,
        )
        if from_message_id is not None:
            query = query.filter(Message.id >= int(from_message_id))
        if to_message_id is not None:
            query = query.filter(Message.id <= int(to_message_id))
        selected_ids = [int(message.id) for message in query.order_by(Message.id.asc()).limit(5000).all()]
        plan = {
            "task_id": int(task.id),
            "mode": "explicit_records",
            "selected_ids": selected_ids,
            "scanned_messages": len(selected_ids),
            "selected_messages": len(selected_ids),
            "valid_messages": len(selected_ids),
            "skipped_messages": 0,
            "resources": len(selected_ids),
            "links": 0,
            "message_previews": [],
        }
    else:
        plan = _build_learning_supplement_plan(
            session,
            task_id=int(task.id),
            mode=mode,
            from_at=from_at,
            to_at=to_at,
            recent_limit=recent_limit,
        )
    selected_ids = list(plan["selected_ids"])
    if dry_run:
        return {
            "task_id": int(task.id),
            "mode": plan["mode"],
            "selected_messages": int(plan["selected_messages"]),
            "scanned_messages": int(plan["scanned_messages"]),
            "valid_messages": int(plan["valid_messages"]),
            "skipped_messages": int(plan["skipped_messages"]),
            "resources": int(plan["resources"]),
            "links": int(plan["links"]),
            "message_ids": selected_ids[:5000],
            "message_previews": plan["message_previews"],
            "dry_run": True,
        }
    result = enqueue_learning_resources_for_message_ids(
        session,
        selected_ids,
        operator=operator,
        task_id=int(task.id),
        supplement_run_id=supplement_run_id,
        allow_paused_task=allow_paused_task,
    )
    task.last_enqueued_at = _utcnow() if result.get("jobs") else task.last_enqueued_at
    session.add(task)
    refresh_learning_automation_task_health(session, int(task.id))
    _record_learning_process_log(
        session,
        stage="replay",
        message=(
            f"补充更新完成：扫描 {int(plan['scanned_messages'])} 条原始消息，"
            f"有效 {int(plan['valid_messages'])} 条，新增 {int(result.get('jobs') or 0)} 个转存任务"
        ),
        task_id=int(task.id),
        supplement_run_id=supplement_run_id,
        details={
            "message_ids": selected_ids[:500],
            "result": result,
            "mode": plan["mode"],
            "scanned_messages": int(plan["scanned_messages"]),
            "valid_messages": int(plan["valid_messages"]),
            "skipped_messages": int(plan["skipped_messages"]),
        },
    )
    session.flush()
    return {
        "task_id": int(task.id),
        "mode": plan["mode"],
        "selected_messages": int(plan["selected_messages"]),
        "scanned_messages": int(plan["scanned_messages"]),
        "valid_messages": int(plan["valid_messages"]),
        "skipped_messages": int(plan["skipped_messages"]),
        "resources": int(plan["resources"]),
        "links": int(plan["links"]),
        "message_previews": plan["message_previews"],
        "dry_run": False,
        **result,
    }


def _serialize_supplement_run(run: LearningResourceSupplementRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "task_id": int(run.task_id),
        "mode": str(run.mode or "checkpoint"),
        "status": str(run.status or "queued"),
        "from_at": run.from_at,
        "to_at": run.to_at,
        "recent_limit": int(run.recent_limit) if run.recent_limit is not None else None,
        "selected_messages": int(run.selected_message_count or 0),
        "scanned_messages": int(run.scanned_message_count or 0),
        "valid_messages": int(run.valid_message_count or 0),
        "skipped_messages": int(run.skipped_message_count or 0),
        "resources": int(run.resource_count or 0),
        "links": int(run.link_count or 0),
        "jobs": int(run.job_count or 0),
        "failed": int(run.failed_count or 0),
        "last_error_message": str(run.last_error_message or "") or None,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "paused_at": run.paused_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def preview_learning_supplement(
    session: Session,
    *,
    task_id: int,
    mode: str = "checkpoint",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    recent_limit: int | None = None,
) -> dict[str, Any]:
    plan = _build_learning_supplement_plan(
        session,
        task_id=int(task_id),
        mode=mode,
        from_at=from_at,
        to_at=to_at,
        recent_limit=recent_limit,
    )
    return {
        "task_id": int(plan["task_id"]),
        "mode": str(plan["mode"]),
        "scanned_messages": int(plan["scanned_messages"]),
        "selected_messages": int(plan["selected_messages"]),
        "valid_messages": int(plan["valid_messages"]),
        "skipped_messages": int(plan["skipped_messages"]),
        "resources": int(plan["resources"]),
        "links": int(plan["links"]),
        "message_previews": plan["message_previews"],
    }


def create_learning_supplement_run(
    session: Session,
    *,
    task_id: int,
    mode: str = "checkpoint",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    recent_limit: int | None = None,
    operator: str = "admin",
) -> dict[str, Any]:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    active_run = session.query(LearningResourceSupplementRun).filter(
        LearningResourceSupplementRun.task_id == int(task.id),
        LearningResourceSupplementRun.status.in_(["queued", "running", "pause_requested"]),
    ).first()
    if active_run is not None:
        raise ValueError("该任务已有补充更新正在运行，请先等待或暂停当前运行")
    normalized_from_at = _normalize_learning_filter_datetime(from_at)
    normalized_to_at = _normalize_learning_filter_datetime(to_at)
    plan = _build_learning_supplement_plan(
        session,
        task_id=int(task.id),
        mode=mode,
        from_at=normalized_from_at,
        to_at=normalized_to_at,
        recent_limit=recent_limit,
    )
    run = LearningResourceSupplementRun(
        task_id=int(task.id),
        mode=str(plan["mode"]),
        status="queued",
        from_at=normalized_from_at,
        to_at=normalized_to_at,
        recent_limit=int(recent_limit) if recent_limit is not None else None,
        selected_message_count=int(plan["selected_messages"]),
        scanned_message_count=int(plan["scanned_messages"]),
        valid_message_count=int(plan["valid_messages"]),
        skipped_message_count=int(plan["skipped_messages"]),
        resource_count=int(plan["resources"]),
        link_count=int(plan["links"]),
        selected_message_ids_json=list(plan["selected_ids"]),
        options_json={
            "mode": str(plan["mode"]),
            "operator": str(operator or "admin"),
            "source_groups": list(plan["source_groups"]),
        },
        requested_by=str(operator or "admin")[:128],
    )
    session.add(run)
    session.flush()
    from app.services.learning_resources import _record_learning_process_log

    _record_learning_process_log(
        session,
        stage="replay",
        message=(
            f"补充更新已排队：扫描 {int(plan['scanned_messages'])} 条原始消息，"
            f"有效 {int(plan['valid_messages'])} 条，资源 {int(plan['resources'])} 条"
        ),
        task_id=int(task.id),
        supplement_run_id=int(run.id),
        details={
            "mode": str(plan["mode"]),
            "scanned_messages": int(plan["scanned_messages"]),
            "valid_messages": int(plan["valid_messages"]),
            "skipped_messages": int(plan["skipped_messages"]),
            "resources": int(plan["resources"]),
            "links": int(plan["links"]),
        },
    )
    session.flush()
    return _serialize_supplement_run(run)


def _advance_learning_supplement_checkpoints(
    session: Session,
    *,
    task_id: int,
    source_groups: list[dict[str, Any]],
) -> None:
    """Advance raw-message cursors after a supplement batch commits successfully."""
    if not source_groups:
        return
    channel_ids = {
        int(group["channel_id"])
        for group in source_groups
        if group.get("channel_id") is not None
    }
    if not channel_ids:
        return
    channel_rows = session.query(LearningResourceAutomationTaskChannel).filter(
        LearningResourceAutomationTaskChannel.task_id == int(task_id),
        LearningResourceAutomationTaskChannel.channel_id.in_(sorted(channel_ids)),
    ).all()
    channel_rows_by_id = {int(row.channel_id): row for row in channel_rows}
    for group in source_groups:
        channel_id = group.get("channel_id")
        message_id = group.get("monitor_message_id")
        row = channel_rows_by_id.get(int(channel_id)) if channel_id is not None else None
        if row is None or message_id is None:
            continue
        message_id = int(message_id)
        if message_id <= 0:
            continue
        if row.last_processed_telegram_message_id is None or message_id > int(row.last_processed_telegram_message_id):
            row.last_processed_telegram_message_id = message_id
            session.add(row)


def _group_message_ids_for_supplement(session: Session, message_ids: list[int]) -> list[list[int]]:
    rows = session.query(Message).filter(Message.id.in_(message_ids)).order_by(Message.id.asc()).all()
    groups: dict[tuple[str, int | str], list[int]] = {}
    for row in rows:
        groups.setdefault(_message_source_key(row), []).append(int(row.id))
    return list(groups.values())


def run_learning_supplement(supplement_run_id: int) -> None:
    session = Session(engine)
    try:
        run = session.get(LearningResourceSupplementRun, int(supplement_run_id))
        if run is None or run.status not in {"queued", "running"}:
            return
        run.status = "running"
        run.started_at = _utcnow()
        session.add(run)
        session.commit()
        message_ids = [int(value) for value in list(run.selected_message_ids_json or []) if int(value) > 0]
        stored_source_groups = list(dict(run.options_json or {}).get("source_groups") or [])
        if not stored_source_groups:
            stored_source_groups = [
                {"message_ids": group_ids}
                for group_ids in _group_message_ids_for_supplement(session, message_ids)
            ]
        chunk_size = 25
        for offset in range(0, len(stored_source_groups), chunk_size):
            session.refresh(run)
            if run.status == "pause_requested":
                run.status = "paused"
                run.paused_at = _utcnow()
                run.finished_at = _utcnow()
                session.add(run)
                session.commit()
                return
            source_group_chunk = stored_source_groups[offset:offset + chunk_size]
            chunk_ids = [
                int(message_id)
                for group in source_group_chunk
                for message_id in list(group.get("message_ids") or [])
                if int(message_id) > 0
            ]
            result: dict[str, Any] = {}
            if chunk_ids:
                result = process_learning_automation_task_now(
                    session,
                    task_id=int(run.task_id),
                    message_ids=chunk_ids,
                    operator=str(run.requested_by or "admin"),
                    supplement_run_id=int(run.id),
                    allow_paused_task=True,
                )
                run.job_count = int(run.job_count or 0) + int(result.get("jobs") or 0)
                run.failed_count = int(run.failed_count or 0) + int(result.get("failed") or 0)
            _advance_learning_supplement_checkpoints(
                session,
                task_id=int(run.task_id),
                source_groups=source_group_chunk,
            )
            run.result_json = {
                "last_result": result,
                "processed_groups": min(offset + chunk_size, len(stored_source_groups)),
            }
            session.add(run)
            session.commit()
        run.status = "completed"
        run.finished_at = _utcnow()
        session.add(run)
        session.commit()
    except Exception as exc:
        session.rollback()
        run = session.get(LearningResourceSupplementRun, int(supplement_run_id))
        if run is not None:
            run.status = "failed"
            run.last_error_message = str(exc or "补充更新失败")[:1800]
            run.finished_at = _utcnow()
            session.add(run)
            session.commit()
    finally:
        session.close()


def pause_learning_supplement(session: Session, *, supplement_run_id: int) -> dict[str, Any]:
    run = session.get(LearningResourceSupplementRun, int(supplement_run_id))
    if run is None:
        raise LookupError("补充更新记录不存在")
    if run.status == "queued":
        run.status = "paused"
        run.paused_at = _utcnow()
        run.finished_at = _utcnow()
    elif run.status == "running":
        run.status = "pause_requested"
    else:
        raise ValueError("当前补充更新不在运行中")
    session.add(run)
    session.flush()
    return _serialize_supplement_run(run)


def get_learning_supplement_run(session: Session, *, supplement_run_id: int) -> dict[str, Any] | None:
    run = session.get(LearningResourceSupplementRun, int(supplement_run_id))
    return _serialize_supplement_run(run) if run is not None else None


def retry_failed_learning_automation_jobs(session: Session, *, task_id: int) -> dict[str, Any]:
    from app.services.learning_resources import _record_learning_process_log

    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None or str(task.status or "") == "deleted":
        raise LookupError("学习资料自动任务不存在")
    if not bool(task.is_enabled):
        raise ValueError("任务已暂停，请先恢复后再重试")
    refresh_learning_automation_task_health(session, int(task.id))
    if task.status == "invalid":
        raise ValueError("任务配置不完整，请先修正频道或转存目标")
    jobs = session.query(LearningResourceTransferJob).filter(
        LearningResourceTransferJob.task_id == int(task.id),
        LearningResourceTransferJob.status == "failed",
    ).all()
    retried = 0
    for job in jobs:
        if not job.batch_item_id:
            continue
        item = session.get(PanTransferBatchItem, int(job.batch_item_id))
        if item is None:
            continue
        item.transfer_status = "queued"
        item.next_retry_at = None
        item.locked_by = None
        item.locked_at = None
        item.started_at = None
        item.finished_at = None
        item.error_message = None
        item.share_status = "shared" if item.new_share_url else "pending"
        item.validation_status = "pending"
        item.replacement_status = "replaced"
        session.add(item)
        batch = session.get(PanTransferBatch, int(item.batch_id))
        if batch is not None:
            batch.status = "running"
            batch.finished_at = None
            session.add(batch)
        job.status = "queued"
        job.last_error_message = None
        session.add(job)
        retried += 1
    _record_learning_process_log(
        session,
        stage="retrying",
        message=f"已重新加入 {retried} 个失败转存任务",
        task_id=int(task.id),
        details={"retried_count": retried},
    )
    refresh_learning_automation_task_health(session, int(task.id))
    session.flush()
    return {"task_id": int(task.id), "retried_count": retried}


def list_learning_automation_logs(session: Session, *, task_id: int, limit: int = 100) -> list[dict[str, Any]]:
    if session.get(LearningResourceAutomationTask, int(task_id)) is None:
        raise LookupError("学习资料自动任务不存在")
    rows = session.query(LearningResourceProcessLog).filter(
        LearningResourceProcessLog.task_id == int(task_id),
    ).order_by(LearningResourceProcessLog.created_at.desc(), LearningResourceProcessLog.id.desc()).limit(
        max(1, min(int(limit or 100), 300))
    ).all()
    return [
        {
            "id": int(row.id),
            "stage": str(row.stage or ""),
            "level": str(row.level or "info"),
            "message": str(row.message or ""),
            "details": dict(row.details_json or {}),
            "resource_id": int(row.resource_id) if row.resource_id else None,
            "transfer_job_id": int(row.transfer_job_id) if row.transfer_job_id else None,
            "source_message_id": int(row.source_message_id) if row.source_message_id else None,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def clear_learning_automation_logs(session: Session, *, task_id: int) -> dict[str, Any]:
    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None:
        raise LookupError("学习资料自动任务不存在")
    deleted_count = int(
        session.query(LearningResourceProcessLog)
        .filter(LearningResourceProcessLog.task_id == int(task_id))
        .delete(synchronize_session=False)
        or 0
    )
    session.flush()
    return {"task_id": int(task_id), "deleted_count": deleted_count}


__all__ = [
    "ACTIVE_LEARNING_JOB_STATUSES",
    "FAILED_LEARNING_JOB_STATUSES",
    "get_learning_automation_task",
    "delete_learning_automation_task",
    "clear_learning_automation_logs",
    "is_learning_target_enabled",
    "list_learning_automation_logs",
    "list_learning_automation_tasks",
    "preview_learning_supplement",
    "create_learning_supplement_run",
    "get_learning_supplement_run",
    "pause_learning_supplement",
    "process_learning_automation_task_now",
    "retry_failed_learning_automation_jobs",
    "refresh_learning_automation_task_health",
    "run_learning_supplement",
    "save_learning_automation_task",
    "set_learning_automation_task_enabled",
    "sync_legacy_learning_channel_config",
]
