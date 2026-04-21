"""
DSS (Decision-Support System) coverage for Milestone 4 upgrade.
Validates:
  - classify_data_quality
  - compute_insight_confidence (score + level)
  - evaluate_alert suppresses Medium / Low confidence
  - build_recommendation gates actionable output by confidence
  - poor-quality records are excluded from analytics
"""
from datetime import datetime, timezone, timedelta
from services.price_intelligence import (
    classify_data_quality,
    compute_insight_confidence,
    evaluate_alert,
    build_recommendation,
    compute_trend,
    compute_stats,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    INSIGHT_WEIGHTS,
)


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _obs(price, days_ago, id_conf=0.95, unit_conf="parser", vendor="SYSCO"):
    d = _iso(days_ago)
    return {
        "price_per_unit": price,
        "observed_at": d,
        "invoice_date": d,
        "vendor_name": vendor,
        "canonical_product_id": "p1",
        "canonical_name": "Chicken",
        "canonical_unit": "lb",
        "identity_confidence": id_conf,
        "unit_confidence": unit_conf,
        "data_quality_flag": classify_data_quality(
            identity_confidence=id_conf, unit_confidence=unit_conf
        ),
    }


# ── classify_data_quality ────────────────────────────────────────────
def test_quality_good():
    assert classify_data_quality(identity_confidence=0.95, unit_confidence="parser") == "good"
    assert classify_data_quality(identity_confidence=0.90, unit_confidence="user_corrected") == "good"


def test_quality_fair():
    # legacy_parser → fair regardless of identity
    assert classify_data_quality(identity_confidence=0.95, unit_confidence="legacy_parser") == "fair"
    # identity 0.60-0.80 → fair
    assert classify_data_quality(identity_confidence=0.70, unit_confidence="parser") == "fair"


def test_quality_poor():
    # low identity
    assert classify_data_quality(identity_confidence=0.40, unit_confidence="parser") == "poor"
    # review/conflict/unknown unit
    assert classify_data_quality(identity_confidence=0.95, unit_confidence="review") == "poor"
    assert classify_data_quality(identity_confidence=0.95, unit_confidence="unknown") == "poor"


# ── compute_insight_confidence ────────────────────────────────────────
def test_confidence_high_level():
    # 6 fresh good-quality observations → high
    obs = [_obs(3.0 + i*0.05, days_ago=3 + i) for i in range(6)]
    c = compute_insight_confidence(obs)
    assert c["score"] >= HIGH_CONFIDENCE_THRESHOLD
    assert c["level"] == "high"
    # weights present
    assert c["weights"] == INSIGHT_WEIGHTS


def test_confidence_medium_level():
    # 4 observations but 120 days old → should drop to medium
    obs = [_obs(3.0, days_ago=120 + i*5) for i in range(4)]
    c = compute_insight_confidence(obs)
    assert MEDIUM_CONFIDENCE_THRESHOLD <= c["score"] < HIGH_CONFIDENCE_THRESHOLD
    assert c["level"] == "medium"


def test_confidence_low_level():
    # A single, old, mid-identity observation → low
    obs = [_obs(3.0, days_ago=200, id_conf=0.65)]
    c = compute_insight_confidence(obs)
    assert c["score"] < MEDIUM_CONFIDENCE_THRESHOLD
    assert c["level"] == "low"


def test_confidence_components_returned():
    obs = [_obs(3.0 + i*0.05, days_ago=3 + i) for i in range(6)]
    c = compute_insight_confidence(obs)
    for key in ("recency", "observations", "identity", "unit"):
        assert key in c["components"]
        assert 0.0 <= c["components"][key] <= 1.0


# ── evaluate_alert: DSS suppression rules ─────────────────────────────
def test_alert_fires_only_on_high_confidence():
    # Big spike (+26%) but stale (120 days) → medium confidence → suppressed
    obs = (
        [_obs(3.0, days_ago=120 + i*5) for i in range(3)]
        + [_obs(3.8, days_ago=100)]
    )
    assert evaluate_alert(obs) is None


