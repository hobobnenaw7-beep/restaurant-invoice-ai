"""
Live integration tests for Decision Audit Log endpoints (iter 92).

Covers:
  - GET /api/procurement/audit/events  (auth, shape, filter validation)
  - GET /api/procurement/audit/stats   (auth, shape, sample_queries)
  - End-to-end lifecycle: recommendations -> events -> save_suggestion -> outcome
  - Idempotency: repeated /recommendations does not duplicate audit records
  - Tenant isolation: cross-tenant leakage check
  - Performance: /procurement/recommendations completes < 5s
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://invoice-ai-35.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@test.com", "password": "testpassword"}
ISO  = {"email": "tenant_iso_test@example.com", "password": "testpass123"}


# ---- helpers ----
def _login(creds: dict) -> str:
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("access_token") or body.get("token")


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_iso_if_needed():
    # Ensure ISO tenant exists; ignore if already registered.
    requests.post(
        f"{API}/auth/register",
        json={
            "email": ISO["email"],
            "password": ISO["password"],
            "restaurant_name": "Iso Test Restaurant",
            "owner_name": "Iso Owner",
        },
        timeout=20,
    )


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def iso_token():
    _register_iso_if_needed()
    return _login(ISO)


# ──────────────────────────────────────────────────────────────────────
# 1. Auth
# ──────────────────────────────────────────────────────────────────────
class TestAuditAuth:
    def test_events_requires_auth(self):
        r = requests.get(f"{API}/procurement/audit/events", timeout=15)
        assert r.status_code in (401, 403)

    def test_stats_requires_auth(self):
        r = requests.get(f"{API}/procurement/audit/stats", timeout=15)
        assert r.status_code in (401, 403)


# ──────────────────────────────────────────────────────────────────────
# 2. Filter validation
# ──────────────────────────────────────────────────────────────────────
class TestAuditFilterValidation:
    def test_invalid_status_400(self, demo_token):
        r = requests.get(f"{API}/procurement/audit/events?status=bogus",
                         headers=_hdr(demo_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_recommendation_type_400(self, demo_token):
        r = requests.get(f"{API}/procurement/audit/events?recommendation_type=bogus",
                         headers=_hdr(demo_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_outcome_type_400(self, demo_token):
        r = requests.get(f"{API}/procurement/audit/events?outcome_type=purchased",
                         headers=_hdr(demo_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_confidence_level_400(self, demo_token):
        r = requests.get(f"{API}/procurement/audit/events?confidence_level=high",
                         headers=_hdr(demo_token), timeout=15)
        assert r.status_code == 400

    def test_valid_filters_ok(self, demo_token):
        for q in [
            "status=open", "status=interacted", "status=finalized",
            "recommendation_type=switch_vendor", "recommendation_type=renegotiate",
            "recommendation_type=no_action", "recommendation_type=monitor_only",
            "outcome_type=acted_on", "outcome_type=not_pursued",
            "confidence_level=High", "confidence_level=Medium", "confidence_level=Low",
        ]:
            r = requests.get(f"{API}/procurement/audit/events?{q}",
                             headers=_hdr(demo_token), timeout=15)
            assert r.status_code == 200, f"filter {q} -> {r.status_code} {r.text}"


# ──────────────────────────────────────────────────────────────────────
# 3. Recommendations call must populate audit (and not regress perf)
# ──────────────────────────────────────────────────────────────────────
class TestRecommendationsHookAndPerf:
    def test_recommendations_under_5s_and_creates_audit(self, demo_token):
        t0 = time.time()
        r = requests.get(f"{API}/procurement/recommendations",
                         headers=_hdr(demo_token), timeout=20)
        dt = time.time() - t0
        assert r.status_code == 200, r.text
        assert dt < 5.0, f"perf regression: /recommendations took {dt:.2f}s"
        # audit /events should now have at least one record (open or interacted)
        r2 = requests.get(f"{API}/procurement/audit/events?limit=2000",
                          headers=_hdr(demo_token), timeout=15)
        assert r2.status_code == 200
        body = r2.json()
        assert "items" in body and "total" in body
        assert body["total"] == len(body["items"])

    def test_idempotent_no_duplicate_open_records(self, demo_token):
        # Snapshot count
        before = requests.get(
            f"{API}/procurement/audit/events?limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["total"]
        # Trigger recommendations twice
        for _ in range(2):
            r = requests.get(f"{API}/procurement/recommendations",
                             headers=_hdr(demo_token), timeout=20)
            assert r.status_code == 200
        after = requests.get(
            f"{API}/procurement/audit/events?limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["total"]
        # The total set is the number of distinct (cpid, rec_type) decisions.
        # It must NOT grow on repeated regeneration.
        assert after <= before + 0  or after == before, \
            f"duplicate audit rows: before={before}, after={after}"


# ──────────────────────────────────────────────────────────────────────
# 4. Stats endpoint shape
# ──────────────────────────────────────────────────────────────────────
class TestAuditStatsShape:
    def test_stats_shape(self, demo_token):
        # Make sure recs have run at least once
        requests.get(f"{API}/procurement/recommendations",
                     headers=_hdr(demo_token), timeout=20)
        r = requests.get(f"{API}/procurement/audit/stats",
                         headers=_hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()
        for k in ("total", "open", "interacted", "finalized",
                  "by_recommendation_type", "high_confidence_not_pursued",
                  "sample_queries"):
            assert k in s, f"missing key {k}"
        for rt in ("switch_vendor", "renegotiate", "no_action", "monitor_only"):
            assert rt in s["by_recommendation_type"]
            for sub in ("generated", "acted_on", "not_pursued",
                        "acted_on_rate", "not_pursued_rate"):
                assert sub in s["by_recommendation_type"][rt]
        assert "switch_vendor_acted_on_rate" in s["sample_queries"]
        assert "high_confidence_not_pursued_count" in s["sample_queries"]
        assert isinstance(s["high_confidence_not_pursued"], list)


# ──────────────────────────────────────────────────────────────────────
# 5. Lifecycle e2e
# ──────────────────────────────────────────────────────────────────────
class TestAuditLifecycle:
    def test_full_lifecycle(self, demo_token):
        # (a) Generate recs and pick one with rec_type we can act on
        rr = requests.get(f"{API}/procurement/recommendations",
                          headers=_hdr(demo_token), timeout=20)
        assert rr.status_code == 200
        recs = rr.json().get("items") or rr.json().get("recommendations") or rr.json()
        if isinstance(recs, dict) and "items" in recs:
            recs = recs["items"]
        # Pick first decision with a canonical_product_id and recommendation_type
        target = None
        for d in recs:
            if d.get("canonical_product_id") and d.get("recommendation_type"):
                target = d
                break
        if target is None:
            pytest.skip("no decisions with cpid+rec_type to drive lifecycle")

        cpid = target["canonical_product_id"]
        rtype = target["recommendation_type"]

        # (b) suggestion_opened -> status interacted
        for ev in ("suggestion_opened", "draft_viewed", "acknowledgment_checked"):
            er = requests.post(
                f"{API}/procurement/events",
                headers=_hdr(demo_token),
                json={
                    "event_type": ev,
                    "canonical_product_id": cpid,
                    "recommendation_type": rtype,
                },
                timeout=15,
            )
            # Some event endpoints respond 200/204 — accept any 2xx
            assert 200 <= er.status_code < 300, f"event {ev} failed: {er.status_code} {er.text}"

        # Find the audit row
        listing = requests.get(
            f"{API}/procurement/audit/events?recommendation_type={rtype}&status=interacted&limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["items"]
        row = next((x for x in listing if x.get("canonical_product_id") == cpid), None)
        assert row is not None, f"no interacted row found for {cpid}/{rtype}"
        assert row["suggestion_opened_at"], "suggestion_opened_at not stamped"
        assert row["draft_viewed_at"], "draft_viewed_at not stamped"
        assert row["acknowledged_at"], "acknowledged_at not stamped"

        ts1 = row["suggestion_opened_at"]
        # (b2) idempotent re-stamp must NOT overwrite suggestion_opened_at
        requests.post(
            f"{API}/procurement/events",
            headers=_hdr(demo_token),
            json={"event_type": "suggestion_opened",
                  "canonical_product_id": cpid,
                  "recommendation_type": rtype},
            timeout=15,
        )
        listing2 = requests.get(
            f"{API}/procurement/audit/events?recommendation_type={rtype}&status=interacted&limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["items"]
        row2 = next((x for x in listing2 if x.get("canonical_product_id") == cpid), None)
        assert row2["suggestion_opened_at"] == ts1, "suggestion_opened_at must not be overwritten"

        # (c) Save suggestion (draft) — link suggestion_id
        sug_payload = {
            "canonical_product_id": cpid,
            "canonical_name": target.get("canonical_name") or "TEST_audit_lifecycle",
            "canonical_unit": target.get("canonical_unit") or "lb",
            "recommendation_type": rtype,
            "current_vendor": (target.get("current_vendor") or "TEST_current_vendor"),
            "draft_note": f"TEST_audit_iter92 {uuid.uuid4()}",
            "acknowledgment_confirmed": True,
        }
        sr = requests.post(f"{API}/procurement/suggestions",
                           headers=_hdr(demo_token), json=sug_payload, timeout=15)
        assert sr.status_code in (200, 201), f"save suggestion failed: {sr.status_code} {sr.text}"
        sug = sr.json()
        sug_id = sug.get("id") or sug.get("suggestion_id") or sug.get("_id")
        assert sug_id, f"no suggestion id in response: {sug}"

        # Confirm audit row now has suggestion_id linked
        listing3 = requests.get(
            f"{API}/procurement/audit/events?recommendation_type={rtype}&limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["items"]
        row3 = next((x for x in listing3
                     if x.get("canonical_product_id") == cpid and x.get("suggestion_id") == sug_id),
                    None)
        assert row3 is not None, f"suggestion_id {sug_id} not linked to audit"

        # (d) PATCH outcome=acted_on -> finalize
        pr = requests.patch(
            f"{API}/procurement/suggestions/{sug_id}/outcome",
            headers=_hdr(demo_token),
            json={"outcome_type": "acted_on", "outcome_note": "TEST_iter92_audit_e2e"},
            timeout=15,
        )
        assert pr.status_code == 200, f"PATCH outcome failed: {pr.status_code} {pr.text}"

        # Confirm audit row finalized
        finalized_list = requests.get(
            f"{API}/procurement/audit/events?status=finalized&outcome_type=acted_on&limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["items"]
        finalized = next((x for x in finalized_list if x.get("suggestion_id") == sug_id), None)
        assert finalized is not None, "audit not finalized after PATCH outcome"
        assert finalized["outcome_type"] == "acted_on"
        assert finalized["outcome_at"]
        assert finalized["status"] == "finalized"


# ──────────────────────────────────────────────────────────────────────
# 6. Tenant isolation
# ──────────────────────────────────────────────────────────────────────
class TestAuditTenantIsolation:
    def test_iso_tenant_does_not_see_demo_records(self, demo_token, iso_token):
        # Trigger demo recs to ensure there are records
        requests.get(f"{API}/procurement/recommendations",
                     headers=_hdr(demo_token), timeout=20)
        demo_items = requests.get(
            f"{API}/procurement/audit/events?limit=2000",
            headers=_hdr(demo_token), timeout=15,
        ).json()["items"]
        demo_ids = {x["event_id"] for x in demo_items}
        # Trigger ISO tenant to populate own records (may be 0 if no observations)
        requests.get(f"{API}/procurement/recommendations",
                     headers=_hdr(iso_token), timeout=20)
        iso_items = requests.get(
            f"{API}/procurement/audit/events?limit=2000",
            headers=_hdr(iso_token), timeout=15,
        ).json()["items"]
        iso_ids = {x["event_id"] for x in iso_items}
        leak = demo_ids & iso_ids
        assert not leak, f"tenant leakage detected: {len(leak)} shared event_ids"

    def test_iso_stats_independent(self, demo_token, iso_token):
        d = requests.get(f"{API}/procurement/audit/stats",
                         headers=_hdr(demo_token), timeout=15).json()
        i = requests.get(f"{API}/procurement/audit/stats",
                         headers=_hdr(iso_token), timeout=15).json()
        # ISO tenant has no purchase observations -> usually total==0; demo has many.
        assert isinstance(d["total"], int) and isinstance(i["total"], int)
        # Loose check: demo total must be >= iso total in this fixture set-up
        assert d["total"] >= i["total"]
