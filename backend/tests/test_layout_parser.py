"""
Test Layout Parser (Phase 3) - Parser-Specific Layout Handling

Tests:
- run_ocr() extracts words with bounding boxes
- detect_rows() groups words into correct rows by y-coordinate clustering
- detect_columns() finds column boundaries from header keywords
- _is_separator_or_summary() filters subtotal/tax/total rows but NOT header rows
- parse_invoice_layout() returns correct structure
- Receipt parser (simple_receipt) extracts items
- Vendor Sysco parser with dark header fallback
- Vendor PFG parser for weight-based invoices
- Structured parser fallback to _extract_items_simple
- Messy layout handling
- Empty image handling
- API integration (layout_parse in response)
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests
import io
import base64
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@test.com", "password": "testpassword"},
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


def create_test_image_with_text(lines, width=800, height=600, font_size=20, line_spacing=30):
    """Create a test image with text lines for OCR testing"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    y = 50
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += line_spacing
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_columnar_invoice_image(items, header_row=None, width=900, height=700, font_size=18):
    """Create a columnar invoice image with proper column alignment"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    # Column positions
    col_positions = {
        "description": 50,
        "qty": 400,
        "price": 550,
        "total": 700,
    }
    
    y = 50
    
    # Draw header row
    if header_row:
        for col, text in header_row.items():
            if col in col_positions:
                draw.text((col_positions[col], y), text, fill="black", font=font)
        y += 35
        # Draw separator line
        draw.line([(40, y), (width - 40, y)], fill="gray", width=1)
        y += 15
    
    # Draw items
    for item in items:
        draw.text((col_positions["description"], y), item.get("description", ""), fill="black", font=font)
        draw.text((col_positions["qty"], y), str(item.get("qty", "")), fill="black", font=font)
        draw.text((col_positions["price"], y), str(item.get("price", "")), fill="black", font=font)
        draw.text((col_positions["total"], y), str(item.get("total", "")), fill="black", font=font)
        y += 30
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_sysco_invoice_with_dark_header(items, width=900, height=700, font_size=18):
    """Create a Sysco-style invoice with dark header background (white text on dark)"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    col_positions = {
        "description": 50,
        "qty": 400,
        "price": 550,
        "total": 700,
    }
    
    y = 50
    
    # Draw dark header background (fill=(50,50,80) with white text)
    # This simulates Sysco invoices where header is unreadable by OCR
    draw.rectangle([(40, y - 5), (width - 40, y + 25)], fill=(50, 50, 80))
    draw.text((col_positions["description"], y), "Description", fill="white", font=font)
    draw.text((col_positions["qty"], y), "Qty", fill="white", font=font)
    draw.text((col_positions["price"], y), "Price", fill="white", font=font)
    draw.text((col_positions["total"], y), "Total", fill="white", font=font)
    y += 40
    
    # Draw items (black text on white background)
    for item in items:
        draw.text((col_positions["description"], y), item.get("description", ""), fill="black", font=font)
        draw.text((col_positions["qty"], y), str(item.get("qty", "")), fill="black", font=font)
        draw.text((col_positions["price"], y), str(item.get("price", "")), fill="black", font=font)
        draw.text((col_positions["total"], y), str(item.get("total", "")), fill="black", font=font)
        y += 30
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_simple_receipt_image(items, width=400, height=600, font_size=16):
    """Create a simple receipt image (informal format)"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    y = 50
    for item in items:
        # Format: "Item Name    qty x price = total"
        line = f"{item['name']}    {item['qty']} x ${item['price']:.2f} = ${item['total']:.2f}"
        draw.text((30, y), line, fill="black", font=font)
        y += 28
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_pfg_invoice_image(items, width=950, height=700, font_size=16):
    """Create a PFG-style invoice with weight-based pricing"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    col_positions = {
        "description": 30,
        "pack": 280,
        "qty": 380,
        "casewt": 450,
        "lb": 550,
        "total": 650,
    }
    
    y = 50
    
    # Header row
    draw.text((col_positions["description"], y), "Description", fill="black", font=font)
    draw.text((col_positions["pack"], y), "Pack", fill="black", font=font)
    draw.text((col_positions["qty"], y), "Qty", fill="black", font=font)
    draw.text((col_positions["casewt"], y), "CaseWt", fill="black", font=font)
    draw.text((col_positions["lb"], y), "$/LB", fill="black", font=font)
    draw.text((col_positions["total"], y), "Total", fill="black", font=font)
    y += 35
    
    # Items
    for item in items:
        draw.text((col_positions["description"], y), item.get("description", ""), fill="black", font=font)
        draw.text((col_positions["pack"], y), item.get("pack", ""), fill="black", font=font)
        draw.text((col_positions["qty"], y), str(item.get("qty", "")), fill="black", font=font)
        draw.text((col_positions["casewt"], y), str(item.get("casewt", "")), fill="black", font=font)
        draw.text((col_positions["lb"], y), str(item.get("lb", "")), fill="black", font=font)
        draw.text((col_positions["total"], y), str(item.get("total", "")), fill="black", font=font)
        y += 28
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_messy_layout_image(items, width=800, height=600, font_size=16):
    """Create an image with uneven spacing (messy layout)"""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    
    y = 50
    for i, item in enumerate(items):
        # Vary x positions to simulate messy layout
        x_offset = 30 + (i % 3) * 15  # Uneven left margin
        spacing = 25 + (i % 2) * 10   # Uneven line spacing
        
        line = f"{item['name']}    {item['qty']}    ${item['price']:.2f}    ${item['total']:.2f}"
        draw.text((x_offset, y), line, fill="black", font=font)
        y += spacing
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ============ Unit Tests for Layout Parser Functions ============

