"""
Test Dashboard Drill-Down Functionality
Tests the new drill-down endpoints for Raw Materials, Salaries, and Other expenses
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardDrillDown:
    """Tests for /api/dashboard/drill-down/{category} endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    # ==================== RAW MATERIALS DRILL-DOWN ====================
    
    def test_raw_materials_returns_200(self):
        """GET /api/dashboard/drill-down/raw_materials returns 200"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        assert response.status_code == 200
        print("PASS: raw_materials endpoint returns 200")
    
    def test_raw_materials_has_required_fields(self):
        """raw_materials response has category, items array, and total"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        data = response.json()
        
        assert "category" in data, "Missing 'category' field"
        assert data["category"] == "raw_materials", f"Expected category='raw_materials', got '{data['category']}'"
        assert "items" in data, "Missing 'items' field"
        assert isinstance(data["items"], list), "'items' should be a list"
        assert "total" in data, "Missing 'total' field"
        print(f"PASS: raw_materials has required fields (category, items, total). Total: ${data['total']}")
    
    def test_raw_materials_item_structure(self):
        """Each raw_materials item has required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        data = response.json()
        
        if len(data["items"]) > 0:
            item = data["items"][0]
            required_fields = ["item_name", "total_spent", "vendors", "cheapest_vendor", "vendor_count"]
            for field in required_fields:
                assert field in item, f"Item missing '{field}' field"
            print(f"PASS: raw_materials items have required fields. First item: {item['item_name']}")
        else:
            print("SKIP: No items in raw_materials to test structure")
    
    def test_raw_materials_vendor_structure(self):
        """Each vendor in raw_materials has required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        data = response.json()
        
        # Find an item with vendors
        for item in data["items"]:
            if len(item.get("vendors", [])) > 0:
                vendor = item["vendors"][0]
                required_fields = ["vendor", "supplier_id", "latest_price", "avg_price", 
                                   "min_price", "max_price", "purchase_count", "unit", "last_date"]
                for field in required_fields:
                    assert field in vendor, f"Vendor missing '{field}' field"
                print(f"PASS: raw_materials vendors have required fields. Vendor: {vendor['vendor']}")
                return
        print("SKIP: No vendors found to test structure")
    
    def test_raw_materials_sorted_by_total_spent(self):
        """raw_materials items are sorted by total_spent descending"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        data = response.json()
        
        items = [i for i in data["items"] if i.get("total_spent", 0) > 0]
        if len(items) >= 2:
            for i in range(len(items) - 1):
                assert items[i]["total_spent"] >= items[i+1]["total_spent"], \
                    f"Items not sorted: {items[i]['item_name']} (${items[i]['total_spent']}) should be >= {items[i+1]['item_name']} (${items[i+1]['total_spent']})"
            print(f"PASS: raw_materials items sorted by total_spent descending. Top: {items[0]['item_name']} (${items[0]['total_spent']})")
        else:
            print("SKIP: Not enough items to test sorting")
    
    def test_raw_materials_cheapest_vendor_correct(self):
        """cheapest_vendor matches the vendor with lowest latest_price"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        data = response.json()
        
        for item in data["items"]:
            if len(item.get("vendors", [])) > 1:
                vendors = item["vendors"]
                # Vendors should be sorted by latest_price ascending
                cheapest = min(vendors, key=lambda v: v["latest_price"])
                assert item["cheapest_vendor"] == cheapest["vendor"], \
                    f"cheapest_vendor mismatch for {item['item_name']}: expected {cheapest['vendor']}, got {item['cheapest_vendor']}"
                print(f"PASS: cheapest_vendor correct for {item['item_name']}: {item['cheapest_vendor']}")
                return
        print("SKIP: No items with multiple vendors to test cheapest_vendor")
    
    # ==================== SALARIES DRILL-DOWN ====================
    
    def test_salaries_returns_200(self):
        """GET /api/dashboard/drill-down/salaries returns 200"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/salaries")
        assert response.status_code == 200
        print("PASS: salaries endpoint returns 200")
    
    def test_salaries_has_required_fields(self):
        """salaries response has category, employees array, and total"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/salaries")
        data = response.json()
        
        assert "category" in data, "Missing 'category' field"
        assert data["category"] == "salaries", f"Expected category='salaries', got '{data['category']}'"
        assert "employees" in data, "Missing 'employees' field"
        assert isinstance(data["employees"], list), "'employees' should be a list"
        assert "total" in data, "Missing 'total' field"
        print(f"PASS: salaries has required fields. Total: ${data['total']}, Employees: {len(data['employees'])}")
    
    def test_salaries_employee_structure(self):
        """Each employee has required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/salaries")
        data = response.json()
        
        if len(data["employees"]) > 0:
            emp = data["employees"][0]
            required_fields = ["name", "position", "amount", "payment_date", "payment_method"]
            for field in required_fields:
                assert field in emp, f"Employee missing '{field}' field"
            print(f"PASS: salaries employees have required fields. First: {emp['name']} - ${emp['amount']}")
        else:
            print("SKIP: No employees in salaries to test structure")
    
    def test_salaries_sorted_by_amount(self):
        """salaries employees are sorted by amount descending"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/salaries")
        data = response.json()
        
        employees = data["employees"]
        if len(employees) >= 2:
            for i in range(len(employees) - 1):
                assert employees[i]["amount"] >= employees[i+1]["amount"], \
                    f"Employees not sorted: {employees[i]['name']} (${employees[i]['amount']}) should be >= {employees[i+1]['name']} (${employees[i+1]['amount']})"
            print(f"PASS: salaries sorted by amount descending. Top: {employees[0]['name']} (${employees[0]['amount']})")
        else:
            print("SKIP: Not enough employees to test sorting")
    
    # ==================== OTHER EXPENSES DRILL-DOWN ====================
    
    def test_other_returns_200(self):
        """GET /api/dashboard/drill-down/other returns 200"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/other")
        assert response.status_code == 200
        print("PASS: other endpoint returns 200")
    
    def test_other_has_required_fields(self):
        """other response has category, categories array, and total"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/other")
        data = response.json()
        
        assert "category" in data, "Missing 'category' field"
        assert data["category"] == "other", f"Expected category='other', got '{data['category']}'"
        assert "categories" in data, "Missing 'categories' field"
        assert isinstance(data["categories"], list), "'categories' should be a list"
        assert "total" in data, "Missing 'total' field"
        print(f"PASS: other has required fields. Total: ${data['total']}, Categories: {len(data['categories'])}")
    
    def test_other_category_structure(self):
        """Each category in other has required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/other")
        data = response.json()
        
        if len(data["categories"]) > 0:
            cat = data["categories"][0]
            required_fields = ["category_name", "total", "items"]
            for field in required_fields:
                assert field in cat, f"Category missing '{field}' field"
            print(f"PASS: other categories have required fields. First: {cat['category_name']} - ${cat['total']}")
        else:
            print("SKIP: No categories in other to test structure")
    
    def test_other_item_structure(self):
        """Each item in other categories has required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/other")
        data = response.json()
        
        for cat in data["categories"]:
            if len(cat.get("items", [])) > 0:
                item = cat["items"][0]
                required_fields = ["title", "amount", "expense_date", "vendor", "notes"]
                for field in required_fields:
                    assert field in item, f"Item missing '{field}' field"
                print(f"PASS: other items have required fields. First: {item['title']} - ${item['amount']}")
                return
        print("SKIP: No items in other categories to test structure")
    
    # ==================== INVALID CATEGORY ====================
    
    def test_invalid_category_returns_error(self):
        """GET /api/dashboard/drill-down/invalid returns error message"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/drill-down/invalid")
        assert response.status_code == 200  # Returns 200 with error in body
        data = response.json()
        assert "error" in data, "Expected 'error' field for invalid category"
        print(f"PASS: invalid category returns error: {data['error']}")
    
    # ==================== AUTHENTICATION ====================
    
    def test_raw_materials_requires_auth(self):
        """raw_materials endpoint requires authentication"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard/drill-down/raw_materials")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: raw_materials requires authentication (401 without token)")
    
    def test_salaries_requires_auth(self):
        """salaries endpoint requires authentication"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard/drill-down/salaries")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: salaries requires authentication (401 without token)")
    
    def test_other_requires_auth(self):
        """other endpoint requires authentication"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard/drill-down/other")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: other requires authentication (401 without token)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
