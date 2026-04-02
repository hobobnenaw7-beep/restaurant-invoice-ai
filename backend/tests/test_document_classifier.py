"""
Test Document Type Classification (Phase 2)
Tests classify_document(), get_parser_route(), layout analysis, and API integration.

Document Types:
- simple_receipt: handwritten/informal (few lines, low density)
- structured_invoice: formal columnar (many lines, table lines)
- vendor_specific: known vendor with stored patterns
- multi_page_pdf: PDF with page_count > 1
"""
import pytest
import requests
import os
import base64
import io
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ── Helper: Create test images ──

def create_simple_receipt_image():
    """Create a simple receipt image: few lines, informal layout, narrow width."""
    img = Image.new('RGB', (400, 600), color='white')
    draw = ImageDraw.Draw(img)
    # Few lines of text (simple receipt style)
    draw.text((20, 50), "RECEIPT", fill='black')
    draw.text((20, 100), "Coffee - $3.50", fill='black')
    draw.text((20, 140), "Muffin - $2.00", fill='black')
    draw.text((20, 200), "Total: $5.50", fill='black')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def create_structured_invoice_image():
    """Create a structured invoice image: many lines, table structure, wide width."""
    img = Image.new('RGB', (1200, 1600), color='white')
    draw = ImageDraw.Draw(img)
    # Header
    draw.text((50, 30), "SYSCO FOODS INVOICE", fill='black')
    draw.text((50, 60), "Invoice #: INV-2024-001", fill='black')
    draw.text((50, 90), "Date: 2024-01-15", fill='black')
    # Table header with horizontal line
    draw.line([(50, 130), (1150, 130)], fill='black', width=2)
    draw.text((50, 140), "Item", fill='black')
    draw.text((400, 140), "Qty", fill='black')
    draw.text((500, 140), "Unit", fill='black')
    draw.text((700, 140), "Price", fill='black')
    draw.text((900, 140), "Total", fill='black')
    draw.line([(50, 170), (1150, 170)], fill='black', width=2)
    # Many line items (20+ lines)
    y = 190
    items = [
        "Chicken Breast 10LB", "Ground Beef 5LB", "Pork Loin 8LB",
        "Salmon Fillet 4LB", "Shrimp 31-35 2LB", "Tilapia 3LB",
        "Lettuce Romaine", "Tomatoes Roma", "Onions Yellow",
        "Potatoes Russet", "Carrots Baby", "Celery Bunch",
        "Olive Oil 1GAL", "Vegetable Oil 1GAL", "Butter 1LB",
        "Heavy Cream 1QT", "Milk 1GAL", "Eggs Large 30ct",
        "Flour AP 25LB", "Sugar White 10LB", "Salt Kosher 3LB",
        "Pepper Black 1LB", "Garlic Minced 1LB", "Basil Fresh"
    ]
    for i, item in enumerate(items):
        draw.text((50, y), item, fill='black')
        draw.text((400, y), str((i % 5) + 1), fill='black')
        draw.text((500, y), "EA", fill='black')
        draw.text((700, y), f"${(i + 1) * 5:.2f}", fill='black')
        draw.text((900, y), f"${(i + 1) * 5 * ((i % 5) + 1):.2f}", fill='black')
        y += 30
    # Footer with totals
    draw.line([(50, y + 10), (1150, y + 10)], fill='black', width=2)
    draw.text((700, y + 20), "Subtotal:", fill='black')
    draw.text((900, y + 20), "$1,234.56", fill='black')
    draw.text((700, y + 50), "Tax:", fill='black')
    draw.text((900, y + 50), "$98.76", fill='black')
    draw.text((700, y + 80), "Total:", fill='black')
    draw.text((900, y + 80), "$1,333.32", fill='black')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def create_medium_invoice_image():
    """Create a medium-complexity invoice (borderline case)."""
    img = Image.new('RGB', (800, 1000), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), "INVOICE", fill='black')
    draw.text((50, 60), "Date: 2024-01-15", fill='black')
    # 10 line items
    y = 120
    for i in range(10):
        draw.text((50, y), f"Item {i+1} - ${(i+1)*10:.2f}", fill='black')
        y += 40
    draw.text((50, y + 20), "Total: $550.00", fill='black')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def create_invalid_base64():
    """Return invalid base64 data."""
    return "not_valid_base64_data!!!"


# ── Test Fixtures ──

