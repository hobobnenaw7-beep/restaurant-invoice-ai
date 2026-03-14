"""
Test Reports Category APIs - Testing 6 tabbed report categories:
- Sales, Raw Materials, Salaries, Other Expenses, Vendors, Profit
- Date range filters, vendor dropdown filter (for vendor tab)
- PDF/Excel export functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for testing"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - cannot continue with tests")

@pytest.fixture(scope="module")
def headers(auth_token):
    """Return headers with authorization"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestSalesReport:
    """Tests for Sales category report - /api/reports/category/sales"""
    
    def test_sales_report_basic(self, headers):
        """Test GET /api/reports/category/sales returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/sales",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "category" in data and data["category"] == "sales"
        assert "date_from" in data
        assert "date_to" in data
        assert "total_sales" in data
        assert "record_count" in data
        assert "avg_per_entry" in data
        assert "records" in data
        assert isinstance(data["records"], list)
        print(f"✓ Sales report: total_sales={data['total_sales']}, records={data['record_count']}")
    
    def test_sales_report_date_filter(self, headers):
        """Test date range filter works on sales report"""
        # Get report with date range
        response = requests.get(
            f"{BASE_URL}/api/reports/category/sales",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["date_from"] == "2026-01-01"
        assert data["date_to"] == "2026-01-31"
        print(f"✓ Sales date filter: {data['date_from']} to {data['date_to']}")


class TestRawMaterialsReport:
    """Tests for Raw Materials category report - /api/reports/category/raw_materials"""
    
    def test_raw_materials_report_basic(self, headers):
        """Test GET /api/reports/category/raw_materials returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/raw_materials",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["category"] == "raw_materials"
        assert "total" in data
        assert "invoice_count" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        
        # If there are items, verify item structure
        if data["items"]:
            item = data["items"][0]
            assert "vendor" in item
            assert "item" in item
            assert "date" in item
            assert "quantity" in item
            assert "unit_price" in item
            assert "line_total" in item
        print(f"✓ Raw materials: total={data['total']}, invoices={data['invoice_count']}, items={len(data['items'])}")


class TestSalariesReport:
    """Tests for Salaries category report - /api/reports/category/salaries"""
    
    def test_salaries_report_basic(self, headers):
        """Test GET /api/reports/category/salaries returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/salaries",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["category"] == "salaries"
        assert "total" in data
        assert "record_count" in data
        assert "records" in data
        assert isinstance(data["records"], list)
        
        # If records exist, verify structure
        if data["records"]:
            rec = data["records"][0]
            assert "employee_name" in rec
            assert "amount" in rec
            assert "payment_date" in rec
        print(f"✓ Salaries: total={data['total']}, payments={data['record_count']}")


class TestOtherExpensesReport:
    """Tests for Other Expenses category report - /api/reports/category/other_expenses"""
    
    def test_other_expenses_report_basic(self, headers):
        """Test GET /api/reports/category/other_expenses returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/other_expenses",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["category"] == "other_expenses"
        assert "total" in data
        assert "record_count" in data
        assert "records" in data
        assert "breakdown" in data  # Category breakdown
        assert isinstance(data["breakdown"], list)
        
        # If records exist, verify structure
        if data["records"]:
            rec = data["records"][0]
            assert "title" in rec
            assert "category" in rec
            assert "amount" in rec
            assert "expense_date" in rec
        print(f"✓ Other expenses: total={data['total']}, records={data['record_count']}, breakdown={len(data['breakdown'])} categories")


