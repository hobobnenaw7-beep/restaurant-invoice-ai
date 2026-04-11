"""
Test the qty_column_visible logic in the trust gate.
Verifies that:
1. qty=1 + price==total + qty_column_visible=True → keeps column_read (TRUSTED)
2. qty=1 + price==total + qty_column_visible=False → downgrades to ambiguous (REVIEW)
3. qty=1 + price==total + qty_column_visible missing → downgrades to ambiguous (REVIEW)
4. All-qty-1 pattern with at least one qty_column_visible=True → no bulk downgrade
5. All-qty-1 pattern with zero qty_column_visible=True → bulk downgrade
"""
import sys
sys.path.insert(0, "/app/backend")

from routes.upload import (
    _validate_single_item_sources,
    _detect_all_qty_one_pattern,
    _apply_numeric_trust_gate,
    _classify_row_type,
)


def make_item(qty, price, total, qty_source="column_read", price_source="column_read",
              total_source="column_read", row_type="line_item", qty_column_visible=None,
              raw_name="TEST PRODUCT"):
    item = {
        "raw_name": raw_name,
        "quantity": qty,
        "unit_price": price,
        "total": total,
        "qty_source": qty_source,
        "price_source": price_source,
        "total_source": total_source,
        "row_type": row_type,
        "valid_calc": abs(round(qty * price, 2) - total) < 0.02,
        "confidence_level": "trusted",
        "numeric_failure_category": "none",
    }
    if qty_column_visible is not None:
        item["qty_column_visible"] = qty_column_visible
    return item


def test_qty1_visible_true():
    """qty=1, price==total, qty_column_visible=True → keeps column_read"""
    item = make_item(1, 45.50, 45.50, qty_column_visible=True)
    _validate_single_item_sources(item)
    assert item["qty_source"] == "column_read", f"Expected column_read, got {item['qty_source']}"
    print("PASS: qty=1 + visible=True → column_read preserved")


def test_qty1_visible_false():
    """qty=1, price==total, qty_column_visible=False → downgrades"""
    item = make_item(1, 45.50, 45.50, qty_column_visible=False)
    _validate_single_item_sources(item)
    assert item["qty_source"] == "ambiguous", f"Expected ambiguous, got {item['qty_source']}"
    print("PASS: qty=1 + visible=False → ambiguous")


def test_qty1_visible_missing():
    """qty=1, price==total, qty_column_visible not present → downgrades"""
    item = make_item(1, 45.50, 45.50)
    _validate_single_item_sources(item)
    assert item["qty_source"] == "ambiguous", f"Expected ambiguous, got {item['qty_source']}"
    print("PASS: qty=1 + visible=missing → ambiguous")


def test_qty1_fee_row():
    """qty=1, price==total, fee row → keeps column_read (fees always qty=1)"""
    item = make_item(1, 12.00, 12.00, row_type="fee", raw_name="FUEL SURCHARGE")
    _validate_single_item_sources(item)
    assert item["qty_source"] == "column_read", f"Expected column_read, got {item['qty_source']}"
    print("PASS: qty=1 fee row → column_read preserved")


def test_qty_not_1():
    """qty=2, price!=total → no downgrade (normal case)"""
    item = make_item(2, 45.50, 91.00, qty_column_visible=True)
    _validate_single_item_sources(item)
    assert item["qty_source"] == "column_read", f"Expected column_read, got {item['qty_source']}"
    print("PASS: qty=2 → column_read preserved")


def test_all_qty1_with_visible():
    """All qty=1 but at least one qty_column_visible=True → no bulk downgrade"""
    items = [
        make_item(1, 30.00, 30.00, qty_column_visible=True, raw_name="ITEM A"),
        make_item(1, 45.50, 45.50, qty_column_visible=True, raw_name="ITEM B"),
        make_item(1, 22.00, 22.00, qty_column_visible=True, raw_name="ITEM C"),
        make_item(1, 15.00, 15.00, qty_column_visible=False, raw_name="ITEM D"),
    ]
    _detect_all_qty_one_pattern(items)
    visible_items = [it for it in items if it.get("qty_column_visible") is True]
    for it in visible_items:
        assert it["qty_source"] == "column_read", \
            f"Item {it['raw_name']}: Expected column_read, got {it['qty_source']}"
    print("PASS: all-qty-1 with visible → no bulk downgrade")


def test_all_qty1_without_visible():
    """All qty=1 and none have qty_column_visible=True → bulk downgrade"""
    items = [
        make_item(1, 30.00, 30.00, raw_name="ITEM A"),
        make_item(1, 45.50, 45.50, raw_name="ITEM B"),
        make_item(1, 22.00, 22.00, raw_name="ITEM C"),
    ]
    _detect_all_qty_one_pattern(items)
    for it in items:
        assert it["qty_source"] == "ambiguous", \
            f"Item {it['raw_name']}: Expected ambiguous, got {it['qty_source']}"
    print("PASS: all-qty-1 without visible → bulk downgrade")


def test_trust_gate_passes_with_visible():
    """Full pipeline: qty=1, visible=True → should be trusted"""
    item = make_item(1, 45.50, 45.50, qty_column_visible=True)
    _validate_single_item_sources(item)
    # Re-check trust gate conditions
    from routes.upload import _assign_numeric_failure_category
    _assign_numeric_failure_category(item)
    _apply_numeric_trust_gate(item)
    assert item["confidence_level"] == "trusted", \
        f"Expected trusted, got {item['confidence_level']}"
    print("PASS: Full pipeline with visible=True → trusted")


def test_trust_gate_fails_without_visible():
    """Full pipeline: qty=1, visible missing → should be needs_review_numeric"""
    item = make_item(1, 45.50, 45.50)
    _validate_single_item_sources(item)
    from routes.upload import _assign_numeric_failure_category
    _assign_numeric_failure_category(item)
    _apply_numeric_trust_gate(item)
    assert item["confidence_level"] == "needs_review_numeric", \
        f"Expected needs_review_numeric, got {item['confidence_level']}"
    print("PASS: Full pipeline without visible → needs_review_numeric")


if __name__ == "__main__":
    tests = [
        test_qty1_visible_true,
        test_qty1_visible_false,
        test_qty1_visible_missing,
        test_qty1_fee_row,
        test_qty_not_1,
        test_all_qty1_with_visible,
        test_all_qty1_without_visible,
        test_trust_gate_passes_with_visible,
        test_trust_gate_fails_without_visible,
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
    else:
        print("SOME TESTS FAILED")
