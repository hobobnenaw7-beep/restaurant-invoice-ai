"""
Test Confidence + Review Layer for OCR/parsing pipeline
Tests validation (qty*price≈total, required fields, pack status) and confidence scoring (100-point scale)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestConfidenceScoring:
    """Test confidence scoring and validation for purchases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed - cannot test")
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        yield
        # Cleanup: delete test purchases
        try:
            purchases = requests.get(f"{BASE_URL}/api/purchases", headers=self.headers).json()
            for p in purchases:
                if p.get("supplier_name", "").startswith("TEST_CONF_"):
                    requests.delete(f"{BASE_URL}/api/purchases/{p['id']}", headers=self.headers)
        except:
            pass

    def test_good_items_high_confidence(self):
        """POST /api/purchases with good items returns confidence_score=100, confidence_level=high"""
        payload = {
            "supplier_name": "TEST_CONF_GoodVendor",
            "invoice_number": "INV-001",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Fresh Tomatoes",
                    "quantity": 10,
                    "pack_size": "10/4 LB",
                    "unit_price": 25.00,
                    "total": 250.00
                },
                {
                    "raw_name": "Organic Lettuce",
                    "quantity": 5,
                    "pack_size": "6/5 LB",
                    "unit_price": 15.00,
                    "total": 75.00
                }
            ],
            "subtotal": 325.00,
            "tax": 26.00,
            "total": 351.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 2, "Expected 2 items"
        
        for item in items:
            # Check confidence fields exist
            assert "confidence_score" in item, f"Missing confidence_score in item: {item}"
            assert "confidence_level" in item, f"Missing confidence_level in item: {item}"
            assert "valid_calc" in item, f"Missing valid_calc in item: {item}"
            assert "validation_errors" in item, f"Missing validation_errors in item: {item}"
            
            # Good items should have high confidence
            assert item["confidence_score"] == 100, f"Expected score 100, got {item['confidence_score']}"
            assert item["confidence_level"] == "high", f"Expected 'high', got {item['confidence_level']}"
            assert item["valid_calc"] == True, f"Expected valid_calc=True, got {item['valid_calc']}"
            assert item["validation_errors"] == [], f"Expected no errors, got {item['validation_errors']}"
        
        print("PASS: Good items return confidence_score=100, confidence_level=high, valid_calc=true")

    def test_bad_math_invalid_calc(self):
        """POST /api/purchases with bad math (qty*price != total) returns valid_calc=false"""
        payload = {
            "supplier_name": "TEST_CONF_BadMath",
            "invoice_number": "INV-002",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Chicken Breast",
                    "quantity": 10,
                    "pack_size": "10/4 LB",
                    "unit_price": 25.00,
                    "total": 300.00  # Should be 250.00 (10 * 25)
                }
            ],
            "subtotal": 300.00,
            "tax": 0,
            "total": 300.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        assert item["valid_calc"] == False, f"Expected valid_calc=False, got {item['valid_calc']}"
        assert len(item["validation_errors"]) > 0, "Expected validation errors for bad math"
        assert any("qty*price" in err or "!=" in err for err in item["validation_errors"]), \
            f"Expected math error message, got {item['validation_errors']}"
        
        # Score should be lower (missing +40 for valid calc)
        assert item["confidence_score"] < 100, f"Expected score < 100, got {item['confidence_score']}"
        
        print(f"PASS: Bad math returns valid_calc=false, errors={item['validation_errors']}, score={item['confidence_score']}")

    def test_missing_fields_lower_confidence(self):
        """POST /api/purchases with missing fields returns lower confidence_score"""
        payload = {
            "supplier_name": "TEST_CONF_MissingFields",
            "invoice_number": "INV-003",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "",  # Missing item name
                    "quantity": 0,   # Missing quantity
                    "pack_size": "",
                    "unit_price": 0, # Missing price
                    "total": 50.00
                }
            ],
            "subtotal": 50.00,
            "tax": 0,
            "total": 50.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        # Should have validation errors for missing fields
        assert len(item["validation_errors"]) > 0, "Expected validation errors for missing fields"
        assert any("missing" in err.lower() for err in item["validation_errors"]), \
            f"Expected 'missing' in errors, got {item['validation_errors']}"
        
        # Score should be low
        assert item["confidence_score"] < 60, f"Expected score < 60 (low), got {item['confidence_score']}"
        assert item["confidence_level"] == "low", f"Expected 'low', got {item['confidence_level']}"
        
        print(f"PASS: Missing fields return lower score={item['confidence_score']}, level={item['confidence_level']}")

    def test_garbled_item_name_lower_confidence(self):
        """POST /api/purchases with garbled item name returns lower confidence"""
        payload = {
            "supplier_name": "TEST_CONF_GarbledName",
            "invoice_number": "INV-004",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "12345678901234567890",  # All digits - garbled
                    "quantity": 5,
                    "pack_size": "10/4 LB",
                    "unit_price": 20.00,
                    "total": 100.00
                }
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        # Should have validation error about garbled name
        assert any("garbled" in err.lower() or "name" in err.lower() for err in item["validation_errors"]), \
            f"Expected name quality error, got {item['validation_errors']}"
        
        # Score should be < 100 (missing +20 for name quality)
        assert item["confidence_score"] < 100, f"Expected score < 100, got {item['confidence_score']}"
        
        print(f"PASS: Garbled name returns score={item['confidence_score']}, errors={item['validation_errors']}")

    def test_failed_pack_size_lower_confidence(self):
        """POST /api/purchases with failed pack_size returns confidence < 100"""
        payload = {
            "supplier_name": "TEST_CONF_FailedPack",
            "invoice_number": "INV-005",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Premium Beef",
                    "quantity": 5,
                    "pack_size": "INVALID_PACK_FORMAT_XYZ",  # Unparseable
                    "unit_price": 50.00,
                    "total": 250.00
                }
            ],
            "subtotal": 250.00,
            "tax": 0,
            "total": 250.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        # Pack parse should fail
        assert item.get("pack_parse_status") == "failed", f"Expected pack_parse_status='failed', got {item.get('pack_parse_status')}"
        
        # Should have validation error about pack parse
        assert any("pack" in err.lower() for err in item["validation_errors"]), \
            f"Expected pack parse error, got {item['validation_errors']}"
        
        # Score should be < 100 (only +5 for failed pack instead of +20)
        assert item["confidence_score"] < 100, f"Expected score < 100, got {item['confidence_score']}"
        
        print(f"PASS: Failed pack returns score={item['confidence_score']}, pack_parse_status={item.get('pack_parse_status')}")

    def test_update_purchase_computes_confidence(self):
        """PUT /api/purchases/{id} also computes confidence on update"""
        # First create a purchase
        create_payload = {
            "supplier_name": "TEST_CONF_Update",
            "invoice_number": "INV-006",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Test Item",
                    "quantity": 5,
                    "pack_size": "10/4 LB",
                    "unit_price": 20.00,
                    "total": 100.00
                }
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/purchases", json=create_payload, headers=self.headers)
        assert create_resp.status_code == 200
        purchase_id = create_resp.json()["id"]
        
        # Now update with new items
        update_payload = {
            "items": [
                {
                    "raw_name": "Updated Item",
                    "quantity": 10,
                    "pack_size": "6/5 LB",
                    "unit_price": 15.00,
                    "total": 150.00
                }
            ],
            "subtotal": 150.00,
            "total": 150.00
        }
        
        update_resp = requests.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload, headers=self.headers)
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        
        data = update_resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        # Confidence fields should be computed on update
        assert "confidence_score" in item, "Missing confidence_score after update"
        assert "confidence_level" in item, "Missing confidence_level after update"
        assert "valid_calc" in item, "Missing valid_calc after update"
        assert item["confidence_score"] == 100, f"Expected score 100, got {item['confidence_score']}"
        
        print(f"PASS: Update computes confidence: score={item['confidence_score']}, level={item['confidence_level']}")

    def test_low_confidence_null_normalized_price(self):
        """Low confidence items show normalized_price_per_lb as null even if pack parsed"""
        payload = {
            "supplier_name": "TEST_CONF_LowConfNull",
            "invoice_number": "INV-007",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "",  # Missing name - will cause low confidence
                    "quantity": 0,   # Missing qty
                    "pack_size": "10/4 LB",  # Valid pack size
                    "unit_price": 0, # Missing price
                    "total": 0       # Missing total
                }
            ],
            "subtotal": 0,
            "tax": 0,
            "total": 0
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        assert len(items) == 1
        
        item = items[0]
        # Should be low confidence
        assert item["confidence_level"] == "low", f"Expected 'low', got {item['confidence_level']}"
        
        # normalized_price_per_lb should be null for low confidence with invalid calc
        # (even though pack_size might parse)
        assert item.get("normalized_price_per_lb") is None, \
            f"Expected null normalized_price_per_lb for low confidence, got {item.get('normalized_price_per_lb')}"
        
        print(f"PASS: Low confidence item has null normalized_price_per_lb")

    def test_confidence_thresholds(self):
        """Test confidence level thresholds: high>=85, medium>=60, low<60"""
        # Test medium confidence (60-84)
        payload = {
            "supplier_name": "TEST_CONF_Medium",
            "invoice_number": "INV-008",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Good Item Name",
                    "quantity": 5,
                    "pack_size": "",  # No pack size - loses some points
                    "unit_price": 20.00,
                    "total": 120.00  # Bad math: 5*20=100, not 120 - loses 40 points
                }
            ],
            "subtotal": 120.00,
            "tax": 0,
            "total": 120.00
        }
        
        resp = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        item = data["items"][0]
        
        # Score breakdown: 0 (bad calc) + 20 (fields) + 15 (no pack) + 20 (name) = 55
        # This should be "low" since < 60
        print(f"Medium test: score={item['confidence_score']}, level={item['confidence_level']}")
        
        # Test that thresholds work correctly
        if item["confidence_score"] >= 85:
            assert item["confidence_level"] == "high"
        elif item["confidence_score"] >= 60:
            assert item["confidence_level"] == "medium"
        else:
            assert item["confidence_level"] == "low"
        
        print(f"PASS: Confidence thresholds work correctly")


