"""
Tests for Sysco validation/classification improvements:
- Row classification (product vs service)
- Expanded pack format handling (dimensions, volume, metric)
- Trust level computation (math + fields + classification)
- Service rows bypass pack validation
- OCR-noisy packs don't downgrade trust when math passes
"""

import sys
import pytest

sys.path.insert(0, "/app/backend")

from services.semantic_validator import (
    classify_row_type,
    is_valid_pack_format,
    compute_trust_level,
    run_semantic_validation,
)


# ═══════════════════════════════════════════════════════════
# TESTS: Row Classification
# ═══════════════════════════════════════════════════════════

class TestRowClassification:
    """Service rows must be classified as 'service', products as 'product'."""

    def test_fuel_surcharge_is_service(self):
        item = {"item_name": "Fuel Surcharge", "quantity": 1, "unit_price": 5.99, "total_price": 5.99}
        assert classify_row_type(item) == "service"

    def test_delivery_fee_is_service(self):
        item = {"item_name": "DELIVERY FEE", "quantity": 0, "unit_price": 0, "total_price": 12.50, "pack_size": ""}
        assert classify_row_type(item) == "service"

    def test_credit_adjustment_is_service(self):
        item = {"item_name": "Credit Adjustment", "quantity": 0, "unit_price": 0, "total_price": -15.00}
        assert classify_row_type(item) == "service"

    def test_discount_is_service(self):
        item = {"item_name": "Volume Discount", "quantity": 0, "unit_price": 0, "total_price": -25.00}
        assert classify_row_type(item) == "service"

    def test_normal_product_is_product(self):
        item = {"item_name": "HEINZ KETCHUP FCY", "quantity": 2, "unit_price": 24.50, "total_price": 49.00, "pack_size": "6/#10"}
        assert classify_row_type(item) == "product"

    def test_chicken_breast_is_product(self):
        item = {"item_name": "CHICKEN BREAST BNLS SKNLS", "quantity": 4, "unit_price": 2.15, "total_price": 86.00}
        assert classify_row_type(item) == "product"

    def test_empty_name_is_product(self):
        """Empty name defaults to product (will be caught by other checks)."""
        item = {"item_name": "", "quantity": 1, "unit_price": 5.00, "total_price": 5.00}
        assert classify_row_type(item) == "product"

    def test_return_deposit_is_service(self):
        item = {"item_name": "RETURN DEPOSIT", "quantity": 0, "unit_price": 0, "total_price": -5.00}
        assert classify_row_type(item) == "service"


# ═══════════════════════════════════════════════════════════
# TESTS: Pack Format Validation
# ═══════════════════════════════════════════════════════════

class TestPackFormatValidation:
    """Expanded pack format acceptance."""

    def test_weight_format(self):
        assert is_valid_pack_format("6/4 LB") is True

    def test_volume_format(self):
        assert is_valid_pack_format("4 GAL") is True

    def test_count_format(self):
        assert is_valid_pack_format("24 CT") is True

    def test_dimension_format(self):
        """1508X8X3 is a valid dimension-based pack."""
        assert is_valid_pack_format("1508X8X3") is True

    def test_dimension_2d(self):
        assert is_valid_pack_format("12X10") is True

    def test_ratio_format(self):
        assert is_valid_pack_format("6/4") is True

    def test_metric_weight(self):
        """10007 GM is a valid metric weight pack."""
        assert is_valid_pack_format("10007 GM") is True

    def test_pound_hash(self):
        assert is_valid_pack_format("25#") is True

    def test_standard_weight_pack(self):
        assert is_valid_pack_format("2/5 OZ") is True

    def test_each_format(self):
        assert is_valid_pack_format("1 EA") is True

    def test_empty_not_valid(self):
        assert is_valid_pack_format("") is False

    def test_none_not_valid(self):
        assert is_valid_pack_format(None) is False


# ═══════════════════════════════════════════════════════════
# TESTS: Trust Level Computation
# ═══════════════════════════════════════════════════════════

