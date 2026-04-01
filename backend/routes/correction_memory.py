import re

from fastapi import APIRouter, Depends

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
        {"restaurant_id": rid, "supplier_id": sup["id"]},
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
