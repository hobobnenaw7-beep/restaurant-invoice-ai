"""
Decision Audit Log — READ-ONLY API
===================================
Queryable dataset for evaluating decision quality.
All endpoints are tenant-scoped via the authenticated user's restaurant_id.
This module never executes purchases; it only exposes historical data.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import get_user
from services.procurement_audit import (
    list_audit_events,
    aggregate_audit_stats,
    AUDIT_STATUS_OPEN,
    AUDIT_STATUS_INTERACTED,
    AUDIT_STATUS_FINALIZED,
)

router = APIRouter()

_ALLOWED_STATUSES = {AUDIT_STATUS_OPEN, AUDIT_STATUS_INTERACTED, AUDIT_STATUS_FINALIZED, ""}
_ALLOWED_RTYPES = {"switch_vendor", "renegotiate", "no_action", "monitor_only", ""}
_ALLOWED_OUTCOMES = {"acted_on", "not_pursued", ""}
_ALLOWED_CONF_LEVELS = {"High", "Medium", "Low", ""}


@router.get("/procurement/audit/events")
async def get_audit_events(
    status: str = Query(default=""),
    recommendation_type: str = Query(default=""),
    outcome_type: str = Query(default=""),
    confidence_level: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=2000),
    user=Depends(get_user),
):
    if status not in _ALLOWED_STATUSES:
        raise HTTPException(400, f"invalid_status: {status}")
    if recommendation_type not in _ALLOWED_RTYPES:
        raise HTTPException(400, f"invalid_recommendation_type: {recommendation_type}")
    if outcome_type not in _ALLOWED_OUTCOMES:
        raise HTTPException(400, f"invalid_outcome_type: {outcome_type}")
    if confidence_level not in _ALLOWED_CONF_LEVELS:
        raise HTTPException(400, f"invalid_confidence_level: {confidence_level}")

    items = await list_audit_events(
        restaurant_id=user["restaurant_id"],
        status=status,
        recommendation_type=recommendation_type,
        outcome_type=outcome_type,
        confidence_level=confidence_level,
        limit=limit,
    )
    return {"items": items, "total": len(items)}


@router.get("/procurement/audit/stats")
async def get_audit_stats(user=Depends(get_user)):
    return await aggregate_audit_stats(restaurant_id=user["restaurant_id"])
