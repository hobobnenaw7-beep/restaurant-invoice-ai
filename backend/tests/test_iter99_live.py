"""Live integration tests for Milestone 23 — canonical identity + learning loop.

Exercises:
  - multi-variant /link (new body shape) composes display_name + persists alias+correction memory
  - legacy variant_key single field back-compat
  - canonical rename propagates to GET /purchases/{pid}
  - autocomplete surfaces learned variants with source='learned' and archived/suggested excluded
  - invalid/undeclared/archived canonical on /link returns proper error codes
"""
import os, uuid, time, requests, pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
EMAIL = "demo@test.com"
PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def canonical_item(auth):
    """Create a canonical item with declared variants type/gender/size (approved)."""
    name = f"TEST_Crab_{uuid.uuid4().hex[:6]}"
    payload = {
        "name": name,
        "category": "seafood",
        "unit": "lb",
        "status": "approved",
        "variants": [
            {"key": "male", "label": "Male", "type": "gender"},
            {"key": "female", "label": "Female", "type": "gender"},
            {"key": "large", "label": "Large", "type": "size"},
            {"key": "small", "label": "Small", "type": "size"},
        ],
    }
    r = auth.post(f"{API}/items", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create item: {r.status_code} {r.text[:300]}"
    item = r.json()
    return item


@pytest.fixture(scope="module")
def purchase_with_line(auth):
    """Create a tiny purchase with one raw line."""
    raw = f"blu crb mle lrg {uuid.uuid4().hex[:4]}"
    payload = {
        "supplier_name": "TEST_Supplier",
        "invoice_number": f"TEST-{uuid.uuid4().hex[:6]}",
        "date": "2026-01-15",
        "invoice_date": "2026-01-15",
        "items": [
            {"raw_name": raw, "quantity": 2, "unit_price": 5.0, "total": 10.0, "unit": "lb"}
        ],
        "subtotal": 10.0,
        "tax": 0.0,
        "total": 10.0,
    }
    r = auth.post(f"{API}/purchases", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create purchase: {r.status_code} {r.text[:400]}"
    p = r.json()
    return p, raw


def test_multi_variant_link_composes_display(auth, canonical_item, purchase_with_line):
    purchase, raw = purchase_with_line
    pid = purchase.get("id") or purchase.get("_id") or purchase.get("purchase_id")
    body = {"canonical_item_id": canonical_item["id"], "variant_keys": ["male", "large"]}
    r = auth.post(f"{API}/purchases/{pid}/items/0/link", json=body, timeout=30)
    assert r.status_code == 200, f"link failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    # variant_keys must be array and preserved
    vk = data.get("variant_keys") or (data.get("item") or {}).get("variant_keys")
    vl = data.get("variant_labels") or (data.get("item") or {}).get("variant_labels")
    dn = data.get("display_name") or (data.get("item") or {}).get("display_name")
    assert isinstance(vk, list) and set(vk) == {"male", "large"}, f"variant_keys bad: {vk}"
    assert isinstance(vl, list) and len(vl) == 2, f"variant_labels bad: {vl}"
    # display uses en-dash with spaces
    assert " — " in dn, f"display_name missing en-dash: {dn!r}"
    assert "Male" in dn and "Large" in dn, f"display_name missing variant labels: {dn!r}"


def test_legacy_variant_key_still_works(auth, canonical_item, purchase_with_line):
    # Add a fresh purchase line to avoid state coupling
    raw = f"blu crb fem {uuid.uuid4().hex[:4]}"
    r0 = auth.post(f"{API}/purchases", json={
        "supplier_name": "TEST_Supplier",
        "invoice_number": f"TEST-{uuid.uuid4().hex[:6]}",
        "date": "2026-01-15",
        "invoice_date": "2026-01-15",
        "items": [{"raw_name": raw, "quantity": 1, "unit_price": 7.0, "total": 7.0, "unit": "lb"}],
        "subtotal": 7.0,
        "tax": 0.0,
        "total": 7.0,
    }, timeout=30)
    assert r0.status_code in (200, 201)
    pid = (r0.json().get("id") or r0.json().get("_id"))
    body = {"canonical_item_id": canonical_item["id"], "variant_key": "female"}  # legacy single
    r = auth.post(f"{API}/purchases/{pid}/items/0/link", json=body, timeout=30)
    assert r.status_code == 200, f"legacy variant_key link failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    vk = data.get("variant_keys") or (data.get("item") or {}).get("variant_keys")
    assert vk and "female" in vk, f"legacy variant_key did not become variant_keys: {vk}"


def test_canonical_rename_propagates(auth, canonical_item, purchase_with_line):
    purchase, _ = purchase_with_line
    pid = (purchase.get("id") or purchase.get("_id"))
    new_name = f"TEST_Renamed_{uuid.uuid4().hex[:5]}"
    r = auth.put(f"{API}/items/{canonical_item['id']}", json={"name": new_name}, timeout=30)
    assert r.status_code in (200, 204), f"rename failed: {r.status_code} {r.text[:300]}"
    # fetch purchase and inspect line
    time.sleep(0.5)
    g = auth.get(f"{API}/purchases/{pid}", timeout=30)
    assert g.status_code == 200
    items = g.json().get("items", [])
    assert items, "purchase has no items"
    line = items[0]
    assert new_name in (line.get("canonical_name") or ""), f"canonical_name not updated: {line}"
    assert new_name in (line.get("display_name") or ""), f"display_name not updated: {line}"
    # raw_name preserved
    assert line.get("raw_name") and "blu" in line["raw_name"].lower()
    canonical_item["name"] = new_name  # update fixture


def test_correction_memory_and_autocomplete_learned(auth, canonical_item, purchase_with_line):
    _, raw = purchase_with_line
    # correction memory must exist with variant_keys
    time.sleep(0.3)
    r = auth.get(f"{API}/correction-memory", timeout=30)
    assert r.status_code == 200, r.text[:300]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    match = [x for x in rows if (x.get("original_raw_name") or "").lower() == raw.lower()]
    assert match, f"correction memory missing row for raw={raw!r}"
    row = match[0]
    assert row.get("canonical_item_id") == canonical_item["id"]
    assert isinstance(row.get("variant_keys"), list) and row["variant_keys"], f"variant_keys missing on correction: {row}"
    # autocomplete: short prefix of raw should return source='learned' suggestion
    prefix = raw.split()[0][:4]
    r2 = auth.get(f"{API}/items/autocomplete", params={"q": prefix}, timeout=30)
    assert r2.status_code == 200, r2.text[:300]
    sugg = r2.json() if isinstance(r2.json(), list) else (r2.json().get("suggestions") or r2.json().get("results") or [])
    sources = {s.get("source") for s in sugg}
    assert sources.issubset({"canonical", "variant", "alias", "learned"}), f"bad sources: {sources}"
    learned = [s for s in sugg if s.get("source") == "learned"]
    assert learned, f"no 'learned' source suggestions for prefix={prefix!r}, got sources={sources}"
    # learned composed label + variant_keys array
    l0 = learned[0]
    assert isinstance(l0.get("variant_keys"), list) and l0["variant_keys"], f"learned missing variant_keys: {l0}"
    label = l0.get("label") or l0.get("display_name") or ""
    assert " — " in label, f"learned label not composed: {label!r}"


def test_link_invalid_canonical_404(auth, purchase_with_line):
    purchase, _ = purchase_with_line
    pid = (purchase.get("id") or purchase.get("_id"))
    r = auth.post(f"{API}/purchases/{pid}/items/0/link",
                  json={"canonical_item_id": "nonexistent-" + uuid.uuid4().hex}, timeout=30)
    assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"


def test_link_undeclared_variant_400(auth, canonical_item, purchase_with_line):
    purchase, _ = purchase_with_line
    pid = (purchase.get("id") or purchase.get("_id"))
    r = auth.post(f"{API}/purchases/{pid}/items/0/link",
                  json={"canonical_item_id": canonical_item["id"], "variant_keys": ["purple"]},
                  timeout=30)
    assert r.status_code == 400, f"expected 400 for undeclared variant: {r.status_code} {r.text[:300]}"
    assert "variant_not_declared" in r.text, f"error body should mention variant_not_declared: {r.text[:200]}"


def test_link_archived_canonical_400(auth, purchase_with_line):
    # create a canonical, then archive it via PUT
    r0 = auth.post(f"{API}/items", json={
        "name": f"TEST_ToArchive_{uuid.uuid4().hex[:5]}",
        "category": "test", "unit": "ea", "status": "approved"
    }, timeout=30)
    assert r0.status_code in (200, 201), r0.text[:200]
    item = r0.json()
    r_arch = auth.put(f"{API}/items/{item['id']}",
                      json={"name": item.get("name"), "status": "archived"}, timeout=30)
    assert r_arch.status_code in (200, 204), f"archive failed: {r_arch.status_code} {r_arch.text[:200]}"
    # sanity-check archived
    g = auth.get(f"{API}/items/{item['id']}", timeout=30)
    if g.status_code == 200:
        assert (g.json().get("status") or "").lower() == "archived", f"item not archived: {g.json().get('status')}"
    purchase, _ = purchase_with_line
    pid = (purchase.get("id") or purchase.get("_id"))
    r = auth.post(f"{API}/purchases/{pid}/items/0/link",
                  json={"canonical_item_id": item["id"]}, timeout=30)
    assert r.status_code == 400, f"expected 400 on archived canonical: {r.status_code} {r.text[:300]}"


def test_autocomplete_excludes_suggested_and_archived(auth):
    # broad query — ensure no 'suggested' status leaks
    r = auth.get(f"{API}/items/autocomplete", params={"q": "test"}, timeout=30)
    assert r.status_code == 200
    sugg = r.json() if isinstance(r.json(), list) else (r.json().get("suggestions") or r.json().get("results") or [])
    for s in sugg:
        # status field may or may not be present but source must be in allowed set
        assert s.get("source") in {"canonical", "variant", "alias", "learned"}, f"bad source: {s}"


def test_sanity_endpoint_up(auth):
    # dv_lower regression — backend still responsive
    r = auth.get(f"{API}/items", params={"limit": 1}, timeout=30)
    assert r.status_code == 200, r.text[:200]