class TestConfidenceScoringUnit:
    """Unit tests for validate_and_score_item function"""
    
    def test_scoring_breakdown(self):
        """Test the scoring breakdown: +40 calc, +20 fields, +20 pack, +20 name"""
        # Import the function directly
        import sys
        sys.path.insert(0, '/app/backend')
        from preprocessing import validate_and_score_item, enrich_item_with_pack_size
        
        # Perfect item: should get 100
        perfect_item = {
            "raw_name": "Fresh Tomatoes",
            "quantity": 10,
            "pack_size": "10/4 LB",
            "unit_price": 25.00,
            "total": 250.00
        }
        enrich_item_with_pack_size(perfect_item)
        validate_and_score_item(perfect_item)
        
        assert perfect_item["confidence_score"] == 100, f"Perfect item should score 100, got {perfect_item['confidence_score']}"
        assert perfect_item["confidence_level"] == "high"
        assert perfect_item["valid_calc"] == True
        assert perfect_item["validation_errors"] == []
        
        print(f"PASS: Perfect item scores 100")
        
        # Item with bad math: loses 40 points
        bad_math_item = {
            "raw_name": "Fresh Tomatoes",
            "quantity": 10,
            "pack_size": "10/4 LB",
            "unit_price": 25.00,
            "total": 300.00  # Wrong: should be 250
        }
        enrich_item_with_pack_size(bad_math_item)
        validate_and_score_item(bad_math_item)
        
        assert bad_math_item["confidence_score"] == 60, f"Bad math item should score 60, got {bad_math_item['confidence_score']}"
        assert bad_math_item["valid_calc"] == False
        
        print(f"PASS: Bad math item scores 60 (loses 40 for calc)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
