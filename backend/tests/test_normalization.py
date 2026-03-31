"""Regression tests for services/normalization.py"""
import sys
sys.path.insert(0, "/app/backend")

from services.normalization import normalize_item, _singularize, _normalize_token, _is_grade


def test_grade_vs_size_code():
    """Grade = lopsided (80/20). Size code = similar (31-35)."""
    assert _is_grade(80, 20) is True
    assert _is_grade(70, 30) is True
    assert _is_grade(93, 7) is True
    assert _is_grade(31, 35) is False
    assert _is_grade(16, 20) is False
    assert _is_grade(21, 25) is False


def test_singularize():
    assert _singularize("TOMATOES") == "TOMATO"
    assert _singularize("ONIONS") == "ONION"
    assert _singularize("BREASTS") == "BREAST"
    assert _singularize("HEARTS") == "HEART"
    assert _singularize("BERRIES") == "BERRY"
    # Exceptions — should NOT be singularized
    assert _singularize("LETTUCE") == "LETTUCE"
    assert _singularize("RICE") == "RICE"
    assert _singularize("CHEESE") == "CHEESE"
    assert _singularize("SAUCE") == "SAUCE"


def test_abbreviation_expansion():
    assert _normalize_token("BNLS") == "BONELESS"
    assert _normalize_token("HDLS") == "HEADLESS"
    assert _normalize_token("CTN") == "CARTON"
    assert _normalize_token("FRZ") == "FROZEN"
    assert _normalize_token("GRND") == "GROUND"
    assert _normalize_token("BRST") == "BREAST"


