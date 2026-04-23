"""
Item Matcher — 6-tier canonical-linking pipeline (Milestone 19)
================================================================

Given a raw invoice item name + a tenant, decide:
  - which canonical_item_id (if any) it maps to
  - which variant_key (if any) on that canonical
  - a confidence tier:  HIGH (auto-link) / MEDIUM (needs_review) / LOW (suggested)
  - explainable match metadata (tier, scores, candidates)

6-tier priority:
  1. exact canonical name match (case-insensitive, whitespace-trimmed)
  2. saved alias exact match
  3. normalized exact match (normalize_name(a) == normalize_name(b))
  4. token-set Jaccard ≥ TOKEN_STRONG
  5. fuzzy char ratio ≥ FUZZY_STRONG (OCR tolerance)
  6. correction_memory hit  (strongest signal short of explicit alias)

Auto-link guardrails (HIGH):
  • TOKEN ≥ TOKEN_AUTO  AND  FUZZY ≥ FUZZY_AUTO
  • single dominant candidate (next best is ≥ MARGIN behind)
  • variant extraction consistent (if the name contains a variant, the
    canonical must know that variant)

Otherwise:
  • any single tier at medium threshold  → MEDIUM (needs_review)
  • nothing above LOW_FLOOR              → LOW (suggested / unlinked)

Pure, stateless(ish): takes already-loaded canonical items, aliases, and
optional correction-memory rows. DB loading lives in services.catalog_linkage.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Iterable, List, Optional

from services.item_identity import (
    normalize_name, jaccard, fuzzy_ratio, split_base_and_variant,
)


# ── Thresholds (Q2 = stricter defaults chosen by product owner) ──
TOKEN_AUTO = 0.85
FUZZY_AUTO = 0.90
TOKEN_STRONG = 0.80
FUZZY_STRONG = 0.85
MEDIUM_FLOOR = 0.70
LOW_FLOOR = 0.55
MARGIN = 0.10  # gap required between best and 2nd-best for HIGH


@dataclass
class Candidate:
    canonical_item_id: str
    canonical_name: str
    variant_key: Optional[str]
    token_score: float
    fuzzy_score: float
    tier_reason: str  # e.g. "exact", "alias", "normalized", "token", "fuzzy", "memory"

    @property
    def composite(self) -> float:
        return max(self.token_score, self.fuzzy_score)


@dataclass
class MatchResult:
    canonical_item_id: Optional[str]
    canonical_name: Optional[str]
    variant_key: Optional[str]
    confidence: str  # "high" | "medium" | "low"
    tier: str        # which rule produced the winning match
    token_score: float
    fuzzy_score: float
    candidates: List[dict] = field(default_factory=list)
    needs_review: bool = False
    auto_linked: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _score_pair(raw: str, target: str) -> tuple[float, float]:
    return (jaccard(raw, target), fuzzy_ratio(raw, target))


def _find_variant_in_raw(raw: str, canonical_variants: list) -> Optional[str]:
    """Extract the variant key from the raw name if the canonical defines it."""
    if not canonical_variants:
        return None
    _, v = split_base_and_variant(raw, canonical_variants)
    return v


def match_item(
    raw_name: str,
    *,
    canonical_items: Iterable[dict],
    aliases: Iterable[dict],
    correction_memory: Iterable[dict] = (),
) -> MatchResult:
    """
    Run the 6-tier match. Callers must pass ONLY approved, non-archived
    canonical items as candidates (suggestions are NOT auto-linkable).

    `aliases` is a flat list of {alias, canonical_item_id} rows for the tenant.
    `correction_memory` is an optional list of {original_raw_name,
    corrected_name} rows.
    """
    raw = (raw_name or "").strip()
    if not raw:
        return MatchResult(None, None, None, "low", "empty", 0.0, 0.0, [], False, False)

    raw_norm = normalize_name(raw)
    canonicals = [c for c in canonical_items if not c.get("is_suggested") and not c.get("is_archived")]

    # Fast index by canonical id + normalized name.
    by_id = {c["id"]: c for c in canonicals if c.get("id")}
    norm_exact: dict[str, dict] = {}
    for c in canonicals:
        n = normalize_name(c.get("name"))
        if n and n not in norm_exact:
            norm_exact[n] = c

    # Alias map (normalized alias → canonical_item_id).
    alias_exact: dict[str, str] = {}
    for a in aliases:
        cid = a.get("canonical_item_id")
        raw_alias = a.get("alias") or a.get("alias_name") or ""
        if not cid or not raw_alias:
            continue
        n = normalize_name(raw_alias)
        if n and n not in alias_exact:
            alias_exact[n] = cid

    # Correction memory: normalized raw → corrected_name.
    memory_map: dict[str, str] = {}
    for m in correction_memory or []:
        orig = normalize_name(m.get("original_raw_name"))
        target = (m.get("corrected_name") or "").strip()
        if orig and target and orig not in memory_map:
            memory_map[orig] = target

    def _finalize_fast(c: dict, tier: str) -> MatchResult:
        """Exact/alias/normalized/memory tiers: still honor the variant
        guardrail — if the canonical defines variants but the raw doesn't
        contain one, downgrade to MEDIUM (needs_review)."""
        variant = _find_variant_in_raw(raw, c.get("variants") or [])
        canon_has_variants = bool(c.get("variants"))
        if canon_has_variants and variant is None:
            return MatchResult(
                c["id"], c.get("name"), None, "medium", tier,
                1.0, 1.0, [], True, False,
            )
        return MatchResult(
            c["id"], c.get("name"), variant, "high", tier,
            1.0, 1.0, [], False, True,
        )

    # ── Tier 1: exact canonical name match ──
    for c in canonicals:
        if (c.get("name") or "").strip().lower() == raw.lower():
            return _finalize_fast(c, "exact")

    # ── Tier 2: alias exact match ──
    if raw_norm in alias_exact:
        cid = alias_exact[raw_norm]
        c = by_id.get(cid)
        if c:
            return _finalize_fast(c, "alias")

    # ── Tier 3: normalized exact match ──
    if raw_norm in norm_exact:
        c = norm_exact[raw_norm]
        return _finalize_fast(c, "normalized")

    # ── Tier 6-ish: correction memory (treat as alias if the target exists) ──
    if raw_norm in memory_map:
        corrected = memory_map[raw_norm]
        c = norm_exact.get(normalize_name(corrected)) or by_id.get(
            alias_exact.get(normalize_name(corrected), "")
        )
        if c:
            return _finalize_fast(c, "memory")

    # ── Tiers 4 + 5: score every candidate, pick top ──
    scored: list[Candidate] = []
    for c in canonicals:
        targets = [c.get("name") or ""]
        # Also score against the canonical's own aliases.
        for alias, cid in alias_exact.items():
            if cid == c.get("id"):
                targets.append(alias)
        best_t = 0.0
        best_f = 0.0
        for t in targets:
            tj, fr = _score_pair(raw, t)
            if tj > best_t:
                best_t = tj
            if fr > best_f:
                best_f = fr
        if best_t >= LOW_FLOOR or best_f >= LOW_FLOOR:
            variant = _find_variant_in_raw(raw, c.get("variants") or [])
            reason = "token" if best_t >= best_f else "fuzzy"
            scored.append(Candidate(
                canonical_item_id=c["id"],
                canonical_name=c.get("name"),
                variant_key=variant,
                token_score=best_t,
                fuzzy_score=best_f,
                tier_reason=reason,
            ))

    scored.sort(key=lambda c: c.composite, reverse=True)
    if not scored:
        return MatchResult(None, None, None, "low", "no_match", 0.0, 0.0, [], False, False)

    top = scored[0]
    runner_up = scored[1].composite if len(scored) > 1 else 0.0
    candidate_dicts = [asdict(c) for c in scored[:5]]

    # ── HIGH / auto-link decision ──
    variant_ok = True  # trivially true — variant_key may be None on both sides
    canonical_has_variants = bool(by_id.get(top.canonical_item_id, {}).get("variants"))
    if canonical_has_variants and top.variant_key is None:
        # Canonical defines variants but we couldn't extract one.  Keep it
        # MEDIUM so a human confirms which variant.
        variant_ok = False

    if (
        top.token_score >= TOKEN_AUTO
        and top.fuzzy_score >= FUZZY_AUTO
        and (top.composite - runner_up) >= MARGIN
        and variant_ok
    ):
        return MatchResult(
            top.canonical_item_id, top.canonical_name, top.variant_key,
            "high", top.tier_reason, top.token_score, top.fuzzy_score,
            candidate_dicts, False, True,
        )

    # ── MEDIUM / needs_review ──
    if (
        top.token_score >= MEDIUM_FLOOR
        or top.fuzzy_score >= MEDIUM_FLOOR
        or top.token_score >= TOKEN_STRONG
        or top.fuzzy_score >= FUZZY_STRONG
    ):
        return MatchResult(
            top.canonical_item_id, top.canonical_name, top.variant_key,
            "medium", top.tier_reason, top.token_score, top.fuzzy_score,
            candidate_dicts, True, False,
        )

    # ── LOW / suggested (keep candidates for UI) ──
    return MatchResult(
        None, None, None, "low", "below_threshold",
        top.token_score, top.fuzzy_score, candidate_dicts, False, False,
    )
