"""
Identity Resolver (Milestone 20)
=================================

Single source of truth for analytics grouping.

Usage pattern:

    idx = await build_canonical_index(restaurant_id)
    for p in purchases:
        for it in p["items"]:
            gkey, canon_name, variant_key = idx.resolve(it)
            # Use gkey (string) as the grouping key across all analytics.
            # canon_name is the display label; fall back to raw_name when None.

Rules (matches spec):
    • If item.canonical_item_id is set AND that canonical still exists →
      group by that id (follows one merge hop to merged_into_item_id).
    • Else if the raw_name maps to a known alias on an approved canonical →
      group by that canonical's id.
    • Else → group by `norm::<normalize_name(raw_name)>` (never the raw
      item_name itself).

Guardrails:
    • Tenant-scoped (all data loaded by restaurant_id).
    • Suggested / archived canonicals can still be resolution targets
      (so their invoice lines don't get fragmented before promotion) —
      but the matcher's auto-link guardrails are unchanged; we're only
      joining, not mutating.
    • Never merges variants: when two invoice lines resolve to the same
      canonical_item_id but have different `variant_key`, their group
      key differs by `::<variant_key>` suffix so variants stay separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.database import db
from services.item_identity import normalize_name


GROUP_PREFIX_CANON = "canon::"
GROUP_PREFIX_NORM = "norm::"


@dataclass
class CanonicalIndex:
    """Indexes used to resolve invoice-item → group key in O(1)."""
    by_id: dict[str, dict]                 # canonical_id → canonical doc
    alias_lookup: dict[str, str]           # normalized_alias → canonical_id
    name_lookup: dict[str, str]            # normalized_name → canonical_id
    merge_targets: dict[str, str]          # canonical_id → merge-resolved id

    def _resolve_canonical_id(self, raw_cid: Optional[str]) -> Optional[str]:
        if not raw_cid:
            return None
        cid = self.merge_targets.get(raw_cid, raw_cid)
        return cid if cid in self.by_id else None

    def resolve(self, item: dict) -> tuple[str, Optional[str], Optional[str]]:
        """
        Return (group_key, canonical_name_or_None, variant_key_or_None).

        group_key is stable across aliases / OCR noise:
          "canon::<canonical_id>[::<variant_key>]"  when identified
          "norm::<normalized_raw_name>"             fallback
        """
        cid = self._resolve_canonical_id(item.get("canonical_item_id"))
        variant_key = (item.get("variant_key") or "").strip().lower() or None

        if not cid:
            raw = (item.get("raw_name") or item.get("name") or "").strip()
            norm = normalize_name(raw)
            # Try alias → canonical
            a_cid = self.alias_lookup.get(norm)
            if a_cid:
                a_cid = self.merge_targets.get(a_cid, a_cid)
            cid = a_cid if a_cid and a_cid in self.by_id else None
            if not cid:
                # Try exact-name → canonical
                n_cid = self.name_lookup.get(norm)
                if n_cid:
                    n_cid = self.merge_targets.get(n_cid, n_cid)
                cid = n_cid if n_cid and n_cid in self.by_id else None

        if cid:
            c = self.by_id[cid]
            key = f"{GROUP_PREFIX_CANON}{cid}"
            if variant_key:
                key = f"{key}::{variant_key}"
            return key, c.get("name"), variant_key

        # Pure fallback — normalized raw_name, not raw
        raw = (item.get("raw_name") or item.get("name") or "").strip()
        norm = normalize_name(raw)
        if not norm:
            return f"{GROUP_PREFIX_NORM}__unnamed__", None, variant_key
        key = f"{GROUP_PREFIX_NORM}{norm}"
        if variant_key:
            key = f"{key}::{variant_key}"
        return key, None, variant_key


async def build_canonical_index(restaurant_id: str) -> CanonicalIndex:
    """Load all canonicals + aliases once for fast read-path joins."""
    canonicals: list[dict] = []
    async for c in db.canonical_items.find(
        {"restaurant_id": restaurant_id}, {"_id": 0},
    ):
        canonicals.append(c)
    aliases: list[dict] = []
    async for a in db.item_aliases.find(
        {"restaurant_id": restaurant_id, "is_archived": {"$ne": True}},
        {"_id": 0, "alias": 1, "alias_name": 1, "canonical_item_id": 1},
    ):
        aliases.append(a)

    by_id: dict[str, dict] = {}
    for c in canonicals:
        cid = c.get("id")
        if cid:
            by_id[cid] = c

    merge_targets: dict[str, str] = {}
    for c in canonicals:
        if c.get("is_merged") and c.get("merged_into_item_id"):
            merge_targets[c["id"]] = c["merged_into_item_id"]

    name_lookup: dict[str, str] = {}
    for c in canonicals:
        n = normalize_name(c.get("name"))
        if n and n not in name_lookup:
            name_lookup[n] = c["id"]

    alias_lookup: dict[str, str] = {}
    for a in aliases:
        alias_text = a.get("alias") or a.get("alias_name") or ""
        n = normalize_name(alias_text)
        cid = a.get("canonical_item_id")
        if n and cid and n not in alias_lookup:
            alias_lookup[n] = cid

    return CanonicalIndex(
        by_id=by_id,
        alias_lookup=alias_lookup,
        name_lookup=name_lookup,
        merge_targets=merge_targets,
    )
