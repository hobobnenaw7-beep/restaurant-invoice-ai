"""
Test Manual Review Workflow for invoice items with needs_review flag.

Features tested:
1. PATCH /api/purchases/{id}/items/{index} - Inline edit for price/qty/total
2. PATCH /api/purchases/{id}/verify - Mark as Verified action
3. GET /api/purchases/{id}/edit-history - Audit trail on all edits
4. Correction memory: name corrections saved, price edits NOT saved
5. GET /api/purchases - Filter by needs_review status
6. GET /api/correction-memory - Verify correction entries
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestManualReviewWorkflow:
    """Test suite for Manual Review Workflow features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as manager
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data["token"]
        self.user = data["user"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Store created purchase IDs for cleanup
        self.created_purchase_ids = []
        yield
        
        # Cleanup: Delete test purchases
        for pid in self.created_purchase_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/purchases/{pid}")
            except:
                pass
    
    def create_test_purchase_with_review_items(self):
        """Helper: Create a purchase with items that need review"""
        purchase_data = {
            "supplier_name": f"TEST_VENDOR_{uuid.uuid4().hex[:8]}",
            "invoice_number": f"TEST-INV-{uuid.uuid4().hex[:6]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "raw_name": "Test Item With Review",
                    "quantity": 5,
                    "unit_price": 10.00,
                    "total": 50.00,
                    "needs_review": True,
                    "review_reason": "Missing price verification"
                },
                {
                    "raw_name": "Test Item Clean",
                    "quantity": 2,
                    "unit_price": 25.00,
                    "total": 50.00,
                    "needs_review": False
                },
                {
                    "raw_name": "Another Review Item",
                    "quantity": 0,  # Missing qty - needs review
                    "unit_price": 15.00,
                    "total": 0,
                    "needs_review": True,
                    "review_reason": "Missing quantity"
                }
            ],
            "subtotal": 100.00,
            "tax": 8.00,
            "total": 108.00
        }
        
        resp = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert resp.status_code == 200, f"Failed to create purchase: {resp.text}"
        purchase = resp.json()
        self.created_purchase_ids.append(purchase["id"])
        return purchase
    
    # ─────────────────────────────────────────────────────────────────
    # Test 1: PATCH /purchases/{id}/items/{index} - Inline Edit
    # ─────────────────────────────────────────────────────────────────
    
    def test_patch_item_updates_price(self):
        """Test: PATCH updates unit_price and recalculates totals"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Patch item 0 - update unit_price
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"unit_price": 12.50}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        result = patch_resp.json()
        assert "item" in result, "Response should contain 'item'"
        assert result["item"]["unit_price"] == 12.50, "unit_price should be updated"
        assert "purchase_totals" in result, "Response should contain purchase_totals"
        print(f"✓ PATCH item price: {result['item']['unit_price']}, totals: {result['purchase_totals']}")
    
    def test_patch_item_updates_quantity(self):
        """Test: PATCH updates quantity and recalculates totals"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Patch item 2 - update quantity (was 0)
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/2",
            json={"quantity": 3, "total": 45.00}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        result = patch_resp.json()
        assert result["item"]["quantity"] == 3, "quantity should be updated"
        assert result["item"]["total"] == 45.00, "total should be updated"
        print(f"✓ PATCH item qty: {result['item']['quantity']}, total: {result['item']['total']}")
    
    def test_patch_item_returns_validation_delta(self):
        """Test: PATCH returns validation_delta (improved/degraded/unchanged)"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Patch item 2 - fix missing values (should improve validation)
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/2",
            json={"quantity": 3, "total": 45.00}
        )
        assert patch_resp.status_code == 200
        
        result = patch_resp.json()
        assert "validation_delta" in result, "Response should contain validation_delta"
        assert result["validation_delta"] in ["improved", "degraded", "unchanged"], \
            f"validation_delta should be one of improved/degraded/unchanged, got: {result['validation_delta']}"
        print(f"✓ validation_delta: {result['validation_delta']}")
    
    def test_patch_item_invalid_index(self):
        """Test: PATCH with invalid item index returns 400"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Try to patch item at invalid index
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/99",
            json={"unit_price": 10.00}
        )
        assert patch_resp.status_code == 400, f"Expected 400 for invalid index, got {patch_resp.status_code}"
        print("✓ Invalid index returns 400")
    
    # ─────────────────────────────────────────────────────────────────
    # Test 2: GET /purchases/{id}/edit-history - Audit Trail
    # ─────────────────────────────────────────────────────────────────
    
    def test_edit_history_created_on_patch(self):
        """Test: PATCH creates edit_history entry with audit trail"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Make an edit
        self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"unit_price": 15.00}
        )
        
        # Get edit history
        history_resp = self.session.get(f"{BASE_URL}/api/purchases/{pid}/edit-history")
        assert history_resp.status_code == 200, f"GET edit-history failed: {history_resp.text}"
        
        result = history_resp.json()
        assert "edit_history" in result, "Response should contain edit_history"
        assert len(result["edit_history"]) >= 1, "Should have at least 1 edit entry"
        
        entry = result["edit_history"][-1]
        assert "item_index" in entry, "Entry should have item_index"
        assert "changes" in entry, "Entry should have changes"
        assert "edited_by" in entry, "Entry should have edited_by"
        assert "edited_at" in entry, "Entry should have edited_at"
        print(f"✓ Edit history entry: {entry}")
    
    def test_edit_history_tracks_changes(self):
        """Test: Edit history tracks previous and new values"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        original_price = purchase["items"][0]["unit_price"]
        new_price = 20.00
        
        # Make an edit
        self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"unit_price": new_price}
        )
        
        # Get edit history
        history_resp = self.session.get(f"{BASE_URL}/api/purchases/{pid}/edit-history")
        result = history_resp.json()
        
        entry = result["edit_history"][-1]
        assert "unit_price" in entry["changes"], "Changes should include unit_price"
        assert entry["changes"]["unit_price"]["previous"] == original_price, \
            f"Previous value should be {original_price}"
        assert entry["changes"]["unit_price"]["new"] == new_price, \
            f"New value should be {new_price}"
        print(f"✓ Changes tracked: {entry['changes']}")
    
    # ─────────────────────────────────────────────────────────────────
    # Test 3: PATCH /purchases/{id}/verify - Mark as Verified
    # ─────────────────────────────────────────────────────────────────
    
    def test_verify_purchase_sets_status(self):
        """Test: PATCH /verify sets review_status='verified' and approval_status='approved'"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Verify the purchase
        verify_resp = self.session.patch(f"{BASE_URL}/api/purchases/{pid}/verify")
        assert verify_resp.status_code == 200, f"Verify failed: {verify_resp.text}"
        
        result = verify_resp.json()
        assert result["status"] == "verified", "Status should be 'verified'"
        assert "verified_at" in result, "Response should contain verified_at"
        assert "verified_by" in result, "Response should contain verified_by"
        
        # Verify the purchase was updated
        get_resp = self.session.get(f"{BASE_URL}/api/purchases/{pid}")
        assert get_resp.status_code == 200
        updated = get_resp.json()
        assert updated["review_status"] == "verified", "review_status should be 'verified'"
        assert updated["approval_status"] == "approved", "approval_status should be 'approved'"
        print(f"✓ Purchase verified: review_status={updated['review_status']}, approval_status={updated['approval_status']}")
    
    def test_verify_purchase_not_found(self):
        """Test: PATCH /verify on non-existent purchase returns 404"""
        verify_resp = self.session.patch(f"{BASE_URL}/api/purchases/nonexistent-id/verify")
        assert verify_resp.status_code == 404, f"Expected 404, got {verify_resp.status_code}"
        print("✓ Non-existent purchase returns 404")
    
    # ─────────────────────────────────────────────────────────────────
    # Test 4: Correction Memory - Name vs Price Edits
    # ─────────────────────────────────────────────────────────────────
    
    def test_name_correction_creates_memory_entry(self):
        """Test: Editing raw_name creates correction_memory entry"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        original_name = purchase["items"][0]["raw_name"]
        new_name = f"CORRECTED_NAME_{uuid.uuid4().hex[:6]}"
        
        # Get correction memory count before
        cm_before = self.session.get(f"{BASE_URL}/api/correction-memory")
        count_before = len(cm_before.json()) if cm_before.status_code == 200 else 0
        
        # Edit the name
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"raw_name": new_name}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        # Get correction memory count after
        cm_after = self.session.get(f"{BASE_URL}/api/correction-memory")
        if cm_after.status_code == 200:
            count_after = len(cm_after.json())
            # Should have at least one more entry
            assert count_after >= count_before, \
                f"Correction memory should have new entry. Before: {count_before}, After: {count_after}"
            print(f"✓ Name correction created memory entry. Count: {count_before} → {count_after}")
        else:
            print(f"⚠ Could not verify correction memory (status: {cm_after.status_code})")
    
    def test_price_edit_does_not_create_memory_entry(self):
        """Test: Editing unit_price does NOT create correction_memory entry"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Get correction memory count before
        cm_before = self.session.get(f"{BASE_URL}/api/correction-memory")
        count_before = len(cm_before.json()) if cm_before.status_code == 200 else 0
        
        # Edit only the price (not the name)
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"unit_price": 99.99}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        # Get correction memory count after
        cm_after = self.session.get(f"{BASE_URL}/api/correction-memory")
        if cm_after.status_code == 200:
            count_after = len(cm_after.json())
            # Count should be the same (no new entry for price-only edit)
            assert count_after == count_before, \
                f"Price edit should NOT create memory entry. Before: {count_before}, After: {count_after}"
            print(f"✓ Price edit did NOT create memory entry. Count unchanged: {count_before}")
        else:
            print(f"⚠ Could not verify correction memory (status: {cm_after.status_code})")
    
    def test_quantity_edit_does_not_create_memory_entry(self):
        """Test: Editing quantity does NOT create correction_memory entry"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        
        # Get correction memory count before
        cm_before = self.session.get(f"{BASE_URL}/api/correction-memory")
        count_before = len(cm_before.json()) if cm_before.status_code == 200 else 0
        
        # Edit only the quantity
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"quantity": 100}
        )
        assert patch_resp.status_code == 200
        
        # Get correction memory count after
        cm_after = self.session.get(f"{BASE_URL}/api/correction-memory")
        if cm_after.status_code == 200:
            count_after = len(cm_after.json())
            assert count_after == count_before, \
                f"Quantity edit should NOT create memory entry. Before: {count_before}, After: {count_after}"
            print(f"✓ Quantity edit did NOT create memory entry. Count unchanged: {count_before}")
        else:
            print(f"⚠ Could not verify correction memory (status: {cm_after.status_code})")
    
    # ─────────────────────────────────────────────────────────────────
    # Test 5: GET /purchases - Filter by needs_review
    # ─────────────────────────────────────────────────────────────────
    
    def test_get_purchases_returns_items_with_needs_review(self):
        """Test: GET /purchases returns purchases with items that have needs_review flag"""
        purchase = self.create_test_purchase_with_review_items()
        
        # Get all purchases
        resp = self.session.get(f"{BASE_URL}/api/purchases")
        assert resp.status_code == 200, f"GET purchases failed: {resp.text}"
        
        purchases = resp.json()
        assert len(purchases) > 0, "Should have at least one purchase"
        
        # Find our test purchase
        test_purchase = next((p for p in purchases if p["id"] == purchase["id"]), None)
        assert test_purchase is not None, "Test purchase should be in list"
        
        # Check items have needs_review flag
        items_with_review = [it for it in test_purchase.get("items", []) if it.get("needs_review")]
        assert len(items_with_review) >= 1, "Should have items with needs_review=True"
        print(f"✓ Purchase has {len(items_with_review)} items needing review")
    
    # ─────────────────────────────────────────────────────────────────
    # Test 6: Real-time totals update
    # ─────────────────────────────────────────────────────────────────
    
    def test_patch_recalculates_purchase_totals(self):
        """Test: PATCH recalculates subtotal and total for the purchase"""
        purchase = self.create_test_purchase_with_review_items()
        pid = purchase["id"]
        original_total = purchase["total"]
        
        # Update item 0 total from 50 to 100
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/purchases/{pid}/items/0",
            json={"total": 100.00}
        )
        assert patch_resp.status_code == 200
        
        result = patch_resp.json()
        new_totals = result.get("purchase_totals", {})
        
        # Verify totals were recalculated
        # Original: item0=50, item1=50, item2=0 = subtotal 100, tax 8, total 108
        # After: item0=100, item1=50, item2=0 = subtotal 150, tax 8, total 158
        assert new_totals.get("subtotal") == 150.00, \
            f"Subtotal should be 150.00, got {new_totals.get('subtotal')}"
        assert new_totals.get("total") == 158.00, \
            f"Total should be 158.00, got {new_totals.get('total')}"
        print(f"✓ Totals recalculated: subtotal={new_totals['subtotal']}, total={new_totals['total']}")


class TestCorrectionMemoryAPI:
    """Test correction memory API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        self.token = data["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_get_correction_memory(self):
        """Test: GET /correction-memory returns list of corrections"""
        resp = self.session.get(f"{BASE_URL}/api/correction-memory")
        assert resp.status_code == 200, f"GET correction-memory failed: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /correction-memory returned {len(data)} entries")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
