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

    # Load ALL non-archived canonical items — both APPROVED and SUGGESTED.
    # Suggested items exist because the user corrected an invoice to that
    # name; they ARE learned memory and must surface in autocomplete so
    # the next time the user types the same correction they see it.
    canonicals = await db.canonical_items.find(
        {
            "restaurant_id": rid,
            "is_archived": {"$ne": True},
        },
        {"_id": 0, "id": 1, "name": 1, "variants": 1, "category": 1, "unit": 1,
         "is_suggested": 1},
    ).to_list(2000)

    # Load aliases for ALL non-archived canonicals (approved + suggested).
    approved_ids = {c["id"] for c in canonicals if c.get("id")}
    aliases = []
    if approved_ids:
        aliases = await db.item_aliases.find(
            {
                "restaurant_id": rid,
                "canonical_item_id": {"$in": list(approved_ids)},
                "is_archived": {"$ne": True},
            },
            {"_id": 0, "alias": 1, "alias_name": 1, "canonical_item_id": 1, "variant_keys": 1},
        ).to_list(5000)

    q_norm = normalize_name(query)
    suggestions: list[dict] = []

    # 1) canonical names + their variants
    for c in canonicals:
        name = c.get("name") or ""
        is_suggested = bool(c.get("is_suggested"))
        base_source = "learned" if is_suggested else "canonical"
        base_score = _score(query, name) + _prefix_boost(q_norm, normalize_name(name))
        if base_score > 0.25:
            suggestions.append({
                "label": name,
                "canonical_item_id": c["id"],
                "variant_key": None,
                "source": base_source,
                "score": round(min(1.0, base_score), 4),
                "category": c.get("category"),
                "unit": c.get("unit"),
                "is_suggested": is_suggested,
            })
        # Variants (approved items only declare variants; suggested rarely do).
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
                    "is_suggested": is_suggested,
                })

    # 2) aliases — may carry learned variants → expose as full "Canon — v1 — v2" suggestion.
    by_id = {c["id"]: c for c in canonicals if c.get("id")}
    for a in aliases:
        text = (a.get("alias") or a.get("alias_name") or "").strip()
        cid = a.get("canonical_item_id")
        c = by_id.get(cid)
        if not text or not c:
            continue
        # Score against alias text AND the canonical name for generous recall
        a_score = max(
            _score(query, text),
            _score(query, c.get("name") or ""),
        ) + _prefix_boost(q_norm, normalize_name(text))
        # Compose a labelled suggestion using learned variants (if any).
        learned_vkeys = list(a.get("variant_keys") or [])
        variant_labels = []
        for vk in learned_vkeys:
            for v in (c.get("variants") or []):
                if (v.get("key") or "").lower() == vk:
                    variant_labels.append(v.get("label") or vk)
                    break
        label = c.get("name") or text
        if variant_labels:
            label = " — ".join([label, *variant_labels])
        if a_score > 0.30:
            is_suggested_canon = bool(c.get("is_suggested"))
            suggestions.append({
                "label": label,
                "canonical_item_id": cid,
                "variant_key": learned_vkeys[0] if learned_vkeys else None,
                "variant_keys": learned_vkeys,
                "source": "learned" if (learned_vkeys or is_suggested_canon) else "alias",
                "score": round(min(1.0, a_score), 4),
                "category": c.get("category"),
                "unit": c.get("unit"),
                "alias_text": text,
                "is_suggested": is_suggested_canon,
            })

    # Deduplicate by (canonical_item_id, variant_keys tuple) — keep highest-scoring.
    dedup: dict[tuple, dict] = {}
    for s in suggestions:
        vks = tuple(s.get("variant_keys") or ([s.get("variant_key")] if s.get("variant_key") else []))
        key = (s["canonical_item_id"], vks)
        if key not in dedup or s["score"] > dedup[key]["score"]:
            dedup[key] = s
    ranked = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)[: max(1, int(limit))]
    return {"query": query, "suggestions": ranked}

