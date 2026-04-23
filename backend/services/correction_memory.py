"""
Correction Memory v2 — services/correction_memory.py

Learns from user edits. Applies corrections to future items from the same vendor.

Key hierarchy (match priority):
  PRIMARY:   canonical_vendor + product_code   (confidence = 1.0)
  SECONDARY: canonical_vendor + norm_name + pack (confidence = 0.8)

Safety rules:
  - raw_name is NEVER overwritten. Corrections are additive only.
  - Corrections enter memory ONLY on explicit user save (not temp edits).
  - No destructive updates to historical records.
  - Primary matches are high-confidence; secondary matches are flagged as lower.
  - Conflicts: first matching primary wins; if no primary, first matching secondary wins.

DB collection: correction_memory
"""

import re
import uuid
from datetime import datetime, timezone

from core.database import db, logger


# ─────────────────────────────────────────────────────────────────────
# Key Building
# ─────────────────────────────────────────────────────────────────────

def _normalize_vendor(vendor_name: str) -> str:
    """Normalize vendor name to a canonical key fragment."""
    if not vendor_name:
        return ""
    v = vendor_name.strip().upper()
    # Map known variants to canonical
    if "SYSCO" in v:
        return "SYSCO"
    if "US FOOD" in v or "USFOODS" in v:
        return "USFOODS"
    if "PERFORMANCE" in v or "PFG" in v:
        return "PFG"
    # For other vendors, normalize to upper + strip punctuation
    v = re.sub(r'[^A-Z0-9\s]', '', v)
    v = re.sub(r'\s+', ' ', v).strip()
    return v


