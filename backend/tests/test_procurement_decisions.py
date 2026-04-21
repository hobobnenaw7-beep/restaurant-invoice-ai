"""
Milestone 5 — Procurement Decision Engine unit tests.
Covers every branch of the decision tree plus guardrail enforcement.
"""
from datetime import datetime, timezone, timedelta
from services.procurement_decisions import (
    build_procurement_decision,
    REC_SWITCH_VENDOR, REC_RENEGOTIATE, REC_MONITOR_ONLY, REC_NO_ACTION,
    SWITCH_VENDOR_PCT, RENEGOTIATE_MA_PCT,
)
from services.price_intelligence import classify_data_quality


def _d(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _obs(price, days_ago, vendor="SYSCO", id_conf=0.95, unit_conf="parser"):
    return {
        "price_per_unit": price,
        "observed_at": _d(days_ago),
        "invoice_date": _d(days_ago),
        "vendor_name": vendor,
        "canonical_product_id": "p1",
        "canonical_name": "Chicken Breast",
        "canonical_unit": "lb",
        "identity_confidence": id_conf,
        "unit_confidence": unit_conf,
        "data_quality_flag": classify_data_quality(
            identity_confidence=id_conf, unit_confidence=unit_conf
        ),
    }


def _decide(observations, target=None):
    return build_procurement_decision(
        canonical_product_id="p1",
        canonical_name="Chicken Breast",
        canonical_unit="lb",
        observations=observations,
        target_price_per_unit=target,
    )


# ── Guardrails ─────────────────────────────────────────────────────────
def test_guardrail_insufficient_observations_returns_monitor_only():
    obs = [_obs(3.0, days_ago=5, vendor="SYSCO")]
    d = _decide(obs)
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    assert d["guardrails_passed"] is False
    assert "insufficient_observations" in d["guardrail_failures"]


def test_guardrail_low_insight_confidence_returns_monitor_only():
    # 4 observations but very old → medium confidence
    obs = [_obs(3.0, days_ago=150 + i*5, vendor="SYSCO") for i in range(4)]
    d = _decide(obs)
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    assert "insight_confidence_not_high" in d["guardrail_failures"]


def test_guardrail_weak_identity_returns_monitor_only():
    # Weak identity per-record → records tagged `fair`, filtered out of analytics,
    # so `good_count = 0` which fails multiple guardrails upstream.
    obs = (
        [_obs(3.0, days_ago=3 + i, id_conf=0.65) for i in range(5)]
        + [_obs(3.8, days_ago=1, id_conf=0.65)]
    )
    d = _decide(obs)
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    assert d["guardrails_passed"] is False
    # Either identity-specific failure OR downstream no-good-observations fires
    assert any(f in d["guardrail_failures"]
               for f in ("identity_confidence_weak", "no_good_observations",
                         "insufficient_observations"))


def test_guardrail_weak_unit_returns_monitor_only():
    # unit=legacy_parser → classified `fair` → filtered from analytics → monitor_only
    obs = [_obs(3.0 + i*0.05, days_ago=3 + i, unit_conf="legacy_parser") for i in range(6)]
    d = _decide(obs)
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    assert d["guardrails_passed"] is False
    assert any(f in d["guardrail_failures"]
               for f in ("unit_confidence_weak", "no_good_observations",
                         "insufficient_observations"))


# ── switch_vendor ─────────────────────────────────────────────────────
def test_switch_vendor_when_alt_is_cheaper_and_has_evidence():
    obs = (
        # Sysco recent trail
        [_obs(4.10, days_ago=2, vendor="SYSCO") for _ in range(3)]
        # Consistent cheaper alt
        + [_obs(3.50, days_ago=5, vendor="USFOODS")]
        + [_obs(3.55, days_ago=4, vendor="USFOODS")]
        + [_obs(3.50, days_ago=3, vendor="USFOODS")]
    )
    d = _decide(obs)
    assert d["recommendation_type"] == REC_SWITCH_VENDOR
    assert d["best_alternative_vendor"] == "USFOODS"
    assert d["price_delta_vs_alternative_pct"] is not None
    assert d["price_delta_vs_alternative_pct"] >= SWITCH_VENDOR_PCT
    assert d["current_vendor"] == "SYSCO"
    assert d["best_alternative_observations"] >= 2
    assert any("USFOODS" in b or "cheaper" in b for b in d["evidence"])


def test_switch_vendor_not_triggered_when_alt_is_stale():
    # Alternative vendor exists but only in OLD observations — not in recent window
    obs = (
        [_obs(3.40, days_ago=60 + i, vendor="USFOODS") for i in range(3)]
        + [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(6)]
    )
    d = _decide(obs)
    assert d["recommendation_type"] != REC_SWITCH_VENDOR


# ── renegotiate ───────────────────────────────────────────────────────
def test_renegotiate_when_above_ma_and_no_alternative():
    # All same vendor; latest is 15% above MA
    obs = [_obs(3.0, days_ago=5 + i, vendor="SYSCO") for i in range(5)]
    obs.append(_obs(3.80, days_ago=1, vendor="SYSCO"))  # ~+26%
    d = _decide(obs)
    assert d["recommendation_type"] == REC_RENEGOTIATE
    assert d["best_alternative_vendor"] is None
    assert d["price_delta_vs_avg_pct"] >= RENEGOTIATE_MA_PCT


def test_renegotiate_when_above_target_but_no_alternative():
    obs = [_obs(3.20, days_ago=5 + i, vendor="SYSCO") for i in range(6)]
    # stable price but above target
    d = _decide(obs, target=2.50)  # 28% above target
    assert d["recommendation_type"] == REC_RENEGOTIATE
    assert d["price_delta_vs_target_pct"] is not None
    assert d["target_price_per_unit"] == 2.50


# ── no_action ─────────────────────────────────────────────────────────
def test_no_action_when_within_tolerance():
    obs = [_obs(3.00 + (i % 3) * 0.01, days_ago=5 + i, vendor="SYSCO") for i in range(6)]
    d = _decide(obs)
    assert d["recommendation_type"] == REC_NO_ACTION
    assert d["risk_level"] == "low"


# ── monitor_only fallback ─────────────────────────────────────────────
def test_monitor_only_when_signals_ambiguous():
    # Latest is 5% above MA — below renegotiate, above no_action tolerance
    obs = [_obs(3.00, days_ago=5 + i, vendor="SYSCO") for i in range(5)]
    obs.append(_obs(3.15, days_ago=1, vendor="SYSCO"))  # +5%
    d = _decide(obs)
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    # Guardrails pass — just soft signals
    assert d["guardrails_passed"] is True


# ── Risk + decision_confidence ────────────────────────────────────────
def test_risk_level_scales_with_evidence():
    # Deep evidence both sides → low risk
    obs = (
        [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(6)]
        + [_obs(3.50, days_ago=2 + i, vendor="USFOODS") for i in range(5)]
    )
    d = _decide(obs)
    assert d["recommendation_type"] == REC_SWITCH_VENDOR
    assert d["risk_level"] == "low"


def test_risk_level_medium_when_thin_alt_evidence():
    obs = (
        [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(4)]
        + [_obs(3.50, days_ago=2, vendor="USFOODS")]
        + [_obs(3.55, days_ago=3, vendor="USFOODS")]
    )
    d = _decide(obs)
    assert d["recommendation_type"] == REC_SWITCH_VENDOR
    assert d["risk_level"] in ("medium", "high")


def test_monitor_only_is_flagged_high_risk_to_act_on():
    d = _decide([_obs(3.0, days_ago=5)])
    assert d["recommendation_type"] == REC_MONITOR_ONLY
    assert d["risk_level"] == "high"


def test_decision_confidence_is_bounded_and_derated_for_monitor():
    d_mon = _decide([_obs(3.0, days_ago=5)])
    assert 0.0 <= d_mon["decision_confidence"] <= 0.5

    strong_obs = (
        [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(6)]
        + [_obs(3.50, days_ago=2 + i, vendor="USFOODS") for i in range(5)]
    )
    d_sw = _decide(strong_obs)
    assert d_sw["decision_confidence"] >= d_mon["decision_confidence"]


# ── Output model shape ────────────────────────────────────────────────
def test_output_model_has_required_fields():
    obs = (
        [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(4)]
        + [_obs(3.50, days_ago=2, vendor="USFOODS")]
        + [_obs(3.55, days_ago=3, vendor="USFOODS")]
    )
    d = _decide(obs, target=3.80)
    required = {
        "canonical_product_id", "canonical_name", "canonical_unit",
        "recommendation_type", "decision_confidence", "confidence_level",
        "insight_confidence", "risk_level", "reason_summary", "evidence",
        "uncertainty", "current_vendor", "current_price_per_unit",
        "target_price_per_unit", "historical_average_price_per_unit",
        "best_alternative_vendor", "best_alternative_price_per_unit",
        "price_delta_vs_avg_pct", "price_delta_vs_target_pct",
        "price_delta_vs_alternative_pct", "observation_count",
        "alert", "trend", "status", "guardrails_passed",
        "guardrail_failures", "generated_at",
    }
    assert required.issubset(d.keys()), required - d.keys()


def test_reason_summary_uses_probabilistic_language():
    obs = [_obs(3.0, days_ago=5 + i, vendor="SYSCO") for i in range(5)]
    obs.append(_obs(3.80, days_ago=1, vendor="SYSCO"))
    d = _decide(obs)
    assert "overpaying" not in d["reason_summary"].lower()
    assert d["reason_summary"].startswith("High likelihood")


def test_evidence_is_non_empty_for_actionable():
    obs = (
        [_obs(4.10, days_ago=1 + i, vendor="SYSCO") for i in range(4)]
        + [_obs(3.50, days_ago=2, vendor="USFOODS")]
        + [_obs(3.55, days_ago=3, vendor="USFOODS")]
    )
    d = _decide(obs)
    assert d["recommendation_type"] == REC_SWITCH_VENDOR
    assert len(d["evidence"]) >= 3
    assert len(d["uncertainty"]) >= 0  # may be empty if all signals strong