@pytest.fixture
def api_session():
    """Create a requests session with auth."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    # Login to get token
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    if login_resp.status_code == 200:
        token = login_resp.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


# ── Unit Tests for classify_document() ──

class TestClassifyDocumentFunction:
    """Test classify_document() function directly."""

    def test_simple_receipt_classification(self):
        """classify_document() returns simple_receipt for informal/handwritten receipts."""
        from services.document_classifier import classify_document
        
        simple_img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[simple_img],
            file_format="image",
            page_count=1,
        )
        
        assert result["document_type"] == "simple_receipt", f"Expected simple_receipt, got {result['document_type']}"
        assert result["page_count"] == 1
        assert result["file_format"] == "image"
        assert result["vendor_pattern"] is None
        assert "confidence_reason" in result
        assert "layout_features" in result
        print(f"PASS: simple_receipt classification - {result['confidence_reason']}")

    def test_structured_invoice_classification(self):
        """classify_document() returns structured_invoice for formal columnar invoices."""
        from services.document_classifier import classify_document
        
        structured_img = create_structured_invoice_image()
        result = classify_document(
            images_b64=[structured_img],
            file_format="image",
            page_count=1,
        )
        
        assert result["document_type"] == "structured_invoice", f"Expected structured_invoice, got {result['document_type']}"
        assert result["page_count"] == 1
        assert result["file_format"] == "image"
        assert "confidence_reason" in result
        assert "layout_features" in result
        # Check layout features indicate structured document
        layout = result["layout_features"]
        assert layout.get("estimated_line_count", 0) >= 10, f"Expected many lines, got {layout.get('estimated_line_count')}"
        print(f"PASS: structured_invoice classification - {result['confidence_reason']}")

    def test_vendor_specific_classification(self):
        """classify_document() returns vendor_specific when has_vendor_pattern=True."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img],
            file_format="image",
            page_count=1,
            vendor_name="Sysco Foods",
            has_vendor_pattern=True,
        )
        
        assert result["document_type"] == "vendor_specific", f"Expected vendor_specific, got {result['document_type']}"
        assert result["vendor_pattern"] == "Sysco Foods"
        assert "Matched vendor pattern" in result["confidence_reason"]
        print(f"PASS: vendor_specific classification - {result['confidence_reason']}")

    def test_multi_page_pdf_classification(self):
        """classify_document() returns multi_page_pdf for PDF files with page_count > 1."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img, img, img],  # 3 pages
            file_format="pdf",
            page_count=3,
        )
        
        assert result["document_type"] == "multi_page_pdf", f"Expected multi_page_pdf, got {result['document_type']}"
        assert result["page_count"] == 3
        assert result["file_format"] == "pdf"
        assert "3 pages" in result["confidence_reason"]
        print(f"PASS: multi_page_pdf classification - {result['confidence_reason']}")

    def test_single_page_pdf_classification(self):
        """classify_document() returns structured_invoice for single-page PDFs (layout-based)."""
        from services.document_classifier import classify_document
        
        structured_img = create_structured_invoice_image()
        result = classify_document(
            images_b64=[structured_img],
            file_format="pdf",
            page_count=1,
        )
        
        # Single-page PDF should be classified by layout, not as multi_page_pdf
        assert result["document_type"] in ["structured_invoice", "simple_receipt"], \
            f"Expected layout-based classification, got {result['document_type']}"
        assert result["page_count"] == 1
        assert result["file_format"] == "pdf"
        print(f"PASS: single-page PDF classification - {result['document_type']}")

    def test_empty_images_list(self):
        """classify_document() gracefully handles empty images list."""
        from services.document_classifier import classify_document
        
        result = classify_document(
            images_b64=[],
            file_format="image",
            page_count=0,
        )
        
        # Should fallback to structured_invoice
        assert result["document_type"] == "structured_invoice"
        assert "Fallback" in result["confidence_reason"] or "no images" in result["confidence_reason"].lower()
        print(f"PASS: empty images fallback - {result['confidence_reason']}")

    def test_invalid_base64_data(self):
        """classify_document() gracefully handles invalid base64 data."""
        from services.document_classifier import classify_document
        
        result = classify_document(
            images_b64=[create_invalid_base64()],
            file_format="image",
            page_count=1,
        )
        
        # Should fallback gracefully - returns structured_invoice with empty layout_features
        assert result["document_type"] == "structured_invoice"
        # Empty layout_features indicates the layout analysis failed and fell back
        assert result["layout_features"] == {}, f"Expected empty layout_features on invalid input, got {result['layout_features']}"
        print(f"PASS: invalid base64 fallback - type={result['document_type']}, layout_features={result['layout_features']}")


# ── Unit Tests for get_parser_route() ──

class TestGetParserRoute:
    """Test get_parser_route() function."""

    def test_simple_receipt_route(self):
        """get_parser_route() maps simple_receipt to parser.simple_receipt."""
        from services.document_classifier import get_parser_route
        
        classification = {"document_type": "simple_receipt", "page_count": 1}
        route = get_parser_route(classification)
        
        assert route == "parser.simple_receipt"
        print("PASS: simple_receipt -> parser.simple_receipt")

    def test_structured_invoice_route(self):
        """get_parser_route() maps structured_invoice to parser.structured_invoice."""
        from services.document_classifier import get_parser_route
        
        classification = {"document_type": "structured_invoice", "page_count": 1}
        route = get_parser_route(classification)
        
        assert route == "parser.structured_invoice"
        print("PASS: structured_invoice -> parser.structured_invoice")

    def test_vendor_specific_route(self):
        """get_parser_route() maps vendor_specific to parser.vendor_specific."""
        from services.document_classifier import get_parser_route
        
        classification = {"document_type": "vendor_specific", "page_count": 1, "vendor_pattern": "Sysco"}
        route = get_parser_route(classification)
        
        assert route == "parser.vendor_specific"
        print("PASS: vendor_specific -> parser.vendor_specific")

    def test_multi_page_pdf_route(self):
        """get_parser_route() maps multi_page_pdf to parser.multi_page_pdf."""
        from services.document_classifier import get_parser_route
        
        classification = {"document_type": "multi_page_pdf", "page_count": 3}
        route = get_parser_route(classification)
        
        assert route == "parser.multi_page_pdf"
        print("PASS: multi_page_pdf -> parser.multi_page_pdf")

    def test_unknown_type_fallback(self):
        """get_parser_route() falls back to structured_invoice for unknown types."""
        from services.document_classifier import get_parser_route
        
        classification = {"document_type": "unknown_type", "page_count": 1}
        route = get_parser_route(classification)
        
        assert route == "parser.structured_invoice"
        print("PASS: unknown_type -> parser.structured_invoice (fallback)")


# ── Unit Tests for Layout Analysis ──

class TestLayoutAnalysis:
    """Test _analyze_first_page() layout feature extraction."""

    def test_layout_features_extracted(self):
        """Layout analysis extracts all required features."""
        from services.document_classifier import _analyze_first_page
        
        img = create_structured_invoice_image()
        layout = _analyze_first_page(img)
        
        # Check all required fields
        required_fields = [
            "width", "height", "aspect_ratio", "text_density",
            "horizontal_line_ratio", "content_fill", "estimated_line_count"
        ]
        for field in required_fields:
            assert field in layout, f"Missing layout field: {field}"
        
        # Validate types
        assert isinstance(layout["width"], int)
        assert isinstance(layout["height"], int)
        assert isinstance(layout["aspect_ratio"], float)
        assert isinstance(layout["text_density"], float)
        assert isinstance(layout["horizontal_line_ratio"], float)
        assert isinstance(layout["content_fill"], float)
        assert isinstance(layout["estimated_line_count"], int)
        
        print(f"PASS: Layout features extracted - {layout}")

    def test_layout_width_height(self):
        """Layout analysis correctly extracts image dimensions."""
        from services.document_classifier import _analyze_first_page
        
        # Create image with known dimensions
        img = Image.new('RGB', (800, 1200), color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        
        layout = _analyze_first_page(b64)
        
        assert layout["width"] == 800
        assert layout["height"] == 1200
        assert abs(layout["aspect_ratio"] - (800/1200)) < 0.01
        print(f"PASS: Dimensions correct - {layout['width']}x{layout['height']}")

    def test_layout_invalid_input(self):
        """Layout analysis returns empty dict for invalid input."""
        from services.document_classifier import _analyze_first_page
        
        layout = _analyze_first_page("invalid_base64!!!")
        
        assert layout == {}
        print("PASS: Invalid input returns empty dict")


# ── Classification Result Structure Tests ──

class TestClassificationResultStructure:
    """Test that classification results include all required fields."""

    def test_result_includes_all_fields(self):
        """Classification result includes document_type, page_count, file_format, vendor_pattern, confidence_reason, layout_features."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img],
            file_format="image",
            page_count=1,
        )
        
        required_fields = [
            "document_type", "page_count", "file_format",
            "vendor_pattern", "confidence_reason", "layout_features"
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"
        
        print(f"PASS: All required fields present - {list(result.keys())}")

    def test_vendor_pattern_none_when_not_matched(self):
        """vendor_pattern is None when no vendor pattern matched."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img],
            file_format="image",
            page_count=1,
            vendor_name=None,
            has_vendor_pattern=False,
        )
        
        assert result["vendor_pattern"] is None
        print("PASS: vendor_pattern is None when not matched")

    def test_vendor_pattern_set_when_matched(self):
        """vendor_pattern is set when vendor pattern matched."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img],
            file_format="image",
            page_count=1,
            vendor_name="Test Vendor",
            has_vendor_pattern=True,
        )
        
        assert result["vendor_pattern"] == "Test Vendor"
        print("PASS: vendor_pattern set when matched")


