"""
Test the complete pipeline: fee handling, column checks, trust_decision audit.
"""
import sys
sys.path.insert(0, "/app/backend")

from routes.upload import (
    _validate_single_item_sources,
    _detect_all_qty_one_pattern,
    _apply_numeric_trust_gate,
    _assign_numeric_failure_category,
    _validate_pfg_extraction,
    _validate_usfoods_extraction,
)


def make_item(qty, price, total, row_type="line_item", raw_name="TEST PRODUCT",
              qty_source="column_read", price_source="column_read", total_source="column_read",
              qty_column_visible=None, pack_size="", item_code=""):
    item = {
        "raw_name": raw_name,
        "quantity": qty,
        "unit_price": price,
        "total": total,
        "qty_source": qty_source,
        "price_source": price_source,
        "total_source": total_source,
        "row_type": row_type,
        "pack_size": pack_size,
        "item_code": item_code,
        "valid_calc": abs(round(qty * price, 2) - total) < 0.02 if qty > 0 and price > 0 and total > 0 else False,
        "confidence_level": "trusted",
        "numeric_failure_category": "none",
    }
    if qty_column_visible is not None:
        item["qty_column_visible"] = qty_column_visible
    return item


# ═══════════════════════════════════════════════════════
# STEP 1: Fee Row Handling
# ═══════════════════════════════════════════════════════

def test_fee_with_total():
    """Fee row with total > 0 → trusted (no qty×price math needed)"""
    item = make_item(0, 0, 12.50, row_type="fee", raw_name="FUEL SURCHARGE")
    _validate_single_item_sources(item)
    _assign_numeric_failure_category(item)
    _apply_numeric_trust_gate(item)
    assert item["confidence_level"] == "trusted", f"Expected trusted, got {item['confidence_level']}"
    assert item["numeric_failure_category"] == "fee_valid"
    assert item["quantity"] == 1  # Normalized
    assert item["unit_price"] == 12.50  # Normalized
    print("PASS: fee with total → trusted")


def test_fee_no_total():
    """Fee row with total = 0 → needs_review"""
    item = make_item(0, 0, 0, row_type="fee", raw_name="DELIVERY FEE")
    _validate_single_item_sources(item)
    _assign_numeric_failure_category(item)
    _apply_numeric_trust_gate(item)
    assert item["confidence_level"] == "needs_review_numeric", f"Got {item['confidence_level']}"
    assert item["numeric_failure_category"] == "fee_missing_total"
    print("PASS: fee with no total → needs_review")


def test_fee_with_price_only():
    """Fee row with price but no total → source validation normalizes it"""
    item = make_item(0, 15.00, 0, row_type="fee", raw_name="SERVICE CHARGE")
    _validate_single_item_sources(item)
    # After source validation, fee should have total set from price
    assert item["quantity"] == 1
    print("PASS: fee with price only → normalized")


def test_fee_skips_product_math():
    """Fee row should NOT go through product math checks"""
    item = make_item(0, 0, 8.75, row_type="fee", raw_name="FUEL SURCHARGE")
    _validate_single_item_sources(item)
    # Check that no product-math overrides were applied
    overrides = item.get("_source_overrides", [])
    product_checks = [o for o in overrides if "math mismatch" in o or "qty may be defaulted" in o]
    assert len(product_checks) == 0, f"Fee row got product checks: {product_checks}"
    print("PASS: fee skips product math checks")


# ═══════════════════════════════════════════════════════
# STEP 2: Vendor-Specific Column Sanity Checks
# ═══════════════════════════════════════════════════════

def test_pfg_weight_as_qty():
    """PFG: qty=75.50 → flagged as WEIGHT column, not SHIP"""
    items = [
        make_item(75.50, 2.15, 162.33, raw_name="CHICKEN BREAST BNLS"),
    ]
    _validate_pfg_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_weight_flag = any("WEIGHT" in e for e in errors)
    assert has_weight_flag, f"Expected WEIGHT flag, got: {errors}"
    print("PASS: PFG weight-as-qty detected")


