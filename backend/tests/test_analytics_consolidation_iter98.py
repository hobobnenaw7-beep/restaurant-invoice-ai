"""
Milestone 20 — Analytics Consolidation proof (iter_98)
=========================================================

End-to-end live HTTP test. Seeds two purchase rows for the SAME product
with different OCR-noisy raw_names, then asserts:
  • vendor-comparison now returns ONE row (consolidated by canonical id)
  • price-history on the canonical item returns BOTH purchase lines
  • the fragmented raw_names never appear as separate rows in
    vendor-comparison
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


def test_identity_based_analytics_consolidation(token: str):
    suffix = uuid.uuid4().hex[:6]
    canonical_name = f"Widget-{suffix}"

    # 1) Create one approved canonical item
    r = httpx.post(f"{API}/items", json={"name": canonical_name},
                   headers=H(token), timeout=15)
    assert r.status_code == 200, r.text
    canon_id = r.json()["id"]

    # 2) Make sure a vendor exists
    rv = httpx.get(f"{API}/suppliers", headers=H(token), timeout=15)
    rv.raise_for_status()
    vendors = rv.json()
    assert vendors, "need at least one vendor in test DB"
    vendor = vendors[0]
    vname = vendor.get("name")
    assert vname

    # 3) Seed two purchases whose raw_name values differ (OCR-noisy), but
    #    both link to the same canonical via canonical_item_id.
    created_pids = []
    try:
        for i, raw in enumerate([f"Widget -{suffix}", f"W1dg3t-{suffix}", f"widget   {suffix}"]):
            total = (1 + i) * (10.0 + i)
            payload = {
                "supplier_id": vendor["id"],
                "supplier_name": vname,
                "invoice_number": f"TEST-IDMIG-{suffix}-{i}",
                "invoice_date": "2026-02-10",
                "items": [{
                    "raw_name": raw,
                    "quantity": 1 + i,
                    "unit_price": 10.0 + i,
                    "total": total,
                    "canonical_item_id": canon_id,
                }],
                "subtotal": total,
                "tax": 0.0,
                "total": total,
            }
            rc = httpx.post(f"{API}/purchases", json=payload,
                            headers=H(token), timeout=15)
            assert rc.status_code == 200, rc.text
            created_pids.append(rc.json()["id"])

        # 4) vendor-comparison must surface EXACTLY ONE row for our canonical
        rc = httpx.get(f"{API}/prices/vendor-comparison",
                       headers=H(token), timeout=30)
        rc.raise_for_status()
        data = rc.json()
        matching = [
            it for it in data["items"]
            if it.get("group_key") == f"canon::{canon_id}"
        ]
        assert len(matching) == 1, (
            f"Expected exactly one consolidated row for canonical "
            f"{canon_id}; got {len(matching)}"
        )
        # Display label must be the canonical name (not any raw variant)
        assert matching[0]["item"] == canonical_name
        # None of the raw variants should appear as separate rows
        raw_names = {f"Widget -{suffix}", f"W1dg3t-{suffix}", f"widget   {suffix}"}
        for it in data["items"]:
            assert it["item"] not in raw_names, (
                f"raw_name {it['item']!r} leaked into vendor-comparison"
            )

        # 5) price-history on the canonical returns all 3 seeded records
        rh = httpx.get(f"{API}/items/{canon_id}/price-history",
                       headers=H(token), timeout=30)
        rh.raise_for_status()
        phist = rh.json()
        # Tolerate extra unrelated records by filtering to our invoice numbers
        our = [r for r in phist.get("records", []) if r.get("vendor") == vname]
        assert len(our) >= 3, (
            f"Expected >=3 price-history records for {canonical_name}, got {len(our)}"
        )

    finally:
        for pid in created_pids:
            httpx.delete(f"{API}/purchases/{pid}", headers=H(token), timeout=15)
        httpx.delete(f"{API}/items/{canon_id}", headers=H(token), timeout=15)
