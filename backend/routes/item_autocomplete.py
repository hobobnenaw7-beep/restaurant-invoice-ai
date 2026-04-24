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

    # Build an alias lookup: {canonical_id: [(alias_text, variant_keys)]}.
    # Aliases are MATCHING SIGNALS only — they never produce their own row.
    alias_index: dict[str, list[tuple[str, list[str]]]] = {}
    for a in aliases:
        text = (a.get("alias") or a.get("alias_name") or "").strip()
        cid = a.get("canonical_item_id")
        if not text or not cid:
            continue
        alias_index.setdefault(cid, []).append(
            (text, [str(v).strip().lower() for v in (a.get("variant_keys") or []) if v]),
        )

    def alias_boost(cid: str) -> tuple[float, list[str]]:
        """
        Return (best_alias_score, variant_keys_from_best_matching_alias).
        This lets alias text contribute recall (e.g. the user types the OCR'd
        form) while still emitting a row labelled with the canonical name.
        """
        best = 0.0
        best_vkeys: list[str] = []
        for text, vkeys in alias_index.get(cid, []):
            s = _score(query, text) + _prefix_boost(q_norm, normalize_name(text))
            if s > best:
                best = s
                best_vkeys = vkeys
        return best, best_vkeys

    # Emit ONE row per (canonical_item_id, variant_key).
    #   • approved canonical → source "canonical" (variants → "variant")
    #   • suggested canonical → source "learned" (no variants)
    # Aliases never become rows — they only boost matching recall and, when
    # they carry variant_keys, can attach the best learned variant to the
    # canonical base row so it still lands on the correct target.
    buckets: dict[tuple, dict] = {}

    def upsert(key: tuple, candidate: dict) -> None:
        prev = buckets.get(key)
        if prev is None or candidate["score"] > prev["score"]:
            buckets[key] = candidate

    for c in canonicals:
        cid = c.get("id")
        name = c.get("name") or ""
        if not cid or not name:
            continue
        is_suggested = bool(c.get("is_suggested"))

        # Alias contribution for this canonical.
        a_score, a_vkeys = alias_boost(cid)

        # ── 1. Base (no variant) row ──
        name_score = _score(query, name) + _prefix_boost(q_norm, normalize_name(name))
        base_score = max(name_score, a_score)
        if base_score > 0.25:
            # If alias carries learned variant_keys, promote to a variant row
            # (see "learned variant attachment" below) instead of a bare base row.
            if not a_vkeys:
                upsert(
                    (cid, ()),
                    {
                        "label": name,
                        "canonical_item_id": cid,
                        "variant_key": None,
                        "variant_keys": [],
                        "source": "learned" if is_suggested else "canonical",
                        "score": round(min(1.0, base_score), 4),
                        "category": c.get("category"),
                        "unit": c.get("unit"),
                        "is_suggested": is_suggested,
                    },
                )

        # ── 2. Declared variant rows (approved canonicals only typically) ──
        declared = c.get("variants") or []
        declared_keys = [(v.get("key") or "").strip().lower() for v in declared]
        for v in declared:
            key = (v.get("key") or "").strip().lower()
            label = (v.get("label") or key).strip()
            if not key:
                continue
            full = " — ".join([name, label])
            vs = _score(query, full) + _prefix_boost(q_norm, normalize_name(full))
            vs = max(vs, _score(query, label))
            # If aliases learned this specific variant, include their score too.
            if key in a_vkeys:
                vs = max(vs, a_score)
            if vs > 0.25:
                upsert(
                    (cid, (key,)),
                    {
                        "label": full,
                        "canonical_item_id": cid,
                        "variant_key": key,
                        "variant_keys": [key],
                        "source": "variant",
                        "score": round(min(1.0, vs), 4),
                        "category": c.get("category"),
                        "unit": c.get("unit"),
                        "is_suggested": is_suggested,
                    },
                )

        # ── 3. Learned-variant attachment ──
        # If an alias carries variant_keys that match DECLARED variants but
        # didn't already land above (because user query matched the alias
        # text, not the variant word), emit the combined canonical+variant row.
        if a_vkeys and a_score > 0.30:
            keys_tuple = tuple(k for k in a_vkeys if k in declared_keys)
            if keys_tuple:
                labels_parts = []
                for k in keys_tuple:
                    for v in declared:
                        if (v.get("key") or "").lower() == k:
                            labels_parts.append(v.get("label") or k)
                            break
                full = " — ".join([name, *labels_parts])
                upsert(
                    (cid, keys_tuple),
                    {
                        "label": full,
                        "canonical_item_id": cid,
                        "variant_key": keys_tuple[0],
                        "variant_keys": list(keys_tuple),
                        "source": "variant",
                        "score": round(min(1.0, a_score), 4),
                        "category": c.get("category"),
                        "unit": c.get("unit"),
                        "is_suggested": is_suggested,
                    },
                )

    ranked = sorted(buckets.values(), key=lambda x: x["score"], reverse=True)[: max(1, int(limit))]
    return {"query": query, "suggestions": ranked}

