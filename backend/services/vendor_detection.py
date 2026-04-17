"""
Multi-Signal Vendor Detection & Parser Routing
================================================

Combines three independent signals to decide which vendor-specific parser
to route an invoice through:

  Signal 1 — GPT Vendor Name:  Enhanced prompt returns structured JSON
             with vendor name, confidence, and identifying clues.
  Signal 2 — Content Clues:    Pattern-match GPT's reported clues against
             known vendor fingerprints (domains, account formats, headers).
  Signal 3 — Layout Signature: Column header keywords that uniquely
             identify a vendor's invoice format.

Each signal produces a per-vendor confidence score (0.0–1.0).
A weighted combination determines the final routing decision.

Logging:  Every routing decision is returned as a structured dict with
          all signals, scores, and the reasoning chain — stored on the
          receipt document for full auditability.
"""

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("restaurant_ai")


# ─────────────────────────────────────────────────────────────────────
# Canonical Vendor Registry
# ─────────────────────────────────────────────────────────────────────

VENDOR_REGISTRY = {
    "sysco": {
        "canonical": "Sysco",
        "parser": "sysco",
        "name_variants": [
            "sysco", "sysco jacksonville", "sysco jacksonville inc",
            "sysco jacksonville, inc", "sysco jacksonville, inc.",
            "sysco atlanta", "sysco atlanta, llc", "sysco atlanta llc",
            "sysco food services", "sysco lifeshare", "sysco los angeles",
            "sysco food services of", "sysco central florida",
            "sysco jacksonville llc", "sysco jacksonville, llc",
            "sysco guest supply", "sysco corporation",
        ],
        "content_clues": [
            r"sysco\.com", r"sysco\s+corporation", r"sysco\s+guest\s+supply",
            r"www\.sysco", r"order\s+guide", r"sysco\s+account",
        ],
        "layout_keywords": [
            "item", "description", "pack", "qty", "price", "amount",
        ],
    },
    "usfoods": {
        "canonical": "US Foods",
        "parser": "usfoods_structural",
        "name_variants": [
            "us foods", "us foods inc", "us foods, inc", "us foods, inc.",
            "us foods inc.", "usfoods", "u.s. foods", "u.s. foods inc",
            "u.s. foods, inc.", "us foods incorporated",
            "us food", "us food inc", "us food service",
            "us foodservice", "usfoodservice",
            "us foods distribution",
        ],
        "content_clues": [
            r"usfoods\.com", r"www\.usfoods", r"USF\s*#", r"USF\d",
            r"us\s*foods.*order", r"usfoods.*account",
            r"us\s*foods.*distribution", r"next\.usfoods",
        ],
        "layout_keywords": [
            "shipped", "ordered", "ext price", "extended price",
            "weight", "brand", "product",
        ],
    },
    "pfg": {
        "canonical": "Performance Foodservice",
        "parser": "pfg",
        "name_variants": [
            "performance foodservice", "performance food service",
            "performance foodservice powell", "pfg", "pfg powell",
            "performance food group", "pfg atlanta",
            "performance foodservice southeast",
            "performance foodservice - southeast",
            "performance foodservice powell-perfection",
            "pfh atlanta", "performance foodservice powell (pfp)",
            "perfection harris", "performance food",
        ],
        "content_clues": [
            r"pfgonline\.com", r"performancefoodservice",
            r"www\.pfg", r"pfg\s+account", r"performance\s+food",
        ],
        "layout_keywords": [
            "ship", "ord", "ext total", "$/lb", "unit prc",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────
# Enhanced Vendor Detection Prompt
# ─────────────────────────────────────────────────────────────────────

VENDOR_DETECT_PROMPT = """Look at this invoice/receipt image. Return a JSON object with:
1. "vendor_name": The supplier/vendor company name printed on the document. If unclear, return "UNKNOWN".
2. "confidence": Your confidence in the vendor identification — "high", "medium", or "low".
3. "clues": A list of identifying text you can see — website URLs, email domains, account number formats, phone numbers, specific header text, column header names visible in any table.

Return ONLY valid JSON, no other text. Example:
{"vendor_name":"US Foods, Inc.","confidence":"high","clues":["usfoods.com","USF# 1234567","SHIPPED column header","EXTENDED PRICE column"]}"""


# ─────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class VendorSignal:
    source: str          # "name_match", "content_clue", "layout_keyword"
    vendor_key: str      # "sysco", "usfoods", "pfg"
    score: float         # 0.0 – 1.0
    detail: str          # Human-readable reason


@dataclass
class VendorRoutingResult:
    detected_vendor: str          # Raw GPT-detected vendor name
    canonical_vendor: str         # Normalized canonical name (or "Unknown")
    selected_parser: str          # "sysco", "usfoods_structural", "pfg", "generic"
    confidence: float             # 0.0 – 1.0 combined confidence
    routing_reason: str           # Human-readable explanation
    signals: list = field(default_factory=list)
    gpt_confidence: str = "low"   # GPT's self-reported confidence

    def to_dict(self) -> dict:
        return {
            "detected_vendor": self.detected_vendor,
            "canonical_vendor": self.canonical_vendor,
            "selected_parser": self.selected_parser,
            "confidence": round(self.confidence, 3),
            "routing_reason": self.routing_reason,
            "gpt_confidence": self.gpt_confidence,
            "signals": [
                {"source": s.source, "vendor": s.vendor_key,
                 "score": round(s.score, 3), "detail": s.detail}
                for s in self.signals
            ],
        }


# ─────────────────────────────────────────────────────────────────────
# Signal 1 — Vendor Name Matching
# ─────────────────────────────────────────────────────────────────────

def _match_vendor_name(raw_name: str) -> list[VendorSignal]:
    """Match a raw vendor name against all known variants."""
    signals = []
    if not raw_name or raw_name.upper() == "UNKNOWN":
        return signals

    norm = raw_name.lower().strip().rstrip(".,")

    for vendor_key, cfg in VENDOR_REGISTRY.items():
        best_score = 0.0
        best_variant = ""

        for variant in cfg["name_variants"]:
            # Exact match
            if norm == variant or norm.startswith(variant):
                best_score = max(best_score, 1.0)
                best_variant = variant
            # Containment match
            elif variant in norm or norm in variant:
                best_score = max(best_score, 0.85)
                best_variant = variant

        if best_score > 0:
            signals.append(VendorSignal(
                source="name_match",
                vendor_key=vendor_key,
                score=best_score,
                detail=f"'{raw_name}' matches variant '{best_variant}' (score={best_score})",
            ))

    return signals


# ─────────────────────────────────────────────────────────────────────
# Signal 2 — Content Clue Matching
# ─────────────────────────────────────────────────────────────────────

def _match_content_clues(clues: list[str]) -> list[VendorSignal]:
    """Match GPT-reported clues against vendor fingerprints."""
    signals = []
    if not clues:
        return signals

    clue_text = " ".join(clues).lower()

    for vendor_key, cfg in VENDOR_REGISTRY.items():
        matches = []
        for pattern in cfg["content_clues"]:
            if re.search(pattern, clue_text, re.IGNORECASE):
                matches.append(pattern)

        if matches:
            # More matching patterns → higher confidence
            score = min(0.5 + 0.15 * len(matches), 1.0)
            signals.append(VendorSignal(
                source="content_clue",
                vendor_key=vendor_key,
                score=score,
                detail=f"{len(matches)} clue pattern(s) matched: {matches[:3]}",
            ))

    return signals


# ─────────────────────────────────────────────────────────────────────
# Signal 3 — Layout Keyword Matching
# ─────────────────────────────────────────────────────────────────────

def _match_layout_keywords(clues: list[str]) -> list[VendorSignal]:
    """Check for vendor-specific column header keywords in clues."""
    signals = []
    if not clues:
        return signals

    clue_text = " ".join(clues).lower()

    for vendor_key, cfg in VENDOR_REGISTRY.items():
        matches = []
        for kw in cfg["layout_keywords"]:
            if kw.lower() in clue_text:
                matches.append(kw)

        if matches:
            # Layout keywords are strong signals — US Foods has unique ones
            # (SHIPPED, EXT PRICE) that don't appear on other vendors
            unique_kws = {"shipped", "ext price", "extended price", "weight", "brand"}
            has_unique = any(m.lower() in unique_kws for m in matches)
            score = 0.3 + 0.1 * len(matches)
            if has_unique:
                score += 0.2
            score = min(score, 1.0)

            signals.append(VendorSignal(
                source="layout_keyword",
                vendor_key=vendor_key,
                score=score,
                detail=f"Layout keywords found: {matches}",
            ))

    return signals


# ─────────────────────────────────────────────────────────────────────
# Main Routing Decision
# ─────────────────────────────────────────────────────────────────────

# Signal weights
W_NAME = 0.55
W_CONTENT = 0.25
W_LAYOUT = 0.20

# Minimum confidence to route to a vendor-specific parser
ROUTING_THRESHOLD = 0.40


def resolve_vendor_routing(
    raw_vendor_name: str,
    gpt_confidence: str,
    clues: list[str],
) -> VendorRoutingResult:
    """
    Combine all signals into a routing decision.

    Returns a VendorRoutingResult with the selected parser and full audit trail.
    """
    all_signals = []

    # Collect signals
    all_signals.extend(_match_vendor_name(raw_vendor_name))
    all_signals.extend(_match_content_clues(clues))
    all_signals.extend(_match_layout_keywords(clues))

    # Aggregate per vendor: weighted combination of best signal per source
    vendor_scores: dict[str, float] = {}
    vendor_signal_details: dict[str, list[VendorSignal]] = {}

    for vendor_key in VENDOR_REGISTRY:
        vendor_signals = [s for s in all_signals if s.vendor_key == vendor_key]
        if not vendor_signals:
            continue

        vendor_signal_details[vendor_key] = vendor_signals

        # Best score per signal source
        best_by_source = {}
        for s in vendor_signals:
            if s.source not in best_by_source or s.score > best_by_source[s.source]:
                best_by_source[s.source] = s.score

        weights = {
            "name_match": W_NAME,
            "content_clue": W_CONTENT,
            "layout_keyword": W_LAYOUT,
        }

        weighted_sum = sum(
            best_by_source.get(src, 0) * w
            for src, w in weights.items()
        )

        # GPT confidence modifier
        conf_mod = {"high": 1.0, "medium": 0.85, "low": 0.7}.get(
            gpt_confidence.lower(), 0.7
        )
        # Only apply modifier to name_match signal
        if "name_match" in best_by_source:
            name_contribution = best_by_source["name_match"] * W_NAME
            adjusted_name = name_contribution * conf_mod
            weighted_sum = weighted_sum - name_contribution + adjusted_name

        vendor_scores[vendor_key] = weighted_sum

    # Pick the highest-scoring vendor
    if not vendor_scores:
        return VendorRoutingResult(
            detected_vendor=raw_vendor_name or "UNKNOWN",
            canonical_vendor="Unknown",
            selected_parser="generic",
            confidence=0.0,
            routing_reason="No vendor signals matched any known vendor",
            signals=all_signals,
            gpt_confidence=gpt_confidence,
        )

    best_vendor = max(vendor_scores, key=vendor_scores.get)
    best_score = vendor_scores[best_vendor]

    if best_score < ROUTING_THRESHOLD:
        reason = (
            f"Best match '{best_vendor}' scored {best_score:.3f} "
            f"(below threshold {ROUTING_THRESHOLD}). "
            f"Routing to generic parser."
        )
        return VendorRoutingResult(
            detected_vendor=raw_vendor_name or "UNKNOWN",
            canonical_vendor="Unknown",
            selected_parser="generic",
            confidence=best_score,
            routing_reason=reason,
            signals=all_signals,
            gpt_confidence=gpt_confidence,
        )

    cfg = VENDOR_REGISTRY[best_vendor]
    matched_signals = vendor_signal_details.get(best_vendor, [])
    signal_sources = [s.source for s in matched_signals]

    reason_parts = []
    if "name_match" in signal_sources:
        reason_parts.append("name match")
    if "content_clue" in signal_sources:
        reason_parts.append("content clues")
    if "layout_keyword" in signal_sources:
        reason_parts.append("layout signature")

    reason = (
        f"Routed to {cfg['parser']} parser — "
        f"confidence {best_score:.3f} from {' + '.join(reason_parts)}"
    )

    return VendorRoutingResult(
        detected_vendor=raw_vendor_name or "UNKNOWN",
        canonical_vendor=cfg["canonical"],
        selected_parser=cfg["parser"],
        confidence=best_score,
        routing_reason=reason,
        signals=matched_signals,
        gpt_confidence=gpt_confidence,
    )


def parse_vendor_detect_response(raw_response: str) -> tuple[str, str, list[str]]:
    """
    Parse the enhanced vendor detection GPT response.
    Returns (vendor_name, confidence, clues).
    Falls back gracefully if GPT returns plain text instead of JSON.
    """
    raw = raw_response.strip().strip('"').strip("'")

    # Try JSON parse
    import json
    try:
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            data = json.loads(json_match.group())
            vendor_name = (data.get("vendor_name") or "UNKNOWN").strip().strip('"').strip("'")
            confidence = (data.get("confidence") or "low").strip().lower()
            clues = data.get("clues") or []
            if isinstance(clues, str):
                clues = [clues]
            return vendor_name, confidence, clues
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: treat as plain vendor name (backward compat)
    vendor_name = raw.split("\n")[0].strip().strip('"').strip("'")
    if len(vendor_name) > 100:
        vendor_name = "UNKNOWN"
    return vendor_name, "low", []
