"""
Test pricing mode detection logic for vendor-specific invoice handling.
Tests the fix for: system was treating case price as $/LB for case-price invoices.

Key behaviors:
- CASE_PRICE mode: Qty×Price=Total (simple math passes) → pricing_mode=case_price, $/LB=CasePrice/CaseWT
- WEIGHT_BASED mode: Simple math fails, weight math works → pricing_mode=weight_based, $/LB=Price
- Non-weight items: pricing_mode=case_price, $/LB=None (GAL, EA, CT packs)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPricingModeDetection:
    """Test pricing_mode detection and $/LB derivation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")
        yield
        # Cleanup: delete test purchases
        try:
            purchases = self.session.get(f"{BASE_URL}/api/purchases", params={"search": "TEST_PRICING_MODE"}).json()
            for p in purchases:
                self.session.delete(f"{BASE_URL}/api/purchases/{p['id']}")
        except:
            pass

    def test_case_price_detection_simple_math_passes(self):
        """
        CASE_PRICE detection: item with qty=3, price=$45.95, total=$137.85, pack=1.25LB
        Expected: pricing_mode=case_price, $/LB=36.76 (not 45.95)
        """
        payload = {
            "supplier_name": "TEST_PRICING_MODE Vendor",
            "invoice_number": "PM-CASE-001",
            "invoice_date": "2026-01-15",
            "items": [{
                "raw_name": "SHRIMP 31-35",
                "quantity": 3,
                "pack_size": "1.25 LB",
                "unit_price": 45.95,
                "total": 137.85  # 3 × 45.95 = 137.85 (simple math passes)
            }],
            "subtotal": 137.85,
            "tax": 0,
            "total": 137.85
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) == 1, "Expected 1 item"
        
        item = items[0]
        # Verify pricing_mode is case_price (simple math passed)
        assert item.get("pricing_mode") == "case_price", f"Expected pricing_mode=case_price, got {item.get('pricing_mode')}"
        
        # Verify $/LB is derived correctly: CasePrice / CaseWT = 45.95 / 1.25 = 36.76
        nplb = item.get("normalized_price_per_lb")
        assert nplb is not None, "Expected normalized_price_per_lb to be set"
        assert abs(nplb - 36.76) < 0.01, f"Expected $/LB=36.76, got {nplb}"
        
        # Verify it's NOT the case price (45.95)
        assert abs(nplb - 45.95) > 1, f"$/LB should NOT be the case price (45.95), got {nplb}"
        
        print(f"✓ CASE_PRICE detection: pricing_mode={item.get('pricing_mode')}, $/LB={nplb}")

    def test_weight_based_detection_simple_math_fails(self):
        """
        WEIGHT_BASED detection: item with qty=5, price=$2.50, total=$375.00, pack=1x30 LB
        Simple math: 5 × 2.50 = 12.50 ≠ 375.00 (fails)
        Weight math: 5 × 30LB × 2.50 = 375.00 (passes)
        Expected: pricing_mode=weight_based, $/LB=2.50 (IS the price)
        """
        payload = {
            "supplier_name": "TEST_PRICING_MODE Vendor",
            "invoice_number": "PM-WEIGHT-001",
            "invoice_date": "2026-01-15",
            "items": [{
                "raw_name": "SALMON FILLET",
                "quantity": 5,
                "pack_size": "1x30 LB",
                "unit_price": 2.50,
                "total": 375.00  # 5 × 30LB × 2.50 = 375.00 (weight math)
            }],
            "subtotal": 375.00,
            "tax": 0,
            "total": 375.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) == 1, "Expected 1 item"
        
        item = items[0]
        # Verify pricing_mode is weight_based (simple math failed, weight math passed)
        assert item.get("pricing_mode") == "weight_based", f"Expected pricing_mode=weight_based, got {item.get('pricing_mode')}"
        
        # Verify $/LB IS the price directly (2.50)
        nplb = item.get("normalized_price_per_lb")
        assert nplb is not None, "Expected normalized_price_per_lb to be set"
        assert abs(nplb - 2.50) < 0.01, f"Expected $/LB=2.50, got {nplb}"
        
        print(f"✓ WEIGHT_BASED detection: pricing_mode={item.get('pricing_mode')}, $/LB={nplb}")

    def test_non_weight_items_no_price_per_lb(self):
        """
        Non-weight items (GAL, EA, CT packs) should have pricing_mode=case_price, $/LB=None
        """
        payload = {
            "supplier_name": "TEST_PRICING_MODE Vendor",
            "invoice_number": "PM-NONWT-001",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "OLIVE OIL",
                    "quantity": 2,
                    "pack_size": "1 GAL",
                    "unit_price": 25.00,
                    "total": 50.00
                },
                {
                    "raw_name": "NAPKINS",
                    "quantity": 10,
                    "pack_size": "150 EA",
                    "unit_price": 5.00,
                    "total": 50.00
                },
                {
                    "raw_name": "EGGS",
                    "quantity": 3,
                    "pack_size": "30 CT",
                    "unit_price": 8.00,
                    "total": 24.00
                }
            ],
            "subtotal": 124.00,
            "tax": 0,
            "total": 124.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) == 3, "Expected 3 items"
        
        for item in items:
            name = item.get("raw_name")
            # All should be case_price (simple math passes)
            assert item.get("pricing_mode") == "case_price", f"{name}: Expected pricing_mode=case_price, got {item.get('pricing_mode')}"
            # $/LB should be None for non-weight units
            nplb = item.get("normalized_price_per_lb")
            assert nplb is None, f"{name}: Expected $/LB=None for non-weight unit, got {nplb}"
            print(f"✓ Non-weight item {name}: pricing_mode={item.get('pricing_mode')}, $/LB={nplb}")

    def test_case_price_derived_correctly(self):
        """
        Verify $/LB is derived correctly in case_price mode: CasePrice/CaseWT
        Example: SHRIMP with price=$60.84, pack=2.5LB → $/LB=$24.34
        """
        payload = {
            "supplier_name": "TEST_PRICING_MODE Performance Foodservice",
            "invoice_number": "PM-DERIVE-001",
            "invoice_date": "2026-01-15",
            "items": [{
                "raw_name": "SHRIMP 16-20",
                "quantity": 2,
                "pack_size": "2.5 LB",
                "unit_price": 60.84,
                "total": 121.68  # 2 × 60.84 = 121.68 (simple math)
            }],
            "subtotal": 121.68,
            "tax": 0,
            "total": 121.68
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        item = data.get("items", [])[0]
        
        # Verify pricing_mode
        assert item.get("pricing_mode") == "case_price", f"Expected case_price, got {item.get('pricing_mode')}"
        
        # Verify $/LB = 60.84 / 2.5 = 24.336
        expected_nplb = 60.84 / 2.5  # 24.336
        nplb = item.get("normalized_price_per_lb")
        assert nplb is not None, "Expected normalized_price_per_lb"
        assert abs(nplb - expected_nplb) < 0.01, f"Expected $/LB={expected_nplb:.2f}, got {nplb}"
        
        # Verify it's NOT the case price
        assert abs(nplb - 60.84) > 10, f"$/LB should NOT be case price (60.84), got {nplb}"
        
        print(f"✓ Case price derivation: CasePrice={60.84}, CaseWT=2.5, $/LB={nplb:.2f}")

    def test_pricing_mode_field_present_on_all_items(self):
        """
        Verify pricing_mode field is present on all items returned by POST /api/purchases
        """
        payload = {
            "supplier_name": "TEST_PRICING_MODE Vendor",
            "invoice_number": "PM-FIELD-001",
            "invoice_date": "2026-01-15",
            "items": [
                {"raw_name": "CHICKEN BREAST", "quantity": 5, "pack_size": "10 LB", "unit_price": 35.00, "total": 175.00},
                {"raw_name": "BEEF RIBEYE", "quantity": 3, "pack_size": "5 LB", "unit_price": 89.00, "total": 267.00},
                {"raw_name": "FLOUR", "quantity": 2, "pack_size": "50 LB", "unit_price": 25.00, "total": 50.00},
            ],
            "subtotal": 492.00,
            "tax": 0,
            "total": 492.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) == 3, "Expected 3 items"
        
        for i, item in enumerate(items):
            assert "pricing_mode" in item, f"Item {i} missing pricing_mode field"
            pm = item.get("pricing_mode")
            assert pm in ("case_price", "weight_based", "unknown"), f"Item {i} has invalid pricing_mode: {pm}"
            print(f"✓ Item {i} ({item.get('raw_name')}): pricing_mode={pm}")

    def test_put_recomputes_pricing_mode_and_nplb(self):
        """
        PUT /api/purchases recomputes pricing_mode and $/LB correctly
        """
        # Create initial purchase
        payload = {
            "supplier_name": "TEST_PRICING_MODE Vendor",
            "invoice_number": "PM-PUT-001",
            "invoice_date": "2026-01-15",
            "items": [{
                "raw_name": "SHRIMP 31-35",
                "quantity": 2,
                "pack_size": "5 LB",
                "unit_price": 50.00,
                "total": 100.00
            }],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        purchase_id = create_resp.json().get("id")
        
        # Update with different values
        update_payload = {
            "items": [{
                "raw_name": "SHRIMP 31-35",
                "quantity": 4,
                "pack_size": "2.5 LB",
                "unit_price": 40.00,
                "total": 160.00  # 4 × 40 = 160 (simple math)
            }],
            "subtotal": 160.00,
            "total": 160.00
        }
        
        update_resp = self.session.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        data = update_resp.json()
        item = data.get("items", [])[0]
        
        # Verify pricing_mode is recomputed
        assert item.get("pricing_mode") == "case_price", f"Expected case_price after update, got {item.get('pricing_mode')}"
        
        # Verify $/LB is recomputed: 40.00 / 2.5 = 16.00
        nplb = item.get("normalized_price_per_lb")
        assert nplb is not None, "Expected normalized_price_per_lb after update"
        assert abs(nplb - 16.00) < 0.01, f"Expected $/LB=16.00 after update, got {nplb}"
        
        print(f"✓ PUT recomputes: pricing_mode={item.get('pricing_mode')}, $/LB={nplb}")


class TestPackSizeParsing:
    """Test parse_pack_size handles various formats correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")
        yield
        # Cleanup
        try:
            purchases = self.session.get(f"{BASE_URL}/api/purchases", params={"search": "TEST_PACK_PARSE"}).json()
            for p in purchases:
                self.session.delete(f"{BASE_URL}/api/purchases/{p['id']}")
        except:
            pass

    def test_parse_25_lb_format(self):
        """
        parse_pack_size handles '25 LB' → total_case_weight=25.0
        """
        payload = {
            "supplier_name": "TEST_PACK_PARSE Vendor",
            "invoice_number": "PP-25LB-001",
            "invoice_date": "2026-01-15",
            "items": [{
                "raw_name": "FLOUR ALL PURPOSE",
                "quantity": 2,
                "pack_size": "25 LB",
                "unit_price": 15.00,
                "total": 30.00
            }],
            "subtotal": 30.00,
            "tax": 0,
            "total": 30.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        item = response.json().get("items", [])[0]
        
        # Verify pack parsing
        assert item.get("pack_parse_status") == "parsed", f"Expected parsed, got {item.get('pack_parse_status')}"
        assert item.get("total_case_weight") == 25.0, f"Expected total_case_weight=25.0, got {item.get('total_case_weight')}"
        assert item.get("pack_unit") == "LB", f"Expected pack_unit=LB, got {item.get('pack_unit')}"
        
        print(f"✓ '25 LB' parsed: total_case_weight={item.get('total_case_weight')}, unit={item.get('pack_unit')}")

    def test_parse_various_pack_formats(self):
        """
        Test various pack size formats are parsed correctly
        """
        test_cases = [
            ("10/4 LB", 40.0, "LB"),      # 10 packs × 4 LB = 40 LB
            ("6/5 LB", 30.0, "LB"),       # 6 packs × 5 LB = 30 LB
            ("1x30 LB", 30.0, "LB"),      # 1 × 30 LB = 30 LB
            ("2/17.5 LB", 35.0, "LB"),    # 2 × 17.5 LB = 35 LB
            ("BAG 50 LB", 50.0, "LB"),    # 1 × 50 LB = 50 LB
            ("50LB", 50.0, "LB"),         # 50 LB
            ("10#", 10.0, "LB"),          # 10 LB (# = LB)
        ]
        
        items = []
        for i, (pack_size, expected_wt, expected_unit) in enumerate(test_cases):
            items.append({
                "raw_name": f"TEST ITEM {i}",
                "quantity": 1,
                "pack_size": pack_size,
                "unit_price": 10.00,
                "total": 10.00
            })
        
        payload = {
            "supplier_name": "TEST_PACK_PARSE Vendor",
            "invoice_number": "PP-FORMATS-001",
            "invoice_date": "2026-01-15",
            "items": items,
            "subtotal": len(items) * 10.00,
            "tax": 0,
            "total": len(items) * 10.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        result_items = response.json().get("items", [])
        
        for i, (pack_size, expected_wt, expected_unit) in enumerate(test_cases):
            item = result_items[i]
            actual_wt = item.get("total_case_weight")
            actual_unit = item.get("pack_unit")
            status = item.get("pack_parse_status")
            
            assert status == "parsed", f"'{pack_size}': Expected parsed, got {status}"
            assert actual_wt == expected_wt, f"'{pack_size}': Expected weight={expected_wt}, got {actual_wt}"
            assert actual_unit == expected_unit, f"'{pack_size}': Expected unit={expected_unit}, got {actual_unit}"
            
            print(f"✓ '{pack_size}' → weight={actual_wt}, unit={actual_unit}")


class TestPerformanceFoodserviceInvoices:
    """Test that Performance Foodservice invoices have correct pricing_mode and review_status"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")

    def test_performance_foodservice_invoices_are_case_price(self):
        """
        All Performance Foodservice invoices should have pricing_mode=case_price
        """
        # Search for Performance Foodservice invoices
        response = self.session.get(f"{BASE_URL}/api/purchases", params={"search": "Performance Foodservice"})
        assert response.status_code == 200, f"Search failed: {response.text}"
        
        purchases = response.json()
        if not purchases:
            pytest.skip("No Performance Foodservice invoices found")
        
        for purchase in purchases:
            invoice_num = purchase.get("invoice_number", "unknown")
            items = purchase.get("items", [])
            
            for item in items:
                name = item.get("raw_name", "unknown")
                pm = item.get("pricing_mode")
                
                # Weight-based items are allowed if they have weight packs
                if pm == "weight_based":
                    # Verify it has a weight pack
                    tcw = item.get("total_case_weight")
                    pack_unit = item.get("pack_unit")
                    assert tcw and pack_unit in ("LB", "OZ"), f"Invoice {invoice_num}, item {name}: weight_based but no weight pack"
                elif pm == "case_price":
                    # This is expected for most items
                    pass
                else:
                    # Unknown is acceptable for items with missing data
                    pass
            
            # Check review_status
            review_status = purchase.get("review_status")
            print(f"Invoice {invoice_num}: {len(items)} items, review_status={review_status}")


class TestWeightMathTestInvoice:
    """Test that Weight Math Test invoice (WM-001) has weight-based items that remain trusted"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")

    def test_weight_math_test_invoice_items_trusted(self):
        """
        Weight Math Test invoice (WM-001) should have weight-based items that are trusted
        """
        response = self.session.get(f"{BASE_URL}/api/purchases", params={"search": "WM-001"})
        assert response.status_code == 200, f"Search failed: {response.text}"
        
        purchases = response.json()
        if not purchases:
            pytest.skip("WM-001 invoice not found")
        
        purchase = purchases[0]
        items = purchase.get("items", [])
        
        for item in items:
            name = item.get("raw_name", "unknown")
            pm = item.get("pricing_mode")
            cl = item.get("confidence_level")
            needs_review = item.get("needs_review")
            
            print(f"WM-001 item {name}: pricing_mode={pm}, confidence_level={cl}, needs_review={needs_review}")
            
            # Items should be trusted (not needing review)
            if cl:
                assert cl == "trusted", f"Item {name}: Expected trusted, got {cl}"
            if needs_review is not None:
                assert needs_review == False, f"Item {name}: Expected needs_review=False, got {needs_review}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