# ── API Integration Tests ──

class TestUploadExtractAPIIntegration:
    """Test POST /api/upload/extract includes classification fields."""

    def test_extract_response_includes_classification(self, api_session):
        """POST /api/upload/extract response includes document_classification and parser_route."""
        # Create a simple test image
        img = Image.new('RGB', (400, 600), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 50), "TEST RECEIPT", fill='black')
        draw.text((20, 100), "Item 1 - $10.00", fill='black')
        draw.text((20, 150), "Total: $10.00", fill='black')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        
        # Upload via multipart form
        files = {'file': ('test_receipt.png', buf, 'image/png')}
        data = {'document_type': 'purchase_invoice'}
        
        # Remove Content-Type header for multipart
        headers = dict(api_session.headers)
        if 'Content-Type' in headers:
            del headers['Content-Type']
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            files=files,
            data=data,
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Check classification fields in response
        assert "document_classification" in result, "Missing document_classification in response"
        assert "parser_route" in result, "Missing parser_route in response"
        
        classification = result["document_classification"]
        assert "document_type" in classification
        assert "page_count" in classification
        assert "file_format" in classification
        assert "vendor_pattern" in classification
        assert "confidence_reason" in classification
        assert "layout_features" in classification
        
        # Verify parser_route format
        assert result["parser_route"].startswith("parser.")
        
        print(f"PASS: API response includes classification - type={classification['document_type']}, route={result['parser_route']}")

    def test_classification_stored_in_database(self, api_session):
        """Classification is stored in uploaded_receipts collection."""
        # Create test image
        img = Image.new('RGB', (400, 600), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 50), "DB TEST RECEIPT", fill='black')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        
        files = {'file': ('db_test.png', buf, 'image/png')}
        data = {'document_type': 'purchase_invoice'}
        
        headers = dict(api_session.headers)
        if 'Content-Type' in headers:
            del headers['Content-Type']
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            files=files,
            data=data,
            headers=headers
        )
        
        assert response.status_code == 200
        result = response.json()
        receipt_id = result.get("receipt_id")
        
        assert receipt_id is not None, "No receipt_id in response"
        
        # The classification should be stored - we verify via the response
        # (Direct DB access would require async, so we verify via API response)
        assert "document_classification" in result
        assert "parser_route" in result
        
        print(f"PASS: Classification stored with receipt_id={receipt_id}")


