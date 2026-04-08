from __future__ import annotations

import base64
import calendar
import hashlib
import http.client
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import BackupRun, BackupTarget, Message, engine, ensure_runtime_storage_tables
from app.services.secret_codec import decrypt_secret, encrypt_secret


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_RUN_STATUSES = {"pending", "running"}
FULL_BACKUP_PREFIX = "tg-backup"
EXPORT_BACKUP_PREFIX = "movie-data"
WEBDAV_DEFAULT_PROVIDER = "generic_webdav"
LOCAL_DEFAULT_DIR = "data/backups"
BACKUP_QUEUE_LOCK_KEY = 90217041
EXPORT_XLSX_COLUMNS = [
    "\u5f71\u89c6\u540d\u5b57",
    "\u63cf\u8ff0",
    "\u6807\u7b7e",
    "\u7f51\u76d8\u94fe\u63a5",
]
EXPORT_XLSX_SHEET_NAME = "\u5f71\u89c6\u8d44\u6e90"

_dispatch_lock = threading.RLock()
_queue_worker_thread: threading.Thread | None = None


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


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "").strip())
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed[:80] or "target"


def _project_relative_or_absolute(path_value: str) -> Path:
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return raw_path
    return (PROJECT_ROOT / raw_path).resolve()


def _encrypt_secret(value: str) -> str:
    return encrypt_secret(value)


def _decrypt_secret(value: str) -> str:
    return decrypt_secret(value, error_message="Unable to decrypt WebDAV password; please verify SECRET_SALT")


def _quote_webdav_path(path_value: str) -> str:
    parts = [quote(part, safe="") for part in path_value.split("/") if part]
    return "/".join(parts)


def _normalize_webdav_root_path(path_value: str) -> str:
    return "/".join(part for part in (path_value or "").strip().split("/") if part)


def _sanitize_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    credentials = f"{parsed.username}@" if parsed.username else ""
    safe_netloc = f"{credentials}{hostname}{port}"
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment))


def _build_webdav_url(base_url: str, relative_path: str) -> str:
    quoted_path = _quote_webdav_path(relative_path)
    return f"{base_url.rstrip('/')}/{quoted_path}" if quoted_path else base_url.rstrip("/")


def _build_remote_file_path(target: BackupTarget | dict[str, Any], file_name: str) -> str:
    root_path = target.webdav_root_path if isinstance(target, BackupTarget) else str(target.get("webdav_root_path") or "")
    normalized_root = _normalize_webdav_root_path(root_path)
    return f"{normalized_root}/{file_name}" if normalized_root else file_name


