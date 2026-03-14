"""
Test suite for Automatic Profit Calculation feature.
Tests Net Profit = Total Sales - Total Expenses (Raw Materials + Salaries + Other Expenses)
Tests daily, weekly, monthly, yearly profit calculations and period-over-period comparisons.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


class TestProfitCalculationAPI:
    """Test profit calculation in dashboard summary API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    # ========== PROFIT FIELDS PRESENCE TESTS ==========
    
    def test_dashboard_summary_returns_daily_profit(self):
        """GET /api/dashboard/summary should return daily_profit field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        assert "daily_profit" in data, "daily_profit field missing from response"
        assert isinstance(data["daily_profit"], (int, float)), "daily_profit should be numeric"
        print(f"✓ daily_profit returned: {data['daily_profit']}")
    
    def test_dashboard_summary_returns_weekly_profit(self):
        """GET /api/dashboard/summary should return weekly_profit field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "weekly_profit" in data, "weekly_profit field missing from response"
        assert isinstance(data["weekly_profit"], (int, float)), "weekly_profit should be numeric"
        print(f"✓ weekly_profit returned: {data['weekly_profit']}")
    
    def test_dashboard_summary_returns_monthly_profit(self):
        """GET /api/dashboard/summary should return monthly_profit field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly_profit" in data, "monthly_profit field missing from response"
        assert isinstance(data["monthly_profit"], (int, float)), "monthly_profit should be numeric"
        print(f"✓ monthly_profit returned: {data['monthly_profit']}")
    
    def test_dashboard_summary_returns_yearly_profit(self):
        """GET /api/dashboard/summary should return yearly_profit field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "yearly_profit" in data, "yearly_profit field missing from response"
        assert isinstance(data["yearly_profit"], (int, float)), "yearly_profit should be numeric"
        print(f"✓ yearly_profit returned: {data['yearly_profit']}")
    
    # ========== PREVIOUS PERIOD PROFIT FIELDS TESTS ==========
    
    def test_dashboard_summary_returns_prev_weekly_profit(self):
        """GET /api/dashboard/summary should return prev_weekly_profit for comparisons"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "prev_weekly_profit" in data, "prev_weekly_profit field missing from response"
        assert isinstance(data["prev_weekly_profit"], (int, float)), "prev_weekly_profit should be numeric"
        print(f"✓ prev_weekly_profit returned: {data['prev_weekly_profit']}")
    
    def test_dashboard_summary_returns_prev_monthly_profit(self):
        """GET /api/dashboard/summary should return prev_monthly_profit for comparisons"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "prev_monthly_profit" in data, "prev_monthly_profit field missing from response"
        assert isinstance(data["prev_monthly_profit"], (int, float)), "prev_monthly_profit should be numeric"
        print(f"✓ prev_monthly_profit returned: {data['prev_monthly_profit']}")
    
    def test_dashboard_summary_returns_prev_yearly_profit(self):
        """GET /api/dashboard/summary should return prev_yearly_profit for comparisons"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "prev_yearly_profit" in data, "prev_yearly_profit field missing from response"
        assert isinstance(data["prev_yearly_profit"], (int, float)), "prev_yearly_profit should be numeric"
        print(f"✓ prev_yearly_profit returned: {data['prev_yearly_profit']}")
    
    # ========== EXPENSE FIELDS TESTS ==========
    
    def test_dashboard_summary_returns_expense_breakdown(self):
        """GET /api/dashboard/summary should return expense breakdown (Raw Materials, Salaries, Other)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check expense breakdown fields
        assert "month_raw_materials" in data, "month_raw_materials (purchases) field missing"
        assert "month_salaries" in data, "month_salaries field missing"
        assert "month_other_expenses" in data, "month_other_expenses field missing"
        
        assert isinstance(data["month_raw_materials"], (int, float))
        assert isinstance(data["month_salaries"], (int, float))
        assert isinstance(data["month_other_expenses"], (int, float))
        
        print(f"✓ month_raw_materials: {data['month_raw_materials']}")
        print(f"✓ month_salaries: {data['month_salaries']}")
        print(f"✓ month_other_expenses: {data['month_other_expenses']}")
    
    def test_dashboard_summary_returns_period_expenses(self):
        """GET /api/dashboard/summary should return daily, weekly, monthly, yearly expenses"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "daily_expenses" in data
        assert "weekly_expenses" in data
        assert "monthly_expenses" in data
        assert "yearly_expenses" in data
        
        print(f"✓ daily_expenses: {data['daily_expenses']}")
        print(f"✓ weekly_expenses: {data['weekly_expenses']}")
        print(f"✓ monthly_expenses: {data['monthly_expenses']}")
        print(f"✓ yearly_expenses: {data['yearly_expenses']}")
    
    # ========== PROFIT CALCULATION VALIDATION TESTS ==========
    
    def test_profit_calculation_formula(self):
        """Verify profit = Total Sales - Total Expenses (Raw Materials + Salaries + Other)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Monthly profit validation
        month_sales = data.get("month_sales", 0)
        month_purchases = data.get("month_purchases", 0)  # Raw Materials
        month_salaries = data.get("month_salaries", 0)
        month_other_expenses = data.get("month_other_expenses", 0)
        monthly_profit = data.get("monthly_profit", 0)
        
        total_expenses = month_purchases + month_salaries + month_other_expenses
        expected_profit = round(month_sales - total_expenses, 2)
        
        print(f"Month Sales: {month_sales}")
        print(f"Month Raw Materials (Purchases): {month_purchases}")
        print(f"Month Salaries: {month_salaries}")
        print(f"Month Other Expenses: {month_other_expenses}")
        print(f"Total Expenses: {total_expenses}")
        print(f"Expected Profit: {expected_profit}")
        print(f"Actual Monthly Profit: {monthly_profit}")
        
        # Allow small floating point difference
        assert abs(monthly_profit - expected_profit) < 0.1, \
            f"Monthly profit calculation mismatch. Expected: {expected_profit}, Got: {monthly_profit}"
        print("✓ Profit calculation formula verified: Net Profit = Total Sales - (Raw Materials + Salaries + Other Expenses)")
    
    def test_yearly_profit_vs_yearly_sales_and_expenses(self):
        """Verify yearly_profit = yearly_sales - yearly_expenses"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        yearly_sales = data.get("yearly_sales", 0)
        yearly_expenses = data.get("yearly_expenses", 0)
        yearly_profit = data.get("yearly_profit", 0)
        
        expected_profit = round(yearly_sales - yearly_expenses, 2)
        
        print(f"Yearly Sales: {yearly_sales}")
        print(f"Yearly Expenses: {yearly_expenses}")
        print(f"Expected Yearly Profit: {expected_profit}")
        print(f"Actual Yearly Profit: {yearly_profit}")
        
        assert abs(yearly_profit - expected_profit) < 0.1, \
            f"Yearly profit calculation mismatch. Expected: {expected_profit}, Got: {yearly_profit}"
        print("✓ Yearly profit calculation verified")
    
    # ========== EXISTING FEATURES TESTS ==========
    
    def test_existing_kpi_fields_still_present(self):
        """Verify existing KPI fields (today_sales, week_sales, etc.) still present"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "today_sales", "today_purchases",
            "week_sales", "week_purchases",
            "month_sales", "month_purchases",
            "prev_week_sales", "prev_week_purchases",
            "prev_month_sales", "prev_month_purchases"
        ]
        
        for field in required_fields:
            assert field in data, f"Required field {field} missing from dashboard summary"
            print(f"✓ {field}: {data[field]}")
    
    def test_smart_alerts_still_returned(self):
        """Verify smart_alerts array still returned in dashboard summary"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "smart_alerts" in data, "smart_alerts field missing"
        assert isinstance(data["smart_alerts"], list), "smart_alerts should be a list"
        print(f"✓ smart_alerts returned: {len(data['smart_alerts'])} alerts")
    
    def test_price_alerts_still_returned(self):
        """Verify price_alerts array still returned in dashboard summary"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "price_alerts" in data, "price_alerts field missing"
        assert isinstance(data["price_alerts"], list), "price_alerts should be a list"
        print(f"✓ price_alerts returned: {len(data['price_alerts'])} alerts")
    
    def test_weekly_trends_still_returned(self):
        """Verify weekly_trends array still returned for charts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "weekly_trends" in data, "weekly_trends field missing"
        assert isinstance(data["weekly_trends"], list), "weekly_trends should be a list"
        print(f"✓ weekly_trends returned: {len(data['weekly_trends'])} weeks")
    
    def test_top_items_and_suppliers_still_returned(self):
        """Verify top_items and top_suppliers arrays still returned"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "top_items" in data, "top_items field missing"
        assert "top_suppliers" in data, "top_suppliers field missing"
        assert isinstance(data["top_items"], list), "top_items should be a list"
        assert isinstance(data["top_suppliers"], list), "top_suppliers should be a list"
        print(f"✓ top_items returned: {len(data['top_items'])} items")
        print(f"✓ top_suppliers returned: {len(data['top_suppliers'])} suppliers")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
