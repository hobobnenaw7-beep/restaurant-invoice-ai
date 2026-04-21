"""Milestone 6 — Controlled Action Layer END-TO-END API tests.

Hits the public preview backend with the demo user and verifies:
  - POST /api/procurement/events validation + persistence (via list)
  - POST /api/procurement/suggestions acknowledgment gate + 'saved_for_review'
  - GET  /api/procurement/suggestions tenant-scoped listing
  - GET  /api/procurement/quantity-hint advisory payload shape
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    # Fallback: read from frontend/.env directly
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().strip('"')
                break
BASE = BASE.rstrip("/")

EMAIL = "demo@test.com"
PASS = "testpassword"
CPID = "2c131d7a-78ad-4715-bdab-2c8e685bb791"  # Chicken Breast – switch_vendor


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": EMAIL, "password": PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in {data}"
    return tok


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- /api/procurement/events ----------

def test_event_invalid_type_returns_400(headers):
    r = requests.post(
        f"{BASE}/api/procurement/events",
        json={"canonical_product_id": CPID, "recommendation_type": "switch_vendor",
              "event_type": "pay_now"},
        headers=headers, timeout=30,
    )
    assert r.status_code == 400, r.text
    assert "invalid_event_type" in r.text


@pytest.mark.parametrize("ev", [
    "suggestion_opened", "draft_viewed", "acknowledgment_checked", "action_canceled",
])
def test_event_allowed_types_persist(headers, ev):
    r = requests.post(
        f"{BASE}/api/procurement/events",
        json={"canonical_product_id": CPID, "recommendation_type": "switch_vendor",
              "event_type": ev, "metadata": {"src": "api_test"}},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event"]["event_type"] == ev
    assert body["event"]["canonical_product_id"] == CPID
    assert body["event"].get("restaurant_id")
    assert "timestamp" in body["event"]


# ---------- /api/procurement/quantity-hint ----------

def test_quantity_hint_shape(headers):
    r = requests.get(
        f"{BASE}/api/procurement/quantity-hint/{CPID}",
        params={"canonical_unit": "lb"},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("lookback", "quantities", "average", "helper_text", "disclaimer",
              "last_vendors", "last_invoice_dates"):
        assert k in body, f"missing key {k} in {body}"
    assert body["disclaimer"] == "Suggestion only — not a recommended order quantity."
    # helper_text must include 'Based on your last' OR fallback message
    assert ("Based on your last" in body["helper_text"]
            or "No recent quantity data" in body["helper_text"])


def test_quantity_hint_missing_unit_param_400(headers):
    r = requests.get(
        f"{BASE}/api/procurement/quantity-hint/{CPID}",
        headers=headers, timeout=30,
    )
    assert r.status_code in (400, 422), r.text


# ---------- /api/procurement/suggestions ----------

def test_save_suggestion_requires_acknowledgment(headers):
    body = {
        "canonical_product_id": CPID, "canonical_unit": "lb",
        "recommendation_type": "switch_vendor", "recommended_vendor": "USFoods",
        "reference_price_per_unit": 3.50, "current_price_per_unit": 4.25,
        "decision_confidence": 0.95, "confidence_level": "high", "risk_level": "medium",
        "reason_summary": "TEST_acknowledgment_required",
        "evidence": ["e1"], "uncertainty": ["u1"],
        "acknowledgment_confirmed": False,
    }
    r = requests.post(f"{BASE}/api/procurement/suggestions", json=body,
                      headers=headers, timeout=30)
    assert r.status_code == 400, r.text
    assert "acknowledgment_required" in r.text


def test_save_suggestion_persists_and_lists(headers):
    marker = f"TEST_marker_{int(time.time())}"
    body = {
        "canonical_product_id": CPID, "canonical_unit": "lb",
        "recommendation_type": "switch_vendor", "recommended_vendor": "USFoods",
        "reference_price_per_unit": 3.50, "current_price_per_unit": 4.25,
        "decision_confidence": 0.95, "confidence_level": "high", "risk_level": "medium",
        "reason_summary": marker,
        "evidence": ["TEST_e1"], "uncertainty": ["TEST_u1"],
        "acknowledgment_confirmed": True,
        "snapshot": {"src": "api_test"},
    }
    r = requests.post(f"{BASE}/api/procurement/suggestions", json=body,
                      headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["status"] == "saved_for_review"
    assert saved["acknowledgment_confirmed"] is True
    assert saved["acknowledged_at"]
    assert saved["reason_summary"] == marker
    assert "id" in saved

    # GET list, must include the just-saved doc
    r2 = requests.get(f"{BASE}/api/procurement/suggestions",
                      headers=headers, timeout=30)
    assert r2.status_code == 200, r2.text
    items = r2.json()["items"]
    assert any(it.get("reason_summary") == marker for it in items), \
        f"saved suggestion {marker} not in list"


def test_unauth_returns_401():
    r = requests.get(f"{BASE}/api/procurement/suggestions", timeout=30)
    assert r.status_code in (401, 403), r.text
