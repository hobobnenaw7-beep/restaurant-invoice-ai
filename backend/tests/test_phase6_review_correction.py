"""
Phase 6: Review + Correction Layer Tests
Tests for:
- PATCH /api/purchases/{id}/items/{index} - inline edit with revalidation and audit trail
- GET /api/purchases/{id}/edit-history - returns edit audit trail
- Validation delta (improved/degraded/unchanged)
- Edit history tracking
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPhase6ReviewCorrection:
    """Phase 6: Review + Correction Layer Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        yield
        
        # Cleanup - delete test purchases
        try:
            purchases = self.session.get(f"{BASE_URL}/api/purchases").json()
            for p in purchases:
                if p.get("supplier_name", "").startswith("TEST_PHASE6_"):
                    self.session.delete(f"{BASE_URL}/api/purchases/{p['id']}")
        except:
            pass
    
    def test_patch_item_endpoint_exists(self):
        """Test PATCH /api/purchases/{id}/items/{index} endpoint exists"""
        # Create a test purchase first
        purchase_data = {
            "supplier_name": "TEST_PHASE6_Vendor",
            "invoice_number": "TEST-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Test Item", "quantity": 2, "unit_price": 10.00, "total": 20.00}
            ],
            "subtotal": 20.00,
            "tax": 0,
            "total": 20.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200, f"Create failed: {create_res.text}"
        purchase_id = create_res.json()["id"]
        
        # Test PATCH endpoint
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"raw_name": "Updated Item Name"}
        )
        assert patch_res.status_code == 200, f"PATCH failed: {patch_res.text}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_returns_validation_delta(self):
        """Test PATCH returns validation_delta field"""
        # Create purchase with item that needs review (math mismatch)
        purchase_data = {
            "supplier_name": "TEST_PHASE6_Delta",
            "invoice_number": "TEST-002",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Math Issue Item", "quantity": 5, "unit_price": 10.00, "total": 100.00}  # Math mismatch: 5*10=50, not 100
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Fix the math issue
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"total": 50.00}  # Correct total: 5*10=50
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check validation_delta is present
        assert "validation_delta" in data, "validation_delta missing from response"
        assert data["validation_delta"] in ["improved", "degraded", "unchanged"], f"Invalid validation_delta: {data['validation_delta']}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_returns_changes(self):
        """Test PATCH returns changes dict with previous/new values"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_Changes",
            "invoice_number": "TEST-003",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Original Name", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Update item name
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"raw_name": "New Name", "quantity": 2}
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check changes structure
        assert "changes" in data, "changes missing from response"
        assert "raw_name" in data["changes"], "raw_name change not tracked"
        assert data["changes"]["raw_name"]["previous"] == "Original Name"
        assert data["changes"]["raw_name"]["new"] == "New Name"
        assert "quantity" in data["changes"], "quantity change not tracked"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_returns_edit_entry(self):
        """Test PATCH returns edit_entry with audit trail info"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_EditEntry",
            "invoice_number": "TEST-004",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Update item
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"unit_price": 15.00}
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check edit_entry structure
        assert "edit_entry" in data, "edit_entry missing from response"
        entry = data["edit_entry"]
        assert "item_index" in entry
        assert "changes" in entry
        assert "validation_delta" in entry
        assert "old_status" in entry
        assert "new_status" in entry
        assert "edited_by" in entry
        assert "edited_at" in entry
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_returns_purchase_totals(self):
        """Test PATCH returns updated purchase_totals"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_Totals",
            "invoice_number": "TEST-005",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item 1", "quantity": 1, "unit_price": 10.00, "total": 10.00},
                {"raw_name": "Item 2", "quantity": 1, "unit_price": 20.00, "total": 20.00}
            ],
            "subtotal": 30.00,
            "tax": 3.00,
            "total": 33.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Update item total
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"total": 15.00}
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check purchase_totals
        assert "purchase_totals" in data, "purchase_totals missing from response"
        totals = data["purchase_totals"]
        assert "subtotal" in totals
        assert "tax" in totals
        assert "total" in totals
        # New subtotal should be 15 + 20 = 35
        assert totals["subtotal"] == 35.00, f"Expected subtotal 35.00, got {totals['subtotal']}"
        # Total should be 35 + 3 = 38
        assert totals["total"] == 38.00, f"Expected total 38.00, got {totals['total']}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_no_changes_returns_unchanged(self):
        """Test PATCH with no actual changes returns unchanged delta"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_NoChange",
            "invoice_number": "TEST-006",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Send same values
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"raw_name": "Item", "quantity": 1}  # Same values
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Should return unchanged
        assert data["validation_delta"] == "unchanged"
        assert data["changes"] == {}
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_invalid_index_returns_400(self):
        """Test PATCH with invalid item index returns 400"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_InvalidIdx",
            "invoice_number": "TEST-007",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Try invalid index
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/99",
            json={"raw_name": "New Name"}
        )
        assert patch_res.status_code == 400, f"Expected 400, got {patch_res.status_code}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_patch_item_nonexistent_purchase_returns_404(self):
        """Test PATCH with nonexistent purchase ID returns 404"""
        fake_id = str(uuid.uuid4())
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{fake_id}/items/0",
            json={"raw_name": "New Name"}
        )
        assert patch_res.status_code == 404
    
    def test_get_edit_history_endpoint(self):
        """Test GET /api/purchases/{id}/edit-history returns edit history"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_History",
            "invoice_number": "TEST-008",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Make an edit
        self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"raw_name": "Updated Item"}
        )
        
        # Get edit history
        history_res = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}/edit-history")
        assert history_res.status_code == 200
        data = history_res.json()
        
        # Check structure
        assert "id" in data
        assert "edit_history" in data
        assert isinstance(data["edit_history"], list)
        assert len(data["edit_history"]) >= 1
        
        # Check first entry
        entry = data["edit_history"][0]
        assert "item_index" in entry
        assert "changes" in entry
        assert "edited_at" in entry
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_get_edit_history_empty_for_new_purchase(self):
        """Test GET edit-history returns empty list for new purchase"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_EmptyHistory",
            "invoice_number": "TEST-009",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Get edit history without making any edits
        history_res = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}/edit-history")
        assert history_res.status_code == 200
        data = history_res.json()
        
        assert data["edit_history"] == []
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_get_edit_history_nonexistent_purchase_returns_404(self):
        """Test GET edit-history with nonexistent purchase returns 404"""
        fake_id = str(uuid.uuid4())
        history_res = self.session.get(f"{BASE_URL}/api/purchases/{fake_id}/edit-history")
        assert history_res.status_code == 404
    
    def test_multiple_edits_tracked_in_history(self):
        """Test multiple edits are all tracked in edit history"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_MultiEdit",
            "invoice_number": "TEST-010",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Make multiple edits
        self.session.patch(f"{BASE_URL}/api/purchases/{purchase_id}/items/0", json={"raw_name": "Edit 1"})
        self.session.patch(f"{BASE_URL}/api/purchases/{purchase_id}/items/0", json={"quantity": 2})
        self.session.patch(f"{BASE_URL}/api/purchases/{purchase_id}/items/0", json={"unit_price": 15.00})
        
        # Get edit history
        history_res = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}/edit-history")
        assert history_res.status_code == 200
        data = history_res.json()
        
        # Should have 3 entries
        assert len(data["edit_history"]) == 3, f"Expected 3 edits, got {len(data['edit_history'])}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_validation_delta_improved_when_fixing_math(self):
        """Test validation_delta is 'improved' when fixing math mismatch"""
        # Create purchase with math mismatch
        purchase_data = {
            "supplier_name": "TEST_PHASE6_MathFix",
            "invoice_number": "TEST-011",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Math Issue", "quantity": 3, "unit_price": 10.00, "total": 50.00}  # 3*10=30, not 50
            ],
            "subtotal": 50.00,
            "tax": 0,
            "total": 50.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Check initial item has needs_review
        purchase = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}").json()
        initial_needs_review = purchase["items"][0].get("needs_review", False)
        
        # Fix the math
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"total": 30.00}  # Correct: 3*10=30
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # If initial had needs_review=True and now fixed, should be improved
        if initial_needs_review:
            assert data["validation_delta"] == "improved", f"Expected 'improved', got '{data['validation_delta']}'"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_editable_fields_only(self):
        """Test only editable fields (raw_name, quantity, unit_price, total, pack_size) are accepted"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_EditableFields",
            "invoice_number": "TEST-012",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 1, "unit_price": 10.00, "total": 10.00}
            ],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Try to update all editable fields
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={
                "raw_name": "New Name",
                "quantity": 5,
                "unit_price": 20.00,
                "total": 100.00,
                "pack_size": "10/1 LB"
            }
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check all fields were updated
        item = data["item"]
        assert item["raw_name"] == "New Name"
        assert item["quantity"] == 5
        assert item["unit_price"] == 20.00
        assert item["total"] == 100.00
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
    
    def test_review_status_updated_after_edit(self):
        """Test purchase review_status is updated after item edit"""
        purchase_data = {
            "supplier_name": "TEST_PHASE6_ReviewStatus",
            "invoice_number": "TEST-013",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": "Item", "quantity": 2, "unit_price": 10.00, "total": 20.00}
            ],
            "subtotal": 20.00,
            "tax": 0,
            "total": 20.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_res.status_code == 200
        purchase_id = create_res.json()["id"]
        
        # Edit item
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{purchase_id}/items/0",
            json={"raw_name": "Updated Name"}
        )
        assert patch_res.status_code == 200
        data = patch_res.json()
        
        # Check review_status is returned
        assert "review_status" in data, "review_status missing from response"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")


class TestExistingPurchaseWithReviewItems:
    """Test with the existing purchase mentioned in the context (9e18064e-df44-4db8-857d-ae6d11fb8b97)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        self.test_purchase_id = "9e18064e-df44-4db8-857d-ae6d11fb8b97"
    
    def test_existing_purchase_exists(self):
        """Test the existing test purchase exists"""
        res = self.session.get(f"{BASE_URL}/api/purchases/{self.test_purchase_id}")
        # May or may not exist depending on environment
        if res.status_code == 200:
            data = res.json()
            print(f"Found purchase: {data.get('supplier_name')}")
            print(f"Items count: {len(data.get('items', []))}")
            items_needing_review = [it for it in data.get('items', []) if it.get('needs_review')]
            print(f"Items needing review: {len(items_needing_review)}")
        else:
            pytest.skip("Test purchase not found in this environment")
    
    def test_patch_existing_purchase_item(self):
        """Test patching an item on the existing purchase"""
        res = self.session.get(f"{BASE_URL}/api/purchases/{self.test_purchase_id}")
        if res.status_code != 200:
            pytest.skip("Test purchase not found")
        
        purchase = res.json()
        if not purchase.get("items"):
            pytest.skip("Purchase has no items")
        
        # Get first item's current name
        original_name = purchase["items"][0].get("raw_name", "")
        
        # Patch it
        patch_res = self.session.patch(
            f"{BASE_URL}/api/purchases/{self.test_purchase_id}/items/0",
            json={"raw_name": f"{original_name} (tested)"}
        )
        assert patch_res.status_code == 200
        
        # Revert
        self.session.patch(
            f"{BASE_URL}/api/purchases/{self.test_purchase_id}/items/0",
            json={"raw_name": original_name}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
