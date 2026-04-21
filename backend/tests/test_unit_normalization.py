"""
Unit Normalization & Price Calculation — Validation Test
=========================================================
Tests: parse_pack_size, normalize_item, before-vs-after JSON.
Covers Sysco, US Foods, PFG patterns + the user-specified formula:
  price_per_unit = line_total / (quantity * normalized_multiplier)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.unit_normalizer import parse_pack_size, normalize_item


def test_parse_patterns():
    """Test pack_size parsing across all vendor formats."""
    cases = [
        # Sysco standard
        ("40 LB",       "lb", 40.0,   None,  "simple_lb"),
        ("4/10 LB",     "lb", 40.0,   None,  "fraction_lb"),
        ("2/5 LB",      "lb", 10.0,   None,  "fraction_lb"),
        ("150LB",       "lb", 150.0,  None,  "simple_lb"),
        ("8/5#",        "lb", 40.0,   None,  "fraction_lb"),
        # Sysco OCR concatenation fix: "410LB" → 4/10 = 40 lb
        ("410LB",       "lb", 40.0,   None,  "fraction_lb"),
        ("220LB",       "lb", 40.0,   None,  "fraction_lb"),  # 2/20 = 40 lb
        # NOT split: prefix=1 is ambiguous
        ("120LB",       "lb", 120.0,  None,  "simple_lb"),
        ("150LB",       "lb", 150.0,  None,  "simple_lb"),
        # CS-prefixed (Sysco GPT output)
        ("CS 410 LB",   "lb", 40.0,   None,  "fraction_lb"),
        ("CS 410LB",    "lb", 40.0,   None,  "fraction_lb"),
        ("CS 120 LB",   "lb", 120.0,  None,  "simple_lb"),
        # US Foods / PFG patterns
        ("40 LB CS",    "lb", 40.0,   None,  "lb_container"),
        ("20 LB BAG",   "lb", 20.0,   None,  "lb_container"),
        ("50 LB BX",    "lb", 50.0,   None,  "lb_container"),
        ("6 CT",        "piece", None, 6,     "ct_count"),
        ("24 CT",       "piece", None, 24,    "ct_count"),
        ("2/24 CT",     "piece", None, 48,    "frac_ct"),
        ("6/4 OZ",      "lb",  1.5,   None,  "fraction_oz"),
        ("12/8 OZ",     "lb",  6.0,   None,  "fraction_oz"),
        # Gallon
        ("4/1GAL",      "gallon", None, None, "gallon"),
        # EA count
        ("25 EA",       "piece", None, 25,    "ea_count"),
        # Ambiguous / review
        ("",            None, None, None, "empty"),
        ("CS",          None, None, None, "cs_only_ambiguous"),
    ]

    print("=" * 70)
    print("  TEST 1: Pack Size Parsing")
    print("=" * 70)
    passed = 0
    for raw, exp_unit, exp_lb, exp_pcs, exp_method in cases:
        result = parse_pack_size(raw)
        ok = True
        if exp_unit is not None and result.get("unit_type") != exp_unit:
            ok = False
        if exp_lb is not None and result.get("total_weight_lb") != exp_lb:
            ok = False
        if exp_pcs is not None and result.get("total_pieces") != exp_pcs:
            ok = False
        if exp_method and result.get("parse_method") != exp_method:
            ok = False

        status = "PASS" if ok else "FAIL"
        detail = f"unit={result.get('unit_type')}, lb={result.get('total_weight_lb')}, pcs={result.get('total_pieces')}, method={result.get('parse_method')}"
        print(f"  [{status}] '{raw:15s}' → {detail}")
        if not ok:
            print(f"         EXPECTED: unit={exp_unit}, lb={exp_lb}, pcs={exp_pcs}, method={exp_method}")
        else:
            passed += 1

    print(f"\n  {passed}/{len(cases)} passed\n")
    return passed == len(cases)


def test_price_formula():
    """Test: price_per_unit = line_total / (quantity * multiplier)."""
    print("=" * 70)
    print("  TEST 2: Price Per Unit Formula")
    print("=" * 70)

    cases = [
        # (raw_name, pack_size, qty, unit_price, total, expected_ppu, expected_unit)
        ("Chicken Breast 40 LB Case", "4/10 LB", 2, 60.95, 121.90, round(121.90 / (2 * 40), 4), "lb"),
        ("Shrimp IQF 2/5 LB",        "2/5 LB",  3, 29.50, 88.50,  round(88.50 / (3 * 10), 4),  "lb"),
        ("Cups 6 CT",                 "6 CT",    10, 5.00,  50.00,  round(50.00 / (10 * 6), 4),  "piece"),
        ("Oil 1 GAL",                 "40 LB CS", 1, 45.00, 45.00,  round(45.00 / (1 * 40), 4),  "lb"),
    ]

    all_pass = True
    for name, pack, qty, up, total, exp_ppu, exp_unit in cases:
        item = {
            "raw_name": name,
            "pack_size": pack,
            "quantity": qty,
            "unit_price": up,
            "total": total,
        }
        normalize_item(item)
        actual_ppu = item.get("price_per_unit")
        actual_unit = item.get("normalized_unit")
        ok = actual_ppu == exp_ppu and actual_unit == exp_unit

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name[:35]:35s} | pack={pack:10s} qty={qty} total=${total}")
        print(f"          ppu=${actual_ppu} (expected ${exp_ppu}) | unit={actual_unit}")
        if not ok:
            all_pass = False

    print()
    return all_pass


def test_before_after_json():
    """Show before-vs-after JSON for a Sysco invoice item."""
    print("=" * 70)
    print("  TEST 3: Before vs After JSON")
    print("=" * 70)

    before = {
        "raw_name": "SYS CLS CHICKN CVP BRST TENDER JUMBO",
        "item_code": "2847593",
        "pack_size": "4/10 LB",
        "quantity": 2,
        "unit_price": 60.95,
        "total": 121.90,
        "confidence_level": "trusted",
        "row_type": "line_item",
    }

    print("\n  BEFORE (raw extraction):")
    print(json.dumps(before, indent=4))

    after = dict(before)
    normalize_item(after)

    print("\n  AFTER (with normalization):")
    print(json.dumps(after, indent=4))

    # Verify
    assert after["price_per_unit"] == round(121.90 / (2 * 40), 4), f"ppu wrong: {after['price_per_unit']}"
    assert after["normalized_unit"] == "lb"
    assert after["normalized_quantity"] == 80.0  # 2 cases × 40 lb
    assert after["unit_status"] == "normalized"
    assert after["_pack_weight_lb"] == 40.0
    print("\n  [PASS] All assertions verified")

    # US Foods example
    print("\n  --- US Foods Example ---")
    usf_before = {
        "raw_name": "SHRIMP 16-20 IQF",
        "item_code": "4523871",
        "pack_size": "2/5 LB",
        "quantity": 3,
        "unit_price": 29.50,
        "total": 88.50,
        "confidence_level": "trusted",
        "row_type": "line_item",
    }
    usf_after = dict(usf_before)
    normalize_item(usf_after)

    print("\n  BEFORE:")
    print(f"    {usf_before['raw_name']} | pack={usf_before['pack_size']} | qty={usf_before['quantity']} | total=${usf_before['total']}")
    print(f"    price_per_unit: (not set)")

    print("\n  AFTER:")
    print(f"    {usf_after['raw_name']} | pack={usf_after['pack_size']} | qty={usf_after['quantity']} | total=${usf_after['total']}")
    print(f"    price_per_unit: ${usf_after['price_per_unit']}/lb")
    print(f"    normalized_quantity: {usf_after['normalized_quantity']} lb (3 cases × 10 lb/case)")
    print(f"    unit_status: {usf_after['unit_status']}")

    assert usf_after["price_per_unit"] == round(88.50 / 30, 4)
    print("\n  [PASS] US Foods example verified")


def test_review_flag():
    """Items with unparseable pack_size should be flagged for review."""
    print("\n" + "=" * 70)
    print("  TEST 4: Review Flag for Ambiguous Items")
    print("=" * 70)

    item = {
        "raw_name": "MYSTERY PRODUCT",
        "pack_size": "",
        "quantity": 1,
        "unit_price": 25.00,
        "total": 25.00,
    }
    normalize_item(item)
    assert item["unit_status"] == "review", f"Expected review, got {item['unit_status']}"
    assert item["price_per_unit"] is None
    print("  [PASS] Empty pack_size → unit_status='review', price_per_unit=None")

    item2 = {
        "raw_name": "WEIRD ITEM",
        "pack_size": "CS",
        "quantity": 1,
        "unit_price": 10.00,
        "total": 10.00,
    }
    normalize_item(item2)
    assert item2["unit_status"] == "review"
    assert item2["price_per_unit"] is None
    print("  [PASS] Ambiguous 'CS' → unit_status='review', price_per_unit=None")


if __name__ == "__main__":
    ok1 = test_parse_patterns()
    ok2 = test_price_formula()
    test_before_after_json()
    test_review_flag()

    print("\n" + "=" * 70)
    if ok1 and ok2:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
    print("=" * 70)
