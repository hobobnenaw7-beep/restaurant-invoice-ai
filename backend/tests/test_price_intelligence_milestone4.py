"""
Milestone 4 — Price Intelligence analytics tests.
Pure-function coverage for compute_trend / compute_stats / evaluate_alert.
"""
from services.price_intelligence import (
    compute_trend,
    compute_stats,
    evaluate_alert,
    MIN_OBSERVATIONS_FOR_TREND,
    MIN_OBSERVATIONS_FOR_ALERT,
    PRICE_ALERT_PCT_THRESHOLD,
)


def _obs(price, date, vendor="SYSCO", cpid="p1", name="Chicken", unit="lb", id_conf=0.95, unit_conf="parser"):
    return {
        "price_per_unit": price,
        "observed_at": date,
        "invoice_date": date,
        "vendor_name": vendor,
        "canonical_product_id": cpid,
        "canonical_name": name,
        "canonical_unit": unit,
        "identity_confidence": id_conf,
        "unit_confidence": unit_conf,
    }


def test_compute_stats_basic():
    obs = [_obs(3.0, "2026-01-01"), _obs(3.5, "2026-01-08"), _obs(4.0, "2026-01-15")]
    s = compute_stats(obs)
    assert s["observations"] == 3
    assert s["min"] == 3.0
    assert s["max"] == 4.0
    assert s["latest"] == 4.0
    assert s["first"] == 3.0
    assert s["latest_vendor"] == "SYSCO"


def test_compute_trend_insufficient():
    # Fewer than MIN_OBSERVATIONS_FOR_TREND
    obs = [_obs(3.0, "2026-01-01"), _obs(3.1, "2026-01-08"), _obs(3.2, "2026-01-15")]
    t = compute_trend(obs)
    assert t["trend"] == "insufficient_data"
    assert t["observations_used"] < MIN_OBSERVATIONS_FOR_TREND


def test_compute_trend_up():
    # latest-3 MA vs prior-3 MA. Needs >=4 observations.
    obs = [
        _obs(3.0, "2026-01-01"),
        _obs(3.0, "2026-01-08"),
        _obs(3.0, "2026-01-15"),
        _obs(4.0, "2026-01-22"),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "up"
    assert t["change_pct"] > 0


def test_compute_trend_down():
    obs = [
        _obs(5.0, "2026-01-01"),
        _obs(5.0, "2026-01-08"),
        _obs(5.0, "2026-01-15"),
        _obs(2.0, "2026-01-22"),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "down"
    assert t["change_pct"] < 0


def test_compute_trend_stable():
    obs = [
        _obs(3.00, "2026-01-01"),
        _obs(3.01, "2026-01-08"),
        _obs(3.02, "2026-01-15"),
        _obs(3.00, "2026-01-22"),
        _obs(3.01, "2026-01-29"),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "stable"


def test_alert_triggers_over_threshold():
    obs = [
        _obs(3.0, "2026-01-01"),
        _obs(3.0, "2026-01-08"),
        _obs(3.0, "2026-01-15"),
        _obs(3.8, "2026-01-22"),  # +26.7% vs prior avg 3.0
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["change_pct"] >= PRICE_ALERT_PCT_THRESHOLD
    assert a["severity"] in ("high", "medium")


def test_alert_not_triggered_below_threshold():
    obs = [
        _obs(3.00, "2026-01-01"),
        _obs(3.05, "2026-01-08"),
        _obs(3.10, "2026-01-15"),
        _obs(3.15, "2026-01-22"),  # +3.3% above prior MA
    ]
    assert evaluate_alert(obs) is None


def test_alert_requires_min_observations():
    obs = [_obs(3.0, "2026-01-01"), _obs(10.0, "2026-01-08")]
    assert len(obs) < MIN_OBSERVATIONS_FOR_ALERT
    assert evaluate_alert(obs) is None


def test_alert_filters_low_confidence():
    obs = [
        _obs(3.0, "2026-01-01", id_conf=0.40),  # low identity
        _obs(3.0, "2026-01-08", id_conf=0.50),  # low identity
        _obs(3.0, "2026-01-15", id_conf=0.60),  # low identity
        _obs(4.5, "2026-01-22", id_conf=0.95),  # single high-conf
    ]
    # Only 1 high-conf observation — insufficient
    assert evaluate_alert(obs) is None


def test_alert_severity_high_at_20pct():
    obs = [
        _obs(3.0, "2026-01-01"),
        _obs(3.0, "2026-01-08"),
        _obs(3.0, "2026-01-15"),
        _obs(3.65, "2026-01-22"),  # +21.7%
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["severity"] == "high"


def test_alert_severity_medium_between_10_and_20():
    obs = [
        _obs(3.0, "2026-01-01"),
        _obs(3.0, "2026-01-08"),
        _obs(3.0, "2026-01-15"),
        _obs(3.4, "2026-01-22"),  # +13.3%
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["severity"] == "medium"
