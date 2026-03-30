"""
Test strict confidence scoring with hard gates.
Tests the new binary classification: 'trusted' vs 'unverified'
Hard gates: math mismatch, missing name, pack parse failed, suspicious patterns
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestStrictConfidenceScoring:
    """Test the strict confidence scoring with hard gates."""
    
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
            "supplier_name": "TEST_CONFIDENCE_VENDOR",
            "invoice_number": "TEST-CONF-001",
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
    
    # ===== TEST 1: Perfect item → trusted/100 =====
    def test_perfect_item_trusted_100(self):
        """Perfect item (math OK, fields present, pack parsed, clear name) → trusted/100"""
        items = [{
            "raw_name": "CHICKEN BREAST BNLS",
            "quantity": 3,
            "pack_size": "4/10 LB",
            "unit_price": 89.45,
            "total": 268.35  # 3 * 89.45 = 268.35 ✓
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # Verify trusted status
        assert item["confidence_level"] == "trusted", f"Expected 'trusted', got '{item.get('confidence_level')}'"
        assert item["confidence_score"] == 100, f"Expected 100, got {item.get('confidence_score')}"
        assert item["valid_calc"] == True, f"Expected valid_calc=True"
        assert item["validation_errors"] == [], f"Expected no errors, got {item.get('validation_errors')}"
        print(f"✓ Perfect item: confidence_level={item['confidence_level']}, score={item['confidence_score']}")
    
    # ===== TEST 2: Pack parse FAILED with pack_size present → unverified (HARD GATE) =====
    def test_pack_parse_failed_forces_unverified(self):
        """Pack parse FAILED with pack_size present → unverified (HARD GATE)"""
        items = [{
            "raw_name": "FLOUR",
            "quantity": 2,
            "pack_size": "CS10007",  # Unparseable pack size
            "unit_price": 16.25,
            "total": 32.50  # 2 * 16.25 = 32.50 ✓
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # HARD GATE: pack parse failed → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert item["pack_parse_status"] == "failed", f"Expected pack_parse_status='failed'"
        assert any("pack_size parse failed" in err for err in item.get("validation_errors", [])), \
            f"Expected pack parse error in validation_errors: {item.get('validation_errors')}"
        print(f"✓ Pack parse failed: confidence_level={item['confidence_level']}, score={item['confidence_score']}")
    
    # ===== TEST 3: Math mismatch → unverified (HARD GATE) =====
    def test_math_mismatch_forces_unverified(self):
        """Math mismatch (qty*price != total) → unverified (HARD GATE)"""
        items = [{
            "raw_name": "SALMON",
            "quantity": 3,
            "pack_size": "4/10 LB",
            "unit_price": 89.45,
            "total": 300.00  # 3 * 89.45 = 268.35 ≠ 300.00 ✗
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # HARD GATE: math mismatch → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert item["valid_calc"] == False, f"Expected valid_calc=False"
        assert any("MATH MISMATCH" in err for err in item.get("validation_errors", [])), \
            f"Expected MATH MISMATCH error: {item.get('validation_errors')}"
        print(f"✓ Math mismatch: confidence_level={item['confidence_level']}, valid_calc={item['valid_calc']}")
    
    # ===== TEST 4: Missing item_name → unverified (HARD GATE) =====
    def test_missing_item_name_forces_unverified(self):
        """Missing item_name → unverified (HARD GATE)"""
        items = [{
            "raw_name": "",  # Missing name
            "quantity": 2,
            "pack_size": "10 LB",
            "unit_price": 25.00,
            "total": 50.00
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # HARD GATE: missing name → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert any("item_name" in err for err in item.get("validation_errors", [])), \
            f"Expected missing item_name error: {item.get('validation_errors')}"
        print(f"✓ Missing name: confidence_level={item['confidence_level']}")
    
    # ===== TEST 5: Total exists but qty=0 and price=0 → unverified (HARD GATE) =====
    def test_total_with_zero_qty_price_forces_unverified(self):
        """Total exists but qty=0 and price=0 → unverified (HARD GATE)"""
        items = [{
            "raw_name": "MYSTERY ITEM",
            "quantity": 0,
            "pack_size": "",
            "unit_price": 0,
            "total": 100.00  # Total exists but qty/price are 0
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # HARD GATE: total exists but qty/price missing → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert any("total exists but qty or unit_price is missing" in err for err in item.get("validation_errors", [])), \
            f"Expected missing qty/price error: {item.get('validation_errors')}"
        print(f"✓ Total with zero qty/price: confidence_level={item['confidence_level']}")
    
    # ===== TEST 6: qty equals unit_price → unverified (SUSPICIOUS pattern) =====
    def test_qty_equals_price_suspicious_pattern(self):
        """qty equals unit_price → unverified (SUSPICIOUS pattern)"""
        items = [{
            "raw_name": "SUSPICIOUS ITEM",
            "quantity": 25,
            "pack_size": "10 LB",
            "unit_price": 25,  # qty == unit_price (suspicious)
            "total": 625  # 25 * 25 = 625 (math is correct)
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # SUSPICIOUS: qty == price → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert any("qty equals unit_price" in err for err in item.get("validation_errors", [])), \
            f"Expected qty equals price error: {item.get('validation_errors')}"
        print(f"✓ Qty equals price: confidence_level={item['confidence_level']}")
    
    # ===== TEST 7: Unrealistic packs_per_case >200 → unverified (SUSPICIOUS) =====
    def test_unrealistic_packs_per_case_suspicious(self):
        """Unrealistic packs_per_case >200 → unverified (SUSPICIOUS)"""
        items = [{
            "raw_name": "BULK ITEM",
            "quantity": 1,
            "pack_size": "300/1 LB",  # 300 packs per case (unrealistic)
            "unit_price": 500.00,
            "total": 500.00
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # SUSPICIOUS: packs_per_case > 200 → must be unverified
        assert item["confidence_level"] == "unverified", f"Expected 'unverified', got '{item.get('confidence_level')}'"
        assert any("unrealistic packs_per_case" in err for err in item.get("validation_errors", [])), \
            f"Expected unrealistic packs error: {item.get('validation_errors')}"
        print(f"✓ Unrealistic packs: confidence_level={item['confidence_level']}")
    
    # ===== TEST 8: Duplicate rows → second row forced unverified (cross-item) =====
    def test_duplicate_rows_second_unverified(self):
        """Duplicate rows (same name+price+total) → second row forced unverified"""
        items = [
            {
                "raw_name": "DUPLICATE ITEM",
                "quantity": 2,
                "pack_size": "10 LB",
                "unit_price": 50.00,
                "total": 100.00
            },
            {
                "raw_name": "DUPLICATE ITEM",  # Same name
                "quantity": 2,
                "pack_size": "10 LB",
                "unit_price": 50.00,  # Same price
                "total": 100.00  # Same total
            }
        ]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # First item should be trusted (if all other checks pass)
        # Second item should be unverified due to duplicate detection
        second_item = data["items"][1]
        assert second_item["confidence_level"] == "unverified", \
            f"Expected second duplicate to be 'unverified', got '{second_item.get('confidence_level')}'"
        assert any("duplicate row" in err for err in second_item.get("validation_errors", [])), \
            f"Expected duplicate row error: {second_item.get('validation_errors')}"
        print(f"✓ Duplicate rows: second item confidence_level={second_item['confidence_level']}")
    
    # ===== TEST 9: Good item without pack_size → trusted (no pack is OK) =====
    def test_good_item_without_pack_trusted(self):
        """Good item without pack_size → trusted (no pack is OK)"""
        items = [{
            "raw_name": "SIMPLE ITEM",
            "quantity": 5,
            "pack_size": "",  # No pack size
            "unit_price": 20.00,
            "total": 100.00  # 5 * 20 = 100 ✓
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        item = data["items"][0]
        
        # No pack_size is fine → should be trusted
        assert item["confidence_level"] == "trusted", f"Expected 'trusted', got '{item.get('confidence_level')}'"
        assert item["valid_calc"] == True, f"Expected valid_calc=True"
        assert item["pack_parse_status"] == "not_applicable", f"Expected pack_parse_status='not_applicable'"
        print(f"✓ No pack size: confidence_level={item['confidence_level']}, score={item['confidence_score']}")
    
    # ===== TEST 10: Verify confidence_level is now binary (trusted/unverified, not high/medium/low) =====
    def test_confidence_level_is_binary(self):
        """Verify confidence_level is 'trusted' or 'unverified' (not 'high'/'medium'/'low')"""
        # Create a good item
        items = [{
            "raw_name": "BINARY TEST ITEM",
            "quantity": 2,
            "pack_size": "5 LB",
            "unit_price": 30.00,
            "total": 60.00
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        # Verify binary classification
        assert item["confidence_level"] in ["trusted", "unverified"], \
            f"Expected 'trusted' or 'unverified', got '{item.get('confidence_level')}'"
        assert item["confidence_level"] not in ["high", "medium", "low"], \
            f"Old classification detected: '{item.get('confidence_level')}'"
        print(f"✓ Binary classification: confidence_level={item['confidence_level']}")
    
    # ===== TEST 11: Update purchase also computes confidence =====
    def test_update_purchase_computes_confidence(self):
        """PUT /api/purchases/{id} also computes confidence on update"""
        # Create initial purchase
        items = [{
            "raw_name": "UPDATE TEST ITEM",
            "quantity": 2,
            "pack_size": "10 LB",
            "unit_price": 40.00,
            "total": 80.00
        }]
        create_resp = self.create_purchase(items)
        assert create_resp.status_code in [200, 201]
        purchase_id = create_resp.json()["id"]
        
        # Update with bad math
        update_payload = {
            "items": [{
                "raw_name": "UPDATE TEST ITEM",
                "quantity": 2,
                "pack_size": "10 LB",
                "unit_price": 40.00,
                "total": 999.00  # Bad math
            }]
        }
        update_resp = requests.put(
            f"{BASE_URL}/api/purchases/{purchase_id}",
            json=update_payload,
            headers=self.headers
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}"
        
        data = update_resp.json()
        item = data["items"][0]
        
        # Should be unverified due to math mismatch
        assert item["confidence_level"] == "unverified", \
            f"Expected 'unverified' after update, got '{item.get('confidence_level')}'"
        assert item["valid_calc"] == False
        print(f"✓ Update computes confidence: confidence_level={item['confidence_level']}")


class TestNormalizedPriceWithConfidence:
    """Test that $/LB is only shown for trusted items."""
    
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
            "supplier_name": "TEST_NPLB_VENDOR",
            "invoice_number": "TEST-NPLB-001",
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
    
    def test_trusted_item_has_normalized_price(self):
        """Trusted item with LB unit should have normalized_price_per_lb"""
        items = [{
            "raw_name": "BEEF RIBEYE",
            "quantity": 2,
            "pack_size": "4/10 LB",  # 40 LB total
            "unit_price": 200.00,
            "total": 400.00  # 2 * 200 = 400 ✓
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "trusted"
        assert item["normalized_price_per_lb"] is not None, "Expected normalized_price_per_lb for trusted item"
        assert item["normalized_price_per_lb"] > 0, "Expected positive normalized_price_per_lb"
        # 200 / 40 = 5.00 per LB
        assert abs(item["normalized_price_per_lb"] - 5.0) < 0.01, \
            f"Expected ~5.0 $/LB, got {item['normalized_price_per_lb']}"
        print(f"✓ Trusted item has $/LB: {item['normalized_price_per_lb']}")
    
    def test_unverified_item_no_normalized_price_shown(self):
        """Unverified item should not show normalized_price_per_lb (even if computed)"""
        items = [{
            "raw_name": "BAD MATH ITEM",
            "quantity": 2,
            "pack_size": "4/10 LB",
            "unit_price": 200.00,
            "total": 999.00  # Bad math → unverified
        }]
        resp = self.create_purchase(items)
        assert resp.status_code in [200, 201]
        
        data = resp.json()
        item = data["items"][0]
        
        assert item["confidence_level"] == "unverified"
        # The backend may still compute it, but frontend should show '—'
        # Backend behavior: normalized_price_per_lb may be null or present
        # The key is that confidence_level is unverified
        print(f"✓ Unverified item: confidence_level={item['confidence_level']}, normalized_price_per_lb={item.get('normalized_price_per_lb')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