def test_alert_fires_when_high_confidence_and_spike():
    # Spike with 6 fresh high-quality records → alert
    base = [_obs(3.0, days_ago=3 + i) for i in range(5)]
    base.append(_obs(3.8, days_ago=1))  # +26% vs prior avg 3.0
    a = evaluate_alert(base)
    assert a is not None
    assert a["confidence"]["level"] == "high"
    assert "probabilistic" not in a["message"].lower()  # uses "High likelihood" wording
    assert "likelihood" in a["message"].lower()


# ── evaluate_alert: poor-quality records excluded ─────────────────────
def test_poor_records_excluded_from_analytics():
    # 3 poor records + 1 good spike — poor records must be filtered before
    # the alert calculation.
    records = (
        [_obs(3.0, days_ago=5, id_conf=0.40, unit_conf="parser") for _ in range(3)]
        + [_obs(6.0, days_ago=2)]
    )
    # Only 1 good observation → alert suppressed due to insufficient high-conf count
    assert evaluate_alert(records) is None


def test_good_vs_poor_stats_differ():
    records = (
        [_obs(3.0, days_ago=5) for _ in range(3)]  # good
        + [_obs(100.0, days_ago=2, id_conf=0.3)]  # poor — should be excluded
    )
    stats = compute_stats(records)
    assert stats["max"] == 3.0  # poor record excluded


# ── build_recommendation: guardrails ──────────────────────────────────
def test_recommendation_high_actionable():
    obs = [_obs(3.0 + i*0.05, days_ago=3 + i) for i in range(6)]
    conf = compute_insight_confidence(obs)
    trend = compute_trend(obs)
    rec = build_recommendation(trend=trend, alert=None, confidence=conf)
    assert conf["level"] == "high"
    assert rec["actionable"] is True
    assert rec["action"] is not None
    assert "review_suggested" not in rec["tags"]


def test_recommendation_medium_review_suggested():
    obs = [_obs(3.0, days_ago=120 + i*5) for i in range(4)]
    conf = compute_insight_confidence(obs)
    trend = compute_trend(obs)
    rec = build_recommendation(trend=trend, alert=None, confidence=conf)
    assert conf["level"] == "medium"
    assert rec["actionable"] is False
    assert "review_suggested" in rec["tags"]
    assert rec["action"] is None


def test_recommendation_low_raw_only():
    obs = [_obs(3.0, days_ago=200, id_conf=0.65)]
    conf = compute_insight_confidence(obs)
    trend = compute_trend(obs)
    rec = build_recommendation(trend=trend, alert=None, confidence=conf)
    assert conf["level"] == "low"
    assert rec["actionable"] is False
    assert rec["action"] is None
    assert "raw" in rec["label"].lower()


def test_recommendation_high_with_alert_uses_probabilistic_language():
    base = [_obs(3.0, days_ago=3 + i) for i in range(5)]
    base.append(_obs(3.8, days_ago=1))
    conf = compute_insight_confidence(base)
    trend = compute_trend(base)
    alert = evaluate_alert(base)
    rec = build_recommendation(trend=trend, alert=alert, confidence=conf)
    assert rec["actionable"] is True
    assert rec["action"] in ("renegotiate", "investigate", "switch_vendor")
    # Probabilistic wording, not imperative
    assert "overpaying" not in rec["detail"].lower()
    assert "likelihood" in rec["detail"].lower() or "above" in rec["detail"].lower()


def test_recommendation_high_switch_vendor():
    obs = [_obs(3.0 + i*0.05, days_ago=3 + i, vendor="SYSCO") for i in range(3)]
    obs += [_obs(2.5, days_ago=2, vendor="CHEAPCO")]
    obs += [_obs(3.2, days_ago=1, vendor="SYSCO")]
    obs += [_obs(2.6, days_ago=0, vendor="CHEAPCO")]
    conf = compute_insight_confidence(obs)
    trend = compute_trend(obs)
    vendor_data = {"best_vendor": "CHEAPCO", "worst_vendor": "SYSCO", "savings_pct": 18.0}
    rec = build_recommendation(trend=trend, alert=None, confidence=conf, vendor_data=vendor_data)
    if conf["level"] == "high":
        assert rec["action"] == "switch_vendor"
        assert "CHEAPCO" in rec["headline"]
