"""
Decision Audit Log (P1 — Learning Foundation)
==============================================
Structured, queryable dataset linking:
    recommendation → user interaction → final outcome

ONE base record per active recommendation. Subsequent events UPDATE the
same record. When a terminal outcome is recorded, the record is FINALIZED
and a fresh generation of the same recommendation opens a new record.

This is a DATA-COLLECTION layer only — NO ML, NO auto-tuning, NO
auto-adjustment of thresholds. It exists to power future evaluation
queries such as:
    "% of switch_vendor recommendations that were acted_on"
    "high-confidence recommendations that were not_pursued"

Collection
----------
procurement_decision_events
    event_id               uuid
    restaurant_id          str                    (tenant isolation)
    user_id                str  (first generator)
    canonical_product_id   str
    canonical_name         str
    canonical_unit         str
    recommendation_type    str  (switch_vendor | renegotiate | no_action | monitor_only)
    confidence_score       float [0..1]           (latest decision_confidence)
    confidence_level       str  (High | Medium | Low)
    risk_level             str  (low | medium | high)
    generated_at           ISO  (latest regeneration time)
    first_generated_at     ISO  (record creation time)
    generation_count       int  (how many times recomputed while still open)
    # Interaction
    suggestion_id          str | None             (set when user saves draft)
    suggestion_opened_at   ISO | None
    draft_viewed_at        ISO | None
    acknowledged_at        ISO | None
    # Outcome
    outcome_type           str | None   (acted_on | not_pursued)
    outcome_at             ISO | None
    outcome_note           str
    outcome_by_user_id     str | None
    # Lifecycle
    status                 str  (open | interacted | finalized)
    updated_at             ISO
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import db

logger = logging.getLogger("restaurant_ai")


AUDIT_STATUS_OPEN = "open"
AUDIT_STATUS_INTERACTED = "interacted"
AUDIT_STATUS_FINALIZED = "finalized"

_TERMINAL_OUTCOMES = {"acted_on", "not_pursued"}
_INTERACTION_EVENTS = {
    "suggestion_opened":      "suggestion_opened_at",
    "draft_viewed":           "draft_viewed_at",
    "acknowledgment_checked": "acknowledged_at",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────
# 1. Record generation (called from recommendations_for_restaurant)
# ──────────────────────────────────────────────────────────────────────
async def record_recommendation_generated(
    *,
    restaurant_id: str,
    user_id: Optional[str],
    decision: dict,
) -> dict:
    """
    Idempotent upsert — one OPEN record per
    (restaurant_id, canonical_product_id, recommendation_type).

    If an open record exists, refresh its confidence/risk/generated_at
    and bump generation_count. If not, insert a new record.
    Records with status=finalized are NOT touched — a new row is created
    so the historical outcome stays queryable.
    """
    cpid = decision.get("canonical_product_id")
    rtype = decision.get("recommendation_type")
    if not cpid or not rtype:
        return {}

    now = _utcnow()
    query = {
        "restaurant_id": restaurant_id,
        "canonical_product_id": cpid,
        "recommendation_type": rtype,
        "status": {"$in": [AUDIT_STATUS_OPEN, AUDIT_STATUS_INTERACTED]},
    }
    existing = await db.procurement_decision_events.find_one(query, {"_id": 0})
    if existing:
        await db.procurement_decision_events.update_one(
            {"event_id": existing["event_id"], "restaurant_id": restaurant_id},
            {"$set": {
                "confidence_score": decision.get("decision_confidence"),
                "confidence_level": decision.get("confidence_level"),
                "risk_level": decision.get("risk_level"),
                "canonical_name": decision.get("canonical_name") or existing.get("canonical_name", ""),
                "canonical_unit": decision.get("canonical_unit") or existing.get("canonical_unit", ""),
                "generated_at": now,
                "updated_at": now,
            },
             "$inc": {"generation_count": 1}},
        )
        return {**existing, "generated_at": now}

    doc = {
        "event_id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "canonical_product_id": cpid,
        "canonical_name": decision.get("canonical_name") or "",
        "canonical_unit": decision.get("canonical_unit") or "",
        "recommendation_type": rtype,
        "confidence_score": decision.get("decision_confidence"),
        "confidence_level": decision.get("confidence_level"),
        "risk_level": decision.get("risk_level"),
        "generated_at": now,
        "first_generated_at": now,
        "generation_count": 1,
        "suggestion_id": None,
        "suggestion_opened_at": None,
        "draft_viewed_at": None,
        "acknowledged_at": None,
        "outcome_type": None,
        "outcome_at": None,
        "outcome_note": "",
        "outcome_by_user_id": None,
        "status": AUDIT_STATUS_OPEN,
        "updated_at": now,
    }
    await db.procurement_decision_events.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


# ──────────────────────────────────────────────────────────────────────
# 2. Record interactions (suggestion_opened / draft_viewed / acknowledged)
# ──────────────────────────────────────────────────────────────────────
async def record_interaction(
    *,
    restaurant_id: str,
    canonical_product_id: str,
    recommendation_type: str,
    event_type: str,
    suggestion_id: Optional[str] = None,
) -> Optional[dict]:
    """Stamp an interaction timestamp on the OPEN audit record."""
    field = _INTERACTION_EVENTS.get(event_type)
    if not field:
        return None  # not an interaction event we track on the audit record

    now = _utcnow()
    query = {
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
        "recommendation_type": recommendation_type,
        "status": {"$in": [AUDIT_STATUS_OPEN, AUDIT_STATUS_INTERACTED]},
    }
    # Only set the timestamp on first occurrence (don't overwrite earlier interaction).
    set_fields: dict[str, Any] = {
        "status": AUDIT_STATUS_INTERACTED,
        "updated_at": now,
    }
    if suggestion_id:
        set_fields["suggestion_id"] = suggestion_id

    # Use $setOnInsert-style guard on the timestamp field itself:
    # only set it if currently null.
    first_stamp_query = {**query, field: None}
    await db.procurement_decision_events.update_one(
        first_stamp_query, {"$set": {**set_fields, field: now}}
    )
    # If the timestamp was already set, still make sure status/suggestion_id/updated_at are refreshed
    await db.procurement_decision_events.update_one(query, {"$set": set_fields})

    return await db.procurement_decision_events.find_one(query, {"_id": 0})


# ──────────────────────────────────────────────────────────────────────
# 3. Finalize outcome (called from record_outcome in suggestions service)
# ──────────────────────────────────────────────────────────────────────
async def finalize_outcome(
    *,
    restaurant_id: str,
    canonical_product_id: str,
    recommendation_type: str,
    suggestion_id: Optional[str],
    outcome_type: str,
    outcome_note: str = "",
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Finalize the OPEN audit record with a terminal outcome.
    Idempotent: if already finalized with the same outcome, returns it; if
    finalized with a different outcome, overwrites (last write wins — the
    inbox UI allows toggling).
    """
    if outcome_type not in _TERMINAL_OUTCOMES:
        raise ValueError(f"invalid_outcome_type: {outcome_type}")

    now = _utcnow()
    # Preferred match: by suggestion_id (strongest link).
    base: dict[str, Any] = {"restaurant_id": restaurant_id}
    if suggestion_id:
        match = {**base, "suggestion_id": suggestion_id}
    else:
        match = {
            **base,
            "canonical_product_id": canonical_product_id,
            "recommendation_type": recommendation_type,
            "status": {"$in": [AUDIT_STATUS_OPEN, AUDIT_STATUS_INTERACTED]},
        }

    update = {"$set": {
        "status": AUDIT_STATUS_FINALIZED,
        "outcome_type": outcome_type,
        "outcome_at": now,
        "outcome_note": (outcome_note or "").strip(),
        "outcome_by_user_id": user_id,
        "updated_at": now,
    }}
    res = await db.procurement_decision_events.update_one(match, update)
    if res.matched_count == 0:
        # No audit record yet (edge case: suggestion saved before hook landed).
        # Create a minimal finalized record so the dataset is complete.
        doc = {
            "event_id": str(uuid.uuid4()),
            "restaurant_id": restaurant_id,
            "user_id": user_id,
            "canonical_product_id": canonical_product_id,
            "canonical_name": "",
            "canonical_unit": "",
            "recommendation_type": recommendation_type,
            "confidence_score": None,
            "confidence_level": None,
            "risk_level": None,
            "generated_at": now,
            "first_generated_at": now,
            "generation_count": 0,
            "suggestion_id": suggestion_id,
            "suggestion_opened_at": None,
            "draft_viewed_at": None,
            "acknowledged_at": None,
            "outcome_type": outcome_type,
            "outcome_at": now,
            "outcome_note": (outcome_note or "").strip(),
            "outcome_by_user_id": user_id,
            "status": AUDIT_STATUS_FINALIZED,
            "updated_at": now,
        }
        await db.procurement_decision_events.insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    return await db.procurement_decision_events.find_one(
        {"restaurant_id": restaurant_id,
         **({"suggestion_id": suggestion_id} if suggestion_id else
            {"canonical_product_id": canonical_product_id,
             "recommendation_type": recommendation_type,
             "status": AUDIT_STATUS_FINALIZED})},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )


