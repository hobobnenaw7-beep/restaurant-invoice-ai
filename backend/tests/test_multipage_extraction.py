"""
Test multi-page invoice extraction with preprocessing, page classification, and priority rules.
Tests the new preprocessing.py module and its integration with /api/upload/extract endpoint.
"""
import pytest
import requests
import os
import sys
import base64
from PIL import Image, ImageDraw, ImageFont
import io

# Add backend directory to path for importing preprocessing module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# Unit Tests for preprocessing.py functions
# ============================================================================

class TestPreprocessingModule:
    """Unit tests for preprocessing.py functions."""
    
    def test_preprocess_image_basic(self):
        """Test that preprocess_image returns valid PNG bytes."""
        from preprocessing import preprocess_image
        
        # Create a simple test image
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), "Test Invoice", fill='black')
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        original_bytes = buf.getvalue()
        
        # Process the image
        processed = preprocess_image(original_bytes)
        
        # Verify it returns bytes
        assert isinstance(processed, bytes)
        assert len(processed) > 0
        
        # Verify it's a valid image
        processed_img = Image.open(io.BytesIO(processed))
        assert processed_img.mode == 'RGB'
        print(f"PASS: preprocess_image returns valid PNG ({len(original_bytes)}→{len(processed)} bytes)")
    
    def test_preprocess_image_fallback_on_error(self):
        """Test that preprocess_image returns original bytes on error."""
        from preprocessing import preprocess_image
        
        # Pass invalid image bytes
        invalid_bytes = b"not an image"
        result = preprocess_image(invalid_bytes)
        
        # Should return original bytes on error
        assert result == invalid_bytes
        print("PASS: preprocess_image returns original bytes on error")
    
    def test_default_classifications_single_page(self):
        """Test _default_classifications for single page."""
        from preprocessing import _default_classifications
        
        result = _default_classifications(1)
        assert result == ["header"]
        print("PASS: _default_classifications(1) = ['header']")
    
    def test_default_classifications_two_pages(self):
        """Test _default_classifications for two pages."""
        from preprocessing import _default_classifications
        
        result = _default_classifications(2)
        assert result == ["header", "totals"]
        print("PASS: _default_classifications(2) = ['header', 'totals']")
    
    def test_default_classifications_three_pages(self):
        """Test _default_classifications for three pages."""
        from preprocessing import _default_classifications
        
        result = _default_classifications(3)
        assert result == ["header", "line_items", "totals"]
        print("PASS: _default_classifications(3) = ['header', 'line_items', 'totals']")
    
    def test_default_classifications_five_pages(self):
        """Test _default_classifications for five pages."""
        from preprocessing import _default_classifications
        
        result = _default_classifications(5)
        assert result == ["header", "line_items", "line_items", "line_items", "totals"]
        print("PASS: _default_classifications(5) = ['header', 'line_items', 'line_items', 'line_items', 'totals']")
    
    def test_build_page_aware_prompt(self):
        """Test build_page_aware_prompt generates correct prompt."""
        from preprocessing import build_page_aware_prompt
        
        page_types = ["header", "line_items", "totals"]
        prompt = build_page_aware_prompt(page_types)
        
        # Check key elements are present
        assert "3 page(s)" in prompt
        assert "Page 1: HEADER" in prompt
        assert "Page 2: LINE ITEMS" in prompt
        assert "Page 3: TOTALS" in prompt
        assert "PRIORITY RULES" in prompt
        assert "TOTALS page wins" in prompt
        assert "HEADER page wins" in prompt
        print("PASS: build_page_aware_prompt generates correct prompt structure")
    
    def test_build_page_aware_prompt_with_vendor_hint(self):
        """Test build_page_aware_prompt includes vendor hint."""
        from preprocessing import build_page_aware_prompt
        
        page_types = ["header", "totals"]
        vendor_hint = "\n\nVENDOR HINT: This is Sysco"
        prompt = build_page_aware_prompt(page_types, vendor_hint)
        
        assert "VENDOR HINT: This is Sysco" in prompt
        print("PASS: build_page_aware_prompt includes vendor hint")
    
    def test_merge_extractions_vendor_priority(self):
        """Test merge_extractions gives header page priority for vendor fields."""
        from preprocessing import merge_extractions
        
        page_results = [
            {"supplier_name": "Header Vendor", "invoice_date": "2026-01-15", "invoice_number": "INV-001", "items": [], "subtotal": 100, "tax": 10, "total": 110},
            {"supplier_name": "Items Vendor", "invoice_date": "2026-01-16", "invoice_number": "INV-002", "items": [], "subtotal": 200, "tax": 20, "total": 220},
            {"supplier_name": "Totals Vendor", "invoice_date": "2026-01-17", "invoice_number": "INV-003", "items": [], "subtotal": 300, "tax": 30, "total": 330},
        ]
        page_types = ["header", "line_items", "totals"]
        
        merged = merge_extractions(page_results, page_types)
        
        # Header page should win for vendor fields
        assert merged["supplier_name"] == "Header Vendor"
        assert merged["invoice_date"] == "2026-01-15"
        assert merged["invoice_number"] == "INV-001"
        print("PASS: merge_extractions gives header page priority for vendor fields")
    
    def test_merge_extractions_totals_priority(self):
        """Test merge_extractions gives totals page priority for totals fields."""
        from preprocessing import merge_extractions
        
        page_results = [
            {"supplier_name": "Vendor", "invoice_date": "2026-01-15", "invoice_number": "INV-001", "items": [], "subtotal": 100, "tax": 10, "total": 110},
            {"supplier_name": "", "invoice_date": "", "invoice_number": "", "items": [], "subtotal": 200, "tax": 20, "total": 220},
            {"supplier_name": "", "invoice_date": "", "invoice_number": "", "items": [], "subtotal": 300, "tax": 30, "total": 330},
        ]
        page_types = ["header", "line_items", "totals"]
        
        merged = merge_extractions(page_results, page_types)
        
        # Totals page should win for totals fields
        assert merged["subtotal"] == 300
        assert merged["tax"] == 30
        assert merged["total"] == 330
        print("PASS: merge_extractions gives totals page priority for totals fields")
    
    def test_merge_extractions_item_dedup(self):
        """Test merge_extractions deduplicates items by (name, qty, price)."""
        from preprocessing import merge_extractions
        
        page_results = [
            {"supplier_name": "Vendor", "invoice_date": "2026-01-15", "invoice_number": "INV-001", 
             "items": [{"raw_name": "Chicken", "quantity": 5, "unit_price": 10, "total": 50}], 
             "subtotal": 50, "tax": 5, "total": 55},
            {"supplier_name": "", "invoice_date": "", "invoice_number": "", 
             "items": [
                 {"raw_name": "Chicken", "quantity": 5, "unit_price": 10, "total": 50},  # Duplicate
                 {"raw_name": "Beef", "quantity": 3, "unit_price": 15, "total": 45}
             ], 
             "subtotal": 95, "tax": 9.5, "total": 104.5},
        ]
        page_types = ["header", "line_items"]
        
        merged = merge_extractions(page_results, page_types)
        
        # Should have 2 unique items (Chicken deduplicated)
        assert len(merged["items"]) == 2
        item_names = [it["raw_name"] for it in merged["items"]]
        assert "Chicken" in item_names
        assert "Beef" in item_names
        print("PASS: merge_extractions deduplicates items correctly")
    
    def test_merge_extractions_skips_terms_page(self):
        """Test merge_extractions skips terms pages."""
        from preprocessing import merge_extractions
        
        page_results = [
            {"supplier_name": "Vendor", "invoice_date": "2026-01-15", "invoice_number": "INV-001", "items": [], "subtotal": 100, "tax": 10, "total": 110},
            {"supplier_name": "Terms Vendor", "invoice_date": "2026-01-20", "invoice_number": "TERMS-001", "items": [{"raw_name": "Terms Item", "quantity": 1, "unit_price": 999, "total": 999}], "subtotal": 999, "tax": 99, "total": 1098},
        ]
        page_types = ["header", "terms"]
        
        merged = merge_extractions(page_results, page_types)
        
        # Terms page should be skipped
        assert merged["supplier_name"] == "Vendor"
        assert len(merged["items"]) == 0  # Terms items should be skipped
        print("PASS: merge_extractions skips terms pages")


