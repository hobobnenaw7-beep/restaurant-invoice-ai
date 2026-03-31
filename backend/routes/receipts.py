from fastapi import APIRouter, HTTPException, Depends
import uuid, re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from core.database import db
from core.auth import get_user
from core.models import ReceiptLearnRequest

router = APIRouter()


@router.post("/receipts/learn")
async def learn_from_receipt(req: ReceiptLearnRequest, user=Depends(get_user)):
    """Learn vendor patterns from user-corrected receipt data."""
    rid = user["restaurant_id"]
    vendor_name = req.vendor_name.strip()
    if not vendor_name:
        raise HTTPException(400, "vendor_name is required")

    vendor_id = req.vendor_id or ""
    if not vendor_id:
        sup = await db.suppliers.find_one(
            {"restaurant_id": rid, "name": {"$regex": f"^{re.escape(vendor_name)}$", "$options": "i"}},
            {"_id": 0, "id": 1}
        )
        if sup:
            vendor_id = sup["id"]

    item_names = [it.get("raw_name", "") or it.get("item_name", "") for it in req.corrected_items if it.get("raw_name") or it.get("item_name")]
    has_tax = (req.corrected_total or 0) > sum(float(it.get("total", 0) or 0) for it in req.corrected_items) + 0.01

    new_hints = req.hints or {}
    if item_names:
        new_hints["typical_items"] = item_names[:15]
    if has_tax:
        new_hints["has_tax"] = True
    new_hints["item_count_typical"] = len(req.corrected_items) if req.corrected_items else None

    existing = await db.vendor_patterns.find_one(
        {"restaurant_id": rid, "vendor_name_lower": vendor_name.lower()},
        {"_id": 0}
    )

    if existing:
        old_items = existing.get("hints", {}).get("typical_items", [])
        merged_items = list(dict.fromkeys(item_names + old_items))[:30]
        new_hints["typical_items"] = merged_items
        new_hints["receipt_count"] = existing.get("hints", {}).get("receipt_count", 0) + 1
        for k, v in existing.get("hints", {}).items():
            if k not in new_hints:
                new_hints[k] = v

        await db.vendor_patterns.update_one(
            {"restaurant_id": rid, "vendor_name_lower": vendor_name.lower()},
            {"$set": {
                "vendor_id": vendor_id or existing.get("vendor_id", ""),
                "vendor_name": vendor_name,
                "hints": new_hints,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
    else:
        new_hints["receipt_count"] = 1
        await db.vendor_patterns.insert_one({
            "id": str(uuid.uuid4()),
            "restaurant_id": rid,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "vendor_name_lower": vendor_name.lower(),
            "hints": new_hints,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    if req.receipt_id:
        await db.uploaded_receipts.update_one(
            {"id": req.receipt_id, "restaurant_id": rid},
            {"$set": {"vendor_id": vendor_id, "learned": True}}
        )

    return {"status": "ok", "vendor_name": vendor_name, "parsing_method": "vendor" if existing else "new_pattern"}


@router.get("/vendor-patterns")
async def list_vendor_patterns(user=Depends(get_user)):
    """List all vendor patterns for this restaurant."""
    rid = user["restaurant_id"]
    patterns = await db.vendor_patterns.find(
        {"restaurant_id": rid}, {"_id": 0}
    ).sort("vendor_name", 1).to_list(200)
    return patterns


@router.get("/vendor-patterns/{vendor_id}")
async def get_vendor_pattern(vendor_id: str, user=Depends(get_user)):
    """Get a specific vendor pattern."""
    rid = user["restaurant_id"]
    pattern = await db.vendor_patterns.find_one(
        {"restaurant_id": rid, "$or": [{"vendor_id": vendor_id}, {"id": vendor_id}]},
        {"_id": 0}
    )
    if not pattern:
        raise HTTPException(404, "Pattern not found")
    return pattern


@router.get("/receipts")
async def list_receipts(limit: int = 50, user=Depends(get_user)):
    """List recent uploaded receipts."""
    rid = user["restaurant_id"]
    receipts = await db.uploaded_receipts.find(
        {"restaurant_id": rid}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return receipts
