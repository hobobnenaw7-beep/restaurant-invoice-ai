"""
Catalog Linkage (lightweight)
==============================
When a user corrects an invoice item's name, attempt to link the correction
to the canonical Items catalog WITHOUT aggressive overwrites.

Flow:
  1. Search canonical_items for a case-insensitive match on `name`
     (exact match first, then `contains`).
  2. If matched → upsert an `item_aliases` row mapping
       raw_name → canonical_item_id. Increment usage count on match.
     Return: {action: "linked", canonical_item_id, canonical_name}.
  3. If NOT matched → insert a new canonical_items row with
     `is_suggested: true` so it shows up in the UI as a suggestion
     the user can promote or edit, but does NOT pollute active catalog.
     Return: {action: "suggested", canonical_item_id, canonical_name}.

Strict rules:
  - NEVER overwrite an existing canonical_item's core fields.
  - NEVER merge / delete existing items.
  - NEVER create duplicates: if an alias for (restaurant_id, raw_name) already exists, update its usage.
  - ALWAYS tenant-scoped via restaurant_id.

Collections used:
  - canonical_items   (existing)
  - item_aliases      (existing)
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import db

logger = logging.getLogger("restaurant_ai")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _find_canonical(restaurant_id: str, corrected_name: str) -> Optional[dict]:
    """Case-insensitive name search: exact then contains."""
    name = (corrected_name or "").strip()
    if not name:
        return None
    # Exact (case-insensitive) match first
    escaped = {
        "restaurant_id": restaurant_id,
        "name": {"$regex": f"^{_regex_escape(name)}$", "$options": "i"},
    }
    hit = await db.canonical_items.find_one(escaped, {"_id": 0})
    if hit:
        return hit
    # Fallback: contains. Restrict to fairly specific matches (>=4 char shared token).
    if len(name) >= 4:
        contains = {
            "restaurant_id": restaurant_id,
            "name": {"$regex": _regex_escape(name), "$options": "i"},
        }
        return await db.canonical_items.find_one(contains, {"_id": 0})
    return None


def _regex_escape(s: str) -> str:
    import re
    return re.escape(s)


async def _upsert_alias(
    *, restaurant_id: str, canonical_item_id: str, raw_name: str, user_id: Optional[str]
) -> None:
    """Create or increment an alias mapping for this raw_name."""
    raw = (raw_name or "").strip()
    if not raw:
        return
    existing = await db.item_aliases.find_one(
        {"restaurant_id": restaurant_id, "canonical_item_id": canonical_item_id, "alias": raw},
        {"_id": 0},
    )
    now = _utcnow()
    if existing:
        await db.item_aliases.update_one(
            {"id": existing["id"]},
            {"$set": {"last_used_at": now}, "$inc": {"usage_count": 1}},
        )
        return
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "canonical_item_id": canonical_item_id,
        "alias": raw,
        "source": "user_edit",
        "created_by_user_id": user_id,
        "created_at": now,
        "last_used_at": now,
        "usage_count": 1,
    }
    await db.item_aliases.insert_one(doc)


async def link_correction_to_catalog(
    *,
    restaurant_id: str,
    user_id: Optional[str],
    original_raw_name: str,
    corrected_name: str,
    unit: str = "",
    category: str = "",
) -> dict:
    """
    Lightweight, non-destructive catalog linkage.

    Returns:
        {"action": "linked" | "suggested" | "skipped",
         "canonical_item_id": str | None,
         "canonical_name": str | None}
    """
    name = (corrected_name or "").strip()
    if not name:
        return {"action": "skipped", "canonical_item_id": None, "canonical_name": None}

    match = await _find_canonical(restaurant_id, name)
    if match:
        await _upsert_alias(
            restaurant_id=restaurant_id,
            canonical_item_id=match["id"],
            raw_name=original_raw_name,
            user_id=user_id,
        )
        return {
            "action": "linked",
            "canonical_item_id": match["id"],
            "canonical_name": match.get("name", name),
        }

    # Not matched → create a suggested canonical_item (non-destructive).
    now = _utcnow()
    new_id = str(uuid.uuid4())
    doc = {
        "id": new_id,
        "restaurant_id": restaurant_id,
        "name": name,
        "category": (category or "").strip(),
        "unit": (unit or "").strip(),
        "is_suggested": True,
        "suggested_source": "user_edit",
        "suggested_by_user_id": user_id,
        "storage_category": "uncategorized",
        "created_at": now,
    }
    await db.canonical_items.insert_one(doc)
    # Also create an alias so the linkage is traceable.
    await _upsert_alias(
        restaurant_id=restaurant_id,
        canonical_item_id=new_id,
        raw_name=original_raw_name,
        user_id=user_id,
    )
    return {"action": "suggested", "canonical_item_id": new_id, "canonical_name": name}