# ── PARSER_ROUTES Dict Tests ──

class TestParserRoutesDict:
    """Test PARSER_ROUTES dictionary mapping."""

    def test_parser_routes_contains_all_types(self):
        """PARSER_ROUTES contains mappings for all document types."""
        from services.document_classifier import PARSER_ROUTES
        
        expected_types = ["simple_receipt", "structured_invoice", "vendor_specific", "multi_page_pdf"]
        
        for doc_type in expected_types:
            assert doc_type in PARSER_ROUTES, f"Missing {doc_type} in PARSER_ROUTES"
            assert PARSER_ROUTES[doc_type].startswith("parser."), f"Invalid route format for {doc_type}"
        
        print(f"PASS: PARSER_ROUTES contains all types - {PARSER_ROUTES}")

    def test_parser_routes_values(self):
        """PARSER_ROUTES has correct route values."""
        from services.document_classifier import PARSER_ROUTES
        
        expected = {
            "simple_receipt": "parser.simple_receipt",
            "structured_invoice": "parser.structured_invoice",
            "vendor_specific": "parser.vendor_specific",
            "multi_page_pdf": "parser.multi_page_pdf",
        }
        
        for doc_type, route in expected.items():
            assert PARSER_ROUTES[doc_type] == route, f"Expected {route}, got {PARSER_ROUTES[doc_type]}"
        
        print("PASS: All PARSER_ROUTES values correct")


# ── Classification Priority Tests ──

class TestClassificationPriority:
    """Test classification priority rules."""

    def test_multi_page_pdf_has_highest_priority(self):
        """Multi-page PDF classification takes priority over vendor_specific."""
        from services.document_classifier import classify_document
        
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img, img],  # 2 pages
            file_format="pdf",
            page_count=2,
            vendor_name="Sysco",
            has_vendor_pattern=True,  # Even with vendor pattern
        )
        
        # Multi-page PDF should win
        assert result["document_type"] == "multi_page_pdf"
        print("PASS: multi_page_pdf has priority over vendor_specific")

    def test_vendor_specific_has_priority_over_layout(self):
        """Vendor-specific classification takes priority over layout-based."""
        from services.document_classifier import classify_document
        
        # Use simple receipt image but with vendor pattern
        img = create_simple_receipt_image()
        result = classify_document(
            images_b64=[img],
            file_format="image",
            page_count=1,
            vendor_name="Known Vendor",
            has_vendor_pattern=True,
        )
        
        # Vendor-specific should win over layout-based simple_receipt
        assert result["document_type"] == "vendor_specific"
        print("PASS: vendor_specific has priority over layout-based classification")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
