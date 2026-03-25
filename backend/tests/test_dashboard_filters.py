"""
Test Dashboard Year/Month Filter Feature
Tests the /api/dashboard/summary endpoint with year and month query parameters
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardFilters:
    """Dashboard year/month filter endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed - skipping tests")
        self.token = response.json().get("token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_dashboard_summary_default_params(self):
        """Test dashboard summary with no params defaults to current year"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return filter_year and filter_month in response
        assert "filter_year" in data
        assert "filter_month" in data
        
        # Default year should be current year
        current_year = datetime.now().year
        assert data["filter_year"] == current_year
        
        # Should have spending and sales data fields
        assert "month_raw_materials" in data
        assert "month_salaries" in data
        assert "month_other_expenses" in data
        assert "month_sales" in data
        assert "prev_month_raw_materials" in data
        assert "prev_month_sales" in data
        print(f"PASS: Default params return year={data['filter_year']}, month={data['filter_month']}")
    
    def test_dashboard_summary_specific_month(self):
        """Test dashboard summary with specific year and month"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"year": 2026, "month": 3},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify filter params are echoed back
        assert data["filter_year"] == 2026
        assert data["filter_month"] == 3
        
        # Should have data for March 2026
        assert isinstance(data["month_raw_materials"], (int, float))
        assert isinstance(data["month_sales"], (int, float))
        
        # Previous period should be February 2026
        assert isinstance(data["prev_month_raw_materials"], (int, float))
        assert isinstance(data["prev_month_sales"], (int, float))
        print(f"PASS: March 2026 - raw_materials=${data['month_raw_materials']}, sales=${data['month_sales']}")
    
    def test_dashboard_summary_all_months(self):
        """Test dashboard summary with month=0 (all months = full year)"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"year": 2026, "month": 0},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify filter params
        assert data["filter_year"] == 2026
        assert data["filter_month"] == 0
        
        # Full year totals should be >= any single month
        full_year_raw = data["month_raw_materials"]
        full_year_sales = data["month_sales"]
        
        # Get March data for comparison
        march_response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"year": 2026, "month": 3},
            headers=self.headers
        )
        march_data = march_response.json()
        
        # Full year should be >= single month
        assert full_year_raw >= march_data["month_raw_materials"]
        assert full_year_sales >= march_data["month_sales"]
        print(f"PASS: Full year 2026 - raw_materials=${full_year_raw}, sales=${full_year_sales}")
        print(f"      March 2026 - raw_materials=${march_data['month_raw_materials']}, sales=${march_data['month_sales']}")
    
    def test_dashboard_summary_january_prev_is_december(self):
        """Test that January's previous period is December of previous year"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"year": 2026, "month": 1},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["filter_year"] == 2026
        assert data["filter_month"] == 1
        
        # Previous period data should exist (December 2025)
        assert "prev_month_raw_materials" in data
        assert "prev_month_sales" in data
        print(f"PASS: January 2026 - prev_raw_materials=${data['prev_month_raw_materials']}")
    
    def test_dashboard_summary_year_range(self):
        """Test that various years work (2020 to current+1)"""
        current_year = datetime.now().year
        test_years = [2020, 2023, current_year, current_year + 1]
        
        for year in test_years:
            response = requests.get(
                f"{BASE_URL}/api/dashboard/summary",
                params={"year": year, "month": 1},
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filter_year"] == year
            print(f"PASS: Year {year} works correctly")
    
    def test_dashboard_summary_all_months_values(self):
        """Test that all 12 months work correctly"""
        for month in range(1, 13):
            response = requests.get(
                f"{BASE_URL}/api/dashboard/summary",
                params={"year": 2026, "month": month},
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filter_month"] == month
        print("PASS: All 12 months (1-12) work correctly")
    
    def test_dashboard_summary_data_consistency(self):
        """Test that full year data equals sum of monthly data"""
        # Get full year data
        full_year_response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"year": 2026, "month": 0},
            headers=self.headers
        )
        full_year_data = full_year_response.json()
        
        # Get individual months and sum
        monthly_raw_sum = 0
        monthly_sales_sum = 0
        for month in range(1, 13):
            response = requests.get(
                f"{BASE_URL}/api/dashboard/summary",
                params={"year": 2026, "month": month},
                headers=self.headers
            )
            data = response.json()
            monthly_raw_sum += data["month_raw_materials"]
            monthly_sales_sum += data["month_sales"]
        
        # Full year should equal sum of months (with small tolerance for floating point)
        assert abs(full_year_data["month_raw_materials"] - monthly_raw_sum) < 0.01
        assert abs(full_year_data["month_sales"] - monthly_sales_sum) < 0.01
        print(f"PASS: Full year totals match sum of monthly totals")
        print(f"      Raw materials: ${full_year_data['month_raw_materials']:.2f} == ${monthly_raw_sum:.2f}")
        print(f"      Sales: ${full_year_data['month_sales']:.2f} == ${monthly_sales_sum:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