# ============================================================================
# API Integration Tests for /api/upload/extract
# ============================================================================

class TestExtractEndpointSinglePage:
    """Test single-page extraction (regression tests)."""
    
    def test_single_image_purchase_invoice(self, auth_headers):
        """Test single image purchase_invoice extraction - should work without page classification."""
        # Use existing test image
        with open("/tmp/page2_items.png", "rb") as f:
            image_bytes = f.read()
        
        files = {"file": ("test_single.png", image_bytes, "image/png")}
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Verify response structure
        assert "extracted_data" in result
        assert "document_type" in result
        assert result["document_type"] == "purchase_invoice"
        
        # page_types should be None for single-page
        assert result.get("page_types") is None, f"Expected page_types=None for single page, got {result.get('page_types')}"
        
        print(f"PASS: Single-page purchase_invoice works, page_types={result.get('page_types')}")
    
    def test_single_image_sales_report(self, auth_headers):
        """Test single image sales_report extraction - should NOT trigger page classification."""
        # Create a simple sales report image
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Daily Sales Report", fill='black')
        draw.text((10, 40), "Date: 2026-01-15", fill='black')
        draw.text((10, 70), "Total Sales: $1,500.00", fill='black')
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        image_bytes = buf.getvalue()
        
        files = {"file": ("sales_report.png", image_bytes, "image/png")}
        data = {"document_type": "sales_report"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # page_types should be None for sales_report
        assert result.get("page_types") is None, f"Expected page_types=None for sales_report, got {result.get('page_types')}"
        
        print(f"PASS: sales_report does NOT trigger page classification, page_types={result.get('page_types')}")
    
    def test_single_image_other_expense(self, auth_headers):
        """Test single image other_expense extraction - should NOT trigger page classification."""
        # Create a simple expense image
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Utility Bill", fill='black')
        draw.text((10, 40), "Electric Company", fill='black')
        draw.text((10, 70), "Amount: $250.00", fill='black')
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        image_bytes = buf.getvalue()
        
        files = {"file": ("utility_bill.png", image_bytes, "image/png")}
        data = {"document_type": "other_expense"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # page_types should be None for other_expense
        assert result.get("page_types") is None, f"Expected page_types=None for other_expense, got {result.get('page_types')}"
        
        print(f"PASS: other_expense does NOT trigger page classification, page_types={result.get('page_types')}")


class TestExtractEndpointMultiPage:
    """Test multi-page extraction with page classification."""
    
    def test_three_page_purchase_invoice(self, auth_headers):
        """Test 3-page purchase_invoice extraction with page classification."""
        # Use existing test images
        with open("/tmp/page1_header.png", "rb") as f:
            page1 = f.read()
        with open("/tmp/page2_items.png", "rb") as f:
            page2 = f.read()
        with open("/tmp/page3_totals.png", "rb") as f:
            page3 = f.read()
        
        files = [
            ("files", ("page1_header.png", page1, "image/png")),
            ("files", ("page2_items.png", page2, "image/png")),
            ("files", ("page3_totals.png", page3, "image/png")),
        ]
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Verify page_types is returned
        page_types = result.get("page_types")
        assert page_types is not None, "Expected page_types to be set for multi-page purchase_invoice"
        assert isinstance(page_types, list), f"Expected page_types to be a list, got {type(page_types)}"
        assert len(page_types) == 3, f"Expected 3 page types, got {len(page_types)}"
        
        # Verify page types are valid
        valid_types = {"header", "line_items", "totals", "terms"}
        for pt in page_types:
            assert pt in valid_types, f"Invalid page type: {pt}"
        
        # Verify extracted data
        extracted = result.get("extracted_data", {})
        assert "items" in extracted, "Expected items in extracted_data"
        
        print(f"PASS: 3-page purchase_invoice returns page_types={page_types}")
        print(f"  - Extracted {len(extracted.get('items', []))} items")
        print(f"  - Supplier: {extracted.get('supplier_name', 'N/A')}")
        print(f"  - Total: {extracted.get('total', 'N/A')}")
    
    def test_two_page_purchase_invoice_with_overlap(self, auth_headers):
        """Test 2-page purchase_invoice with overlapping content (deduplication)."""
        # Use existing overlap test images
        with open("/tmp/overlap_page1.png", "rb") as f:
            page1 = f.read()
        with open("/tmp/overlap_page2.png", "rb") as f:
            page2 = f.read()
        
        files = [
            ("files", ("overlap_page1.png", page1, "image/png")),
            ("files", ("overlap_page2.png", page2, "image/png")),
        ]
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Verify page_types is returned
        page_types = result.get("page_types")
        assert page_types is not None, "Expected page_types to be set for multi-page purchase_invoice"
        assert len(page_types) == 2, f"Expected 2 page types, got {len(page_types)}"
        
        # Verify extracted data
        extracted = result.get("extracted_data", {})
        items = extracted.get("items", [])
        
        print(f"PASS: 2-page purchase_invoice with overlap returns page_types={page_types}")
        print(f"  - Extracted {len(items)} items (should be deduplicated)")
        
        # Check for deduplication - if Calamari appears, it should only appear once
        calamari_count = sum(1 for it in items if "calamari" in it.get("raw_name", "").lower())
        if calamari_count > 0:
            assert calamari_count == 1, f"Expected Calamari to appear once (deduplicated), got {calamari_count}"
            print(f"  - Calamari deduplication verified: appears {calamari_count} time(s)")
    
    def test_multipage_sales_report_no_classification(self, auth_headers):
        """Test multi-page sales_report does NOT trigger page classification."""
        # Create two simple sales report images
        images = []
        for i in range(2):
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Sales Report Page {i+1}", fill='black')
            draw.text((10, 40), f"Total: ${500 * (i+1)}", fill='black')
            
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            images.append(buf.getvalue())
        
        files = [
            ("files", ("sales_page1.png", images[0], "image/png")),
            ("files", ("sales_page2.png", images[1], "image/png")),
        ]
        data = {"document_type": "sales_report"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # page_types should be None for sales_report even with multiple pages
        assert result.get("page_types") is None, f"Expected page_types=None for sales_report, got {result.get('page_types')}"
        
        print(f"PASS: Multi-page sales_report does NOT trigger page classification")


class TestPreprocessingIntegration:
    """Test that preprocessing is applied to uploaded images."""
    
    def test_preprocessing_logged(self, auth_headers):
        """Test that preprocessing is applied and logged."""
        # Create a test image
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "Test Invoice", fill='black')
        draw.text((50, 100), "Vendor: Test Supplier", fill='black')
        draw.text((50, 150), "Date: 2026-01-15", fill='black')
        draw.text((50, 200), "Item: Test Item  Qty: 5  Price: $10.00  Total: $50.00", fill='black')
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        image_bytes = buf.getvalue()
        original_size = len(image_bytes)
        
        files = {"file": ("test_preprocess.png", image_bytes, "image/png")}
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # The preprocessing should have been applied (we can't directly verify from response,
        # but we can check the backend logs show "Preprocessed image: X→Y bytes")
        print(f"PASS: Image uploaded successfully (original size: {original_size} bytes)")
        print("  - Check backend logs for 'Preprocessed image: X→Y bytes' message")


class TestPageClassificationTypes:
    """Test that page classification returns valid types."""
    
    def test_page_types_are_valid(self, auth_headers):
        """Test that all returned page_types are valid."""
        # Use existing test images
        with open("/tmp/page1_header.png", "rb") as f:
            page1 = f.read()
        with open("/tmp/page2_items.png", "rb") as f:
            page2 = f.read()
        
        files = [
            ("files", ("page1.png", page1, "image/png")),
            ("files", ("page2.png", page2, "image/png")),
        ]
        data = {"document_type": "purchase_invoice"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=90
        )
        
        assert response.status_code == 200
        result = response.json()
        
        page_types = result.get("page_types")
        assert page_types is not None
        
        valid_types = {"header", "line_items", "totals", "terms"}
        for pt in page_types:
            assert pt in valid_types, f"Invalid page type: {pt}. Valid types: {valid_types}"
        
        print(f"PASS: All page types are valid: {page_types}")


# ============================================================================
# Backend Health Check
# ============================================================================

class TestBackendHealth:
    """Test that backend starts without errors."""
    
    def test_auth_login(self):
        """Test authentication works."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }, timeout=10)
        assert response.status_code == 200
        assert "token" in response.json()
        print("PASS: Authentication works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
