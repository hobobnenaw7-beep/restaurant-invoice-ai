"""
Milestone 4 — Price Intelligence analytics tests.
Pure-function coverage for compute_trend / compute_stats / evaluate_alert.

NOTE: Dates use a sliding window relative to today so that recency scores
stay above the 'fresh' threshold — the DSS upgrade gates alert evaluation
on the insight confidence level.
"""
from datetime import datetime, timezone, timedelta
from services.price_intelligence import (
    compute_trend,
    compute_stats,
    evaluate_alert,
    MIN_OBSERVATIONS_FOR_TREND,
    MIN_OBSERVATIONS_FOR_ALERT,
    PRICE_ALERT_PCT_THRESHOLD,
    classify_data_quality,
)


def _d(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


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
        "data_quality_flag": classify_data_quality(
            identity_confidence=id_conf, unit_confidence=unit_conf
        ),
    }


def test_compute_stats_basic():
    obs = [_obs(3.0, _d(25)), _obs(3.5, _d(18)), _obs(4.0, _d(11))]
    s = compute_stats(obs)
    assert s["observations"] == 3
    assert s["min"] == 3.0
    assert s["max"] == 4.0
    assert s["latest"] == 4.0
    assert s["first"] == 3.0
    assert s["latest_vendor"] == "SYSCO"


def test_compute_trend_insufficient():
    # Fewer than MIN_OBSERVATIONS_FOR_TREND
    obs = [_obs(3.0, _d(25)), _obs(3.1, _d(18)), _obs(3.2, _d(11))]
    t = compute_trend(obs)
    assert t["trend"] == "insufficient_data"
    assert t["observations_used"] < MIN_OBSERVATIONS_FOR_TREND


def test_compute_trend_up():
    # latest-3 MA vs prior-3 MA. Needs >=4 observations.
    obs = [
        _obs(3.0, _d(25)),
        _obs(3.0, _d(18)),
        _obs(3.0, _d(11)),
        _obs(4.0, _d(4)),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "up"
    assert t["change_pct"] > 0


def test_compute_trend_down():
    obs = [
        _obs(5.0, _d(25)),
        _obs(5.0, _d(18)),
        _obs(5.0, _d(11)),
        _obs(2.0, _d(4)),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "down"
    assert t["change_pct"] < 0


def test_compute_trend_stable():
    obs = [
        _obs(3.00, _d(25)),
        _obs(3.01, _d(18)),
        _obs(3.02, _d(11)),
        _obs(3.00, _d(4)),
        _obs(3.01, _d(1)),
    ]
    t = compute_trend(obs)
    assert t["trend"] == "stable"


def test_alert_triggers_over_threshold():
    obs = [
        _obs(3.0, _d(25)),
        _obs(3.0, _d(18)),
        _obs(3.0, _d(11)),
        _obs(3.8, _d(4)),  # +26.7% vs prior avg 3.0
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["change_pct"] >= PRICE_ALERT_PCT_THRESHOLD
    assert a["severity"] in ("high", "medium")


def test_alert_not_triggered_below_threshold():
    obs = [
        _obs(3.00, _d(25)),
        _obs(3.05, _d(18)),
        _obs(3.10, _d(11)),
        _obs(3.15, _d(4)),  # +3.3% above prior MA
    ]
    assert evaluate_alert(obs) is None


def test_alert_requires_min_observations():
    obs = [_obs(3.0, _d(25)), _obs(10.0, _d(18))]
    assert len(obs) < MIN_OBSERVATIONS_FOR_ALERT
    assert evaluate_alert(obs) is None


def test_alert_filters_low_confidence():
    obs = [
        _obs(3.0, _d(25), id_conf=0.40),  # low identity
        _obs(3.0, _d(18), id_conf=0.50),  # low identity
        _obs(3.0, _d(11), id_conf=0.60),  # low identity
        _obs(4.5, _d(4), id_conf=0.95),  # single high-conf
    ]
    # Only 1 high-conf observation — insufficient
    assert evaluate_alert(obs) is None


def test_alert_severity_high_at_20pct():
    obs = [
        _obs(3.0, _d(25)),
        _obs(3.0, _d(18)),
        _obs(3.0, _d(11)),
        _obs(3.65, _d(4)),  # +21.7%
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["severity"] == "high"


def test_alert_severity_medium_between_10_and_20():
    obs = [
        _obs(3.0, _d(25)),
        _obs(3.0, _d(18)),
        _obs(3.0, _d(11)),
        _obs(3.4, _d(4)),  # +13.3%
    ]
    a = evaluate_alert(obs)
    assert a is not None
    assert a["severity"] == "medium"