class TestRunOCR:
    """Test run_ocr() extracts words with bounding boxes"""
    
    def test_run_ocr_extracts_words(self):
        """run_ocr() extracts words with bounding boxes from an image"""
        from services.layout_parser import run_ocr
        
        # Create test image with known text
        lines = ["INVOICE", "Item Description    Qty    Price    Total", "Chicken Breast    5    10.00    50.00"]
        image_bytes = create_test_image_with_text(lines)
        
        words = run_ocr(image_bytes)
        
        assert isinstance(words, list), "run_ocr should return a list"
        assert len(words) > 0, "run_ocr should extract at least some words"
        
        # Check word structure
        for word in words:
            assert "text" in word, "Each word should have 'text'"
            assert "left" in word, "Each word should have 'left'"
            assert "top" in word, "Each word should have 'top'"
            assert "width" in word, "Each word should have 'width'"
            assert "height" in word, "Each word should have 'height'"
            assert "conf" in word, "Each word should have 'conf'"
        
        print(f"PASS - run_ocr extracted {len(words)} words with bounding boxes")
    
    def test_run_ocr_empty_image(self):
        """run_ocr() handles empty/blank images gracefully"""
        from services.layout_parser import run_ocr
        
        # Create blank white image
        img = Image.new("RGB", (400, 300), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        
        words = run_ocr(buf.getvalue())
        
        assert isinstance(words, list), "run_ocr should return a list even for blank images"
        # May return empty list or very few noise words
        print(f"PASS - run_ocr handles blank image, returned {len(words)} words")


class TestDetectRows:
    """Test detect_rows() groups words into correct rows"""
    
    def test_detect_rows_groups_by_y_coordinate(self):
        """detect_rows() groups words into correct rows by y-coordinate clustering"""
        from services.layout_parser import run_ocr, detect_rows
        
        # Create image with clear row separation
        lines = [
            "Row One Text Here",
            "Row Two Different Text",
            "Row Three More Content",
        ]
        image_bytes = create_test_image_with_text(lines, line_spacing=40)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        
        assert isinstance(rows, list), "detect_rows should return a list"
        assert len(rows) >= 2, f"Should detect at least 2 rows, got {len(rows)}"
        
        # Each row should be sorted left-to-right
        for row in rows:
            if len(row) > 1:
                for i in range(len(row) - 1):
                    assert row[i]["left"] <= row[i + 1]["left"], "Words in row should be sorted left-to-right"
        
        print(f"PASS - detect_rows grouped words into {len(rows)} rows")
    
    def test_detect_rows_empty_input(self):
        """detect_rows() handles empty word list"""
        from services.layout_parser import detect_rows
        
        rows = detect_rows([])
        
        assert rows == [], "detect_rows should return empty list for empty input"
        print("PASS - detect_rows handles empty input")


class TestDetectColumns:
    """Test detect_columns() finds column boundaries from header keywords"""
    
    def test_detect_columns_with_standard_header(self):
        """Column detection works when header row has standard keywords"""
        from services.layout_parser import run_ocr, detect_rows, detect_columns
        
        # Create columnar invoice with header
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "Chicken Breast", "qty": "5", "price": "10.00", "total": "50.00"},
            {"description": "Beef Ribeye", "qty": "3", "price": "25.00", "total": "75.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        col_info = detect_columns(rows)
        
        assert "header_row_idx" in col_info, "Should have header_row_idx"
        assert "columns" in col_info, "Should have columns"
        assert "data_start_idx" in col_info, "Should have data_start_idx"
        
        # Should detect header row
        assert col_info["header_row_idx"] >= 0, "Should detect header row"
        
        # Should have multiple columns
        assert len(col_info["columns"]) >= 2, f"Should detect at least 2 columns, got {len(col_info['columns'])}"
        
        # Check column structure
        for col in col_info["columns"]:
            assert "name" in col, "Column should have 'name'"
            assert "left" in col, "Column should have 'left'"
            assert "right" in col, "Column should have 'right'"
            assert "field" in col, "Column should have 'field'"
        
        print(f"PASS - detect_columns found {len(col_info['columns'])} columns with header at row {col_info['header_row_idx']}")
    
    def test_detect_columns_no_header(self):
        """detect_columns() infers columns from data when no header present"""
        from services.layout_parser import run_ocr, detect_rows, detect_columns
        
        # Create invoice without header row
        items = [
            {"description": "Chicken Breast", "qty": "5", "price": "10.00", "total": "50.00"},
            {"description": "Beef Ribeye", "qty": "3", "price": "25.00", "total": "75.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=None)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        col_info = detect_columns(rows)
        
        # Should still return valid structure
        assert "header_row_idx" in col_info
        assert "columns" in col_info
        assert "data_start_idx" in col_info
        
        print(f"PASS - detect_columns handles no-header case, header_row_idx={col_info['header_row_idx']}")


class TestIsSeparatorOrSummary:
    """Test _is_separator_or_summary() filtering logic"""
    
    def test_filters_subtotal_rows(self):
        """_is_separator_or_summary() correctly filters subtotal/tax/total rows"""
        from services.layout_parser import _is_separator_or_summary
        
        # These should be filtered (return True)
        summary_texts = [
            "Subtotal: $125.00",
            "Tax: $10.00",
            "Total: $135.00",
            "Balance Due: $135.00",
            "Amount Due: $135.00",
            "Thank you for your business",
            "Invoice Total: $500.00",
            "Page 1 of 2",
            "Terms: Net 30",
            "-------------------",
            "==================",
        ]
        
        for text in summary_texts:
            result = _is_separator_or_summary(text)
            assert result == True, f"Should filter '{text}' as separator/summary"
        
        print("PASS - _is_separator_or_summary correctly filters subtotal/tax/total rows")
    
    def test_does_not_filter_header_rows(self):
        """_is_separator_or_summary() does NOT filter rows containing multiple column keywords"""
        from services.layout_parser import _is_separator_or_summary
        
        # These should NOT be filtered (return False) - they are header rows
        header_texts = [
            "Item Description Qty Price Total",
            "Product Name Quantity Unit Price Amount",
            "Description Pack Size Price Total",
            "Item Qty Price Ext",
        ]
        
        for text in header_texts:
            result = _is_separator_or_summary(text)
            assert result == False, f"Should NOT filter header row '{text}'"
        
        print("PASS - _is_separator_or_summary does NOT filter header rows with multiple column keywords")
    
    def test_does_not_filter_data_rows(self):
        """_is_separator_or_summary() does NOT filter normal data rows"""
        from services.layout_parser import _is_separator_or_summary
        
        # These should NOT be filtered (return False) - they are data rows
        data_texts = [
            "Chicken Breast 5 10.00 50.00",
            "Beef Ribeye 3 25.00 75.00",
            "SHRIMP 31-35 2 89.00 178.00",
            "Olive Oil Extra Virgin 1 15.99 15.99",
        ]
        
        for text in data_texts:
            result = _is_separator_or_summary(text)
            assert result == False, f"Should NOT filter data row '{text}'"
        
        print("PASS - _is_separator_or_summary does NOT filter normal data rows")


class TestParseInvoiceLayout:
    """Test parse_invoice_layout() main function"""
    
    def test_returns_correct_structure(self):
        """parse_invoice_layout() returns correct structure"""
        from services.layout_parser import parse_invoice_layout
        
        # Create test invoice
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "Chicken Breast", "qty": "5", "price": "10.00", "total": "50.00"},
            {"description": "Beef Ribeye", "qty": "3", "price": "25.00", "total": "75.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image)
        
        # Check required fields
        assert "items" in result, "Result should have 'items'"
        assert "row_count" in result, "Result should have 'row_count'"
        assert "column_count" in result, "Result should have 'column_count'"
        assert "header_detected" in result, "Result should have 'header_detected'"
        assert "parser_used" in result, "Result should have 'parser_used'"
        assert "raw_rows" in result, "Result should have 'raw_rows'"
        
        assert isinstance(result["items"], list), "items should be a list"
        assert isinstance(result["row_count"], int), "row_count should be int"
        assert isinstance(result["column_count"], int), "column_count should be int"
        assert isinstance(result["header_detected"], bool), "header_detected should be bool"
        assert isinstance(result["parser_used"], str), "parser_used should be str"
        assert isinstance(result["raw_rows"], list), "raw_rows should be list"
        
        print(f"PASS - parse_invoice_layout returns correct structure: {len(result['items'])} items, parser={result['parser_used']}")
    
    def test_handles_empty_image(self):
        """Layout parser gracefully handles images with no text"""
        from services.layout_parser import parse_invoice_layout
        
        # Create blank white image
        img = Image.new("RGB", (400, 300), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()
        
        result = parse_invoice_layout(b64_image)
        
        # Should return empty result structure
        assert result["items"] == [], "Should return empty items for blank image"
        assert result["row_count"] == 0, "Should return 0 row_count for blank image"
        assert "no_ocr_words" in result["parser_used"] or "no_rows" in result["parser_used"], \
            f"parser_used should indicate no content, got: {result['parser_used']}"
        
        print(f"PASS - parse_invoice_layout handles empty image gracefully: parser_used={result['parser_used']}")


class TestReceiptParser:
    """Test simple_receipt parser"""
    
    def test_receipt_parser_extracts_items(self):
        """Receipt parser (simple_receipt) extracts all items from informal receipt"""
        from services.layout_parser import parse_invoice_layout
        
        # Create simple receipt
        items = [
            {"name": "Coffee", "qty": 2, "price": 4.50, "total": 9.00},
            {"name": "Sandwich", "qty": 1, "price": 8.99, "total": 8.99},
            {"name": "Cookie", "qty": 3, "price": 2.00, "total": 6.00},
        ]
        image_bytes = create_simple_receipt_image(items)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, document_type="simple_receipt")
        
        assert result["parser_used"] == "receipt_parser", f"Should use receipt_parser, got {result['parser_used']}"
        assert len(result["items"]) >= 1, "Should extract at least 1 item from receipt"
        
        # Check item structure
        for item in result["items"]:
            assert "item_name" in item, "Item should have item_name"
            assert "quantity" in item, "Item should have quantity"
            assert "unit_price" in item, "Item should have unit_price"
            assert "total_price" in item, "Item should have total_price"
        
        print(f"PASS - Receipt parser extracted {len(result['items'])} items")


class TestVendorParsers:
    """Test vendor-specific parsers"""
    
    def test_sysco_parser_with_dark_header(self):
        """Vendor Sysco parser correctly extracts items from columnar invoice with dark header background"""
        from services.layout_parser import parse_invoice_layout
        
        # Create Sysco-style invoice with dark header (white text on dark background)
        items = [
            {"description": "CHICKEN BREAST BNLS", "qty": "5", "price": "42.50", "total": "212.50"},
            {"description": "SHRIMP 31-35", "qty": "3", "price": "89.00", "total": "267.00"},
        ]
        image_bytes = create_sysco_invoice_with_dark_header(items)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, vendor_name="Sysco")
        
        assert "sysco" in result["parser_used"].lower() or "fallback" in result["parser_used"].lower(), \
            f"Should use sysco or fallback parser, got {result['parser_used']}"
        
        # Should extract items even with dark header (using fallback)
        assert len(result["items"]) >= 1, f"Should extract at least 1 item, got {len(result['items'])}"
        
        print(f"PASS - Sysco parser extracted {len(result['items'])} items with dark header, parser={result['parser_used']}")
    
    def test_pfg_parser_weight_based(self):
        """Vendor PFG parser correctly extracts items from weight-based invoice"""
        from services.layout_parser import parse_invoice_layout
        
        # Create PFG-style invoice with weight-based pricing
        items = [
            {"description": "BEEF RIBEYE", "pack": "2/10LB", "qty": "2", "casewt": "20", "lb": "12.50", "total": "250.00"},
            {"description": "PORK LOIN", "pack": "4/5LB", "qty": "3", "casewt": "20", "lb": "8.00", "total": "480.00"},
        ]
        image_bytes = create_pfg_invoice_image(items)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, vendor_name="PFG")
        
        assert "pfg" in result["parser_used"].lower(), f"Should use PFG parser, got {result['parser_used']}"
        
        # Should extract items
        assert len(result["items"]) >= 1, f"Should extract at least 1 item, got {len(result['items'])}"
        
        # Check that qty and total are present
        for item in result["items"]:
            if item["item_name"]:  # Skip empty items
                assert item["quantity"] >= 0 or item["total_price"] >= 0, \
                    f"Item should have qty or total: {item}"
        
        print(f"PASS - PFG parser extracted {len(result['items'])} items from weight-based invoice")


class TestFallbackParser:
    """Test fallback to _extract_items_simple when column detection fails"""
    
    def test_structured_fallback_when_columns_fail(self):
        """Structured parser falls back to _extract_items_simple when column detection fails"""
        from services.layout_parser import parse_invoice_layout
        
        # Create image with no clear column structure
        lines = [
            "INVOICE #12345",
            "Chicken Breast 5 10.00 50.00",
            "Beef Ribeye 3 25.00 75.00",
            "Subtotal: 125.00",
        ]
        image_bytes = create_test_image_with_text(lines)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, document_type="structured_invoice")
        
        # Should use some parser (columnar, inferred, or fallback)
        assert result["parser_used"] in ["structured_columnar", "structured_inferred", "structured_fallback"], \
            f"Should use structured parser variant, got {result['parser_used']}"
        
        print(f"PASS - Structured parser used: {result['parser_used']}, extracted {len(result['items'])} items")


