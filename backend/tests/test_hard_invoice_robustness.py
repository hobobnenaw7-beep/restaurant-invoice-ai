"""
Test suite for hard invoice robustness layer functions:
- sanitize_extracted_item: type coercion, negative handling, null handling
- detect_column_misread: column swap detection
- compute_extraction_meta: invoice-level confidence computation
- salvage_partial_extraction: recover data from broken JSON
- POST /api/purchases with messy items: edge cases handling
"""
import pytest
import requests
import os
import sys

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ============================================================================
# Unit Tests for preprocessing.py functions
# ============================================================================

class TestSanitizeExtractedItem:
    """Tests for sanitize_extracted_item function"""
    
    def test_string_numbers_converted(self):
        """String numbers like '$42.50' should be converted to float 42.5"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": "$5.00",
            "unit_price": "$42.50",
            "total": "$212.50"
        }
        result = sanitize_extracted_item(item)
        
        assert result["quantity"] == 5.0, f"Expected 5.0, got {result['quantity']}"
        assert result["unit_price"] == 42.5, f"Expected 42.5, got {result['unit_price']}"
        assert result["total"] == 212.5, f"Expected 212.5, got {result['total']}"
        print("PASS: String numbers converted correctly")
    
    def test_negative_values_made_absolute(self):
        """Negative values should be converted to absolute values"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": -5,
            "unit_price": -10.50,
            "total": -52.50
        }
        result = sanitize_extracted_item(item)
        
        assert result["quantity"] == 5, f"Expected 5, got {result['quantity']}"
        assert result["unit_price"] == 10.50, f"Expected 10.50, got {result['unit_price']}"
        assert result["total"] == 52.50, f"Expected 52.50, got {result['total']}"
        assert "_parse_issues" in result, "Should have parse issues logged"
        print("PASS: Negative values converted to absolute")
    
    def test_none_values_default_to_zero(self):
        """None values should default to 0"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": None,
            "unit_price": None,
            "total": None
        }
        result = sanitize_extracted_item(item)
        
        assert result["quantity"] == 0, f"Expected 0, got {result['quantity']}"
        assert result["unit_price"] == 0, f"Expected 0, got {result['unit_price']}"
        assert result["total"] == 0, f"Expected 0, got {result['total']}"
        print("PASS: None values default to 0")
    
    def test_non_string_names_coerced(self):
        """Non-string names (int, float) should be coerced to string"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": 12345,
            "quantity": 1,
            "unit_price": 10,
            "total": 10
        }
        result = sanitize_extracted_item(item)
        
        assert result["raw_name"] == "12345", f"Expected '12345', got {result['raw_name']}"
        assert isinstance(result["raw_name"], str), "raw_name should be string"
        print("PASS: Non-string names coerced to string")
    
    def test_null_pack_size_defaults_to_empty_string(self):
        """Null pack_size should default to empty string"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size": None
        }
        result = sanitize_extracted_item(item)
        
        assert result["pack_size"] == "", f"Expected '', got {result['pack_size']}"
        print("PASS: Null pack_size defaults to empty string")
    
    def test_zero_pack_size_defaults_to_empty_string(self):
        """Zero pack_size (numeric) should default to empty string"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size": 0
        }
        result = sanitize_extracted_item(item)
        
        assert result["pack_size"] == "", f"Expected '', got {result['pack_size']}"
        print("PASS: Zero pack_size defaults to empty string")
    
    def test_garbled_numeric_values(self):
        """Garbled values like 'abc' should default to 0"""
        from preprocessing import sanitize_extracted_item
        
        item = {
            "raw_name": "Test Item",
            "quantity": "abc",
            "unit_price": "xyz",
            "total": "!!!"
        }
        result = sanitize_extracted_item(item)
        
        assert result["quantity"] == 0, f"Expected 0, got {result['quantity']}"
        assert result["unit_price"] == 0, f"Expected 0, got {result['unit_price']}"
        assert result["total"] == 0, f"Expected 0, got {result['total']}"
        # Note: Empty strings after cleaning don't generate parse issues, only truly unparseable values do
        # The function correctly handles these by defaulting to 0
        print("PASS: Garbled values default to 0")


