"""
Milestone 6 — Controlled Action Layer API
==========================================
Advisory endpoints only — no execution, no vendor communication.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from core.auth import get_user
from services.procurement_suggestions import (
    log_event, save_suggestion, list_suggestions, suggested_quantity_hint,
    record_outcome, ALLOWED_EVENT_TYPES, ALLOWED_OUTCOME_STATUSES,
)

router = APIRouter()


class EventBody(BaseModel):
    canonical_product_id: str
    recommendation_type: str
    event_type: str = Field(..., description="One of: " + ", ".join(sorted(ALLOWED_EVENT_TYPES)))
    metadata: Optional[dict] = None


class SaveSuggestionBody(BaseModel):
    canonical_product_id: str
    canonical_unit: str
    canonical_name: str = ""
    current_vendor: str = ""
    recommendation_type: str
    recommended_vendor: str = ""
    reference_price_per_unit: Optional[float] = None
    current_price_per_unit: Optional[float] = None
    decision_confidence: Optional[float] = None
    confidence_level: Optional[str] = None
    risk_level: Optional[str] = None
    reason_summary: str = ""
    evidence: list[str] = []
    uncertainty: list[str] = []
    acknowledgment_confirmed: bool
    snapshot: Optional[dict] = None


@router.post("/procurement/events")
async def post_event(body: EventBody, user=Depends(get_user)):
    try:
        ev = await log_event(
            user=user,
            canonical_product_id=body.canonical_product_id,
            recommendation_type=body.recommendation_type,
            event_type=body.event_type,
            metadata=body.metadata,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"event": ev}


@router.post("/procurement/suggestions")
async def post_suggestion(body: SaveSuggestionBody, user=Depends(get_user)):
    if not body.acknowledgment_confirmed:
        raise HTTPException(400, "acknowledgment_required")
    try:
        doc = await save_suggestion(
            user=user,
            canonical_product_id=body.canonical_product_id,
            canonical_unit=body.canonical_unit,
            canonical_name=body.canonical_name,
            current_vendor=body.current_vendor,
            recommendation_type=body.recommendation_type,
            recommended_vendor=body.recommended_vendor,
            reference_price_per_unit=body.reference_price_per_unit,
            current_price_per_unit=body.current_price_per_unit,
            decision_confidence=body.decision_confidence,
            confidence_level=body.confidence_level,
            risk_level=body.risk_level,
            reason_summary=body.reason_summary,
            evidence=body.evidence,
            uncertainty=body.uncertainty,
            acknowledgment_confirmed=body.acknowledgment_confirmed,
            snapshot=body.snapshot,
        )
    except PermissionError:
        raise HTTPException(400, "acknowledgment_required")
    return doc


@router.get("/procurement/suggestions")
async def get_suggestions(status: str = Query(default=""), user=Depends(get_user)):
    items = await list_suggestions(user["restaurant_id"], status=status)
    breakdown = {
        "saved_for_review": 0,
        "acted_on": 0,
        "not_pursued": 0,
    }
    # Count from the UNFILTERED list so counters stay stable across tabs
    all_items = await list_suggestions(user["restaurant_id"])
    for it in all_items:
        s = it.get("status") or "saved_for_review"
        if s in breakdown:
            breakdown[s] += 1
    return {"items": items, "total": len(items), "breakdown": breakdown}


class OutcomeBody(BaseModel):
    outcome_type: str = Field(..., description="One of: " + ", ".join(sorted(ALLOWED_OUTCOME_STATUSES)))
    outcome_note: Optional[str] = Field(default="", max_length=1000)


@router.patch("/procurement/suggestions/{suggestion_id}/outcome")
async def patch_outcome(suggestion_id: str, body: OutcomeBody, user=Depends(get_user)):
    try:
        doc = await record_outcome(
            user=user,
            suggestion_id=suggestion_id,
            outcome_type=body.outcome_type,
            outcome_note=body.outcome_note or "",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "suggestion_not_found")
    return doc


@router.get("/procurement/quantity-hint/{canonical_product_id}")
async def quantity_hint(
    canonical_product_id: str,
    canonical_unit: str = Query(...),
    user=Depends(get_user),
):
    return await suggested_quantity_hint(
        restaurant_id=user["restaurant_id"],
        canonical_product_id=canonical_product_id,
        canonical_unit=canonical_unit,
    )
