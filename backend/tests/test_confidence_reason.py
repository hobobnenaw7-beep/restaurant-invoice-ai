"""
Test confidence_reason field for explainability.
Tests that each item has a human-readable reason explaining WHY it's trusted/unverified.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestConfidenceReason:
    """Test the confidence_reason field for explainability."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token."""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed - skipping tests")
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        self.created_ids = []
        yield
        # Cleanup
        for pid in self.created_ids:
            try:
                requests.delete(f"{BASE_URL}/api/purchases/{pid}", headers=self.headers)
            except:
                pass
    
    def create_purchase(self, items):
        """Helper to create a purchase with given items."""
        payload = {
            "supplier_name": "TEST_REASON_VENDOR",
            "invoice_number": "TEST-REASON-001",
            "invoice_date": "2026-01-15",
            "items": items,
            "subtotal": sum(it.get("total", 0) for it in items),
            "tax": 0,
            "total": sum(it.get("total", 0) for it in items)
        }
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        if resp.status_code in [200, 201] and resp.json().get("id"):
            self.created_ids.append(resp.json()["id"])
        return resp
    
    # ===== TEST 1: Trusted item → confidence_reason = "All checks passed" =====
    def test_trusted_item_reason_all_checks_passed(self):
        """Trusted item should have confidence_reason = 'All checks passed'"""
        items = [{
            "raw_name": "CHICKEN BREAST",
            "quantity": 3,
            "pack_size": "4/10 LB",
            "unit_price": 89.45,
            "total": 268.35  # 3 * 89.45 = 268.35 ✓
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "trusted"
        assert "confidence_reason" in item, "Expected confidence_reason field"
        assert item["confidence_reason"] == "All checks passed", \
            f"Expected 'All checks passed', got '{item.get('confidence_reason')}'"
        print(f"✓ Trusted item reason: {item['confidence_reason']}")
    
    # ===== TEST 2: Math mismatch → confidence_reason = "Math mismatch (qty × price ≠ total)" =====
    def test_math_mismatch_reason(self):
        """Math mismatch should have confidence_reason = 'Math mismatch (qty × price ≠ total)'"""
        items = [{
            "raw_name": "SALMON",
            "quantity": 3,
            "pack_size": "4/10 LB",
            "unit_price": 89.45,
            "total": 300.00  # 3 * 89.45 = 268.35 ≠ 300.00 ✗
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        assert "confidence_reason" in item
        assert item["confidence_reason"] == "Math mismatch (qty × price ≠ total)", \
            f"Expected 'Math mismatch (qty × price ≠ total)', got '{item.get('confidence_reason')}'"
        print(f"✓ Math mismatch reason: {item['confidence_reason']}")
    
    # ===== TEST 3: Pack parse failed → confidence_reason = "Pack size could not be parsed" =====
    def test_pack_parse_failed_reason(self):
        """Pack parse failed should have confidence_reason = 'Pack size could not be parsed'"""
        items = [{
            "raw_name": "FLOUR",
            "quantity": 2,
            "pack_size": "CS10007",  # Unparseable
            "unit_price": 16.25,
            "total": 32.50  # Math is correct
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        assert "confidence_reason" in item
        assert item["confidence_reason"] == "Pack size could not be parsed", \
            f"Expected 'Pack size could not be parsed', got '{item.get('confidence_reason')}'"
        print(f"✓ Pack parse failed reason: {item['confidence_reason']}")
    
    # ===== TEST 4: Missing item name → confidence_reason = "Missing item name" =====
    def test_missing_name_reason(self):
        """Missing item name should have confidence_reason = 'Missing item name'"""
        items = [{
            "raw_name": "",  # Missing name
            "quantity": 2,
            "pack_size": "10 LB",
            "unit_price": 25.00,
            "total": 50.00
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        assert "confidence_reason" in item
        assert item["confidence_reason"] == "Missing item name", \
            f"Expected 'Missing item name', got '{item.get('confidence_reason')}'"
        print(f"✓ Missing name reason: {item['confidence_reason']}")
    
    # ===== TEST 5: Missing fields → confidence_reason = "Missing fields: ..." =====
    def test_missing_fields_reason(self):
        """Missing fields should have confidence_reason = 'Missing fields: ...'"""
        items = [{
            "raw_name": "TOMATOES",
            "quantity": 0,  # Missing qty
            "pack_size": "",
            "unit_price": 0,  # Missing price
            "total": 0  # Missing total
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        assert "confidence_reason" in item
        assert "Missing fields:" in item["confidence_reason"], \
            f"Expected 'Missing fields:...' in reason, got '{item.get('confidence_reason')}'"
        print(f"✓ Missing fields reason: {item['confidence_reason']}")
    
    # ===== TEST 6: Suspicious values → confidence_reason = "Suspicious values detected" =====
    def test_suspicious_values_reason(self):
        """Suspicious values should have confidence_reason = 'Suspicious values detected'"""
        items = [{
            "raw_name": "SUSPICIOUS ITEM",
            "quantity": 25,
            "pack_size": "10 LB",
            "unit_price": 25,  # qty == unit_price (suspicious)
            "total": 625  # Math is correct
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        assert "confidence_reason" in item
        assert item["confidence_reason"] == "Suspicious values detected", \
            f"Expected 'Suspicious values detected', got '{item.get('confidence_reason')}'"
        print(f"✓ Suspicious values reason: {item['confidence_reason']}")
    
    # ===== TEST 7: Mixed items - verify each has correct reason =====
    def test_mixed_items_each_has_reason(self):
        """Create purchase with 4 items (2 trusted, 2 unverified) and verify each has correct reason"""
        items = [
            # Item 1: Trusted (all checks pass)
            {
                "raw_name": "CHICKEN BREAST",
                "quantity": 3,
                "pack_size": "4/10 LB",
                "unit_price": 89.45,
                "total": 268.35
            },
            # Item 2: Unverified (pack parse failed)
            {
                "raw_name": "FLOUR",
                "quantity": 2,
                "pack_size": "CS10007",
                "unit_price": 16.25,
                "total": 32.50
            },
            # Item 3: Unverified (math mismatch)
            {
                "raw_name": "SALMON",
                "quantity": 3,
                "pack_size": "4/10 LB",
                "unit_price": 89.45,
                "total": 300.00  # Wrong total
            },
            # Item 4: Trusted (no pack size is OK)
            {
                "raw_name": "TOMATOES",
                "quantity": 5,
                "pack_size": "1/25 LB",
                "unit_price": 24.75,
                "total": 123.75
            }
        ]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        
        # Verify each item has confidence_reason
        for i, item in enumerate(data["items"]):
            assert "confidence_reason" in item, f"Item {i} missing confidence_reason"
            assert item["confidence_reason"], f"Item {i} has empty confidence_reason"
            print(f"  Item {i} ({item['raw_name']}): {item['confidence_level']} - {item['confidence_reason']}")
        
        # Verify specific reasons
        assert data["items"][0]["confidence_reason"] == "All checks passed"
        assert data["items"][1]["confidence_reason"] == "Pack size could not be parsed"
        assert data["items"][2]["confidence_reason"] == "Math mismatch (qty × price ≠ total)"
        assert data["items"][3]["confidence_reason"] == "All checks passed"
        
        print(f"✓ All 4 items have correct confidence_reason")


class TestConfidenceReasonOnUpdate:
    """Test that confidence_reason is computed on update as well."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token."""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed - skipping tests")
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        self.created_ids = []
        yield
        # Cleanup
        for pid in self.created_ids:
            try:
                requests.delete(f"{BASE_URL}/api/purchases/{pid}", headers=self.headers)
            except:
                pass
    
    def create_purchase(self, items):
        """Helper to create a purchase with given items."""
        payload = {
            "supplier_name": "TEST_UPDATE_REASON_VENDOR",
            "invoice_number": "TEST-UPD-001",
            "invoice_date": "2026-01-15",
            "items": items,
            "subtotal": sum(it.get("total", 0) for it in items),
            "tax": 0,
            "total": sum(it.get("total", 0) for it in items)
        }
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        if resp.status_code in [200, 201] and resp.json().get("id"):
            self.created_ids.append(resp.json()["id"])
        return resp
    
    def test_update_changes_reason_when_fixed(self):
        """When user fixes math, confidence_reason should change to 'All checks passed'"""
        # Create with math mismatch
        items = [{
            "raw_name": "SALMON",
            "quantity": 3,
            "pack_size": "4/10 LB",
            "unit_price": 89.45,
            "total": 300.00  # Wrong total
        }]
        create_resp = self.create_purchase(items)
        assert create_resp.status_code in [200, 201]
        purchase_id = create_resp.json()["id"]
        
        # Verify initial state is unverified
        initial_item = create_resp.json()["items"][0]
        assert initial_item["confidence_level"] == "unverified"
        assert initial_item["confidence_reason"] == "Math mismatch (qty × price ≠ total)"
        
        # Update with correct math
        update_payload = {
            "items": [{
                "raw_name": "SALMON",
                "quantity": 3,
                "pack_size": "4/10 LB",
                "unit_price": 89.45,
                "total": 268.35  # Correct: 3 * 89.45 = 268.35
            }]
        }
        update_resp = requests.put(
            f"{BASE_URL}/api/purchases/{purchase_id}",
            json=update_payload,
            headers=self.headers
        )
        assert update_resp.status_code == 200
        
        # Verify updated state is trusted
        updated_item = update_resp.json()["items"][0]
        assert updated_item["confidence_level"] == "trusted", \
            f"Expected 'trusted' after fix, got '{updated_item.get('confidence_level')}'"
        assert updated_item["confidence_reason"] == "All checks passed", \
            f"Expected 'All checks passed' after fix, got '{updated_item.get('confidence_reason')}'"
        
        print(f"✓ After fix: {updated_item['confidence_level']} - {updated_item['confidence_reason']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
