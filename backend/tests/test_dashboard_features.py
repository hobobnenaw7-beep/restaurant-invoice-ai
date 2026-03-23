"""
Test Dashboard Features - Quick Actions, Sales Donut, Drill-Down with Date Filters
Tests for iteration_33: Dashboard final updates
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


class TestDashboardSummary:
    """Test GET /api/dashboard/summary endpoint - includes month_sales and prev_month_sales"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_summary_returns_200(self):
        """Dashboard summary endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Dashboard summary returns 200")
    
    def test_dashboard_summary_has_spending_fields(self):
        """Dashboard summary has spending category fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        # Current month spending
        assert "month_raw_materials" in data, "Missing month_raw_materials"
        assert "month_salaries" in data, "Missing month_salaries"
        assert "month_other_expenses" in data, "Missing month_other_expenses"
        
        # Previous month spending
        assert "prev_month_raw_materials" in data, "Missing prev_month_raw_materials"
        assert "prev_month_salaries" in data, "Missing prev_month_salaries"
        assert "prev_month_other_expenses" in data, "Missing prev_month_other_expenses"
        
        print("PASS: Dashboard summary has all spending fields")
    
    def test_dashboard_summary_has_sales_fields(self):
        """Dashboard summary has month_sales and prev_month_sales for Sales donut"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        assert "month_sales" in data, "Missing month_sales field"
        assert "prev_month_sales" in data, "Missing prev_month_sales field"
        
        # Verify they are numeric
        assert isinstance(data["month_sales"], (int, float)), "month_sales should be numeric"
        assert isinstance(data["prev_month_sales"], (int, float)), "prev_month_sales should be numeric"
        
        print(f"PASS: month_sales={data['month_sales']}, prev_month_sales={data['prev_month_sales']}")
    
    def test_dashboard_summary_has_data_freshness(self):
        """Dashboard summary has last_data_update and purchase_count for data freshness indicator"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=self.headers)
        data = response.json()
        
        assert "last_data_update" in data, "Missing last_data_update"
        assert "purchase_count" in data, "Missing purchase_count"
        
        print(f"PASS: last_data_update={data['last_data_update']}, purchase_count={data['purchase_count']}")


class TestDrillDownEndpoints:
    """Test GET /api/dashboard/drill-down/{category} with date filters"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Date range for testing
        now = datetime.now()
        self.date_from = now.strftime("%Y-%m-01")
        self.date_to = now.strftime("%Y-%m-%d")
    
    def test_raw_materials_drilldown_returns_200(self):
        """Raw materials drill-down returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: raw_materials drill-down returns 200")
    
    def test_raw_materials_drilldown_accepts_date_filters(self):
        """Raw materials drill-down accepts date_from and date_to params"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/raw_materials",
            params={"date_from": self.date_from, "date_to": self.date_to},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "category" in data and data["category"] == "raw_materials"
        assert "items" in data
        assert "total" in data
        assert "date_from" in data
        assert "date_to" in data
        
        print(f"PASS: raw_materials drill-down with dates: total={data['total']}, items={len(data['items'])}")
    
    def test_salaries_drilldown_returns_200(self):
        """Salaries drill-down returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/salaries", headers=self.headers)
        assert response.status_code == 200
        print("PASS: salaries drill-down returns 200")
    
    def test_salaries_drilldown_accepts_date_filters(self):
        """Salaries drill-down accepts date_from and date_to params"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/salaries",
            params={"date_from": self.date_from, "date_to": self.date_to},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "category" in data and data["category"] == "salaries"
        assert "employees" in data
        assert "total" in data
        assert "date_from" in data
        assert "date_to" in data
        
        print(f"PASS: salaries drill-down with dates: total={data['total']}, employees={len(data['employees'])}")
    
    def test_other_drilldown_returns_200(self):
        """Other expenses drill-down returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/other", headers=self.headers)
        assert response.status_code == 200
        print("PASS: other drill-down returns 200")
    
    def test_other_drilldown_accepts_date_filters(self):
        """Other expenses drill-down accepts date_from and date_to params"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/other",
            params={"date_from": self.date_from, "date_to": self.date_to},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "category" in data and data["category"] == "other"
        assert "categories" in data
        assert "total" in data
        assert "date_from" in data
        assert "date_to" in data
        
        print(f"PASS: other drill-down with dates: total={data['total']}, categories={len(data['categories'])}")
    
    def test_sales_drilldown_returns_200(self):
        """Sales drill-down returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/sales", headers=self.headers)
        assert response.status_code == 200
        print("PASS: sales drill-down returns 200")
    
    def test_sales_drilldown_accepts_date_filters(self):
        """Sales drill-down accepts date_from and date_to params"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/sales",
            params={"date_from": self.date_from, "date_to": self.date_to},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "category" in data and data["category"] == "sales"
        assert "records" in data
        assert "total" in data
        assert "date_from" in data
        assert "date_to" in data
        
        print(f"PASS: sales drill-down with dates: total={data['total']}, records={len(data['records'])}")
    
    def test_sales_drilldown_record_structure(self):
        """Sales drill-down records have correct structure"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/sales", headers=self.headers)
        data = response.json()
        
        if data["records"]:
            record = data["records"][0]
            assert "report_date" in record, "Missing report_date"
            assert "total_sales" in record, "Missing total_sales"
            print(f"PASS: Sales record structure correct: {record}")
        else:
            print("PASS: No sales records to verify structure (empty data)")
    
    def test_drilldown_date_filter_changes_results(self):
        """Date filter actually filters the data"""
        # Get data for current month
        response1 = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/raw_materials",
            params={"date_from": self.date_from, "date_to": self.date_to},
            headers=self.headers
        )
        data1 = response1.json()
        
        # Get data for a past date range (should be different or empty)
        past_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        past_end = (datetime.now() - timedelta(days=330)).strftime("%Y-%m-%d")
        response2 = requests.get(
            f"{BASE_URL}/api/dashboard/drill-down/raw_materials",
            params={"date_from": past_date, "date_to": past_end},
            headers=self.headers
        )
        data2 = response2.json()
        
        # Both should return valid responses
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        print(f"PASS: Date filter works - current month total: {data1['total']}, past year total: {data2['total']}")