def _normalize_remote_path(path_value: str) -> str:
    parts = [part for part in str(path_value or "").strip().split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _get_target_timezone(target: BackupTarget | dict[str, Any]) -> ZoneInfo:
    timezone_name = target.timezone if isinstance(target, BackupTarget) else str(target.get("timezone") or "Asia/Shanghai")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _days_label(days: int | None) -> str:
    return "all" if not days else f"{days}d"


def _build_timestamp_label(target: BackupTarget | dict[str, Any]) -> str:
    return datetime.now(_get_target_timezone(target)).strftime("%Y%m%d-%H%M%S")


def _build_file_name(target: BackupTarget | dict[str, Any]) -> tuple[str, str]:
    target_name = target.name if isinstance(target, BackupTarget) else str(target.get("name") or "target")
    backup_mode = target.backup_mode if isinstance(target, BackupTarget) else str(target.get("backup_mode") or "full")
    timestamp = _build_timestamp_label(target)
    slug = _slugify(target_name)
    if backup_mode == "media_export":
        range_kind = target.export_range_kind if isinstance(target, BackupTarget) else str(target.get("export_range_kind") or "all")
        range_days = target.export_range_days if isinstance(target, BackupTarget) else target.get("export_range_days")
        file_name = f"{EXPORT_BACKUP_PREFIX}-{slug}-{_days_label(range_days) if range_kind == 'days' else 'all'}-{timestamp}.xlsx"
        return file_name, "xlsx"
    file_name = f"{FULL_BACKUP_PREFIX}-{slug}-{timestamp}.zip"
    return file_name, "zip"


def _parse_backup_file_name(file_name: str, *, target: BackupTarget | dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "backup_time": None,
        "backup_mode": None,
        "range_label": None,
        "file_format": Path(file_name).suffix.lstrip(".").lower() or None,
    }

    local_tz = _get_target_timezone(target)
    full_match = re.match(rf"^{FULL_BACKUP_PREFIX}-.+-(\d{{8}}-\d{{6}})\.zip$", file_name)
    export_match = re.match(rf"^{EXPORT_BACKUP_PREFIX}-.+-(all|\d+d)-(\d{{8}}-\d{{6}})\.xlsx$", file_name)

    timestamp_label: str | None = None
    if full_match:
        parsed["backup_mode"] = "full"
        timestamp_label = full_match.group(1)
    elif export_match:
        parsed["backup_mode"] = "media_export"
        range_token = export_match.group(1)
        parsed["range_label"] = "全部数据" if range_token == "all" else f"最近 {range_token[:-1]} 天"
        timestamp_label = export_match.group(2)

    if timestamp_label:
        try:
            parsed_dt = datetime.strptime(timestamp_label, "%Y%m%d-%H%M%S").replace(tzinfo=local_tz)
            parsed["backup_time"] = parsed_dt.isoformat()
        except ValueError:
            parsed["backup_time"] = None

    return parsed


def _format_schedule_summary(target: BackupTarget) -> str:
    if not target.schedule_enabled:
        return "manual"
    time_part = f"{target.schedule_hour:02d}:{target.schedule_minute:02d}"
    if target.schedule_kind == "daily":
        return f"daily {time_part}"
    if target.schedule_kind == "weekly":
        weekday_labels = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        weekday = target.schedule_weekday or 0
        return f"{weekday_labels[weekday]} {time_part}"
    if target.schedule_kind == "monthly":
        return f"monthly day {target.schedule_day} {time_part}"
    return "manual"


def _format_destination_summary(target: BackupTarget) -> str:
    return target.local_dir if target.target_kind == "local" else _sanitize_url(target.webdav_base_url)


def _serialize_backup_target(target: BackupTarget, active_runs: dict[int, BackupRun] | None = None) -> dict[str, Any]:
    active_run = (active_runs or {}).get(target.id)
    return {
        "id": target.id,
        "name": target.name,
        "target_kind": target.target_kind,
        "provider": target.provider,
        "is_enabled": bool(target.is_enabled),
        "backup_mode": target.backup_mode,
        "schedule_enabled": bool(target.schedule_enabled),
        "schedule_kind": target.schedule_kind,
        "schedule_hour": target.schedule_hour,
        "schedule_minute": target.schedule_minute,
        "schedule_priority": target.schedule_priority or 100,
        "schedule_weekday": target.schedule_weekday,
        "schedule_day": target.schedule_day,
        "timezone": target.timezone,
        "retention_count": target.retention_count,
        "local_dir": target.local_dir,
        "webdav_base_url": target.webdav_base_url,
        "webdav_username": target.webdav_username,
        "webdav_root_path": target.webdav_root_path,
        "webdav_timeout_seconds": target.webdav_timeout_seconds,
        "webdav_verify_ssl": bool(target.webdav_verify_ssl),
        "webdav_password_configured": bool(target.webdav_password_encrypted),
        "include_env_file": bool(target.include_env_file),
        "include_runtime_data": bool(target.include_runtime_data),
        "export_range_kind": target.export_range_kind,
        "export_range_days": target.export_range_days,
        "last_run_at": _to_iso(target.last_run_at),
        "next_run_at": _to_iso(target.next_run_at),
        "last_status": target.last_status,
        "last_error_message": target.last_error_message,
        "has_active_run": active_run is not None,
        "active_run_id": active_run.id if active_run else None,
        "active_run_status": active_run.status if active_run else None,
        "extra_json": {
            **(target.extra_json or {}),
            "schedule_summary": _format_schedule_summary(target),
            "destination_summary": _format_destination_summary(target),
        },
        "created_at": _to_iso(target.created_at),
        "updated_at": _to_iso(target.updated_at),
        "updated_by": target.updated_by,
    }


def _serialize_backup_run(run: BackupRun, *, reused_existing: bool = False) -> dict[str, Any]:
    return {
        "id": run.id,
        "target_id": run.target_id,
        "target_name": run.target_name,
        "target_kind": run.target_kind,
        "provider": run.provider,
        "backup_mode": run.backup_mode,
        "trigger_source": run.trigger_source,
        "status": run.status,
        "file_name": run.file_name,
        "file_format": run.file_format,
        "file_size_bytes": run.file_size_bytes,
        "sha256": run.sha256,
        "local_path": run.local_path,
        "remote_path": run.remote_path,
        "remote_url": run.remote_url,
        "item_count": run.item_count,
        "started_at": _to_iso(run.started_at),
        "finished_at": _to_iso(run.finished_at),
        "duration_seconds": run.duration_seconds,
        "created_by": run.created_by,
        "error_message": run.error_message,
        "result_json": run.result_json or {},
        "created_at": _to_iso(run.created_at),
        "reused_existing": reused_existing,
    }


def _compute_next_run_at(target: BackupTarget, *, now_utc: datetime | None = None) -> datetime | None:
    if not target.schedule_enabled or target.schedule_kind == "manual":
        return None

    reference_utc = _from_utc_storage(now_utc or _utc_now()) or datetime.now(timezone.utc)
    timezone_info = _get_target_timezone(target)
    current_local = reference_utc.astimezone(timezone_info)

    def local_candidate(year: int, month: int, day: int) -> datetime:
        return datetime(
            year,
            month,
            day,
            target.schedule_hour,
            target.schedule_minute,
            tzinfo=timezone_info,
        )

    if target.schedule_kind == "daily":
        candidate = local_candidate(current_local.year, current_local.month, current_local.day)
        if candidate <= current_local:
            candidate += timedelta(days=1)
        return _to_utc_storage(candidate)

    if target.schedule_kind == "weekly":
        weekday = target.schedule_weekday or 0
        delta_days = (weekday - current_local.weekday()) % 7
        base_day = current_local + timedelta(days=delta_days)
        candidate = local_candidate(base_day.year, base_day.month, base_day.day)
        if candidate <= current_local:
            candidate += timedelta(days=7)
        return _to_utc_storage(candidate)

    if target.schedule_kind == "monthly":
        target_day = max(1, min(31, target.schedule_day or 1))
        year = current_local.year
        month = current_local.month
        max_day = calendar.monthrange(year, month)[1]
        candidate = local_candidate(year, month, min(target_day, max_day))
        if candidate <= current_local:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            max_day = calendar.monthrange(year, month)[1]
            candidate = local_candidate(year, month, min(target_day, max_day))
        return _to_utc_storage(candidate)

    return None


def _apply_target_payload(target: BackupTarget, values: dict[str, Any], *, is_update: bool) -> None:
    target.name = values["name"]
    target.target_kind = values["target_kind"]
    requested_provider = str(values.get("provider") or "").strip().lower()
    target.provider = "local" if target.target_kind == "local" else (WEBDAV_DEFAULT_PROVIDER if not requested_provider or requested_provider == "local" else requested_provider)
    target.is_enabled = bool(values["is_enabled"])
    target.backup_mode = values["backup_mode"]
    target.schedule_enabled = bool(values["schedule_enabled"])
    target.schedule_kind = values["schedule_kind"]
    target.schedule_hour = int(values["schedule_hour"])
    target.schedule_minute = int(values["schedule_minute"])
    target.schedule_priority = max(1, int(values.get("schedule_priority") or 100))
    target.schedule_weekday = values.get("schedule_weekday")
    target.schedule_day = values.get("schedule_day")
    target.timezone = values["timezone"]
    target.retention_count = int(values["retention_count"])
    target.retention_days = 0
    target.run_log_retention_days = 0
    target.local_dir = values.get("local_dir") or LOCAL_DEFAULT_DIR
    target.webdav_base_url = (values.get("webdav_base_url") or "").strip()
    target.webdav_username = (values.get("webdav_username") or "").strip()
    target.webdav_root_path = _normalize_webdav_root_path(values.get("webdav_root_path") or "")
    target.webdav_timeout_seconds = int(values["webdav_timeout_seconds"])
    target.webdav_verify_ssl = bool(values["webdav_verify_ssl"])
    target.include_database = True
    target.include_users_json = False
    target.include_env_file = bool(values["include_env_file"])
    target.include_runtime_data = bool(values["include_runtime_data"])
    target.export_range_kind = values["export_range_kind"]
    target.export_range_days = values.get("export_range_days")

    if values.get("clear_webdav_password"):
        target.webdav_password_encrypted = ""
    elif values.get("webdav_password"):
        target.webdav_password_encrypted = _encrypt_secret(values["webdav_password"])
    elif not is_update:
        target.webdav_password_encrypted = ""

    if target.schedule_enabled and target.is_enabled:
        target.next_run_at = _compute_next_run_at(target)
    else:
        target.next_run_at = None


def list_backup_targets() -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        active_runs = {
            run.target_id: run
            for run in session.query(BackupRun)
            .filter(BackupRun.target_id.isnot(None), BackupRun.status.in_(ACTIVE_RUN_STATUSES))
            .all()
            if run.target_id is not None
        }
        targets = session.query(BackupTarget).order_by(BackupTarget.created_at.desc(), BackupTarget.id.desc()).all()
        return [_serialize_backup_target(target, active_runs) for target in targets]


def create_backup_target(values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = BackupTarget()
        _apply_target_payload(target, values, is_update=False)
        target.updated_by = updated_by
        session.add(target)
        session.commit()
        session.refresh(target)
        return _serialize_backup_target(target)


def update_backup_target(target_id: int, values: dict[str, Any], *, updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            raise LookupError("Backup target not found")
        _apply_target_payload(target, values, is_update=True)
        target.updated_by = updated_by
        session.add(target)
        session.commit()
        session.refresh(target)
        return _serialize_backup_target(target)


def delete_backup_target(target_id: int) -> None:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            raise LookupError("Backup target not found")
        active_run = (
            session.query(BackupRun)
            .filter(BackupRun.target_id == target_id, BackupRun.status.in_(ACTIVE_RUN_STATUSES))
            .first()
        )
        if active_run is not None:
            raise ValueError("Backup target still has an active run and cannot be deleted")
        session.delete(target)
        session.commit()


def list_backup_target_remote_files(target_id: int) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            raise LookupError("Backup target not found")
        if target.target_kind != "webdav":
            raise ValueError("Only WebDAV targets support remote file browsing")
        target_snapshot = _clone_target(target)

    return _list_webdav_files(target_snapshot)


def delete_backup_target_remote_file(target_id: int, remote_path: str) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            raise LookupError("Backup target not found")
        if target.target_kind != "webdav":
            raise ValueError("Only WebDAV targets support remote file deletion")
        target_snapshot = _clone_target(target)

    normalized_path = _validate_remote_file_path(target_snapshot, remote_path)
    deleted = _delete_webdav_file(target_snapshot, normalized_path)

    with Session(engine) as session:
        runs = (
            session.query(BackupRun)
            .filter(BackupRun.target_id == target_id, BackupRun.remote_path == normalized_path)
            .all()
        )
        for run in runs:
            run.remote_path = None
            run.remote_url = None
            run.result_json = {
                **(run.result_json or {}),
                "remote_file_deleted": True,
            }
            session.add(run)
        session.commit()

    return {
        "success": bool(deleted),
        "remote_path": normalized_path,
    }


def list_backup_runs(*, limit: int = 40, target_id: int | None = None) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    safe_limit = max(1, min(limit, 200))
    with Session(engine) as session:
        query = session.query(BackupRun)
        if target_id is not None:
            query = query.filter(BackupRun.target_id == target_id)
        runs = query.order_by(BackupRun.started_at.desc(), BackupRun.id.desc()).limit(safe_limit).all()
        return [_serialize_backup_run(run) for run in runs]


def delete_backup_runs(run_ids: list[int]) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    normalized_ids = [run_id for run_id in dict.fromkeys(int(value) for value in run_ids if int(value) > 0)]
    if not normalized_ids:
        raise ValueError("No backup runs selected")

    deleted_ids: list[int] = []
    skipped_active_count = 0
    skipped_missing_count = 0

    with Session(engine) as session:
        runs = session.query(BackupRun).filter(BackupRun.id.in_(normalized_ids)).all()
        run_map = {run.id: run for run in runs}

        for run_id in normalized_ids:
            run = run_map.get(run_id)
            if run is None:
                skipped_missing_count += 1
                continue
            if run.status in ACTIVE_RUN_STATUSES:
                skipped_active_count += 1
                continue

            session.delete(run)
            deleted_ids.append(run_id)

        session.commit()

    return {
        "deleted_count": len(deleted_ids),
        "skipped_active_count": skipped_active_count,
        "skipped_missing_count": skipped_missing_count,
        "deleted_ids": deleted_ids,
    }


def cleanup_expired_backup_run_logs() -> dict[str, Any]:
    return {
        "deleted_count": 0,
        "deleted_ids": [],
    }


def _build_run_from_target(target: BackupTarget, *, trigger_source: str, created_by: str | None) -> BackupRun:
    return BackupRun(
        target_id=target.id,
        target_name=target.name,
        target_kind=target.target_kind,
        provider=target.provider,
        backup_mode=target.backup_mode,
        trigger_source=trigger_source,
        status="pending",
        created_by=created_by,
        result_json={},
    )


def start_backup_run(target_id: int, *, trigger_source: str = "manual", created_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = (
            session.query(BackupTarget)
            .filter(BackupTarget.id == target_id)
            .with_for_update()
            .first()
        )
        if target is None:
            raise LookupError("Backup target not found")

        active_run = (
            session.query(BackupRun)
            .filter(BackupRun.target_id == target_id, BackupRun.status.in_(ACTIVE_RUN_STATUSES))
            .first()
        )
        if active_run is not None:
            return _serialize_backup_run(active_run, reused_existing=True)

        run = _build_run_from_target(target, trigger_source=trigger_source, created_by=created_by)
        session.add(run)
        target.last_status = "pending"
        target.last_error_message = None
        if trigger_source == "scheduled":
            target.next_run_at = _compute_next_run_at(target)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            active_run = (
                session.query(BackupRun)
                .filter(BackupRun.target_id == target_id, BackupRun.status.in_(ACTIVE_RUN_STATUSES))
                .first()
            )
            if active_run is not None:
                return _serialize_backup_run(active_run, reused_existing=True)
            raise

        session.refresh(run)

    dispatch_pending_backup_runs()
    return _serialize_backup_run(run)


def claim_due_backup_runs(*, limit: int | None = None) -> int:
    ensure_runtime_storage_tables()
    now_utc = _utc_now()
    created_run_count = 0

    with Session(engine) as session:
        query = (
            session.query(BackupTarget)
            .filter(
                BackupTarget.is_enabled.is_(True),
                BackupTarget.schedule_enabled.is_(True),
                BackupTarget.next_run_at.isnot(None),
                BackupTarget.next_run_at <= now_utc,
            )
            .order_by(BackupTarget.next_run_at.asc(), BackupTarget.schedule_priority.asc(), BackupTarget.id.asc())
            .with_for_update(skip_locked=True)
        )
        if limit is not None:
            query = query.limit(max(1, min(int(limit), 500)))
        due_targets = query.all()

        for target in due_targets:
            active_run = (
                session.query(BackupRun)
                .filter(BackupRun.target_id == target.id, BackupRun.status.in_(ACTIVE_RUN_STATUSES))
                .first()
            )
            target.next_run_at = _compute_next_run_at(target, now_utc=now_utc)
            if active_run is not None:
                continue

            run = _build_run_from_target(target, trigger_source="scheduled", created_by="scheduler")
            target.last_status = "pending"
            target.last_error_message = None
            session.add(run)
            created_run_count += 1

        session.commit()

    if created_run_count > 0:
        dispatch_pending_backup_runs()

    return created_run_count


def dispatch_pending_backup_runs() -> bool:
    with _dispatch_lock:
        global _queue_worker_thread
        if _queue_worker_thread is not None and _queue_worker_thread.is_alive():
            return False
        worker = threading.Thread(
            target=_run_backup_queue_worker,
            daemon=True,
            name="backup-queue-worker",
        )
        _queue_worker_thread = worker
    worker.start()
    return True


def _try_acquire_backup_queue_lock(connection: Any) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (BACKUP_QUEUE_LOCK_KEY,))
        row = cursor.fetchone()
        connection.commit()
        return bool(row[0]) if row else False
    finally:
        cursor.close()


def _release_backup_queue_lock(connection: Any, *, acquired: bool) -> None:
    try:
        if acquired:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (BACKUP_QUEUE_LOCK_KEY,))
                connection.commit()
            finally:
                cursor.close()
    finally:
        connection.close()


def _claim_next_pending_run() -> int | None:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        run = (
            session.query(BackupRun)
            .filter(BackupRun.status == "pending")
            .order_by(BackupRun.created_at.asc(), BackupRun.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if run is None:
            return None

        run.status = "running"
        run.started_at = _utc_now()
        session.add(run)
        session.commit()
        return run.id


def _has_pending_backup_runs() -> bool:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        return session.query(BackupRun.id).filter(BackupRun.status == "pending").first() is not None


def _run_backup_queue_worker() -> None:
    connection = None
    acquired = False
    should_recheck_queue = False
    try:
        connection = engine.raw_connection()
        acquired = _try_acquire_backup_queue_lock(connection)
        if not acquired:
            return

        while True:
            run_id = _claim_next_pending_run()
            if run_id is None:
                break
            _execute_backup_run(run_id)
    finally:
        if connection is not None:
            _release_backup_queue_lock(connection, acquired=acquired)
        with _dispatch_lock:
            global _queue_worker_thread
            if _queue_worker_thread is threading.current_thread():
                _queue_worker_thread = None
                should_recheck_queue = acquired
        if should_recheck_queue and _has_pending_backup_runs():
            dispatch_pending_backup_runs()


def _hash_file(path: Path) -> tuple[float, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return float(size), digest.hexdigest()


def _resolve_local_output_path(target: BackupTarget, file_name: str) -> Path:
    destination_dir = _project_relative_or_absolute(target.local_dir or LOCAL_DEFAULT_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)
    return destination_dir / file_name


def _resolve_pg_dump_path() -> str:
    env_override = os.getenv("PG_DUMP_PATH", "").strip()
    if env_override and Path(env_override).exists():
        return env_override

    resolved = shutil.which("pg_dump")
    if resolved:
        return resolved

    candidate_paths: list[Path] = []
    if os.name == "nt":
        candidate_paths.extend(Path(r"C:\Program Files\PostgreSQL").glob(r"*\bin\pg_dump.exe"))
    else:
        candidate_paths.extend(
            [
                Path("/usr/bin/pg_dump"),
                Path("/usr/local/bin/pg_dump"),
            ]
        )
        candidate_paths.extend(Path("/usr/lib/postgresql").glob("*/bin/pg_dump"))

    for candidate in candidate_paths:
        try:
            if candidate.exists():
                return str(candidate)
        except Exception:
            continue

    raise RuntimeError(
        "pg_dump not found; install PostgreSQL client tools, add pg_dump to PATH, or set PG_DUMP_PATH"
    )


def _dump_database(output_path: Path) -> None:
    database_url = make_url(settings.DATABASE_URL)
    db_name = database_url.database
    if not db_name:
        raise RuntimeError("DATABASE_URL does not include a database name")

    command = [
        _resolve_pg_dump_path(),
        "--format=plain",
        "--encoding=UTF8",
        "--no-owner",
        "--no-privileges",
        "--host",
        database_url.host or "",
        "--port",
        str(database_url.port or 5432),
        "--username",
        database_url.username or "",
        "--file",
        str(output_path),
        db_name,
    ]
    env = os.environ.copy()
    if database_url.password:
        env["PGPASSWORD"] = database_url.password

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pg_dump not found; install PostgreSQL client tools, add pg_dump to PATH, or set PG_DUMP_PATH"
        ) from exc

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"pg_dump failed: {message}")


def _copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _should_skip_runtime_path(path_value: Path, *, excluded_dirs: list[Path]) -> bool:
    resolved = path_value.resolve()
    return any(resolved == excluded or excluded in resolved.parents for excluded in excluded_dirs)


def _copy_runtime_data(destination_dir: Path, *, target: BackupTarget) -> int:
    source_root = PROJECT_ROOT / "data"
    if not source_root.exists():
        return 0

    excluded_dirs = [(PROJECT_ROOT / "data" / "backups").resolve()]
    try:
        target_dir = _project_relative_or_absolute(target.local_dir or LOCAL_DEFAULT_DIR)
        project_data_dir = (PROJECT_ROOT / "data").resolve()
        if target_dir.exists() and (target_dir == project_data_dir or project_data_dir in target_dir.parents):
            excluded_dirs.append(target_dir.resolve())
    except Exception:
        pass

    copied_count = 0
    for source_path in source_root.rglob("*"):
        if source_path.is_dir():
            continue
        if _should_skip_runtime_path(source_path, excluded_dirs=excluded_dirs):
            continue
        relative_path = source_path.relative_to(source_root)
        destination_path = destination_dir / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied_count += 1
    return copied_count


def _zip_directory(source_dir: Path, output_path: Path) -> int:
    file_count = 0
    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path_value in sorted(source_dir.rglob("*")):
            if path_value.is_dir():
                continue
            archive.write(path_value, path_value.relative_to(source_dir))
            file_count += 1
    return file_count


def _flatten_message_links(links: Any) -> str:
    if not isinstance(links, dict):
        return ""

    lines: list[str] = []
    for provider, value in links.items():
        if isinstance(value, str):
            lines.append(f"{provider}: {value}")
            continue
        if isinstance(value, dict):
            url = value.get("url")
            if url:
                label = str(value.get("label") or "").strip()
                prefix = f"{provider} ({label})" if label else provider
                lines.append(f"{prefix}: {url}")
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    lines.append(f"{provider}: {item}")
                elif isinstance(item, dict) and item.get("url"):
                    label = str(item.get("label") or "").strip()
                    prefix = f"{provider} ({label})" if label else provider
                    lines.append(f"{prefix}: {item['url']}")
    return "\n".join(lines)


def _build_export_rows(target: BackupTarget) -> list[dict[str, Any]]:
    with Session(engine) as session:
        query = session.query(Message.title, Message.description, Message.tags, Message.links).filter(Message.links.isnot(None))
        if target.export_range_kind == "days" and target.export_range_days:
            cutoff = _utc_now() - timedelta(days=int(target.export_range_days))
            query = query.filter(Message.timestamp >= cutoff)
        query = query.order_by(Message.timestamp.desc())

        rows: list[dict[str, Any]] = []
        for title, description, tags, links in query.yield_per(500):
            link_text = _flatten_message_links(links)
            if not link_text:
                continue
            rows.append(
                {
                    EXPORT_XLSX_COLUMNS[0]: title or "",
                    EXPORT_XLSX_COLUMNS[1]: description or "",
                    EXPORT_XLSX_COLUMNS[2]: " ".join(f"#{tag}" for tag in (tags or [])),
                    EXPORT_XLSX_COLUMNS[3]: link_text,
                }
            )
        return rows


def _write_export_xlsx(output_path: Path, target: BackupTarget) -> int:
    rows = _build_export_rows(target)
    try:
        import pandas as pd
    except Exception as exc:
        raise RuntimeError("pandas is required to generate the Excel export") from exc

    try:
        dataframe = pd.DataFrame(rows, columns=EXPORT_XLSX_COLUMNS)
        dataframe.to_excel(output_path, index=False, sheet_name=EXPORT_XLSX_SHEET_NAME, engine="openpyxl")
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to generate the Excel export") from exc
    return len(rows)


def _build_full_backup_archive(target: BackupTarget, output_path: Path) -> tuple[int, dict[str, Any]]:
    manifest: dict[str, Any] = {
        "generated_at": _utc_now().isoformat(),
        "target_id": target.id,
        "target_name": target.name,
        "target_kind": target.target_kind,
        "backup_mode": target.backup_mode,
        "included_files": [],
    }

    with tempfile.TemporaryDirectory(prefix="tg-backup-stage-") as staging_dir:
        staging_root = Path(staging_dir)

        database_dump_path = staging_root / "database.sql"
        _dump_database(database_dump_path)
        manifest["included_files"].append("database.sql")

        if target.include_env_file and _copy_if_exists(PROJECT_ROOT / ".env", staging_root / ".env"):
            manifest["included_files"].append(".env")

        runtime_file_count = 0
        if target.include_runtime_data:
            runtime_destination = staging_root / "data"
            runtime_file_count = _copy_runtime_data(runtime_destination, target=target)
            if runtime_file_count > 0:
                manifest["included_files"].append("data/")

        manifest["runtime_file_count"] = runtime_file_count
        manifest_path = staging_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["included_files"].append("manifest.json")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        file_count = _zip_directory(staging_root, output_path)
        return file_count, manifest


def _build_webdav_connection(url: str, *, timeout_seconds: int, verify_ssl: bool) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("WebDAV URL must start with http:// or https://")
    host = parsed.hostname
    if not host:
        raise ValueError("WebDAV URL is missing a host name")

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    if parsed.scheme == "https":
        context = ssl.create_default_context()
        if not verify_ssl:
            context = ssl._create_unverified_context()
        connection = http.client.HTTPSConnection(host, parsed.port or 443, timeout=timeout_seconds, context=context)
    else:
        connection = http.client.HTTPConnection(host, parsed.port or 80, timeout=timeout_seconds)

    return connection, path


def _build_webdav_headers(target: BackupTarget) -> dict[str, str]:
    headers = {"User-Agent": "tg-monitor-backup/1.0"}
    if target.webdav_username:
        password = _decrypt_secret(target.webdav_password_encrypted)
        token = base64.b64encode(f"{target.webdav_username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _perform_webdav_request(
    target: BackupTarget,
    method: str,
    url: str,
    *,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> int:
    status_code, _, _ = _perform_webdav_request_raw(
        target,
        method,
        url,
        body=body,
        headers=headers,
    )
    return status_code


def _perform_webdav_request_raw(
    target: BackupTarget,
    method: str,
    url: str,
    *,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    current_url = url
    merged_headers = _build_webdav_headers(target)
    if headers:
        merged_headers.update(headers)

    for _ in range(5):
        connection, request_path = _build_webdav_connection(
            current_url,
            timeout_seconds=target.webdav_timeout_seconds,
            verify_ssl=bool(target.webdav_verify_ssl),
        )

        try:
            connection.request(method, request_path, body=body, headers=merged_headers)
            response = connection.getresponse()
            status_code = response.status
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            response_body = response.read()
        finally:
            connection.close()

        if status_code in {301, 302, 307, 308} and response_headers.get("location"):
            current_url = urljoin(current_url, response_headers["location"])
            continue

        return status_code, response_headers, response_body

    raise RuntimeError("WebDAV request redirected too many times")


def _ensure_webdav_directories(target: BackupTarget, remote_path: str) -> None:
    normalized_root = "/".join(part for part in remote_path.split("/")[:-1] if part)
    if not normalized_root:
        return

    current_path = ""
    for segment in normalized_root.split("/"):
        current_path = f"{current_path}/{segment}" if current_path else segment
        status_code = _perform_webdav_request(
            target,
            "MKCOL",
            _build_webdav_url(target.webdav_base_url, current_path),
        )
        if status_code in {200, 201, 204, 301, 302, 405}:
            continue
        if status_code == 409:
            raise RuntimeError(f"Unable to create remote directory {current_path}; check parent path and permissions")
        raise RuntimeError(f"Failed to create remote directory: HTTP {status_code}")


def _upload_file_to_webdav(target: BackupTarget, local_path: Path, remote_path: str) -> str:
    _ensure_webdav_directories(target, remote_path)
    target_url = _build_webdav_url(target.webdav_base_url, remote_path)
    connection, request_path = _build_webdav_connection(
        target_url,
        timeout_seconds=target.webdav_timeout_seconds,
        verify_ssl=bool(target.webdav_verify_ssl),
    )
    headers = _build_webdav_headers(target)
    headers["Content-Length"] = str(local_path.stat().st_size)
    headers["Content-Type"] = "application/octet-stream"

    try:
        with local_path.open("rb") as file_handle:
            connection.request("PUT", request_path, body=file_handle, headers=headers)
            response = connection.getresponse()
            status_code = response.status
            response.read()
    finally:
        connection.close()

    if status_code not in {200, 201, 204}:
        raise RuntimeError(f"WebDAV upload failed: HTTP {status_code}")

    return _sanitize_url(target_url)


def _delete_webdav_file(target: BackupTarget, remote_path: str) -> bool:
    status_code = _perform_webdav_request(
        target,
        "DELETE",
        _build_webdav_url(target.webdav_base_url, remote_path),
    )
    return status_code in {200, 202, 204, 404}


def _extract_relative_webdav_path(base_url: str, href: str) -> str:
    base_path = urlsplit(base_url).path.rstrip("/")
    href_path = unquote(urlsplit(href).path).rstrip("/")
    if base_path and href_path.startswith(base_path):
        href_path = href_path[len(base_path):]
    return _normalize_remote_path(href_path)


def _serialize_remote_file(
    target: BackupTarget,
    *,
    name: str,
    remote_path: str,
    size_bytes: float | None,
    modified_at: datetime | None,
) -> dict[str, Any]:
    parsed_meta = _parse_backup_file_name(name, target=target)
    return {
        "name": name,
        "remote_path": remote_path,
        "remote_url": _sanitize_url(_build_webdav_url(target.webdav_base_url, remote_path)),
        "size_bytes": size_bytes,
        "modified_at": _to_iso(modified_at),
        "backup_time": parsed_meta["backup_time"],
        "backup_mode": parsed_meta["backup_mode"],
        "range_label": parsed_meta["range_label"],
        "file_format": parsed_meta["file_format"],
    }


def _list_webdav_files(target: BackupTarget) -> list[dict[str, Any]]:
    remote_root = _normalize_webdav_root_path(target.webdav_root_path)
    status_code, _, response_body = _perform_webdav_request_raw(
        target,
        "PROPFIND",
        _build_webdav_url(target.webdav_base_url, remote_root),
        body=(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:propfind xmlns:d="DAV:"><d:prop>'
            "<d:displayname/><d:getcontentlength/><d:getlastmodified/><d:resourcetype/>"
            "</d:prop></d:propfind>"
        ).encode("utf-8"),
        headers={
            "Depth": "1",
            "Content-Type": 'application/xml; charset="utf-8"',
        },
    )

    if status_code == 404:
        return []
    if status_code not in {200, 207}:
        raise RuntimeError(f"Failed to list WebDAV directory: HTTP {status_code}")

    try:
        xml_root = ET.fromstring(response_body)
    except ET.ParseError as exc:
        raise RuntimeError("WebDAV directory listing returned invalid XML") from exc

    namespace = {"d": "DAV:"}
    files: list[dict[str, Any]] = []
    for response_node in xml_root.findall("d:response", namespace):
        href = response_node.findtext("d:href", default="", namespaces=namespace)
        relative_path = _extract_relative_webdav_path(target.webdav_base_url, href)
        if not relative_path or relative_path == remote_root:
            continue

        resource_type = response_node.find(".//d:resourcetype", namespace)
        if resource_type is not None and resource_type.find("d:collection", namespace) is not None:
            continue

        display_name = response_node.findtext(".//d:displayname", default="", namespaces=namespace).strip()
        file_name = display_name or Path(relative_path).name
        content_length = response_node.findtext(".//d:getcontentlength", default="", namespaces=namespace).strip()
        modified_raw = response_node.findtext(".//d:getlastmodified", default="", namespaces=namespace).strip()

        size_bytes = None
        if content_length:
            try:
                size_bytes = float(content_length)
            except ValueError:
                size_bytes = None

        modified_at = None
        if modified_raw:
            try:
                modified_at = datetime.strptime(modified_raw, "%a, %d %b %Y %H:%M:%S %Z")
            except ValueError:
                try:
                    modified_at = datetime.strptime(modified_raw, "%a, %d %b %Y %H:%M:%S GMT")
                except ValueError:
                    modified_at = None

        files.append(
            _serialize_remote_file(
                target,
                name=file_name,
                remote_path=relative_path,
                size_bytes=size_bytes,
                modified_at=modified_at,
            )
        )

    files.sort(
        key=lambda item: (
            item.get("backup_time") or item.get("modified_at") or "",
            item.get("name") or "",
        ),
        reverse=True,
    )
    return files


def _validate_remote_file_path(target: BackupTarget, remote_path: str) -> str:
    normalized_path = _normalize_remote_path(remote_path)
    if not normalized_path:
        raise ValueError("remote_path is required")

    normalized_root = _normalize_webdav_root_path(target.webdav_root_path)
    if normalized_root and normalized_path != normalized_root and not normalized_path.startswith(f"{normalized_root}/"):
        raise ValueError("remote_path is outside the configured WebDAV directory")

    return normalized_path


def _cleanup_local_file(path_value: str | None) -> bool:
    if not path_value:
        return False
    try:
        path = Path(path_value)
        if path.exists():
            path.unlink()
            return True
    except Exception:
        logger.warning("Failed to delete local backup file: %s", path_value, exc_info=True)
    return False


def _apply_retention(target_id: int, *, current_run_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    deleted_local = 0
    deleted_remote = 0
    removed_run_ids: list[int] = []

    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            return {"deleted_local_files": 0, "deleted_remote_files": 0, "removed_run_ids": []}

        runs = (
            session.query(BackupRun)
            .filter(BackupRun.target_id == target_id, BackupRun.status == "success")
            .order_by(BackupRun.finished_at.desc().nullslast(), BackupRun.id.desc())
            .all()
        )

        for index, run in enumerate(runs):
            if run.id == current_run_id:
                continue

            if not (target.retention_count > 0 and index >= target.retention_count):
                continue

            local_pruned = not run.local_path
            remote_pruned = not run.remote_path

            if run.local_path and _cleanup_local_file(run.local_path):
                deleted_local += 1
                local_pruned = True

            if target.target_kind == "webdav" and run.remote_path:
                try:
                    if _delete_webdav_file(target, run.remote_path):
                        deleted_remote += 1
                        remote_pruned = True
                except Exception:
                    logger.warning("Failed to delete remote backup file: %s", run.remote_path, exc_info=True)

            if local_pruned:
                run.local_path = None
            if remote_pruned:
                run.remote_path = None
                run.remote_url = None
            run.result_json = {
                **(run.result_json or {}),
                "artifact_pruned": bool(local_pruned and remote_pruned),
            }
            session.add(run)
            removed_run_ids.append(run.id)

        session.commit()

    return {
        "deleted_local_files": deleted_local,
        "deleted_remote_files": deleted_remote,
        "removed_run_ids": removed_run_ids,
    }


def _perform_backup(target: BackupTarget) -> dict[str, Any]:
    file_name, file_format = _build_file_name(target)

    if target.target_kind == "local":
        temp_output_path = _resolve_local_output_path(target, file_name)
        temp_dir = None
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="tg-backup-upload-")
        temp_output_path = Path(temp_dir.name) / file_name

    try:
        if target.backup_mode == "media_export":
            item_count = _write_export_xlsx(temp_output_path, target)
            manifest = {
                "mode": "media_export",
                "range_kind": target.export_range_kind,
                "range_days": target.export_range_days,
                "exported_rows": item_count,
            }
        else:
            item_count, manifest = _build_full_backup_archive(target, temp_output_path)
            manifest["mode"] = "full"

        file_size_bytes, sha256 = _hash_file(temp_output_path)
        result: dict[str, Any] = {
            "file_name": file_name,
            "file_format": file_format,
            "file_size_bytes": file_size_bytes,
            "sha256": sha256,
            "item_count": item_count,
            "result_json": manifest,
            "local_path": str(temp_output_path) if target.target_kind == "local" else None,
            "remote_path": None,
            "remote_url": None,
        }

        if target.target_kind == "webdav":
            remote_path = _build_remote_file_path(target, file_name)
            remote_url = _upload_file_to_webdav(target, temp_output_path, remote_path)
            result["remote_path"] = remote_path
            result["remote_url"] = remote_url

        return result
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def _clone_target(target: BackupTarget) -> BackupTarget:
    cloned = BackupTarget()
    for field in (
        "id",
        "name",
        "target_kind",
        "provider",
        "is_enabled",
        "backup_mode",
        "schedule_enabled",
        "schedule_kind",
        "schedule_hour",
        "schedule_minute",
        "schedule_priority",
        "schedule_weekday",
        "schedule_day",
        "timezone",
        "retention_count",
        "retention_days",
        "run_log_retention_days",
        "local_dir",
        "webdav_base_url",
        "webdav_username",
        "webdav_password_encrypted",
        "webdav_root_path",
        "webdav_timeout_seconds",
        "webdav_verify_ssl",
        "include_database",
        "include_users_json",
        "include_env_file",
        "include_runtime_data",
        "export_range_kind",
        "export_range_days",
    ):
        setattr(cloned, field, getattr(target, field))
    return cloned


def _execute_backup_run(run_id: int) -> None:
    ensure_runtime_storage_tables()
    started_at = _utc_now()

    with Session(engine) as session:
        run = session.get(BackupRun, run_id)
        if run is None:
            return
        if run.status != "running":
            return
        started_at = run.started_at or started_at

    try:
        with Session(engine) as session:
            run = session.get(BackupRun, run_id)
            if run is None:
                raise LookupError("Backup run not found")
            if run.target_id is None:
                raise LookupError("Backup target not found")
            target = session.get(BackupTarget, run.target_id)
            if target is None:
                raise LookupError("Backup target not found")
            target_snapshot = _clone_target(target)

        result = _perform_backup(target_snapshot)
        cleanup_info = _apply_retention(target_snapshot.id, current_run_id=run_id)
        finished_at = _utc_now()
        duration = max(0.0, (finished_at - started_at).total_seconds())

        with Session(engine) as session:
            run = session.get(BackupRun, run_id)
            target = session.get(BackupTarget, target_snapshot.id)
            if run is None or target is None:
                return

            run.status = "success"
            run.file_name = result["file_name"]
            run.file_format = result["file_format"]
            run.file_size_bytes = result["file_size_bytes"]
            run.sha256 = result["sha256"]
            run.local_path = result["local_path"]
            run.remote_path = result["remote_path"]
            run.remote_url = result["remote_url"]
            run.item_count = result["item_count"]
            run.finished_at = finished_at
            run.duration_seconds = duration
            run.error_message = None
            run.result_json = {**(result["result_json"] or {}), "retention": cleanup_info}

            target.last_run_at = finished_at
            target.last_status = "success"
            target.last_error_message = None
            if target.schedule_enabled and target.is_enabled and target.next_run_at is None:
                target.next_run_at = _compute_next_run_at(target, now_utc=finished_at)

            session.add(run)
            session.add(target)
            session.commit()

    except Exception as exc:
        logger.exception("Backup run %s failed", run_id)
        finished_at = _utc_now()
        duration = max(0.0, (finished_at - started_at).total_seconds())
        with Session(engine) as session:
            run = session.get(BackupRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.finished_at = finished_at
            run.duration_seconds = duration
            run.error_message = str(exc)
            run.result_json = {**(run.result_json or {}), "error": str(exc)}
            session.add(run)

            if run.target_id is not None:
                target = session.get(BackupTarget, run.target_id)
                if target is not None:
                    target.last_status = "failed"
                    target.last_error_message = str(exc)
                    target.last_run_at = finished_at
                    if target.schedule_enabled and target.is_enabled and target.next_run_at is None:
                        target.next_run_at = _compute_next_run_at(target, now_utc=finished_at)
                    session.add(target)

            session.commit()


def test_backup_target(target_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        target = session.get(BackupTarget, target_id)
        if target is None:
            raise LookupError("Backup target not found")

        if target.target_kind == "local":
            resolved_path = _resolve_local_output_path(target, ".probe").parent
            resolved_path.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "target_kind": "local",
                "message": "Local directory is writable",
                "resolved_path": str(resolved_path),
                "remote_path": None,
            }

        probe_path = _build_remote_file_path(target, ".probe")
        _ensure_webdav_directories(target, probe_path)
        return {
            "success": True,
            "target_kind": "webdav",
            "message": "WebDAV connection succeeded",
            "resolved_path": None,
            "remote_path": _normalize_webdav_root_path(target.webdav_root_path),
        }
