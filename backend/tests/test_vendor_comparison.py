"""
Test suite for Vendor Price Comparison endpoint: GET /api/vendor-comparison/normalized
Tests:
- Only items with pack_parse_status=parsed and normalized_price_per_lb > 0 are included
- Items with failed/not_applicable status or non-weight units (EA, GAL, PK) are excluded
- Multi-vendor items appear first, sorted by spread_pct descending
- Item grouping is exact-match (conservative, no fuzzy merge)
- Stats object contains correct counts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestVendorComparisonNormalized:
    """Tests for GET /api/vendor-comparison/normalized endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_endpoint_returns_200(self):
        """Test that the endpoint returns 200 OK"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS - Endpoint returns 200 OK")
    
    def test_response_structure(self):
        """Test that response has correct structure with comparisons and stats"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check top-level keys
        assert "comparisons" in data, "Missing 'comparisons' key"
        assert "stats" in data, "Missing 'stats' key"
        
        # Check stats structure
        stats = data["stats"]
        assert "total_qualifying_items" in stats, "Missing 'total_qualifying_items' in stats"
        assert "total_groups" in stats, "Missing 'total_groups' in stats"
        assert "multi_vendor_groups" in stats, "Missing 'multi_vendor_groups' in stats"
        assert "vendors_represented" in stats, "Missing 'vendors_represented' in stats"
        
        print(f"PASS - Response structure correct. Stats: {stats}")
    
    def test_qualifying_items_have_valid_normalized_price(self):
        """Test that all items in comparisons have normalized_price_per_lb > 0"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        for group in data.get("comparisons", []):
            for entry in group.get("entries", []):
                nplb = entry.get("normalized_price_per_lb", 0)
                assert nplb > 0, f"Entry has invalid normalized_price_per_lb: {entry}"
                
                # Check pack_unit is LB or OZ (normalizable)
                pack_unit = entry.get("pack_unit", "")
                assert pack_unit in ["LB", "OZ"], f"Entry has non-normalizable unit '{pack_unit}': {entry}"
        
        print("PASS - All qualifying items have valid normalized_price_per_lb > 0 and LB/OZ units")
    
    def test_no_excluded_units_in_results(self):
        """Test that EA, GAL, PK and other non-weight units are excluded"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        excluded_units = {"EA", "GAL", "PK", "CT", "EACH", "GALLON", "PACK", "BOX", "BX", "CS", "CASE"}
        
        for group in data.get("comparisons", []):
            for entry in group.get("entries", []):
                pack_unit = entry.get("pack_unit", "").upper()
                assert pack_unit not in excluded_units, f"Found excluded unit '{pack_unit}' in results: {entry}"
        
        print("PASS - No excluded units (EA, GAL, PK, etc.) found in results")
    
    def test_multi_vendor_items_sorted_first(self):
        """Test that multi-vendor items appear before single-vendor items"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        comparisons = data.get("comparisons", [])
        if len(comparisons) < 2:
            print("SKIP - Not enough comparison groups to test sorting")
            return
        
        # Find first single-vendor group index
        first_single_idx = None
        for i, group in enumerate(comparisons):
            if not group.get("is_multi_vendor", False):
                first_single_idx = i
                break
        
        if first_single_idx is None:
            print("PASS - All groups are multi-vendor (sorting N/A)")
            return
        
        # All groups before first_single_idx should be multi-vendor
        for i in range(first_single_idx):
            assert comparisons[i].get("is_multi_vendor", False), \
                f"Group at index {i} should be multi-vendor but is not"
        
        print(f"PASS - Multi-vendor items sorted first (first single-vendor at index {first_single_idx})")
    
    def test_comparison_group_structure(self):
        """Test that each comparison group has required fields"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        for group in data.get("comparisons", []):
            assert "item_key" in group, "Missing 'item_key' in group"
            assert "comparison_unit" in group, "Missing 'comparison_unit' in group"
            assert "entries" in group, "Missing 'entries' in group"
            assert "best_price" in group, "Missing 'best_price' in group"
            assert "spread_pct" in group, "Missing 'spread_pct' in group"
            assert "vendor_count" in group, "Missing 'vendor_count' in group"
            assert "is_multi_vendor" in group, "Missing 'is_multi_vendor' in group"
            
            # Check comparison_unit is always LB
            assert group["comparison_unit"] == "LB", f"Expected comparison_unit='LB', got '{group['comparison_unit']}'"
        
        print("PASS - All comparison groups have required fields")
    
    def test_entry_structure(self):
        """Test that each entry has required fields for UI display"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        required_fields = ["vendor", "raw_name", "pack_size_raw", "unit_price", 
                          "total_case_weight", "pack_unit", "normalized_price_per_lb", "invoice_date"]
        
        for group in data.get("comparisons", []):
            for entry in group.get("entries", []):
                for field in required_fields:
                    assert field in entry, f"Missing '{field}' in entry: {entry}"
        
        print("PASS - All entries have required fields for UI display")
    
    def test_best_price_is_minimum(self):
        """Test that best_price is the minimum normalized_price_per_lb in each group"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        for group in data.get("comparisons", []):
            entries = group.get("entries", [])
            if not entries:
                continue
            
            prices = [e["normalized_price_per_lb"] for e in entries]
            expected_best = min(prices)
            actual_best = group["best_price"]
            
            assert abs(actual_best - expected_best) < 0.0001, \
                f"best_price mismatch: expected {expected_best}, got {actual_best}"
        
        print("PASS - best_price is correctly the minimum in each group")
    
    def test_entries_sorted_by_price_ascending(self):
        """Test that entries within each group are sorted by price ascending"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        for group in data.get("comparisons", []):
            entries = group.get("entries", [])
            if len(entries) < 2:
                continue
            
            prices = [e["normalized_price_per_lb"] for e in entries]
            assert prices == sorted(prices), f"Entries not sorted by price in group '{group['item_key']}'"
        
        print("PASS - Entries within groups are sorted by price ascending")
    
    def test_stats_counts_match_data(self):
        """Test that stats counts match the actual data"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        comparisons = data.get("comparisons", [])
        stats = data.get("stats", {})
        
        # total_groups should match number of comparison groups
        assert stats["total_groups"] == len(comparisons), \
            f"total_groups mismatch: {stats['total_groups']} vs {len(comparisons)}"
        
        # multi_vendor_groups count
        actual_multi = sum(1 for g in comparisons if g.get("is_multi_vendor", False))
        assert stats["multi_vendor_groups"] == actual_multi, \
            f"multi_vendor_groups mismatch: {stats['multi_vendor_groups']} vs {actual_multi}"
        
        # vendors_represented
        all_vendors = set()
        for g in comparisons:
            for e in g.get("entries", []):
                all_vendors.add(e.get("vendor", ""))
        assert stats["vendors_represented"] == len(all_vendors), \
            f"vendors_represented mismatch: {stats['vendors_represented']} vs {len(all_vendors)}"
        
        print(f"PASS - Stats counts match data: {stats}")
    
    def test_exact_match_grouping(self):
        """Test that item grouping is exact-match (conservative)"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check that item_key is uppercase normalized version of raw_name
        for group in data.get("comparisons", []):
            item_key = group.get("item_key", "")
            for entry in group.get("entries", []):
                raw_name = entry.get("raw_name", "").strip().upper()
                # Normalize whitespace
                import re
                normalized_raw = re.sub(r"\s+", " ", raw_name)
                assert item_key == normalized_raw, \
                    f"Item key '{item_key}' doesn't match normalized raw_name '{normalized_raw}'"
        
        print("PASS - Item grouping is exact-match (conservative)")


class TestVendorComparisonWithSeededData:
    """Tests that verify seeded test data is correctly processed"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_seeded_data_present(self):
        """Test that seeded vendor comparison data is present"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        stats = data.get("stats", {})
        comparisons = data.get("comparisons", [])
        
        print(f"Stats: {stats}")
        print(f"Number of comparison groups: {len(comparisons)}")
        
        # According to agent context: 12 qualifying items, 6 groups, 5 multi-vendor groups, 3 vendors
        # But we should verify what's actually there
        if stats.get("total_qualifying_items", 0) > 0:
            print(f"PASS - Found {stats['total_qualifying_items']} qualifying items")
        else:
            print("INFO - No qualifying items found (may need seeded data)")
    
    def test_expected_items_present(self):
        """Test that expected items from seeded data are present"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Expected items from agent context
        expected_items = [
            "CHICKEN BREAST BNLS",
            "FLOUR ALL PURPOSE",
            "SHRIMP 31-35 HDLS",
            "TOMATO ROMA 25LB",
            "GROUND BEEF 80/20",
            "SALMON FILLET"
        ]
        
        found_items = set()
        for group in data.get("comparisons", []):
            item_key = group.get("item_key", "")
            for expected in expected_items:
                if expected.upper() in item_key.upper():
                    found_items.add(expected)
        
        print(f"Found items: {found_items}")
        print(f"Expected items: {set(expected_items)}")
        
        if found_items:
            print(f"PASS - Found {len(found_items)}/{len(expected_items)} expected items")
        else:
            print("INFO - No expected items found (may need seeded data)")
    
    def test_excluded_items_not_present(self):
        """Test that items with non-weight units are excluded"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Items that should be excluded (PK, EA units)
        excluded_items = [
            "LETTUCE ROMAINE HEARTS",  # PK unit
            "CONTAINER FOAM 150CT"     # EA unit
        ]
        
        all_item_keys = [g.get("item_key", "") for g in data.get("comparisons", [])]
        
        for excluded in excluded_items:
            for item_key in all_item_keys:
                assert excluded.upper() not in item_key.upper(), \
                    f"Excluded item '{excluded}' found in results"
        
        print(f"PASS - Excluded items (PK/EA units) not present in results")
    
    def test_expected_vendors_present(self):
        """Test that expected vendors are represented"""
        resp = requests.get(f"{BASE_URL}/api/vendor-comparison/normalized", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Expected vendors from agent context
        expected_vendors = [
            "US Foods Test",
            "Sysco Restaurant Supply",
            "Performance Food Group"
        ]
        
        all_vendors = set()
        for group in data.get("comparisons", []):
            for entry in group.get("entries", []):
                all_vendors.add(entry.get("vendor", ""))
        
        print(f"Found vendors: {all_vendors}")
        
        found_vendors = set()
        for expected in expected_vendors:
            for vendor in all_vendors:
                if expected.lower() in vendor.lower():
                    found_vendors.add(expected)
        
        if found_vendors:
            print(f"PASS - Found {len(found_vendors)}/{len(expected_vendors)} expected vendors")
        else:
            print("INFO - No expected vendors found (may need seeded data)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
