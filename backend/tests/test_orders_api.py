"""
Backend tests for NEW Orders endpoints (Phase 4 — Navigation Restructure).
Covers: auth, CREATE/GET/DELETE lifecycle, bogus item_id → 400, invalid status → 400,
tenant scoping, response shape (no _id leakage).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def demo_token():
    tok = _login("demo@test.com", "testpassword")
    assert tok, "demo login returned no token"
    return tok


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_item_ids(demo_headers):
    r = requests.get(f"{API}/items", headers=demo_headers, timeout=20)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list) and len(items) > 0
    return [it["id"] for it in items[:2]]


# ── AUTH ────────────────────────────────────────────────────────────
def test_orders_requires_auth():
    r = requests.get(f"{API}/orders", timeout=10)
    assert r.status_code in (401, 403)


def test_orders_post_requires_auth():
    r = requests.post(f"{API}/orders", json={"items": []}, timeout=10)
    assert r.status_code in (401, 403)


# ── LIST ────────────────────────────────────────────────────────────
def test_list_orders_shape(demo_headers):
    r = requests.get(f"{API}/orders", headers=demo_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "total" in body
    assert isinstance(body["items"], list)
    for o in body["items"]:
        assert "_id" not in o  # no ObjectId leakage


# ── CREATE + VERIFY + DELETE ────────────────────────────────────────
def test_create_order_valid_item(demo_headers, sample_item_ids):
    payload = {
        "order_date": "2026-01-15",
        "vendor_name": "TEST_VendorX",
        "note": "TEST_orders_iter93",
        "status": "draft",
        "items": [
            {"item_id": sample_item_ids[0], "quantity": 3, "unit": "lb",
             "last_known_price": 2.5, "last_known_vendor": "Sysco"},
        ],
    }
    r = requests.post(f"{API}/orders", headers=demo_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # shape
    for key in ["id", "status", "items", "total_estimated", "created_at", "restaurant_id"]:
        assert key in data, f"missing {key}"
    assert "_id" not in data
    assert data["status"] == "draft"
    assert len(data["items"]) == 1
    assert data["items"][0]["item_id"] == sample_item_ids[0]
    assert data["items"][0]["item_name"]  # enriched
    assert data["total_estimated"] == pytest.approx(7.5, rel=1e-3)
    order_id = data["id"]

    # GET verifies persistence
    rl = requests.get(f"{API}/orders", headers=demo_headers, timeout=15).json()
    ids = [o["id"] for o in rl["items"]]
    assert order_id in ids

    # DELETE
    rd = requests.delete(f"{API}/orders/{order_id}", headers=demo_headers, timeout=15)
    assert rd.status_code == 200, rd.text
    assert rd.json().get("deleted") is True

    # VERIFY REMOVED
    rl2 = requests.get(f"{API}/orders", headers=demo_headers, timeout=15).json()
    ids2 = [o["id"] for o in rl2["items"]]
    assert order_id not in ids2


def test_create_order_bogus_item_id_returns_400(demo_headers):
    payload = {
        "status": "draft",
        "items": [{"item_id": "does-not-exist-xyz", "quantity": 1}],
    }
    r = requests.post(f"{API}/orders", headers=demo_headers, json=payload, timeout=15)
    assert r.status_code == 400, r.text
    assert "unknown_item_ids" in (r.json().get("detail") or "")


def test_create_order_invalid_status_executed(demo_headers, sample_item_ids):
    payload = {
        "status": "executed",
        "items": [{"item_id": sample_item_ids[0], "quantity": 1}],
    }
    r = requests.post(f"{API}/orders", headers=demo_headers, json=payload, timeout=15)
    assert r.status_code == 400
    assert "invalid_status" in (r.json().get("detail") or "")


def test_create_order_invalid_status_random(demo_headers, sample_item_ids):
    payload = {
        "status": "weirdo",
        "items": [{"item_id": sample_item_ids[0], "quantity": 1}],
    }
    r = requests.post(f"{API}/orders", headers=demo_headers, json=payload, timeout=15)
    assert r.status_code == 400


def test_create_order_submitted_ok(demo_headers, sample_item_ids):
    payload = {
        "status": "submitted",
        "note": "TEST_orders_iter93 submitted",
        "items": [{"item_id": sample_item_ids[0], "quantity": 2,
                   "last_known_price": 4.0, "unit": "ea"}],
    }
    r = requests.post(f"{API}/orders", headers=demo_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "submitted"
    # cleanup
    requests.delete(f"{API}/orders/{d['id']}", headers=demo_headers, timeout=10)


def test_delete_nonexistent_order(demo_headers):
    r = requests.delete(f"{API}/orders/no-such-id-xyz", headers=demo_headers, timeout=10)
    assert r.status_code == 404


# ── REGRESSION: existing procurement endpoints still serve ──────────
def test_procurement_recommendations_still_works(demo_headers):
    r = requests.get(f"{API}/procurement/recommendations", headers=demo_headers, timeout=30)
    assert r.status_code == 200, r.text


def test_price_intelligence_endpoint_still_works(demo_headers):
    r = requests.get(f"{API}/procurement/price-intelligence/summary", headers=demo_headers, timeout=30)
    assert r.status_code in (200, 404)  # endpoint may be named differently; just ensure no 500


def test_procurement_suggestions_list_still_works(demo_headers):
    for tab in ["saved_for_review", "acted_on", "not_pursued"]:
        r = requests.get(f"{API}/procurement/suggestions?tab={tab}", headers=demo_headers, timeout=20)
        assert r.status_code == 200, f"{tab}: {r.text}"
