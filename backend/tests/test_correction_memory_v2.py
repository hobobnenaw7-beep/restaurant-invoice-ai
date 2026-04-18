"""
Correction Memory v2 — Validation Script
Tests the complete save → apply cycle with primary and secondary key matching.
"""
import json, sys, os, requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"

def login():
    resp = requests.post(f"{API_URL}/api/auth/login",
                         json={"email": "demo@test.com", "password": "testpassword"})
    resp.raise_for_status()
    return resp.json()["token"]


def test_key_building():
    """Test the key building functions directly."""
    sys.path.insert(0, "/app/backend")
    os.chdir("/app/backend")
    from services.correction_memory import (
        build_primary_key, build_secondary_key,
        _normalize_vendor, _normalize_name, _normalize_pack, _clean_product_code,
    )

    print("=" * 70)
    print("  TEST 1: Key Building Functions")
    print("=" * 70)

    # Vendor normalization
    cases = [
        ("US Foods, Inc.", "USFOODS"),
        ("US Foods Inc.", "USFOODS"),
        ("Sysco Jacksonville", "SYSCO"),
        ("SYSCO JACKSONVILLE, INC.", "SYSCO"),
        ("Performance Foodservice Powell", "PFG"),
        ("Gville Seafood N Chicken", "GVILLE SEAFOOD N CHICKEN"),
    ]
    for raw, expected in cases:
        result = _normalize_vendor(raw)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] vendor '{raw}' → '{result}' (expected '{expected}')")

    # Product code cleaning
    code_cases = [
        ("1234567", "1234567"),
        ("USF#1234567", "1234567"),
        ("12", ""),  # too short
        ("", ""),
    ]
    for raw, expected in code_cases:
        result = _clean_product_code(raw)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] code '{raw}' → '{result}' (expected '{expected}')")

    # Primary key
    pk = build_primary_key("US Foods, Inc.", "1234567")
    assert pk == "USFOODS:1234567", f"Expected 'USFOODS:1234567', got '{pk}'"
    print(f"  [PASS] primary key: '{pk}'")

    pk_empty = build_primary_key("US Foods", "")
    assert pk_empty == "", f"Expected '', got '{pk_empty}'"
    print(f"  [PASS] primary key (no code): '{pk_empty}'")

    # Secondary key
    sk = build_secondary_key("Sysco Jacksonville", "CHICKEN BREAST BNLS", "6/4 LB")
    expected_sk = "SYSCO:BNLS BREAST CHICKEN:6/4LB"
    assert sk == expected_sk, f"Expected '{expected_sk}', got '{sk}'"
    print(f"  [PASS] secondary key: '{sk}'")

    print()


