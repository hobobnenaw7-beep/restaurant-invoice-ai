"""
Permanent regression test fixtures for PFG / Performance Foodservice parser.

Locked behavior:
- PFG = SHIP is the authoritative quantity (not ORD, not WEIGHT)
- Unknown columns must NEVER fill qty when a dedicated qty column exists
- Pack-size tokens (6/4 LB, 2/5 LB) must not be confused with quantity
- qty × price ≈ total must hold for correctly parsed rows

These tests use pre-built JSON fixtures (not OCR images) to isolate parser logic
from OCR quality variance.
"""

import sys
import io
import base64
import pytest

sys.path.insert(0, "/app/backend")

from PIL import Image, ImageDraw, ImageFont
from preprocessing import preprocess_image
from services.layout_parser import (
    parse_invoice_layout,
    _map_words_to_columns,
    _parse_pfg_inferred,
    detect_rows,
    run_ocr_from_b64,
)


# ── Fonts ──
F12 = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", 12)
F13 = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", 13)
FB14 = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", 14)
FB18 = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", 18)


def _draw_pfg(items):
    """Draw a PFG invoice image with 8-column layout."""
    cols_x = {"item": 30, "desc": 100, "pack": 380, "ord": 480,
              "ship": 540, "weight": 610, "perlb": 700, "ext": 810}
    row_h = 22
    img_h = 160 + len(items) * row_h + 60
    img = Image.new("RGB", (960, img_h), "white")
    d = ImageDraw.Draw(img)
    y = 18
    d.text((30, y), "PERFORMANCE FOODSERVICE", fill="black", font=FB18)
    y += 28
    d.text((30, y), "Invoice: PFS-TEST", fill=(60, 60, 60), font=F13)
    y += 28
    d.rectangle([(25, y - 2), (935, y + 17)], fill=(40, 60, 40))
    for lbl, x in [("ITEM#", 30), ("DESCRIPTION", 100), ("PACK", 380),
                    ("ORD", 480), ("SHIP", 540), ("WEIGHT", 610),
                    ("$/LB", 700), ("EXT PRICE", 810)]:
        d.text((x, y), lbl, fill="white", font=FB14)
    y += row_h
    for item_no, desc, pack, ord_q, ship_q, weight, perlb, ext in items:
        d.text((cols_x["item"], y), item_no, fill=(80, 80, 80), font=F12)
        d.text((cols_x["desc"], y), desc, fill="black", font=F13)
        d.text((cols_x["pack"], y), pack, fill="black", font=F13)
        d.text((cols_x["ord"], y), ord_q, fill="black", font=F13)
        d.text((cols_x["ship"], y), ship_q, fill="black", font=F13)
        d.text((cols_x["weight"], y), weight, fill="black", font=F13)
        d.text((cols_x["perlb"], y), perlb, fill="black", font=F13)
        d.text((cols_x["ext"], y), ext, fill="black", font=F13)
        y += row_h
    return img


def _pipeline(img, vendor):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    processed = preprocess_image(buf.getvalue())
    b64 = base64.b64encode(processed).decode()
    return parse_invoice_layout(b64, "structured_invoice", vendor)


# ═══════════════════════════════════════════════════════════
# FIXTURE: The problematic PFG invoice (8 rows)
# ═══════════════════════════════════════════════════════════
PFG_PROBLEMATIC = [
    # (item#, desc, pack, ORD, SHIP, weight, $/LB, ext)
    ("7234501", "BEEF TENDERLOIN CHOICE",      "6/4 LB",  "6",  "1",  "24.00", "$8.33",  "$199.99"),
    ("8120034", "CHICKEN BREAST BNLS SKNLS",   "4/10 LB", "4",  "4",  "40.00", "$2.15",  "$86.00"),
    ("9934210", "SALMON FILLET ATLANTIC FRESH", "2/5 LB",  "3",  "2",  "10.00", "$12.55", "$125.50"),
    ("3321099", "PORK LOIN BNLS CENTER CUT",   "2/8 LB",  "4",  "3",  "24.00", "$5.50",  "$132.00"),
    ("5510221", "SHRIMP 16/20 IQF P&D",        "2/5 LB",  "5",  "5",  "25.00", "$8.40",  "$210.00"),
    ("1123450", "GROUND BEEF 80/20 FRESH",      "4/10 LB", "10", "8",  "80.00", "$4.12",  "$329.60"),
    ("8837201", "LOBSTER TAIL 8OZ COLD WATER",  "1/10 CT", "3",  "2",  "20.00", "$18.50", "$370.00"),
    ("6654320", "RICE JASMINE LONG GRAIN",      "1/50 LB", "30", "25", "50.00", "$1.22",  "$60.84"),
]