# ──────────────────────────────────────────────────────────────────────
# 4. Link a saved suggestion to its audit record
# ──────────────────────────────────────────────────────────────────────
async def link_suggestion(
    *,
    restaurant_id: str,
    canonical_product_id: str,
    recommendation_type: str,
    suggestion_id: str,
) -> None:
    """Attach the saved-suggestion id to the open audit record (if any)."""
    now = _utcnow()
    query = {
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
        "recommendation_type": recommendation_type,
        "status": {"$in": [AUDIT_STATUS_OPEN, AUDIT_STATUS_INTERACTED]},
    }
    await db.procurement_decision_events.update_one(
        query,
        {"$set": {"suggestion_id": suggestion_id, "updated_at": now}},
    )


# ──────────────────────────────────────────────────────────────────────
# 5. Read APIs — list + aggregate stats (tenant-scoped)
# ──────────────────────────────────────────────────────────────────────
async def list_audit_events(
    *,
    restaurant_id: str,
    status: str = "",
    recommendation_type: str = "",
    outcome_type: str = "",
    confidence_level: str = "",
    limit: int = 500,
) -> list[dict]:
    query: dict[str, Any] = {"restaurant_id": restaurant_id}
    if status:
        query["status"] = status
    if recommendation_type:
        query["recommendation_type"] = recommendation_type
    if outcome_type:
        query["outcome_type"] = outcome_type
    if confidence_level:
        query["confidence_level"] = confidence_level
    cursor = db.procurement_decision_events.find(query, {"_id": 0}).sort("generated_at", -1)
    return await cursor.to_list(max(1, min(limit, 2000)))