def test_save_and_apply():
    """Test the full save → apply cycle via API."""
    print("=" * 70)
    print("  TEST 2: Save and Apply Cycle")
    print("=" * 70)

    token = login()
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: Create a test purchase with a Sysco item
    print("\n  Step 1: Create test purchase...")
    purchase_data = {
        "supplier_name": "Sysco Jacksonville",
        "invoice_date": "2026-04-18",
        "invoice_number": "CORR-TEST-001",
        "items": [
            {
                "raw_name": "CHKN BRST BNLS 6OZ",
                "item_code": "5551234",
                "quantity": 2,
                "unit_price": 45.99,
                "total": 91.98,
                "pack_size": "4/10 LB",
            },
            {
                "raw_name": "SHRIMP 16-20 IQF",
                "item_code": "",
                "quantity": 3,
                "unit_price": 29.50,
                "total": 88.50,
                "pack_size": "2/5 LB",
            },
        ],
        "subtotal": 180.48,
        "tax": 0,
        "total": 180.48,
    }
    resp = requests.post(f"{API_URL}/api/purchases",
                         json=purchase_data, headers=headers)
    if resp.status_code != 200:
        print(f"    FAIL: Create purchase returned {resp.status_code}: {resp.text[:200]}")
        return
    purchase = resp.json()
    pid = purchase["id"]
    print(f"    Created purchase {pid}")

    # Step 2: Edit item 0's name (simulates user correction) via PUT
    print("\n  Step 2: Edit item 0 name (explicit save → correction memory)...")
    items_copy = purchase.get("items", [])
    items_copy[0]["raw_name"] = "Chicken Breast Boneless 6oz"  # Corrected name

    resp = requests.put(f"{API_URL}/api/purchases/{pid}",
                        json={"items": items_copy}, headers=headers)
    if resp.status_code != 200:
        print(f"    FAIL: Update returned {resp.status_code}: {resp.text[:200]}")
        return
    print(f"    Updated item 0 name to 'Chicken Breast Boneless 6oz'")

    # Step 3: Edit item 1's name via PATCH (inline edit)
    print("\n  Step 3: Edit item 1 name via PATCH (inline edit → correction memory)...")
    resp = requests.patch(
        f"{API_URL}/api/purchases/{pid}/items/1",
        json={"raw_name": "Shrimp 16-20 Count IQF"},
        headers=headers,
    )
    if resp.status_code != 200:
        print(f"    FAIL: Patch returned {resp.status_code}: {resp.text[:200]}")
        return
    print(f"    Patched item 1 name to 'Shrimp 16-20 Count IQF'")

    # Step 4: Check correction memory
    print("\n  Step 4: Verify corrections in memory...")
    resp = requests.get(f"{API_URL}/api/correction-memory", headers=headers)
    if resp.status_code != 200:
        print(f"    FAIL: Get corrections returned {resp.status_code}")
        return
    all_corrections = resp.json()

    # Find our corrections
    our_corrections = [c for c in all_corrections if "CORR-TEST" in str(c)]
    # Actually search by content
    chkn_corr = [c for c in all_corrections if "CHKN" in c.get("original_raw_name", "").upper()
                 or "CHICKEN" in c.get("corrected_name", "").upper()
                 and c.get("canonical_vendor", "") == "SYSCO"]
    shrimp_corr = [c for c in all_corrections if "SHRIMP" in c.get("original_raw_name", "").upper()
                   and c.get("canonical_vendor", "") == "SYSCO"]

    print(f"    Total corrections in DB: {len(all_corrections)}")
    print(f"    Chicken corrections found: {len(chkn_corr)}")
    print(f"    Shrimp corrections found: {len(shrimp_corr)}")

    if chkn_corr:
        c = chkn_corr[-1]
        print(f"\n    --- Chicken Correction (PRIMARY KEY EXPECTED) ---")
        print(f"    correction_key:      {c.get('correction_key', '?')}")
        print(f"    primary_key:         {c.get('primary_key', '?')}")
        print(f"    secondary_key:       {c.get('secondary_key', '?')}")
        print(f"    key_type:            {c.get('key_type', '?')}")
        print(f"    canonical_vendor:    {c.get('canonical_vendor', '?')}")
        print(f"    product_code:        {c.get('product_code', '?')}")
        print(f"    original_raw_name:   {c.get('original_raw_name', '?')}")
        print(f"    corrected_name:      {c.get('corrected_name', '?')}")
        print(f"    corrected_by_user_id:{c.get('corrected_by_user_id', '?')}")
        print(f"    corrected_by_name:   {c.get('corrected_by_name', '?')}")
        print(f"    times_matched:       {c.get('times_matched', '?')}")
        has_primary = c.get("key_type") == "primary" and c.get("product_code")
        print(f"    HAS PRIMARY KEY:     {'YES' if has_primary else 'NO'}")

    if shrimp_corr:
        c = shrimp_corr[-1]
        print(f"\n    --- Shrimp Correction (SECONDARY KEY EXPECTED) ---")
        print(f"    correction_key:      {c.get('correction_key', '?')}")
        print(f"    primary_key:         {c.get('primary_key', '?')}")
        print(f"    secondary_key:       {c.get('secondary_key', '?')}")
        print(f"    key_type:            {c.get('key_type', '?')}")
        print(f"    canonical_vendor:    {c.get('canonical_vendor', '?')}")
        print(f"    product_code:        {c.get('product_code', '?')}")
        print(f"    original_raw_name:   {c.get('original_raw_name', '?')}")
        print(f"    corrected_name:      {c.get('corrected_name', '?')}")
        has_secondary = c.get("key_type") == "secondary" and not c.get("product_code")
        print(f"    HAS SECONDARY KEY:   {'YES' if has_secondary else 'NO'}")

    # Step 5: Create a SECOND purchase with same items (simulates future extraction)
    print("\n  Step 5: Create second purchase (same items, should auto-apply)...")
    purchase2_data = {
        "supplier_name": "SYSCO JACKSONVILLE",
        "invoice_date": "2026-04-19",
        "invoice_number": "CORR-TEST-002",
        "items": [
            {
                "raw_name": "CHKN BRST BNLS 6OZ",
                "item_code": "5551234",
                "quantity": 1,
                "unit_price": 45.99,
                "total": 45.99,
                "pack_size": "4/10 LB",
            },
            {
                "raw_name": "SHRIMP 16-20 IQF",
                "item_code": "",
                "quantity": 2,
                "unit_price": 29.50,
                "total": 59.00,
                "pack_size": "2/5 LB",
            },
        ],
        "subtotal": 104.99,
        "tax": 0,
        "total": 104.99,
    }
    resp = requests.post(f"{API_URL}/api/purchases",
                         json=purchase2_data, headers=headers)
    if resp.status_code != 200:
        print(f"    FAIL: Create purchase 2 returned {resp.status_code}: {resp.text[:200]}")
        return
    purchase2 = resp.json()
    pid2 = purchase2["id"]
    items2 = purchase2.get("items", [])
    print(f"    Created purchase {pid2}")

    # Check if corrections were applied
    print("\n  Step 6: Verify correction application on new purchase...")
    for i, item in enumerate(items2):
        corr = item.get("correction_applied")
        raw = item.get("raw_name", "?")
        if corr:
            print(f"    Item {i}: raw_name='{raw}'")
            print(f"      corrected_name:  {corr.get('corrected_name', '?')}")
            print(f"      match_type:      {corr.get('match_type', '?')}")
            print(f"      match_key:       {corr.get('match_key', '?')}")
            print(f"      match_confidence:{corr.get('match_confidence', '?')}")
            print(f"      raw_name_preserved: {corr.get('raw_name_preserved', '?')}")
            print(f"      confidence_level:{item.get('confidence_level', '?')}")

            # SAFEGUARD: Verify raw_name is NOT overwritten
            assert raw == corr.get("raw_name_preserved"), \
                f"SAFEGUARD VIOLATION: raw_name was overwritten! {raw} != {corr.get('raw_name_preserved')}"
            print(f"      SAFEGUARD: raw_name preserved ✓")
        else:
            print(f"    Item {i}: raw_name='{raw}' — no correction applied")

    # Cleanup
    print("\n  Cleanup: Deleting test purchases...")
    requests.delete(f"{API_URL}/api/purchases/{pid}", headers=headers)
    requests.delete(f"{API_URL}/api/purchases/{pid2}", headers=headers)
    print("    Done")

    print()


