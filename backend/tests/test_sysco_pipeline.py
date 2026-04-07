"""
Tests for Sysco Table Reconstruction Pipeline.
Tests each stage independently: OCR, row segmentation, column detection,
row classification, numeric extraction, validation, trust gate.
"""
import sys
import io
import base64
import numpy as np
import cv2
import pytest
from PIL import Image

sys.path.insert(0, "/app/backend")

from services.sysco_pipeline import (
    _extract_words,
    _segment_rows,
    _detect_columns,
    _data_driven_column_detection,
    _is_numeric_word,
    _cluster_x_positions,
    _classify_structured_row,
    _build_structured_rows,
    _extract_numerics,
    _validate_item_math,
    _apply_trust_gate,
    _validate_subtotal,
    _parse_number,
    _trim_footer_rows,
    run_sysco_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_image(w=800, h=1100):
    """Create a simple test image with text-like content."""
    img = np.ones((h, w, 3), dtype=np.uint8) * 255
    for y in range(100, h - 100, 40):
        cv2.line(img, (50, y), (w - 50, y), (30, 30, 30), 1)
    return Image.fromarray(img)


def _img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# Tests: _parse_number
# ---------------------------------------------------------------------------

class TestParseNumber:
    def test_simple_int(self):
        assert _parse_number("42") == 42.0

    def test_decimal(self):
        assert _parse_number("34.95") == 34.95

    def test_with_dollar(self):
        assert _parse_number("$499.50") == 499.50

    def test_with_comma(self):
        assert _parse_number("1,234.56") == 1234.56

    def test_negative_parens(self):
        assert _parse_number("(12.50)") == -12.50

    def test_empty(self):
        assert _parse_number("") is None

    def test_non_numeric(self):
        assert _parse_number("abc") is None

    def test_ocr_noise(self):
        assert _parse_number("$34.95|") == 34.95

    def test_trailing_garbage(self):
        assert _parse_number("19.50;") == 19.50


# ---------------------------------------------------------------------------
# Tests: _is_numeric_word
# ---------------------------------------------------------------------------

class TestIsNumericWord:
    def test_integer(self):
        assert _is_numeric_word("42") is True

    def test_decimal(self):
        assert _is_numeric_word("34.95") is True

    def test_dollar(self):
        assert _is_numeric_word("$499.50") is True

    def test_word(self):
        assert _is_numeric_word("CHICKEN") is False

    def test_mixed(self):
        # "410LB" has 2 non-numeric chars — correctly rejected as not a standalone number
        assert _is_numeric_word("410LB") is False

    def test_code_with_pipe(self):
        assert _is_numeric_word("329|") is True  # 1 non-numeric char

    def test_code(self):
        assert _is_numeric_word("2880029418") is True


# ---------------------------------------------------------------------------
# Tests: _cluster_x_positions
# ---------------------------------------------------------------------------

class TestClusterXPositions:
    def test_basic_clusters(self):
        positions = [100, 105, 110, 500, 510, 520, 900, 910]
        clusters = _cluster_x_positions(positions, min_gap=80)
        assert len(clusters) == 3
        assert clusters[0]["center"] < clusters[1]["center"] < clusters[2]["center"]

    def test_single_cluster(self):
        positions = [100, 105, 110, 115]
        clusters = _cluster_x_positions(positions, min_gap=80)
        assert len(clusters) == 1

    def test_filters_small_clusters(self):
        positions = [100, 500, 501, 900, 901]
        clusters = _cluster_x_positions(positions, min_gap=80)
        # Position 100 is alone → filtered out (count < 2)
        assert all(c["count"] >= 2 for c in clusters)


# ---------------------------------------------------------------------------
# Tests: _classify_structured_row
# ---------------------------------------------------------------------------

class TestClassifyStructuredRow:
    def _make_row(self, raw_text, desc="", qty="", total="", words=5):
        return {
            "raw_text": raw_text,
            "description_text": desc or raw_text,
            "qty_text": qty,
            "total_text": total,
            "word_count": words,
        }

    def test_group_total(self):
        row = self._make_row("GROUP TOTAL****")
        assert _classify_structured_row(row) == "group_total"

    def test_subtotal(self):
        row = self._make_row("SUBTOTAL", words=1)
        assert _classify_structured_row(row) == "group_total"

    def test_header_asterisks(self):
        row = self._make_row("***POULTRY***", words=1)
        assert _classify_structured_row(row) == "header"

    def test_tax_line(self):
        row = self._make_row("SALES TAX", words=2)
        assert _classify_structured_row(row) == "tax"

    def test_fee_line(self):
        row = self._make_row("FUEL SURCHARGE", words=2)
        assert _classify_structured_row(row) == "fee"

    def test_normal_product(self):
        row = self._make_row("SYS CLS CHICKEN CVP GIZZARD SM", total="139.80", words=6)
        assert _classify_structured_row(row) == "line_item"

    def test_order_summary(self):
        row = self._make_row("ORDER SUMMARY", words=2)
        assert _classify_structured_row(row) == "subtotal"


# ---------------------------------------------------------------------------
# Tests: _validate_item_math
# ---------------------------------------------------------------------------

class TestValidateItemMath:
    def test_correct_math(self):
        item = {"quantity": 4, "unit_price": 34.95, "total": 139.80}
        _validate_item_math(item)
        assert item["valid_calc"] is True

    def test_math_mismatch(self):
        item = {"quantity": 4, "unit_price": 34.95, "total": 1393.30}
        _validate_item_math(item)
        assert item["valid_calc"] is False
        assert any("math_mismatch" in e for e in item["validation_errors"])

    def test_missing_qty(self):
        item = {"quantity": 0, "unit_price": 18.95, "total": 94.75}
        _validate_item_math(item)
        assert item["valid_calc"] is False
        assert any("missing_qty" in e for e in item["validation_errors"])

    def test_missing_total(self):
        item = {"quantity": 3, "unit_price": 39.25, "total": 0}
        _validate_item_math(item)
        assert item["valid_calc"] is False


# ---------------------------------------------------------------------------
# Tests: _apply_trust_gate
# ---------------------------------------------------------------------------

class TestApplyTrustGate:
    def test_all_column_read_trusted(self):
        item = {
            "raw_name": "CHICKEN WING",
            "quantity": 10, "unit_price": 49.95, "total": 499.50,
            "qty_source": "column_read", "price_source": "column_read",
            "total_source": "column_read", "valid_calc": True,
        }
        _apply_trust_gate(item)
        assert item["confidence_level"] == "trusted"
        assert item["needs_review"] is False

    def test_ambiguous_qty_review(self):
        item = {
            "raw_name": "OKRA BRD",
            "quantity": 0, "unit_price": 31.79, "total": 31.79,
            "qty_source": "ambiguous", "price_source": "column_read",
            "total_source": "column_read", "valid_calc": False,
        }
        _apply_trust_gate(item)
        assert item["confidence_level"] == "needs_review_numeric"
        assert item["needs_review"] is True
        assert item["numeric_failure_category"] == "qty_wrong"

    def test_math_fail_review(self):
        item = {
            "raw_name": "GIZZARD SM",
            "quantity": 4, "unit_price": 34.95, "total": 1393.30,
            "qty_source": "column_read", "price_source": "column_read",
            "total_source": "column_read", "valid_calc": False,
        }
        _apply_trust_gate(item)
        assert item["confidence_level"] == "needs_review_numeric"

    def test_missing_name_review(self):
        item = {
            "raw_name": "",
            "quantity": 1, "unit_price": 10.0, "total": 10.0,
            "qty_source": "column_read", "price_source": "column_read",
            "total_source": "column_read", "valid_calc": True,
        }
        _apply_trust_gate(item)
        assert item["confidence_level"] == "needs_review_numeric"


# ---------------------------------------------------------------------------
# Tests: _trim_footer_rows
# ---------------------------------------------------------------------------

class TestTrimFooterRows:
    def test_trims_after_group_total(self):
        rows = [
            {"row_type": "line_item", "raw_text": "Product A"},
            {"row_type": "group_total", "raw_text": "GROUP TOTAL"},
            {"row_type": "line_item", "raw_text": "Footer text"},
        ]
        _trim_footer_rows(rows)
        assert rows[0]["row_type"] == "line_item"
        assert rows[2]["row_type"] == "unknown"

    def test_no_trim_without_summary(self):
        rows = [
            {"row_type": "line_item", "raw_text": "Product A"},
            {"row_type": "line_item", "raw_text": "Product B"},
        ]
        _trim_footer_rows(rows)
        assert rows[0]["row_type"] == "line_item"
        assert rows[1]["row_type"] == "line_item"


# ---------------------------------------------------------------------------
# Tests: _validate_subtotal
# ---------------------------------------------------------------------------

class TestValidateSubtotal:
    def test_matching_subtotal(self):
        items = [
            {"total": 100.0},
            {"total": 200.0},
        ]
        groups = [{"total_text": "300.00"}]
        result = _validate_subtotal(items, groups)
        assert result["subtotal_match"] is True

    def test_mismatching_subtotal(self):
        items = [
            {"total": 100.0},
            {"total": 200.0},
        ]
        groups = [{"total_text": "500.00"}]
        result = _validate_subtotal(items, groups)
        assert result["subtotal_match"] is False


# ---------------------------------------------------------------------------
# Tests: Full pipeline on real image (if available)
# ---------------------------------------------------------------------------

class TestSyscoPipelineE2E:
    def test_pipeline_on_real_image(self):
        """Test full pipeline with a real Sysco invoice if available."""
        import os
        from preprocessing import preprocess_image

        test_file = "/app/backend/uploads/00260b2f-7bc8-4d08-9e77-f58486e4cd71.jpg"
        if not os.path.exists(test_file):
            pytest.skip("Real Sysco invoice not available")

        with open(test_file, "rb") as f:
            raw = f.read()
        processed = preprocess_image(raw)
        b64 = base64.b64encode(processed).decode()

        result = run_sysco_pipeline(b64)

        assert len(result["items"]) > 0
        assert result["pipeline_meta"]["pipeline"] == "sysco_table_reconstruction"

        # Verify structure
        for item in result["items"]:
            assert "raw_name" in item
            assert "quantity" in item
            assert "unit_price" in item
            assert "total" in item
            assert "qty_source" in item
            assert "price_source" in item
            assert "total_source" in item
            assert "confidence_level" in item
            assert "valid_calc" in item
            assert item["extraction_source"] == "ocr_table_reconstruction"

        # At least some items should be trusted (we know this invoice works)
        trusted = sum(1 for it in result["items"] if it["confidence_level"] == "trusted")
        assert trusted >= 3, f"Expected at least 3 trusted items, got {trusted}"

    def test_empty_image(self):
        """Pipeline should handle empty/blank images gracefully."""
        img = Image.new("RGB", (800, 1100), (255, 255, 255))
        b64 = _img_to_b64(img)
        result = run_sysco_pipeline(b64)
        assert isinstance(result["items"], list)
        assert "pipeline_meta" in result
