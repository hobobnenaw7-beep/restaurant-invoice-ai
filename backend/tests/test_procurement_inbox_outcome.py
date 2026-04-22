"""
Milestone 7 — Saved Suggestions Inbox + Outcome PATCH endpoint
Tests against PUBLIC URL.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend env file in case env not exported in test process
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@test.com"
DEMO_PASSWORD = "testpassword"
ALT_EMAIL = "tenant_iso_test@example.com"
ALT_PASSWORD = "testpass123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _register_or_login(email, password, name, restaurant_name):
    """Register an isolated-tenant user; if it already exists, log in."""
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": password,
                            "name": name, "restaurant_name": restaurant_name},
                      timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    return _login(email, password)


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="module")
def alt_token():
    # alt user is in a DIFFERENT restaurant than demo (multi-tenant)
    return _register_or_login(ALT_EMAIL, ALT_PASSWORD, "Iso Tester", "Iso Test Restaurant")


def _hdrs(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _create_saved_suggestion(token, marker):
    body = {
        "canonical_product_id": f"TEST_pid_{marker}",
        "canonical_unit": "lb",
        "canonical_name": f"TEST Product {marker}",
        "current_vendor": "TEST Vendor A",
        "recommendation_type": "switch_vendor",
        "recommended_vendor": "TEST Vendor B",
        "reference_price_per_unit": 5.0,
        "current_price_per_unit": 6.5,
        "decision_confidence": 0.82,
        "confidence_level": "high",
        "risk_level": "low",
        "reason_summary": f"Test save {marker}",
        "evidence": ["e1"],
        "uncertainty": [],
        "acknowledgment_confirmed": True,
        "snapshot": {"marker": marker},
    }
    r = requests.post(f"{API}/procurement/suggestions", json=body, headers=_hdrs(token), timeout=30)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    return r.json()


# ── GET list + breakdown ────────────────────────────────────────────────
class TestListAndBreakdown:
    def test_list_includes_breakdown_keys(self, demo_token):
        r = requests.get(f"{API}/procurement/suggestions", headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "breakdown" in data and "total" in data
        bd = data["breakdown"]
        for k in ("saved_for_review", "acted_on", "not_pursued"):
            assert k in bd and isinstance(bd[k], int)

    def test_status_filter_only_returns_matching_status(self, demo_token):
        # ensure at least one saved_for_review exists
        _create_saved_suggestion(demo_token, f"filter_{int(time.time())}")
        r = requests.get(f"{API}/procurement/suggestions?status=saved_for_review",
                         headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        for it in data["items"]:
            assert (it.get("status") or "saved_for_review") == "saved_for_review"

    def test_breakdown_stays_total_across_filters(self, demo_token):
        r_all = requests.get(f"{API}/procurement/suggestions",
                             headers=_hdrs(demo_token), timeout=30).json()
        r_act = requests.get(f"{API}/procurement/suggestions?status=acted_on",
                             headers=_hdrs(demo_token), timeout=30).json()
        # breakdown should be identical regardless of the filter
        assert r_all["breakdown"] == r_act["breakdown"]
        # total of breakdown >= total acted_on items
        assert r_act["total"] <= sum(r_all["breakdown"].values())


# ── PATCH outcome ───────────────────────────────────────────────────────
class TestOutcomePatch:
    def test_acted_on_updates_doc(self, demo_token):
        s = _create_saved_suggestion(demo_token, f"acted_{int(time.time()*1000)}")
        sid = s["id"]
        r = requests.patch(f"{API}/procurement/suggestions/{sid}/outcome",
                           json={"outcome_type": "acted_on", "outcome_note": ""},
                           headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "acted_on"
        assert doc["outcome_type"] == "acted_on"
        assert doc.get("outcome_note", "") == ""
        assert doc.get("outcome_at")
        # ISO format check (parses)
        from datetime import datetime
        datetime.fromisoformat(doc["outcome_at"].replace("Z", "+00:00"))
        assert doc.get("outcome_by_user_id")
        # GET-verify persistence: appears in acted_on filter
        listing = requests.get(f"{API}/procurement/suggestions?status=acted_on",
                               headers=_hdrs(demo_token), timeout=30).json()
        assert any(it["id"] == sid for it in listing["items"])

    def test_not_pursued_with_note_persists(self, demo_token):
        s = _create_saved_suggestion(demo_token, f"np_{int(time.time()*1000)}")
        sid = s["id"]
        note = "Contract already signed for the quarter."
        r = requests.patch(f"{API}/procurement/suggestions/{sid}/outcome",
                           json={"outcome_type": "not_pursued", "outcome_note": note},
                           headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "not_pursued"
        assert doc["outcome_type"] == "not_pursued"
        assert doc["outcome_note"] == note

    def test_not_pursued_empty_note_allowed(self, demo_token):
        s = _create_saved_suggestion(demo_token, f"np_empty_{int(time.time()*1000)}")
        sid = s["id"]
        r = requests.patch(f"{API}/procurement/suggestions/{sid}/outcome",
                           json={"outcome_type": "not_pursued"},
                           headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["outcome_note"] == ""

    def test_invalid_outcome_type_returns_400(self, demo_token):
        s = _create_saved_suggestion(demo_token, f"bad_{int(time.time()*1000)}")
        sid = s["id"]
        for bad in ("order_placed", "executed", "purchased", ""):
            r = requests.patch(f"{API}/procurement/suggestions/{sid}/outcome",
                               json={"outcome_type": bad},
                               headers=_hdrs(demo_token), timeout=30)
            assert r.status_code in (400, 422), f"expected 400/422 for '{bad}', got {r.status_code}"

    def test_unknown_id_returns_404(self, demo_token):
        r = requests.patch(f"{API}/procurement/suggestions/does-not-exist-xyz-123/outcome",
                           json={"outcome_type": "acted_on"},
                           headers=_hdrs(demo_token), timeout=30)
        assert r.status_code == 404

    def test_multi_tenant_isolation_returns_404(self, demo_token, alt_token):
        # Create a suggestion in demo's tenant
        s = _create_saved_suggestion(demo_token, f"iso_{int(time.time()*1000)}")
        sid = s["id"]
        # Try to update from alt user in DIFFERENT restaurant
        r = requests.patch(f"{API}/procurement/suggestions/{sid}/outcome",
                           json={"outcome_type": "acted_on"},
                           headers=_hdrs(alt_token), timeout=30)
        # Must NOT succeed; must NOT leak existence — expect 404
        assert r.status_code == 404, f"tenant isolation broken: got {r.status_code} {r.text}"

    def test_unauth_returns_401(self):
        r = requests.patch(f"{API}/procurement/suggestions/whatever/outcome",
                           json={"outcome_type": "acted_on"},
                           headers={"Content-Type": "application/json"}, timeout=30)
        assert r.status_code in (401, 403)
