"""
Milestone 6 — Controlled Action Layer
======================================
Saves advisory "Purchase Suggestion" drafts and logs every interaction for
audit. NEVER executes a purchase, sends comms, or implies automation.

Collections
-----------
`procurement_suggestions`
    Advisory draft the user explicitly chose to save. Contains a snapshot
    of the recommendation at the moment of saving.

`procurement_suggestion_events`
    Minimal, structured event log. Every record:
      {user_id, restaurant_id, canonical_product_id, recommendation_type,
       event_type, timestamp, metadata}
    event_type ∈ {
      suggestion_opened, draft_viewed,
      acknowledgment_checked, action_confirmed, action_canceled,
    }
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import db

logger = logging.getLogger("restaurant_ai")

ALLOWED_EVENT_TYPES = {
    "suggestion_opened",
    "draft_viewed",
    "acknowledgment_checked",
    "action_confirmed",
    "action_canceled",
}


async def log_event(
    *,
    user: dict,
    canonical_product_id: str,
    recommendation_type: str,
    event_type: str,
    metadata: Optional[dict] = None,
) -> dict:
    """Append a single advisory-UI event to the audit log."""
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"invalid_event_type: {event_type}")
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": user["restaurant_id"],
        "user_id": user.get("id"),
        "user_name": user.get("name", ""),
        "canonical_product_id": canonical_product_id,
        "recommendation_type": recommendation_type,
        "event_type": event_type,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.procurement_suggestion_events.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def save_suggestion(
    *,
    user: dict,
    canonical_product_id: str,
    canonical_unit: str,
    canonical_name: str,
    current_vendor: str,
    recommendation_type: str,
    recommended_vendor: str,
    reference_price_per_unit: Optional[float],
    current_price_per_unit: Optional[float],
    decision_confidence: Optional[float],
    confidence_level: Optional[str],
    risk_level: Optional[str],
    reason_summary: str,
    evidence: list[str],
    uncertainty: list[str],
    acknowledgment_confirmed: bool,
    snapshot: Optional[dict] = None,
) -> dict:
    """Persist the user-saved advisory draft (gated by acknowledgment flag)."""
    if not acknowledgment_confirmed:
        raise PermissionError("acknowledgment_required")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": user["restaurant_id"],
        "user_id": user.get("id"),
        "user_name": user.get("name", ""),
        "canonical_product_id": canonical_product_id,
        "canonical_unit": canonical_unit,
        "canonical_name": canonical_name,
        "current_vendor": current_vendor,
        "recommendation_type": recommendation_type,
        "recommended_vendor": recommended_vendor,
        "reference_price_per_unit": reference_price_per_unit,
        "current_price_per_unit": current_price_per_unit,
        "decision_confidence": decision_confidence,
        "confidence_level": confidence_level,
        "risk_level": risk_level,
        "reason_summary": reason_summary,
        "evidence": evidence or [],
        "uncertainty": uncertainty or [],
        "acknowledgment_confirmed": True,
        "acknowledged_at": now,
        "status": "saved_for_review",   # fixed — this layer never executes
        "snapshot": snapshot or {},
        "created_at": now,
    }
    await db.procurement_suggestions.insert_one(doc)

    # Mirror the confirm event for completeness
    await log_event(
        user=user,
        canonical_product_id=canonical_product_id,
        recommendation_type=recommendation_type,
        event_type="action_confirmed",
        metadata={"suggestion_id": doc["id"]},
    )
    return {k: v for k, v in doc.items() if k != "_id"}


async def list_suggestions(restaurant_id: str, *, status: str = "") -> list[dict]:
    query: dict[str, Any] = {"restaurant_id": restaurant_id}
    if status:
        query["status"] = status
    cursor = db.procurement_suggestions.find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(500)


# Outcome tracking (feedback loop)
ALLOWED_OUTCOME_STATUSES = {"acted_on", "not_pursued"}


async def record_outcome(
    *,
    user: dict,
    suggestion_id: str,
    outcome_type: str,
    outcome_note: str = "",
) -> dict:
    """
    Apply a terminal outcome to a saved suggestion:
      acted_on    — user followed through on the recommendation
      not_pursued — user chose not to act (optional note)
    Idempotent: overwrites any prior outcome for the same suggestion.
    NEVER triggers purchasing or vendor actions.
    """
    if outcome_type not in ALLOWED_OUTCOME_STATUSES:
        raise ValueError(f"invalid_outcome_type: {outcome_type}")

    now = datetime.now(timezone.utc).isoformat()
    query = {"id": suggestion_id, "restaurant_id": user["restaurant_id"]}
    update = {
        "$set": {
            "status": outcome_type,
            "outcome_type": outcome_type,
            "outcome_note": (outcome_note or "").strip(),
            "outcome_at": now,
            "outcome_by_user_id": user.get("id"),
            "outcome_by_user_name": user.get("name", ""),
            "updated_at": now,
        }
    }
    result = await db.procurement_suggestions.update_one(query, update)
    if result.matched_count == 0:
        raise KeyError("suggestion_not_found")

    suggestion = await db.procurement_suggestions.find_one(query, {"_id": 0})

    # Log a tracking event so the audit log captures the outcome too
    await log_event(
        user=user,
        canonical_product_id=suggestion.get("canonical_product_id", ""),
        recommendation_type=suggestion.get("recommendation_type", ""),
        event_type="action_confirmed" if outcome_type == "acted_on" else "action_canceled",
        metadata={
            "suggestion_id": suggestion_id,
            "outcome_type": outcome_type,
            "outcome_note_present": bool(outcome_note),
        },
    )
    return suggestion


async def suggested_quantity_hint(
    *, restaurant_id: str, canonical_product_id: str, canonical_unit: str
) -> dict:
    """
    Purely advisory helper: inspect the last 3 good-quality price_history
    observations for this canonical product and return their quantities.
    NEVER pre-fills an input — consumer renders as helper text only.
    """
    cursor = db.price_history.find(
        {
            "restaurant_id": restaurant_id,
            "canonical_product_id": canonical_product_id,
            "canonical_unit": canonical_unit,
            "data_quality_flag": "good",
        },
        {"_id": 0, "quantity": 1, "vendor_name": 1, "invoice_date": 1, "observed_at": 1},
    ).sort("observed_at", -1)
    rows = await cursor.to_list(3)
    qtys: list[float] = []
    for r in rows:
        try:
            q = float(r.get("quantity") or 0)
        except (TypeError, ValueError):
            q = 0.0
        if q > 0:
            qtys.append(q)
    avg = round(sum(qtys) / len(qtys), 2) if qtys else None
    return {
        "lookback": len(qtys),
        "quantities": qtys,
        "average": avg,
        "canonical_unit": canonical_unit,
        "last_invoice_dates": [r.get("invoice_date") or r.get("observed_at") or "" for r in rows],
        "last_vendors": [r.get("vendor_name") or "" for r in rows],
        "helper_text": (
            f"Based on your last {len(qtys)} purchase(s): ~{avg} {canonical_unit}"
            if avg is not None else
            "No recent quantity data available for this product."
        ),
        "disclaimer": "Suggestion only — not a recommended order quantity.",
    }
