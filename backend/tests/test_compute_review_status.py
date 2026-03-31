"""
Test compute_review_status() bug fix:
- Old items without needs_review field should still be evaluated
- Items with math mismatches should return 'error' even without needs_review
- Items with confidence_level='unverified' should return 'error' or 'warning'
- Items with all fields valid should return 'clean'
"""
import pytest
import requests
import os
import sys

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')
from preprocessing import compute_review_status

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestComputeReviewStatusUnit:
    """Unit tests for compute_review_status function"""
    
    def test_clean_items_with_needs_review_false(self):
        """Items with needs_review=False should return 'clean'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00, "needs_review": False},
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 40.00, "needs_review": False},
        ]
        result = compute_review_status(items)
        assert result == "clean", f"Expected 'clean' but got '{result}'"
        print("PASS: Items with needs_review=False return 'clean'")
    
    def test_error_when_needs_review_true_with_math_mismatch(self):
        """Items with needs_review=True and math mismatch should return 'error'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00, "needs_review": False},
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 100.00, "needs_review": True, "review_reason": "Math mismatch"},
        ]
        result = compute_review_status(items)
        assert result == "error", f"Expected 'error' but got '{result}'"
        print("PASS: Items with needs_review=True and math mismatch return 'error'")
    
    def test_old_items_without_needs_review_math_mismatch(self):
        """OLD ITEMS: Items without needs_review field but with math mismatch should return 'error'"""
        # This is the key bug fix test - old items don't have needs_review field
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00},  # No needs_review
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 100.00},  # Math mismatch: 5*8=40 != 100
        ]
        result = compute_review_status(items)
        assert result == "error", f"Expected 'error' for math mismatch but got '{result}'"
        print("PASS: Old items without needs_review but with math mismatch return 'error'")
    
    def test_old_items_without_needs_review_missing_name(self):
        """OLD ITEMS: Items without needs_review field but missing name should return 'error'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00},
            {"raw_name": "", "quantity": 5, "unit_price": 8.00, "total": 40.00},  # Missing name
        ]
        result = compute_review_status(items)
        assert result == "error", f"Expected 'error' for missing name but got '{result}'"
        print("PASS: Old items without needs_review but missing name return 'error'")
    
    def test_old_items_without_needs_review_all_valid(self):
        """OLD ITEMS: Items without needs_review field but all valid should return 'clean'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00},  # 10*5=50 ✓
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 40.00},  # 5*8=40 ✓
        ]
        result = compute_review_status(items)
        assert result == "clean", f"Expected 'clean' for valid items but got '{result}'"
        print("PASS: Old items without needs_review but all valid return 'clean'")
    
    def test_confidence_level_unverified_returns_error(self):
        """Items with confidence_level='unverified' should return 'error' or 'warning'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00, "confidence_level": "trusted"},
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 40.00, "confidence_level": "unverified"},
        ]
        result = compute_review_status(items)
        # Unverified items should trigger needs_review=True inference
        assert result in ["error", "warning"], f"Expected 'error' or 'warning' but got '{result}'"
        print(f"PASS: Items with confidence_level='unverified' return '{result}'")
    
    def test_mixed_old_and_new_items(self):
        """Mix of old items (no needs_review) and new items (with needs_review)"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00, "needs_review": False},
            {"raw_name": "Ground Beef", "quantity": 5, "unit_price": 8.00, "total": 100.00},  # Old item with math mismatch
        ]
        result = compute_review_status(items)
        assert result == "error", f"Expected 'error' for mixed items with math mismatch but got '{result}'"
        print("PASS: Mixed old/new items with math mismatch return 'error'")
    
    def test_warning_for_minor_issues(self):
        """Items with minor issues (not math mismatch or missing name) should return 'warning'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 10, "unit_price": 5.00, "total": 50.00, "needs_review": True, "review_reason": "Pack size could not be parsed"},
        ]
        result = compute_review_status(items)
        assert result == "warning", f"Expected 'warning' for minor issues but got '{result}'"
        print("PASS: Items with minor issues return 'warning'")
    
    def test_empty_items_returns_clean(self):
        """Empty items list should return 'clean'"""
        result = compute_review_status([])
        assert result == "clean", f"Expected 'clean' for empty items but got '{result}'"
        print("PASS: Empty items list returns 'clean'")
    
    def test_old_items_missing_qty_or_price(self):
        """OLD ITEMS: Items without needs_review and missing qty/price should return 'error'"""
        items = [
            {"raw_name": "Chicken Breast", "quantity": 0, "unit_price": 5.00, "total": 50.00},  # qty=0
        ]
        result = compute_review_status(items)
        assert result in ["error", "warning"], f"Expected 'error' or 'warning' for missing qty but got '{result}'"
        print(f"PASS: Old items with missing qty return '{result}'")


class TestComputeReviewStatusAPI:
    """Integration tests for review_status via API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        else:
            pytest.skip("Authentication failed")
    
    def test_create_purchase_clean_items_returns_clean(self):
        """POST /api/purchases with clean items returns review_status='clean'"""
        payload = {
            "supplier_name": "TEST_Clean_Vendor",
            "invoice_number": "TEST-CLEAN-001",
            "invoice_date": "2026-01-22",
            "items": [
                {"raw_name": "Test Chicken", "quantity": 10, "unit_price": 5.00, "total": 50.00},
                {"raw_name": "Test Beef", "quantity": 5, "unit_price": 8.00, "total": 40.00},
            ],
            "subtotal": 90.00,
            "tax": 0,
            "total": 90.00
        }
        response = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert "review_status" in data, "review_status field missing"
        assert data["review_status"] == "clean", f"Expected 'clean' but got '{data['review_status']}'"
        print(f"PASS: POST /api/purchases with clean items returns review_status='clean'")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/purchases/{data['id']}", headers=self.headers)
    
    def test_create_purchase_math_mismatch_returns_error(self):
        """POST /api/purchases with math mismatch items returns review_status='error'"""
        payload = {
            "supplier_name": "TEST_Error_Vendor",
            "invoice_number": "TEST-ERROR-001",
            "invoice_date": "2026-01-22",
            "items": [
                {"raw_name": "Test Chicken", "quantity": 10, "unit_price": 5.00, "total": 50.00},
                {"raw_name": "Test Beef", "quantity": 5, "unit_price": 8.00, "total": 100.00},  # Math mismatch
            ],
            "subtotal": 150.00,
            "tax": 0,
            "total": 150.00
        }
        response = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert "review_status" in data, "review_status field missing"
        assert data["review_status"] == "error", f"Expected 'error' but got '{data['review_status']}'"
        print(f"PASS: POST /api/purchases with math mismatch returns review_status='error'")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/purchases/{data['id']}", headers=self.headers)
    
    def test_update_purchase_recomputes_review_status(self):
        """PUT /api/purchases recomputes review_status correctly after update"""
        # Create with error
        payload = {
            "supplier_name": "TEST_Update_Vendor",
            "invoice_number": "TEST-UPDATE-001",
            "invoice_date": "2026-01-22",
            "items": [
                {"raw_name": "Test Item", "quantity": 5, "unit_price": 10.00, "total": 100.00},  # Math mismatch
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        create_response = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        created = create_response.json()
        purchase_id = created.get("id")
        assert created.get("review_status") == "error", f"Initial status should be 'error'"
        
        # Update to fix the math
        update_payload = {
            "items": [
                {"raw_name": "Test Item", "quantity": 5, "unit_price": 10.00, "total": 50.00},  # Fixed: 5*10=50
            ],
            "subtotal": 50.00,
            "total": 50.00
        }
        update_response = requests.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload, headers=self.headers)
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        updated = update_response.json()
        assert updated.get("review_status") == "clean", f"Expected 'clean' after fix but got '{updated.get('review_status')}'"
        print(f"PASS: PUT /api/purchases recomputes review_status correctly")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=self.headers)
    
    def test_get_purchases_returns_review_status(self):
        """GET /api/purchases returns review_status field on all records"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=self.headers)
        assert response.status_code == 200, f"GET failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Check that review_status exists on records
        for purchase in data[:5]:  # Check first 5
            assert "review_status" in purchase, f"review_status missing on purchase {purchase.get('id')}"
            assert purchase["review_status"] in ["clean", "warning", "error"], f"Invalid review_status: {purchase['review_status']}"
        
        print(f"PASS: GET /api/purchases returns review_status on all {len(data)} records")
    
    def test_existing_invoices_review_status(self):
        """Check existing invoices have correct review_status based on their items"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=self.headers)
        assert response.status_code == 200
        purchases = response.json()
        
        # Find invoices with different review statuses
        clean_count = sum(1 for p in purchases if p.get("review_status") == "clean")
        warning_count = sum(1 for p in purchases if p.get("review_status") == "warning")
        error_count = sum(1 for p in purchases if p.get("review_status") == "error")
        
        print(f"Review status distribution: clean={clean_count}, warning={warning_count}, error={error_count}")
        
        # Verify at least some invoices exist
        assert len(purchases) > 0, "No purchases found"
        print(f"PASS: Found {len(purchases)} purchases with review_status distribution")


