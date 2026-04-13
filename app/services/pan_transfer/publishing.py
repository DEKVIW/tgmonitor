from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import (
    LinkCheckDetails,
    LinkTarget,
    Message,
    PanTransferAccount,
    PanTransferBatchItem,
    PanTransferPublishRecord,
    ensure_runtime_storage_tables,
)
from app.services.resource_ops import ensure_message_link_refs_for_messages
from app.services.resource_ops.catalog import flatten_message_links

from .common import utcnow
from .execution_logs import append_pan_transfer_execution_log
from .providers import decrypt_account_credential, get_pan_transfer_provider
from .validation import validate_share_url
from .worker import (
    _build_share_request_from_snapshot,
    _describe_exception,
    _extract_error_payload,
    _get_share_request,
    _get_staging_snapshot,
    _mark_account_validation,
)


_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _current_local_message_time() -> datetime:
    return datetime.now(_SHANGHAI_TZ).replace(tzinfo=None)


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_publish_tags(values: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        tag = _normalize_text(raw_value, max_length=64)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized


def _extract_primary_flattened_link(value: Any) -> Any | None:
    flattened = flatten_message_links(value)
    if not flattened:
        return None
    return flattened[0]


def _extract_primary_url_from_links(value: Any) -> str | None:
    item = _extract_primary_flattened_link(value)
    if item is None:
        return None
    return _normalize_text(getattr(item, "target_url", None)) or None


def _detect_platform_from_url(url: str, *, fallback: str | None = None) -> str:
    item = _extract_primary_flattened_link({"url": url})
    if item is not None:
        platform = _normalize_text(getattr(item, "platform", None), max_length=64)
        if platform:
            return platform
    return _normalize_text(fallback, max_length=64)


def _find_existing_target_for_url(session: Session, *, url: str) -> LinkTarget | None:
    item = _extract_primary_flattened_link({"url": url})
    if item is None:
        return None
    return (
        session.query(LinkTarget)
        .filter(
            LinkTarget.platform == item.platform,
            LinkTarget.normalized_url_hash == item.normalized_url_hash,
        )
        .first()
    )


def _build_publish_links_payload(*, platform: str, source_url: str, title: str) -> dict[str, Any]:
    provider_label = _normalize_text(platform, max_length=64) or "网盘链接"
    return {
        provider_label: [
            {
                "url": source_url,
                "label": title,
            }
        ]
    }


def _build_message_netdisk_types(platform: str) -> list[str]:
    normalized_platform = _normalize_text(platform, max_length=64)
    return [normalized_platform] if normalized_platform else []


def _resolve_publish_source_url(session: Session, *, item: PanTransferBatchItem) -> str:
    if item.new_link_target_id is not None:
        target = session.get(LinkTarget, int(item.new_link_target_id))
        if target is not None and _normalize_text(target.original_url):
            return _normalize_text(target.original_url)
    if _normalize_text(item.new_share_url):
        return _normalize_text(item.new_share_url)
    if _normalize_text(item.original_url):
        return _normalize_text(item.original_url)
    raise ValueError("no publishable source url is available for this transfer item")


def _append_publish_history(item: PanTransferBatchItem, *, entry: dict[str, Any]) -> None:
    extra_json = dict(item.extra_json or {})
    current_history = extra_json.get("manual_publish_history")
    history: list[dict[str, Any]] = []
    if isinstance(current_history, list):
        for raw_entry in current_history:
            if isinstance(raw_entry, dict):
                history.append(dict(raw_entry))
    history.append(dict(entry))
    extra_json["last_manual_publish"] = dict(entry)
    extra_json["manual_publish_history"] = history[-20:]
    item.extra_json = extra_json


def _append_publish_record_refresh_history(row: PanTransferPublishRecord, *, entry: dict[str, Any]) -> None:
    extra_json = dict(row.extra_json or {})
    current_history = extra_json.get("share_refresh_history")
    history: list[dict[str, Any]] = []
    if isinstance(current_history, list):
        for raw_entry in current_history:
            if isinstance(raw_entry, dict):
                history.append(dict(raw_entry))
    history.append(dict(entry))
    extra_json["last_share_refresh"] = dict(entry)
    extra_json["share_refresh_history"] = history[-20:]
    row.extra_json = extra_json


def _build_link_health_snapshot(session: Session, *, url: str | None) -> dict[str, Any]:
    normalized_url = _normalize_text(url)
    if not normalized_url:
        return {
            "status": None,
            "detail_message": None,
            "checked_at": None,
        }

    flattened = _extract_primary_flattened_link({"url": normalized_url})
    query = session.query(LinkCheckDetails)
    if flattened is not None and _normalize_text(getattr(flattened, "normalized_url", None)):
        query = query.filter(LinkCheckDetails.normalized_url == getattr(flattened, "normalized_url"))
    else:
        query = query.filter(LinkCheckDetails.url == normalized_url)
    row = query.order_by(LinkCheckDetails.check_time.desc(), LinkCheckDetails.id.desc()).first()
    if row is None:
        return {
            "status": "unknown",
            "detail_message": "暂无校验记录",
            "checked_at": None,
        }
    if row.is_valid is True:
        return {
            "status": "healthy",
            "detail_message": _normalize_text(row.error_reason, max_length=255) or "链接有效",
            "checked_at": row.check_time,
        }
    return {
        "status": "invalid",
        "detail_message": _normalize_text(row.error_reason, max_length=255) or "链接失效",
        "checked_at": row.check_time,
    }


def _build_published_validation_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _normalize_text(result.get("status"), max_length=32).lower() or "unknown",
        "detail_message": _normalize_text(result.get("detail_message"), max_length=255) or None,
        "checked_at": utcnow().isoformat() + "Z",
        "result": dict(result.get("result") or {}),
    }


