from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.models import (
    Channel,
    LearningChannelConfig,
    LearningResourceProcessLog,
    LearningResourceTransferJob,
    LearningResourceAutomationTask,
    LearningResourceAutomationTaskChannel,
    LearningResourceAutomationTaskTarget,
    Message,
    PanTransferAccount,
    PanTransferBatch,
    PanTransferBatchItem,
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


def is_learning_target_enabled(session: Session, extra_json: dict[str, Any]) -> bool:
    """Check the current task and target before a worker starts a network request."""
    task_id = extra_json.get("learning_task_id")
    target_id = extra_json.get("learning_target_id")
    if task_id and target_id:
        task = session.get(LearningResourceAutomationTask, int(task_id))
        target = session.get(LearningResourceAutomationTaskTarget, int(target_id))
        if task is None or target is None or not bool(task.is_enabled) or str(task.transfer_policy or "automatic") != "automatic" or not bool(target.is_enabled):
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
    tasks = session.query(LearningResourceAutomationTask).order_by(
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
    if task is None:
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
    if task_id and task is None:
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
    else:
        _pause_task_jobs(session, int(task.id))
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
    if task is None:
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
        _pause_task_jobs(session, int(task.id))
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
    if task is None:
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


def process_learning_automation_task_now(
    session: Session,
    *,
    task_id: int,
    message_ids: Iterable[int] | None = None,
    from_message_id: int | None = None,
    to_message_id: int | None = None,
    dry_run: bool = False,
    operator: str = "admin",
) -> dict[str, Any]:
    from app.services.learning_resources import (
        _record_learning_process_log,
        enqueue_learning_resources_for_message_ids,
    )

    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None:
        raise LookupError("学习资料自动任务不存在")
    if not bool(task.is_enabled):
        raise ValueError("任务已暂停，请先恢复后再处理")
    refresh_learning_automation_task_health(session, int(task.id))
    if task.status == "invalid":
        raise ValueError("任务配置不完整，请先修正频道或转存目标")
    channel_rows = session.query(LearningResourceAutomationTaskChannel).filter(
        LearningResourceAutomationTaskChannel.task_id == int(task.id),
        LearningResourceAutomationTaskChannel.is_enabled.is_(True),
    ).all()
    channel_ids = {int(row.channel_id) for row in channel_rows}
    channel_keys = {
        _channel_key(channel)
        for channel in session.query(Channel).filter(Channel.id.in_(sorted(channel_ids))).all()
    } if channel_ids else set()
    if not channel_ids:
        raise ValueError("任务没有启用的监听频道")
    query = session.query(Message).filter(
        or_(
            Message.monitor_channel_config_id.in_(sorted(channel_ids)),
            Message.monitor_channel_key.in_(sorted(channel_keys)),
        )
    )
    normalized_ids = sorted({int(value) for value in (message_ids or []) if int(value) > 0})
    if normalized_ids:
        query = query.filter(Message.id.in_(normalized_ids))
    if from_message_id is not None:
        query = query.filter(Message.id >= int(from_message_id))
    if to_message_id is not None:
        query = query.filter(Message.id <= int(to_message_id))
    if not normalized_ids and from_message_id is None and to_message_id is None:
        query = query.order_by(Message.id.desc()).limit(200)
    else:
        query = query.order_by(Message.id.asc()).limit(5000)
    selected = query.all()
    selected_ids = [int(message.id) for message in selected]
    if dry_run:
        return {"task_id": int(task.id), "selected_messages": len(selected_ids), "message_ids": selected_ids, "dry_run": True}
    result = enqueue_learning_resources_for_message_ids(
        session,
        selected_ids,
        operator=operator,
        task_id=int(task.id),
    )
    task.last_enqueued_at = _utcnow() if result.get("jobs") else task.last_enqueued_at
    session.add(task)
    refresh_learning_automation_task_health(session, int(task.id))
    _record_learning_process_log(
        session,
        stage="replay",
        message=f"已手动处理 {len(selected_ids)} 条消息，新增 {int(result.get('jobs') or 0)} 个转存任务",
        task_id=int(task.id),
        details={"message_ids": selected_ids[:500], "result": result},
    )
    session.flush()
    return {"task_id": int(task.id), "selected_messages": len(selected_ids), "dry_run": False, **result}


def retry_failed_learning_automation_jobs(session: Session, *, task_id: int) -> dict[str, Any]:
    from app.services.learning_resources import _record_learning_process_log

    task = session.get(LearningResourceAutomationTask, int(task_id))
    if task is None:
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


__all__ = [
    "ACTIVE_LEARNING_JOB_STATUSES",
    "FAILED_LEARNING_JOB_STATUSES",
    "get_learning_automation_task",
    "is_learning_target_enabled",
    "list_learning_automation_logs",
    "list_learning_automation_tasks",
    "process_learning_automation_task_now",
    "retry_failed_learning_automation_jobs",
    "refresh_learning_automation_task_health",
    "save_learning_automation_task",
    "set_learning_automation_task_enabled",
    "sync_legacy_learning_channel_config",
]
