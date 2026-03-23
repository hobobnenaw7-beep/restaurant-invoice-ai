"""
Test Dashboard Charts Feature - Monthly Spending Donut Chart and Expense Trends Line Chart
Tests the GET /api/dashboard/summary endpoint for new chart-related fields
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardCharts:
    """Tests for dashboard chart data fields"""
    
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
    
    def test_dashboard_summary_returns_200(self):
        """Dashboard summary endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        print("PASS: Dashboard summary returns 200")
    
    def test_dashboard_has_monthly_expense_fields(self):
        """Dashboard returns all 4 monthly expense category fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        # Check current month fields
        assert "month_raw_materials" in data, "Missing month_raw_materials"
        assert "month_salaries" in data, "Missing month_salaries"
        assert "month_utilities" in data, "Missing month_utilities"
        assert "month_other_expenses" in data, "Missing month_other_expenses"
        
        # Verify they are numbers
        assert isinstance(data["month_raw_materials"], (int, float))
        assert isinstance(data["month_salaries"], (int, float))
        assert isinstance(data["month_utilities"], (int, float))
        assert isinstance(data["month_other_expenses"], (int, float))
        
        print(f"PASS: Monthly expense fields present - Raw: ${data['month_raw_materials']}, Salaries: ${data['month_salaries']}, Utilities: ${data['month_utilities']}, Other: ${data['month_other_expenses']}")
    
    def test_dashboard_has_prev_month_expense_fields(self):
        """Dashboard returns all 4 previous month expense category fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        # Check previous month fields
        assert "prev_month_raw_materials" in data, "Missing prev_month_raw_materials"
        assert "prev_month_salaries" in data, "Missing prev_month_salaries"
        assert "prev_month_utilities" in data, "Missing prev_month_utilities"
        assert "prev_month_other_expenses" in data, "Missing prev_month_other_expenses"
        
        # Verify they are numbers
        assert isinstance(data["prev_month_raw_materials"], (int, float))
        assert isinstance(data["prev_month_salaries"], (int, float))
        assert isinstance(data["prev_month_utilities"], (int, float))
        assert isinstance(data["prev_month_other_expenses"], (int, float))
        
        print(f"PASS: Previous month expense fields present - Raw: ${data['prev_month_raw_materials']}, Salaries: ${data['prev_month_salaries']}, Utilities: ${data['prev_month_utilities']}, Other: ${data['prev_month_other_expenses']}")
    
    def test_dashboard_has_weekly_trends(self):
        """Dashboard returns weekly_trends array"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        assert "weekly_trends" in data, "Missing weekly_trends"
        assert isinstance(data["weekly_trends"], list), "weekly_trends should be a list"
        assert len(data["weekly_trends"]) == 8, f"Expected 8 weeks, got {len(data['weekly_trends'])}"
        
        print(f"PASS: weekly_trends has {len(data['weekly_trends'])} weeks")
    
    def test_weekly_trends_has_all_expense_categories(self):
        """Each week in weekly_trends has all 4 expense categories"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        for i, week in enumerate(data["weekly_trends"]):
            assert "week" in week, f"Week {i} missing 'week' label"
            assert "purchases" in week, f"Week {i} missing 'purchases' (raw materials)"
            assert "salaries" in week, f"Week {i} missing 'salaries'"
            assert "utilities" in week, f"Week {i} missing 'utilities'"
            assert "other_expenses" in week, f"Week {i} missing 'other_expenses'"
            
            # Verify they are numbers
            assert isinstance(week["purchases"], (int, float))
            assert isinstance(week["salaries"], (int, float))
            assert isinstance(week["utilities"], (int, float))
            assert isinstance(week["other_expenses"], (int, float))
        
        print("PASS: All weekly_trends entries have required expense category fields")
    
    def test_weekly_trends_week_labels(self):
        """Weekly trends have correct W1-W8 labels"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        expected_labels = ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]
        actual_labels = [w["week"] for w in data["weekly_trends"]]
        
        assert actual_labels == expected_labels, f"Expected {expected_labels}, got {actual_labels}"
        print(f"PASS: Weekly trend labels are correct: {actual_labels}")
    
    def test_monthly_expense_total_calculation(self):
        """Verify total monthly expenses can be calculated from 4 categories"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        total = (
            data["month_raw_materials"] +
            data["month_salaries"] +
            data["month_utilities"] +
            data["month_other_expenses"]
        )
        
        assert total >= 0, "Total monthly expenses should be non-negative"
        print(f"PASS: Total monthly expenses = ${total:.2f}")
    
    def test_expense_percentages_calculation(self):
        """Verify expense percentages can be calculated correctly"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        total = (
            data["month_raw_materials"] +
            data["month_salaries"] +
            data["month_utilities"] +
            data["month_other_expenses"]
        )
        
        if total > 0:
            raw_pct = (data["month_raw_materials"] / total) * 100
            sal_pct = (data["month_salaries"] / total) * 100
            util_pct = (data["month_utilities"] / total) * 100
            other_pct = (data["month_other_expenses"] / total) * 100
            
            # Percentages should sum to 100
            total_pct = raw_pct + sal_pct + util_pct + other_pct
            assert abs(total_pct - 100) < 0.1, f"Percentages should sum to 100, got {total_pct}"
            
            print(f"PASS: Expense percentages - Raw: {raw_pct:.1f}%, Salaries: {sal_pct:.1f}%, Utilities: {util_pct:.1f}%, Other: {other_pct:.1f}%")
        else:
            print("SKIP: No expenses to calculate percentages")
    
    def test_dashboard_requires_auth(self):
        """Dashboard summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Dashboard requires authentication")
    
    def test_smart_alerts_present(self):
        """Dashboard returns smart_alerts array"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        assert "smart_alerts" in data, "Missing smart_alerts"
        assert isinstance(data["smart_alerts"], list), "smart_alerts should be a list"
        print(f"PASS: smart_alerts present with {len(data['smart_alerts'])} alerts")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
