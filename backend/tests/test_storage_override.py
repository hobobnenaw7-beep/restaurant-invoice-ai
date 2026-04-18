"""
Unit test: Manual override protection in storage_classifier.
Confirms manual category is NEVER overwritten by auto-classification.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.storage_classifier import classify_items_by_section


def test_manual_override_never_overwritten():
    """Manual category_source='manual' must survive all classification paths."""

    # Case 1: Keyword would assign 'frozen', but manual says 'chilled'
    items = [
        {"raw_name": "FROZEN SHRIMP IQF", "item_code": "1111",
         "storage_category": "chilled", "category_source": "manual"},
    ]
    classify_items_by_section(items)
    assert items[0]["storage_category"] == "chilled", \
        f"FAIL: keyword overrode manual — got '{items[0]['storage_category']}'"
    assert items[0]["category_source"] == "manual", \
        f"FAIL: category_source changed — got '{items[0]['category_source']}'"
    print("[PASS] Case 1: keyword 'FROZEN' did NOT overwrite manual 'chilled'")

    # Case 2: Section header would assign 'frozen', but manual says 'dry'
    raw_text = "FROZEN\n1111  SHRIMP IQF  2  30.00  60.00\n"
    items2 = [
        {"raw_name": "SHRIMP IQF", "item_code": "1111",
         "storage_category": "dry", "category_source": "manual"},
    ]
    classify_items_by_section(items2, raw_text)
    assert items2[0]["storage_category"] == "dry", \
        f"FAIL: section header overrode manual — got '{items2[0]['storage_category']}'"
    assert items2[0]["category_source"] == "manual", \
        f"FAIL: category_source changed — got '{items2[0]['category_source']}'"
    print("[PASS] Case 2: section header 'FROZEN' did NOT overwrite manual 'dry'")

    # Case 3: Mixed — one manual, one auto
    items3 = [
        {"raw_name": "FROZEN CHICKEN", "item_code": "2222",
         "storage_category": "chilled", "category_source": "manual"},
        {"raw_name": "FROZEN SHRIMP", "item_code": "3333"},
    ]
    classify_items_by_section(items3)
    assert items3[0]["storage_category"] == "chilled" and items3[0]["category_source"] == "manual", \
        f"FAIL: manual item was changed"
    assert items3[1]["storage_category"] == "frozen" and items3[1]["category_source"] == "auto", \
        f"FAIL: auto item was not classified"
    print("[PASS] Case 3: manual preserved, auto classified correctly")

    # Case 4: Manual 'uncategorized' stays uncategorized
    items4 = [
        {"raw_name": "FRESH SALMON", "item_code": "4444",
         "storage_category": "uncategorized", "category_source": "manual"},
    ]
    classify_items_by_section(items4)
    assert items4[0]["storage_category"] == "uncategorized", \
        f"FAIL: manual uncategorized was overwritten — got '{items4[0]['storage_category']}'"
    assert items4[0]["category_source"] == "manual"
    print("[PASS] Case 4: manual 'uncategorized' preserved despite keyword 'FRESH'")

    # Case 5: No category_source field → treated as auto, gets classified
    items5 = [
        {"raw_name": "RICE LONG GRAIN", "item_code": "5555"},
    ]
    classify_items_by_section(items5)
    assert items5[0]["storage_category"] == "dry"
    assert items5[0]["category_source"] == "auto"
    print("[PASS] Case 5: item without category_source gets auto-classified")

    # Case 6: Empty storage_category + no keyword match → uncategorized
    items6 = [
        {"raw_name": "WIDGET UNKNOWN", "item_code": "6666"},
    ]
    classify_items_by_section(items6)
    assert items6[0]["storage_category"] == "uncategorized"
    assert items6[0]["category_source"] == "auto"
    print("[PASS] Case 6: unrecognizable item → uncategorized")


if __name__ == "__main__":
    test_manual_override_never_overwritten()
    print("\nAll 6 tests passed.")
