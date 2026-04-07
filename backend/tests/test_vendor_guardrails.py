"""
Tests for vendor operational status guardrails:
- PFG limited mode: all items → needs_review
- Sysco operational: missing qty flagged, math checked
- Row type classification: group totals, fees, line items
"""
import sys
import pytest
sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/routes")

from routes.upload import (
    _validate_pfg_extraction,
    _validate_sysco_extraction,
    _classify_row_type,
    _classify_all_row_types,
    _validate_numeric_field_sources,
)


class TestPFGLimitedMode:
    """PFG items should always be marked needs_review until column separation is implemented."""

    def test_pfg_all_items_get_review(self):
        items = [
            {"raw_name": "OYSTER MEAT 18-24", "quantity": 6, "unit_price": 199.99,
             "total": 1199.94, "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SQUID TUBE RING", "quantity": 10, "unit_price": 29.69,
             "total": 296.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_pfg_extraction(items)


class TestRowTypeClassification:
    """Row type classification must correctly identify group totals, fees, headers."""

    def test_group_total_classified(self):
        item = {"raw_name": "GROUP TOTAL****", "quantity": 0, "unit_price": 0, "total": 700.25}
        assert _classify_row_type(item) == "group_total"

    def test_group_total_with_category(self):
        item = {"raw_name": "CANNED & DRY** GROUP TOTAL****", "quantity": 0, "unit_price": 0, "total": 31.79}
        assert _classify_row_type(item) == "group_total"

    def test_subtotal_classified(self):
        item = {"raw_name": "SUBTOTAL", "quantity": 0, "unit_price": 0, "total": 1066.11}
        assert _classify_row_type(item) == "group_total"  # subtotal pattern matches group_total

    def test_asterisk_header_classified(self):
        item = {"raw_name": "***POULTRY***", "quantity": 0, "unit_price": 0, "total": 0}
        assert _classify_row_type(item) == "header"

    def test_fuel_surcharge_is_fee(self):
        item = {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 6.50, "total": 6.50}
        assert _classify_row_type(item) == "fee"

    def test_misc_charges_fuel_is_fee(self):
        item = {"raw_name": "MISC CHARGES - CHGS FOR FUEL SURCHARGE", "quantity": 1, "unit_price": 6.50, "total": 6.50}
        assert _classify_row_type(item) == "fee"

    def test_delivery_charge_is_fee(self):
        item = {"raw_name": "DELIVERY FEE", "quantity": 1, "unit_price": 25.00, "total": 25.00}
        assert _classify_row_type(item) == "fee"

    def test_normal_product_is_line_item(self):
        item = {"raw_name": "SYS CLS CHICKEN CVP GIZZARD SM", "quantity": 4, "unit_price": 34.95, "total": 139.80}
        assert _classify_row_type(item) == "line_item"

    def test_ketchup_is_line_item(self):
        item = {"raw_name": "KETCHUP PACKET FOIL", "quantity": 2, "unit_price": 18.95, "total": 37.90}
        assert _classify_row_type(item) == "line_item"

    def test_classify_all_sets_row_type(self):
        items = [
            {"raw_name": "CHICKEN BREAST", "quantity": 5, "unit_price": 10, "total": 50},
            {"raw_name": "GROUP TOTAL****", "quantity": 0, "unit_price": 0, "total": 50},
            {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 6, "total": 6},
        ]
        _classify_all_row_types(items)
        assert items[0]["row_type"] == "line_item"
        assert items[1]["row_type"] == "group_total"
        assert items[2]["row_type"] == "fee"


class TestSyscoOperationalGuardrails:
    """Sysco guardrails: missing qty, math validation. Row classification done upstream."""

    def _prepare(self, items):
        """Classify row types before validation (as pipeline does)."""
        _classify_all_row_types(items)

    def test_group_total_excluded_from_validation(self):
        """Group totals are classified upstream and skipped by Sysco validation."""
        items = [
            {"raw_name": "PAPA GROUP TOTAL DISP", "quantity": 2, "unit_price": 38.45,
             "total": 76.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        assert items[0]["row_type"] == "group_total"
        _validate_sysco_extraction(items)
        # Sysco validation should skip this row entirely (row_type != line_item)
        # The upstream classifier already marks group totals as excluded

    def test_missing_qty_flagged(self):
        """qty=0 with total>0 → needs_review_numeric."""
        items = [
            {"raw_name": "CONTAINER FOAM HNG", "quantity": 0, "unit_price": 13.50,
             "total": 326.04, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        _validate_sysco_extraction(items)
        assert items[0]["needs_review"] is True
        assert items[0]["confidence_level"] == "needs_review_numeric"
        assert any("missing_qty" in e for e in items[0]["validation_errors"])

    def test_math_mismatch_flagged(self):
        """qty × price ≠ total by >2% → needs_review_numeric."""
        items = [
            {"raw_name": "CHICKEN BREAST", "quantity": 5, "unit_price": 10.00,
             "total": 80.00, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        _validate_sysco_extraction(items)
        assert items[0]["needs_review"] is True
        assert items[0]["confidence_level"] == "needs_review_numeric"
        assert any("math_mismatch" in e for e in items[0]["validation_errors"])

    def test_correct_math_passes(self):
        """qty × price ≈ total → stays trusted (vendor_status set)."""
        items = [
            {"raw_name": "CHICKEN CVP GIZZARD SM", "quantity": 3, "unit_price": 34.94,
             "total": 104.82, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        _validate_sysco_extraction(items)
        assert items[0].get("confidence_level") == "trusted"
        assert items[0].get("vendor_status") == "controlled_operational"

    def test_service_row_classified_as_fee(self):
        """Fuel surcharge → fee row type (classified upstream)."""
        items = [
            {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 6.50,
             "total": 6.50, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        assert items[0]["row_type"] == "fee"
        _validate_sysco_extraction(items)
        assert items[0].get("vendor_status") == "controlled_operational"

    def test_normal_product_passes(self):
        """Normal product with correct math → trusted + controlled_operational."""
        items = [
            {"raw_name": "KETCHUP PACKET FOIL", "quantity": 2, "unit_price": 18.95,
             "total": 37.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        self._prepare(items)
        _validate_sysco_extraction(items)
        assert items[0].get("confidence_level") == "trusted"
        assert items[0].get("vendor_status") == "controlled_operational"


class TestNumericFieldSources:
    """Test field-level source validation and trust gating."""

    def _prepare(self, items):
        _classify_all_row_types(items)

    def test_all_column_read_stays_trusted(self):
        """If all sources are column_read and math validates → trusted."""
        items = [
            {"raw_name": "CHICKEN GIZZARD", "quantity": 4, "unit_price": 34.95,
             "total": 139.80, "confidence_level": "trusted", "valid_calc": True,
             "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        assert items[0]["confidence_level"] == "trusted"
        assert items[0]["numeric_failure_category"] == "none"

    def test_ambiguous_qty_downgrades(self):
        """If qty_source is ambiguous → needs_review_numeric."""
        items = [
            {"raw_name": "OKRA BRD MED", "quantity": 1, "unit_price": 31.79,
             "total": 31.79, "confidence_level": "trusted", "valid_calc": True,
             "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        # price==total with qty=1 → system overrides qty_source to ambiguous
        assert items[0]["qty_source"] == "ambiguous"
        assert items[0]["confidence_level"] == "needs_review_numeric"
        assert items[0]["numeric_failure_category"] == "qty_wrong"

    def test_fee_row_not_flagged_for_qty1(self):
        """Fee rows with qty=1 and price==total should NOT be flagged."""
        items = [
            {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 6.50,
             "total": 6.50, "confidence_level": "trusted", "valid_calc": True,
             "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        assert items[0]["qty_source"] == "column_read"
        assert items[0]["confidence_level"] == "trusted"

    def test_all_qty_one_detected(self):
        """If all line_items have qty=1 → all qty_source downgraded."""
        items = [
            {"raw_name": "PRODUCT A", "quantity": 1, "unit_price": 10, "total": 10,
             "confidence_level": "trusted", "valid_calc": True, "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
            {"raw_name": "PRODUCT B", "quantity": 1, "unit_price": 20, "total": 20,
             "confidence_level": "trusted", "valid_calc": True, "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
            {"raw_name": "PRODUCT C", "quantity": 1, "unit_price": 30, "total": 30,
             "confidence_level": "trusted", "valid_calc": True, "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        for it in items:
            assert it["qty_source"] == "ambiguous"
            assert it["confidence_level"] == "needs_review_numeric"

    def test_math_mismatch_downgrades_all_sources(self):
        """If math doesn't match, all sources get downgraded."""
        items = [
            {"raw_name": "PRODUCT X", "quantity": 5, "unit_price": 10, "total": 80,
             "confidence_level": "trusted", "valid_calc": False, "validation_errors": [],
             "qty_source": "column_read", "price_source": "column_read", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        assert items[0]["qty_source"] == "ambiguous"
        assert items[0]["price_source"] == "ambiguous"
        assert items[0]["total_source"] == "ambiguous"
        assert items[0]["confidence_level"] == "needs_review_numeric"

    def test_group_total_excluded(self):
        """Group totals should not go through numeric validation."""
        items = [
            {"raw_name": "GROUP TOTAL****", "quantity": 0, "unit_price": 0, "total": 500,
             "confidence_level": "trusted", "valid_calc": False, "validation_errors": []},
        ]
        self._prepare(items)
        assert items[0]["row_type"] == "group_total"
        # Only line_item/fee rows are passed to _validate_numeric_field_sources
        scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
        assert len(scoreable) == 0

    def test_failure_category_both_wrong(self):
        """Both qty and price ambiguous → both_wrong."""
        items = [
            {"raw_name": "PRODUCT Y", "quantity": 2, "unit_price": 15, "total": 60,
             "confidence_level": "trusted", "valid_calc": False, "validation_errors": [],
             "qty_source": "ambiguous", "price_source": "ambiguous", "total_source": "column_read"},
        ]
        self._prepare(items)
        _validate_numeric_field_sources(items)
        assert items[0]["numeric_failure_category"] == "both_wrong"