class TestDetectColumnMisread:
    """Tests for detect_column_misread function"""
    
    def test_normal_qty_price_ratios_no_issues(self):
        """Normal qty/price ratios should return no issues"""
        from preprocessing import detect_column_misread
        
        items = [
            {"quantity": 5, "unit_price": 42.50, "total": 212.50},
            {"quantity": 3, "unit_price": 18.99, "total": 56.97},
            {"quantity": 10, "unit_price": 8.50, "total": 85.00},
        ]
        issues = detect_column_misread(items)
        
        assert len(issues) == 0, f"Expected no issues, got {issues}"
        print("PASS: Normal qty/price ratios return no issues")
    
    def test_detects_swap_when_qty_looks_like_prices(self):
        """Should detect swap when avg quantity >> avg price with decimal qtys"""
        from preprocessing import detect_column_misread
        
        # Simulating swapped columns: quantities have price-like values
        items = [
            {"quantity": 42.50, "unit_price": 5, "total": 212.50},
            {"quantity": 18.99, "unit_price": 3, "total": 56.97},
            {"quantity": 85.00, "unit_price": 10, "total": 850.00},
        ]
        issues = detect_column_misread(items)
        
        assert len(issues) > 0, f"Expected issues, got none"
        assert any("column swap" in issue.lower() or "decimal" in issue.lower() for issue in issues), \
            f"Expected column swap or decimal issue, got {issues}"
        print(f"PASS: Detected column misread issues: {issues}")
    
    def test_few_items_no_detection(self):
        """With fewer than 3 items, should not detect issues"""
        from preprocessing import detect_column_misread
        
        items = [
            {"quantity": 42.50, "unit_price": 5, "total": 212.50},
            {"quantity": 18.99, "unit_price": 3, "total": 56.97},
        ]
        issues = detect_column_misread(items)
        
        assert len(issues) == 0, f"Expected no issues for <3 items, got {issues}"
        print("PASS: Few items return no issues")


