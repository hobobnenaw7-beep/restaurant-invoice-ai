"""
Tests for Sysco preprocessing validation improvements:
- Pack parse: dimension formats (1508X8X3) now accepted
- Pack parse: metric weight (10007 GM) doesn't trigger suspicious
- Service row detection: fuel surcharge, delivery fee
- Trust level: math-passing items not downgraded by pack noise
"""

import sys
import pytest

sys.path.insert(0, "/app/backend")

from preprocessing import (
    parse_pack_size,
    validate_and_score_item,
    enrich_item_with_pack_size,
    _detect_suspicious_patterns,
)


class TestPackParseDimensions:
    """Dimension packs like '1508X8X3' should parse, not fail."""

    def test_3segment_dimension(self):
        result = parse_pack_size("1508X8X3")
        assert result["pack_parse_status"] == "parsed", \
            f"'1508X8X3' should parse as dimension, got status={result['pack_parse_status']}"

    def test_3segment_lowercase(self):
        result = parse_pack_size("12x10x5")
        assert result["pack_parse_status"] == "parsed"

    def test_2segment_dimension(self):
        """2-segment already handled by pattern 4b, verify it still works."""
        result = parse_pack_size("12x10")
        assert result["pack_parse_status"] == "parsed"


class TestPackParseMetric:
    """Metric units like '10007 GM' should parse and not trigger suspicious."""

    def test_grams_parse(self):
        result = parse_pack_size("10007 GM")
        assert result["pack_parse_status"] == "parsed"
        assert result["unit"] == "G"  # Canonicalized

    def test_grams_not_suspicious(self):
        """10007 GM = ~22 LB, should NOT trigger unrealistic case weight."""
        item = {
            "raw_name": "KETCHUP FCY", "quantity": 2, "unit_price": 24.50,
            "total": 49.00, "pack_size": "10007 GM",
        }
        enrich_item_with_pack_size(item)
        flags = _detect_suspicious_patterns(item)
        sus_weight = [f for f in flags if "unrealistic case weight" in f]
        assert not sus_weight, f"10007 GM should not be flagged as unrealistic: {flags}"

    def test_5000_lb_is_suspicious(self):
        """5000 LB IS unrealistic."""
        item = {
            "raw_name": "TEST ITEM", "quantity": 1, "unit_price": 10.00,
            "total": 10.00,
            "total_case_weight": 5001, "pack_unit": "LB",
        }
        flags = _detect_suspicious_patterns(item)
        assert any("unrealistic case weight" in f for f in flags)


class TestServiceRowDetection:
    """Service rows bypass pack validation."""

    def test_fuel_surcharge_trusted(self):
        """Fuel surcharge with correct math → trusted, no pack penalty."""
        item = {
            "raw_name": "Fuel Surcharge", "quantity": 1,
            "unit_price": 5.99, "total": 5.99, "pack_size": "",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["confidence_level"] == "trusted", \
            f"Fuel surcharge should be trusted, got {item['confidence_level']}: {item.get('validation_errors')}"
        assert item["row_type"] == "service"

    def test_delivery_fee_trusted(self):
        item = {
            "raw_name": "DELIVERY FEE", "quantity": 1,
            "unit_price": 12.50, "total": 12.50, "pack_size": "",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["confidence_level"] == "trusted"
        assert item["row_type"] == "service"

    def test_normal_product_not_service(self):
        item = {
            "raw_name": "HEINZ KETCHUP FCY", "quantity": 2,
            "unit_price": 24.50, "total": 49.00, "pack_size": "6/10 LB",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["row_type"] == "product"


class TestMathPassesPackNoise:
    """When math is correct, pack noise should NOT downgrade trust."""

    def test_unrecognized_pack_with_math_ok(self):
        """Unrecognized pack format but math passes → still trusted."""
        item = {
            "raw_name": "CHICKEN BREAST BNLS", "quantity": 4,
            "unit_price": 22.50, "total": 90.00, "pack_size": "WEIRD-FORMAT",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["confidence_level"] == "trusted", \
            f"Math passes, so unrecognized pack should not block trust: {item.get('validation_errors')}"
        # Should have an informational warning, not a hard error
        errors = item.get("validation_errors", [])
        assert any("informational" in e for e in errors), \
            f"Expected informational warning for unrecognized pack, got: {errors}"

    def test_dimension_pack_not_failed(self):
        """Dimension pack '1508X8X3' should parse correctly now."""
        item = {
            "raw_name": "NAPKIN DINNER 2PLY WHT", "quantity": 1,
            "unit_price": 32.00, "total": 32.00, "pack_size": "1508X8X3",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["pack_parse_status"] == "parsed", \
            f"'1508X8X3' should parse, got status={item['pack_parse_status']}"
        assert item["confidence_level"] == "trusted", \
            f"Dimension pack should not prevent trust: {item.get('validation_errors')}"

    def test_grams_pack_not_suspicious(self):
        """'10007 GM' pack with correct math → trusted."""
        item = {
            "raw_name": "HEINZ KETCHUP FCY", "quantity": 2,
            "unit_price": 24.50, "total": 49.00, "pack_size": "10007 GM",
        }
        enrich_item_with_pack_size(item)
        validate_and_score_item(item)
        assert item["confidence_level"] == "trusted", \
            f"10007 GM with correct math should be trusted: {item.get('validation_errors')}"
