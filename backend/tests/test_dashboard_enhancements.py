"""
Test Dashboard Enhancements - Quick Actions, Data Freshness, Best Opportunities
Tests the new dashboard features: last_data_update, purchase_count, best_opportunities
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardEnhancements:
    """Tests for dashboard summary enhancements"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    # ─── Dashboard Summary Endpoint Tests ───
    
    def test_dashboard_summary_returns_200(self):
        """Dashboard summary endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Dashboard summary returns 200")
    
    def test_dashboard_summary_has_last_data_update(self):
        """Dashboard summary includes last_data_update timestamp"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        assert "last_data_update" in data, "Missing last_data_update field"
        assert data["last_data_update"] is not None, "last_data_update is None"
        assert isinstance(data["last_data_update"], str), "last_data_update should be string"
        # Should be ISO format timestamp
        assert "T" in data["last_data_update"], "last_data_update should be ISO format"
        print(f"PASS: last_data_update = {data['last_data_update']}")
    
    def test_dashboard_summary_has_purchase_count(self):
        """Dashboard summary includes purchase_count"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        assert "purchase_count" in data, "Missing purchase_count field"
        assert isinstance(data["purchase_count"], int), "purchase_count should be integer"
        assert data["purchase_count"] >= 0, "purchase_count should be non-negative"
        print(f"PASS: purchase_count = {data['purchase_count']}")
    
    def test_dashboard_summary_has_best_opportunities(self):
        """Dashboard summary includes best_opportunities array"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        assert "best_opportunities" in data, "Missing best_opportunities field"
        assert isinstance(data["best_opportunities"], list), "best_opportunities should be array"
        print(f"PASS: best_opportunities is array with {len(data['best_opportunities'])} items")
    
    def test_best_opportunities_max_two_items(self):
        """best_opportunities contains max 2 items"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        opps = data.get("best_opportunities", [])
        assert len(opps) <= 2, f"best_opportunities should have max 2 items, got {len(opps)}"
        print(f"PASS: best_opportunities has {len(opps)} items (max 2)")
    
    def test_best_opportunities_types(self):
        """best_opportunities items have valid types (saving or risk)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        opps = data.get("best_opportunities", [])
        valid_types = {"saving", "risk"}
        for opp in opps:
            assert "type" in opp, "Opportunity missing type field"
            assert opp["type"] in valid_types, f"Invalid type: {opp['type']}"
        print(f"PASS: All opportunities have valid types")
    
    def test_saving_opportunity_structure(self):
        """Saving opportunity has required fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        opps = data.get("best_opportunities", [])
        savings = [o for o in opps if o.get("type") == "saving"]
        
        if savings:
            saving = savings[0]
            required_fields = ["item_name", "vendor", "savings_pct", "cheaper_price", "current_price"]
            for field in required_fields:
                assert field in saving, f"Saving opportunity missing {field}"
            assert isinstance(saving["savings_pct"], (int, float)), "savings_pct should be numeric"
            assert isinstance(saving["cheaper_price"], (int, float)), "cheaper_price should be numeric"
            assert isinstance(saving["current_price"], (int, float)), "current_price should be numeric"
            print(f"PASS: Saving opportunity has all required fields: {saving['item_name']}")
        else:
            print("SKIP: No saving opportunities in data")
    
    def test_risk_opportunity_structure(self):
        """Risk opportunity has required fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        opps = data.get("best_opportunities", [])
        risks = [o for o in opps if o.get("type") == "risk"]
        
        if risks:
            risk = risks[0]
            required_fields = ["item_name", "vendor", "change_pct", "old_price", "new_price"]
            for field in required_fields:
                assert field in risk, f"Risk opportunity missing {field}"
            assert isinstance(risk["change_pct"], (int, float)), "change_pct should be numeric"
            assert isinstance(risk["old_price"], (int, float)), "old_price should be numeric"
            assert isinstance(risk["new_price"], (int, float)), "new_price should be numeric"
            print(f"PASS: Risk opportunity has all required fields: {risk['item_name']}")
        else:
            print("SKIP: No risk opportunities in data")
    
    # ─── Authentication Tests ───
    
    def test_dashboard_summary_requires_auth(self):
        """Dashboard summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: Dashboard summary requires authentication")
    
    # ─── Data Consistency Tests ───
    
    def test_purchase_count_matches_purchases_list(self):
        """purchase_count matches actual purchases count"""
        # Get dashboard summary
        summary_response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        summary_data = summary_response.json()
        dashboard_count = summary_data.get("purchase_count", 0)
        
        # Get purchases list
        purchases_response = requests.get(f"{BASE_URL}/api/purchases", headers=self.headers)
        purchases_data = purchases_response.json()
        actual_count = len(purchases_data) if isinstance(purchases_data, list) else 0
        
        assert dashboard_count == actual_count, f"purchase_count mismatch: dashboard={dashboard_count}, actual={actual_count}"
        print(f"PASS: purchase_count ({dashboard_count}) matches actual purchases ({actual_count})")
    
    def test_smart_alerts_present(self):
        """Dashboard summary includes smart_alerts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        assert "smart_alerts" in data, "Missing smart_alerts field"
        assert isinstance(data["smart_alerts"], list), "smart_alerts should be array"
        print(f"PASS: smart_alerts is array with {len(data['smart_alerts'])} items")
    
    def test_spending_totals_present(self):
        """Dashboard summary includes spending totals"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        required_fields = [
            "month_raw_materials", "month_salaries", "month_other_expenses",
            "prev_month_raw_materials", "prev_month_salaries", "prev_month_other_expenses"
        ]
        for field in required_fields:
            assert field in data, f"Missing {field}"
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
        print("PASS: All spending totals present and numeric")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