async def aggregate_audit_stats(*, restaurant_id: str) -> dict:
    """
    Returns a flat set of descriptive metrics suitable for a learning
    dashboard. Performs a single scan per tenant — zero impact on
    existing recommendation/suggestion endpoints.

    Shape:
        {
          total, open, interacted, finalized,
          by_recommendation_type: {
             switch_vendor: {generated, acted_on, not_pursued,
                             acted_on_rate, not_pursued_rate},
             renegotiate:   {...},
             no_action:     {...},
             monitor_only:  {...},
          },
          high_confidence_not_pursued: [ {event_id, canonical_product_id,
             canonical_name, recommendation_type, confidence_score,
             outcome_at, outcome_note}, ... ],
          sample_queries: {
             "switch_vendor_acted_on_rate": float | null,
             "high_confidence_not_pursued_count": int,
          }
        }
    """
    items = await list_audit_events(restaurant_id=restaurant_id, limit=2000)

    buckets: dict[str, dict[str, int]] = {
        "switch_vendor": {"generated": 0, "acted_on": 0, "not_pursued": 0},
        "renegotiate":   {"generated": 0, "acted_on": 0, "not_pursued": 0},
        "no_action":     {"generated": 0, "acted_on": 0, "not_pursued": 0},
        "monitor_only":  {"generated": 0, "acted_on": 0, "not_pursued": 0},
    }
    status_counts = {"open": 0, "interacted": 0, "finalized": 0}
    hi_not_pursued: list[dict] = []

    for it in items:
        rt = it.get("recommendation_type")
        if rt in buckets:
            buckets[rt]["generated"] += 1
            ot = it.get("outcome_type")
            if ot == "acted_on":
                buckets[rt]["acted_on"] += 1
            elif ot == "not_pursued":
                buckets[rt]["not_pursued"] += 1
        s = it.get("status")
        if s in status_counts:
            status_counts[s] += 1
        if (it.get("confidence_level") == "High" and it.get("outcome_type") == "not_pursued"):
            hi_not_pursued.append({
                "event_id": it.get("event_id"),
                "canonical_product_id": it.get("canonical_product_id"),
                "canonical_name": it.get("canonical_name"),
                "recommendation_type": it.get("recommendation_type"),
                "confidence_score": it.get("confidence_score"),
                "risk_level": it.get("risk_level"),
                "outcome_at": it.get("outcome_at"),
                "outcome_note": it.get("outcome_note") or "",
            })

    def _rate(num: int, den: int) -> Optional[float]:
        return round(num / den, 4) if den > 0 else None

    by_type = {}
    for rt, c in buckets.items():
        by_type[rt] = {
            **c,
            "acted_on_rate":    _rate(c["acted_on"], c["generated"]),
            "not_pursued_rate": _rate(c["not_pursued"], c["generated"]),
        }

    sv = by_type["switch_vendor"]
    return {
        "total": len(items),
        "open": status_counts["open"],
        "interacted": status_counts["interacted"],
        "finalized": status_counts["finalized"],
        "by_recommendation_type": by_type,
        "high_confidence_not_pursued": hi_not_pursued,
        "sample_queries": {
            # "% of switch_vendor recommendations that were acted_on"
            "switch_vendor_acted_on_rate": sv["acted_on_rate"],
            # "high-confidence recommendations that were not_pursued"
            "high_confidence_not_pursued_count": len(hi_not_pursued),
        },
    }
