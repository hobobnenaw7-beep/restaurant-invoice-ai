"""
Test suite for the minimal dashboard redesign.
Tests the new simplified dashboard with:
- GET /api/dashboard/summary: Returns ONLY spending data (raw materials, salaries, other) + max 5 smart alerts
- GET /api/dashboard/item-search: New endpoint for item/vendor price comparison
- NO: sales, profit, weekly_trends, utilities, top_items, top_vendors
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardSummaryMinimal:
    """Test the simplified dashboard summary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            self.token = login_resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Login failed - skipping authenticated tests")
    
    def test_dashboard_summary_returns_200(self):
        """Dashboard summary endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Dashboard summary returns 200")
    
    def test_dashboard_summary_has_required_spending_fields(self):
        """Dashboard should return month_raw_materials, month_salaries, month_other_expenses"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields for the donut chart
        required_fields = [
            "month_raw_materials",
            "month_salaries", 
            "month_other_expenses",
            "prev_month_raw_materials",
            "prev_month_salaries",
            "prev_month_other_expenses"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
        
        print(f"PASS: All required spending fields present")
        print(f"  - month_raw_materials: ${data['month_raw_materials']}")
        print(f"  - month_salaries: ${data['month_salaries']}")
        print(f"  - month_other_expenses: ${data['month_other_expenses']}")
    
    def test_dashboard_summary_no_utilities_field(self):
        """Dashboard should NOT have utilities field (removed)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Utilities was removed from the dashboard
        assert "month_utilities" not in data, "month_utilities should NOT be present (removed)"
        assert "prev_month_utilities" not in data, "prev_month_utilities should NOT be present (removed)"
        print("PASS: Utilities fields correctly removed from dashboard")
    
    def test_dashboard_summary_no_sales_fields(self):
        """Dashboard should NOT have sales fields (removed)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Sales fields were removed
        removed_fields = [
            "today_sales", "week_sales", "month_sales",
            "prev_today_sales", "prev_week_sales", "prev_month_sales"
        ]
        
        for field in removed_fields:
            assert field not in data, f"{field} should NOT be present (removed)"
        
        print("PASS: Sales fields correctly removed from dashboard")
    
    def test_dashboard_summary_no_profit_fields(self):
        """Dashboard should NOT have profit fields (removed)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Profit fields were removed
        removed_fields = ["net_profit", "prev_net_profit", "profit_margin"]
        
        for field in removed_fields:
            assert field not in data, f"{field} should NOT be present (removed)"
        
        print("PASS: Profit fields correctly removed from dashboard")
    
    def test_dashboard_summary_no_weekly_trends(self):
        """Dashboard should NOT have weekly_trends (removed)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "weekly_trends" not in data, "weekly_trends should NOT be present (removed)"
        print("PASS: weekly_trends correctly removed from dashboard")
    
    def test_dashboard_summary_smart_alerts_max_5(self):
        """Dashboard should return max 5 smart alerts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "smart_alerts" in data, "smart_alerts field should be present"
        alerts = data["smart_alerts"]
        assert isinstance(alerts, list), "smart_alerts should be a list"
        assert len(alerts) <= 5, f"smart_alerts should have max 5 items, got {len(alerts)}"
        
        print(f"PASS: smart_alerts has {len(alerts)} items (max 5)")
        
        # Verify alert structure if any exist
        if alerts:
            alert = alerts[0]
            assert "type" in alert, "Alert should have 'type' field"
            assert "severity" in alert, "Alert should have 'severity' field"
            assert alert["type"] in ["price_increase", "cheaper_vendor", "not_ordered"], \
                f"Invalid alert type: {alert['type']}"
            print(f"  - First alert type: {alert['type']}, severity: {alert['severity']}")
    
    def test_dashboard_summary_requires_auth(self):
        """Dashboard summary should require authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: Dashboard summary requires authentication")


class TestDashboardItemSearch:
    """Test the new item search endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if login_resp.status_code == 200:
            self.token = login_resp.json().get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Login failed - skipping authenticated tests")
    
    def test_item_search_returns_200(self):
        """Item search endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "salmon"}, headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Item search returns 200")
    
    def test_item_search_returns_results_structure(self):
        """Item search should return proper results structure"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "salmon"}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "results" in data, "Response should have 'results' field"
        assert isinstance(data["results"], list), "results should be a list"
        
        print(f"PASS: Item search returns results array with {len(data['results'])} items")
    
    def test_item_search_result_has_required_fields(self):
        """Each search result should have item_name, vendors, cheapest_vendor, cheapest_price"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "salmon"}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        if data["results"]:
            result = data["results"][0]
            required_fields = ["item_name", "vendors", "cheapest_vendor", "cheapest_price"]
            
            for field in required_fields:
                assert field in result, f"Result missing required field: {field}"
            
            print(f"PASS: Search result has all required fields")
            print(f"  - item_name: {result['item_name']}")
            print(f"  - cheapest_vendor: {result['cheapest_vendor']}")
            print(f"  - cheapest_price: ${result['cheapest_price']}")
            print(f"  - vendor_count: {len(result['vendors'])}")
        else:
            print("SKIP: No results found for 'salmon' - may need seed data")
    
    def test_item_search_vendor_has_required_fields(self):
        """Each vendor in results should have vendor, latest_price, avg_price, min_price, max_price, purchase_count, unit"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "salmon"}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        if data["results"] and data["results"][0]["vendors"]:
            vendor = data["results"][0]["vendors"][0]
            required_fields = ["vendor", "latest_price", "avg_price", "min_price", "max_price", "purchase_count", "unit"]
            
            for field in required_fields:
                assert field in vendor, f"Vendor missing required field: {field}"
            
            print(f"PASS: Vendor has all required fields")
            print(f"  - vendor: {vendor['vendor']}")
            print(f"  - latest_price: ${vendor['latest_price']}")
            print(f"  - avg_price: ${vendor['avg_price']}")
            print(f"  - purchase_count: {vendor['purchase_count']}")
        else:
            print("SKIP: No vendor data found - may need seed data")
    
    def test_item_search_empty_for_short_query(self):
        """Item search should return empty results for queries < 2 chars"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "x"}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "results" in data, "Response should have 'results' field"
        assert data["results"] == [], f"Expected empty results for short query, got {len(data['results'])} items"
        
        print("PASS: Short query returns empty results")
    
    def test_item_search_empty_for_no_match(self):
        """Item search should return empty results for non-matching query"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", 
                               params={"q": "xyznonexistent123"}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "results" in data, "Response should have 'results' field"
        assert data["results"] == [], f"Expected empty results for non-matching query"
        
        print("PASS: Non-matching query returns empty results")
    
    def test_item_search_requires_auth(self):
        """Item search should require authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/item-search", params={"q": "salmon"})
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: Item search requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
