"""
Tests for Guided Correction Suggestions V1 feature.
Tests _generate_suggested_fix function and suggested_fix field in validate_and_score_item.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Import preprocessing functions for unit tests
import sys
sys.path.insert(0, '/app/backend')
from preprocessing import _generate_suggested_fix, validate_and_score_item, parse_pack_size


class TestGenerateSuggestedFixUnit:
    """Unit tests for _generate_suggested_fix function"""
    
    def test_math_mismatch_suggests_corrected_total(self):
        """Math mismatch → suggest corrected total"""
        item = {
            "raw_name": "SHRIMP 31-35",
            "quantity": 3.0,
            "unit_price": 89.0,
            "total": 999.99,  # Wrong! Should be 267.0
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for math mismatch"
        assert "total" in suggestion["fields"], "Should suggest corrected total"
        assert suggestion["fields"]["total"] == 267.0, f"Expected 267.0, got {suggestion['fields']['total']}"
        assert suggestion["type"] == "math", f"Expected type 'math', got {suggestion['type']}"
        assert any("Recalculate total" in r for r in suggestion["reasons"]), "Should have recalculate reason"
    
    def test_missing_total_suggests_computed_total(self):
        """Missing total (qty×price → compute total)"""
        item = {
            "raw_name": "CHICKEN",
            "quantity": 5.0,
            "unit_price": 42.5,
            "total": 0,  # Missing
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for missing total"
        assert "total" in suggestion["fields"], "Should suggest computed total"
        assert suggestion["fields"]["total"] == 212.5, f"Expected 212.5, got {suggestion['fields']['total']}"
        assert suggestion["type"] == "math"
        assert any("Compute total" in r for r in suggestion["reasons"])
    
    def test_missing_price_suggests_computed_price(self):
        """Missing price (total÷qty → compute price)"""
        item = {
            "raw_name": "FLOUR",
            "quantity": 10.0,
            "unit_price": 0,  # Missing
            "total": 38.5,
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for missing price"
        assert "unit_price" in suggestion["fields"], "Should suggest computed price"
        assert suggestion["fields"]["unit_price"] == 3.85, f"Expected 3.85, got {suggestion['fields']['unit_price']}"
        assert suggestion["type"] == "math"
        assert any("Compute price" in r for r in suggestion["reasons"])
    
    def test_missing_quantity_suggests_computed_quantity(self):
        """Missing quantity (total÷price → compute quantity)"""
        item = {
            "raw_name": "SUGAR",
            "quantity": 0,  # Missing
            "unit_price": 5.0,
            "total": 25.0,
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for missing quantity"
        assert "quantity" in suggestion["fields"], "Should suggest computed quantity"
        assert suggestion["fields"]["quantity"] == 5.0, f"Expected 5.0, got {suggestion['fields']['quantity']}"
        assert suggestion["type"] == "math"
        assert any("Compute quantity" in r for r in suggestion["reasons"])
    
    def test_pack_parse_failure_suggests_normalized_format(self):
        """Pack parse failure with recoverable format (e.g. 1x30LB → 1/30 LB)"""
        item = {
            "raw_name": "CRAB LEGS",
            "quantity": 2.0,
            "unit_price": 50.0,
            "total": 100.0,
            "pack_size_raw": "1x30LB",  # OCR variant
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for pack parse failure"
        assert "pack_size" in suggestion["fields"], "Should suggest normalized pack size"
        assert suggestion["fields"]["pack_size"] == "1/30 LB", f"Expected '1/30 LB', got {suggestion['fields']['pack_size']}"
        assert suggestion["type"] == "pack"
        assert any("Normalize pack size" in r for r in suggestion["reasons"])
    
    def test_pack_parse_failure_with_X_separator(self):
        """Pack parse failure with X separator (e.g. 2X5LB → 2/5 LB)"""
        item = {
            "raw_name": "BEEF PATTIES",
            "quantity": 1.0,
            "unit_price": 45.0,
            "total": 45.0,
            "pack_size_raw": "2X5LB",
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None, "Should generate suggestion for X separator"
        assert "pack_size" in suggestion["fields"]
        assert suggestion["fields"]["pack_size"] == "2/5 LB"
        assert suggestion["type"] == "pack"
    
    def test_trusted_item_returns_null(self):
        """Trusted items should return suggested_fix=null"""
        item = {
            "raw_name": "CHICKEN BREAST",
            "quantity": 5.0,
            "unit_price": 42.5,
            "total": 212.5,  # Correct: 5 × 42.5 = 212.5
            "pack_size_raw": "10/4 LB",
            "pack_parse_status": "parsed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is None, "Trusted item should not have suggestion"
    
    def test_no_suggestion_when_all_zeros(self):
        """No suggestion when all numeric fields are zero"""
        item = {
            "raw_name": "UNKNOWN",
            "quantity": 0,
            "unit_price": 0,
            "total": 0,
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable"
        }
        suggestion = _generate_suggested_fix(item)
        
        # No math suggestion possible when all zeros
        assert suggestion is None or "total" not in suggestion.get("fields", {})


class TestValidateAndScoreItemSuggestedFix:
    """Tests that validate_and_score_item correctly sets suggested_fix"""
    
    def test_unverified_item_gets_suggested_fix(self):
        """Unverified items should have suggested_fix populated"""
        item = {
            "raw_name": "SHRIMP",
            "quantity": 3.0,
            "unit_price": 89.0,
            "total": 999.99,  # Math mismatch
            "pack_size": "",
        }
        result = validate_and_score_item(item)
        
        assert result["confidence_level"] == "unverified"
        assert result["needs_review"] == True
        assert result["suggested_fix"] is not None
        assert result["suggested_fix"]["fields"]["total"] == 267.0
    
    def test_trusted_item_has_null_suggested_fix(self):
        """Trusted items should have suggested_fix=null"""
        item = {
            "raw_name": "CHICKEN BREAST",
            "quantity": 5.0,
            "unit_price": 42.5,
            "total": 212.5,
            "pack_size": "10/4 LB",
        }
        # First enrich with pack size parsing
        from preprocessing import enrich_item_with_pack_size
        item = enrich_item_with_pack_size(item)
        result = validate_and_score_item(item)
        
        assert result["confidence_level"] == "trusted"
        assert result["needs_review"] == False
        assert result["suggested_fix"] is None


class TestSuggestedFixAPI:
    """Integration tests for suggested_fix in API responses"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_suggestion_test_vendor_has_suggested_fixes(self, auth_headers):
        """Suggestion Test Vendor (SUG-001) should have items with suggested_fix"""
        response = requests.get(
            f"{BASE_URL}/api/purchases",
            params={"search": "Suggestion Test Vendor"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0, "Should find Suggestion Test Vendor"
        
        purchase = data[0]
        items = purchase.get("items", [])
        
        # Find items by name and verify suggestions
        items_by_name = {it["raw_name"]: it for it in items}
        
        # CHICKEN BREAST - trusted, no suggestion
        chicken = items_by_name.get("CHICKEN BREAST")
        assert chicken is not None, "Should have CHICKEN BREAST item"
        assert chicken["confidence_level"] == "trusted"
        assert chicken["suggested_fix"] is None, "Trusted item should not have suggestion"
        
        # SHRIMP 31-35 - math mismatch, suggests total=267.0
        shrimp = items_by_name.get("SHRIMP 31-35")
        assert shrimp is not None, "Should have SHRIMP 31-35 item"
        assert shrimp["needs_review"] == True
        assert shrimp["suggested_fix"] is not None, "Math mismatch should have suggestion"
        assert shrimp["suggested_fix"]["fields"]["total"] == 267.0
        assert shrimp["suggested_fix"]["type"] == "math"
        
        # CRAB LEGS - pack parse fail, suggests pack_size='1/30 LB'
        crab = items_by_name.get("CRAB LEGS")
        assert crab is not None, "Should have CRAB LEGS item"
        assert crab["needs_review"] == True
        assert crab["suggested_fix"] is not None, "Pack parse fail should have suggestion"
        assert crab["suggested_fix"]["fields"]["pack_size"] == "1/30 LB"
        assert crab["suggested_fix"]["type"] == "pack"
        
        # FLOUR - missing price, suggests unit_price=3.85
        flour = items_by_name.get("FLOUR")
        assert flour is not None, "Should have FLOUR item"
        assert flour["needs_review"] == True
        assert flour["suggested_fix"] is not None, "Missing price should have suggestion"
        assert flour["suggested_fix"]["fields"]["unit_price"] == 3.85
        assert flour["suggested_fix"]["type"] == "math"
    
    def test_post_purchase_returns_suggested_fix(self, auth_headers):
        """POST /api/purchases should return suggested_fix on items that need review"""
        payload = {
            "supplier_name": "TEST_Suggestion_API_Vendor",
            "invoice_number": "TEST-SUG-API-001",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "TEST ITEM GOOD",
                    "quantity": 2,
                    "unit_price": 10.0,
                    "total": 20.0,  # Correct
                    "pack_size": ""
                },
                {
                    "raw_name": "TEST ITEM BAD MATH",
                    "quantity": 3,
                    "unit_price": 15.0,
                    "total": 100.0,  # Wrong! Should be 45.0
                    "pack_size": ""
                }
            ],
            "subtotal": 120.0,
            "tax": 0,
            "total": 120.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/purchases",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        
        created = response.json()
        purchase_id = created["id"]
        
        try:
            # Verify items have suggested_fix
            items = created.get("items", [])
            items_by_name = {it["raw_name"]: it for it in items}
            
            good_item = items_by_name.get("TEST ITEM GOOD")
            assert good_item is not None
            assert good_item["suggested_fix"] is None, "Good item should not have suggestion"
            
            bad_item = items_by_name.get("TEST ITEM BAD MATH")
            assert bad_item is not None
            assert bad_item["suggested_fix"] is not None, "Bad math item should have suggestion"
            assert bad_item["suggested_fix"]["fields"]["total"] == 45.0
            
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
    
    def test_quick_review_vendor_items_without_db_suggestions(self, auth_headers):
        """Quick Review Test Vendor has old items that may not have DB suggested_fix"""
        response = requests.get(
            f"{BASE_URL}/api/purchases",
            params={"search": "Quick Review Test Vendor"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0, "Should find Quick Review Test Vendor"
        
        purchase = data[0]
        items = purchase.get("items", [])
        
        # Find items needing review
        review_items = [it for it in items if it.get("needs_review")]
        assert len(review_items) > 0, "Should have items needing review"
        
        # Check that at least one has a math mismatch (SHRIMP 31-35)
        shrimp = next((it for it in items if "SHRIMP" in it.get("raw_name", "")), None)
        if shrimp and shrimp.get("needs_review"):
            # This item has math mismatch - backend should generate suggestion
            # Note: older items might not have suggested_fix in DB, but backend should compute it
            assert shrimp.get("validation_errors") or shrimp.get("review_reason")


class TestPackSizeNormalizationSuggestions:
    """Tests for pack size normalization suggestions"""
    
    def test_x_separator_normalized(self):
        """1x30LB should normalize to 1/30 LB"""
        item = {
            "raw_name": "TEST",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size_raw": "1x30LB",
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None
        assert suggestion["fields"]["pack_size"] == "1/30 LB"
    
    def test_uppercase_X_separator_normalized(self):
        """2X5LB should normalize to 2/5 LB"""
        item = {
            "raw_name": "TEST",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size_raw": "2X5LB",
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None
        assert suggestion["fields"]["pack_size"] == "2/5 LB"
    
    def test_multiplication_sign_normalized(self):
        """3×10LB should normalize to 3/10 LB"""
        item = {
            "raw_name": "TEST",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size_raw": "3×10LB",
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        assert suggestion is not None
        assert suggestion["fields"]["pack_size"] == "3/10 LB"
    
    def test_no_suggestion_for_unparseable_pack(self):
        """Completely unparseable pack size should not generate suggestion"""
        item = {
            "raw_name": "TEST",
            "quantity": 1,
            "unit_price": 10,
            "total": 10,
            "pack_size_raw": "RANDOM GARBAGE",
            "pack_parse_status": "failed"
        }
        suggestion = _generate_suggested_fix(item)
        
        # Should not have pack_size suggestion since normalization doesn't help
        if suggestion:
            assert "pack_size" not in suggestion.get("fields", {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
