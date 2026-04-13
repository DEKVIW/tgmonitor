from __future__ import annotations

import logging
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
    row = PanTransferExecutionLog(
        batch_id=int(item.batch_id),
        batch_item_id=int(item.id),
        level=normalized_level[:16],
        stage=normalized_stage[:32],
        message=normalized_message,
        payload=dict(payload or {}),
    )
    session.add(row)
    session.flush()

    log_method = _LEVEL_TO_METHOD.get(normalized_level, logger.info)
    log_method(
        "event=pan_transfer_execution batch_id=%s item_id=%s platform=%s stage=%s message=%s payload=%s",
        int(item.batch_id),
        int(item.id),
        str(item.platform or ""),
        normalized_stage,
        normalized_message,
        dict(payload or {}),
    )
    return row