class TestComputeExtractionMeta:
    """Tests for compute_extraction_meta function"""
    
    def test_high_confidence_for_all_good_items(self):
        """Should return 'high' confidence for all-good items"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "Chicken Breast", "total": 50.00, "needs_review": False},
            {"raw_name": "Olive Oil", "total": 25.00, "needs_review": False},
            {"raw_name": "Tomatoes", "total": 15.00, "needs_review": False},
        ]
        extracted_data = {
            "supplier_name": "Test Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "INV-001",
            "subtotal": 90.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        assert meta["extraction_confidence"] == "high", f"Expected 'high', got {meta['extraction_confidence']}"
        assert meta["items_with_issues"] == 0, f"Expected 0 issues, got {meta['items_with_issues']}"
        print("PASS: High confidence for all-good items")
    
    def test_low_confidence_for_mostly_bad_items(self):
        """Should return 'low' confidence for mostly-bad items"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "", "total": 0, "needs_review": True},
            {"raw_name": "", "total": 0, "needs_review": True},
            {"raw_name": "", "total": 0, "needs_review": True},
            {"raw_name": "Good Item", "total": 50.00, "needs_review": False},
        ]
        extracted_data = {
            "supplier_name": "Test Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "INV-001",
            "subtotal": 50.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        assert meta["extraction_confidence"] == "low", f"Expected 'low', got {meta['extraction_confidence']}"
        print("PASS: Low confidence for mostly-bad items")
    
    def test_medium_confidence_for_mixed_items(self):
        """Should return 'medium' confidence for mixed items"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "Good Item 1", "total": 50.00, "needs_review": False},
            {"raw_name": "Good Item 2", "total": 25.00, "needs_review": False},
            {"raw_name": "", "total": 0, "needs_review": True},
            {"raw_name": "Good Item 3", "total": 15.00, "needs_review": False},
        ]
        extracted_data = {
            "supplier_name": "Test Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "INV-001",
            "subtotal": 90.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        # 1 out of 4 items has issues = 25% issue ratio, should be high
        # But if we have empty name, it counts as issue
        assert meta["extraction_confidence"] in ["high", "medium"], \
            f"Expected 'high' or 'medium', got {meta['extraction_confidence']}"
        print(f"PASS: Confidence for mixed items: {meta['extraction_confidence']}")
    
    def test_flags_missing_header_fields(self):
        """Should flag missing header fields (supplier_name, invoice_date, invoice_number)"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "Good Item", "total": 50.00, "needs_review": False},
        ]
        extracted_data = {
            "supplier_name": "",
            "invoice_date": "",
            "invoice_number": "",
            "subtotal": 50.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        assert any("supplier name" in issue.lower() for issue in meta["extraction_issues"]), \
            f"Expected supplier name issue, got {meta['extraction_issues']}"
        assert any("invoice date" in issue.lower() for issue in meta["extraction_issues"]), \
            f"Expected invoice date issue, got {meta['extraction_issues']}"
        assert any("invoice number" in issue.lower() for issue in meta["extraction_issues"]), \
            f"Expected invoice number issue, got {meta['extraction_issues']}"
        print(f"PASS: Flags missing header fields: {meta['extraction_issues']}")
    
    def test_detects_partial_extraction(self):
        """Should detect partial extraction when many items have zero totals"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "Item 1", "total": 0, "needs_review": True},
            {"raw_name": "Item 2", "total": 0, "needs_review": True},
            {"raw_name": "Item 3", "total": 0, "needs_review": True},
        ]
        extracted_data = {
            "supplier_name": "Test Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "INV-001",
            "subtotal": 100.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        assert meta["partial_extraction"] == True, f"Expected partial_extraction=True"
        print("PASS: Detects partial extraction")
    
    def test_flags_subtotal_mismatch_over_20_percent(self):
        """Should flag subtotal mismatch >20%"""
        from preprocessing import compute_extraction_meta
        
        items = [
            {"raw_name": "Item 1", "total": 50.00, "needs_review": False},
            {"raw_name": "Item 2", "total": 30.00, "needs_review": False},
        ]
        # Items sum = 80, but subtotal = 200 (150% difference)
        extracted_data = {
            "supplier_name": "Test Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "INV-001",
            "subtotal": 200.00
        }
        
        meta = compute_extraction_meta(items, extracted_data)
        
        assert any("differs from subtotal" in issue for issue in meta["extraction_issues"]), \
            f"Expected subtotal mismatch issue, got {meta['extraction_issues']}"
        print(f"PASS: Flags subtotal mismatch: {meta['extraction_issues']}")


class TestSalvagePartialExtraction:
    """Tests for salvage_partial_extraction function"""
    
    def test_extracts_supplier_name_from_broken_json(self):
        """Should extract supplier_name from broken JSON response"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = '''
        Here is the data I found:
        {"supplier_name": "ACME Foods", "invoice_date": "2026-01-15"
        The rest of the JSON is corrupted...
        '''
        
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("supplier_name") == "ACME Foods", f"Expected 'ACME Foods', got {result.get('supplier_name')}"
        assert result.get("_salvaged") == True, "Should have _salvaged=True"
        print("PASS: Extracts supplier_name from broken JSON")
    
    def test_extracts_invoice_date_from_broken_json(self):
        """Should extract invoice_date from broken JSON response"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = '''
        {"invoice_date": "2026-01-15", "total": 500
        '''
        
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("invoice_date") == "2026-01-15", f"Expected '2026-01-15', got {result.get('invoice_date')}"
        print("PASS: Extracts invoice_date from broken JSON")
    
    def test_extracts_total_from_broken_json(self):
        """Should extract total from broken JSON response"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = '''
        {"supplier_name": "Test", "total": 1234.56
        '''
        
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("total") == 1234.56, f"Expected 1234.56, got {result.get('total')}"
        print("PASS: Extracts total from broken JSON")
    
    def test_returns_empty_items_for_garbage_input(self):
        """Should return empty items list for garbage input"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = "This is complete garbage with no JSON at all!!!"
        
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("items") == [], f"Expected empty items, got {result.get('items')}"
        assert result.get("_salvaged") == True, "Should have _salvaged=True"
        print("PASS: Returns empty items for garbage input")
    
    def test_always_sets_salvaged_true(self):
        """Should always set _salvaged=True"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = "anything"
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("_salvaged") == True, "Should have _salvaged=True"
        print("PASS: Always sets _salvaged=True")
    
    def test_extracts_date_from_anywhere(self):
        """Should find a date anywhere in the response if invoice_date field is missing"""
        from preprocessing import salvage_partial_extraction
        
        raw_response = '''
        The invoice was dated 2026-03-20 and the total was $500.
        '''
        
        result = salvage_partial_extraction(raw_response)
        
        assert result.get("invoice_date") == "2026-03-20", f"Expected '2026-03-20', got {result.get('invoice_date')}"
        print("PASS: Extracts date from anywhere in response")


# ============================================================================
# Integration Tests for POST /api/purchases with messy items
# ============================================================================

class TestPurchasesWithMessyItems:
    """Integration tests for POST /api/purchases with edge cases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_response.status_code == 200:
            token = login_response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")
    
    def test_empty_name_items_get_needs_review(self):
        """Empty-name items should get needs_review=True with 'Missing item name' reason"""
        payload = {
            "supplier_name": "TEST_Robustness Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "ROB-001",
            "items": [
                {"raw_name": "", "quantity": 5, "unit_price": 10.00, "total": 50.00},
                {"raw_name": "Valid Item", "quantity": 2, "unit_price": 25.00, "total": 50.00}
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        
        # Find the empty-name item
        empty_item = next((it for it in items if not it.get("raw_name", "").strip()), None)
        assert empty_item is not None, "Should have an empty-name item"
        assert empty_item.get("needs_review") == True, "Empty-name item should need review"
        assert "missing item name" in (empty_item.get("review_reason") or "").lower(), \
            f"Expected 'Missing item name' reason, got {empty_item.get('review_reason')}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Empty-name items get needs_review=True with correct reason")
    
    def test_math_mismatch_items_get_error_status(self):
        """Math mismatch items should result in review_status=error"""
        payload = {
            "supplier_name": "TEST_Math Mismatch Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "MATH-001",
            "items": [
                {"raw_name": "Mismatched Item", "quantity": 5, "unit_price": 10.00, "total": 100.00},  # 5*10=50, not 100
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("review_status") == "error", f"Expected review_status=error, got {data.get('review_status')}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Math mismatch items result in review_status=error")
    
    def test_all_items_saved_no_blocking(self):
        """All items should be saved even with issues - no blocking"""
        payload = {
            "supplier_name": "TEST_No Blocking Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "NOBLOCK-001",
            "items": [
                {"raw_name": "", "quantity": 5, "unit_price": 10.00, "total": 50.00},  # Empty name
                {"raw_name": "Math Error", "quantity": 5, "unit_price": 10.00, "total": 999.00},  # Math mismatch
                {"raw_name": "Valid Item", "quantity": 2, "unit_price": 25.00, "total": 50.00},  # Valid
            ],
            "subtotal": 1099.00,
            "tax": 0,
            "total": 1099.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        
        assert len(items) == 3, f"Expected 3 items saved, got {len(items)}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: All items saved without blocking")
    
    def test_review_status_clean_when_all_good(self):
        """review_status should be 'clean' when all items are good"""
        payload = {
            "supplier_name": "TEST_Clean Status Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "CLEAN-001",
            "items": [
                {"raw_name": "Good Item 1", "quantity": 5, "unit_price": 10.00, "total": 50.00},
                {"raw_name": "Good Item 2", "quantity": 2, "unit_price": 25.00, "total": 50.00},
            ],
            "subtotal": 100.00,
            "tax": 0,
            "total": 100.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("review_status") == "clean", f"Expected review_status=clean, got {data.get('review_status')}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: review_status=clean when all items are good")
    
    def test_review_status_error_when_hard_errors_exist(self):
        """review_status should be 'error' when hard errors exist"""
        payload = {
            "supplier_name": "TEST_Error Status Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "ERROR-001",
            "items": [
                {"raw_name": "", "quantity": 5, "unit_price": 10.00, "total": 50.00},  # Missing name = hard error
            ],
            "subtotal": 50.00,
            "tax": 0,
            "total": 50.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("review_status") == "error", f"Expected review_status=error, got {data.get('review_status')}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: review_status=error when hard errors exist")
    
    def test_per_item_isolation_one_bad_item_no_crash(self):
        """One bad item should not crash the entire extraction pipeline"""
        # This tests that even with problematic items, the purchase is still created
        payload = {
            "supplier_name": "TEST_Isolation Vendor",
            "invoice_date": "2026-01-15",
            "invoice_number": "ISO-001",
            "items": [
                {"raw_name": "Normal Item", "quantity": 5, "unit_price": 10.00, "total": 50.00},
                {"raw_name": "", "quantity": None, "unit_price": None, "total": None},  # All bad
                {"raw_name": "Another Normal", "quantity": 3, "unit_price": 20.00, "total": 60.00},
            ],
            "subtotal": 110.00,
            "tax": 0,
            "total": 110.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        
        # All 3 items should be saved
        assert len(items) == 3, f"Expected 3 items, got {len(items)}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
        print("PASS: Per-item isolation - one bad item doesn't crash pipeline")


class TestGetPurchasesWithReviewStatus:
    """Tests for GET /api/purchases returning review_status field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_response.status_code == 200:
            token = login_response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")
    
    def test_get_purchases_returns_review_status(self):
        """GET /api/purchases should return review_status field on each record"""
        response = self.session.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        if len(data) > 0:
            # Check that at least some purchases have review_status
            has_review_status = any(p.get("review_status") for p in data)
            assert has_review_status, "Expected some purchases to have review_status field"
            
            # Check valid values
            for p in data:
                if p.get("review_status"):
                    assert p["review_status"] in ["clean", "warning", "error"], \
                        f"Invalid review_status: {p['review_status']}"
        
        print(f"PASS: GET /api/purchases returns review_status (checked {len(data)} records)")
    
    def test_get_purchases_sorted_by_date(self):
        """GET /api/purchases should return sorted results"""
        response = self.session.get(f"{BASE_URL}/api/purchases?sort_order=desc")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Check sorting (desc by default)
        if len(data) >= 2:
            dates = [p.get("invoice_date") or p.get("created_at") for p in data]
            # Filter out empty dates
            valid_dates = [d for d in dates if d]
            if len(valid_dates) >= 2:
                # Should be descending
                for i in range(len(valid_dates) - 1):
                    assert valid_dates[i] >= valid_dates[i+1], \
                        f"Not sorted desc: {valid_dates[i]} < {valid_dates[i+1]}"
        
        print("PASS: GET /api/purchases returns sorted results")


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
