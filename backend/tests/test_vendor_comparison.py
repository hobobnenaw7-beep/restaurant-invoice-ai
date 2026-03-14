"""
Test vendor price comparison endpoint: GET /api/prices/vendor-comparison
Tests:
- Endpoint returns items with vendor prices
- best_vendor field correctly identifies lowest price vendor
- vendors array sorted by latest_price ascending (cheapest first)
- savings_pct calculated correctly
- Items with 1 vendor don't have savings (savings_pct = 0)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestVendorComparison:
    """Vendor price comparison endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed - skipping tests")
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_vendor_comparison_endpoint_returns_200(self):
        """Test GET /api/prices/vendor-comparison returns 200"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Vendor comparison endpoint returns 200")
    
    def test_vendor_comparison_response_structure(self):
        """Test response has required fields: items array and total_items count"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "total_items" in data, "Response missing 'total_items' field"
        assert isinstance(data["items"], list), "'items' should be an array"
        assert isinstance(data["total_items"], int), "'total_items' should be integer"
        assert data["total_items"] == len(data["items"]), "total_items should match items array length"
        print(f"✓ Response structure valid with {data['total_items']} items")
    
    def test_item_structure(self):
        """Test each item has required fields: item, vendors, best_vendor, best_price, savings_pct, vendor_count"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) > 0, "Expected at least one item"
        
        for item in data["items"]:
            assert "item" in item, f"Item missing 'item' name field"
            assert "vendors" in item, f"Item '{item.get('item', 'unknown')}' missing 'vendors' array"
            assert "best_vendor" in item, f"Item '{item.get('item', 'unknown')}' missing 'best_vendor'"
            assert "best_price" in item, f"Item '{item.get('item', 'unknown')}' missing 'best_price'"
            assert "savings_pct" in item, f"Item '{item.get('item', 'unknown')}' missing 'savings_pct'"
            assert "vendor_count" in item, f"Item '{item.get('item', 'unknown')}' missing 'vendor_count'"
            
            # Vendor count should match vendors array
            assert item["vendor_count"] == len(item["vendors"]), f"vendor_count mismatch for {item['item']}"
        
        print(f"✓ All {len(data['items'])} items have required fields")
    
    def test_vendor_structure(self):
        """Test each vendor entry has: vendor, latest_price, latest_date, avg_price, purchase_count, unit"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) > 0, "Expected at least one item"
        
        for item in data["items"]:
            for vendor in item["vendors"]:
                assert "vendor" in vendor, f"Vendor missing 'vendor' name"
                assert "latest_price" in vendor, f"Vendor missing 'latest_price'"
                assert "latest_date" in vendor, f"Vendor missing 'latest_date'"
                assert "avg_price" in vendor, f"Vendor missing 'avg_price'"
                assert "purchase_count" in vendor, f"Vendor missing 'purchase_count'"
                assert "unit" in vendor, f"Vendor missing 'unit'"
                
                # Validate data types
                assert isinstance(vendor["latest_price"], (int, float)), "latest_price should be numeric"
                assert isinstance(vendor["avg_price"], (int, float)), "avg_price should be numeric"
                assert isinstance(vendor["purchase_count"], int), "purchase_count should be integer"
        
        print("✓ All vendor entries have correct structure and data types")
    
    def test_vendors_sorted_by_latest_price_ascending(self):
        """Test vendors array is sorted by latest_price ascending (cheapest first)"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        items_checked = 0
        for item in data["items"]:
            if len(item["vendors"]) > 1:
                prices = [v["latest_price"] for v in item["vendors"]]
                assert prices == sorted(prices), f"Vendors not sorted by price for {item['item']}: {prices}"
                items_checked += 1
        
        assert items_checked > 0, "No items with multiple vendors to test sorting"
        print(f"✓ Verified sorting for {items_checked} items with multiple vendors")
    
    def test_best_vendor_is_cheapest(self):
        """Test best_vendor correctly identifies vendor with lowest latest_price"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        for item in data["items"]:
            if len(item["vendors"]) > 0:
                cheapest_vendor = item["vendors"][0]  # First vendor should be cheapest
                assert item["best_vendor"] == cheapest_vendor["vendor"], \
                    f"best_vendor mismatch for {item['item']}: expected {cheapest_vendor['vendor']}, got {item['best_vendor']}"
                assert item["best_price"] == cheapest_vendor["latest_price"], \
                    f"best_price mismatch for {item['item']}"
        
        print("✓ best_vendor and best_price correctly identify cheapest option")
    
    def test_savings_pct_calculation(self):
        """Test savings_pct = (1 - best_price / worst_price) * 100 for multi-vendor items"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        multi_vendor_items = [i for i in data["items"] if len(i["vendors"]) > 1]
        assert len(multi_vendor_items) > 0, "No multi-vendor items to test savings calculation"
        
        for item in multi_vendor_items:
            best_price = item["vendors"][0]["latest_price"]
            worst_price = item["vendors"][-1]["latest_price"]
            
            if worst_price > 0:
                expected_savings = round((1 - best_price / worst_price) * 100, 1)
                assert abs(item["savings_pct"] - expected_savings) < 0.2, \
                    f"savings_pct mismatch for {item['item']}: expected {expected_savings}, got {item['savings_pct']}"
        
        print(f"✓ savings_pct calculation correct for {len(multi_vendor_items)} multi-vendor items")
    
    def test_single_vendor_items_no_best_badge(self):
        """Test items with 1 vendor have savings_pct = 0 (no comparison possible)"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        single_vendor_items = [i for i in data["items"] if len(i["vendors"]) == 1]
        
        for item in single_vendor_items:
            assert item["savings_pct"] == 0, \
                f"Single-vendor item {item['item']} should have savings_pct = 0, got {item['savings_pct']}"
        
        if single_vendor_items:
            print(f"✓ {len(single_vendor_items)} single-vendor items correctly have savings_pct = 0")
        else:
            print("✓ No single-vendor items to test (all items have multiple vendors)")
    
    def test_requires_authentication(self):
        """Test endpoint returns 401 without auth token"""
        response = requests.get(f"{BASE_URL}/api/prices/vendor-comparison")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Endpoint correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