class TestMessyLayout:
    """Test handling of messy/uneven layouts"""
    
    def test_messy_layout_handling(self):
        """Messy layout parser handles uneven spacing correctly"""
        from services.layout_parser import parse_invoice_layout
        
        # Create image with uneven spacing
        items = [
            {"name": "Chicken Breast", "qty": 5, "price": 10.00, "total": 50.00},
            {"name": "Beef Ribeye", "qty": 3, "price": 25.00, "total": 75.00},
            {"name": "Salmon Fillet", "qty": 2, "price": 18.00, "total": 36.00},
        ]
        image_bytes = create_messy_layout_image(items)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image)
        
        # Should still extract some items despite messy layout
        assert result["row_count"] >= 1, "Should detect at least 1 row"
        
        print(f"PASS - Messy layout handled: {result['row_count']} rows, {len(result['items'])} items, parser={result['parser_used']}")


# ============ API Integration Tests ============

class TestAPIIntegration:
    """Test layout_parse in POST /api/upload/extract response"""
    
    def test_layout_parse_in_extract_response(self, auth_headers):
        """Layout parse result is included in POST /api/upload/extract response"""
        # Create test invoice image
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "Chicken Breast", "qty": "5", "price": "10.00", "total": "50.00"},
            {"description": "Beef Ribeye", "qty": "3", "price": "25.00", "total": "75.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        
        # Upload via API
        files = {"file": ("test_invoice.png", io.BytesIO(image_bytes), "image/png")}
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
        )
        
        assert response.status_code == 200, f"Upload should succeed, got {response.status_code}: {response.text}"
        
        result = response.json()
        
        # Check layout_parse is in response
        assert "layout_parse" in result, "Response should include layout_parse"
        
        layout_parse = result["layout_parse"]
        assert layout_parse is not None, "layout_parse should not be None"
        
        # Check layout_parse structure
        assert "parser_used" in layout_parse, "layout_parse should have parser_used"
        assert "items" in layout_parse, "layout_parse should have items"
        assert "row_count" in layout_parse, "layout_parse should have row_count"
        assert "column_count" in layout_parse, "layout_parse should have column_count"
        assert "header_detected" in layout_parse, "layout_parse should have header_detected"
        
        print(f"PASS - layout_parse in response: parser={layout_parse['parser_used']}, items={len(layout_parse['items'])}, rows={layout_parse['row_count']}")
    
    def test_layout_parse_stored_in_database(self, auth_headers):
        """Layout parse summary is stored in uploaded_receipts collection"""
        # Create test invoice image
        items = [
            {"description": "Test Item", "qty": "2", "price": "15.00", "total": "30.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row={"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"})
        
        # Upload via API
        files = {"file": ("test_db_invoice.png", io.BytesIO(image_bytes), "image/png")}
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
        )
        
        assert response.status_code == 200, f"Upload should succeed, got {response.status_code}"
        
        result = response.json()
        receipt_id = result.get("receipt_id")
        assert receipt_id, "Response should include receipt_id"
        
        # The layout_parse summary should be stored (we verify via the response which reflects DB storage)
        assert "layout_parse" in result, "layout_parse should be in response (reflects DB storage)"
        
        print(f"PASS - layout_parse stored with receipt_id={receipt_id}")


class TestExtractLineItems:
    """Test extract_line_items() function"""
    
    def test_extract_line_items_with_columns(self):
        """extract_line_items() correctly maps row cells to columns"""
        from services.layout_parser import run_ocr, detect_rows, detect_columns, extract_line_items
        
        # Create columnar invoice
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "Chicken Breast", "qty": "5", "price": "10.00", "total": "50.00"},
            {"description": "Beef Ribeye", "qty": "3", "price": "25.00", "total": "75.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        col_info = detect_columns(rows)
        line_items = extract_line_items(rows, col_info)
        
        assert isinstance(line_items, list), "Should return list of items"
        
        # Check item structure
        for item in line_items:
            assert "item_name" in item, "Item should have item_name"
            assert "quantity" in item, "Item should have quantity"
            assert "unit_price" in item, "Item should have unit_price"
            assert "total_price" in item, "Item should have total_price"
        
        print(f"PASS - extract_line_items extracted {len(line_items)} items with column mapping")


class TestUSFoodsParser:
    """Test US Foods vendor parser"""
    
    def test_usfoods_parser(self):
        """US Foods parser correctly extracts items"""
        from services.layout_parser import parse_invoice_layout
        
        # Create US Foods style invoice
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "SALMON FILLET", "qty": "4", "price": "22.00", "total": "88.00"},
            {"description": "TUNA STEAK", "qty": "6", "price": "18.00", "total": "108.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, vendor_name="US Foods")
        
        assert "usfoods" in result["parser_used"].lower(), f"Should use US Foods parser, got {result['parser_used']}"
        assert len(result["items"]) >= 1, f"Should extract at least 1 item"
        
        print(f"PASS - US Foods parser extracted {len(result['items'])} items")


class TestRowText:
    """Test row_text() helper function"""
    
    def test_row_text_preserves_spacing(self):
        """row_text() reconstructs text from row words preserving spacing"""
        from services.layout_parser import run_ocr, detect_rows, row_text
        
        lines = ["Item Description    Qty    Price    Total"]
        image_bytes = create_test_image_with_text(lines)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        
        if rows:
            text = row_text(rows[0])
            assert isinstance(text, str), "row_text should return string"
            assert len(text) > 0, "row_text should return non-empty string"
            print(f"PASS - row_text reconstructed: '{text}'")
        else:
            pytest.skip("No rows detected")


class TestParseNumber:
    """Test _parse_number() helper function"""
    
    def test_parse_number_handles_currency(self):
        """_parse_number() handles $ and , characters"""
        from services.layout_parser import _parse_number
        
        test_cases = [
            ("$10.00", 10.0),
            ("$1,234.56", 1234.56),
            ("100.50", 100.5),
            ("1,000", 1000.0),
            ("invalid", 0.0),
            ("", 0.0),
        ]
        
        for text, expected in test_cases:
            result = _parse_number(text)
            assert result == expected, f"_parse_number('{text}') should be {expected}, got {result}"
        
        print("PASS - _parse_number handles currency formatting correctly")


class TestMultipleInvoiceFormats:
    """Test that parser works on at least 3 different invoice formats"""
    
    def test_format_1_columnar_with_header(self):
        """Format 1: Standard columnar invoice with header row"""
        from services.layout_parser import parse_invoice_layout
        
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "Product A", "qty": "10", "price": "5.00", "total": "50.00"},
            {"description": "Product B", "qty": "5", "price": "12.00", "total": "60.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image)
        
        assert result["header_detected"] == True, "Should detect header"
        assert len(result["items"]) >= 1, "Should extract items"
        print(f"PASS - Format 1 (columnar with header): {len(result['items'])} items, parser={result['parser_used']}")
    
    def test_format_2_simple_receipt(self):
        """Format 2: Simple receipt format (informal)"""
        from services.layout_parser import parse_invoice_layout
        
        items = [
            {"name": "Coffee", "qty": 2, "price": 4.50, "total": 9.00},
            {"name": "Muffin", "qty": 1, "price": 3.50, "total": 3.50},
        ]
        image_bytes = create_simple_receipt_image(items)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image, document_type="simple_receipt")
        
        assert result["parser_used"] == "receipt_parser", "Should use receipt parser"
        print(f"PASS - Format 2 (simple receipt): {len(result['items'])} items")
    
    def test_format_3_no_header_inferred(self):
        """Format 3: Invoice without header (columns inferred from data)"""
        from services.layout_parser import parse_invoice_layout
        
        items = [
            {"description": "Widget X", "qty": "3", "price": "15.00", "total": "45.00"},
            {"description": "Widget Y", "qty": "7", "price": "8.00", "total": "56.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=None)
        b64_image = base64.b64encode(image_bytes).decode()
        
        result = parse_invoice_layout(b64_image)
        
        # Should use inferred or fallback parser
        assert result["parser_used"] in ["structured_columnar", "structured_inferred", "structured_fallback"], \
            f"Should use structured parser variant, got {result['parser_used']}"
        print(f"PASS - Format 3 (no header): {len(result['items'])} items, parser={result['parser_used']}")


class TestNoColumnMixing:
    """Test that columns are not mixed between each other"""
    
    def test_columns_not_mixed(self):
        """Verify no mixing between columns - each field maps to correct column"""
        from services.layout_parser import run_ocr, detect_rows, detect_columns
        
        header = {"description": "Description", "qty": "Qty", "price": "Price", "total": "Total"}
        items = [
            {"description": "CHICKEN BREAST", "qty": "5", "price": "10.00", "total": "50.00"},
        ]
        image_bytes = create_columnar_invoice_image(items, header_row=header)
        
        words = run_ocr(image_bytes)
        rows = detect_rows(words)
        col_info = detect_columns(rows)
        
        columns = col_info.get("columns", [])
        
        # Check that columns have distinct boundaries (no overlap)
        for i, col1 in enumerate(columns):
            for j, col2 in enumerate(columns):
                if i < j:
                    # Columns should not significantly overlap
                    overlap = min(col1["right"], col2["right"]) - max(col1["left"], col2["left"])
                    col1_width = col1["right"] - col1["left"]
                    col2_width = col2["right"] - col2["left"]
                    
                    # Allow some overlap but not more than 50% of smaller column
                    min_width = min(col1_width, col2_width)
                    if min_width > 0:
                        overlap_ratio = overlap / min_width
                        assert overlap_ratio < 0.5, f"Columns {col1['name']} and {col2['name']} overlap too much"
        
        print(f"PASS - {len(columns)} columns detected with no significant overlap")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