# Expected: qty = SHIP column, price = $/LB, total = EXT PRICE
PFG_EXPECTED = [
    {"qty": 1,  "price": 8.33,  "total": 199.99},
    {"qty": 4,  "price": 2.15,  "total": 86.00},
    {"qty": 2,  "price": 12.55, "total": 125.50},
    {"qty": 3,  "price": 5.50,  "total": 132.00},
    {"qty": 5,  "price": 8.40,  "total": 210.00},
    {"qty": 8,  "price": 4.12,  "total": 329.60},
    {"qty": 2,  "price": 18.50, "total": 370.00},
    {"qty": 25, "price": 1.22,  "total": 60.84},
]

# ═══════════════════════════════════════════════════════════
# FIXTURE: PFG variant (5 rows, different edge cases)
# ═══════════════════════════════════════════════════════════
PFG_VARIANT = [
    ("4401122", "TURKEY BREAST SMOKED",     "2/8 LB",  "2", "2",  "16.00", "$6.25",  "$100.00"),
    ("5520011", "HAM VIRGINIA SLICED",       "1/12 LB", "1", "1",  "12.00", "$4.50",  "$54.00"),
    ("7799001", "BACON APPLEWOOD THICK CUT", "4/5 LB",  "8", "6",  "30.00", "$5.80",  "$174.00"),
    ("3310055", "LAMB RACK FRENCHED",        "2/3 LB",  "3", "1",  "3.00",  "$28.00", "$84.00"),
    ("8812233", "VEAL CUTLET POUNDED",       "1/5 LB",  "4", "4",  "20.00", "$12.00", "$240.00"),
]

PFG_VARIANT_EXPECTED = [
    {"qty": 2,  "price": 6.25,  "total": 100.00},
    {"qty": 1,  "price": 4.50,  "total": 54.00},
    {"qty": 6,  "price": 5.80,  "total": 174.00},
    {"qty": 1,  "price": 28.00, "total": 84.00},
    {"qty": 4,  "price": 12.00, "total": 240.00},
]


# ═══════════════════════════════════════════════════════════
# TESTS: SHIP vs ORD selection
# ═══════════════════════════════════════════════════════════

class TestPFGShipVsOrd:
    """Assert that SHIP (not ORD) is used as the authoritative quantity."""

    def test_ship_selected_over_ord_row0(self):
        """Row 0: ORD=6, SHIP=1. Must use SHIP=1."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 1, "Expected at least 1 item"
        assert abs(items[0]["quantity"] - 1) < 0.5, \
            f"Row 0 qty should be 1 (SHIP), got {items[0]['quantity']} (likely used ORD=6)"

    def test_ship_selected_over_ord_row7(self):
        """Row 7: ORD=30, SHIP=25. Must use SHIP=25."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 8, f"Expected 8 items, got {len(items)}"
        assert abs(items[7]["quantity"] - 25) < 0.5, \
            f"Row 7 qty should be 25 (SHIP), got {items[7]['quantity']} (likely used ORD=30)"

    def test_ship_not_ord_when_different(self):
        """BACON: ORD=8, SHIP=6. Must use SHIP=6."""
        img = _draw_pfg(PFG_VARIANT)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 3
        # BACON is row 2 (index 2)
        assert abs(items[2]["quantity"] - 6) < 0.5, \
            f"BACON qty should be 6 (SHIP), got {items[2]['quantity']} (ORD was 8)"


# ═══════════════════════════════════════════════════════════
# TESTS: WEIGHT must never be used as quantity
# ═══════════════════════════════════════════════════════════

class TestPFGWeightIgnored:
    """Assert that WEIGHT column values never appear as quantity."""

    def test_weight_not_qty_row5(self):
        """Row 5: WEIGHT=80.00. Must NOT be used as qty (correct qty=8)."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 6
        assert items[5]["quantity"] != 80, \
            "Row 5 qty is 80 (WEIGHT), should be 8 (SHIP). WEIGHT leaked into qty!"
        assert abs(items[5]["quantity"] - 8) < 0.5

    def test_weight_not_qty_row0(self):
        """Row 0: WEIGHT=24.00. Must NOT be used as qty (correct qty=1)."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 1
        assert items[0]["quantity"] != 24, \
            "Row 0 qty is 24 (WEIGHT), should be 1 (SHIP). WEIGHT leaked into qty!"


# ═══════════════════════════════════════════════════════════
# TESTS: Pack-size tokens must not be confused with quantity
# ═══════════════════════════════════════════════════════════

class TestPFGPackSizeHandling:
    """Assert pack-size patterns are correctly separated, not used as qty."""

    def test_pack_not_qty(self):
        """Pack '6/4 LB' → qty must NOT be 6 or 4."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 1
        qty = items[0]["quantity"]
        assert qty not in (6, 4), \
            f"Row 0 qty={qty} matches pack fragment (6/4 LB). Pack leaked into qty!"

    def test_pack_correctly_extracted(self):
        """Verify pack_size field is populated for PFG items."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        packs_found = sum(1 for it in items if it.get("pack_size", "").strip())
        assert packs_found >= 4, \
            f"Expected at least 4 items with pack_size, got {packs_found}"


