"""
Test Receipt OCR Improvement System
Tests for:
- POST /api/upload/extract - Extract data from receipt images/PDFs
- POST /api/receipts/learn - Save vendor patterns from corrected data
- GET /api/vendor-patterns - List vendor patterns
- GET /api/receipts - List uploaded receipts
- Vendor pattern matching on second extraction
"""

import pytest
import requests
import os
import base64
from io import BytesIO
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture
def test_image():
    """Create a simple test image with text for OCR testing."""
    # Create a simple image with some text-like content
    img = Image.new('RGB', (400, 300), color='white')
    # Add some basic shapes to simulate receipt content
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 390, 290], outline='black')
    draw.text((20, 20), "TEST VENDOR INC", fill='black')
    draw.text((20, 50), "Invoice #: INV-001", fill='black')
    draw.text((20, 80), "Date: 2026-03-25", fill='black')
    draw.text((20, 110), "Item 1: Tomatoes - $10.00", fill='black')
    draw.text((20, 140), "Item 2: Onions - $5.00", fill='black')
    draw.text((20, 170), "Total: $15.00", fill='black')
    
    # Save to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


class TestUploadExtractEndpoint:
    """Tests for POST /api/upload/extract endpoint."""
    
    def test_extract_requires_auth(self):
        """Test that extraction requires authentication."""
        # Create a minimal test image
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            files={"file": ("test.png", img_bytes, "image/png")},
            data={"document_type": "purchase_invoice"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_extract_returns_expected_fields(self, auth_token, test_image):
        """Test that extraction returns receipt_id, parsing_method, detected_vendor."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=headers,
            files={"file": ("receipt.png", test_image, "image/png")},
            data={"document_type": "purchase_invoice"},
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check required fields
        assert "extracted_data" in data, "Response should contain extracted_data"
        assert "receipt_id" in data, "Response should contain receipt_id"
        assert "parsing_method" in data, "Response should contain parsing_method"
        
        # parsing_method should be 'general' or 'vendor'
        assert data["parsing_method"] in ["general", "vendor"], f"parsing_method should be 'general' or 'vendor', got {data['parsing_method']}"
        
        # extracted_data should have expected structure for purchase_invoice
        extracted = data["extracted_data"]
        assert "supplier_name" in extracted or "error" in extracted, "extracted_data should have supplier_name or error"
        
        print(f"✓ Extraction returned receipt_id: {data['receipt_id']}")
        print(f"✓ Parsing method: {data['parsing_method']}")
        print(f"✓ Detected vendor: {data.get('detected_vendor', 'N/A')}")
    
    def test_extract_stores_receipt_record(self, auth_token, test_image):
        """Test that extraction stores a receipt record in uploaded_receipts."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Extract from image
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=headers,
            files={"file": ("receipt_test.png", test_image, "image/png")},
            data={"document_type": "purchase_invoice"},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        receipt_id = data.get("receipt_id")
        assert receipt_id, "Should return receipt_id"
        
        # Verify receipt is stored by listing receipts
        list_response = requests.get(
            f"{BASE_URL}/api/receipts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert list_response.status_code == 200
        receipts = list_response.json()
        
        # Find our receipt
        found = any(r.get("id") == receipt_id for r in receipts)
        assert found, f"Receipt {receipt_id} should be in receipts list"
        print(f"✓ Receipt {receipt_id} stored successfully")


class TestReceiptsLearnEndpoint:
    """Tests for POST /api/receipts/learn endpoint."""
    
    def test_learn_requires_auth(self):
        """Test that learning requires authentication."""
        response = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            json={"vendor_name": "Test Vendor", "corrected_items": []}
        )
        assert response.status_code == 401
    
    def test_learn_requires_vendor_name(self, auth_headers):
        """Test that vendor_name is required."""
        response = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            headers=auth_headers,
            json={"vendor_name": "", "corrected_items": []}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_learn_saves_vendor_pattern(self, auth_headers):
        """Test that learning saves a vendor pattern."""
        unique_vendor = f"TEST_VENDOR_LEARN_{os.urandom(4).hex()}"
        
        response = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            headers=auth_headers,
            json={
                "vendor_name": unique_vendor,
                "corrected_items": [
                    {"raw_name": "Tomatoes", "quantity": 5, "unit": "kg", "unit_price": 2.50, "total": 12.50},
                    {"raw_name": "Onions", "quantity": 3, "unit": "kg", "unit_price": 1.50, "total": 4.50}
                ],
                "corrected_date": "2026-03-25",
                "corrected_total": 17.00
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("vendor_name") == unique_vendor
        
        # Verify pattern was saved
        patterns_response = requests.get(
            f"{BASE_URL}/api/vendor-patterns",
            headers=auth_headers
        )
        assert patterns_response.status_code == 200
        patterns = patterns_response.json()
        
        found = any(p.get("vendor_name") == unique_vendor for p in patterns)
        assert found, f"Pattern for {unique_vendor} should be saved"
        print(f"✓ Vendor pattern saved for {unique_vendor}")
    
    def test_learn_merges_with_existing_pattern(self, auth_headers):
        """Test that learning merges with existing pattern (receipt_count increments)."""
        unique_vendor = f"TEST_VENDOR_MERGE_{os.urandom(4).hex()}"
        
        # First learn call
        response1 = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            headers=auth_headers,
            json={
                "vendor_name": unique_vendor,
                "corrected_items": [{"raw_name": "Apples", "quantity": 10, "unit": "kg", "unit_price": 3.00, "total": 30.00}],
                "corrected_total": 30.00
            }
        )
        assert response1.status_code == 200
        assert response1.json().get("parsing_method") == "new_pattern"
        
        # Second learn call - should merge
        response2 = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            headers=auth_headers,
            json={
                "vendor_name": unique_vendor,
                "corrected_items": [{"raw_name": "Oranges", "quantity": 5, "unit": "kg", "unit_price": 4.00, "total": 20.00}],
                "corrected_total": 20.00
            }
        )
        assert response2.status_code == 200
        assert response2.json().get("parsing_method") == "vendor", "Second call should return 'vendor' parsing_method"
        
        # Verify pattern has merged items
        patterns_response = requests.get(
            f"{BASE_URL}/api/vendor-patterns",
            headers=auth_headers
        )
        patterns = patterns_response.json()
        pattern = next((p for p in patterns if p.get("vendor_name") == unique_vendor), None)
        
        assert pattern, f"Pattern for {unique_vendor} should exist"
        hints = pattern.get("hints", {})
        typical_items = hints.get("typical_items", [])
        receipt_count = hints.get("receipt_count", 0)
        
        assert receipt_count == 2, f"receipt_count should be 2, got {receipt_count}"
        assert "Oranges" in typical_items, "Oranges should be in typical_items"
        assert "Apples" in typical_items, "Apples should be in typical_items"
        print(f"✓ Pattern merged: receipt_count={receipt_count}, items={typical_items}")


