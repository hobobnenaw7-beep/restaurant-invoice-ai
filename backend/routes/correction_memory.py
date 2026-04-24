import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.database import db
from core.auth import get_user

router = APIRouter()


# ── Traceability: enrich corrections with their canonical destination ──

def _status_from_canonical(doc: dict) -> str:
    """Translate canonical_items flags into a user-facing status string."""
    if not doc:
        return "unlinked"
    if doc.get("is_merged"):
        return "merged"
    if doc.get("is_suggested") and doc.get("is_archived"):
        return "dismissed"
    if doc.get("is_archived"):
        return "archived"
    if doc.get("is_suggested"):
        return "suggested"
    return "approved"


async def _enrich_corrections_with_destination(rid: str, corrections: list) -> list:
    """
    For each correction, attach a `canonical_destination` dict describing
    where the user's edit ended up in the catalog today:

        {
          "status": "approved"|"suggested"|"merged"|"dismissed"|"archived"|"unlinked",
          "canonical_item_id": str | None,
          "canonical_name": str | None,
          "merged_from_name": str | None,   # set when a suggestion was merged
          "merged_from_item_id": str | None
        }

    Traceability rules:
      1. The raw alias `item_aliases.alias == original_raw_name` tells us the
         canonical item id today. If a merge happened, the alias was already
         transferred → this points to the merge target.
      2. To surface "Merged into X", we look for any `canonical_items` with
         `is_merged=True, merged_into_item_id=<current_id>` whose name matches
         the correction's `corrected_name` (case-insensitive). If present,
         status becomes "merged" with merged_from_name set.
      3. If no alias exists, status is "unlinked" (rare edge case).
    """
    if not corrections:
        return corrections

    raw_names = list({
        (c.get("original_raw_name") or "").strip()
        for c in corrections if c.get("original_raw_name")
    })
    if not raw_names:
        for c in corrections:
            c["canonical_destination"] = {
                "status": "unlinked", "canonical_item_id": None,
                "canonical_name": None, "merged_from_name": None,
                "merged_from_item_id": None,
            }
        return corrections

    # Batch fetch aliases for all raw_names in one query (case-insensitive via regex list).
    # Use a broad exact-value $in first (most aliases preserve the raw_name verbatim).
    aliases = await db.item_aliases.find(
        {"restaurant_id": rid, "alias": {"$in": raw_names}},
        {"_id": 0, "alias": 1, "canonical_item_id": 1},
    ).to_list(2000)
    alias_map = {a["alias"]: a["canonical_item_id"] for a in aliases if a.get("canonical_item_id")}

    canonical_ids = list({cid for cid in alias_map.values() if cid})
    canon_docs = {}
    if canonical_ids:
        async for d in db.canonical_items.find(
            {"id": {"$in": canonical_ids}, "restaurant_id": rid},
            {"_id": 0},
        ):
            canon_docs[d["id"]] = d

    # For each correction, also detect whether a sibling suggested canonical
    # (same corrected_name) was merged INTO the current canonical. That tells
    # us the correction went through a merge step.
    corrected_names = list({
        (c.get("corrected_name") or "").strip()
        for c in corrections if c.get("corrected_name")
    })
    merged_sources = []
    if corrected_names and canonical_ids:
        # Build an $or of regex exact (case-insensitive) for the name.
        name_clauses = [
            {"name": {"$regex": f"^{re.escape(n)}$", "$options": "i"}}
            for n in corrected_names if n
        ]
        if name_clauses:
            cursor = db.canonical_items.find(
                {
                    "restaurant_id": rid,
                    "is_merged": True,
                    "merged_into_item_id": {"$in": canonical_ids},
                    "$or": name_clauses,
                },
                {"_id": 0, "id": 1, "name": 1, "merged_into_item_id": 1},
            )
            merged_sources = await cursor.to_list(2000)

    # Index merged-source docs by (lowercased_name, target_id) for lookup.
    merge_index = {}
    for m in merged_sources:
        key = ((m.get("name") or "").strip().lower(), m.get("merged_into_item_id"))
        # If multiple, keep the first — it's still a valid trace.
        merge_index.setdefault(key, m)

    for c in corrections:
        raw = (c.get("original_raw_name") or "").strip()
        canonical_id = alias_map.get(raw)
        canon = canon_docs.get(canonical_id) if canonical_id else None

        dest = {
            "status": _status_from_canonical(canon),
            "canonical_item_id": canonical_id if canon else None,
            "canonical_name": (canon.get("name") if canon else None),
            "merged_from_name": None,
            "merged_from_item_id": None,
        }

        # Merge detection: if the current canonical is approved but a
        # sibling was merged into it with the corrected_name, surface "merged".
        if canon and not canon.get("is_merged"):
            corrected = (c.get("corrected_name") or "").strip().lower()
            m = merge_index.get((corrected, canon["id"]))
            if m:
                dest["status"] = "merged"
                dest["merged_from_name"] = m.get("name")
                dest["merged_from_item_id"] = m.get("id")

        c["canonical_destination"] = dest

    return corrections


@router.get("/correction-memory")
async def list_corrections(user=Depends(get_user)):
    """List all correction memory entries for this restaurant."""
    rows = await db.correction_memory.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).sort("updated_at", -1).to_list(500)
    return await _enrich_corrections_with_destination(user["restaurant_id"], rows)


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
    rows = await db.correction_memory.find(
        {"restaurant_id": user["restaurant_id"], "supplier_id": supplier_id},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(500)
    return await _enrich_corrections_with_destination(user["restaurant_id"], rows)


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
    enriched = await _enrich_corrections_with_destination(user["restaurant_id"], [doc] if doc else [])
    return enriched[0] if enriched else doc
