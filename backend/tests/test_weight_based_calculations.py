"""
Test Weight-Based Invoice Calculations
======================================
Tests the core calculation fix for weight-based invoices:
- Line Total = Qty × Pack Weight (LB) × Price/LB (NOT Qty × Price)
- Pack formats like 1x30, 1x30LB, 12x1LB must parse to LB weight
- Case WT must auto-fill from pack
- $/LB = unit_price directly (not unit_price/case_weight)
- Validate using weight-based math
- Suggest corrections using weight-based formula
- Non-weight items still use simple math
"""

import pytest
import requests
import os
import sys

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')
from preprocessing import parse_pack_size, enrich_item_with_pack_size, validate_and_score_item, compute_review_status, _generate_suggested_fix

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestParsePackSizeNxNFormats:
    """Test parse_pack_size handles NxN formats correctly (Pattern 4b)"""
    
    def test_1x30_parses_to_30LB(self):
        """1x30 -> 30LB (default unit is LB)"""
        result = parse_pack_size("1x30")
        assert result["pack_parse_status"] == "parsed", f"Expected parsed, got {result}"
        assert result["packs_per_case"] == 1
        assert result["weight_per_pack"] == 30.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 30.0
        print("PASS: 1x30 -> 30LB")
    
    def test_1x30LB_parses_to_30LB(self):
        """1x30LB -> 30LB"""
        result = parse_pack_size("1x30LB")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 1
        assert result["weight_per_pack"] == 30.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 30.0
        print("PASS: 1x30LB -> 30LB")
    
    def test_12x1LB_parses_to_12LB(self):
        """12x1LB -> 12LB (12 packs × 1 LB each)"""
        result = parse_pack_size("12x1LB")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 12
        assert result["weight_per_pack"] == 1.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 12.0
        print("PASS: 12x1LB -> 12LB")
    
    def test_1x10LB_parses_to_10LB(self):
        """1x10LB -> 10LB"""
        result = parse_pack_size("1x10LB")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 1
        assert result["weight_per_pack"] == 10.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 10.0
        print("PASS: 1x10LB -> 10LB")
    
    def test_uppercase_X_separator(self):
        """1X30 -> 30LB (uppercase X)"""
        result = parse_pack_size("1X30")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 1
        assert result["weight_per_pack"] == 30.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 30.0
        print("PASS: 1X30 -> 30LB")
    
    def test_1x30_space_LB(self):
        """1x30 LB -> 30LB (with space before unit)"""
        result = parse_pack_size("1x30 LB")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 1
        assert result["weight_per_pack"] == 30.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 30.0
        print("PASS: 1x30 LB -> 30LB")
    
    def test_2x5LB_parses_to_10LB(self):
        """2x5LB -> 10LB (2 packs × 5 LB each)"""
        result = parse_pack_size("2x5LB")
        assert result["pack_parse_status"] == "parsed"
        assert result["packs_per_case"] == 2
        assert result["weight_per_pack"] == 5.0
        assert result["unit"] == "LB"
        assert result["total_case_weight"] == 10.0
        print("PASS: 2x5LB -> 10LB")


