"""
Test suite for Item Price History feature
- GET /api/items/{item_id}/price-history endpoint
- Tests for price history matching canonical names + aliases
- Tests for summary stats, trend data, and records
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPriceHistory:
    """Price History endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_items_list(self):
        """Test that items endpoint returns list with aliases"""
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        assert response.status_code == 200
        items = response.json()
        assert isinstance(items, list)
        assert len(items) > 0
        # Check item structure
        item = items[0]
        assert "id" in item
        assert "name" in item
        assert "aliases" in item
    
    def test_price_history_for_beef_with_aliases(self):
        """Test price history for Beef item (has aliases: Ground Beef, Beef 80/20, Fresh Beef)"""
        # First get items to find Beef item
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        assert response.status_code == 200
        items = response.json()
        
        beef_item = next((i for i in items if i["name"] == "Beef"), None)
        assert beef_item is not None, "Beef item not found"
        assert len(beef_item.get("aliases", [])) > 0, "Beef should have aliases"
        
        # Get price history
        response = requests.get(f"{BASE_URL}/api/items/{beef_item['id']}/price-history", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["item_name"] == "Beef"
        assert "records" in data
        assert "trend" in data
        assert "summary" in data
        
        # Verify records from aliases (Ground Beef is most common)
        records = data["records"]
        assert len(records) > 0, "Beef should have price records from its aliases"
        
        # Check record structure
        record = records[0]
        assert "vendor" in record
        assert "date" in record
        assert "unit_price" in record
        assert "quantity" in record
        assert "unit" in record
        assert "raw_name" in record
        
        # Verify summary stats
        summary = data["summary"]
        assert "total_records" in summary
        assert "avg_price" in summary
        assert "min_price" in summary
        assert "max_price" in summary
        assert "vendors" in summary
        assert summary["total_records"] > 0
        assert summary["avg_price"] > 0
        assert summary["min_price"] <= summary["avg_price"] <= summary["max_price"]
    
    def test_price_history_for_salmon_with_aliases(self):
        """Test price history for Salmon Fillet (has aliases: Fresh Salmon, Atlantic Salmon)"""
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        items = response.json()
        
        salmon_item = next((i for i in items if i["name"] == "Salmon Fillet"), None)
        assert salmon_item is not None, "Salmon Fillet item not found"
        
        response = requests.get(f"{BASE_URL}/api/items/{salmon_item['id']}/price-history", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["item_name"] == "Salmon Fillet"
        
        # Check records include alias names
        records = data["records"]
        assert len(records) > 0
        raw_names = set(r["raw_name"] for r in records)
        # Should include "Fresh Salmon" which is an alias
        assert "Fresh Salmon" in raw_names
        
        # Check trend data
        trend = data["trend"]
        assert len(trend) > 0
        assert "date" in trend[0]
        assert "avg_price" in trend[0]
    
    def test_price_history_trend_sorted_by_date(self):
        """Test that trend data is sorted by date ascending"""
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        items = response.json()
        
        # Find item with price history
        beef_item = next((i for i in items if i["name"] == "Beef"), None)
        assert beef_item is not None
        
        response = requests.get(f"{BASE_URL}/api/items/{beef_item['id']}/price-history", headers=self.headers)
        data = response.json()
        
        trend = data["trend"]
        if len(trend) > 1:
            dates = [t["date"] for t in trend]
            assert dates == sorted(dates), "Trend data should be sorted by date ascending"
    
    def test_price_history_records_structure(self):
        """Test that price records have all required fields"""
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        items = response.json()
        
        # Find Rice item
        rice_item = next((i for i in items if i["name"] == "Rice"), None)
        if rice_item:
            response = requests.get(f"{BASE_URL}/api/items/{rice_item['id']}/price-history", headers=self.headers)
            assert response.status_code == 200
            
            data = response.json()
            for record in data.get("records", []):
                assert "vendor" in record and isinstance(record["vendor"], str)
                assert "date" in record and isinstance(record["date"], str)
                assert "unit_price" in record and isinstance(record["unit_price"], (int, float))
                assert "quantity" in record and isinstance(record["quantity"], (int, float))
                assert "unit" in record
                assert "raw_name" in record and isinstance(record["raw_name"], str)
    
    def test_price_history_not_found_item(self):
        """Test 404 for non-existent item"""
        response = requests.get(f"{BASE_URL}/api/items/non-existent-id-12345/price-history", headers=self.headers)
        assert response.status_code == 404
    
    def test_price_history_summary_vendors_list(self):
        """Test that summary contains unique vendors list"""
        response = requests.get(f"{BASE_URL}/api/items", headers=self.headers)
        items = response.json()
        
        salmon_item = next((i for i in items if i["name"] == "Salmon Fillet"), None)
        if salmon_item:
            response = requests.get(f"{BASE_URL}/api/items/{salmon_item['id']}/price-history", headers=self.headers)
            data = response.json()
            
            vendors = data["summary"]["vendors"]
            assert isinstance(vendors, list)
            # Should have unique vendors
            assert len(vendors) == len(set(vendors))
    
    def test_price_history_unauthorized(self):
        """Test that endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/items/any-id/price-history")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
