"""
Milestone 4 — Price Intelligence API Endpoint Tests
=====================================================
Tests live HTTP endpoints for /api/price-intelligence/* with authenticated
users. Validates contracts, idempotency, multi-tenant isolation,
ingestion hooks on /api/purchases, and dashboard smart_alerts merge.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://invoice-ai-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@test.com", "password": "testpassword"}
STAFF = {"email": "staff@test.com", "password": "testpass123"}
ACCOUNTANT = {"email": "accountant@test.com", "password": "testpass123"}


# ── Fixtures ────────────────────────────────────────────────────────

def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def demo_headers():
    return {"Authorization": f"Bearer {_login(DEMO)}"}


@pytest.fixture(scope="module")
def staff_headers():
    return {"Authorization": f"Bearer {_login(STAFF)}"}


@pytest.fixture(scope="module")
def accountant_headers():
    return {"Authorization": f"Bearer {_login(ACCOUNTANT)}"}


# ── Backfill endpoint ───────────────────────────────────────────────

class TestBackfill:
    def test_backfill_contract_and_idempotent(self, demo_headers):
        r1 = requests.post(f"{API}/price-intelligence/backfill", headers=demo_headers, timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        for key in ["purchases_scanned", "observations_inserted", "observations_skipped", "skip_reasons"]:
            assert key in d1, f"missing key {key} in backfill response: {d1}"
        assert isinstance(d1["skip_reasons"], dict)

        # Idempotent: rerun should produce same counts (delete-then-insert semantic)
        r2 = requests.post(f"{API}/price-intelligence/backfill", headers=demo_headers, timeout=120)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["purchases_scanned"] == d1["purchases_scanned"]
        assert d2["observations_inserted"] == d1["observations_inserted"]
        assert d2["observations_skipped"] == d1["observations_skipped"]


# ── Products summary ────────────────────────────────────────────────

class TestProductsSummary:
    def test_products_summary_contract(self, demo_headers):
        r = requests.get(f"{API}/price-intelligence/products", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "total" in body
        assert isinstance(body["items"], list)
        assert body["total"] == len(body["items"])
        # Demo user has pre-seeded synthetic data; items should be non-empty
        assert body["total"] > 0, "Expected pre-seeded price_history for demo user"

        item = body["items"][0]
        for key in ["canonical_product_id", "canonical_unit", "stats", "trend", "vendors", "alert"]:
            assert key in item, f"missing key {key} in product item"

        stats = item["stats"]
        for s in ["min", "max", "avg", "latest", "observations"]:
            assert s in stats

        trend = item["trend"]
        for t in ["trend", "moving_average_latest", "moving_average_prior", "change_pct"]:
            assert t in trend

    def test_seeded_product_present(self, demo_headers):
        """The seeded product 2c131d7a-78ad-4715-bdab-2c8e685bb791 should be present."""
        r = requests.get(f"{API}/price-intelligence/products", headers=demo_headers, timeout=30)
        items = r.json()["items"]
        seeded_id = "2c131d7a-78ad-4715-bdab-2c8e685bb791"
        found = [i for i in items if i["canonical_product_id"] == seeded_id]
        assert found, f"Seeded product {seeded_id} not found. Got {[i['canonical_product_id'] for i in items]}"
        it = found[0]
        assert it["stats"]["observations"] >= 4


# ── Product history ─────────────────────────────────────────────────

class TestProductHistory:
    SEEDED_CPID = "2c131d7a-78ad-4715-bdab-2c8e685bb791"

    def test_history_sorted_ascending(self, demo_headers):
        r = requests.get(
            f"{API}/price-intelligence/products/{self.SEEDED_CPID}/history",
            params={"canonical_unit": "lb"},
            headers=demo_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["observations", "stats", "trend", "alert", "canonical_unit"]:
            assert key in d
        obs = d["observations"]
        assert len(obs) >= 1
        # Ascending by observed_at
        ts = [o.get("observed_at") or "" for o in obs]
        assert ts == sorted(ts), f"Observations not sorted ascending: {ts}"

    def test_history_404_for_unknown(self, demo_headers):
        r = requests.get(
            f"{API}/price-intelligence/products/{uuid.uuid4()}/history",
            headers=demo_headers, timeout=30,
        )
        assert r.status_code == 404


# ── Product vendors ─────────────────────────────────────────────────

class TestProductVendors:
    SEEDED_CPID = "2c131d7a-78ad-4715-bdab-2c8e685bb791"

    def test_vendors_contract(self, demo_headers):
        r = requests.get(
            f"{API}/price-intelligence/products/{self.SEEDED_CPID}/vendors",
            params={"canonical_unit": "lb"},
            headers=demo_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["vendors", "best_vendor", "worst_vendor", "savings_pct"]:
            assert key in d
        assert isinstance(d["vendors"], list)
        assert len(d["vendors"]) >= 1
        v = d["vendors"][0]
        for k in ["vendor", "latest_price", "avg_price", "min_price", "max_price", "observations"]:
            assert k in v

    def test_vendors_404_for_unknown(self, demo_headers):
        r = requests.get(
            f"{API}/price-intelligence/products/{uuid.uuid4()}/vendors",
            headers=demo_headers, timeout=30,
        )
        assert r.status_code == 404


# ── Alerts ──────────────────────────────────────────────────────────

class TestAlerts:
    def test_alerts_contract(self, demo_headers):
        r = requests.get(f"{API}/price-intelligence/alerts", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "alerts" in d and "total" in d
        assert d["total"] == len(d["alerts"])
        for a in d["alerts"]:
            assert a.get("type") == "price_intelligence"
            assert "severity" in a
            assert a["severity"] in ("high", "medium", "low")
            assert "canonical_product_id" in a

    def test_dashboard_includes_pi_alerts(self, demo_headers):
        """Dashboard summary smart_alerts should include PI alerts at the top."""
        alerts_resp = requests.get(f"{API}/price-intelligence/alerts", headers=demo_headers, timeout=30).json()
        pi_count = alerts_resp["total"]

        r = requests.get(f"{API}/dashboard/summary", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        smart = r.json().get("smart_alerts", [])
        if pi_count > 0:
            sources = [s.get("source") for s in smart]
            # At least one PI alert should be present when active
            assert "price_intelligence" in sources, f"PI alerts not merged into smart_alerts. Got sources: {sources}"


# ── Multi-tenant isolation ──────────────────────────────────────────

class TestMultiTenant:
    def test_staff_same_tenant_sees_data(self, staff_headers, demo_headers):
        """staff@test.com is same tenant — should see SAME data (scope=own doesn't apply to PI)."""
        demo_items = requests.get(f"{API}/price-intelligence/products", headers=demo_headers, timeout=30).json()["items"]
        staff_items = requests.get(f"{API}/price-intelligence/products", headers=staff_headers, timeout=30).json()["items"]
        demo_cpids = sorted([i["canonical_product_id"] for i in demo_items])
        staff_cpids = sorted([i["canonical_product_id"] for i in staff_items])
        assert demo_cpids == staff_cpids, (
            f"Same-tenant users got different PI data. demo={demo_cpids} staff={staff_cpids}"
        )

    def test_different_tenant_isolated(self, demo_headers, accountant_headers):
        """accountant@test.com is a different reference user — verify isolation OR same-tenant consistency."""
        # Fetch current user info
        demo_me = requests.get(f"{API}/auth/me", headers=demo_headers, timeout=30).json()
        acc_me = requests.get(f"{API}/auth/me", headers=accountant_headers, timeout=30).json()
        demo_rid = demo_me.get("restaurant_id")
        acc_rid = acc_me.get("restaurant_id")

        demo_items = requests.get(f"{API}/price-intelligence/products", headers=demo_headers, timeout=30).json()["items"]
        acc_items = requests.get(f"{API}/price-intelligence/products", headers=accountant_headers, timeout=30).json()["items"]

        if demo_rid != acc_rid:
            # Different tenants — data sets must be disjoint on observed ids OR accountant must have none
            demo_cpids = set(i["canonical_product_id"] for i in demo_items)
            acc_cpids = set(i["canonical_product_id"] for i in acc_items)
            # A cross-leak would mean accountant sees demo's seeded product
            assert "2c131d7a-78ad-4715-bdab-2c8e685bb791" not in acc_cpids, (
                "LEAK: accountant tenant sees demo's seeded price_history product"
            )


# ── Purchases ingest hook ───────────────────────────────────────────

class TestPurchasesIngestHook:
    def _fetch_seeded_observations_count(self, headers):
        r = requests.get(f"{API}/price-intelligence/products", headers=headers, timeout=30).json()
        total = sum(i["stats"].get("observations", 0) for i in r["items"])
        return total

    def test_create_purchase_triggers_ingest(self, demo_headers):
        """Creating a purchase with canonical_unit+ppu+cpid should insert into price_history."""
        # Pick an existing canonical product id (seeded)
        cpid = "2c131d7a-78ad-4715-bdab-2c8e685bb791"
        before = self._fetch_seeded_observations_count(demo_headers)

        payload = {
            "supplier_name": "TEST_SYSCO_PI",
            "invoice_date": "2026-01-10",
            "invoice_number": f"TEST_PI_{uuid.uuid4().hex[:8]}",
            "items": [
                {
                    "raw_name": "TEST Chicken Breast Premium",
                    "item_code": "TESTPI001",
                    "quantity": 10,
                    "unit_price": 25.00,
                    "price_per_unit": 2.50,
                    "canonical_unit": "lb",
                    "canonical_product_id": cpid,
                    "canonical_name": "Chicken Breast",
                    "identity_confidence": 0.95,
                    "identity_match_type": "exact",
                    "unit_status": "resolved",
                    "_unit_source": "parser",
                    "total_price": 25.00,
                }
            ],
            "subtotal": 25.00,
            "tax": 0.0,
            "total": 25.00,
        }
        r = requests.post(f"{API}/purchases", headers=demo_headers, json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text
        purchase = r.json()
        pid = purchase.get("id")
        assert pid

        # Give hot-reload/ingest a moment
        time.sleep(1)

        after = self._fetch_seeded_observations_count(demo_headers)
        assert after >= before + 1, f"Observations did not increase after purchase create. before={before} after={after}"

        # Cleanup
        requests.delete(f"{API}/purchases/{pid}", headers=demo_headers, timeout=30)

    def test_purchase_without_canonical_fields_skipped(self, demo_headers):
        before = self._fetch_seeded_observations_count(demo_headers)
        payload = {
            "supplier_name": "TEST_SYSCO_PI2",
            "invoice_date": "2026-01-11",
            "invoice_number": f"TEST_PI_SKIP_{uuid.uuid4().hex[:8]}",
            "items": [
                {
                    "raw_name": "Mystery Item No Canonical",
                    "quantity": 1,
                    "unit_price": 99.0,
                    "total_price": 99.0,
                    # no canonical_unit, no price_per_unit, no canonical_product_id
                }
            ],
            "subtotal": 99.0,
            "tax": 0.0,
            "total": 99.0,
        }
        r = requests.post(f"{API}/purchases", headers=demo_headers, json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text
        pid = r.json().get("id")
        time.sleep(1)
        after = self._fetch_seeded_observations_count(demo_headers)
        # Count should NOT go up (or at worst stay equal - but definitely not jump)
        assert after == before, f"Item without canonical fields was ingested! before={before} after={after}"
        if pid:
            requests.delete(f"{API}/purchases/{pid}", headers=demo_headers, timeout=30)

    def test_patch_item_reingests(self, demo_headers):
        """PATCH /purchases/{pid}/items/{idx} should re-ingest price_history (idempotent)."""
        cpid = "2c131d7a-78ad-4715-bdab-2c8e685bb791"
        # Create purchase with an ALREADY-eligible item so initial ingest inserts 1
        payload = {
            "supplier_name": "TEST_PATCH_PI",
            "invoice_date": "2026-01-12",
            "invoice_number": f"TEST_PATCH_{uuid.uuid4().hex[:8]}",
            "items": [
                {
                    "raw_name": "Patch Chicken Breast Item",
                    "item_code": "PATCHPI001",
                    "quantity": 5,
                    "unit_price": 20.0,
                    "total_price": 20.0,
                    "total": 20.0,
                    "price_per_unit": 4.0,
                    "canonical_unit": "lb",
                    "canonical_product_id": cpid,
                    "canonical_name": "Chicken Breast",
                    "identity_confidence": 0.95,
                    "identity_match_type": "exact",
                    "unit_status": "resolved",
                    "_unit_source": "parser",
                }
            ],
            "subtotal": 20.0,
            "tax": 0.0,
            "total": 20.0,
        }
        r = requests.post(f"{API}/purchases", headers=demo_headers, json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        time.sleep(1)
        before = self._fetch_seeded_observations_count(demo_headers)

        # PATCH an editable field — should trigger _reingest_price_intelligence
        patch_body = {"unit_price": 22.5, "total": 22.5, "quantity": 5}
        pr = requests.patch(f"{API}/purchases/{pid}/items/0", headers=demo_headers, json=patch_body, timeout=60)
        assert pr.status_code in (200, 204), f"PATCH returned {pr.status_code}: {pr.text}"
        pr_body = pr.json() if pr.status_code == 200 else {}
        pi_stats = pr_body.get("price_intelligence", {})
        # Must have re-ingested (idempotent: prior obs deleted + new one inserted)
        assert pi_stats.get("inserted", 0) >= 1, (
            f"PATCH did not re-ingest price_intelligence. Response: {pr_body}"
        )

        time.sleep(1)
        after = self._fetch_seeded_observations_count(demo_headers)
        # Idempotent — count stays the same (delete-then-insert)
        assert after == before, f"PATCH re-ingest not idempotent. before={before} after={after}"

        # Cleanup
        requests.delete(f"{API}/purchases/{pid}", headers=demo_headers, timeout=30)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