def _normalize_name(raw_name: str) -> str:
    """Normalize raw item name for secondary key matching."""
    if not raw_name:
        return ""
    n = raw_name.upper().strip()
    n = re.sub(r'[^A-Z0-9\s/]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    # Sort tokens for order-independence
    tokens = sorted(n.split())
    return ' '.join(tokens)


def _normalize_pack(pack_size: str) -> str:
    """Normalize pack size for key matching."""
    if not pack_size:
        return ""
    p = pack_size.upper().strip()
    p = re.sub(r'\s+', '', p)  # Remove all spaces: "1x30 LB" → "1X30LB"
    return p


def _clean_product_code(code: str) -> str:
    """Extract clean product code (digits only, min 4 chars)."""
    if not code:
        return ""
    digits = re.sub(r'[^0-9]', '', code)
    return digits if len(digits) >= 4 else ""


def build_primary_key(canonical_vendor: str, product_code: str) -> str:
    """Build primary correction key: vendor + product_code."""
    vendor = _normalize_vendor(canonical_vendor)
    code = _clean_product_code(product_code)
    if not vendor or not code:
        return ""
    return f"{vendor}:{code}"


def build_secondary_key(canonical_vendor: str, raw_name: str, pack_size: str) -> str:
    """Build secondary correction key: vendor + normalized_name + pack."""
    vendor = _normalize_vendor(canonical_vendor)
    name = _normalize_name(raw_name)
    pack = _normalize_pack(pack_size)
    if not vendor or not name:
        return ""
    return f"{vendor}:{name}:{pack}"


# ─────────────────────────────────────────────────────────────────────
# Save Correction (called on explicit user save only)
# ─────────────────────────────────────────────────────────────────────

async def save_correction(
    user_id: str,
    user_name: str,
    restaurant_id: str,
    canonical_vendor: str,
    original_raw_name: str,
    corrected_name: str,
    product_code: str = "",
    pack_size: str = "",
    corrected_specs: dict = None,
    # Legacy compat: accept supplier_id for backward compatibility
    supplier_id: str = "",
    normalized_key: str = "",
    # Correction Pipeline v3 metadata (non-breaking additions)
    source: str = "user_edit",
    variant: str = "",
    unit: str = "",
    category: str = "",
):
    """
    Save a correction when user explicitly saves an item edit.
    Upserts: if same primary or secondary key exists, update it.
    """
    p_key = build_primary_key(canonical_vendor, product_code)
    s_key = build_secondary_key(canonical_vendor, original_raw_name, pack_size)

    # Determine which key to use for upsert
    if p_key:
        match_key = p_key
        key_type = "primary"
    elif s_key:
        match_key = s_key
        key_type = "secondary"
    else:
        logger.warning(
            f"Correction skipped: no valid key for vendor='{canonical_vendor}', "
            f"code='{product_code}', name='{original_raw_name}'"
        )
        return None

    now = datetime.now(timezone.utc).isoformat()

    # Correction Pipeline v3 — canonicalize new metadata for storage
    src = (source or "user_edit").strip() or "user_edit"
    var = (variant or "").strip()
    un  = (unit or "").strip()
    cat = (category or "").strip()

    # Check for existing correction with same key
    existing = await db.correction_memory.find_one({
        "restaurant_id": restaurant_id,
        "correction_key": match_key,
    }, {"_id": 0})

    if existing:
        updates = {
            "corrected_name": corrected_name,
            "corrected_specs": corrected_specs or {},
            "corrected_by_user_id": user_id,
            "corrected_by_name": user_name,
            "original_raw_name": original_raw_name,
            "canonical_vendor": _normalize_vendor(canonical_vendor),
            "product_code": _clean_product_code(product_code),
            "pack_size": pack_size.strip() if pack_size else "",
            "source": src,
            "variant": var,
            "unit": un,
            "category": cat,
            "updated_at": now,
        }
        # Preserve primary_key / secondary_key if they got stronger
        if p_key and not existing.get("primary_key"):
            updates["primary_key"] = p_key
            updates["key_type"] = "primary"
        if s_key and not existing.get("secondary_key"):
            updates["secondary_key"] = s_key

        await db.correction_memory.update_one(
            {"id": existing["id"]},
            {"$set": updates},
        )
        logger.info(
            f"Correction updated [{key_type}]: '{original_raw_name}' → "
            f"'{corrected_name}' (key={match_key})"
        )
        return {**existing, **updates}
    else:
        doc = {
            "id": str(uuid.uuid4()),
            "restaurant_id": restaurant_id,
            "corrected_by_user_id": user_id,
            "corrected_by_name": user_name,
            "canonical_vendor": _normalize_vendor(canonical_vendor),
            "product_code": _clean_product_code(product_code),
            "pack_size": pack_size.strip() if pack_size else "",
            "correction_key": match_key,
            "primary_key": p_key,
            "secondary_key": s_key,
            "key_type": key_type,
            "original_raw_name": original_raw_name,
            "corrected_name": corrected_name,
            "corrected_specs": corrected_specs or {},
            # Correction Pipeline v3 fields
            "source": src,
            "variant": var,
            "unit": un,
            "category": cat,
            "enabled": True,
            "times_matched": 0,
            "last_used_at": None,
            "created_at": now,
            "updated_at": now,
            # Legacy compat fields
            "supplier_id": supplier_id,
            "normalized_key": normalized_key or match_key,
            "user_id": user_id,
            "usage_count": 0,
        }
        await db.correction_memory.insert_one(doc)
        doc.pop("_id", None)
        logger.info(
            f"Correction saved [{key_type}]: '{original_raw_name}' → "
            f"'{corrected_name}' (key={match_key})"
        )
        return doc


# ─────────────────────────────────────────────────────────────────────
# Apply Corrections (called post-extraction)
# ─────────────────────────────────────────────────────────────────────

# Confidence levels for match types
CONFIDENCE_PRIMARY = 1.0    # vendor + product_code — strong
CONFIDENCE_SECONDARY = 0.75  # vendor + name + pack — weaker


async def apply_corrections(
    items: list,
    restaurant_id: str,
    canonical_vendor: str,
    # Legacy compat
    supplier_id: str = "",
):
    """
    Check each item against correction_memory. If a match is found,
    apply the corrected name as a display layer. Never overwrites raw_name.

    Match priority:
      1. PRIMARY: canonical_vendor + product_code  (confidence=1.0)
      2. SECONDARY: canonical_vendor + norm_name + pack (confidence=0.75)

    Conflict resolution: first matching key wins per priority tier.

    Provenance: every applied correction is logged and stored on the item
    in the `correction_applied` dict.
    """
    if not items:
        return items

    norm_vendor = _normalize_vendor(canonical_vendor)
    if not norm_vendor:
        return items

    # Batch-load all corrections for this vendor OR legacy supplier_id
    query = {"restaurant_id": restaurant_id, "enabled": {"$ne": False}}
    # Match by canonical_vendor (new) or supplier_id (legacy)
    or_clauses = [{"canonical_vendor": norm_vendor}]
    if supplier_id:
        or_clauses.append({"supplier_id": supplier_id})
    query["$or"] = or_clauses

    corrections = await db.correction_memory.find(
        query, {"_id": 0}
    ).to_list(500)

    if not corrections:
        return items

    # Build lookup indexes
    primary_index = {}   # key: primary_key → correction
    secondary_index = {}  # key: secondary_key → correction

    for c in corrections:
        # Primary index: by product code key
        pk = c.get("primary_key", "")
        if pk and pk not in primary_index:
            primary_index[pk] = c

        # Secondary index: by name+pack key
        sk = c.get("secondary_key", "")
        if sk and sk not in secondary_index:
            secondary_index[sk] = c

        # Legacy compat: index by old normalized_key (secondary tier)
        legacy_key = c.get("normalized_key", "")
        if legacy_key and not sk:
            # Build a pseudo-secondary key from legacy data
            legacy_sk = f"{norm_vendor}:{legacy_key}:"
            if legacy_sk not in secondary_index:
                secondary_index[legacy_sk] = c

    now = datetime.now(timezone.utc).isoformat()
    used_ids = []

    for item in items:
        raw_name = (item.get("raw_name") or "").strip()
        item_code = (item.get("item_code") or "").strip()
        pack = (item.get("pack_size") or item.get("pack_size_raw") or "").strip()

        matched_correction = None
        match_type = None
        match_key_used = ""
        match_confidence = 0.0

        # ── Priority 1: PRIMARY match (vendor + product_code) ──
        p_key = build_primary_key(canonical_vendor, item_code)
        if p_key and p_key in primary_index:
            matched_correction = primary_index[p_key]
            match_type = "primary"
            match_key_used = p_key
            match_confidence = CONFIDENCE_PRIMARY

        # ── Priority 2: SECONDARY match (vendor + name + pack) ──
        if not matched_correction:
            s_key = build_secondary_key(canonical_vendor, raw_name, pack)
            if s_key and s_key in secondary_index:
                matched_correction = secondary_index[s_key]
                match_type = "secondary"
                match_key_used = s_key
                match_confidence = CONFIDENCE_SECONDARY

        # ── Legacy fallback: match by old normalized_key ──
        if not matched_correction:
            norm_data = item.get("norm") or {}
            strict_key = norm_data.get("strict_match_key", "")
            if strict_key:
                legacy_sk = f"{norm_vendor}:{strict_key}:"
                if legacy_sk in secondary_index:
                    matched_correction = secondary_index[legacy_sk]
                    match_type = "secondary_legacy"
                    match_key_used = legacy_sk
                    match_confidence = CONFIDENCE_SECONDARY

        if not matched_correction:
            continue

        corrected_name = matched_correction.get("corrected_name", "")
        corrected_specs = matched_correction.get("corrected_specs", {})

        # ── Apply correction (ADDITIVE ONLY — raw_name untouched) ──
        item["correction_applied"] = {
            "corrected_name": corrected_name,
            "raw_name_preserved": raw_name,
            "correction_id": matched_correction["id"],
            "match_type": match_type,
            "match_key": match_key_used,
            "match_confidence": match_confidence,
            "corrected_specs": corrected_specs,
        }

        # Apply to display layer only
        norm_data = item.get("norm") or {}
        if corrected_name and corrected_name != raw_name:
            norm_data["clean_name"] = corrected_name.strip().upper()
            norm_data["base_name"] = corrected_name.strip().upper()
            item["norm"] = norm_data

        if corrected_specs:
            specs = norm_data.get("specs") or {}
            for k, v in corrected_specs.items():
                if v is not None:
                    specs[k] = v
            norm_data["specs"] = specs
            item["norm"] = norm_data

        item["confidence_level"] = "learned"
        # Only clear review if no validation errors
        if not item.get("validation_errors"):
            item["needs_review"] = False
            item["review_reason"] = None

        logger.info(
            f"Correction applied [{match_type}, conf={match_confidence}]: "
            f"raw='{raw_name}' → corrected='{corrected_name}' "
            f"(key={match_key_used})"
        )
        used_ids.append(matched_correction["id"])

    # Batch-update usage stats
    if used_ids:
        await db.correction_memory.update_many(
            {"id": {"$in": used_ids}},
            {"$inc": {"times_matched": 1, "usage_count": 1},
             "$set": {"last_used_at": now}},
        )

    return items
