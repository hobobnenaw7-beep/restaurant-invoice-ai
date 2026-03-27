"""
Test Multi-Image Upload Flow
Tests the backend's ability to handle multiple files in the /upload/extract endpoint
"""
import pytest
import requests
import os
import io
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}"
    }


def create_test_image(text="Test Image", color=(255, 200, 150), size=(200, 100)):
    """Create a simple test image with text"""
    img = Image.new('RGB', size, color=color)
    # Add some visual features (simple gradient)
    for x in range(size[0]):
        for y in range(size[1]):
            r = int(color[0] * (1 - x/size[0]))
            g = int(color[1] * (1 - y/size[1]))
            b = color[2]
            img.putpixel((x, y), (r, g, b))
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


class TestMultiImageUploadBackend:
    """Backend tests for multi-image upload functionality"""
    
    def test_extract_requires_auth(self):
        """Test that /upload/extract requires authentication"""
        img = create_test_image("Page 1")
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            files=[("files", ("test1.png", img, "image/png"))],
            data={"document_type": "purchase_invoice"}
        )
        assert response.status_code in [401, 422], f"Expected 401/422, got {response.status_code}"
        print("PASS: /upload/extract requires authentication")
    
    def test_extract_single_file_with_files_key(self, auth_headers):
        """Test extraction with single file using 'files' key (multi-file format)"""
        img = create_test_image("Invoice Page 1", color=(255, 220, 180))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[("files", ("invoice1.png", img, "image/png"))],
            data={"document_type": "purchase_invoice"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Single file with 'files' key returns 200 with extracted_data")
        print(f"  - Keys in response: {list(data.keys())}")
    
    def test_extract_single_file_with_file_key(self, auth_headers):
        """Test extraction with single file using 'file' key (backward compat)"""
        img = create_test_image("Invoice Page 1", color=(180, 220, 255))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[("file", ("invoice1.png", img, "image/png"))],
            data={"document_type": "purchase_invoice"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Single file with 'file' key returns 200 (backward compat)")
    
    def test_extract_multiple_files(self, auth_headers):
        """Test extraction with multiple files using 'files' key"""
        img1 = create_test_image("Invoice Page 1", color=(255, 200, 150))
        img2 = create_test_image("Invoice Page 2", color=(150, 200, 255))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[
                ("files", ("page1.png", img1, "image/png")),
                ("files", ("page2.png", img2, "image/png"))
            ],
            data={"document_type": "purchase_invoice"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Multiple files with 'files' key returns 200")
        print(f"  - Response keys: {list(data.keys())}")
    
    def test_extract_three_files(self, auth_headers):
        """Test extraction with three files"""
        img1 = create_test_image("Page 1", color=(255, 180, 180))
        img2 = create_test_image("Page 2", color=(180, 255, 180))
        img3 = create_test_image("Page 3", color=(180, 180, 255))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[
                ("files", ("page1.png", img1, "image/png")),
                ("files", ("page2.png", img2, "image/png")),
                ("files", ("page3.png", img3, "image/png"))
            ],
            data={"document_type": "purchase_invoice"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Three files extraction returns 200")
    
    def test_extract_sales_report_multi_file(self, auth_headers):
        """Test multi-file extraction for sales_report document type"""
        img1 = create_test_image("Sales Page 1", color=(200, 255, 200))
        img2 = create_test_image("Sales Page 2", color=(200, 200, 255))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[
                ("files", ("sales1.png", img1, "image/png")),
                ("files", ("sales2.png", img2, "image/png"))
            ],
            data={"document_type": "sales_report"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Multi-file sales_report extraction returns 200")
    
    def test_extract_other_expense_multi_file(self, auth_headers):
        """Test multi-file extraction for other_expense document type"""
        img1 = create_test_image("Expense Page 1", color=(255, 255, 200))
        img2 = create_test_image("Expense Page 2", color=(255, 200, 255))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[
                ("files", ("expense1.png", img1, "image/png")),
                ("files", ("expense2.png", img2, "image/png"))
            ],
            data={"document_type": "other_expense"},
            timeout=90
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "extracted_data" in data, "Response should contain extracted_data"
        print(f"PASS: Multi-file other_expense extraction returns 200")
    
    def test_extract_returns_expected_structure(self, auth_headers):
        """Test that extraction returns expected data structure for purchase_invoice"""
        img = create_test_image("Invoice", color=(255, 230, 200))
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=[("files", ("invoice.png", img, "image/png"))],
            data={"document_type": "purchase_invoice"},
            timeout=90
        )
        
        assert response.status_code == 200
        data = response.json()
        extracted = data.get("extracted_data", {})
        
        # Check expected fields for purchase_invoice
        expected_fields = ["supplier_name", "invoice_date", "items", "subtotal", "tax", "total"]
        for field in expected_fields:
            assert field in extracted, f"Missing field: {field}"
        
        # Items should be a list
        assert isinstance(extracted.get("items"), list), "items should be a list"
        
        print(f"PASS: Extraction returns expected structure")
        print(f"  - Fields: {list(extracted.keys())}")
    
    def test_no_files_returns_error(self, auth_headers):
        """Test that no files returns an error"""
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            data={"document_type": "purchase_invoice"},
            timeout=30
        )
        
        # Should return 400 or 422 for missing files
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        print(f"PASS: No files returns error ({response.status_code})")


class TestManualEntryWithoutUpload:
    """Test that manual entry without upload still works"""
    
    def test_create_purchase_without_upload(self, auth_headers):
        """Test creating a purchase record without any file upload"""
        payload = {
            "supplier_name": "TEST_Manual_Vendor",
            "invoice_number": "TEST-MANUAL-001",
            "invoice_date": "2026-01-15",
            "items": [
                {"raw_name": "Test Item", "quantity": 5, "unit": "kg", "unit_price": 10.00, "total": 50.00}
            ],
            "subtotal": 50.00,
            "tax": 5.00,
            "total": 55.00
        }
        
        response = requests.post(
            f"{BASE_URL}/api/purchases",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        
        # Cleanup
        purchase_id = data["id"]
        requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        
        print(f"PASS: Manual purchase entry works without upload")
    
    def test_create_sale_without_upload(self, auth_headers):
        """Test creating a sale record without any file upload"""
        payload = {
            "date_from": "2026-01-15",
            "date_to": "2026-01-15",
            "total_sales": 500.00,
            "items": [
                {"menu_item": "Test Dish", "quantity": 10, "revenue": 500.00}
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/sales",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        
        # Cleanup
        sale_id = data["id"]
        requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        
        print(f"PASS: Manual sale entry works without upload")
    
    def test_create_other_expense_without_upload(self, auth_headers):
        """Test creating an other expense record without any file upload"""
        payload = {
            "title": "TEST_Manual_Expense",
            "category": "Utilities",
            "amount": 150.00,
            "expense_date": "2026-01-15",
            "notes": "Test manual entry"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/other-expenses",
            headers={**auth_headers, "Content-Type": "application/json"},
            json=payload
        )
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        
        # Cleanup
        expense_id = data["id"]
        requests.delete(f"{BASE_URL}/api/other-expenses/{expense_id}", headers=auth_headers)
        
        print(f"PASS: Manual other expense entry works without upload")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