class TestTrustLevel:
    """Trust level = math + fields + classification."""

    def test_math_pass_no_flags_is_trusted(self):
        item = {
            "item_name": "KETCHUP", "quantity": 2, "unit_price": 10.00, "total_price": 20.00,
            "validation": {"status": "pass"}, "semantic_flags": [], "row_type": "product",
        }
        assert compute_trust_level(item) == "trusted"

    def test_math_pass_with_pack_noise_is_trusted(self):
        """OCR-noisy pack with correct math → trusted (not downgraded)."""
        item = {
            "item_name": "KETCHUP FCY", "quantity": 2, "unit_price": 24.50, "total_price": 49.00,
            "validation": {"status": "pass"},
            "semantic_flags": ["pack_format_unusual: '10007 GM' (math OK, informational)"],
            "row_type": "product",
        }
        assert compute_trust_level(item) == "trusted"

    def test_math_fail_is_needs_review(self):
        item = {
            "item_name": "CHICKEN", "quantity": 5, "unit_price": 10.00, "total_price": 99.00,
            "validation": {"status": "needs_review"}, "semantic_flags": [], "row_type": "product",
        }
        assert compute_trust_level(item) == "needs_review"

    def test_service_row_with_total_is_trusted(self):
        """Service row with correct amount → trusted after classification."""
        item = {
            "item_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 5.99, "total_price": 5.99,
            "validation": {"status": "pass"}, "semantic_flags": [], "row_type": "service",
        }
        assert compute_trust_level(item) == "trusted"

    def test_service_row_no_total_is_info(self):
        item = {
            "item_name": "DELIVERY FEE", "quantity": 0, "unit_price": 0, "total_price": 0,
            "validation": {"status": "pass"}, "semantic_flags": [], "row_type": "service",
        }
        assert compute_trust_level(item) == "info"

    def test_ambiguous_structure_is_warning(self):
        """Rows with structural ambiguity should NOT be trusted."""
        item = {
            "item_name": "XY", "quantity": 2, "unit_price": 10.00, "total_price": 20.00,
            "validation": {"status": "pass"},
            "semantic_flags": ["truncated_name: 'XY' (2 chars)"],
            "row_type": "product",
        }
        assert compute_trust_level(item) == "warning"

    def test_missing_critical_fields_is_warning(self):
        item = {
            "item_name": "", "quantity": 0, "unit_price": 0, "total_price": 0,
            "validation": {"status": "pass"}, "semantic_flags": [], "row_type": "product",
        }
        assert compute_trust_level(item) == "warning"

    def test_math_warning_no_structural_is_trusted(self):
        """Close math (warning) without structural issues → trusted."""
        item = {
            "item_name": "RICE LONG GRAIN", "quantity": 10, "unit_price": 5.00, "total_price": 50.25,
            "validation": {"status": "warning"},
            "semantic_flags": [],
            "row_type": "product",
        }
        assert compute_trust_level(item) == "trusted"


# ═══════════════════════════════════════════════════════════
# TESTS: Sysco-specific scenarios
# ═══════════════════════════════════════════════════════════

class TestSyscoScenarios:
    """End-to-end scenarios for Sysco validation issues."""

    def test_ketchup_not_downgraded_with_correct_math(self):
        """
        Ketchup row with OCR-noisy pack '10007 GM' but correct math
        should NOT be downgraded. Trust level should be 'trusted'.
        """
        items = [
            {
                "item_name": "HEINZ KETCHUP FCY", "quantity": 2,
                "unit_price": 24.50, "total_price": 49.00, "pack_size": "10007 GM",
                "validation": {"status": "pass", "issues": [], "computed_total": 49.00,
                               "total_diff": 0.0, "total_diff_pct": 0.0},
            }
        ]
        result = run_semantic_validation(items, vendor="Sysco")
        assert items[0]["trust_level"] == "trusted", \
            f"Ketchup should be 'trusted' (math passes), got '{items[0]['trust_level']}'"

    def test_dimension_pack_not_flagged_as_failure(self):
        """
        Dimension-based pack '1508X8X3' should NOT produce 'pack_parse_failed'.
        """
        items = [
            {
                "item_name": "NAPKIN DINNER 2PLY WHT", "quantity": 1,
                "unit_price": 32.00, "total_price": 32.00, "pack_size": "1508X8X3",
                "validation": {"status": "pass", "issues": [], "computed_total": 32.00,
                               "total_diff": 0.0, "total_diff_pct": 0.0},
            }
        ]
        result = run_semantic_validation(items, vendor="Sysco")
        flags = items[0].get("semantic_flags", [])
        assert not any("pack_parse_failed" in f for f in flags), \
            f"Dimension pack '1508X8X3' flagged as failure: {flags}"
        assert items[0]["trust_level"] == "trusted"

    def test_service_row_bypasses_pack_validation(self):
        """
        Fuel surcharge row should bypass pack validation entirely
        and be classified as 'service'.
        """
        items = [
            {
                "item_name": "FUEL SURCHARGE", "quantity": 1,
                "unit_price": 7.99, "total_price": 7.99, "pack_size": "",
                "validation": {"status": "pass", "issues": [], "computed_total": 7.99,
                               "total_diff": 0.0, "total_diff_pct": 0.0},
            }
        ]
        result = run_semantic_validation(items, vendor="Sysco")
        assert items[0]["row_type"] == "service"
        flags = items[0].get("semantic_flags", [])
        assert not any("distributor_missing_pack_size" in f for f in flags), \
            f"Service row should not get pack validation: {flags}"
        assert items[0]["trust_level"] == "trusted"

    def test_mixed_products_and_service(self):
        """
        Invoice with products and a service row: each classified correctly.
        """
        items = [
            {
                "item_name": "CHICKEN BREAST BNLS 10LB", "quantity": 4,
                "unit_price": 22.50, "total_price": 90.00, "pack_size": "4/10 LB",
                "validation": {"status": "pass", "issues": [], "computed_total": 90.00,
                               "total_diff": 0.0, "total_diff_pct": 0.0},
            },
            {
                "item_name": "DELIVERY SURCHARGE", "quantity": 1,
                "unit_price": 9.99, "total_price": 9.99, "pack_size": "",
                "validation": {"status": "pass", "issues": [], "computed_total": 9.99,
                               "total_diff": 0.0, "total_diff_pct": 0.0},
            },
        ]
        result = run_semantic_validation(items, vendor="Sysco")
        assert items[0]["row_type"] == "product"
        assert items[1]["row_type"] == "service"
        assert items[0]["trust_level"] == "trusted"
        assert items[1]["trust_level"] == "trusted"
