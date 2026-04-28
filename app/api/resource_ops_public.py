from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies_runtime_v2 import get_db, get_optional_current_user
from app.schemas.resource_ops_models import ResourceOpsTrackClickRequest, ResourceOpsTrackClickResponse
from app.services.resource_ops import get_redirect_target_url, record_click_event


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resource-ops", tags=["resource-ops"])


@router.post("/clicks/track", response_model=ResourceOpsTrackClickResponse, summary="Track link click")
async def track_resource_click(
    payload: ResourceOpsTrackClickRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> ResourceOpsTrackClickResponse:
    try:
        result = record_click_event(
            db,
            link_ref_id=payload.link_ref_id,
            request=request,
            current_user=current_user,
            event_token=payload.event_token,
            session_key=payload.session_key,
            source_page=payload.source_page,
            search_query=payload.search_query,
            redirect_confirmed=False,
        )
        db.commit()
        return ResourceOpsTrackClickResponse(**result)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to track resource click")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track click: {exc}",
        ) from exc


@router.get("/go/{link_ref_id}", summary="Redirect tracked link")
async def redirect_tracked_link(
    link_ref_id: int,
    request: Request,
    et: Optional[str] = Query(default=None),
    sk: Optional[str] = Query(default=None),
    sp: Optional[str] = Query(default=None),
    sq: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
):
    try:
        target_url = get_redirect_target_url(db, link_ref_id=link_ref_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        record_click_event(
            db,
            link_ref_id=link_ref_id,
            request=request,
            current_user=current_user,
            event_token=et,
            session_key=sk,
            source_page=sp,
            search_query=sq,
            redirect_confirmed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist redirect click for link_ref=%s", link_ref_id)

    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
