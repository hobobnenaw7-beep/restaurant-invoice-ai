"""
Milestone 23 iter100 — Live regression tests for PUT /api/items partial-update fix.

Specifically verifies:
  1. PUT /api/items/{id} with only `name` does NOT wipe `variants`.
  2. Autocomplete returns learned suggestions with composed "Canonical — Variant" label
     after explicit /link (even after a subsequent name-only rename of canonical).
  3. Archived canonical /link returns HTTP 400 with canonical_item_archived error.
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


# ────────── Test 1: PUT name-only preserves variants ──────────
def test_put_name_only_preserves_variants(token):
    name = f"TEST_PreserveVariants_{uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/items",
                   json={"name": name,
                         "variants": [
                             {"key": "male", "label": "Male"},
                             {"key": "female", "label": "Female"},
                         ]},
                   headers=H(token), timeout=15)
    assert r.status_code == 200, r.text
    canon_id = r.json()["id"]
    try:
        # PUT only name — should not strip variants
        new_name = name + "_Renamed"
        ru = httpx.put(f"{API}/items/{canon_id}", json={"name": new_name},
                       headers=H(token), timeout=15)
        assert ru.status_code == 200, ru.text

        # GET back — variants intact, name updated
        rg = httpx.get(f"{API}/items", headers=H(token),
                       params={"search": new_name}, timeout=15)
        rg.raise_for_status()
        found = [i for i in rg.json() if i["id"] == canon_id]
        assert found, "canonical not returned in GET list after rename"
        item = found[0]
        assert item["name"] == new_name
        variants = item.get("variants") or []
        keys = {(v.get("key") or "").lower() for v in variants}
        assert keys == {"male", "female"}, (
            f"variants were stripped/modified on PUT name-only: got {variants}"
        )
    finally:
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)


# ────────── Test 2: Learned-autocomplete composes "Canon — Variant" label ──────────
def test_learned_autocomplete_includes_variant_label(token):
    purchase = _first_purchase_with_items(token)
    if not purchase:
        pytest.skip("no purchases")
    pid = purchase["id"]
    idx = 0

    marker = uuid.uuid4().hex[:6]
    name = f"TEST_AutoCompose_{marker}"
    messy = f"tst-compose-{marker}-XYZ-#42"

    r = httpx.post(f"{API}/items",
                   json={"name": name,
                         "variants": [{"key": "male", "label": "Male"}]},
                   headers=H(token), timeout=15)
    assert r.status_code == 200
    canon_id = r.json()["id"]
    try:
        httpx.patch(f"{API}/purchases/{pid}/items/{idx}",
                    json={"raw_name": messy}, headers=H(token), timeout=15)
        rl = httpx.post(
            f"{API}/purchases/{pid}/items/{idx}/link",
            json={"canonical_item_id": canon_id, "variant_keys": ["male"]},
            headers=H(token), timeout=15,
        )
        assert rl.status_code == 200, rl.text

        # Simulate a subsequent name-only rename — must NOT wipe variants
        renamed = name + "_v2"
        ru = httpx.put(f"{API}/items/{canon_id}", json={"name": renamed},
                       headers=H(token), timeout=15)
        assert ru.status_code == 200, ru.text

        q = f"tst-compose-{marker}"
        ra = httpx.get(f"{API}/items/autocomplete",
                       params={"q": q, "limit": 10},
                       headers=H(token), timeout=15)
        ra.raise_for_status()
        suggestions = ra.json()["suggestions"]
        assert suggestions, f"no autocomplete suggestions for '{q}'"

        learned = [s for s in suggestions
                   if s.get("canonical_item_id") == canon_id
                   and s.get("source") == "learned"]
        assert learned, (
            f"no learned suggestion with canonical_item_id={canon_id}: "
            f"got {suggestions}"
        )
        s = learned[0]
        vk = s.get("variant_keys") or ([s["variant_key"]] if s.get("variant_key") else [])
        assert "male" in [x.lower() for x in vk], (
            f"learned suggestion missing variant_keys=['male']: {s}"
        )
        # Label must compose "Canonical — Male" even after rename
        assert "Male" in s["label"] and " — " in s["label"], (
            f"learned label did not compose variant text: {s['label']}"
        )
    finally:
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)


# ────────── Test 3: Archived canonical /link rejection ──────────
def test_archived_canonical_link_returns_400(token):
    purchase = _first_purchase_with_items(token)
    if not purchase:
        pytest.skip("no purchases")
    pid = purchase["id"]
    idx = 0

    name = f"TEST_ArchLink_{uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/items", json={"name": name},
                   headers=H(token), timeout=15)
    assert r.status_code == 200
    canon_id = r.json()["id"]

    # No public PUT field for is_archived on approved items (CanonicalItemCreate
    # doesn't expose it). Flip directly in DB to exercise the /link guard.
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _flip():
        mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        db_name = os.environ.get("DB_NAME") or "test_database"
        # Parse backend/.env for MONGO_URL if not in env
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.strip().split("=", 1)[1].strip('"').strip("'")
                    elif line.startswith("DB_NAME="):
                        db_name = line.strip().split("=", 1)[1].strip('"').strip("'")
        except FileNotFoundError:
            pass
        client = AsyncIOMotorClient(mongo_url)
        await client[db_name].canonical_items.update_one(
            {"id": canon_id}, {"$set": {"is_archived": True}}
        )
        client.close()
    asyncio.run(_flip())

    try:
        # Verify persisted
        rg = httpx.get(f"{API}/items",
                       params={"status": "archived"},
                       headers=H(token), timeout=15)
        rg.raise_for_status()
        ids = [i["id"] for i in rg.json()]
        assert canon_id in ids, "archive flag did not persist (DB flip failed)"

        # Now /link must reject
        rl = httpx.post(
            f"{API}/purchases/{pid}/items/{idx}/link",
            json={"canonical_item_id": canon_id},
            headers=H(token), timeout=15,
        )
        assert rl.status_code == 400, (
            f"expected 400 on archived /link; got {rl.status_code}: {rl.text}"
        )
        body = rl.json()
        err = (body.get("detail") or body.get("error") or body.get("message") or "").lower()
        assert "archiv" in err, f"expected archive-related error; got {body}"
    finally:
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)