def test_pfg_decimal_qty():
    """PFG: qty=24.50 (decimal) → flagged because SHIP is always integer"""
    items = [
        make_item(24.50, 3.00, 73.50, raw_name="GROUND BEEF 80/20"),
    ]
    _validate_pfg_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_decimal_flag = any("decimal" in e for e in errors)
    assert has_decimal_flag, f"Expected decimal flag, got: {errors}"
    print("PASS: PFG decimal qty detected")


def test_pfg_pack_as_qty():
    """PFG: pack='6/4 LB' and qty=6 → flagged as PACK confusion"""
    items = [
        make_item(6, 12.00, 72.00, raw_name="SHRIMP 16/20", pack_size="6/4 LB"),
    ]
    _validate_pfg_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_pack_flag = any("PACK" in e for e in errors)
    assert has_pack_flag, f"Expected PACK flag, got: {errors}"
    print("PASS: PFG pack-as-qty detected")


def test_pfg_normal_qty():
    """PFG: qty=3 (normal integer) → no flags"""
    items = [
        make_item(3, 45.00, 135.00, raw_name="SALMON FILLET"),
    ]
    _validate_pfg_extraction(items)
    errors = items[0].get("validation_errors", [])
    column_errors = [e for e in errors if "column_check" in e]
    assert len(column_errors) == 0, f"Normal qty got column flags: {column_errors}"
    print("PASS: PFG normal qty → no flags")


def test_usfoods_weight_as_qty():
    """US Foods: qty=120.00 → flagged as WEIGHT column"""
    items = [
        make_item(120.00, 1.50, 180.00, raw_name="CHICKEN THIGH BNLS", item_code="1234567"),
    ]
    _validate_usfoods_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_weight_flag = any("WEIGHT" in e for e in errors)
    assert has_weight_flag, f"Expected WEIGHT flag, got: {errors}"
    print("PASS: US Foods weight-as-qty detected")


def test_usfoods_decimal_qty():
    """US Foods: qty=24.50 → flagged as WEIGHT"""
    items = [
        make_item(24.50, 3.00, 73.50, raw_name="BEEF PATTY 4OZ", item_code="9876543"),
    ]
    _validate_usfoods_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_decimal_flag = any("decimal" in e or "WEIGHT" in e for e in errors)
    assert has_decimal_flag, f"Expected decimal/WEIGHT flag, got: {errors}"
    print("PASS: US Foods decimal qty detected")


def test_usfoods_ordered_vs_shipped():
    """US Foods: qty > 0 but total = 0 → possible ORDERED vs SHIPPED confusion"""
    items = [
        make_item(5, 25.00, 0, raw_name="CRAB CAKE", item_code="5551234"),
    ]
    _validate_usfoods_extraction(items)
    errors = items[0].get("validation_errors", [])
    has_ordered_flag = any("ORDERED" in e for e in errors)
    assert has_ordered_flag, f"Expected ORDERED flag, got: {errors}"
    print("PASS: US Foods ordered-vs-shipped detected")


def test_usfoods_fee_handling():
    """US Foods: fuel surcharge → reclassified as fee"""
    items = [
        make_item(0, 0, 15.00, raw_name="FUEL SURCHARGE"),
    ]
    _validate_usfoods_extraction(items)
    assert items[0]["row_type"] == "fee", f"Expected fee, got {items[0]['row_type']}"
    assert items[0]["valid_calc"] is True
    assert items[0]["quantity"] == 1
    print("PASS: US Foods fee handling")


# ═══════════════════════════════════════════════════════
# Run all tests
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    tests = [
        # Step 1: Fee handling
        test_fee_with_total,
        test_fee_no_total,
        test_fee_with_price_only,
        test_fee_skips_product_math,
        # Step 2: Column sanity checks
        test_pfg_weight_as_qty,
        test_pfg_decimal_qty,
        test_pfg_pack_as_qty,
        test_pfg_normal_qty,
        test_usfoods_weight_as_qty,
        test_usfoods_decimal_qty,
        test_usfoods_ordered_vs_shipped,
        test_usfoods_fee_handling,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("ALL TESTS PASSED")
