"""
Orders (Phase 4 — Navigation Restructure)
==========================================
LIGHTWEIGHT, ITEM-DRIVEN orders. Strict constraints:
  - NO free-text product creation inside an order.
  - NO duplicate product definitions — every line item MUST reference an
    existing canonical_items.id.
  - NO connection to Procurement recommendations (no auto-ordering,
    no auto-fill execution).

Collection `orders`:
  {id, restaurant_id, created_by_user_id, created_by_user_name,
   order_date, vendor_name, note, status,
   items: [{item_id, item_name, category, unit, quantity,
            last_known_price, last_known_vendor}],
   total_estimated, created_at, updated_at}

Status: draft | submitted (submitted = user marked as done; there is NO
actual external purchase — terminology kept conservative on purpose).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_user
from core.database import db

router = APIRouter()

ALLOWED_STATUSES = {"draft", "submitted"}


class OrderLineItemIn(BaseModel):
    item_id: str = Field(..., description="Required — must reference canonical_items.id")
    quantity: float = Field(..., ge=0)
    unit: Optional[str] = ""
    last_known_price: Optional[float] = None
    last_known_vendor: Optional[str] = ""


class CreateOrderBody(BaseModel):
    order_date: Optional[str] = ""
    vendor_name: Optional[str] = ""
    note: Optional[str] = Field(default="", max_length=1000)
    status: str = "draft"
    items: list[OrderLineItemIn] = []


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _enrich_items(restaurant_id: str, items: list[OrderLineItemIn]) -> list[dict]:
    """
    Resolve every item_id against canonical_items (tenant-scoped) so the
    line item is stored with name / category / unit. Missing items raise 400.
    """
    ids = [i.item_id for i in items]
    if not ids:
        return []
    cursor = db.canonical_items.find(
        {"id": {"$in": ids}, "restaurant_id": restaurant_id}, {"_id": 0}
    )
    found = {c["id"]: c async for c in cursor}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f"unknown_item_ids: {missing}")

    enriched = []
    for li in items:
        c = found[li.item_id]
        enriched.append({
            "item_id": li.item_id,
            "item_name": c.get("name", ""),
            "category": c.get("category", ""),
            "unit": li.unit or "",
            "quantity": float(li.quantity or 0),
            "last_known_price": li.last_known_price,
            "last_known_vendor": li.last_known_vendor or "",
        })
    return enriched


def _estimated_total(items: list[dict]) -> float:
    t = 0.0
    for it in items:
        p = it.get("last_known_price")
        q = it.get("quantity") or 0
        if p:
            t += float(p) * float(q)
    return round(t, 2)


@router.get("/orders")
async def list_orders(user=Depends(get_user)):
    rid = user["restaurant_id"]
    cursor = db.orders.find({"restaurant_id": rid}, {"_id": 0}).sort("created_at", -1)
    rows = await cursor.to_list(500)
    return {"items": rows, "total": len(rows)}


@router.post("/orders")
async def create_order(body: CreateOrderBody, user=Depends(get_user)):
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(400, f"invalid_status: {body.status}")
    try:
        items = await _enrich_items(user["restaurant_id"], body.items)
    except ValueError as e:
        raise HTTPException(400, str(e))

    now = _utcnow()
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": user["restaurant_id"],
        "created_by_user_id": user.get("id"),
        "created_by_user_name": user.get("name", ""),
        "order_date": (body.order_date or "").strip(),
        "vendor_name": (body.vendor_name or "").strip(),
        "note": (body.note or "").strip(),
        "status": body.status,
        "items": items,
        "total_estimated": _estimated_total(items),
        "created_at": now,
        "updated_at": now,
    }
    await db.orders.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str, user=Depends(get_user)):
    res = await db.orders.delete_one({"id": order_id, "restaurant_id": user["restaurant_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "order_not_found")
    return {"deleted": True}
