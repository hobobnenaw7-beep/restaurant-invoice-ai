import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.database import db
from core.auth import get_user

router = APIRouter()


@router.get("/correction-memory")
async def list_corrections(user=Depends(get_user)):
    """List all correction memory entries for this restaurant."""
    return await db.correction_memory.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).sort("updated_at", -1).to_list(500)


@router.get("/correction-hints")
async def get_correction_hints(supplier_name: str = "", user=Depends(get_user)):
    """
    Return stored corrections for a specific supplier.
    Used by the edit dialog to surface 'Previously corrected' hints.
    No intelligence — raw records only, keyed by normalized_key.
    """
    rid = user["restaurant_id"]
    name = supplier_name.strip()
    if not name:
        return []

    sup = await db.suppliers.find_one(
        {"restaurant_id": rid, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if not sup:
        return []

    corrections = await db.correction_memory.find(
        {"restaurant_id": rid, "supplier_id": sup["id"], "enabled": {"$ne": False}},
        {"_id": 0},
    ).to_list(500)

    # Group by normalized_key — if multiple records exist for the same key,
    # that's ambiguous, so exclude those keys entirely (safety rule)
    by_key = {}
    for c in corrections:
        key = c.get("normalized_key", "")
        if not key:
            continue
        if key in by_key:
            by_key[key] = None  # Mark as ambiguous
        else:
            by_key[key] = c

    # Return only unambiguous corrections
    return [v for v in by_key.values() if v is not None]


# ── Correction Memory Management ──


@router.get("/corrections/vendors")
async def list_vendors_with_corrections(user=Depends(get_user)):
    """List vendors that have stored corrections, with counts."""
    rid = user["restaurant_id"]

    pipeline = [
        {"$match": {"restaurant_id": rid}},
        {"$group": {
            "_id": "$supplier_id",
            "count": {"$sum": 1},
            "enabled_count": {"$sum": {"$cond": [{"$ne": ["$enabled", False]}, 1, 0]}},
            "total_usage": {"$sum": {"$ifNull": ["$usage_count", 0]}},
            "last_updated": {"$max": "$updated_at"},
        }},
        {"$sort": {"last_updated": -1}},
    ]
    groups = await db.correction_memory.aggregate(pipeline).to_list(200)

    # Fetch supplier names
    supplier_ids = [g["_id"] for g in groups if g["_id"]]
    suppliers = {}
    if supplier_ids:
        async for s in db.suppliers.find(
            {"restaurant_id": rid, "id": {"$in": supplier_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            suppliers[s["id"]] = s["name"]

    return [
        {
            "supplier_id": g["_id"],
            "supplier_name": suppliers.get(g["_id"], "Unknown Vendor"),
            "correction_count": g["count"],
            "enabled_count": g["enabled_count"],
            "total_usage": g["total_usage"],
            "last_updated": g["last_updated"],
        }
        for g in groups
        if g["_id"]
    ]


@router.get("/corrections/by-vendor/{supplier_id}")
async def get_corrections_by_vendor(supplier_id: str, user=Depends(get_user)):
    """Get all corrections for a specific vendor."""
    return await db.correction_memory.find(
        {"restaurant_id": user["restaurant_id"], "supplier_id": supplier_id},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(500)


@router.delete("/corrections/{correction_id}")
async def delete_correction(correction_id: str, user=Depends(get_user)):
    """Delete a correction record."""
    result = await db.correction_memory.delete_one(
        {"id": correction_id, "restaurant_id": user["restaurant_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Correction not found")
    return {"status": "deleted"}


class CorrectionToggle(BaseModel):
    enabled: bool


@router.patch("/corrections/{correction_id}/toggle")
async def toggle_correction(correction_id: str, body: CorrectionToggle, user=Depends(get_user)):
    """Enable or disable a correction."""
    result = await db.correction_memory.update_one(
        {"id": correction_id, "restaurant_id": user["restaurant_id"]},
        {"$set": {"enabled": body.enabled}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Correction not found")
    return {"status": "updated", "enabled": body.enabled}


class CorrectionEdit(BaseModel):
    corrected_name: Optional[str] = None
    corrected_specs: Optional[dict] = None


@router.patch("/corrections/{correction_id}")
async def edit_correction(correction_id: str, body: CorrectionEdit, user=Depends(get_user)):
    """Edit a correction's values."""
    updates = {}
    if body.corrected_name is not None:
        updates["corrected_name"] = body.corrected_name
    if body.corrected_specs is not None:
        updates["corrected_specs"] = body.corrected_specs
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.correction_memory.update_one(
        {"id": correction_id, "restaurant_id": user["restaurant_id"]},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Correction not found")

    doc = await db.correction_memory.find_one(
        {"id": correction_id}, {"_id": 0}
    )
    return doc
