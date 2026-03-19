"""
Vendor Detail Page Feature Tests
Tests the new vendor detail endpoints: GET /suppliers/{sid}/detail and GET /suppliers/{sid}/purchases
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Authenticate and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_vendor(headers):
    """Get an existing vendor for testing"""
    response = requests.get(f"{BASE_URL}/api/suppliers", headers=headers)
    assert response.status_code == 200
    vendors = response.json()
    assert len(vendors) > 0, "No vendors in database for testing"
    # Return a vendor that has purchases (Sysco Restaurant Supply has 3 invoices)
    for v in vendors:
        if v.get("invoice_count", 0) > 0 or "Sysco" in v.get("name", ""):
            return v
    return vendors[0]


class TestVendorDetailEndpoint:
    """Tests for GET /api/suppliers/{sid}/detail"""
    
    def test_vendor_detail_returns_correct_data(self, headers, test_vendor):
        """Verify detail endpoint returns vendor info with total_spending and invoice_count"""
        response = requests.get(f"{BASE_URL}/api/suppliers/{test_vendor['id']}/detail", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        # Verify basic vendor fields
        assert data["id"] == test_vendor["id"]
        assert data["name"] == test_vendor["name"]
        assert "contact_person" in data
        assert "phone" in data
        
        # Verify computed fields
        assert "total_spending" in data
        assert "invoice_count" in data
        assert isinstance(data["total_spending"], (int, float))
        assert isinstance(data["invoice_count"], int)
        assert data["invoice_count"] >= 0
        assert data["total_spending"] >= 0
    
    def test_vendor_detail_not_found(self, headers):
        """Verify 404 for non-existent vendor"""
        response = requests.get(f"{BASE_URL}/api/suppliers/nonexistent-id-12345/detail", headers=headers)
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()
    
    def test_vendor_detail_requires_auth(self):
        """Verify authentication is required"""
        response = requests.get(f"{BASE_URL}/api/suppliers/any-id/detail")
        assert response.status_code == 401


class TestVendorPurchasesEndpoint:
    """Tests for GET /api/suppliers/{sid}/purchases"""
    
    def test_purchases_returns_sorted_list(self, headers, test_vendor):
        """Verify purchases are returned sorted by date descending"""
        response = requests.get(f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases", headers=headers)
        assert response.status_code == 200
        
        purchases = response.json()
        assert isinstance(purchases, list)
        
        # If there are multiple purchases, verify descending date order
        if len(purchases) >= 2:
            dates = [p.get("invoice_date", "") for p in purchases]
            assert dates == sorted(dates, reverse=True), "Purchases should be sorted by date descending"
    
    def test_purchases_have_required_fields(self, headers, test_vendor):
        """Verify each purchase has required fields for display"""
        response = requests.get(f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases", headers=headers)
        assert response.status_code == 200
        
        purchases = response.json()
        if len(purchases) > 0:
            p = purchases[0]
            # Required display fields
            assert "id" in p
            assert "invoice_date" in p
            assert "invoice_number" in p
            assert "total" in p
            assert "items" in p
            # Items should have line details for modal
            if p.get("items"):
                item = p["items"][0]
                assert "raw_name" in item
                assert "quantity" in item
                assert "unit_price" in item
                assert "total" in item
    
    def test_purchases_search_filter(self, headers, test_vendor):
        """Test invoice number search filter"""
        # First get all purchases
        response = requests.get(f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases", headers=headers)
        all_purchases = response.json()
        
        if len(all_purchases) > 0 and all_purchases[0].get("invoice_number"):
            inv_num = all_purchases[0]["invoice_number"]
            # Search for partial match
            search_term = inv_num[:5] if len(inv_num) > 5 else inv_num
            
            response = requests.get(
                f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases",
                params={"search": search_term},
                headers=headers
            )
            assert response.status_code == 200
            filtered = response.json()
            assert len(filtered) >= 1
            assert any(search_term in p.get("invoice_number", "") for p in filtered)
    
    def test_purchases_date_from_filter(self, headers, test_vendor):
        """Test date_from filter"""
        response = requests.get(
            f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases",
            params={"date_from": "2026-02-01"},
            headers=headers
        )
        assert response.status_code == 200
        purchases = response.json()
        
        # All returned purchases should have date >= 2026-02-01
        for p in purchases:
            assert p.get("invoice_date", "") >= "2026-02-01"
    
    def test_purchases_date_to_filter(self, headers, test_vendor):
        """Test date_to filter"""
        response = requests.get(
            f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases",
            params={"date_to": "2026-01-31"},
            headers=headers
        )
        assert response.status_code == 200
        purchases = response.json()
        
        # All returned purchases should have date <= 2026-01-31
        for p in purchases:
            assert p.get("invoice_date", "") <= "2026-01-31"
    
    def test_purchases_date_range_filter(self, headers, test_vendor):
        """Test combined date_from and date_to filter"""
        response = requests.get(
            f"{BASE_URL}/api/suppliers/{test_vendor['id']}/purchases",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
            headers=headers
        )
        assert response.status_code == 200
        purchases = response.json()
        
        for p in purchases:
            date = p.get("invoice_date", "")
            assert "2026-01-01" <= date <= "2026-01-31"
    
    def test_purchases_not_found_vendor(self, headers):
        """Verify 404 for purchases of non-existent vendor"""
        response = requests.get(
            f"{BASE_URL}/api/suppliers/nonexistent-vendor-id/purchases",
            headers=headers
        )
        assert response.status_code == 404
    
    def test_purchases_requires_auth(self):
        """Verify authentication is required"""
        response = requests.get(f"{BASE_URL}/api/suppliers/any-id/purchases")
        assert response.status_code == 401


class TestVendorDeletePurchase:
    """Test deleting a purchase from vendor detail view updates totals"""
    
    def test_delete_purchase_updates_vendor_totals(self, headers, test_vendor):
        """Create a purchase, delete it, verify vendor totals update"""
        vendor_id = test_vendor["id"]
        vendor_name = test_vendor["name"]
        
        # Get initial vendor detail
        response = requests.get(f"{BASE_URL}/api/suppliers/{vendor_id}/detail", headers=headers)
        initial = response.json()
        initial_spending = initial["total_spending"]
        initial_count = initial["invoice_count"]
        
        # Create a test purchase for this vendor
        new_purchase = {
            "supplier_name": vendor_name,
            "invoice_number": "TEST-VD-DELETE-001",
            "invoice_date": "2026-03-01",
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "ea", "unit_price": 100, "total": 100}],
            "subtotal": 100,
            "tax": 0,
            "total": 100
        }
        response = requests.post(f"{BASE_URL}/api/purchases", json=new_purchase, headers=headers)
        assert response.status_code == 200
        created_purchase = response.json()
        purchase_id = created_purchase["id"]
        
        # Verify vendor totals increased
        response = requests.get(f"{BASE_URL}/api/suppliers/{vendor_id}/detail", headers=headers)
        after_create = response.json()
        assert after_create["total_spending"] == initial_spending + 100
        assert after_create["invoice_count"] == initial_count + 1
        
        # Delete the purchase
        response = requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=headers)
        assert response.status_code == 200
        
        # Verify vendor totals returned to original
        response = requests.get(f"{BASE_URL}/api/suppliers/{vendor_id}/detail", headers=headers)
        after_delete = response.json()
        assert after_delete["total_spending"] == initial_spending
        assert after_delete["invoice_count"] == initial_count


class TestVendorListStillWorks:
    """Regression tests - ensure vendors list CRUD still works"""
    
    def test_vendors_list_shows_spending_and_count(self, headers):
        """Verify vendor list includes total_spending and invoice_count"""
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=headers)
        assert response.status_code == 200
        vendors = response.json()
        
        if len(vendors) > 0:
            v = vendors[0]
            assert "total_spending" in v
            assert "invoice_count" in v
    
    def test_create_edit_delete_vendor(self, headers):
        """Test full CRUD cycle still works"""
        # Create
        new_vendor = {
            "name": "TEST_VENDOR_CRUD_CHECK",
            "contact_person": "Test Contact",
            "phone": "555-0000",
            "email": "test@example.com",
            "address": "123 Test St"
        }
        response = requests.post(f"{BASE_URL}/api/suppliers", json=new_vendor, headers=headers)
        assert response.status_code == 200
        created = response.json()
        vendor_id = created["id"]
        assert created["name"] == "TEST_VENDOR_CRUD_CHECK"
        
        # Edit
        updated = {"name": "TEST_VENDOR_UPDATED", "contact_person": "Updated", "phone": "", "email": "", "address": ""}
        response = requests.put(f"{BASE_URL}/api/suppliers/{vendor_id}", json=updated, headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "TEST_VENDOR_UPDATED"
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/suppliers/{vendor_id}", headers=headers)
        assert response.status_code == 200


class TestEmptyVendorState:
    """Test vendor with no purchases"""
    
    def test_vendor_with_no_purchases(self, headers):
        """Create a vendor with no purchases, verify detail and purchases endpoints"""
        # Create new vendor
        new_vendor = {
            "name": "TEST_EMPTY_VENDOR_" + str(os.urandom(4).hex()),
            "contact_person": "",
            "phone": "",
            "email": "",
            "address": ""
        }
        response = requests.post(f"{BASE_URL}/api/suppliers", json=new_vendor, headers=headers)
        assert response.status_code == 200
        vendor = response.json()
        vendor_id = vendor["id"]
        
        try:
            # Detail should show 0 spending and 0 invoices
            response = requests.get(f"{BASE_URL}/api/suppliers/{vendor_id}/detail", headers=headers)
            assert response.status_code == 200
            detail = response.json()
            assert detail["total_spending"] == 0
            assert detail["invoice_count"] == 0
            
            # Purchases should return empty array
            response = requests.get(f"{BASE_URL}/api/suppliers/{vendor_id}/purchases", headers=headers)
            assert response.status_code == 200
            purchases = response.json()
            assert purchases == []
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/suppliers/{vendor_id}", headers=headers)