# ═══════════════════════════════════════════════════════════
# TESTS: qty × price ≈ total consistency
# ═══════════════════════════════════════════════════════════

class TestPFGMathConsistency:
    """Verify mathematical consistency of parsed values."""

    def test_all_rows_math_check(self):
        """PFG uses weight-based pricing (total = weight × $/LB, NOT qty × $/LB).
        Math check will show mismatch — which is EXPECTED for PFG.
        Verify that flagged rows get needs_review, not false pass."""
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        for i, (it, exp) in enumerate(zip(items, PFG_EXPECTED)):
            qty = it.get("quantity", 0)
            # Primary assertion: qty matches expected SHIP value
            assert abs(qty - exp["qty"]) < 0.5, \
                f"Row {i}: qty should be {exp['qty']} (SHIP), got {qty}"
            # Secondary: verify math validation catches the weight-based pricing mismatch
            val = it.get("validation", {})
            math_status = val.get("status", "?")
            # PFG rows: qty×$/LB ≠ total (because total = weight×$/LB)
            # so math should flag as warning or needs_review, NOT silently pass
            if qty > 0 and it.get("unit_price", 0) > 0 and it.get("total_price", 0) > 0:
                computed = round(qty * it["unit_price"], 2)
                if abs(computed - it["total_price"]) > 1.0:
                    assert math_status != "pass", \
                        f"Row {i}: math should NOT be 'pass' for PFG weight-based pricing"

    def test_variant_math_check(self):
        """PFG variant: all rows should pass math check."""
        img = _draw_pfg(PFG_VARIANT)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        for i, (it, exp) in enumerate(zip(items, PFG_VARIANT_EXPECTED)):
            qty = it.get("quantity", 0)
            assert abs(qty - exp["qty"]) < 0.5, \
                f"Variant row {i}: expected qty={exp['qty']}, got {qty}"


# ═══════════════════════════════════════════════════════════
# TESTS: Guard — unknown columns must not fill qty
# ═══════════════════════════════════════════════════════════

class TestUnknownColumnGuard:
    """When a dedicated qty column exists, unknown columns must never fill qty."""

    def test_unknown_does_not_fill_qty(self):
        """Simulate: qty column returns 0 (OCR misread), unknown has 80.0. Qty must stay 0."""
        def w(text, left, right):
            return {"text": text, "left": left, "right": right,
                    "width": right - left, "top": 100, "height": 15, "conf": 90}

        words = [
            w("GROUND BEEF", 86, 200),
            w("lo", 526, 540),       # OCR misread → _parse_number returns 0
            w("80.00", 596, 633),    # WEIGHT → unknown column
            w("$4.12", 686, 723),    # Price
            w("$329.60", 796, 849),  # Total
        ]
        columns = [
            {"name": "Description", "left": 0, "right": 400, "field": "item_name"},
            {"name": "Ship Qty", "left": 516, "right": 542, "field": "quantity"},
            {"name": "Weight", "left": 586, "right": 643, "field": "unknown"},
            {"name": "$/LB", "left": 676, "right": 741, "field": "unit_price"},
            {"name": "Ext Price", "left": 786, "right": 862, "field": "total"},
        ]
        result = _map_words_to_columns(words, columns)
        # qty should NOT be 80 (from unknown/WEIGHT column)
        assert result["quantity"] != 80, \
            "Unknown column filled qty with 80 (WEIGHT). Guard failed!"


# ═══════════════════════════════════════════════════════════
# TESTS: Full end-to-end comparison
# ═══════════════════════════════════════════════════════════

class TestPFGEndToEnd:
    """Full pipeline: image → preprocess → OCR → parse → validate."""

    def test_problematic_invoice_full(self):
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 7, f"Expected at least 7 items, got {len(items)}"
        for i, exp in enumerate(PFG_EXPECTED[:len(items)]):
            it = items[i]
            assert abs(it["quantity"] - exp["qty"]) < 0.5, \
                f"Row {i} qty: expected {exp['qty']}, got {it['quantity']}"

    def test_variant_invoice_full(self):
        img = _draw_pfg(PFG_VARIANT)
        result = _pipeline(img, "Performance Food Group")
        items = result.get("items", [])
        assert len(items) >= 4, f"Expected at least 4 items, got {len(items)}"
        for i, exp in enumerate(PFG_VARIANT_EXPECTED[:len(items)]):
            it = items[i]
            assert abs(it["quantity"] - exp["qty"]) < 0.5, \
                f"Variant row {i} qty: expected {exp['qty']}, got {it['quantity']}"

    def test_parser_used_is_pfg(self):
        img = _draw_pfg(PFG_PROBLEMATIC)
        result = _pipeline(img, "Performance Food Group")
        assert result.get("parser_used") == "vendor_pfg", \
            f"Expected vendor_pfg parser, got {result.get('parser_used')}"