def _get_publish_record_row(session: Session, *, record_id: int) -> PanTransferPublishRecord:
    row = session.get(PanTransferPublishRecord, int(record_id))
    if row is None:
        raise LookupError("publish record not found")
    return row


def _get_publish_record_batch_item(session: Session, *, row: PanTransferPublishRecord) -> PanTransferBatchItem | None:
    if row.source_batch_item_id is None:
        return None
    query = session.query(PanTransferBatchItem).filter(PanTransferBatchItem.id == int(row.source_batch_item_id))
    if row.source_batch_id is not None:
        query = query.filter(PanTransferBatchItem.batch_id == int(row.source_batch_id))
    return query.first()


def _get_publish_record_message(session: Session, *, row: PanTransferPublishRecord) -> Message | None:
    if row.published_message_id is None:
        return None
    return session.get(Message, int(row.published_message_id))


def _resolve_published_link_status(
    session: Session,
    *,
    row: PanTransferPublishRecord,
    published_url: str | None,
) -> dict[str, Any]:
    validation = dict(dict(row.extra_json or {}).get("published_link_validation") or {})
    if validation:
        return {
            "status": _normalize_text(validation.get("status"), max_length=32).lower() or "unknown",
            "detail_message": _normalize_text(validation.get("detail_message"), max_length=255) or None,
            "checked_at": _parse_datetime(validation.get("checked_at")),
        }
    return _build_link_health_snapshot(session, url=published_url)


