"""
Test module for Reports API endpoints.
Tests: /api/reports, /api/reports/download (PDF & Excel)
Period types: weekly, monthly, yearly
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
TEST_EMAIL = "test@demo.com"
TEST_PASSWORD = "password123"

class TestReportsAPI:
    """Reports endpoint tests - GET /api/reports"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed - skipping tests")
        self.token = response.json().get("token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    # ========== Weekly Reports ==========
    def test_get_weekly_report_default(self):
        """Test GET /api/reports with weekly report type (default)"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "weekly"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify report structure
        assert "report_type" in data
        assert data["report_type"] == "weekly"
        assert "date_range" in data
        assert "start" in data["date_range"]
        assert "end" in data["date_range"]
        
        # Verify KPI fields exist
        assert "total_sales" in data
        assert "total_purchases" in data
        assert "profit" in data
        assert "margin_pct" in data
        
        # Verify previous period comparison fields
        assert "prev_sales" in data
        assert "prev_purchases" in data
        assert "prev_profit" in data
        assert "prev_date_range" in data
        
        # Verify tables data
        assert "spending_by_supplier" in data
        assert "price_changes" in data
        assert "daily_breakdown" in data
        assert "top_items" in data
        
        print(f"Weekly report loaded: {data['date_range']['start']} to {data['date_range']['end']}")
        print(f"KPIs - Sales: ${data['total_sales']}, Purchases: ${data['total_purchases']}, Profit: ${data['profit']}, Margin: {data['margin_pct']}%")
    
    def test_weekly_report_has_supplier_spending(self):
        """Test that weekly report includes supplier spending data"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "weekly"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check supplier spending structure
        for supplier in data.get("spending_by_supplier", []):
            assert "name" in supplier
            assert "total" in supplier
            assert "invoices" in supplier
            assert isinstance(supplier["total"], (int, float))
            assert isinstance(supplier["invoices"], int)
        
        print(f"Found {len(data.get('spending_by_supplier', []))} suppliers in spending data")
    
    def test_weekly_report_has_price_changes(self):
        """Test that weekly report includes price changes data"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "weekly"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check price changes structure
        for change in data.get("price_changes", []):
            assert "item" in change
            assert "current_price" in change
            assert "previous_price" in change
            assert "change_pct" in change
            assert isinstance(change["change_pct"], (int, float))
        
        print(f"Found {len(data.get('price_changes', []))} price changes")
    
    # ========== Monthly Reports ==========
    def test_get_monthly_report(self):
        """Test GET /api/reports with monthly report type"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "monthly"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["report_type"] == "monthly"
        assert "total_sales" in data
        assert "total_purchases" in data
        assert "margin_pct" in data
        assert "prev_sales" in data
        assert "prev_purchases" in data
        
        print(f"Monthly report: {data['date_range']['start']} to {data['date_range']['end']}")
    
    # ========== Yearly Reports ==========
    def test_get_yearly_report(self):
        """Test GET /api/reports with yearly report type"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "yearly"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["report_type"] == "yearly"
        assert "total_sales" in data
        assert "total_purchases" in data
        assert "margin_pct" in data
        
        print(f"Yearly report: {data['date_range']['start']} to {data['date_range']['end']}")
    
    # ========== Custom Date Reports ==========
    def test_get_report_with_custom_date(self):
        """Test GET /api/reports with custom date parameter"""
        response = requests.get(
            f"{BASE_URL}/api/reports",
            params={"report_type": "weekly", "date": "2025-01-06"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["report_type"] == "weekly"
        assert data["date_range"]["start"] == "2025-01-06"
        
        print(f"Custom date report: {data['date_range']['start']} to {data['date_range']['end']}")


class TestReportsDownloadAPI:
    """Reports download tests - GET /api/reports/download"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_download_pdf_weekly(self):
        """Test PDF download for weekly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "weekly", "fmt": "pdf"},
            headers=self.headers
        )
        assert response.status_code == 200, f"PDF download failed: {response.status_code}"
        
        # Verify PDF content type
        content_type = response.headers.get("content-type", "")
        assert "pdf" in content_type.lower(), f"Expected PDF content type, got {content_type}"
        
        # Verify file attachment header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp.lower()
        assert ".pdf" in content_disp.lower()
        
        # Verify response has content
        assert len(response.content) > 1000, "PDF file too small, may be empty"
        
        print(f"PDF download successful: {len(response.content)} bytes, {content_disp}")
    
    def test_download_excel_weekly(self):
        """Test Excel download for weekly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "weekly", "fmt": "excel"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Excel download failed: {response.status_code}"
        
        # Verify Excel content type
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type.lower() or "xlsx" in content_type.lower(), f"Expected Excel content type, got {content_type}"
        
        # Verify file attachment header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp.lower()
        assert ".xlsx" in content_disp.lower()
        
        # Verify response has content
        assert len(response.content) > 1000, "Excel file too small, may be empty"
        
        print(f"Excel download successful: {len(response.content)} bytes, {content_disp}")
    
    def test_download_pdf_monthly(self):
        """Test PDF download for monthly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "monthly", "fmt": "pdf"},
            headers=self.headers
        )
        assert response.status_code == 200
        assert "pdf" in response.headers.get("content-type", "").lower()
        print(f"Monthly PDF download: {len(response.content)} bytes")
    
    def test_download_excel_monthly(self):
        """Test Excel download for monthly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "monthly", "fmt": "excel"},
            headers=self.headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type.lower() or "xlsx" in content_type.lower()
        print(f"Monthly Excel download: {len(response.content)} bytes")
    
    def test_download_pdf_yearly(self):
        """Test PDF download for yearly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "yearly", "fmt": "pdf"},
            headers=self.headers
        )
        assert response.status_code == 200
        assert "pdf" in response.headers.get("content-type", "").lower()
        print(f"Yearly PDF download: {len(response.content)} bytes")
    
    def test_download_excel_yearly(self):
        """Test Excel download for yearly report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"report_type": "yearly", "fmt": "excel"},
            headers=self.headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type.lower() or "xlsx" in content_type.lower()
        print(f"Yearly Excel download: {len(response.content)} bytes")


class TestReportsAuthentication:
    """Test authentication for reports endpoints"""
    
    def test_reports_requires_auth(self):
        """Test that /api/reports requires authentication"""
        response = requests.get(f"{BASE_URL}/api/reports")
        assert response.status_code == 401
        print("GET /api/reports correctly requires authentication")
    
    def test_reports_download_requires_auth(self):
        """Test that /api/reports/download requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/reports/download",
            params={"fmt": "pdf"}
        )
        assert response.status_code == 401
        print("GET /api/reports/download correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
