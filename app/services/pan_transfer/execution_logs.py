from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import PanTransferBatchItem, PanTransferExecutionLog


logger = logging.getLogger(__name__)

_LEVEL_TO_METHOD = {
    "debug": logger.debug,
    "info": logger.info,
    "warning": logger.warning,
    "error": logger.error,
}


def _serialize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        text = value.isoformat()
        return f"{text}Z" if value.tzinfo is None else text
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_json_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_log_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _serialize_json_value(payload or {})
    return normalized if isinstance(normalized, dict) else {"value": normalized}


def append_pan_transfer_execution_log(
    session: Session,
    *,
    item: PanTransferBatchItem,
    stage: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> PanTransferExecutionLog:
    normalized_level = str(level or "info").strip().lower() or "info"
    normalized_stage = str(stage or "general").strip().lower() or "general"
    normalized_message = str(message or "").strip()[:2000]
    normalized_payload = _normalize_log_payload(payload)
    row = PanTransferExecutionLog(
        batch_id=int(item.batch_id),
        batch_item_id=int(item.id),
        level=normalized_level[:16],
        stage=normalized_stage[:32],
        message=normalized_message,
        payload=normalized_payload,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except Exception as exc:
        if row in session:
            session.expunge(row)
        logger.warning(
            "failed to append pan transfer execution log batch_id=%s item_id=%s stage=%s message=%s payload=%s error=%s",
            int(item.batch_id),
            int(item.id),
            normalized_stage,
            normalized_message,
            normalized_payload,
            str(exc)[:1000],
        )

    log_method = _LEVEL_TO_METHOD.get(normalized_level, logger.info)
    log_method(
        "event=pan_transfer_execution batch_id=%s item_id=%s platform=%s stage=%s message=%s payload=%s",
        int(item.batch_id),
        int(item.id),
        str(item.platform or ""),
        normalized_stage,
        normalized_message,
        normalized_payload,
    )
    return row
