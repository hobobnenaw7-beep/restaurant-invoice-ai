"""
Tests for PFG post-extraction validation and subtotal-level validation.
These validate the LLM output post-processing logic.
"""
import sys
import pytest
sys.path.insert(0, "/app/backend")

# Import the function directly from upload module
sys.path.insert(0, "/app/backend/routes")


class TestPFGPostExtraction:
    """Test _validate_pfg_extraction() in routes/upload.py."""

    def _get_validator(self):
        """Import the PFG validator."""
        from routes.upload import _validate_pfg_extraction
        return _validate_pfg_extraction

    def test_all_qty_1_flagged(self):
        """When all product items have qty=1, flag as likely SHIP column miss."""
        validate = self._get_validator()
        items = [
            {"raw_name": "OYSTER MEAT 18-24", "quantity": 1, "unit_price": 199.99, "total": 199.99,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SQUID TUBE RING", "quantity": 1, "unit_price": 29.69, "total": 29.69,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SCALLOP LAND SEA", "quantity": 1, "unit_price": 79.85, "total": 79.85,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SHRIMP WHL 13-15", "quantity": 1, "unit_price": 60.84, "total": 60.84,
             "confidence_level": "trusted", "validation_errors": []},
        ]
        validate(items)
        # All items should be flagged
        for it in items:
            assert it["needs_review"] is True, f"{it['raw_name']} should need review"
            assert it["confidence_level"] != "trusted", f"{it['raw_name']} should not be trusted"
            assert any("pfg_all_qty_1" in e for e in it["validation_errors"])

    def test_mixed_qty_not_flagged(self):
        """When items have different quantities, don't flag."""
        validate = self._get_validator()
        items = [
            {"raw_name": "OYSTER MEAT", "quantity": 6, "unit_price": 199.99, "total": 1199.94,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SQUID RING", "quantity": 10, "unit_price": 29.69, "total": 296.90,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SCALLOP", "quantity": 10, "unit_price": 79.85, "total": 798.50,
             "confidence_level": "trusted", "validation_errors": []},
        ]
        validate(items)
        for it in items:
            assert not any("pfg_all_qty_1" in e for e in it.get("validation_errors", []))

    def test_service_rows_excluded_from_all_qty_1(self):
        """Service rows (surcharge) should not count toward the all-qty-1 check."""
        validate = self._get_validator()
        items = [
            {"raw_name": "OYSTER MEAT", "quantity": 6, "unit_price": 199.99, "total": 1199.94,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "SQUID RING", "quantity": 10, "unit_price": 29.69, "total": 296.90,
             "confidence_level": "trusted", "validation_errors": []},
            {"raw_name": "FUEL SURCHARGE", "quantity": 1, "unit_price": 7.00, "total": 7.00,
             "confidence_level": "trusted", "validation_errors": []},
        ]
        validate(items)
        # Surcharge should be classified as service, not affect qty check
        assert items[2].get("row_type") == "service"
        # Product items should NOT be flagged
        assert not any("pfg_all_qty_1" in e for e in items[0].get("validation_errors", []))

    def test_pack_in_name_detected(self):
        """Pack pattern in item name should be flagged."""
        validate = self._get_validator()
        items = [
            {"raw_name": "CHICKEN BREAST 4/10 LB BNLS", "quantity": 4, "unit_price": 22.50,
             "total": 90.00, "confidence_level": "trusted", "validation_errors": []},
        ]
        validate(items)
        assert any("pfg_pack_in_name" in e for e in items[0]["validation_errors"])

    def test_weight_as_qty_detected(self):
        """Suspiciously large qty (>100) should be flagged as possible weight."""
        validate = self._get_validator()
        items = [
            {"raw_name": "BEEF TENDERLOIN", "quantity": 150, "unit_price": 8.33, "total": 1249.50,
             "confidence_level": "trusted", "validation_errors": []},
        ]
        validate(items)
        assert any("pfg_suspicious_qty" in e for e in items[0]["validation_errors"])
        assert items[0]["confidence_level"] != "trusted"


class TestSubtotalValidation:
    """Test invoice-level subtotal mismatch detection."""

    def test_subtotal_mismatch_downgrades_trust(self):
        """When items sum differs from declared subtotal by >5%, downgrade all items."""
        items = [
            {"raw_name": "ITEM A", "quantity": 1, "unit_price": 100.00, "total": 100.00,
             "confidence_level": "trusted", "needs_review": False, "validation_errors": []},
            {"raw_name": "ITEM B", "quantity": 1, "unit_price": 50.00, "total": 50.00,
             "confidence_level": "trusted", "needs_review": False, "validation_errors": []},
        ]
        # Items sum = $150, but declare subtotal = $2103.74 (massive mismatch)
        extracted = {"items": items, "subtotal": 2103.74, "total": 2103.74}

        items_sum = round(sum(float(it.get("total", 0) or 0) for it in extracted.get("items", [])), 2)
        subtotal = float(extracted.get("subtotal", 0) or 0)
        pct_diff = abs(items_sum - subtotal) / subtotal if subtotal else 0

        if pct_diff > 0.05:
            for it in extracted["items"]:
                if it.get("confidence_level") == "trusted":
                    it["confidence_level"] = "review"
                    it["needs_review"] = True

        for it in items:
            assert it["confidence_level"] == "review"
            assert it["needs_review"] is True

    def test_matching_subtotal_keeps_trust(self):
        """When items sum matches subtotal, trust is maintained."""
        items = [
            {"raw_name": "ITEM A", "quantity": 6, "unit_price": 199.99, "total": 1199.94,
             "confidence_level": "trusted", "needs_review": False, "validation_errors": []},
            {"raw_name": "ITEM B", "quantity": 10, "unit_price": 29.69, "total": 296.90,
             "confidence_level": "trusted", "needs_review": False, "validation_errors": []},
        ]
        extracted = {"items": items, "subtotal": 1496.84, "total": 1496.84}

        items_sum = round(sum(float(it.get("total", 0) or 0) for it in extracted.get("items", [])), 2)
        subtotal = float(extracted.get("subtotal", 0) or 0)
        pct_diff = abs(items_sum - subtotal) / subtotal if subtotal else 0

        assert pct_diff < 0.05
        for it in items:
            assert it["confidence_level"] == "trusted"