def _serialize_publish_record(session: Session, row: PanTransferPublishRecord) -> dict[str, Any]:
    extra_json = dict(row.extra_json or {})
    batch_item = _get_publish_record_batch_item(session, row=row)
    message = _get_publish_record_message(session, row=row)
    published_url = _extract_primary_url_from_links(getattr(message, "links", None)) or _normalize_text(row.source_url) or None
    published_platform = _detect_platform_from_url(published_url or "", fallback=str(row.platform or ""))
    source_original_url = (
        _normalize_text(extra_json.get("source_original_url"))
        or _normalize_text(getattr(batch_item, "original_url", None))
        or None
    )
    current_share_url = (
        _normalize_text(extra_json.get("current_share_url"))
        or _normalize_text(getattr(batch_item, "new_share_url", None))
        or None
    )
    original_snapshot = _build_link_health_snapshot(session, url=source_original_url)
    current_share_snapshot = _build_link_health_snapshot(session, url=current_share_url)
    published_snapshot = _resolve_published_link_status(session, row=row, published_url=published_url)

    can_refresh_share = False
    if batch_item is not None and batch_item.target_account_id is not None and _get_staging_snapshot(batch_item) is not None:
        account = session.get(PanTransferAccount, int(batch_item.target_account_id))
        can_refresh_share = account is not None and bool(account.is_enabled)

    published_tags = _normalize_publish_tags(list(getattr(message, "tags", None) or list(row.published_tags or [])))
    return {
        "id": int(row.id),
        "source_type": str(row.source_type or "manual"),
        "source_batch_id": int(row.source_batch_id) if row.source_batch_id is not None else None,
        "source_batch_item_id": int(row.source_batch_item_id) if row.source_batch_item_id is not None else None,
        "source_link_target_id": int(row.source_link_target_id) if row.source_link_target_id is not None else None,
        "source_new_link_target_id": int(row.source_new_link_target_id) if row.source_new_link_target_id is not None else None,
        "platform": published_platform,
        "source_url": published_url or "",
        "source_original_url": source_original_url,
        "current_share_url": current_share_url,
        "published_message_id": int(row.published_message_id) if row.published_message_id is not None else None,
        "published_title": _normalize_text(getattr(message, "title", None), max_length=255) or str(row.published_title or ""),
        "published_description": _normalize_text(getattr(message, "description", None), max_length=1000) or (_normalize_text(row.published_description, max_length=1000) or None),
        "published_tags": published_tags,
        "original_link_status": original_snapshot["status"],
        "current_share_status": current_share_snapshot["status"],
        "published_link_status": published_snapshot["status"],
        "published_link_detail_message": published_snapshot["detail_message"],
        "published_link_checked_at": published_snapshot["checked_at"],
        "can_refresh_share": can_refresh_share,
        "can_edit": message is not None,
        "operator": _normalize_text(row.operator, max_length=128) or None,
        "extra_json": extra_json,
        "published_at": row.published_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _create_admin_manual_message(
    session: Session,
    *,
    platform: str,
    source_url: str,
    title: str,
    description: str | None,
    tags: list[str] | None,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    publish_title = _normalize_text(title, max_length=255)
    if not publish_title:
        raise ValueError("title cannot be empty")

    publish_source_url = _normalize_text(source_url)
    if not publish_source_url:
        raise ValueError("source_url cannot be empty")

    publish_platform = _detect_platform_from_url(publish_source_url, fallback=platform)
    publish_description = _normalize_text(description, max_length=1000) or None
    publish_tags = _normalize_publish_tags(tags)
    existing_target = _find_existing_target_for_url(session, url=publish_source_url)
    published_local_time = _current_local_message_time()

    message = Message(
        timestamp=published_local_time,
        title=publish_title,
        description=publish_description,
        tags=publish_tags,
        links=_build_publish_links_payload(
            platform=publish_platform,
            source_url=publish_source_url,
            title=publish_title,
        ),
        source="admin_manual",
        channel="管理员发布",
        group_name="运营发布",
        bot=_normalize_text(operator, max_length=255) or "admin",
        netdisk_types=_build_message_netdisk_types(publish_platform),
    )
    session.add(message)
    session.flush()

    refs_by_message, _ = ensure_message_link_refs_for_messages(session, [message])
    published_refs = refs_by_message.get(int(message.id), [])
    published_link_target_id = int(published_refs[0].link_target_id) if published_refs else None
    reused_existing_target = existing_target is not None and published_link_target_id == int(existing_target.id)
    return {
        "message": message,
        "published_at": published_local_time,
        "published_link_target_id": published_link_target_id,
        "reused_existing_target": reused_existing_target,
        "platform": publish_platform,
    }


def _create_publish_record(
    session: Session,
    *,
    source_type: str,
    platform: str,
    source_url: str,
    title: str,
    description: str | None,
    tags: list[str] | None,
    operator: str | None,
    message_id: int | None,
    published_at: datetime,
    source_batch_id: int | None = None,
    source_batch_item_id: int | None = None,
    source_link_target_id: int | None = None,
    source_new_link_target_id: int | None = None,
    extra_json: dict[str, Any] | None = None,
) -> PanTransferPublishRecord:
    record = PanTransferPublishRecord(
        source_type=_normalize_text(source_type, max_length=32) or "manual",
        source_batch_id=source_batch_id,
        source_batch_item_id=source_batch_item_id,
        source_link_target_id=source_link_target_id,
        source_new_link_target_id=source_new_link_target_id,
        platform=_normalize_text(platform, max_length=64),
        source_url=_normalize_text(source_url),
        published_message_id=message_id,
        published_title=_normalize_text(title, max_length=255),
        published_description=_normalize_text(description, max_length=1000) or None,
        published_tags=_normalize_publish_tags(tags),
        operator=_normalize_text(operator, max_length=128) or None,
        extra_json=dict(extra_json or {}),
        published_at=published_at,
    )
    session.add(record)
    session.flush()
    return record


def list_pan_transfer_publish_records(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    query = session.query(PanTransferPublishRecord)
    total = int(query.count() or 0)
    rows = (
        query.order_by(PanTransferPublishRecord.published_at.desc(), PanTransferPublishRecord.id.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return {
        "items": [_serialize_publish_record(session, row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
    }


def update_pan_transfer_publish_record(
    session: Session,
    *,
    record_id: int,
    payload: dict[str, Any],
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    row = _get_publish_record_row(session, record_id=record_id)
    message = _get_publish_record_message(session, row=row)
    if message is None:
        raise LookupError("published frontend message not found")

    source_url = _normalize_text(payload.get("source_url"))
    if not source_url:
        raise ValueError("source_url cannot be empty")
    title = _normalize_text(payload.get("title"), max_length=255)
    if not title:
        raise ValueError("title cannot be empty")
    description = _normalize_text(payload.get("description"), max_length=1000) or None
    tags = _normalize_publish_tags(list(payload.get("tags") or []))
    publish_platform = _detect_platform_from_url(source_url, fallback=str(row.platform or ""))
    existing_target = _find_existing_target_for_url(session, url=source_url)

    message.title = title
    message.description = description
    message.tags = tags
    message.links = _build_publish_links_payload(platform=publish_platform, source_url=source_url, title=title)
    message.netdisk_types = _build_message_netdisk_types(publish_platform)
    session.add(message)
    refs_by_message, _ = ensure_message_link_refs_for_messages(session, [message])
    published_refs = refs_by_message.get(int(message.id), [])
    published_link_target_id = int(published_refs[0].link_target_id) if published_refs else None
    reused_existing_target = existing_target is not None and published_link_target_id == int(existing_target.id)

    extra_json = dict(row.extra_json or {})
    extra_json["published_link_target_id"] = published_link_target_id
    extra_json["reused_existing_target"] = reused_existing_target
    extra_json["published_link_validation"] = {}
    extra_json["last_publish_edit"] = {
        "operator": _normalize_text(operator, max_length=128) or None,
        "updated_at": utcnow().isoformat() + "Z",
    }

    row.platform = publish_platform
    row.source_url = source_url
    row.published_title = title
    row.published_description = description
    row.published_tags = tags
    row.operator = _normalize_text(operator, max_length=128) or row.operator
    row.extra_json = extra_json
    session.add(row)
    session.flush()
    return _serialize_publish_record(session, row)


async def validate_pan_transfer_publish_record(
    session: Session,
    *,
    record_id: int,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    row = _get_publish_record_row(session, record_id=record_id)
    message = _get_publish_record_message(session, row=row)
    current_url = _extract_primary_url_from_links(getattr(message, "links", None)) or _normalize_text(row.source_url)
    if not current_url:
        raise ValueError("published source_url is missing")

    result = await validate_share_url(current_url)
    extra_json = dict(row.extra_json or {})
    extra_json["published_link_validation"] = _build_published_validation_snapshot(result)
    row.source_url = current_url
    row.extra_json = extra_json
    session.add(row)
    session.flush()
    return _serialize_publish_record(session, row)


async def refresh_pan_transfer_publish_record_share(
    session: Session,
    *,
    record_id: int,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    row = _get_publish_record_row(session, record_id=record_id)
    if _normalize_text(row.source_type, max_length=32) != "batch_item":
        raise ValueError("only batch-item publish records can refresh share")

    item = _get_publish_record_batch_item(session, row=row)
    if item is None:
        raise LookupError("source batch item not found")
    message = _get_publish_record_message(session, row=row)
    if message is None:
        raise LookupError("published frontend message not found")
    account = session.get(PanTransferAccount, int(item.target_account_id or 0))
    if account is None:
        raise LookupError("target account not found")
    if not bool(account.is_enabled):
        raise ValueError("target account is disabled")

    staging_snapshot = _get_staging_snapshot(item)
    if staging_snapshot is None:
        raise ValueError("staging snapshot is missing, cannot recreate share")
    share_request = _get_share_request(item)
    if share_request is None:
        share_request = _build_share_request_from_snapshot(account=account, item=item, staging_snapshot=staging_snapshot)

    credential_value = decrypt_account_credential(account)
    provider = get_pan_transfer_provider(str(item.platform or row.platform or ""))
    append_pan_transfer_execution_log(
        session,
        item=item,
        stage="share",
        message="Refreshing share for published frontend message",
        payload={
            "published_record_id": int(row.id),
            "published_message_id": int(message.id),
            "account_id": int(account.id),
            "account_name": _normalize_text(account.account_name, max_length=128) or None,
            "staging_root": _normalize_text(staging_snapshot.get("root")),
            "staging_folder_name": _normalize_text(staging_snapshot.get("folder_name"), max_length=255) or None,
            "share_target_mode": _normalize_text(share_request.get("share_target_mode"), max_length=32) or None,
        },
    )
    try:
        share_result = await provider.share_staging_target(
            credential_value=credential_value,
            account_name=_normalize_text(account.account_name, max_length=128),
            staging_root=_normalize_text(staging_snapshot.get("root")),
            staging_folder_name=_normalize_text(staging_snapshot.get("folder_name"), max_length=255),
            staging_folder_id=_normalize_text(staging_snapshot.get("folder_id"), max_length=255) or None,
            share_target_mode=_normalize_text(share_request.get("share_target_mode"), max_length=32) or "resource_dir",
            share_mode=_normalize_text(share_request.get("share_mode"), max_length=32) or "public",
            share_passcode=_normalize_text(share_request.get("share_passcode"), max_length=32) or None,
            share_expire_days=share_request.get("share_expire_days"),
            title_hint=_normalize_text(share_request.get("title_hint"), max_length=255) or _normalize_text(row.published_title, max_length=255) or None,
        )
    except Exception as exc:
        error_detail = _describe_exception(exc)
        error_payload = {
            "published_record_id": int(row.id),
            "published_message_id": int(message.id),
            "account_id": int(account.id),
            "account_name": _normalize_text(account.account_name, max_length=128) or None,
            **_extract_error_payload(exc),
        }
        _mark_account_validation(account, ok=False, detail_message=error_detail, payload=error_payload)
        session.add(account)
        session.flush()
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="share",
            level="error",
            message=f"Share refresh failed: {error_detail}",
            payload=error_payload,
        )
        raise ValueError(f"刷新分享失败：{error_detail}") from exc

    validation_result = await validate_share_url(str(share_result.new_share_url or ""))
    validation_snapshot = _build_published_validation_snapshot(validation_result)
    if validation_snapshot["status"] == "invalid":
        detail_message = _normalize_text(validation_snapshot["detail_message"], max_length=255) or "new share URL validation failed"
        _mark_account_validation(account, ok=False, detail_message=detail_message, payload=dict(validation_result))
        session.add(account)
        session.flush()
        append_pan_transfer_execution_log(
            session,
            item=item,
            stage="validate",
            level="error",
            message=f"Refreshed share validation failed: {detail_message}",
            payload=dict(validation_result),
        )
        raise ValueError(f"新分享校验未通过：{detail_message}")

    publish_platform = _detect_platform_from_url(str(share_result.new_share_url or ""), fallback=str(row.platform or item.platform or ""))
    message.links = _build_publish_links_payload(
        platform=publish_platform,
        source_url=str(share_result.new_share_url or ""),
        title=_normalize_text(message.title, max_length=255) or _normalize_text(row.published_title, max_length=255),
    )
    message.netdisk_types = _build_message_netdisk_types(publish_platform)
    session.add(message)
    refs_by_message, _ = ensure_message_link_refs_for_messages(session, [message])
    published_refs = refs_by_message.get(int(message.id), [])
    published_link_target_id = int(published_refs[0].link_target_id) if published_refs else None

    refresh_entry = {
        "share_url": _normalize_text(share_result.new_share_url),
        "share_title": _normalize_text(share_result.share_title, max_length=255) or None,
        "share_passcode": _normalize_text(share_result.share_passcode, max_length=32) or None,
        "operator": _normalize_text(operator, max_length=128) or None,
        "refreshed_at": utcnow().isoformat() + "Z",
    }
    _append_publish_record_refresh_history(row, entry=refresh_entry)
    extra_json = dict(row.extra_json or {})
    extra_json["current_share_url"] = _normalize_text(share_result.new_share_url)
    extra_json["published_link_target_id"] = published_link_target_id
    extra_json["published_link_validation"] = validation_snapshot
    extra_json["refresh_provider_payload"] = dict(share_result.payload or {})

    row.platform = publish_platform
    row.source_url = _normalize_text(share_result.new_share_url)
    row.operator = _normalize_text(operator, max_length=128) or row.operator
    row.extra_json = extra_json

    _mark_account_validation(account, ok=True, detail_message="Validated during publish share refresh", payload=dict(share_result.payload or {}))
    session.add(account)
    session.add(row)
    session.flush()

    append_pan_transfer_execution_log(
        session,
        item=item,
        stage="publish",
        message="Published frontend message updated to refreshed share URL",
        payload={
            "published_record_id": int(row.id),
            "published_message_id": int(message.id),
            "new_share_url": _normalize_text(share_result.new_share_url),
            "published_link_target_id": published_link_target_id,
        },
    )
    return _serialize_publish_record(session, row)


def publish_manual_pan_transfer_message(
    session: Session,
    *,
    payload: dict[str, Any],
    operator: str | None,
) -> dict[str, Any]:
    publish_platform = _normalize_text(payload.get("platform"), max_length=64)
    publish_source_url = _normalize_text(payload.get("source_url"))
    publish_title = _normalize_text(payload.get("title"), max_length=255)
    publish_description = _normalize_text(payload.get("description"), max_length=1000) or None
    publish_tags = _normalize_publish_tags(list(payload.get("tags") or []))

    created = _create_admin_manual_message(
        session,
        platform=publish_platform,
        source_url=publish_source_url,
        title=publish_title,
        description=publish_description,
        tags=publish_tags,
        operator=operator,
    )
    message = created["message"]
    _create_publish_record(
        session,
        source_type="manual",
        platform=created["platform"],
        source_url=publish_source_url,
        title=publish_title,
        description=publish_description,
        tags=publish_tags,
        operator=operator,
        message_id=int(message.id),
        published_at=created["published_at"],
        extra_json={
            "reused_existing_target": created["reused_existing_target"],
            "published_link_target_id": created["published_link_target_id"],
        },
    )
    return {
        "message_id": int(message.id),
        "title": publish_title,
        "source_url": publish_source_url,
        "link_target_id": created["published_link_target_id"],
        "published_at": message.timestamp,
        "reused_existing_target": created["reused_existing_target"],
    }


def publish_pan_transfer_batch_item_message(
    session: Session,
    *,
    batch_id: int,
    item_id: int,
    payload: dict[str, Any],
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    item = (
        session.query(PanTransferBatchItem)
        .filter(
            PanTransferBatchItem.batch_id == int(batch_id),
            PanTransferBatchItem.id == int(item_id),
        )
        .first()
    )
    if item is None:
        raise LookupError("pan transfer batch item not found")

    publish_title = _normalize_text(payload.get("title"), max_length=255)
    if not publish_title:
        raise ValueError("title cannot be empty")

    publish_description = _normalize_text(payload.get("description"), max_length=1000) or None
    publish_tags = _normalize_publish_tags(list(payload.get("tags") or []))
    source_url = _resolve_publish_source_url(session, item=item)
    created = _create_admin_manual_message(
        session,
        platform=str(item.platform or ""),
        source_url=source_url,
        title=publish_title,
        description=publish_description,
        tags=publish_tags,
        operator=operator,
    )
    message = created["message"]

    publish_entry = {
        "message_id": int(message.id),
        "title": publish_title,
        "source_url": source_url,
        "link_target_id": created["published_link_target_id"],
        "operator": _normalize_text(operator, max_length=128) or "admin",
        "published_at": created["published_at"].isoformat(),
    }
    _append_publish_history(item, entry=publish_entry)
    session.add(item)
    session.flush()

    _create_publish_record(
        session,
        source_type="batch_item",
        platform=created["platform"],
        source_url=source_url,
        title=publish_title,
        description=publish_description,
        tags=publish_tags,
        operator=operator,
        message_id=int(message.id),
        published_at=created["published_at"],
        source_batch_id=int(item.batch_id),
        source_batch_item_id=int(item.id),
        source_link_target_id=int(item.link_target_id),
        source_new_link_target_id=int(item.new_link_target_id) if item.new_link_target_id is not None else None,
        extra_json={
            "reused_existing_target": created["reused_existing_target"],
            "published_link_target_id": created["published_link_target_id"],
            "source_original_url": _normalize_text(item.original_url) or None,
            "current_share_url": _normalize_text(item.new_share_url) or None,
        },
    )

    append_pan_transfer_execution_log(
        session,
        item=item,
        stage="publish",
        message="Admin message published to feed",
        payload={
            "published_message_id": int(message.id),
            "published_title": publish_title,
            "source_url": source_url,
            "published_link_target_id": created["published_link_target_id"],
            "reused_existing_target": created["reused_existing_target"],
            "operator": _normalize_text(operator, max_length=128) or "admin",
        },
    )

    return {
        "message_id": int(message.id),
        "title": publish_title,
        "source_url": source_url,
        "link_target_id": created["published_link_target_id"],
        "published_at": message.timestamp,
        "reused_existing_target": created["reused_existing_target"],
    }