def test_legacy_migration_review():
    """Review the 8 legacy corrections and their mapping to new structure."""
    sys.path.insert(0, "/app/backend")
    os.chdir("/app/backend")
    from pymongo import MongoClient
    from services.correction_memory import (
        build_primary_key, build_secondary_key, _normalize_vendor,
    )

    print("=" * 70)
    print("  TEST 3: Legacy Correction Review")
    print("=" * 70)

    client = MongoClient("mongodb://localhost:27017")
    db = client["test_database"]

    corrections = list(db.correction_memory.find({}, {"_id": 0}))
    # Filter to legacy-only (no correction_key field)
    legacy = [c for c in corrections if not c.get("correction_key")]

    print(f"\n  Legacy corrections (no correction_key): {len(legacy)}")
    print(f"  New-format corrections: {len(corrections) - len(legacy)}")

    for i, c in enumerate(legacy, 1):
        name_changed = c.get("original_raw_name", "") != c.get("corrected_name", "")
        has_usage = (c.get("usage_count", 0) or 0) > 0
        old_key = c.get("normalized_key", "")

        # What would the new key be?
        # Legacy corrections don't have canonical_vendor or product_code
        # They map to secondary keys via normalized_key
        vendor = "UNKNOWN"
        sup_id = c.get("supplier_id", "")
        sup = db.suppliers.find_one({"id": sup_id}, {"_id": 0, "name": 1})
        if sup:
            vendor = _normalize_vendor(sup["name"])

        recommendation = "KEEP"
        reason = ""
        if "Quick Review Test" in (sup.get("name", "") if sup else ""):
            recommendation = "DROP (test data)"
            reason = "Test vendor"
        elif "fumil" in c.get("corrected_name", ""):
            recommendation = "DROP (typo)"
            reason = "Corrected name contains typo 'fumil'"
        elif not name_changed and not c.get("corrected_specs"):
            recommendation = "DROP (no change)"
            reason = "No name or spec changes"

        print(f"\n  Legacy #{i}:")
        print(f"    old normalized_key: {old_key[:50]}")
        print(f"    vendor:             {vendor}")
        print(f"    name_changed:       {name_changed}")
        print(f"    has_usage:          {has_usage} (count={c.get('usage_count', 0)})")
        print(f"    original_raw_name:  {c.get('original_raw_name', '?')[:50]}")
        print(f"    corrected_name:     {c.get('corrected_name', '?')[:50]}")
        print(f"    corrected_specs:    {json.dumps(c.get('corrected_specs', {}))[:60]}")
        print(f"    RECOMMENDATION:     {recommendation}")
        if reason:
            print(f"    REASON:             {reason}")

    client.close()
    print()


if __name__ == "__main__":
    test_key_building()
    test_save_and_apply()
    test_legacy_migration_review()
    print("=" * 70)
    print("  ALL TESTS COMPLETE")
    print("=" * 70)
