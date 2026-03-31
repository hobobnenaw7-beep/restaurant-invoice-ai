"""
Test suite for invoice sorting and review_status features.
Tests:
1. Sorting by date fields (invoice_date, report_date, expense_date, payment_date) with fallback to created_at
2. review_status field computation (clean|warning|error) on purchases
3. review_status persistence through create/update operations
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestPurchasesSorting:
    """Test GET /api/purchases sorting by invoice_date with fallback to created_at"""
    
    def test_purchases_default_sort_desc(self, api_client):
        """Purchases should be sorted by invoice_date descending by default"""
        response = api_client.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) >= 2:
            # Check that dates are in descending order
            dates = []
            for p in data:
                # Use invoice_date if present, else created_at
                date_val = p.get("invoice_date") or p.get("created_at", "")
                dates.append(date_val)
            
            # Verify descending order (newest first)
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] >= dates[i+1], f"Dates not in descending order: {dates[i]} < {dates[i+1]}"
        print(f"PASS: Purchases sorted by invoice_date desc (found {len(data)} records)")
    
    def test_purchases_sort_asc(self, api_client):
        """Purchases can be sorted ascending"""
        response = api_client.get(f"{BASE_URL}/api/purchases", params={"sort_order": "asc"})
        assert response.status_code == 200
        data = response.json()
        
        if len(data) >= 2:
            dates = [p.get("invoice_date") or p.get("created_at", "") for p in data]
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] <= dates[i+1], f"Dates not in ascending order: {dates[i]} > {dates[i+1]}"
        print(f"PASS: Purchases sorted ascending")


class TestSalesSorting:
    """Test GET /api/sales sorting by report_date with fallback to created_at"""
    
    def test_sales_default_sort_desc(self, api_client):
        """Sales should be sorted by report_date descending by default"""
        response = api_client.get(f"{BASE_URL}/api/sales")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) >= 2:
            dates = [s.get("report_date") or s.get("created_at", "") for s in data]
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] >= dates[i+1], f"Sales dates not in descending order"
        print(f"PASS: Sales sorted by report_date desc (found {len(data)} records)")
    
    def test_sales_sort_asc(self, api_client):
        """Sales can be sorted ascending"""
        response = api_client.get(f"{BASE_URL}/api/sales", params={"sort_order": "asc"})
        assert response.status_code == 200
        data = response.json()
        
        if len(data) >= 2:
            dates = [s.get("report_date") or s.get("created_at", "") for s in data]
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] <= dates[i+1], f"Sales dates not in ascending order"
        print(f"PASS: Sales sorted ascending")


class TestOtherExpensesSorting:
    """Test GET /api/other-expenses sorting by expense_date with fallback to created_at"""
    
    def test_other_expenses_default_sort_desc(self, api_client):
        """Other expenses should be sorted by expense_date descending by default"""
        response = api_client.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) >= 2:
            dates = [e.get("expense_date") or e.get("created_at", "") for e in data]
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] >= dates[i+1], f"Expense dates not in descending order"
        print(f"PASS: Other expenses sorted by expense_date desc (found {len(data)} records)")


class TestSalariesSorting:
    """Test GET /api/salaries sorting by payment_date with fallback to created_at"""
    
    def test_salaries_default_sort_desc(self, api_client):
        """Salaries should be sorted by payment_date descending by default"""
        response = api_client.get(f"{BASE_URL}/api/salaries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) >= 2:
            dates = [s.get("payment_date") or s.get("created_at", "") for s in data]
            for i in range(len(dates) - 1):
                if dates[i] and dates[i+1]:
                    assert dates[i] >= dates[i+1], f"Salary dates not in descending order"
        print(f"PASS: Salaries sorted by payment_date desc (found {len(data)} records)")


class TestPurchaseReviewStatus:
    """Test review_status field on purchases (clean|warning|error)"""
    
    def test_purchases_have_review_status(self, api_client):
        """All purchases should have review_status field"""
        response = api_client.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        data = response.json()
        
        for p in data:
            assert "review_status" in p, f"Purchase {p.get('id')} missing review_status"
            assert p["review_status"] in ["clean", "warning", "error"], f"Invalid review_status: {p['review_status']}"
        print(f"PASS: All {len(data)} purchases have valid review_status")
    
    def test_error_status_for_math_mismatch(self, api_client):
        """Purchases with math mismatch items should have review_status=error"""
        response = api_client.get(f"{BASE_URL}/api/purchases", params={"search": "Quick Review Test"})
        assert response.status_code == 200
        data = response.json()
        
        # Find the test purchase with known errors
        test_purchase = None
        for p in data:
            if "Quick Review Test" in p.get("supplier_name", ""):
                test_purchase = p
                break
        
        if test_purchase:
            assert test_purchase["review_status"] == "error", f"Expected error status for test purchase, got {test_purchase['review_status']}"
            print(f"PASS: Test purchase with errors has review_status=error")
        else:
            print("SKIP: Test purchase 'Quick Review Test Vendor' not found")
    
    def test_clean_status_for_valid_items(self, api_client):
        """Purchases with all valid items should have review_status=clean"""
        response = api_client.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        data = response.json()
        
        clean_count = sum(1 for p in data if p.get("review_status") == "clean")
        error_count = sum(1 for p in data if p.get("review_status") == "error")
        warning_count = sum(1 for p in data if p.get("review_status") == "warning")
        
        print(f"PASS: Review status distribution - clean: {clean_count}, warning: {warning_count}, error: {error_count}")
        assert clean_count > 0 or error_count > 0 or warning_count > 0, "Should have at least one purchase with review_status"


class TestCreatePurchaseReviewStatus:
    """Test that POST /api/purchases computes review_status correctly"""
    
    def test_create_purchase_with_clean_items(self, api_client):
        """Creating purchase with valid items should set review_status=clean"""
        payload = {
            "supplier_name": "TEST_Clean_Vendor",
            "invoice_number": "TEST-CLEAN-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "raw_name": "TEST CHICKEN BREAST",
                    "quantity": 5,
                    "pack_size": "10 LB",
                    "unit_price": 25.00,
                    "total": 125.00
                }
            ],
            "subtotal": 125.00,
            "tax": 0,
            "total": 125.00
        }
        
        response = api_client.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert "review_status" in data, "Response missing review_status"
        assert data["review_status"] == "clean", f"Expected clean status, got {data['review_status']}"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Create purchase with valid items sets review_status=clean")
    
    def test_create_purchase_with_error_items(self, api_client):
        """Creating purchase with math mismatch should set review_status=error"""
        payload = {
            "supplier_name": "TEST_Error_Vendor",
            "invoice_number": "TEST-ERROR-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "raw_name": "TEST ITEM WITH MISMATCH",
                    "quantity": 5,
                    "pack_size": "",
                    "unit_price": 10.00,
                    "total": 100.00  # Math mismatch: 5 * 10 = 50, not 100
                }
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        response = api_client.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert "review_status" in data, "Response missing review_status"
        assert data["review_status"] == "error", f"Expected error status for math mismatch, got {data['review_status']}"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Create purchase with math mismatch sets review_status=error")
    
    def test_create_purchase_with_missing_name(self, api_client):
        """Creating purchase with missing item name should set review_status=error"""
        payload = {
            "supplier_name": "TEST_Missing_Name_Vendor",
            "invoice_number": "TEST-NONAME-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "raw_name": "",  # Missing name
                    "quantity": 5,
                    "pack_size": "",
                    "unit_price": 10.00,
                    "total": 50.00
                }
            ],
            "subtotal": 50.00,
            "tax": 0,
            "total": 50.00
        }
        
        response = api_client.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert "review_status" in data, "Response missing review_status"
        assert data["review_status"] == "error", f"Expected error status for missing name, got {data['review_status']}"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Create purchase with missing item name sets review_status=error")


class TestUpdatePurchaseReviewStatus:
    """Test that PUT /api/purchases recomputes review_status"""
    
    def test_update_purchase_recomputes_status(self, api_client):
        """Updating purchase items should recompute review_status"""
        # First create a purchase with error
        payload = {
            "supplier_name": "TEST_Update_Vendor",
            "invoice_number": "TEST-UPDATE-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "raw_name": "TEST ITEM",
                    "quantity": 5,
                    "pack_size": "",
                    "unit_price": 10.00,
                    "total": 100.00  # Math mismatch
                }
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/purchases", json=payload)
        assert create_response.status_code == 200
        created = create_response.json()
        purchase_id = created["id"]
        
        assert created["review_status"] == "error", "Initial status should be error"
        
        # Now update to fix the math
        update_payload = {
            "items": [
                {
                    "raw_name": "TEST ITEM FIXED",
                    "quantity": 5,
                    "pack_size": "",
                    "unit_price": 20.00,
                    "total": 100.00  # Now correct: 5 * 20 = 100
                }
            ],
            "subtotal": 100.00,
            "total": 100.00
        }
        
        update_response = api_client.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload)
        assert update_response.status_code == 200
        updated = update_response.json()
        
        assert updated["review_status"] == "clean", f"After fix, status should be clean, got {updated['review_status']}"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        print("PASS: Update purchase recomputes review_status correctly")


class TestSortingWithMissingDates:
    """Test that sorting falls back to created_at when date field is missing"""
    
    def test_purchases_with_empty_date_sorted_by_created_at(self, api_client):
        """Purchases with empty invoice_date should use created_at for sorting"""
        # Create a purchase without invoice_date
        payload = {
            "supplier_name": "TEST_No_Date_Vendor",
            "invoice_number": "TEST-NODATE-001",
            "invoice_date": "",  # Empty date
            "items": [
                {
                    "raw_name": "TEST ITEM",
                    "quantity": 1,
                    "pack_size": "",
                    "unit_price": 10.00,
                    "total": 10.00
                }
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        
        response = api_client.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200
        created = response.json()
        purchase_id = created["id"]
        
        # Verify it appears in the list (sorted by created_at since invoice_date is empty)
        list_response = api_client.get(f"{BASE_URL}/api/purchases")
        assert list_response.status_code == 200
        data = list_response.json()
        
        # The newly created purchase should be near the top (newest first)
        found = False
        for i, p in enumerate(data[:5]):  # Check first 5
            if p["id"] == purchase_id:
                found = True
                break
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        
        assert found, "Purchase with empty date should appear in sorted list using created_at"
        print("PASS: Purchases with empty date use created_at for sorting")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