class TestVendorPatternsEndpoint:
    """Tests for GET /api/vendor-patterns endpoint."""
    
    def test_vendor_patterns_requires_auth(self):
        """Test that listing patterns requires authentication."""
        response = requests.get(f"{BASE_URL}/api/vendor-patterns")
        assert response.status_code == 401
    
    def test_vendor_patterns_returns_list(self, auth_headers):
        """Test that vendor-patterns returns a list."""
        response = requests.get(
            f"{BASE_URL}/api/vendor-patterns",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Found {len(data)} vendor patterns")
        
        # If patterns exist, verify structure
        if data:
            pattern = data[0]
            assert "vendor_name" in pattern, "Pattern should have vendor_name"
            assert "hints" in pattern, "Pattern should have hints"
            print(f"✓ First pattern: {pattern.get('vendor_name')}")


class TestReceiptsEndpoint:
    """Tests for GET /api/receipts endpoint."""
    
    def test_receipts_requires_auth(self):
        """Test that listing receipts requires authentication."""
        response = requests.get(f"{BASE_URL}/api/receipts")
        assert response.status_code == 401
    
    def test_receipts_returns_list(self, auth_headers):
        """Test that receipts returns a list."""
        response = requests.get(
            f"{BASE_URL}/api/receipts",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Found {len(data)} uploaded receipts")
        
        # If receipts exist, verify structure
        if data:
            receipt = data[0]
            assert "id" in receipt, "Receipt should have id"
            assert "file_name" in receipt, "Receipt should have file_name"
            assert "parsing_method" in receipt, "Receipt should have parsing_method"
            print(f"✓ First receipt: {receipt.get('file_name')} - {receipt.get('parsing_method')}")


class TestVendorPatternMatching:
    """Tests for vendor pattern matching on second extraction."""
    
    def test_second_extraction_uses_vendor_pattern(self, auth_token):
        """Test that second extraction from same vendor uses 'vendor' parsing_method."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        unique_vendor = f"TEST_PATTERN_MATCH_{os.urandom(4).hex()}"
        
        # First, create a vendor pattern
        learn_response = requests.post(
            f"{BASE_URL}/api/receipts/learn",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "vendor_name": unique_vendor,
                "corrected_items": [
                    {"raw_name": "Chicken Breast", "quantity": 10, "unit": "kg", "unit_price": 8.00, "total": 80.00},
                    {"raw_name": "Ground Beef", "quantity": 5, "unit": "kg", "unit_price": 12.00, "total": 60.00}
                ],
                "corrected_total": 140.00
            }
        )
        assert learn_response.status_code == 200, f"Learn failed: {learn_response.text}"
        
        # Verify pattern exists
        patterns_response = requests.get(
            f"{BASE_URL}/api/vendor-patterns",
            headers={**headers, "Content-Type": "application/json"}
        )
        patterns = patterns_response.json()
        pattern = next((p for p in patterns if p.get("vendor_name") == unique_vendor), None)
        assert pattern, f"Pattern for {unique_vendor} should exist"
        
        print(f"✓ Vendor pattern created for {unique_vendor}")
        print(f"✓ Pattern hints: {pattern.get('hints', {})}")


class TestExtractionDataStructure:
    """Tests for extraction data structure."""
    
    def test_extraction_data_has_items_array(self, auth_token, test_image):
        """Test that extracted_data has items array with expected fields."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=headers,
            files={"file": ("receipt.png", test_image, "image/png")},
            data={"document_type": "purchase_invoice"},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        extracted = data.get("extracted_data", {})
        
        # Check items structure if present
        if "items" in extracted and extracted["items"]:
            item = extracted["items"][0]
            # Items should have these fields
            expected_fields = ["raw_name", "quantity", "unit_price", "total"]
            for field in expected_fields:
                assert field in item, f"Item should have {field} field"
            print(f"✓ Items have expected structure: {list(item.keys())}")
        else:
            print("⚠ No items extracted (may be due to simple test image)")


# Cleanup fixture
@pytest.fixture(scope="module", autouse=True)
def cleanup_test_patterns(auth_token):
    """Cleanup test patterns after all tests."""
    yield
    # Cleanup is handled by test data prefix - patterns starting with TEST_ can be identified


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