def test_clean_name_preserves_meaning():
    """clean_name only does safe cleanup: uppercase, whitespace, grade separator."""
    item = {"raw_name": "GROUND BEEF 80-20", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["clean_name"] == "GROUND BEEF 80/20"

    item = {"raw_name": "SHRIMP 31-35 HDLS", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["clean_name"] == "SHRIMP 31-35 HDLS"  # size code separator preserved

    item = {"raw_name": "Carf Meal #11", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["clean_name"] == "CARF MEAL #11"  # product code preserved

    item = {"raw_name": "ROMA TOMATO 25LB", "unit": "", "pack_size": "1/25 LB"}
    normalize_item(item)
    assert item["norm"]["clean_name"] == "ROMA TOMATO 25LB"  # embedded weight preserved


def test_base_name_strips_specs():
    """base_name aggressively removes specs for broad matching."""
    item = {"raw_name": "GROUND BEEF 80/20", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["base_name"] == "GROUND BEEF"

    item = {"raw_name": "SHRIMP 31-35 HDLS", "unit": "", "pack_size": "10/4 LB"}
    normalize_item(item)
    assert item["norm"]["base_name"] == "SHRIMP HDLS"

    item = {"raw_name": "Carf Meal #11", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["base_name"] == "CARF MEAL"

    # Embedded weight only stripped when pack_size exists
    item = {"raw_name": "ROMA TOMATO 25LB", "unit": "", "pack_size": "1/25 LB"}
    normalize_item(item)
    assert item["norm"]["base_name"] == "ROMA TOMATO"

    item = {"raw_name": "ROMA TOMATO 25LB", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["base_name"] == "ROMA TOMATO 25LB"  # No pack_size → keep it


def test_strict_match_key_distinguishes_products():
    """strict_match_key includes specs, so 80/20 ≠ 90/10."""
    a = {"raw_name": "GROUND BEEF 80/20", "unit": "", "pack_size": ""}
    b = {"raw_name": "GROUND BEEF 90/10", "unit": "", "pack_size": ""}
    normalize_item(a)
    normalize_item(b)
    assert a["norm"]["strict_match_key"] != b["norm"]["strict_match_key"]


def test_loose_match_key_groups_broadly():
    """loose_match_key ignores specs, so all ground beef matches."""
    a = {"raw_name": "GROUND BEEF 80/20", "unit": "", "pack_size": ""}
    b = {"raw_name": "GROUND BEEF 90/10", "unit": "", "pack_size": ""}
    normalize_item(a)
    normalize_item(b)
    assert a["norm"]["loose_match_key"] == b["norm"]["loose_match_key"]


def test_word_order_invariance():
    """Same words in different order produce same match keys."""
    pairs = [
        ("CHICKEN BREAST BNLS", "BNLS CHICKEN BREAST"),
        ("ALL PURPOSE FLOUR", "FLOUR ALL PURPOSE"),
        ("ROMA TOMATO 25LB", "TOMATO ROMA 25LB"),
        ("SHRIMP 31-35 HDLS", "SHRIMP HDLS 31-35"),
    ]
    for a_name, b_name in pairs:
        a = {"raw_name": a_name, "unit": "", "pack_size": "1/25 LB"}
        b = {"raw_name": b_name, "unit": "", "pack_size": "1/25 LB"}
        normalize_item(a)
        normalize_item(b)
        assert a["norm"]["strict_match_key"] == b["norm"]["strict_match_key"], f"strict mismatch: {a_name} vs {b_name}"
        assert a["norm"]["loose_match_key"] == b["norm"]["loose_match_key"], f"loose mismatch: {a_name} vs {b_name}"


def test_abbreviation_in_match_keys():
    """BNLS and BONELESS produce the same match key."""
    a = {"raw_name": "CHICKEN BREAST BNLS", "unit": "", "pack_size": ""}
    b = {"raw_name": "CHICKEN BREAST BONELESS", "unit": "", "pack_size": ""}
    normalize_item(a)
    normalize_item(b)
    assert a["norm"]["strict_match_key"] == b["norm"]["strict_match_key"]


def test_plural_in_match_keys():
    """TOMATOES and TOMATO produce the same match key."""
    a = {"raw_name": "Roma Tomatoes", "unit": "lb", "pack_size": ""}
    b = {"raw_name": "ROMA TOMATO", "unit": "lb", "pack_size": ""}
    normalize_item(a)
    normalize_item(b)
    assert a["norm"]["strict_match_key"] == b["norm"]["strict_match_key"]
    assert a["norm"]["loose_match_key"] == b["norm"]["loose_match_key"]


def test_unit_standardization():
    assert normalize_item({"raw_name": "X", "unit": "lb"})["norm"]["unit_std"] == "LB"
    assert normalize_item({"raw_name": "X", "unit": "lbs"})["norm"]["unit_std"] == "LB"
    assert normalize_item({"raw_name": "X", "unit": "bag"})["norm"]["unit_std"] == "BG"
    assert normalize_item({"raw_name": "X", "unit": "bottle"})["norm"]["unit_std"] == "BOTTLE"
    assert normalize_item({"raw_name": "X", "unit": "kg"})["norm"]["unit_std"] == "KG"
    assert normalize_item({"raw_name": "X", "unit": ""})["norm"]["unit_std"] == ""


def test_specs_extraction():
    item = {"raw_name": "GROUND BEEF 80-20", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["specs"] == {"grade": "80/20"}

    item = {"raw_name": "SHRIMP 31-35 HDLS", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["specs"] == {"size_code": "31-35"}

    item = {"raw_name": "Carf Meal #11", "unit": "", "pack_size": ""}
    normalize_item(item)
    assert item["norm"]["specs"] == {"product_code": "#11"}

    item = {"raw_name": "ROMA TOMATO 25LB", "unit": "", "pack_size": "1/25 LB"}
    normalize_item(item)
    assert item["norm"]["specs"] == {"embedded_weight": "25LB"}


def test_empty_raw_name():
    item = {"raw_name": "", "unit": "lb"}
    normalize_item(item)
    assert item["norm"]["clean_name"] == ""
    assert item["norm"]["base_name"] == ""
    assert item["norm"]["strict_match_key"] == ""
    assert item["norm"]["loose_match_key"] == ""
    assert item["norm"]["unit_std"] == "LB"


def test_original_fields_untouched():
    """normalize_item must NEVER modify raw_name or other original fields."""
    item = {"raw_name": "GROUND BEEF 80-20", "unit": "lb", "pack_size": "8/5 LB", "quantity": 3, "unit_price": 175.0}
    normalize_item(item)
    assert item["raw_name"] == "GROUND BEEF 80-20"
    assert item["unit"] == "lb"
    assert item["pack_size"] == "8/5 LB"
    assert item["quantity"] == 3
    assert item["unit_price"] == 175.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
