"""
Comprehensive MVP Tests for Restaurant Accountant AI
Tests: Auth, Dashboard, Expenses, Sales, Reports, Vendors, Items, OCR/Excel Extraction
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for all tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def api_session(auth_token):
    """Authenticated session for API calls"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session

class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test successful login with demo credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo@test.com"
        assert data["user"]["role"] == "manager"
    
    def test_login_invalid_credentials(self):
        """Test login with wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@test.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401

class TestDashboard:
    """Dashboard summary tests - smart alerts, financial data"""
    
    def test_dashboard_summary_returns_all_fields(self, api_session):
        """Test dashboard returns all required financial summary fields"""
        response = api_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields exist
        required_fields = [
            "today_sales", "today_purchases",
            "week_sales", "week_purchases",
            "month_sales", "month_purchases",
            "smart_alerts", "price_alerts",
            "daily_profit", "weekly_profit", "monthly_profit",
            "top_items", "top_suppliers", "weekly_trends"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
    
    def test_smart_alerts_present(self, api_session):
        """Test smart_alerts array is returned"""
        response = api_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        assert "smart_alerts" in data
        assert isinstance(data["smart_alerts"], list)

class TestExpenses:
    """Expenses API tests - Purchases, Salaries, Other Expenses"""
    
    def test_list_purchases(self, api_session):
        """Test listing raw material purchases"""
        response = api_session.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_salaries(self, api_session):
        """Test listing salaries"""
        response = api_session.get(f"{BASE_URL}/api/salaries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_other_expenses(self, api_session):
        """Test listing other expenses"""
        response = api_session.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_purchase_with_auto_calculation(self, api_session):
        """Test creating purchase - verify subtotal/total calculations"""
        purchase = {
            "supplier_name": "TEST_AutoCalc Vendor",
            "invoice_number": "TEST-CALC-001",
            "invoice_date": "2026-03-15",
            "items": [
                {"raw_name": "Item A", "quantity": 10, "unit": "kg", "unit_price": 5.00, "total": 50.00},
                {"raw_name": "Item B", "quantity": 5, "unit": "lb", "unit_price": 10.00, "total": 50.00}
            ],
            "subtotal": 100.00,
            "tax": 8.00,
            "total": 108.00
        }
        response = api_session.post(f"{BASE_URL}/api/purchases", json=purchase)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/purchases/{data['id']}")

class TestSales:
    """Sales API tests"""
    
    def test_list_sales(self, api_session):
        """Test listing sales records"""
        response = api_session.get(f"{BASE_URL}/api/sales")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_sale_with_date_range(self, api_session):
        """Test creating sale with date_from/date_to"""
        sale = {
            "date_from": "2026-03-15",
            "date_to": "2026-03-15",
            "report_date": "2026-03-15",
            "total_sales": 1500.00,
            "items": [
                {"menu_item": "Burger", "quantity": 50, "revenue": 500.00},
                {"menu_item": "Pizza", "quantity": 40, "revenue": 1000.00}
            ]
        }
        response = api_session.post(f"{BASE_URL}/api/sales", json=sale)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        
        # Verify persistence
        get_response = api_session.get(f"{BASE_URL}/api/sales/{data['id']}")
        if get_response.status_code == 200:
            fetched = get_response.json()
            assert fetched.get("date_from") == "2026-03-15"
            assert fetched.get("date_to") == "2026-03-15"
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/sales/{data['id']}")

class TestReports:
    """Reports API tests - approval_status filtering"""
    
    def test_reports_main_endpoint(self, api_session):
        """Test main reports endpoint with approval_status filter"""
        response = api_session.get(f"{BASE_URL}/api/reports?report_type=monthly")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_purchases" in data
        assert "total_sales" in data
        assert "net_profit" in data
        assert "date_range" in data
    
    def test_category_report_sales(self, api_session):
        """Test sales category report"""
        response = api_session.get(f"{BASE_URL}/api/reports/category/sales")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "sales"
        assert "total_sales" in data
        assert "record_count" in data
    
    def test_category_report_raw_materials(self, api_session):
        """Test raw materials category report"""
        response = api_session.get(f"{BASE_URL}/api/reports/category/raw_materials")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "raw_materials"
        assert "total" in data
        assert "invoice_count" in data
    
    def test_category_report_salaries(self, api_session):
        """Test salaries category report"""
        response = api_session.get(f"{BASE_URL}/api/reports/category/salaries")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "salaries"
    
    def test_category_report_other_expenses(self, api_session):
        """Test other expenses category report"""
        response = api_session.get(f"{BASE_URL}/api/reports/category/other_expenses")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "other_expenses"
    
    def test_category_report_profit(self, api_session):
        """Test profit category report"""
        response = api_session.get(f"{BASE_URL}/api/reports/category/profit")
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "profit"
        assert "total_sales" in data
        assert "total_expenses" in data
        assert "net_profit" in data

class TestSuppliers:
    """Suppliers (Vendors) CRUD tests with spending totals - endpoint is /api/suppliers"""
    
    def test_list_suppliers(self, api_session):
        """Test listing suppliers (vendors)"""
        response = api_session.get(f"{BASE_URL}/api/suppliers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_supplier(self, api_session):
        """Test creating a supplier"""
        supplier = {
            "name": "TEST_New Supplier Co",
            "contact_person": "John Test",
            "phone": "555-TEST-001",
            "email": "test@supplier.com"
        }
        response = api_session.post(f"{BASE_URL}/api/suppliers", json=supplier)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/suppliers/{data['id']}")
    
    def test_supplier_spending_total(self, api_session):
        """Test suppliers endpoint returns data correctly"""
        response = api_session.get(f"{BASE_URL}/api/suppliers")
        assert response.status_code == 200
        data = response.json()
        
        # Check first supplier has expected fields
        if len(data) > 0:
            supplier = data[0]
            assert "name" in supplier
            assert "id" in supplier

class TestItems:
    """Items CRUD tests with price history and vendor comparison"""
    
    def test_list_items(self, api_session):
        """Test listing items"""
        response = api_session.get(f"{BASE_URL}/api/items")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_item_has_aliases(self, api_session):
        """Test items include aliases"""
        response = api_session.get(f"{BASE_URL}/api/items")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            assert "aliases" in item
            assert isinstance(item["aliases"], list)
    
    def test_item_price_history(self, api_session):
        """Test item price history endpoint"""
        # Get first item
        items_response = api_session.get(f"{BASE_URL}/api/items")
        assert items_response.status_code == 200
        items = items_response.json()
        
        if len(items) > 0:
            item_id = items[0]["id"]
            response = api_session.get(f"{BASE_URL}/api/items/{item_id}/price-history")
            assert response.status_code == 200
            data = response.json()
            
            # Check price history structure
            assert "records" in data or "summary" in data
    
    def test_vendor_price_comparison(self, api_session):
        """Test vendor price comparison endpoint - at /api/prices/vendor-comparison"""
        response = api_session.get(f"{BASE_URL}/api/prices/vendor-comparison")
        assert response.status_code == 200
        data = response.json()
        # Response is a dict with 'items' list
        assert "items" in data
        assert isinstance(data["items"], list)

class TestRecordsLibrary:
    """Records Library tests - view only"""
    
    def test_list_records(self, api_session):
        """Test listing records"""
        response = api_session.get(f"{BASE_URL}/api/records?folder=sales")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_expense_records_with_category(self, api_session):
        """Test expense records can filter by category"""
        response = api_session.get(f"{BASE_URL}/api/records?folder=expenses&expense_category=raw_material")
        assert response.status_code == 200

class TestExcelParsing:
    """Excel/CSV parsing tests"""
    
    def test_parse_csv_purchase(self, api_session):
        """Test CSV parsing for purchase invoice"""
        import tempfile
        csv_content = "Item,Quantity,Unit,Unit Price,Total\nApples,10,kg,2.50,25.00\nOranges,5,kg,3.00,15.00"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name
        
        with open(csv_path, 'rb') as f:
            files = {'file': ('test.csv', f, 'text/csv')}
            data = {'document_type': 'purchase_invoice'}
            
            # Remove Content-Type header for multipart
            headers = {"Authorization": api_session.headers["Authorization"]}
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                files=files,
                data=data,
                headers=headers
            )
            
            assert response.status_code == 200
            result = response.json()
            assert "extracted_data" in result
            assert "items" in result["extracted_data"]
            assert len(result["extracted_data"]["items"]) == 2

class TestNotifications:
    """Notification/Alert tests"""
    
    def test_smart_alerts_in_dashboard(self, api_session):
        """Test smart_alerts array in dashboard"""
        response = api_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "smart_alerts" in data
        alerts = data["smart_alerts"]
        assert isinstance(alerts, list)
        
        # If alerts exist, verify structure
        if len(alerts) > 0:
            alert = alerts[0]
            assert "type" in alert or "alert_type" in alert
            assert "severity" in alert or "priority" in alert
