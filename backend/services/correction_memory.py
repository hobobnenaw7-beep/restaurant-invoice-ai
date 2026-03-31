"""
Correction Memory — services/correction_memory.py

Learns from user edits. Applies corrections to future items from the same supplier.

Matching: strict_match_key only, supplier-scoped.
Safety: Never overwrites raw_name. Stores corrections separately.

DB collection: correction_memory
"""

import uuid
from datetime import datetime, timezone

from core.database import db, logger


async def save_correction(
    user_id: str,
    restaurant_id: str,
    supplier_id: str,
    original_raw_name: str,
    normalized_key: str,
    corrected_name: str,
    corrected_specs: dict = None,
):
    """
    Save a correction when user edits an item.
    Upserts: if same (restaurant_id, supplier_id, normalized_key) exists, update it.
    """
    if not normalized_key or not supplier_id:
        return None

    existing = await db.correction_memory.find_one({
        "restaurant_id": restaurant_id,
        "supplier_id": supplier_id,
        "normalized_key": normalized_key,
    }, {"_id": 0})

    now = datetime.now(timezone.utc).isoformat()

    if existing:
        updates = {
            "corrected_name": corrected_name,
            "corrected_specs": corrected_specs or {},
            "original_raw_name": original_raw_name,
            "user_id": user_id,
            "updated_at": now,
            "confidence": min(existing.get("confidence", 1.0) + 0.1, 2.0),
        }
        await db.correction_memory.update_one(
            {"id": existing["id"]},
            {"$set": updates},
        )
        logger.info(
            f"Correction updated: '{original_raw_name}' → '{corrected_name}' "
            f"(supplier={supplier_id[:8]}, key={normalized_key})"
        )
        return {**existing, **updates}
    else:
        doc = {
            "id": str(uuid.uuid4()),
            "restaurant_id": restaurant_id,
            "user_id": user_id,
            "supplier_id": supplier_id,
            "normalized_key": normalized_key,
            "original_raw_name": original_raw_name,
            "corrected_name": corrected_name,
            "corrected_specs": corrected_specs or {},
            "confidence": 1.0,
            "created_at": now,
            "updated_at": now,
        }
        await db.correction_memory.insert_one(doc)
        doc.pop("_id", None)
        logger.info(
            f"Correction saved: '{original_raw_name}' → '{corrected_name}' "
            f"(supplier={supplier_id[:8]}, key={normalized_key})"
        )
        return doc


async def apply_corrections(items: list, restaurant_id: str, supplier_id: str):
    """
    Check each item against correction_memory. If a match is found,
    apply the corrected name/specs and mark confidence_level as 'learned'.

    Match key: (restaurant_id, supplier_id, strict_match_key)

    Does NOT overwrite raw_name. Adds 'correction_applied' metadata.
    """
    if not supplier_id or not items:
        return items

    # Batch-load all corrections for this supplier
    corrections = await db.correction_memory.find(
        {"restaurant_id": restaurant_id, "supplier_id": supplier_id},
        {"_id": 0},
    ).to_list(500)

    if not corrections:
        return items

    # Index by normalized_key for O(1) lookup
    correction_map = {}
    for c in corrections:
        key = c.get("normalized_key", "")
        if key:
            correction_map[key] = c

    for item in items:
        norm = item.get("norm")
        if not norm:
            continue

        strict_key = norm.get("strict_match_key", "")
        if not strict_key:
            continue

        correction = correction_map.get(strict_key)
        if not correction:
            continue

        # Apply correction — store ALONGSIDE originals, never replace raw_name
        corrected_name = correction.get("corrected_name", "")
        corrected_specs = correction.get("corrected_specs", {})

        item["correction_applied"] = {
            "from_raw": item.get("raw_name", ""),
            "corrected_name": corrected_name,
            "corrected_specs": corrected_specs,
            "correction_id": correction["id"],
            "correction_confidence": correction.get("confidence", 1.0),
            "matched_key": strict_key,
        }

        # Override display-level fields (NOT raw_name)
        if corrected_name:
            norm["clean_name"] = corrected_name.strip().upper()
            norm["base_name"] = corrected_name.strip().upper()

        if corrected_specs:
            for k, v in corrected_specs.items():
                if v is not None:
                    norm["specs"][k] = v

        item["confidence_level"] = "learned"
        # Only clear needs_review if item has no validation errors
        # (math mismatch, missing name, etc. should still require review)
        has_validation_errors = bool(item.get("validation_errors"))
        if not has_validation_errors:
            item["needs_review"] = False
            item["review_reason"] = None

        logger.info(
            f"Correction applied: '{item.get('raw_name','')}' → '{corrected_name}' "
            f"(key={strict_key}, confidence={correction.get('confidence', 1.0)})"
        )

    return items
