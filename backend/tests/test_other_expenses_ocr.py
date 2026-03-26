"""
Test Other Expenses Tab with OCR/Upload Support
Tests the new subcategories (Utilities, Taxes, Maintenance & Repairs, Software & Subscriptions, Services, Rent / Facility, Miscellaneous)
and the OCR extraction for other_expense document_type.
"""
import pytest
import requests
import os
import base64
from io import BytesIO
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# The 7 subcategories for Other Expenses
OTHER_CATEGORIES = ['Utilities', 'Taxes', 'Maintenance & Repairs', 'Software & Subscriptions', 'Services', 'Rent / Facility', 'Miscellaneous']


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for testing."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


def create_test_image_with_text(text_lines):
    """Create a simple test image with text for OCR testing."""
    img = Image.new('RGB', (400, 300), color='white')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    y_position = 20
    for line in text_lines:
        draw.text((20, y_position), line, fill='black')
        y_position += 30
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


class TestOtherExpensesAPI:
    """Test Other Expenses CRUD API endpoints."""

    def test_get_other_expenses_requires_auth(self):
        """GET /api/other-expenses requires authentication."""
        response = requests.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /api/other-expenses returns 401 without auth")

    def test_get_other_expenses_returns_list(self, auth_headers):
        """GET /api/other-expenses returns a list."""
        response = requests.get(f"{BASE_URL}/api/other-expenses", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: GET /api/other-expenses returns list with {len(data)} items")

    def test_create_other_expense_with_new_category(self, auth_headers):
        """POST /api/other-expenses creates record with new subcategory."""
        for category in OTHER_CATEGORIES:
            payload = {
                "title": f"TEST_{category}_Expense",
                "category": category,
                "amount": 100.50,
                "expense_date": "2026-03-15",
                "notes": f"Test expense for {category}"
            }
            response = requests.post(f"{BASE_URL}/api/other-expenses", json=payload, headers=auth_headers)
            assert response.status_code == 200, f"Failed to create expense with category {category}: {response.text}"
            data = response.json()
            assert data.get("category") == category, f"Expected category {category}, got {data.get('category')}"
            assert data.get("title") == f"TEST_{category}_Expense"
            assert data.get("amount") == 100.50
            assert "id" in data, "Response should contain id"
            print(f"PASS: Created expense with category '{category}'")

    def test_get_other_expenses_filter_by_category(self, auth_headers):
        """GET /api/other-expenses?category=X filters by category."""
        # First get all expenses
        response = requests.get(f"{BASE_URL}/api/other-expenses", headers=auth_headers)
        assert response.status_code == 200
        all_expenses = response.json()
        
        # Filter by Utilities
        response = requests.get(f"{BASE_URL}/api/other-expenses?category=Utilities", headers=auth_headers)
        assert response.status_code == 200
        filtered = response.json()
        
        # All filtered items should have category=Utilities
        for item in filtered:
            assert item.get("category") == "Utilities", f"Expected Utilities, got {item.get('category')}"
        
        print(f"PASS: Category filter works - {len(filtered)} Utilities expenses out of {len(all_expenses)} total")

    def test_update_other_expense(self, auth_headers):
        """PUT /api/other-expenses/{id} updates record."""
        # Create a test expense
        payload = {
            "title": "TEST_Update_Expense",
            "category": "Miscellaneous",
            "amount": 50.00,
            "expense_date": "2026-03-10",
            "notes": "Original notes"
        }
        create_response = requests.post(f"{BASE_URL}/api/other-expenses", json=payload, headers=auth_headers)
        assert create_response.status_code == 200
        expense_id = create_response.json().get("id")
        
        # Update the expense
        update_payload = {
            "title": "TEST_Updated_Expense",
            "category": "Taxes",
            "amount": 75.00,
            "notes": "Updated notes"
        }
        update_response = requests.put(f"{BASE_URL}/api/other-expenses/{expense_id}", json=update_payload, headers=auth_headers)
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated.get("title") == "TEST_Updated_Expense"
        assert updated.get("category") == "Taxes"
        assert updated.get("amount") == 75.00
        print("PASS: PUT /api/other-expenses/{id} updates record correctly")

    def test_delete_other_expense(self, auth_headers):
        """DELETE /api/other-expenses/{id} deletes record."""
        # Create a test expense
        payload = {
            "title": "TEST_Delete_Expense",
            "category": "Services",
            "amount": 25.00,
            "expense_date": "2026-03-05",
            "notes": "To be deleted"
        }
        create_response = requests.post(f"{BASE_URL}/api/other-expenses", json=payload, headers=auth_headers)
        assert create_response.status_code == 200
        expense_id = create_response.json().get("id")
        
        # Delete the expense
        delete_response = requests.delete(f"{BASE_URL}/api/other-expenses/{expense_id}", headers=auth_headers)
        assert delete_response.status_code == 200
        assert delete_response.json().get("status") == "deleted"
        
        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/other-expenses", headers=auth_headers)
        expenses = get_response.json()
        ids = [e.get("id") for e in expenses]
        assert expense_id not in ids, "Deleted expense should not appear in list"
        print("PASS: DELETE /api/other-expenses/{id} removes record")


class TestOtherExpenseOCRExtraction:
    """Test OCR extraction for other_expense document_type."""

    def test_extract_requires_auth(self):
        """POST /api/upload/extract requires authentication."""
        response = requests.post(f"{BASE_URL}/api/upload/extract")
        assert response.status_code in [401, 422], f"Expected 401 or 422, got {response.status_code}"
        print("PASS: POST /api/upload/extract requires auth")

    def test_extract_other_expense_returns_expected_fields(self, auth_headers):
        """POST /api/upload/extract with document_type=other_expense returns category from 7 subcategories."""
        # Create a test image with utility bill text
        text_lines = [
            "Electric Company Inc.",
            "Account: 12345678",
            "Bill Date: March 15, 2026",
            "Amount Due: $150.00",
            "Service: Electricity"
        ]
        img_buffer = create_test_image_with_text(text_lines)
        
        files = {'file': ('test_bill.png', img_buffer, 'image/png')}
        data = {'document_type': 'other_expense'}
        
        # Remove Content-Type from headers for multipart
        headers = {"Authorization": auth_headers["Authorization"]}
        
        response = requests.post(f"{BASE_URL}/api/upload/extract", files=files, data=data, headers=headers, timeout=60)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        result = response.json()
        assert "extracted_data" in result, "Response should contain extracted_data"
        
        extracted = result.get("extracted_data", {})
        # Check that category is one of the 7 subcategories
        category = extracted.get("category", "")
        assert category in OTHER_CATEGORIES or category == "", f"Category '{category}' should be one of {OTHER_CATEGORIES}"
        
        # Check other expected fields
        assert "title" in extracted, "extracted_data should have title"
        assert "amount" in extracted, "extracted_data should have amount"
        assert "expense_date" in extracted, "extracted_data should have expense_date"
        
        print(f"PASS: OCR extraction returns category='{category}' and expected fields")
        print(f"  - title: {extracted.get('title')}")
        print(f"  - amount: {extracted.get('amount')}")
        print(f"  - expense_date: {extracted.get('expense_date')}")

    def test_extract_returns_receipt_id_and_parsing_method(self, auth_headers):
        """POST /api/upload/extract returns receipt_id and parsing_method."""
        text_lines = [
            "Tax Payment Receipt",
            "Date: March 20, 2026",
            "Amount: $500.00",
            "Reference: TAX-2026-001"
        ]
        img_buffer = create_test_image_with_text(text_lines)
        
        files = {'file': ('tax_receipt.png', img_buffer, 'image/png')}
        data = {'document_type': 'other_expense'}
        headers = {"Authorization": auth_headers["Authorization"]}
        
        response = requests.post(f"{BASE_URL}/api/upload/extract", files=files, data=data, headers=headers, timeout=60)
        assert response.status_code == 200
        
        result = response.json()
        assert "receipt_id" in result, "Response should contain receipt_id"
        assert "parsing_method" in result, "Response should contain parsing_method"
        assert result.get("parsing_method") in ["general", "vendor"], f"parsing_method should be 'general' or 'vendor'"
        
        print(f"PASS: OCR returns receipt_id={result.get('receipt_id')[:8]}... and parsing_method={result.get('parsing_method')}")


class TestCleanup:
    """Cleanup test data."""

    def test_cleanup_test_expenses(self, auth_headers):
        """Remove TEST_ prefixed expenses."""
        response = requests.get(f"{BASE_URL}/api/other-expenses", headers=auth_headers)
        if response.status_code == 200:
            expenses = response.json()
            deleted_count = 0
            for expense in expenses:
                if expense.get("title", "").startswith("TEST_"):
                    delete_response = requests.delete(f"{BASE_URL}/api/other-expenses/{expense['id']}", headers=auth_headers)
                    if delete_response.status_code == 200:
                        deleted_count += 1
            print(f"PASS: Cleaned up {deleted_count} test expenses")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
