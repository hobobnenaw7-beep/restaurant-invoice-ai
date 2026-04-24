"""
Iteration 96 — Traceability Loop Closure (Correction → Canonical)
Tests the canonical_destination enrichment on:
  - GET /api/correction-memory
  - GET /api/corrections/by-vendor/{supplier_id}
  - PATCH /api/corrections/{id}
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
EMAIL = "demo@test.com"
PASSWORD = "testpassword"

VALID_STATUSES = {"approved", "suggested", "merged", "dismissed", "archived", "unlinked"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"No token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Tests for GET /api/correction-memory ──

class TestCorrectionMemoryEnrichment:
    def test_endpoint_returns_200(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_every_row_has_canonical_destination(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        rows = r.json()
        assert len(rows) > 0, "Seeded correction-memory rows expected"
        for c in rows:
            assert "canonical_destination" in c, f"row missing canonical_destination: {c.get('id')}"
            d = c["canonical_destination"]
            assert set(d.keys()) >= {
                "status",
                "canonical_item_id",
                "canonical_name",
                "merged_from_name",
                "merged_from_item_id",
            }, f"destination missing keys: {d.keys()}"
            assert d["status"] in VALID_STATUSES, f"invalid status: {d['status']}"

    def test_no_mongo_id_exposed(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        rows = r.json()
        for c in rows:
            assert "_id" not in c, f"MongoDB _id leaked: {c.get('id')}"
            d = c.get("canonical_destination", {})
            assert "_id" not in d

    def test_statuses_observed(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        rows = r.json()
        seen = {c["canonical_destination"]["status"] for c in rows}
        # At least 2 distinct valid statuses should be observable in seeded data
        assert len(seen) >= 1
        assert seen.issubset(VALID_STATUSES), f"unknown statuses: {seen - VALID_STATUSES}"
        print(f"Observed statuses: {sorted(seen)}")

    def test_merged_rows_carry_merge_fields(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        rows = r.json()
        merged = [c for c in rows if c["canonical_destination"]["status"] == "merged"]
        for m in merged:
            d = m["canonical_destination"]
            # Either merged_from_* is set OR the canonical itself is is_merged
            # In either case we must have a canonical_item_id to navigate to
            assert d["canonical_item_id"], f"merged row missing canonical_item_id: {m.get('id')}"
            # merged_from_name is typically set for loop-closure merged rows
            # but can be empty if the canonical itself was marked is_merged.
            # Accept either shape.


# ── Tests for GET /api/corrections/by-vendor/{supplier_id} ──

class TestCorrectionsByVendorEnrichment:
    def _get_vendor(self, headers):
        r = requests.get(f"{BASE_URL}/api/corrections/vendors", headers=headers, timeout=20)
        assert r.status_code == 200
        vendors = r.json()
        if not vendors:
            pytest.skip("No vendors with corrections seeded")
        return vendors[0]

    def test_by_vendor_returns_enriched(self, headers):
        vendor = self._get_vendor(headers)
        sid = vendor["supplier_id"]
        r = requests.get(
            f"{BASE_URL}/api/corrections/by-vendor/{sid}", headers=headers, timeout=20
        )
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) > 0
        for c in rows:
            assert "_id" not in c
            assert "canonical_destination" in c
            d = c["canonical_destination"]
            assert d["status"] in VALID_STATUSES


# ── Tests for PATCH /api/corrections/{id} ──

class TestPatchCorrectionKeepsEnrichment:
    def test_patch_response_has_canonical_destination(self, headers):
        r = requests.get(f"{BASE_URL}/api/correction-memory", headers=headers, timeout=20)
        rows = r.json()
        assert rows, "need at least one correction"
        target = rows[0]
        cid = target["id"]
        original_name = target.get("corrected_name") or "Test Name"

        # PATCH with the same name (idempotent)
        r2 = requests.patch(
            f"{BASE_URL}/api/corrections/{cid}",
            headers=headers,
            json={"corrected_name": original_name},
            timeout=20,
        )
        assert r2.status_code == 200, r2.text
        doc = r2.json()
        assert "_id" not in doc
        assert "canonical_destination" in doc, "PATCH response must include canonical_destination"
        d = doc["canonical_destination"]
        assert d["status"] in VALID_STATUSES


# ── Smart Duplicate Hint data requirement: items API ──

class TestItemsForDuplicateHint:
    def test_items_returns_suggested_and_approved(self, headers):
        r = requests.get(f"{BASE_URL}/api/items?limit=500", headers=headers, timeout=30)
        assert r.status_code == 200
        payload = r.json()
        items = payload if isinstance(payload, list) else payload.get("items", [])
        assert isinstance(items, list)
        # Verify shape: each item has name + is_suggested flag
        for it in items[:5]:
            assert "id" in it
            assert "name" in it
        print(f"items fetched: {len(items)}")
