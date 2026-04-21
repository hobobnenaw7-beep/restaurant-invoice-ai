"""
Milestone 5 — Procurement Decision Engine
==========================================
Converts high-confidence pricing insights into structured, decision-ready
procurement recommendations with explicit evidence, uncertainty and risk.

This is a DECISION-SUPPORT layer — it never executes purchases; it only
surfaces recommended actions with probabilistic language and guardrails.

Decision flow
-------------
    ┌────────────────────────────────────────────────────────────────┐
    │ 1. GUARDRAILS (fail-closed, default → monitor_only)            │
    │   * insight confidence level == "high"                         │
    │   * insight confidence score >= 0.80                           │
    │   * observation_count (good-quality only) >= 3                 │
    │   * per-record identity_confidence >= 0.80                     │
    │   * per-record unit_confidence ∈ high-trust set                │
    └──────────────────────────────┬─────────────────────────────────┘
                                   │
                                   ▼
    ┌────────────────────────────────────────────────────────────────┐
    │ 2. SIGNALS (compute deltas — all in the same canonical_unit)   │
    │   * delta_vs_avg       = (current - hist_avg) / hist_avg       │
    │   * delta_vs_target    = (current - target) / target (if any)  │
    │   * delta_vs_alt       = (current - best_alt) / current        │
    │   * alt_evidence_depth = # of good obs for alternative vendor  │
    └──────────────────────────────┬─────────────────────────────────┘
                                   │
                                   ▼
    ┌────────────────────────────────────────────────────────────────┐
    │ 3. RULES (first match wins)                                    │
    │   a) strong cheaper alternative (delta_vs_alt >= SWITCH_PCT    │
    │      AND alt_evidence_depth >= 2 AND alt vendor in ≥ last N    │
    │      observations) ............................ SWITCH_VENDOR  │
    │   b) above MA or above target beyond tolerance                 │
    │      ............................................ RENEGOTIATE │
    │   c) within tolerance ............................. NO_ACTION │
    │   d) fallback ................................... MONITOR_ONLY │
    └──────────────────────────────┬─────────────────────────────────┘
                                   │
                                   ▼
    ┌────────────────────────────────────────────────────────────────┐
    │ 4. RISK + DECISION_CONFIDENCE                                  │
    │   risk_level = f(observation_depth, alt_evidence_depth, unit   │
    │                  quality mix, target presence)                 │
    │   decision_confidence ∈ [0,1] = insight_score * evidence_scale │
    └────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import db
from services.price_intelligence import (
    compute_insight_confidence,
    compute_stats,
    compute_trend,
    evaluate_alert,
    _analytic_observations,
    _sort_observations,
    _vendor_comparison_from_obs,
    HIGH_CONFIDENCE_THRESHOLD,
    HIGH_IDENTITY_CONFIDENCE,
    MIN_OBSERVATIONS_FOR_ALERT,
)

logger = logging.getLogger("restaurant_ai")

# ── Decision thresholds ────────────────────────────────────────────────
SWITCH_VENDOR_PCT = 5.0           # alt must be ≥5% cheaper than current
SWITCH_MIN_ALT_OBS = 2            # alt needs ≥2 good observations
RENEGOTIATE_MA_PCT = 10.0         # current ≥10% above historical MA
RENEGOTIATE_TARGET_PCT = 5.0      # current ≥5% above target price
NO_ACTION_TOLERANCE_PCT = 3.0     # within ±3% of reference = "no_action"
ALT_RECENCY_WINDOW = 6            # alt must appear in last N observations

# Allowed recommendation types
REC_SWITCH_VENDOR = "switch_vendor"
REC_RENEGOTIATE = "renegotiate"
REC_MONITOR_ONLY = "monitor_only"
REC_NO_ACTION = "no_action"

# Unit-quality labels that count as "high trust"
_HIGH_TRUST_UNITS = {"parser", "user_corrected", "memory:user_corrected", "auto"}


# ──────────────────────────────────────────────────────────────────────
# Main entrypoint
# ──────────────────────────────────────────────────────────────────────
def build_procurement_decision(
    *,
    canonical_product_id: str,
    canonical_name: str,
    canonical_unit: str,
    observations: list[dict],
    target_price_per_unit: Optional[float] = None,
    category: str = "",
) -> dict:
    """
    Build a structured procurement recommendation.

    Arguments
        observations: raw list of price_history docs (mixed quality is fine —
                      filtering happens internally).
        target_price_per_unit: optional user-defined target (same canonical_unit).

    Returns a `ProcurementDecision` dict (see module docstring for shape).
    """
    good = _analytic_observations(observations)
    good = _sort_observations(good)
    good_count = len(good)

    confidence = compute_insight_confidence(observations)
    stats = compute_stats(observations)
    trend = compute_trend(observations)
    alert = evaluate_alert(observations)
    vendor_comp = _vendor_comparison_from_obs(observations)

    latest_obs = good[-1] if good else None
    current_vendor = (latest_obs or {}).get("vendor_name") or ""
    current_price = float((latest_obs or {}).get("price_per_unit") or 0) or None
    hist_avg = stats.get("avg")

    # ── Signals ───────────────────────────────────────────────────────
    delta_vs_avg = _pct_delta(current_price, hist_avg)
    delta_vs_target = _pct_delta(current_price, target_price_per_unit)

    best_alt = _find_best_alternative(vendor_comp.get("vendors") or [], current_vendor)
    alt_evidence_depth = (best_alt or {}).get("observations", 0)
    alt_price = (best_alt or {}).get("latest_price")
    delta_vs_alt = (
        round((current_price - alt_price) / current_price * 100, 2)
        if current_price and alt_price and current_price > 0
        else None
    )

    # Does the alternative vendor appear recently enough to be actionable?
    alt_recent = _alt_is_recent(
        good, (best_alt or {}).get("vendor") or "", current_vendor, window=ALT_RECENCY_WINDOW
    )

    # ── Guardrails ────────────────────────────────────────────────────
    guardrail_failures = _evaluate_guardrails(
        observations=observations,
        confidence=confidence,
        good_count=good_count,
    )

    # ── Rule selection ────────────────────────────────────────────────
    if guardrail_failures:
        rec_type = REC_MONITOR_ONLY
    elif (
        delta_vs_alt is not None
        and delta_vs_alt >= SWITCH_VENDOR_PCT
        and alt_evidence_depth >= SWITCH_MIN_ALT_OBS
        and alt_recent
    ):
        rec_type = REC_SWITCH_VENDOR
    elif (
        (delta_vs_avg is not None and delta_vs_avg >= RENEGOTIATE_MA_PCT)
        or (target_price_per_unit and delta_vs_target is not None and delta_vs_target >= RENEGOTIATE_TARGET_PCT)
    ):
        rec_type = REC_RENEGOTIATE
    elif delta_vs_avg is not None and abs(delta_vs_avg) <= NO_ACTION_TOLERANCE_PCT:
        rec_type = REC_NO_ACTION
    else:
        # Ambiguous zone — soft signals, not enough for a strong action
        rec_type = REC_MONITOR_ONLY

    # ── Risk + decision confidence ────────────────────────────────────
    risk_level = _risk_level(
        rec_type=rec_type,
        good_count=good_count,
        alt_evidence_depth=alt_evidence_depth,
        observations=good,
        has_target=target_price_per_unit is not None,
    )
    decision_confidence = _decision_confidence(
        insight_score=confidence["score"],
        rec_type=rec_type,
        alt_evidence_depth=alt_evidence_depth,
    )

    # ── Evidence + uncertainty + reason ───────────────────────────────
    evidence = _evidence_bullets(
        rec_type=rec_type,
        current_vendor=current_vendor,
        current_price=current_price,
        canonical_unit=canonical_unit,
        hist_avg=hist_avg,
        delta_vs_avg=delta_vs_avg,
        target_price=target_price_per_unit,
        delta_vs_target=delta_vs_target,
        best_alt=best_alt,
        delta_vs_alt=delta_vs_alt,
        good_count=good_count,
        trend=trend,
    )
    uncertainty = _uncertainty_bullets(
        rec_type=rec_type,
        good_count=good_count,
        alt_evidence_depth=alt_evidence_depth,
        confidence=confidence,
        guardrail_failures=guardrail_failures,
        has_target=target_price_per_unit is not None,
    )
    reason_summary = _reason_summary(
        rec_type=rec_type,
        canonical_name=canonical_name,
        current_vendor=current_vendor,
        best_alt=best_alt,
        delta_vs_avg=delta_vs_avg,
        delta_vs_alt=delta_vs_alt,
        delta_vs_target=delta_vs_target,
        guardrail_failures=guardrail_failures,
    )

    status = "actionable" if rec_type in (REC_SWITCH_VENDOR, REC_RENEGOTIATE) else \
             "informational" if rec_type == REC_NO_ACTION else "advisory"

    return {
        "canonical_product_id": canonical_product_id,
        "canonical_name": canonical_name,
        "canonical_unit": canonical_unit,
        "category": category,
        "recommendation_type": rec_type,
        "decision_confidence": decision_confidence,
        "confidence_level": confidence["level"],
        "insight_confidence": confidence,
        "risk_level": risk_level,
        "reason_summary": reason_summary,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "current_vendor": current_vendor,
        "current_price_per_unit": current_price,
        "target_price_per_unit": target_price_per_unit,
        "historical_average_price_per_unit": hist_avg,
        "best_alternative_vendor": (best_alt or {}).get("vendor"),
        "best_alternative_price_per_unit": (best_alt or {}).get("latest_price"),
        "best_alternative_observations": alt_evidence_depth,
        "price_delta_vs_avg_pct": delta_vs_avg,
        "price_delta_vs_target_pct": delta_vs_target,
        "price_delta_vs_alternative_pct": delta_vs_alt,
        "observation_count": good_count,
        "alert": alert,
        "trend": trend,
        "status": status,
        "guardrails_passed": len(guardrail_failures) == 0,
        "guardrail_failures": guardrail_failures,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _pct_delta(current: Optional[float], reference: Optional[float]) -> Optional[float]:
    if current is None or reference is None or reference <= 0:
        return None
    return round((current - reference) / reference * 100, 2)


def _find_best_alternative(vendors: list[dict], current_vendor: str) -> Optional[dict]:
    """Cheapest vendor (by latest_price) that is NOT the current vendor."""
    alts = [v for v in vendors if v.get("vendor") and v["vendor"] != current_vendor]
    if not alts:
        return None
    return min(alts, key=lambda v: v.get("latest_price") or float("inf"))


def _alt_is_recent(good_obs: list[dict], alt_vendor: str, current_vendor: str, window: int) -> bool:
    """The alternative vendor must appear in the most recent `window` observations."""
    if not alt_vendor:
        return False
    tail = good_obs[-window:] if good_obs else []
    return any((o.get("vendor_name") or "") == alt_vendor for o in tail)


def _evaluate_guardrails(*, observations: list[dict], confidence: dict, good_count: int) -> list[str]:
    """Return a list of failure reason codes. Empty list means all guardrails pass."""
    failures: list[str] = []
    if good_count < MIN_OBSERVATIONS_FOR_ALERT:
        failures.append("insufficient_observations")
    if confidence.get("level") != "high":
        failures.append("insight_confidence_not_high")
    if float(confidence.get("score") or 0) < HIGH_CONFIDENCE_THRESHOLD:
        failures.append("insight_score_below_threshold")

    # Per-record identity + unit quality checks (mean across good-quality only)
    good = _analytic_observations(observations)
    if good:
        mean_id = sum(float(o.get("identity_confidence") or 0) for o in good) / len(good)
        if mean_id < HIGH_IDENTITY_CONFIDENCE:
            failures.append("identity_confidence_weak")
        low_unit = [
            o for o in good
            if (o.get("unit_confidence") or "").lower() not in _HIGH_TRUST_UNITS
        ]
        # If more than half of good obs have low-trust unit labels, fail
        if len(low_unit) > len(good) / 2:
            failures.append("unit_confidence_weak")
    else:
        failures.append("no_good_observations")
    return failures


def _risk_level(
    *,
    rec_type: str,
    good_count: int,
    alt_evidence_depth: int,
    observations: list[dict],
    has_target: bool,
) -> str:
    """
    Risk for the buyer in ACTING on this recommendation.
      low    — lots of evidence, consistent story
      medium — thin evidence for the specific signal (especially alt-vendor)
      high   — any advisory case or any recommendation with only 3 obs
    """
    if rec_type == REC_MONITOR_ONLY:
        return "high"  # acting on monitor_only is inherently risky
    if rec_type == REC_NO_ACTION:
        return "low"

    # Actionable recommendations — rate by evidence depth
    if rec_type == REC_SWITCH_VENDOR:
        if alt_evidence_depth >= 5 and good_count >= 6:
            return "low"
        if alt_evidence_depth >= 3 and good_count >= 4:
            return "medium"
        return "high"
    if rec_type == REC_RENEGOTIATE:
        if good_count >= 6 and has_target:
            return "low"
        if good_count >= 4:
            return "medium"
        return "high"
    return "medium"


def _decision_confidence(*, insight_score: float, rec_type: str, alt_evidence_depth: int) -> float:
    """A [0,1] score for how confident we are in the RECOMMENDATION itself."""
    if rec_type == REC_MONITOR_ONLY:
        return round(min(0.50, insight_score), 4)
    if rec_type == REC_NO_ACTION:
        return round(insight_score, 4)
    # Actionable — derate if alt evidence is thin
    scale = 1.0
    if rec_type == REC_SWITCH_VENDOR:
        if alt_evidence_depth < 3:
            scale = 0.85
        if alt_evidence_depth < 2:
            scale = 0.70
    return round(min(1.0, insight_score * scale), 4)


def _evidence_bullets(
    *,
    rec_type: str,
    current_vendor: str,
    current_price: Optional[float],
    canonical_unit: str,
    hist_avg: Optional[float],
    delta_vs_avg: Optional[float],
    target_price: Optional[float],
    delta_vs_target: Optional[float],
    best_alt: Optional[dict],
    delta_vs_alt: Optional[float],
    good_count: int,
    trend: dict,
) -> list[str]:
    bullets: list[str] = []
    if current_vendor and current_price:
        bullets.append(
            f"{current_vendor} currently at ${current_price:.2f}/{canonical_unit}."
        )
    if hist_avg and delta_vs_avg is not None:
        direction = "above" if delta_vs_avg > 0 else "below"
        bullets.append(
            f"{abs(delta_vs_avg):.1f}% {direction} your own recent average of "
            f"${hist_avg:.2f}/{canonical_unit} across {good_count} observation(s)."
        )
    if target_price and delta_vs_target is not None:
        direction = "above" if delta_vs_target > 0 else "below"
        bullets.append(
            f"{abs(delta_vs_target):.1f}% {direction} the target price of "
            f"${target_price:.2f}/{canonical_unit}."
        )
    if best_alt and delta_vs_alt is not None and rec_type in (REC_SWITCH_VENDOR, REC_RENEGOTIATE):
        bullets.append(
            f"Alternative vendor {best_alt['vendor']} has been ${best_alt['latest_price']:.2f}/"
            f"{canonical_unit} ({delta_vs_alt:.1f}% cheaper than {current_vendor or 'current'}) "
            f"across {best_alt['observations']} recent observation(s)."
        )
    if trend.get("trend") in ("up", "down"):
        arrow = "upward" if trend["trend"] == "up" else "downward"
        bullets.append(
            f"Moving-average trend is {arrow} by {trend.get('change_pct')}% vs prior window."
        )
    return bullets


def _uncertainty_bullets(
    *,
    rec_type: str,
    good_count: int,
    alt_evidence_depth: int,
    confidence: dict,
    guardrail_failures: list[str],
    has_target: bool,
) -> list[str]:
    bullets: list[str] = []
    if "insufficient_observations" in guardrail_failures:
        bullets.append(f"Only {good_count} good-quality observation(s) available — minimum is 3.")
    if "insight_confidence_not_high" in guardrail_failures:
        bullets.append(
            f"Overall insight confidence is {confidence.get('level')} (score "
            f"{confidence.get('score')}) — threshold is ≥ 0.80."
        )
    if "identity_confidence_weak" in guardrail_failures:
        bullets.append("Product identity match is not strong enough to act on.")
    if "unit_confidence_weak" in guardrail_failures:
        bullets.append("Unit normalization quality is mixed for this product.")

    # Rec-specific uncertainty
    if rec_type == REC_SWITCH_VENDOR and alt_evidence_depth < 5:
        bullets.append(
            f"Alternative-vendor comparison is based on only {alt_evidence_depth} "
            "observation(s); prices may vary on future orders."
        )
    if rec_type == REC_RENEGOTIATE and not has_target:
        bullets.append("No target price is set — comparison is vs your own historical average only.")
    if rec_type == REC_RENEGOTIATE and alt_evidence_depth == 0:
        bullets.append("No alternative vendor data for this product — renegotiation leverage is limited.")
    if rec_type == REC_MONITOR_ONLY and not guardrail_failures:
        bullets.append("Price signals are ambiguous; continuing to collect data is the safest path.")
    return bullets


def _reason_summary(
    *,
    rec_type: str,
    canonical_name: str,
    current_vendor: str,
    best_alt: Optional[dict],
    delta_vs_avg: Optional[float],
    delta_vs_alt: Optional[float],
    delta_vs_target: Optional[float],
    guardrail_failures: list[str],
) -> str:
    if rec_type == REC_SWITCH_VENDOR and best_alt:
        return (
            f"High likelihood of savings by switching {canonical_name} from "
            f"{current_vendor or 'current vendor'} to {best_alt['vendor']} "
            f"(~{delta_vs_alt:.1f}% lower across {best_alt['observations']} observations)."
        )
    if rec_type == REC_RENEGOTIATE:
        parts = []
        if delta_vs_avg is not None and delta_vs_avg > 0:
            parts.append(f"{delta_vs_avg:.1f}% above recent average")
        if delta_vs_target is not None and delta_vs_target > 0:
            parts.append(f"{delta_vs_target:.1f}% above target")
        where = " and ".join(parts) if parts else "above typical"
        return (
            f"High likelihood you are paying more than recent typical for {canonical_name} "
            f"({where}) with no strong alternative vendor available — renegotiation suggested."
        )
    if rec_type == REC_NO_ACTION:
        return f"{canonical_name} is within your recent typical pricing — no action suggested."
    if rec_type == REC_MONITOR_ONLY:
        if guardrail_failures:
            return (
                f"Not enough reliable evidence to recommend a specific action on "
                f"{canonical_name} — continue to monitor."
            )
        return (
            f"Pricing signals for {canonical_name} are ambiguous — continue monitoring "
            "and revisit once more data is available."
        )
    return f"No recommendation generated for {canonical_name}."


# ──────────────────────────────────────────────────────────────────────
# DB-backed aggregations (consumed by the API layer)
# ──────────────────────────────────────────────────────────────────────
async def recommendations_for_restaurant(
    restaurant_id: str, *, only_actionable: bool = False
) -> list[dict]:
    """Build decisions for every (canonical_product, canonical_unit) bucket."""
    obs_by_key: dict[tuple, list[dict]] = {}
    async for o in db.price_history.find({"restaurant_id": restaurant_id}, {"_id": 0}):
        key = (o["canonical_product_id"], o.get("canonical_unit") or "")
        obs_by_key.setdefault(key, []).append(o)

    # Load canonical products once (for names, category, target prices)
    pids = [k[0] for k in obs_by_key.keys()]
    cp_map: dict[str, dict] = {}
    if pids:
        async for cp in db.canonical_products.find(
            {"id": {"$in": pids}, "restaurant_id": restaurant_id}, {"_id": 0}
        ):
            cp_map[cp["id"]] = cp

    out: list[dict] = []
    for (cpid, unit), obs in obs_by_key.items():
        cp = cp_map.get(cpid, {})
        target = None
        # Accept target on matching canonical_unit only
        t_unit = cp.get("target_unit") or cp.get("canonical_unit")
        if cp.get("target_price_per_unit") and (not t_unit or t_unit == unit):
            try:
                target = float(cp["target_price_per_unit"])
            except (TypeError, ValueError):
                target = None

        decision = build_procurement_decision(
            canonical_product_id=cpid,
            canonical_name=cp.get("canonical_name") or (obs[-1].get("canonical_name") if obs else ""),
            canonical_unit=unit,
            observations=obs,
            target_price_per_unit=target,
            category=cp.get("category", ""),
        )
        if only_actionable and decision["recommendation_type"] not in (REC_SWITCH_VENDOR, REC_RENEGOTIATE):
            continue
        # Safety rule: summary/inline views must only show high-confidence actionable
        if only_actionable and decision["confidence_level"] != "high":
            continue
        out.append(decision)

    # Sort: actionable first, then high decision_confidence first
    order = {REC_SWITCH_VENDOR: 0, REC_RENEGOTIATE: 1, REC_NO_ACTION: 2, REC_MONITOR_ONLY: 3}
    out.sort(key=lambda d: (
        order.get(d["recommendation_type"], 99),
        -float(d.get("decision_confidence") or 0),
        d.get("canonical_name", ""),
    ))
    return out


async def recommendation_for_product(
    restaurant_id: str, canonical_product_id: str, canonical_unit: str = ""
) -> Optional[dict]:
    """Single-product decision with optional unit filter."""
    query: dict[str, Any] = {
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
    }
    if canonical_unit:
        query["canonical_unit"] = canonical_unit

    obs = await db.price_history.find(query, {"_id": 0}).to_list(5000)
    if not obs:
        return None
    if not canonical_unit:
        counts: dict[str, int] = {}
        for o in obs:
            counts[o.get("canonical_unit") or ""] = counts.get(o.get("canonical_unit") or "", 0) + 1
        canonical_unit = max(counts, key=counts.get)
        obs = [o for o in obs if (o.get("canonical_unit") or "") == canonical_unit]

    cp = await db.canonical_products.find_one(
        {"id": canonical_product_id, "restaurant_id": restaurant_id}, {"_id": 0}
    ) or {}
    target = None
    t_unit = cp.get("target_unit") or cp.get("canonical_unit")
    if cp.get("target_price_per_unit") and (not t_unit or t_unit == canonical_unit):
        try:
            target = float(cp["target_price_per_unit"])
        except (TypeError, ValueError):
            target = None

    return build_procurement_decision(
        canonical_product_id=canonical_product_id,
        canonical_name=cp.get("canonical_name") or (obs[-1].get("canonical_name") if obs else ""),
        canonical_unit=canonical_unit,
        observations=obs,
        target_price_per_unit=target,
        category=cp.get("category", ""),
    )


async def set_target_price(
    restaurant_id: str,
    canonical_product_id: str,
    *,
    target_price_per_unit: Optional[float],
    canonical_unit: Optional[str],
) -> dict:
    """Set/clear a target price on a canonical product."""
    cp = await db.canonical_products.find_one(
        {"id": canonical_product_id, "restaurant_id": restaurant_id}, {"_id": 0}
    )
    if not cp:
        raise KeyError("canonical_product_not_found")

    update_doc: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if target_price_per_unit is None:
        update_doc["target_price_per_unit"] = None
        update_doc["target_unit"] = None
    else:
        tp = float(target_price_per_unit)
        if tp <= 0:
            raise ValueError("target_price_must_be_positive")
        update_doc["target_price_per_unit"] = round(tp, 4)
        update_doc["target_unit"] = (canonical_unit or "").strip() or None

    await db.canonical_products.update_one(
        {"id": canonical_product_id, "restaurant_id": restaurant_id},
        {"$set": update_doc},
    )
    return {
        "canonical_product_id": canonical_product_id,
        "target_price_per_unit": update_doc["target_price_per_unit"],
        "target_unit": update_doc["target_unit"],
    }
