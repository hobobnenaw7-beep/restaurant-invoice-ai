"""
Tax Reporting Feature Tests
Tests for: /api/reports endpoint with tax fields, quarterly support, PDF/Excel downloads
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTaxReportingBackend:
    """Tax reporting API tests - Total Sales, Total Expenses, Net Profit, Net Margin"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    # ============== Monthly Report Tests ==============
    
    def test_monthly_report_returns_tax_fields(self, auth_headers):
        """GET /api/reports?report_type=monthly returns all tax summary fields"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "monthly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Core tax fields must be present
        assert "total_sales" in data, "Missing total_sales field"
        assert "total_expenses" in data, "Missing total_expenses field"
        assert "net_profit" in data, "Missing net_profit field"
        assert "total_salaries" in data, "Missing total_salaries field"
        assert "total_other_expenses" in data, "Missing total_other_expenses field"
        assert "net_margin_pct" in data, "Missing net_margin_pct field"
        
        # Previous period fields for comparisons
        assert "prev_sales" in data, "Missing prev_sales field"
        assert "prev_purchases" in data, "Missing prev_purchases field"
        assert "prev_salaries" in data, "Missing prev_salaries field"
        assert "prev_other_expenses" in data, "Missing prev_other_expenses field"
        assert "prev_total_expenses" in data, "Missing prev_total_expenses field"
        assert "prev_net_profit" in data, "Missing prev_net_profit field"
        
        print(f"Monthly report tax fields verified. Net Profit: ${data['net_profit']}, Net Margin: {data['net_margin_pct']}%")
    
    def test_monthly_report_net_profit_calculation(self, auth_headers):
        """Net Profit = Total Sales - (Raw Materials + Salaries + Other Expenses)"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "monthly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Calculate expected net profit
        total_sales = data["total_sales"]
        raw_materials = data["total_purchases"]
        salaries = data["total_salaries"]
        other_expenses = data["total_other_expenses"]
        total_expenses = data["total_expenses"]
        net_profit = data["net_profit"]
        
        # Verify total_expenses = raw_materials + salaries + other_expenses
        expected_total_expenses = round(raw_materials + salaries + other_expenses, 2)
        assert abs(total_expenses - expected_total_expenses) < 0.02, \
            f"Total expenses mismatch: {total_expenses} vs expected {expected_total_expenses}"
        
        # Verify net_profit = total_sales - total_expenses
        expected_net_profit = round(total_sales - total_expenses, 2)
        assert abs(net_profit - expected_net_profit) < 0.02, \
            f"Net profit mismatch: {net_profit} vs expected {expected_net_profit}"
        
        print(f"Net Profit calculation verified: ${total_sales} - (${raw_materials} + ${salaries} + ${other_expenses}) = ${net_profit}")
    
    # ============== Quarterly Report Tests ==============
    
    def test_quarterly_report_returns_tax_fields(self, auth_headers):
        """GET /api/reports?report_type=quarterly returns all tax summary fields"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "quarterly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Core tax fields must be present
        assert "total_sales" in data, "Missing total_sales in quarterly"
        assert "total_expenses" in data, "Missing total_expenses in quarterly"
        assert "net_profit" in data, "Missing net_profit in quarterly"
        assert "total_salaries" in data, "Missing total_salaries in quarterly"
        assert "total_other_expenses" in data, "Missing total_other_expenses in quarterly"
        assert "net_margin_pct" in data, "Missing net_margin_pct in quarterly"
        
        # Verify report_type
        assert data["report_type"] == "quarterly", f"Wrong report_type: {data['report_type']}"
        
        print(f"Quarterly report tax fields verified. Date range: {data['date_range']['start']} to {data['date_range']['end']}")
    
    def test_quarterly_date_range_format_q1(self, auth_headers):
        """GET /api/reports?report_type=quarterly&date=2026-Q1 returns correct Q1 date range"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "quarterly", "date": "2026-Q1"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Q1 should be Jan 1 to Mar 31
        assert data["date_range"]["start"] == "2026-01-01", f"Q1 start should be 2026-01-01, got {data['date_range']['start']}"
        assert data["date_range"]["end"] == "2026-03-31", f"Q1 end should be 2026-03-31, got {data['date_range']['end']}"
        
        # Previous quarter (Q4 2025) should be Oct 1 to Dec 31
        assert data["prev_date_range"]["start"] == "2025-10-01", f"Prev Q4 start should be 2025-10-01, got {data['prev_date_range']['start']}"
        assert data["prev_date_range"]["end"] == "2025-12-31", f"Prev Q4 end should be 2025-12-31, got {data['prev_date_range']['end']}"
        
        print(f"Q1 2026 date range verified: {data['date_range']['start']} to {data['date_range']['end']}")
    
    def test_quarterly_date_range_format_q2(self, auth_headers):
        """GET /api/reports?report_type=quarterly&date=2026-2 returns correct Q2 date range"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "quarterly", "date": "2026-2"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Q2 should be Apr 1 to Jun 30
        assert data["date_range"]["start"] == "2026-04-01", f"Q2 start should be 2026-04-01, got {data['date_range']['start']}"
        assert data["date_range"]["end"] == "2026-06-30", f"Q2 end should be 2026-06-30, got {data['date_range']['end']}"
        
        print(f"Q2 2026 date range verified: {data['date_range']['start']} to {data['date_range']['end']}")
    
    def test_quarterly_date_range_format_q3(self, auth_headers):
        """GET /api/reports?report_type=quarterly&date=2026-Q3 returns correct Q3 date range"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "quarterly", "date": "2026-Q3"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Q3 should be Jul 1 to Sep 30
        assert data["date_range"]["start"] == "2026-07-01", f"Q3 start should be 2026-07-01, got {data['date_range']['start']}"
        assert data["date_range"]["end"] == "2026-09-30", f"Q3 end should be 2026-09-30, got {data['date_range']['end']}"
        
        print(f"Q3 2026 date range verified: {data['date_range']['start']} to {data['date_range']['end']}")
    
    def test_quarterly_date_range_format_q4(self, auth_headers):
        """GET /api/reports?report_type=quarterly&date=2026-Q4 returns correct Q4 date range"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "quarterly", "date": "2026-Q4"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Q4 should be Oct 1 to Dec 31
        assert data["date_range"]["start"] == "2026-10-01", f"Q4 start should be 2026-10-01, got {data['date_range']['start']}"
        assert data["date_range"]["end"] == "2026-12-31", f"Q4 end should be 2026-12-31, got {data['date_range']['end']}"
        
        print(f"Q4 2026 date range verified: {data['date_range']['start']} to {data['date_range']['end']}")
    
    # ============== Yearly Report Tests ==============
    
    def test_yearly_report_returns_tax_fields(self, auth_headers):
        """GET /api/reports?report_type=yearly returns all tax summary fields"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "yearly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Core tax fields must be present
        assert "total_sales" in data, "Missing total_sales in yearly"
        assert "total_expenses" in data, "Missing total_expenses in yearly"
        assert "net_profit" in data, "Missing net_profit in yearly"
        assert "total_salaries" in data, "Missing total_salaries in yearly"
        assert "total_other_expenses" in data, "Missing total_other_expenses in yearly"
        assert "net_margin_pct" in data, "Missing net_margin_pct in yearly"
        
        # Verify report_type
        assert data["report_type"] == "yearly", f"Wrong report_type: {data['report_type']}"
        
        print(f"Yearly report tax fields verified. Date range: {data['date_range']['start']} to {data['date_range']['end']}")
    
    def test_yearly_report_expense_breakdown(self, auth_headers):
        """Yearly report includes all expense breakdowns"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "yearly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expense fields are numeric
        assert isinstance(data["total_purchases"], (int, float)), "total_purchases should be numeric"
        assert isinstance(data["total_salaries"], (int, float)), "total_salaries should be numeric"
        assert isinstance(data["total_other_expenses"], (int, float)), "total_other_expenses should be numeric"
        assert isinstance(data["total_expenses"], (int, float)), "total_expenses should be numeric"
        
        # Verify net_margin_pct is numeric
        assert isinstance(data["net_margin_pct"], (int, float)), "net_margin_pct should be numeric"
        
        print(f"Yearly expense breakdown: Raw Materials=${data['total_purchases']}, Salaries=${data['total_salaries']}, Other=${data['total_other_expenses']}")
    
    # ============== Weekly Report Tests ==============
    
    def test_weekly_report_returns_tax_fields(self, auth_headers):
        """GET /api/reports?report_type=weekly returns all tax summary fields"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "weekly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Core tax fields must be present
        assert "total_sales" in data, "Missing total_sales in weekly"
        assert "total_expenses" in data, "Missing total_expenses in weekly"
        assert "net_profit" in data, "Missing net_profit in weekly"
        assert "net_margin_pct" in data, "Missing net_margin_pct in weekly"
        
        # Verify report_type
        assert data["report_type"] == "weekly", f"Wrong report_type: {data['report_type']}"
        
        print(f"Weekly report tax fields verified. Net Profit: ${data['net_profit']}")
    
    # ============== PDF Download Tests ==============
    
    def test_quarterly_pdf_download(self, auth_headers):
        """GET /api/reports/download?report_type=quarterly&fmt=pdf returns valid PDF"""
        response = requests.get(f"{BASE_URL}/api/reports/download", 
                               params={"report_type": "quarterly", "fmt": "pdf"}, 
                               headers=auth_headers)
        assert response.status_code == 200, f"PDF download failed with status {response.status_code}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, f"Wrong content type: {content_type}"
        
        # Check content disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, f"Missing attachment disposition: {content_disp}"
        assert ".pdf" in content_disp, f"Filename should have .pdf extension: {content_disp}"
        
        # Check that content is valid PDF (starts with %PDF)
        content = response.content
        assert len(content) > 100, f"PDF content too small: {len(content)} bytes"
        assert content[:4] == b'%PDF', f"Content doesn't start with PDF header: {content[:20]}"
        
        print(f"Quarterly PDF downloaded successfully, size: {len(content)} bytes")
    
    def test_monthly_pdf_download(self, auth_headers):
        """GET /api/reports/download?report_type=monthly&fmt=pdf returns valid PDF"""
        response = requests.get(f"{BASE_URL}/api/reports/download", 
                               params={"report_type": "monthly", "fmt": "pdf"}, 
                               headers=auth_headers)
        assert response.status_code == 200, f"PDF download failed with status {response.status_code}"
        
        # Check PDF header
        content = response.content
        assert content[:4] == b'%PDF', f"Content doesn't start with PDF header"
        
        print(f"Monthly PDF downloaded successfully, size: {len(content)} bytes")
    
    # ============== Excel Download Tests ==============
    
    def test_monthly_excel_download(self, auth_headers):
        """GET /api/reports/download?report_type=monthly&fmt=excel returns valid Excel"""
        response = requests.get(f"{BASE_URL}/api/reports/download", 
                               params={"report_type": "monthly", "fmt": "excel"}, 
                               headers=auth_headers)
        assert response.status_code == 200, f"Excel download failed with status {response.status_code}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "xlsx" in content_type, f"Wrong content type: {content_type}"
        
        # Check content disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, f"Missing attachment disposition: {content_disp}"
        assert ".xlsx" in content_disp, f"Filename should have .xlsx extension: {content_disp}"
        
        # Check that content is valid XLSX (starts with PK - ZIP file format)
        content = response.content
        assert len(content) > 100, f"Excel content too small: {len(content)} bytes"
        assert content[:2] == b'PK', f"Content doesn't start with ZIP header (xlsx): {content[:10]}"
        
        print(f"Monthly Excel downloaded successfully, size: {len(content)} bytes")
    
    def test_quarterly_excel_download(self, auth_headers):
        """GET /api/reports/download?report_type=quarterly&fmt=excel returns valid Excel"""
        response = requests.get(f"{BASE_URL}/api/reports/download", 
                               params={"report_type": "quarterly", "fmt": "excel"}, 
                               headers=auth_headers)
        assert response.status_code == 200, f"Excel download failed with status {response.status_code}"
        
        # Check that content is valid XLSX
        content = response.content
        assert content[:2] == b'PK', f"Content doesn't start with ZIP header (xlsx)"
        
        print(f"Quarterly Excel downloaded successfully, size: {len(content)} bytes")
    
    def test_yearly_excel_download(self, auth_headers):
        """GET /api/reports/download?report_type=yearly&fmt=excel returns valid Excel"""
        response = requests.get(f"{BASE_URL}/api/reports/download", 
                               params={"report_type": "yearly", "fmt": "excel"}, 
                               headers=auth_headers)
        assert response.status_code == 200, f"Excel download failed with status {response.status_code}"
        
        # Check that content is valid XLSX
        content = response.content
        assert content[:2] == b'PK', f"Content doesn't start with ZIP header (xlsx)"
        
        print(f"Yearly Excel downloaded successfully, size: {len(content)} bytes")
    
    # ============== Existing Feature Tests ==============
    
    def test_report_includes_kpi_fields(self, auth_headers):
        """Reports still include existing KPI fields"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "monthly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Existing fields should still be present
        assert "total_purchases" in data, "Missing total_purchases"
        assert "profit" in data, "Missing profit (gross profit)"
        assert "margin_pct" in data, "Missing margin_pct (gross margin)"
        assert "spending_by_supplier" in data, "Missing spending_by_supplier"
        assert "top_items" in data, "Missing top_items"
        assert "price_changes" in data, "Missing price_changes"
        assert "daily_breakdown" in data, "Missing daily_breakdown"
        
        print(f"Existing KPI fields verified. Suppliers: {len(data.get('spending_by_supplier', []))}, Items: {len(data.get('top_items', []))}")
    
    def test_report_date_range_fields(self, auth_headers):
        """Reports include date_range and prev_date_range"""
        response = requests.get(f"{BASE_URL}/api/reports", params={"report_type": "monthly"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Date range fields
        assert "date_range" in data, "Missing date_range"
        assert "start" in data["date_range"], "Missing date_range.start"
        assert "end" in data["date_range"], "Missing date_range.end"
        
        assert "prev_date_range" in data, "Missing prev_date_range"
        assert "start" in data["prev_date_range"], "Missing prev_date_range.start"
        assert "end" in data["prev_date_range"], "Missing prev_date_range.end"
        
        print(f"Date ranges: Current={data['date_range']['start']} to {data['date_range']['end']}, Previous={data['prev_date_range']['start']} to {data['prev_date_range']['end']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
