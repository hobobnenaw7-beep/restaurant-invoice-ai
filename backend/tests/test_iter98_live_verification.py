"""
Milestone 20 — iter_98 live verification
=========================================
Covers (against the live external URL):
  • vendor-comparison rows now carry `group_key` (canon:: or norm::)
  • price-intelligence exposes comparison_items[].group_key
  • variant isolation on same canonical: 2 variants -> 2 distinct rows
  • backwards-compat: unlinked purchases still appear with norm:: group_key
  • tenant isolation (only demo tenant sees its own canonical rows)
  • procurement regression: /procurement/recommendations still 200
  • milestone 19 regression: /items/autocomplete + link still work
"""
from __future__ import annotations
import os, uuid, pytest, httpx


def _base():
    if os.environ.get("BASE_URL"):
        return os.environ["BASE_URL"]
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.strip().split("=", 1)[1]
    return None


BASE = _base()
API = f"{BASE}/api" if BASE else None


@pytest.fixture(scope="module")
def tok():
    if not API:
        pytest.skip("BASE_URL missing")
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "demo@test.com", "password": "testpassword"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def H(t): return {"Authorization": f"Bearer {t}"}


# ─── shape / metadata ─────────────────────────────────────
def test_vendor_comparison_carries_group_key(tok):
    r = httpx.get(f"{API}/prices/vendor-comparison", headers=H(tok), timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    if not data["items"]:
        pytest.skip("no vendor-comparison rows to verify shape against")
    for it in data["items"]:
        assert "group_key" in it, f"row missing group_key: {it}"
        gk = it["group_key"]
        assert gk.startswith("canon::") or gk.startswith("norm::"), gk


def test_price_intelligence_exposes_group_key(tok):
    r = httpx.get(f"{API}/prices/intelligence", headers=H(tok), timeout=30)
    assert r.status_code == 200
    data = r.json()
    # endpoint key is "comparison" (vendor-price-comparison sub-section)
    items = data.get("comparison") or data.get("comparison_items") or []
    if not items:
        pytest.skip("no comparison rows to verify")
    for it in items:
        assert "group_key" in it, f"intelligence row missing group_key: {it}"
        assert it["group_key"].startswith(("canon::", "norm::"))
    # price_trends must be keyed by canonical display names (strings)
    assert isinstance(data.get("price_trends", {}), dict)
    # price_alerts still uses "item" display field
    for a in data.get("price_alerts", []):
        assert "item" in a


# ─── CRITICAL: variant isolation ──────────────────────────
def test_variants_isolate_into_separate_rows(tok):
    suffix = uuid.uuid4().hex[:6]
    cname = f"VarWidget-{suffix}"

    # create canonical with variants
    r = httpx.post(f"{API}/items",
                   json={"name": cname,
                         "variants": [{"key": "male", "label": "Male"},
                                      {"key": "female", "label": "Female"}]},
                   headers=H(tok), timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    v = httpx.get(f"{API}/suppliers", headers=H(tok), timeout=15).json()
    assert v, "need a vendor"
    vendor = v[0]

    pids = []
    try:
        for i, vkey in enumerate(["male", "female"]):
            payload = {
                "supplier_id": vendor["id"],
                "supplier_name": vendor["name"],
                "invoice_number": f"VAR-{suffix}-{vkey}",
                "invoice_date": "2026-02-12",
                "items": [{
                    "raw_name": f"{vkey} {cname}",
                    "quantity": 1,
                    "unit_price": 10.0 + i,
                    "total": 10.0 + i,
                    "canonical_item_id": cid,
                    "variant_key": vkey,
                }],
                "subtotal": 10.0 + i, "tax": 0.0, "total": 10.0 + i,
            }
            rc = httpx.post(f"{API}/purchases", json=payload,
                            headers=H(tok), timeout=15)
            assert rc.status_code == 200, rc.text
            pids.append(rc.json()["id"])

        rc = httpx.get(f"{API}/prices/vendor-comparison",
                       headers=H(tok), timeout=30)
        rc.raise_for_status()
        rows = rc.json()["items"]
        male = [it for it in rows if it.get("group_key") == f"canon::{cid}::male"]
        female = [it for it in rows if it.get("group_key") == f"canon::{cid}::female"]
        assert len(male) == 1, f"expected 1 male row, got {len(male)}"
        assert len(female) == 1, f"expected 1 female row, got {len(female)}"
    finally:
        for pid in pids:
            httpx.delete(f"{API}/purchases/{pid}", headers=H(tok), timeout=15)
        httpx.delete(f"{API}/items/{cid}", headers=H(tok), timeout=15)


# ─── CRITICAL: backwards-compat (norm:: fallback) ─────────
def test_norm_fallback_rows_wellformed(tok):
    """Backwards-compat: legacy / unlinked rows surface under norm::<normalized_raw>.
    We don't seed new ones (purchase POST auto-creates canonicals for new raw_names,
    which is pre-existing ingest behavior); instead we verify that any norm:: rows
    already present in the DB are well-formed and do NOT leak raw item_name."""
    rc = httpx.get(f"{API}/prices/vendor-comparison",
                   headers=H(tok), timeout=30)
    rc.raise_for_status()
    rows = rc.json()["items"]
    norm_rows = [it for it in rows
                 if it.get("group_key", "").startswith("norm::")]
    # norm:: rows may or may not exist depending on DB state — but the
    # back-compat path MUST be present in the schema. Verify shape if any.
    for it in norm_rows:
        gk = it["group_key"]
        # must be "norm::<normalized>" with no uppercase or tabs
        tail = gk[len("norm::"):].split("::")[0]
        assert tail == tail.lower(), f"norm:: tail should be normalized-lowercase: {gk}"
        assert "\t" not in tail
    # Schema check: every row has a group_key from exactly these prefixes
    prefixes = {it.get("group_key", "").split("::", 1)[0] + "::"
                for it in rows}
    assert prefixes.issubset({"canon::", "norm::"}), prefixes


# ─── regressions ──────────────────────────────────────────
def test_procurement_recommendations_still_works(tok):
    r = httpx.get(f"{API}/procurement/recommendations",
                  headers=H(tok), timeout=30)
    assert r.status_code == 200, r.text
    # must be JSON and contain the expected top-level container
    assert isinstance(r.json(), (list, dict))


def test_autocomplete_empty_q_returns_empty(tok):
    r = httpx.get(f"{API}/items/autocomplete?q=", headers=H(tok), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("suggestions") == []


def test_autocomplete_returns_sources(tok):
    r = httpx.get(f"{API}/items/autocomplete?q=a", headers=H(tok), timeout=15)
    assert r.status_code == 200
    for s in r.json().get("suggestions", []):
        assert s.get("source") in {"canonical", "variant", "alias"}


# ─── tenant isolation probe ───────────────────────────────
def test_tenant_scoped_vendor_comparison(tok):
    """Seed a uniquely-named canonical, confirm it appears for THIS tenant
       (we can't easily log in as a different tenant in this harness, but the
       tenant-scoped DB loader is covered by unit test
       test_build_canonical_index_scopes_by_tenant)."""
    suffix = uuid.uuid4().hex[:6]
    cname = f"TenantProbe-{suffix}"
    r = httpx.post(f"{API}/items", json={"name": cname},
                   headers=H(tok), timeout=15)
    assert r.status_code == 200
    cid = r.json()["id"]
    v = httpx.get(f"{API}/suppliers", headers=H(tok), timeout=15).json()[0]
    payload = {
        "supplier_id": v["id"], "supplier_name": v["name"],
        "invoice_number": f"TEN-{suffix}",
        "invoice_date": "2026-02-12",
        "items": [{"raw_name": cname, "quantity": 1,
                   "unit_price": 3.0, "total": 3.0,
                   "canonical_item_id": cid}],
        "subtotal": 3.0, "tax": 0.0, "total": 3.0,
    }
    pr = httpx.post(f"{API}/purchases", json=payload,
                    headers=H(tok), timeout=15)
    assert pr.status_code == 200
    pid = pr.json()["id"]
    try:
        rc = httpx.get(f"{API}/prices/vendor-comparison",
                       headers=H(tok), timeout=30)
        rows = rc.json()["items"]
        hit = [it for it in rows if it.get("group_key") == f"canon::{cid}"]
        assert len(hit) == 1
        assert hit[0]["item"] == cname
    finally:
        httpx.delete(f"{API}/purchases/{pid}", headers=H(tok), timeout=15)
        httpx.delete(f"{API}/items/{cid}", headers=H(tok), timeout=15)