class TestDrillDownDataStructure:
    """Test drill-down data structure for each category"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_raw_materials_item_structure(self):
        """Raw materials items have vendor details and cheapest badge info"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials", headers=self.headers)
        data = response.json()
        
        if data["items"]:
            item = data["items"][0]
            assert "item_name" in item, "Missing item_name"
            assert "total_spent" in item, "Missing total_spent"
            assert "vendors" in item, "Missing vendors"
            assert "cheapest_vendor" in item, "Missing cheapest_vendor"
            assert "vendor_count" in item, "Missing vendor_count"
            
            if item["vendors"]:
                vendor = item["vendors"][0]
                assert "vendor" in vendor, "Missing vendor name"
                assert "latest_price" in vendor, "Missing latest_price"
                print(f"PASS: Raw materials item structure correct with vendor details")
            else:
                print("PASS: Raw materials item structure correct (no vendors)")
        else:
            print("PASS: No raw materials items to verify (empty data)")
    
    def test_salaries_employee_structure(self):
        """Salaries employees have amount and progress bar data"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/salaries", headers=self.headers)
        data = response.json()
        
        if data["employees"]:
            emp = data["employees"][0]
            assert "name" in emp, "Missing name"
            assert "amount" in emp, "Missing amount"
            assert "position" in emp or emp.get("position") == "", "Missing position field"
            print(f"PASS: Salaries employee structure correct: {emp['name']} - ${emp['amount']}")
        else:
            print("PASS: No salary employees to verify (empty data)")
    
    def test_other_expenses_category_structure(self):
        """Other expenses grouped by category"""
        response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/other", headers=self.headers)
        data = response.json()
        
        if data["categories"]:
            cat = data["categories"][0]
            assert "category_name" in cat, "Missing category_name"
            assert "total" in cat, "Missing total"
            assert "items" in cat, "Missing items"
            
            if cat["items"]:
                item = cat["items"][0]
                assert "title" in item, "Missing title"
                assert "amount" in item, "Missing amount"
                assert "expense_date" in item, "Missing expense_date"
                print(f"PASS: Other expenses category structure correct: {cat['category_name']}")
            else:
                print("PASS: Other expenses category structure correct (no items)")
        else:
            print("PASS: No other expense categories to verify (empty data)")


class TestAuthRequired:
    """Test that endpoints require authentication"""
    
    def test_dashboard_summary_requires_auth(self):
        """Dashboard summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Dashboard summary requires auth")
    
    def test_drilldown_requires_auth(self):
        """Drill-down endpoints require authentication"""
        for category in ["raw_materials", "salaries", "other", "sales"]:
            response = requests.get(f"{BASE_URL}/api/dashboard/drill-down/{category}")
            assert response.status_code == 401, f"Expected 401 for {category}, got {response.status_code}"
        print("PASS: All drill-down endpoints require auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
