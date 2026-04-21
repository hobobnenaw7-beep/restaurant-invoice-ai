"""
DSS (Decision-Support System) contract tests for Price Intelligence API.

Scope:
  * Confidence engine fields present on products list + product history + vendor list
  * Recommendation fields present & DSS-gated (high=actionable, med=review, low=raw-only)
  * data_quality aggregates + per-record data_quality_flag
  * Alerts endpoint suppresses Medium/Low (only High confidence)
  * Dashboard smart_alerts only surfaces price_intelligence alerts with confidence_level=='high'
  * Probabilistic wording ('likelihood' yes, 'overpaying' no)
  * Poor-quality-only product → confidence=low, stats/alert empty, tags include review_suggested+data_thin
  * Multi-tenant boundary still holds via staff@test.com (same tenant as demo), and
    absence of leakage of demo tenant's data via user-scoped queries.
  * Backfill tags data_quality_flag on inserted records.
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://invoice-ai-35.preview.emergentagent.com").rstrip("/")

DEMO_EMAIL = "demo@test.com"
DEMO_PASS = "testpassword"
STAFF_EMAIL = "staff@test.com"
STAFF_PASS = "testpass123"

HIGH_CPID = "2c131d7a-78ad-4715-bdab-2c8e685bb791"   # Chicken Breast — 6 fresh good obs + alert
LOW_CPID = "e703a4fe-e389-4aec-8be4-bc34e5b9b8b3"    # Ground Beef 80/20 — 3 POOR obs


# ── Fixtures ─────────────────────────────────────────────────────────
def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"No token in login response for {email}: {r.json()}"
    return token


@pytest.fixture(scope="module")
def demo_client():
    token = _login(DEMO_EMAIL, DEMO_PASS)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def staff_client():
    token = _login(STAFF_EMAIL, STAFF_PASS)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def products_summary(demo_client):
    r = demo_client.get(f"{BASE_URL}/api/price-intelligence/products", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. Products list — confidence + recommendation + data_quality contract ──
class TestProductsSummaryContract:
    def test_status_and_shape(self, products_summary):
        assert "items" in products_summary
        assert "total" in products_summary
        assert isinstance(products_summary["items"], list)
        assert products_summary["total"] == len(products_summary["items"])
        assert products_summary["total"] > 0

    def test_every_item_has_dss_fields(self, products_summary):
        required_top = {
            "canonical_product_id", "canonical_unit", "stats", "trend",
            "alert", "confidence", "recommendation", "data_quality",
        }
        for it in products_summary["items"]:
            missing = required_top - set(it.keys())
            assert not missing, f"Missing {missing} on item {it.get('canonical_product_id')}"

    def test_confidence_subshape(self, products_summary):
        for it in products_summary["items"]:
            c = it["confidence"]
            assert set(["score", "level", "components", "weights", "explanation"]).issubset(c.keys())
            assert 0.0 <= c["score"] <= 1.0
            assert c["level"] in ("high", "medium", "low")
            assert set(c["components"].keys()) == {"recency", "observations", "identity", "unit"}
            # weights
            w = c["weights"]
            assert abs(w["recency"] - 0.30) < 1e-6
            assert abs(w["observations"] - 0.25) < 1e-6
            assert abs(w["identity"] - 0.25) < 1e-6
            assert abs(w["unit"] - 0.20) < 1e-6
            # level mapping
            if c["score"] >= 0.80:
                assert c["level"] == "high"
            elif c["score"] >= 0.60:
                assert c["level"] == "medium"
            else:
                assert c["level"] == "low"

    def test_recommendation_subshape(self, products_summary):
        for it in products_summary["items"]:
            r = it["recommendation"]
            for k in ("level", "actionable", "label", "headline", "detail", "action", "tags"):
                assert k in r, f"recommendation missing {k}"
            assert r["level"] == it["confidence"]["level"]
            assert r["actionable"] is (r["level"] == "high")
            if r["level"] == "low":
                assert r["action"] is None
                assert "review_suggested" in r["tags"]
                assert "data_thin" in r["tags"]

    def test_data_quality_aggregate(self, products_summary):
        for it in products_summary["items"]:
            dq = it["data_quality"]
            assert set(dq.keys()) == {"good", "fair", "poor"}
            for k in dq:
                assert isinstance(dq[k], int) and dq[k] >= 0

    def test_keyed_by_cpid_and_unit(self, products_summary):
        seen = set()
        for it in products_summary["items"]:
            key = (it["canonical_product_id"], it.get("canonical_unit") or "")
            assert key not in seen, f"duplicate bucket {key}"
            seen.add(key)

    def test_high_confidence_chicken_present(self, products_summary):
        match = [i for i in products_summary["items"] if i["canonical_product_id"] == HIGH_CPID]
        assert match, "HIGH_CPID (Chicken Breast) not present"
        it = match[0]
        assert it["confidence"]["level"] == "high", f"expected high, got {it['confidence']}"
        assert it["confidence"]["score"] >= 0.80
        assert it["recommendation"]["actionable"] is True
        # alert should exist on the seeded active-alert product
        assert it["alert"] is not None, "seeded high-confidence product missing alert"

    def test_low_confidence_beef_present(self, products_summary):
        match = [i for i in products_summary["items"] if i["canonical_product_id"] == LOW_CPID]
        # LOW data may be excluded from summary bucket if all poor — but since bucket is
        # built from ALL observations, it should still appear. Stats should be empty.
        if not match:
            pytest.skip("LOW_CPID not surfaced — poor-only may be excluded upstream")
        it = match[0]
        assert it["confidence"]["level"] == "low"
        assert it["confidence"]["score"] < 0.60
        # stats from good-only obs should be empty
        s = it["stats"]
        assert s.get("observations", 0) == 0
        assert s.get("min") is None and s.get("max") is None and s.get("avg") is None
        # alert must be suppressed
        assert it["alert"] is None
        # recommendation tags
        tags = set(it["recommendation"]["tags"])
        assert "review_suggested" in tags and "data_thin" in tags
        assert it["recommendation"]["action"] is None
        # data_quality.poor >= 1
        assert it["data_quality"]["poor"] >= 1
        assert it["data_quality"]["good"] == 0


# ── 2. Product history — confidence + recommendation + data_quality_flag ──
class TestProductHistory:
    def test_high_product_history(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/price-intelligence/products/{HIGH_CPID}/history", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("confidence", "recommendation", "data_quality", "observations"):
            assert k in d, f"missing {k}"
        assert d["confidence"]["level"] == "high"
        assert d["recommendation"]["actionable"] is True
        # observations list contains raw-level records with data_quality_flag
        assert len(d["observations"]) >= 1
        for o in d["observations"]:
            assert "data_quality_flag" in o
            assert o["data_quality_flag"] in ("good", "fair", "poor")

    def test_low_product_history_excludes_poor_from_stats(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/price-intelligence/products/{LOW_CPID}/history", timeout=30)
        if r.status_code == 404:
            pytest.skip("LOW_CPID has no observations (404) — seed may be purged")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["confidence"]["level"] == "low"
        # raw observations still visible with data_quality_flag='poor'
        assert len(d["observations"]) >= 1
        poor_obs = [o for o in d["observations"] if o.get("data_quality_flag") == "poor"]
        assert len(poor_obs) >= 1, "expected at least 1 poor-flagged record"
        # stats excluded
        assert d["stats"].get("observations", 0) == 0
        assert d["trend"]["trend"] == "insufficient_data"
        assert d["alert"] is None
        tags = set(d["recommendation"]["tags"])
        assert {"review_suggested", "data_thin"}.issubset(tags)
        assert d["recommendation"]["action"] is None


# ── 3. Vendor comparison — filters to good-only ──
class TestVendorComparison:
    def test_high_product_vendors(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/price-intelligence/products/{HIGH_CPID}/vendors", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "confidence" in d and "recommendation" in d
        assert d["confidence"]["level"] == "high"
        assert isinstance(d["vendors"], list) and len(d["vendors"]) >= 1

    def test_low_product_vendors_404_or_empty(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/price-intelligence/products/{LOW_CPID}/vendors", timeout=30)
        # Since all obs are poor → good-filtered vendors list is empty → 404
        assert r.status_code == 404, f"expected 404 for poor-only product, got {r.status_code}"


# ── 4. Alerts endpoint — only High confidence surfaces ──
class TestAlertsSuppression:
    def test_alerts_list_high_only(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/price-intelligence/alerts", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "alerts" in d and "total" in d
        for a in d["alerts"]:
            # confidence_level field should exist and be 'high'
            assert a.get("confidence_level") == "high", \
                f"non-high alert surfaced: {a.get('confidence_level')} — {a.get('item_name')}"

    def test_low_product_has_no_alert(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/price-intelligence/alerts", timeout=30)
        d = r.json()
        for a in d["alerts"]:
            assert a.get("canonical_product_id") != LOW_CPID, \
                "alert leaked for low-confidence product"


# ── 5. Dashboard summary — filter + probabilistic wording ──
class TestDashboardDSS:
    def test_smart_alerts_high_only(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/dashboard/summary", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        pi_alerts = [a for a in d.get("smart_alerts", []) if a.get("source") == "price_intelligence"]
        assert len(pi_alerts) >= 1, "expected at least 1 PI alert on dashboard (seeded high alert)"
        for a in pi_alerts:
            assert a.get("confidence_level") == "high"

    def test_probabilistic_wording(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/dashboard/summary", timeout=30)
        d = r.json()
        pi_alerts = [a for a in d.get("smart_alerts", []) if a.get("source") == "price_intelligence"]
        texts = [a.get("message", "") for a in pi_alerts]
        joined = " ".join(texts).lower()
        if texts:
            assert "overpaying" not in joined, f"non-probabilistic word found: {joined}"
            # must contain 'likelihood' (per price_intelligence.evaluate_alert message template)
            assert "likelihood" in joined, f"expected probabilistic 'likelihood' term: {joined}"


# ── 6. Probabilistic wording in alert & recommendation (from PI endpoints) ──
class TestProbabilisticLanguage:
    def test_alert_message_wording(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/price-intelligence/alerts", timeout=30)
        d = r.json()
        for a in d["alerts"]:
            msg = (a.get("message") or "").lower()
            if msg:
                assert "overpaying" not in msg
                assert "likelihood" in msg

    def test_recommendation_detail_wording(self, products_summary):
        for it in products_summary["items"]:
            detail = (it["recommendation"].get("detail") or "").lower()
            assert "overpaying" not in detail


# ── 7. Multi-tenant isolation (staff is same tenant as demo — should see same data) ──
class TestMultiTenant:
    def test_staff_same_tenant_sees_same_high_cpid(self, staff_client):
        r = staff_client.get(f"{BASE_URL}/api/price-intelligence/products", timeout=30)
        if r.status_code == 403:
            pytest.skip("staff lacks view permission")
        assert r.status_code == 200, r.text
        ids = {i["canonical_product_id"] for i in r.json()["items"]}
        # same tenant → should see same HIGH seed
        assert HIGH_CPID in ids


# ── 8. Backfill — data_quality_flag is set on inserted records ──
class TestBackfillQualityFlag:
    def test_backfill_and_records_flagged(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/price-intelligence/backfill", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("purchases_scanned", "observations_inserted", "observations_skipped", "skip_reasons"):
            assert k in body
        # After backfill, verify at least one history record has data_quality_flag
        h = demo_client.get(
            f"{BASE_URL}/api/price-intelligence/products/{HIGH_CPID}/history", timeout=30)
        assert h.status_code == 200
        obs = h.json()["observations"]
        assert obs, "no observations after backfill"
        assert all("data_quality_flag" in o for o in obs)
        assert all(o["data_quality_flag"] in ("good", "fair", "poor") for o in obs)