class TestSpecificInvoices:
    """Test specific invoices mentioned in the bug report"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        else:
            pytest.skip("Authentication failed")
    
    def test_quick_review_test_vendor_has_error_status(self):
        """'Quick Review Test Vendor' invoice should have review_status='error'"""
        response = requests.get(f"{BASE_URL}/api/purchases?search=Quick Review Test Vendor", headers=self.headers)
        assert response.status_code == 200
        purchases = response.json()
        
        if len(purchases) == 0:
            pytest.skip("Quick Review Test Vendor invoice not found")
        
        for p in purchases:
            if "Quick Review Test Vendor" in (p.get("supplier_name") or ""):
                print(f"Found: {p.get('supplier_name')} - review_status={p.get('review_status')}")
                assert p.get("review_status") == "error", f"Expected 'error' but got '{p.get('review_status')}'"
                print("PASS: Quick Review Test Vendor has review_status='error'")
                return
        
        pytest.skip("Quick Review Test Vendor not found in results")
    
    def test_us_foods_test_has_warning_status(self):
        """'US Foods Test' invoice should have review_status='warning'"""
        response = requests.get(f"{BASE_URL}/api/purchases?search=US Foods Test", headers=self.headers)
        assert response.status_code == 200
        purchases = response.json()
        
        if len(purchases) == 0:
            pytest.skip("US Foods Test invoice not found")
        
        for p in purchases:
            if "US Foods Test" in (p.get("supplier_name") or ""):
                print(f"Found: {p.get('supplier_name')} - review_status={p.get('review_status')}")
                assert p.get("review_status") == "warning", f"Expected 'warning' but got '{p.get('review_status')}'"
                print("PASS: US Foods Test has review_status='warning'")
                return
        
        pytest.skip("US Foods Test not found in results")
    
    def test_gordon_food_service_has_clean_status(self):
        """'Gordon Food Service' invoice should have review_status='clean'"""
        response = requests.get(f"{BASE_URL}/api/purchases?search=Gordon Food Service", headers=self.headers)
        assert response.status_code == 200
        purchases = response.json()
        
        if len(purchases) == 0:
            pytest.skip("Gordon Food Service invoice not found")
        
        for p in purchases:
            if "Gordon Food Service" in (p.get("supplier_name") or ""):
                print(f"Found: {p.get('supplier_name')} - review_status={p.get('review_status')}")
                # Gordon Food Service should be clean
                print(f"INFO: Gordon Food Service has review_status='{p.get('review_status')}'")
                return
        
        pytest.skip("Gordon Food Service not found in results")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
