"""
Smart Autocomplete — Approved-only suggestions (Milestone 19)
==============================================================

GET /api/items/autocomplete?q=<query>&limit=20

Suggestion sources (APPROVED system data only):
  1. canonical items where is_suggested=False AND is_archived=False
  2. variants declared on those canonical items
  3. saved aliases on those canonical items

NEVER returns:
  - raw invoice text
  - suggested (pending) canonical items
  - archived items
  - free-typed user text

Response shape (each suggestion):
  {
    "label": "Live Blue Crab (Male)",
    "canonical_item_id": "<uuid>",
    "variant_key": "male" | null,
    "source": "canonical" | "variant" | "alias",
    "score": 0..1
  }
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.database import db
from core.auth import get_user
from services.item_identity import normalize_name, jaccard, fuzzy_ratio

router = APIRouter()


def _score(q: str, target: str) -> float:
    # Max of token-set Jaccard and fuzzy ratio — good for short prefixes.
    return max(jaccard(q, target), fuzzy_ratio(q, target))


def _prefix_boost(q_norm: str, target_norm: str) -> float:
    """Give a small boost when the normalized target starts with the query."""
    if not q_norm or not target_norm:
        return 0.0
    if target_norm.startswith(q_norm):
        return 0.15
    # Any token in target starting with q?
    for tok in target_norm.split(" "):
        if tok.startswith(q_norm):
            return 0.08
    return 0.0


@router.get("/items/autocomplete")
async def item_autocomplete(
    q: str = "",
    limit: int = 20,
    user=Depends(get_user),
):
    rid = user["restaurant_id"]
    query = (q or "").strip()
    if not query:
        return {"query": "", "suggestions": []}

    # Load approved, non-archived canonical items only.
    canonicals = await db.canonical_items.find(
        {
            "restaurant_id": rid,
            "is_suggested": {"$ne": True},
            "is_archived": {"$ne": True},
        },
        {"_id": 0, "id": 1, "name": 1, "variants": 1, "category": 1, "unit": 1},
    ).to_list(2000)

    # Load aliases for those canonicals only (still tenant-scoped).
    approved_ids = {c["id"] for c in canonicals if c.get("id")}
    aliases = []
    if approved_ids:
        aliases = await db.item_aliases.find(
            {
                "restaurant_id": rid,
                "canonical_item_id": {"$in": list(approved_ids)},
                "is_archived": {"$ne": True},
            },
            {"_id": 0, "alias": 1, "alias_name": 1, "canonical_item_id": 1},
        ).to_list(5000)

    q_norm = normalize_name(query)
    suggestions: list[dict] = []

    # 1) canonical names + their variants
    for c in canonicals:
        name = c.get("name") or ""
        base_score = _score(query, name) + _prefix_boost(q_norm, normalize_name(name))
        if base_score > 0.25:
            suggestions.append({
                "label": name,
                "canonical_item_id": c["id"],
                "variant_key": None,
                "source": "canonical",
                "score": round(min(1.0, base_score), 4),
                "category": c.get("category"),
                "unit": c.get("unit"),
            })
        # Variants
        for v in (c.get("variants") or []):
            key = (v.get("key") or "").strip()
            label = (v.get("label") or key).strip()
            if not key:
                continue
            variant_label = f"{name} ({label})"
            v_score = _score(query, variant_label) + _prefix_boost(q_norm, normalize_name(variant_label))
            # Also consider match against just the variant word (e.g. "male").
            v_score = max(v_score, _score(query, label))
            if v_score > 0.25:
                suggestions.append({
                    "label": variant_label,
                    "canonical_item_id": c["id"],
                    "variant_key": key,
                    "source": "variant",
                    "score": round(min(1.0, v_score), 4),
                    "category": c.get("category"),
                    "unit": c.get("unit"),
                })

    # 2) aliases
    by_id = {c["id"]: c for c in canonicals if c.get("id")}
    for a in aliases:
        text = (a.get("alias") or a.get("alias_name") or "").strip()
        cid = a.get("canonical_item_id")
        c = by_id.get(cid)
        if not text or not c:
            continue
        a_score = _score(query, text) + _prefix_boost(q_norm, normalize_name(text))
        if a_score > 0.30:
            suggestions.append({
                "label": f'{c.get("name")}  —  "{text}"',
                "canonical_item_id": cid,
                "variant_key": None,
                "source": "alias",
                "score": round(min(1.0, a_score), 4),
                "category": c.get("category"),
                "unit": c.get("unit"),
            })

    # Deduplicate by (canonical_item_id, variant_key) — keep highest-scoring.
    dedup: dict[tuple, dict] = {}
    for s in suggestions:
        key = (s["canonical_item_id"], s.get("variant_key"))
        if key not in dedup or s["score"] > dedup[key]["score"]:
            dedup[key] = s
    ranked = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)[: max(1, int(limit))]
    return {"query": query, "suggestions": ranked}