class TestVendorReport:
    """Tests for Vendor category report - /api/reports/category/vendor"""
    
    def test_vendor_report_basic(self, headers):
        """Test GET /api/reports/category/vendor returns correct structure with vendor list"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/vendor",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["category"] == "vendor"
        assert "total" in data
        assert "invoice_count" in data
        assert "items" in data
        assert "vendors" in data  # Vendor list for dropdown
        assert isinstance(data["vendors"], list)
        assert "vendor" in data  # Current vendor filter value
        
        # If items exist, verify structure
        if data["items"]:
            item = data["items"][0]
            assert "vendor" in item
            assert "item" in item
            assert "date" in item
            assert "quantity" in item
            assert "price" in item
            assert "total" in item
        print(f"✓ Vendor report: total={data['total']}, invoices={data['invoice_count']}, vendors available={len(data['vendors'])}")
    
    def test_vendor_report_filtered(self, headers):
        """Test vendor filter works correctly"""
        # First get available vendors
        response = requests.get(
            f"{BASE_URL}/api/reports/category/vendor",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        data = response.json()
        
        if data.get("vendors"):
            vendor_name = data["vendors"][0]
            # Filter by specific vendor
            filtered_response = requests.get(
                f"{BASE_URL}/api/reports/category/vendor",
                params={"date_from": "2026-01-01", "date_to": "2026-03-14", "vendor": vendor_name},
                headers=headers
            )
            assert filtered_response.status_code == 200
            filtered_data = filtered_response.json()
            assert filtered_data["vendor"] == vendor_name
            print(f"✓ Vendor filter works: filtered by '{vendor_name}'")
        else:
            print("⚠ No vendors to test filter - skipping")


class TestProfitReport:
    """Tests for Profit category report - /api/reports/category/profit"""
    
    def test_profit_report_basic(self, headers):
        """Test GET /api/reports/category/profit returns net_profit and breakdown"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/profit",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["category"] == "profit"
        assert "total_sales" in data
        assert "raw_materials" in data
        assert "salaries" in data
        assert "other_expenses" in data
        assert "total_expenses" in data
        assert "net_profit" in data
        assert "net_margin_pct" in data
        
        # Verify calculations are correct
        calculated_expenses = data["raw_materials"] + data["salaries"] + data["other_expenses"]
        assert round(calculated_expenses, 2) == round(data["total_expenses"], 2)
        
        calculated_profit = data["total_sales"] - data["total_expenses"]
        assert round(calculated_profit, 2) == round(data["net_profit"], 2)
        
        print(f"✓ Profit: sales={data['total_sales']}, expenses={data['total_expenses']}, net_profit={data['net_profit']}, margin={data['net_margin_pct']}%")


class TestExportPDF:
    """Tests for PDF export functionality"""
    
    def test_sales_export_pdf(self, headers):
        """Test PDF export for sales category"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/sales/export",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14", "fmt": "pdf"},
            headers=headers
        )
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("Content-Type", "")
        assert len(response.content) > 0  # PDF has content
        print(f"✓ Sales PDF export: {len(response.content)} bytes")


class TestExportExcel:
    """Tests for Excel export functionality"""
    
    def test_sales_export_excel(self, headers):
        """Test Excel export for sales category"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/sales/export",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14", "fmt": "excel"},
            headers=headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("Content-Type", "")
        # Excel files can be served as various MIME types
        assert "spreadsheet" in content_type or "excel" in content_type or "octet-stream" in content_type or "openxml" in content_type
        assert len(response.content) > 0
        print(f"✓ Sales Excel export: {len(response.content)} bytes")
    
    def test_profit_export_excel(self, headers):
        """Test Excel export for profit category"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/profit/export",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14", "fmt": "excel"},
            headers=headers
        )
        assert response.status_code == 200
        assert len(response.content) > 0
        print(f"✓ Profit Excel export: {len(response.content)} bytes")


class TestInvalidCategory:
    """Test error handling for invalid category"""
    
    def test_invalid_category(self, headers):
        """Test that invalid category returns 400 error"""
        response = requests.get(
            f"{BASE_URL}/api/reports/category/invalid_category",
            params={"date_from": "2026-01-01", "date_to": "2026-03-14"},
            headers=headers
        )
        assert response.status_code == 400
        print("✓ Invalid category returns 400 error as expected")
