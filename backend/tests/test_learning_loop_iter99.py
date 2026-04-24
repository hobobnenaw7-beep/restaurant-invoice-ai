"""
Milestone 23 — Full learning-loop + multi-variant E2E tests.

Validates the closed loop:
    OCR-like raw → manual link → alias + correction memory saved
    → autocomplete surfaces the learned pair later
    → canonical rename propagates to all reads
    → multi-variant link composes "[Canonical] — v1 — v2"
"""
from __future__ import annotations

import os
import uuid
import pytest
import httpx


def _base_url() -> str | None:
    if os.environ.get("BASE_URL"):
        return os.environ["BASE_URL"]
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass
    return None


BASE = _base_url()
API = f"{BASE}/api" if BASE else None


@pytest.fixture(scope="module")
def token() -> str:
    if not API:
        pytest.skip("BASE_URL not available")
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "demo@test.com", "password": "testpassword"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def H(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _first_purchase_with_items(token):
    r = httpx.get(f"{API}/purchases", headers=H(token), timeout=30)
    r.raise_for_status()
    for p in r.json():
        if p.get("items"):
            return p
    return None


# ─────────────────── Test 1: multi-variant link ───────────────────
def test_multi_variant_link_composes_display_name(token):
    purchase = _first_purchase_with_items(token)
    if not purchase:
        pytest.skip("no purchases")
    pid = purchase["id"]
    idx = 0

    name = f"Live Blue Crab {uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/items",
                   json={"name": name,
                         "variants": [
                             {"key": "male", "label": "Male"},
                             {"key": "large", "label": "Large"},
                             {"key": "female", "label": "Female"},
                         ]},
                   headers=H(token), timeout=15)
    assert r.status_code == 200, r.text
    canon_id = r.json()["id"]

    try:
        rl = httpx.post(
            f"{API}/purchases/{pid}/items/{idx}/link",
            json={"canonical_item_id": canon_id, "variant_keys": ["male", "large"]},
            headers=H(token), timeout=15,
        )
        assert rl.status_code == 200, rl.text
        body = rl.json()
        assert set(body.get("variant_keys") or []) == {"male", "large"}
        # Composed display_name must include BOTH variants in "— v1 — v2" form
        dn = body["display_name"]
        assert "Male" in dn and "Large" in dn
        assert " — " in dn

        # Read back via /purchases to confirm enrichment
        rp = httpx.get(f"{API}/purchases/{pid}", headers=H(token), timeout=15)
        rp.raise_for_status()
        fresh = rp.json()["items"][idx]
        assert set(fresh.get("variant_keys") or []) == {"male", "large"}
        assert "Male" in fresh["display_name"] and "Large" in fresh["display_name"]
    finally:
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)


# ─────────────────── Test 2: learning loop via autocomplete ───────────────────
def test_learning_loop_surfaces_in_autocomplete(token):
    purchase = _first_purchase_with_items(token)
    if not purchase:
        pytest.skip("no purchases")
    pid = purchase["id"]
    idx = 0

    marker = uuid.uuid4().hex[:6]
    name = f"Learned Item {marker}"
    messy = f"lrnd-itm-{marker}-XYZ-435 #"  # OCR-noisy raw

    # Seed the canonical + link messy raw to it via explicit link
    r = httpx.post(f"{API}/items",
                   json={"name": name,
                         "variants": [{"key": "male", "label": "Male"}]},
                   headers=H(token), timeout=15)
    assert r.status_code == 200
    canon_id = r.json()["id"]

    try:
        # First, PATCH the invoice row to carry the messy raw_name so alias
        # learning has something to hook onto.
        httpx.patch(f"{API}/purchases/{pid}/items/{idx}",
                    json={"raw_name": messy}, headers=H(token), timeout=15)
        # Now explicitly link with variant
        rl = httpx.post(
            f"{API}/purchases/{pid}/items/{idx}/link",
            json={"canonical_item_id": canon_id, "variant_keys": ["male"]},
            headers=H(token), timeout=15,
        )
        assert rl.status_code == 200, rl.text

        # The learning loop must have created BOTH an alias AND a correction-memory row.
        rc = httpx.get(f"{API}/correction-memory", headers=H(token), timeout=15)
        rc.raise_for_status()
        found = [m for m in rc.json()
                 if (m.get("original_raw_name") or "").lower() == messy.lower()]
        assert found, "correction memory row not created by explicit link"
        assert found[0].get("corrected_name") == name
        # Variant tags stored
        assert "male" in (found[0].get("variant_keys") or [])

        # Autocomplete must now surface the learned pairing for a short prefix
        # of the messy raw name.
        q = f"lrnd-itm-{marker}"
        ra = httpx.get(f"{API}/items/autocomplete",
                       params={"q": q, "limit": 10},
                       headers=H(token), timeout=15)
        ra.raise_for_status()
        suggestions = ra.json()["suggestions"]
        assert suggestions, f"no autocomplete suggestions for '{q}'"
        assert any(s["canonical_item_id"] == canon_id for s in suggestions), \
            f"learned canonical {canon_id} not returned in autocomplete"
        # The learned row should carry variant_keys
        learned = next(s for s in suggestions if s["canonical_item_id"] == canon_id)
        assert ("male" in (learned.get("variant_keys") or [])
                or learned.get("variant_key") == "male"
                or "Male" in learned["label"])
    finally:
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)


# ─────────────────── Test 3: rename propagation ───────────────────
def test_canonical_rename_propagates_to_all_reads(token):
    purchase = _first_purchase_with_items(token)
    if not purchase:
        pytest.skip("no purchases")
    pid = purchase["id"]
    idx = 0

    old_name = f"Rename Before {uuid.uuid4().hex[:6]}"
    new_name = f"Rename After {uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/items", json={"name": old_name},
                   headers=H(token), timeout=15)
    assert r.status_code == 200
    cid = r.json()["id"]
    try:
        rl = httpx.post(
            f"{API}/purchases/{pid}/items/{idx}/link",
            json={"canonical_item_id": cid},
            headers=H(token), timeout=15,
        )
        assert rl.status_code == 200

        # Verify invoice line now shows the OLD canonical name
        rp = httpx.get(f"{API}/purchases/{pid}", headers=H(token), timeout=15)
        assert old_name in rp.json()["items"][idx]["display_name"]

        # Rename the canonical
        ru = httpx.put(f"{API}/items/{cid}",
                       json={"name": new_name},
                       headers=H(token), timeout=15)
        assert ru.status_code == 200

        # Invoice list reflects new name WITHOUT touching the purchase doc
        rp2 = httpx.get(f"{API}/purchases/{pid}", headers=H(token), timeout=15)
        fresh = rp2.json()["items"][idx]
        assert fresh["canonical_name"] == new_name
        assert new_name in fresh["display_name"]
        # Raw name untouched — invoice→canonical isolation preserved
        assert "raw_name" in fresh
    finally:
        httpx.delete(f"{API}/items/{cid}", headers=H(token), timeout=15)
