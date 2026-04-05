"""
Tests for vendor operational status guardrails:
- PFG limited mode: all items → needs_review
- Sysco operational: group text filtered, missing qty flagged, math checked
"""
import sys
import pytest
sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/routes")

from routes.upload import _validate_pfg_extraction, _validate_sysco_extraction


class TestPFGLimitedMode:
    """PFG items should always be marked needs_review until column separation is implemented."""

    def test_pfg_all_items_get_review(self):
        """After _validate_pfg_extraction, items may or may not be flagged.
        The pipeline then forces ALL PFG items to review. This tests the validator."""
        items = [
            {"raw_name": "OYSTER MEAT 18-24", "quantity": 6, "unit_price": 199.99,
             "total": 1199.94, "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SQUID TUBE RING", "quantity": 10, "unit_price": 29.69,
             "total": 296.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_pfg_extraction(items)
        # The pipeline in upload.py then forces all to review — tested at integration level


class TestSyscoOperationalGuardrails:
    """Sysco guardrails: group text, missing qty, math validation."""

    def test_group_text_flagged(self):
        """Items with 'GROUP TOTAL' or 'SUBTOTAL' text → extraction_failed."""
        items = [
            {"raw_name": "PAPA GROUP TOTAL DISP", "quantity": 2, "unit_price": 38.45,
             "total": 76.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0]["needs_review"] is True
        assert items[0]["confidence_level"] == "extraction_failed"
        assert any("group_text" in e for e in items[0]["validation_errors"])

    def test_subtotal_text_flagged(self):
        items = [
            {"raw_name": "POULTRY SUBTOTAL", "quantity": 0, "unit_price": 0,
             "total": 635.41, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0]["needs_review"] is True

    def test_missing_qty_flagged(self):
        """qty=0 with total>0 → needs_review_numeric."""
        items = [
            {"raw_name": "CONTAINER FOAM HNG", "quantity": 0, "unit_price": 13.50,
             "total": 326.04, "confidence_level": "trusted", "validation_errors": []},
        ]
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
        _validate_sysco_extraction(items)
        # 5×10=50 vs 80 → 37.5% off → needs_review_numeric
        assert items[0]["needs_review"] is True
        assert items[0]["confidence_level"] == "needs_review_numeric"
        assert any("math_mismatch" in e for e in items[0]["validation_errors"])

    def test_correct_math_passes(self):
        """qty × price ≈ total → stays trusted."""
        items = [
            {"raw_name": "CHICKEN CVP GIZZARD SM", "quantity": 3, "unit_price": 34.94,
             "total": 104.82, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0].get("confidence_level") == "trusted"
        assert items[0].get("needs_review") is not True

    def test_service_row_classified(self):
        """Fuel surcharge → service row."""
        items = [
            {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 6.50,
             "total": 6.50, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0].get("row_type") == "service"
        assert items[0].get("vendor_status") == "controlled_operational"

    def test_normal_product_passes(self):
        """Normal product with correct math → trusted + controlled_operational."""
        items = [
            {"raw_name": "KETCHUP PACKET FOIL", "quantity": 2, "unit_price": 18.95,
             "total": 37.90, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0].get("confidence_level") == "trusted"
        assert items[0].get("vendor_status") == "controlled_operational"

    def test_asterisk_header_flagged(self):
        """Row with *** → group header text, flagged."""
        items = [
            {"raw_name": "***POULTRY*** CHICKEN WING", "quantity": 1, "unit_price": 106.03,
             "total": 106.03, "confidence_level": "trusted", "validation_errors": []},
        ]
        _validate_sysco_extraction(items)
        assert items[0]["needs_review"] is True
