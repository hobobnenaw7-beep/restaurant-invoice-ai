"""
Quick Review Feature Tests
Tests for needs_review, review_reason, and confidence_level fields on purchase items
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://invoice-ai-35.preview.emergentagent.com').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestQuickReviewBackend:
    """Backend API tests for Quick Review feature"""
    
    def test_get_purchases_returns_review_fields(self, auth_headers):
        """Test that GET /api/purchases returns needs_review and review_reason fields"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        
        purchases = response.json()
        assert len(purchases) > 0, "No purchases found"
        
        # Find the Quick Review Test Vendor invoice
        test_invoice = None
        for p in purchases:
            if "Quick Review Test" in p.get("supplier_name", ""):
                test_invoice = p
                break
        
        assert test_invoice is not None, "Quick Review Test Vendor invoice not found"
        
        items = test_invoice.get("items", [])
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"
        
        # Check that items have review fields
        for item in items:
            assert "needs_review" in item, f"Item missing needs_review field: {item.get('raw_name')}"
            assert "confidence_level" in item, f"Item missing confidence_level field: {item.get('raw_name')}"
    
    def test_trusted_items_have_correct_flags(self, auth_headers):
        """Test that trusted items have needs_review=False"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        
        purchases = response.json()
        test_invoice = next((p for p in purchases if "Quick Review Test" in p.get("supplier_name", "")), None)
        assert test_invoice is not None
        
        items = test_invoice.get("items", [])
        
        # CHICKEN BREAST BNLS should be trusted
        chicken = next((it for it in items if "CHICKEN" in (it.get("raw_name") or "").upper()), None)
        assert chicken is not None, "CHICKEN BREAST BNLS not found"
        assert chicken.get("needs_review") == False, "CHICKEN BREAST BNLS should not need review"
        assert chicken.get("confidence_level") == "trusted", "CHICKEN BREAST BNLS should be trusted"
        assert chicken.get("review_reason") is None, "Trusted item should have no review_reason"
        
        # OLIVE OIL EXTRA VIRGIN should be trusted
        olive = next((it for it in items if "OLIVE" in (it.get("raw_name") or "").upper()), None)
        assert olive is not None, "OLIVE OIL EXTRA VIRGIN not found"
        assert olive.get("needs_review") == False, "OLIVE OIL should not need review"
        assert olive.get("confidence_level") == "trusted", "OLIVE OIL should be trusted"
    
    def test_flagged_items_have_correct_flags(self, auth_headers):
        """Test that flagged items have needs_review=True and review_reason"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        
        purchases = response.json()
        test_invoice = next((p for p in purchases if "Quick Review Test" in p.get("supplier_name", "")), None)
        assert test_invoice is not None
        
        items = test_invoice.get("items", [])
        
        # SHRIMP 31-35 should need review (math mismatch)
        shrimp = next((it for it in items if "SHRIMP" in (it.get("raw_name") or "").upper()), None)
        assert shrimp is not None, "SHRIMP 31-35 not found"
        assert shrimp.get("needs_review") == True, "SHRIMP should need review"
        assert shrimp.get("confidence_level") == "unverified", "SHRIMP should be unverified"
        assert shrimp.get("review_reason") is not None, "SHRIMP should have review_reason"
        assert "math" in shrimp.get("review_reason", "").lower() or "mismatch" in shrimp.get("review_reason", "").lower(), \
            f"SHRIMP review_reason should mention math mismatch: {shrimp.get('review_reason')}"
        
        # Empty-name item should need review
        empty_name = next((it for it in items if not (it.get("raw_name") or "").strip()), None)
        assert empty_name is not None, "Empty-name item not found"
        assert empty_name.get("needs_review") == True, "Empty-name item should need review"
        assert empty_name.get("review_reason") is not None, "Empty-name item should have review_reason"
        assert "name" in empty_name.get("review_reason", "").lower(), \
            f"Empty-name review_reason should mention missing name: {empty_name.get('review_reason')}"
    
    def test_create_purchase_sets_review_flags(self, auth_headers):
        """Test that POST /api/purchases sets needs_review and review_reason on items"""
        # Create a purchase with items that should trigger review
        payload = {
            "supplier_name": "TEST_Quick_Review_Create",
            "invoice_number": "QR-CREATE-001",
            "invoice_date": "2026-03-31",
            "items": [
                {
                    "raw_name": "TEST ITEM GOOD",
                    "quantity": 5,
                    "unit_price": 10.00,
                    "total": 50.00,  # Math correct: 5 * 10 = 50
                    "pack_size": ""
                },
                {
                    "raw_name": "TEST ITEM BAD MATH",
                    "quantity": 3,
                    "unit_price": 20.00,
                    "total": 100.00,  # Math wrong: 3 * 20 = 60, not 100
                    "pack_size": ""
                },
                {
                    "raw_name": "",  # Missing name
                    "quantity": 2,
                    "unit_price": 15.00,
                    "total": 30.00,
                    "pack_size": ""
                }
            ],
            "subtotal": 180.00,
            "tax": 0,
            "total": 180.00
        }
        
        response = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        
        created = response.json()
        purchase_id = created.get("id")
        assert purchase_id is not None
        
        try:
            items = created.get("items", [])
            assert len(items) == 3, f"Expected 3 items, got {len(items)}"
            
            # Good item should be trusted
            good_item = next((it for it in items if "GOOD" in (it.get("raw_name") or "").upper()), None)
            assert good_item is not None, "Good item not found"
            assert good_item.get("needs_review") == False, "Good item should not need review"
            assert good_item.get("confidence_level") == "trusted", "Good item should be trusted"
            
            # Bad math item should need review
            bad_math = next((it for it in items if "BAD MATH" in (it.get("raw_name") or "").upper()), None)
            assert bad_math is not None, "Bad math item not found"
            assert bad_math.get("needs_review") == True, "Bad math item should need review"
            assert bad_math.get("review_reason") is not None, "Bad math item should have review_reason"
            
            # Empty name item should need review
            empty_name = next((it for it in items if not (it.get("raw_name") or "").strip()), None)
            assert empty_name is not None, "Empty name item not found"
            assert empty_name.get("needs_review") == True, "Empty name item should need review"
            
            print(f"Created purchase {purchase_id} with correct review flags")
            
        finally:
            # Cleanup: delete the test purchase
            delete_response = requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
            assert delete_response.status_code == 200, f"Failed to delete test purchase: {delete_response.text}"
            print(f"Cleaned up test purchase {purchase_id}")
    
    def test_update_purchase_preserves_review_flags(self, auth_headers):
        """Test that PUT /api/purchases preserves/updates review flags"""
        # First get the test invoice
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        
        purchases = response.json()
        test_invoice = next((p for p in purchases if "Quick Review Test" in p.get("supplier_name", "")), None)
        assert test_invoice is not None
        
        purchase_id = test_invoice.get("id")
        original_items = test_invoice.get("items", [])
        
        # Update without changing items - flags should persist
        update_payload = {
            "supplier_name": test_invoice.get("supplier_name"),
            "invoice_number": test_invoice.get("invoice_number"),
            "invoice_date": test_invoice.get("invoice_date"),
            "items": original_items,
            "subtotal": test_invoice.get("subtotal"),
            "tax": test_invoice.get("tax"),
            "total": test_invoice.get("total")
        }
        
        response = requests.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload, headers=auth_headers)
        assert response.status_code == 200, f"Update failed: {response.text}"
        
        updated = response.json()
        updated_items = updated.get("items", [])
        
        # Count items needing review
        needs_review_count = sum(1 for it in updated_items if it.get("needs_review"))
        trusted_count = sum(1 for it in updated_items if it.get("confidence_level") == "trusted")
        
        assert needs_review_count == 2, f"Expected 2 items needing review, got {needs_review_count}"
        assert trusted_count == 2, f"Expected 2 trusted items, got {trusted_count}"
        
        print(f"Update preserved review flags: {needs_review_count} need review, {trusted_count} trusted")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