class TestWeightBasedValidation:
    """Test weight-based validation: Line Total = Qty × Case WT × $/LB"""
    
    def test_weight_based_trusted_1x30LB(self):
        """Item with pack 1x30LB, qty=1, price=$3.50, total=$105.00 should be TRUSTED (1×30×3.50=105)"""
        item = {
            "raw_name": "CHICKEN BREAST",
            "quantity": 1,
            "pack_size": "1x30LB",
            "unit_price": 3.50,
            "total": 105.00
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["total_case_weight"] == 30.0, f"Expected case weight 30, got {validated.get('total_case_weight')}"
        assert validated["confidence_level"] == "trusted", f"Expected trusted, got {validated['confidence_level']}. Errors: {validated.get('validation_errors')}"
        assert validated["valid_calc"] == True
        print("PASS: 1×30LB×$3.50=$105.00 is TRUSTED")
    
    def test_weight_based_trusted_1x10LB(self):
        """Item with pack 1x10LB, qty=3, price=$8.99, total=$269.70 should be TRUSTED (3×10×8.99=269.70)"""
        item = {
            "raw_name": "SHRIMP 31-35",
            "quantity": 3,
            "pack_size": "1x10LB",
            "unit_price": 8.99,
            "total": 269.70
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["total_case_weight"] == 10.0
        assert validated["confidence_level"] == "trusted", f"Expected trusted, got {validated['confidence_level']}. Errors: {validated.get('validation_errors')}"
        assert validated["valid_calc"] == True
        print("PASS: 3×10LB×$8.99=$269.70 is TRUSTED")
    
    def test_previously_false_mismatch_now_trusted(self):
        """Previously false mismatch: qty=5, pack=1x30, price=$2.50, total=$375.00 should now be TRUSTED (5×30×2.50=375)"""
        item = {
            "raw_name": "BEEF RIBEYE",
            "quantity": 5,
            "pack_size": "1x30",
            "unit_price": 2.50,
            "total": 375.00
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["total_case_weight"] == 30.0
        assert validated["confidence_level"] == "trusted", f"Expected trusted, got {validated['confidence_level']}. Errors: {validated.get('validation_errors')}"
        assert validated["valid_calc"] == True
        print("PASS: 5×30LB×$2.50=$375.00 is TRUSTED (previously was false mismatch)")
    
    def test_non_weight_item_simple_math(self):
        """Non-weight items still use simple math: qty=4, price=$18.75, total=$75.00 should be TRUSTED"""
        item = {
            "raw_name": "OLIVE OIL",
            "quantity": 4,
            "pack_size": "1 GAL",
            "unit_price": 18.75,
            "total": 75.00
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        # GAL is not a weight unit, so simple math applies
        assert validated["confidence_level"] == "trusted", f"Expected trusted, got {validated['confidence_level']}. Errors: {validated.get('validation_errors')}"
        assert validated["valid_calc"] == True
        print("PASS: Non-weight item 4×$18.75=$75.00 is TRUSTED (simple math)")
    
    def test_non_weight_item_EA(self):
        """Non-weight items with EA unit: qty=10, price=$5.00, total=$50.00 should be TRUSTED"""
        item = {
            "raw_name": "NAPKINS",
            "quantity": 10,
            "pack_size": "100 EA",
            "unit_price": 5.00,
            "total": 50.00
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["confidence_level"] == "trusted", f"Expected trusted, got {validated['confidence_level']}. Errors: {validated.get('validation_errors')}"
        print("PASS: Non-weight item (EA) uses simple math")


class TestCaseWeightAutoFill:
    """Test Case WT auto-fills from pack parse"""
    
    def test_case_wt_from_1x30LB(self):
        """1x30LB -> total_case_weight=30.0"""
        item = {"raw_name": "TEST", "quantity": 1, "pack_size": "1x30LB", "unit_price": 3.00, "total": 90.00}
        enriched = enrich_item_with_pack_size(item)
        assert enriched["total_case_weight"] == 30.0
        print("PASS: 1x30LB -> total_case_weight=30.0")
    
    def test_case_wt_from_12x1LB(self):
        """12x1LB -> total_case_weight=12.0"""
        item = {"raw_name": "TEST", "quantity": 1, "pack_size": "12x1LB", "unit_price": 2.00, "total": 24.00}
        enriched = enrich_item_with_pack_size(item)
        assert enriched["total_case_weight"] == 12.0
        print("PASS: 12x1LB -> total_case_weight=12.0")
    
    def test_case_wt_from_2x5LB(self):
        """2x5LB -> total_case_weight=10.0"""
        item = {"raw_name": "TEST", "quantity": 1, "pack_size": "2x5LB", "unit_price": 4.00, "total": 40.00}
        enriched = enrich_item_with_pack_size(item)
        assert enriched["total_case_weight"] == 10.0
        print("PASS: 2x5LB -> total_case_weight=10.0")


class TestPricePerLBCalculation:
    """Test $/LB = unit_price directly for weight-based items"""
    
    def test_price_per_lb_equals_unit_price(self):
        """$/LB = unit_price directly (not unit_price / case_weight)"""
        item = {
            "raw_name": "CHICKEN BREAST",
            "quantity": 1,
            "pack_size": "1x30LB",
            "unit_price": 3.50,
            "total": 105.00
        }
        enriched = enrich_item_with_pack_size(item)
        
        # $/LB should equal unit_price directly
        assert enriched["normalized_price_per_lb"] == 3.50, f"Expected $/LB=3.50, got {enriched.get('normalized_price_per_lb')}"
        print("PASS: $/LB = unit_price directly ($3.50)")
    
    def test_price_per_lb_computed_from_total(self):
        """$/LB auto-computed from total when unit_price missing: total=300, qty=2, pack=1x30LB -> $/LB=5.00"""
        item = {
            "raw_name": "BEEF RIBEYE",
            "quantity": 2,
            "pack_size": "1x30LB",
            "unit_price": 0,  # Missing
            "total": 300.00
        }
        enriched = enrich_item_with_pack_size(item)
        
        # $/LB = total / (qty × case_weight) = 300 / (2 × 30) = 5.00
        assert enriched["normalized_price_per_lb"] == 5.00, f"Expected $/LB=5.00, got {enriched.get('normalized_price_per_lb')}"
        print("PASS: $/LB computed from total: $300 ÷ (2 × 30LB) = $5.00/LB")


class TestWeightBasedSuggestions:
    """Test suggestion uses weight-based math"""
    
    def test_suggestion_uses_weight_based_math(self):
        """Wrong total with pack=1x30LB suggests Qty×30LB×$/LB"""
        item = {
            "raw_name": "CHICKEN BREAST",
            "quantity": 2,
            "pack_size": "1x30LB",
            "unit_price": 3.50,
            "total": 100.00  # Wrong! Should be 2×30×3.50=210
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["confidence_level"] == "unverified"
        assert validated["suggested_fix"] is not None, "Expected a suggested fix"
        
        # Check suggestion contains weight-based calculation
        suggestion = validated["suggested_fix"]
        assert "total" in suggestion["fields"], f"Expected total in suggestion fields: {suggestion}"
        assert suggestion["fields"]["total"] == 210.00, f"Expected suggested total=210, got {suggestion['fields'].get('total')}"
        
        # Check reason mentions weight-based math
        reasons = " ".join(suggestion["reasons"])
        assert "30" in reasons or "LB" in reasons, f"Expected weight-based reason, got: {reasons}"
        print(f"PASS: Suggestion uses weight-based math: {suggestion['reasons']}")
    
    def test_suggestion_computes_price_per_lb(self):
        """Missing price with weight-based item suggests $/LB"""
        item = {
            "raw_name": "SHRIMP",
            "quantity": 2,
            "pack_size": "1x10LB",
            "unit_price": 0,  # Missing
            "total": 200.00
        }
        enriched = enrich_item_with_pack_size(item)
        validated = validate_and_score_item(enriched)
        
        assert validated["suggested_fix"] is not None
        suggestion = validated["suggested_fix"]
        
        # $/LB = 200 / (2 × 10) = 10.00
        assert "unit_price" in suggestion["fields"]
        assert suggestion["fields"]["unit_price"] == 10.00, f"Expected $/LB=10.00, got {suggestion['fields'].get('unit_price')}"
        print(f"PASS: Suggestion computes $/LB: {suggestion['reasons']}")


class TestComputeReviewStatus:
    """Test compute_review_status with weight-based items"""
    
    def test_weight_based_items_clean_status(self):
        """Weight-based items with correct math return review_status=clean"""
        items = [
            {
                "raw_name": "CHICKEN BREAST",
                "quantity": 1,
                "pack_size": "1x30LB",
                "unit_price": 3.50,
                "total": 105.00,
                "pack_parse_status": "parsed",
                "total_case_weight": 30.0,
                "pack_unit": "LB",
                "confidence_level": "trusted",
                "needs_review": False
            },
            {
                "raw_name": "SHRIMP",
                "quantity": 2,
                "pack_size": "1x10LB",
                "unit_price": 8.00,
                "total": 160.00,
                "pack_parse_status": "parsed",
                "total_case_weight": 10.0,
                "pack_unit": "LB",
                "confidence_level": "trusted",
                "needs_review": False
            }
        ]
        status = compute_review_status(items)
        assert status == "clean", f"Expected clean, got {status}"
        print("PASS: Weight-based items with correct math -> review_status=clean")
    
    def test_weight_based_items_error_status(self):
        """Weight-based items with wrong math return review_status=error"""
        items = [
            {
                "raw_name": "CHICKEN BREAST",
                "quantity": 1,
                "pack_size": "1x30LB",
                "unit_price": 3.50,
                "total": 50.00,  # Wrong! Should be 105
                "pack_parse_status": "parsed",
                "total_case_weight": 30.0,
                "pack_unit": "LB",
                "confidence_level": "unverified",
                "needs_review": True,
                "validation_errors": ["MATH MISMATCH"]
            }
        ]
        status = compute_review_status(items)
        assert status == "error", f"Expected error, got {status}"
        print("PASS: Weight-based items with wrong math -> review_status=error")


class TestAPIWeightBasedPurchases:
    """Test API endpoints with weight-based items"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_post_purchase_weight_based_clean(self):
        """POST /api/purchases with weight-based items returns review_status=clean when math passes"""
        payload = {
            "supplier_name": "TEST_Weight_Math_Vendor",
            "invoice_number": "WM-TEST-001",
            "invoice_date": "2024-01-15",
            "items": [
                {
                    "raw_name": "CHICKEN BREAST",
                    "quantity": 1,
                    "pack_size": "1x30LB",
                    "unit_price": 3.50,
                    "total": 105.00
                },
                {
                    "raw_name": "SHRIMP 31-35",
                    "quantity": 2,
                    "pack_size": "1x10LB",
                    "unit_price": 8.00,
                    "total": 160.00
                }
            ],
            "subtotal": 265.00,
            "tax": 0,
            "total": 265.00
        }
        
        response = requests.post(f"{BASE_URL}/api/purchases", json=payload, headers=self.headers)
        assert response.status_code in [200, 201], f"POST failed: {response.text}"
        
        data = response.json()
        assert data.get("review_status") == "clean", f"Expected review_status=clean, got {data.get('review_status')}"
        
        # Verify items are trusted
        for item in data.get("items", []):
            assert item.get("confidence_level") == "trusted", f"Expected trusted, got {item.get('confidence_level')} for {item.get('raw_name')}"
            assert item.get("total_case_weight") is not None, f"Expected total_case_weight, got None for {item.get('raw_name')}"
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/purchases/{data['id']}", headers=self.headers)
        
        print("PASS: POST /api/purchases with weight-based items returns review_status=clean")
    
    def test_get_existing_weight_math_test_invoice(self):
        """Verify the 'Weight Math Test' (WM-001) invoice exists and is clean"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=self.headers, params={"search": "WM-001"})
        assert response.status_code == 200
        
        purchases = response.json()
        wm_invoice = None
        for p in purchases:
            if p.get("invoice_number") == "WM-001":
                wm_invoice = p
                break
        
        if wm_invoice:
            assert wm_invoice.get("review_status") == "clean", f"Expected WM-001 to be clean, got {wm_invoice.get('review_status')}"
            print(f"PASS: WM-001 invoice found with review_status=clean, {len(wm_invoice.get('items', []))} items")
        else:
            print("INFO: WM-001 invoice not found (may not exist in test data)")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
