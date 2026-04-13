from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import (
    LinkTarget,
    Message,
    PanTransferBatchItem,
    PanTransferPublishRecord,
    ensure_runtime_storage_tables,
)
from app.services.resource_ops import ensure_message_link_refs_for_messages
from app.services.resource_ops.catalog import flatten_message_links

from .execution_logs import append_pan_transfer_execution_log


_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _current_local_message_time() -> datetime:
    return datetime.now(_SHANGHAI_TZ).replace(tzinfo=None)


def _normalize_publish_tags(values: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        tag = str(raw_value or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag[:64])
    return normalized


def _find_existing_target_for_url(session: Session, *, url: str) -> LinkTarget | None:
    flattened = flatten_message_links({"url": url})
    if not flattened:
        return None
    item = flattened[0]
    return (
        session.query(LinkTarget)
        .filter(
            LinkTarget.platform == item.platform,
            LinkTarget.normalized_url_hash == item.normalized_url_hash,
        )
        .first()
    )


def _build_publish_links_payload(*, platform: str, source_url: str, title: str) -> dict[str, Any]:
    provider_label = str(platform or "").strip() or "网盘链接"
    return {
        provider_label: [
            {
                "url": source_url,
                "label": title,
            }
        ]
    }


def _resolve_publish_source_url(session: Session, *, item: PanTransferBatchItem) -> str:
    if item.new_link_target_id is not None:
        target = session.get(LinkTarget, int(item.new_link_target_id))
        if target is not None and str(target.original_url or "").strip():
            return str(target.original_url or "").strip()
    if str(item.new_share_url or "").strip():
        return str(item.new_share_url or "").strip()
    if str(item.original_url or "").strip():
        return str(item.original_url or "").strip()
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


def _serialize_publish_record(row: PanTransferPublishRecord) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "source_type": str(row.source_type or "manual"),
        "source_batch_id": int(row.source_batch_id) if row.source_batch_id is not None else None,
        "source_batch_item_id": int(row.source_batch_item_id) if row.source_batch_item_id is not None else None,
        "source_link_target_id": int(row.source_link_target_id) if row.source_link_target_id is not None else None,
        "source_new_link_target_id": int(row.source_new_link_target_id) if row.source_new_link_target_id is not None else None,
        "platform": str(row.platform or ""),
        "source_url": str(row.source_url or ""),
        "published_message_id": int(row.published_message_id) if row.published_message_id is not None else None,
        "published_title": str(row.published_title or ""),
        "published_description": str(row.published_description or "") or None,
        "published_tags": [str(tag).strip() for tag in list(row.published_tags or []) if str(tag).strip()],
        "operator": str(row.operator or "") or None,
        "extra_json": dict(row.extra_json or {}),
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
    publish_title = str(title or "").strip()
    if not publish_title:
        raise ValueError("title cannot be empty")

    publish_platform = str(platform or "").strip()
    publish_source_url = str(source_url or "").strip()
    if not publish_source_url:
        raise ValueError("source_url cannot be empty")

    publish_description = str(description or "").strip() or None
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
        bot=str(operator or "admin")[:255],
        netdisk_types=[publish_platform] if publish_platform else [],
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
        source_type=str(source_type or "manual")[:32] or "manual",
        source_batch_id=source_batch_id,
        source_batch_item_id=source_batch_item_id,
        source_link_target_id=source_link_target_id,
        source_new_link_target_id=source_new_link_target_id,
        platform=str(platform or "")[:64],
        source_url=str(source_url or ""),
        published_message_id=message_id,
        published_title=str(title or "")[:255],
        published_description=str(description or "")[:2000] or None,
        published_tags=_normalize_publish_tags(tags),
        operator=str(operator or "")[:128] or None,
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
        "items": [_serialize_publish_record(row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
    }


def publish_manual_pan_transfer_message(
    session: Session,
    *,
    payload: dict[str, Any],
    operator: str | None,
) -> dict[str, Any]:
    publish_platform = str(payload.get("platform") or "").strip()
    publish_source_url = str(payload.get("source_url") or "").strip()
    publish_title = str(payload.get("title") or "").strip()
    publish_description = str(payload.get("description") or "").strip() or None
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
        platform=publish_platform,
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

    publish_title = str(payload.get("title") or "").strip()
    if not publish_title:
        raise ValueError("title cannot be empty")

    publish_description = str(payload.get("description") or "").strip() or None
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
        "operator": str(operator or "admin")[:128],
        "published_at": created["published_at"].isoformat(),
    }
    _append_publish_history(item, entry=publish_entry)
    session.add(item)
    session.flush()

    _create_publish_record(
        session,
        source_type="batch_item",
        platform=str(item.platform or ""),
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
            "current_share_url": str(item.new_share_url or "") or None,
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
            "operator": str(operator or "admin")[:128],
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
