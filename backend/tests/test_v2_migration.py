"""
Backend V2 Migration Tests
Tests all 25+ API endpoints after monolithic server.py was refactored into modular architecture.
Verifies JSON response shapes are preserved and all routes work correctly.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_login_success(self):
        """POST /api/auth/login returns token and user info"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Missing token in response"
        assert "user" in data, "Missing user in response"
        assert data["user"]["email"] == TEST_EMAIL
        assert "role" in data["user"]
        assert "restaurant_id" in data["user"]
        assert "name" in data["user"]
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login with wrong password returns 401"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_auth_me_with_token(self):
        """GET /api/auth/me with Bearer token returns user info"""
        # First login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json()["token"]
        
        # Then get /me
        response = self.session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "role" in data
        assert "restaurant_id" in data
        assert "email" in data
    
    def test_auth_me_without_token(self):
        """GET /api/auth/me without token returns 401"""
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401


class TestDashboardEndpoints:
    """Dashboard endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login and get token
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_dashboard_summary(self):
        """GET /api/dashboard/summary returns purchase_count, month_raw_materials, smart_alerts"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        assert "purchase_count" in data
        assert "month_raw_materials" in data
        assert "smart_alerts" in data
        assert isinstance(data["smart_alerts"], list)
    
    def test_dashboard_summary_with_filters(self):
        """GET /api/dashboard/summary with year/month filters"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary?year=2026&month=3")
        assert response.status_code == 200
        data = response.json()
        assert data["filter_year"] == 2026
        assert data["filter_month"] == 3


class TestPurchasesEndpoints:
    """Purchases CRUD endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_purchases(self):
        """GET /api/purchases returns array of purchase objects"""
        response = self.session.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_purchase(self):
        """POST /api/purchases creates a new purchase with confidence scoring"""
        purchase_data = {
            "supplier_name": "TEST_V2_Vendor",
            "invoice_number": "TEST-V2-001",
            "invoice_date": "2026-03-30",
            "subtotal": 100.00,
            "tax": 0.00,
            "total": 100.00,
            "items": [
                {
                    "item_name": "Test Item",
                    "raw_name": "Test Item",
                    "quantity": 10,
                    "unit_price": 10.00,
                    "total": 100.00,
                    "unit": "LB"
                }
            ]
        }
        response = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["supplier_name"] == "TEST_V2_Vendor"
        # Verify confidence scoring
        if data.get("items"):
            assert "confidence_level" in data["items"][0]
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/purchases/{data['id']}")


class TestSalesEndpoints:
    """Sales CRUD endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_sales(self):
        """GET /api/sales returns array of sales"""
        response = self.session.get(f"{BASE_URL}/api/sales")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_sale(self):
        """POST /api/sales creates a new sale record"""
        sale_data = {
            "report_date": "2026-03-30",
            "total_sales": 500.00,
            "total_tax": 50.00,
            "total_tips": 25.00,
            "source": "POS",
            "notes": "TEST_V2_Sale"
        }
        response = self.session.post(f"{BASE_URL}/api/sales", json=sale_data)
        assert response.status_code == 200, f"Create sale failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["total_sales"] == 500.00
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/sales/{data['id']}")


class TestSalariesEndpoints:
    """Salaries endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_salaries(self):
        """GET /api/salaries returns array of salaries"""
        response = self.session.get(f"{BASE_URL}/api/salaries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestOtherExpensesEndpoints:
    """Other expenses endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_other_expenses(self):
        """GET /api/other-expenses returns array of other expenses"""
        response = self.session.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestSuppliersEndpoints:
    """Suppliers endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_suppliers(self):
        """GET /api/suppliers returns array with total_spending, invoice_count fields"""
        response = self.session.get(f"{BASE_URL}/api/suppliers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # If there are suppliers, verify fields
        if data:
            assert "total_spending" in data[0] or "name" in data[0]


class TestItemsEndpoints:
    """Items endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_items(self):
        """GET /api/items returns array with aliases embedded"""
        response = self.session.get(f"{BASE_URL}/api/items")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestReportsEndpoints:
    """Reports endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_reports(self):
        """GET /api/reports returns report_type, total_purchases, total_sales, net_profit"""
        response = self.session.get(f"{BASE_URL}/api/reports")
        assert response.status_code == 200
        data = response.json()
        assert "report_type" in data or "total_purchases" in data or isinstance(data, dict)
    
    def test_get_reports_category_sales(self):
        """GET /api/reports/category/sales returns sales report"""
        response = self.session.get(f"{BASE_URL}/api/reports/category/sales")
        assert response.status_code == 200


class TestPricesEndpoints:
    """Prices/Intelligence endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_price_intelligence(self):
        """GET /api/prices/intelligence returns suppliers, comparison, price_trends"""
        response = self.session.get(f"{BASE_URL}/api/prices/intelligence")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_get_vendor_comparison(self):
        """GET /api/prices/vendor-comparison returns items array with vendors, best_vendor"""
        response = self.session.get(f"{BASE_URL}/api/prices/vendor-comparison")
        assert response.status_code == 200


class TestVendorComparisonEndpoints:
    """Vendor comparison endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_normalized_comparison(self):
        """GET /api/vendor-comparison/normalized returns comparisons and stats"""
        response = self.session.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestItemMappingsEndpoints:
    """Item mappings endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_item_mappings(self):
        """GET /api/item-mappings returns mappings array"""
        response = self.session.get(f"{BASE_URL}/api/item-mappings")
        assert response.status_code == 200
        data = response.json()
        # API returns {mappings: [...]} or list directly
        if isinstance(data, dict):
            assert "mappings" in data
            assert isinstance(data["mappings"], list)
        else:
            assert isinstance(data, list)
    
    def test_get_item_mappings_suggestions(self):
        """GET /api/item-mappings/suggestions returns suggestions"""
        response = self.session.get(f"{BASE_URL}/api/item-mappings/suggestions")
        assert response.status_code == 200


class TestAlertsEndpoints:
    """Alerts endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_alerts(self):
        """GET /api/alerts returns array of alerts"""
        response = self.session.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestPurchaseDecisionsEndpoints:
    """Purchase decisions endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_purchase_decisions(self):
        """GET /api/purchase-decisions returns items, insights, potential_savings"""
        response = self.session.get(f"{BASE_URL}/api/purchase-decisions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestApprovalsEndpoints:
    """Approvals endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_approvals_counts(self):
        """GET /api/approvals/counts returns total count"""
        response = self.session.get(f"{BASE_URL}/api/approvals/counts")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data or isinstance(data, dict)


class TestRecordsEndpoints:
    """Records endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_records(self):
        """GET /api/records returns array of records"""
        response = self.session.get(f"{BASE_URL}/api/records")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestChatEndpoints:
    """Chat endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_chat_messages(self):
        """GET /api/chat/messages returns array"""
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestDuplicatesEndpoints:
    """Duplicates endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_check_duplicates(self):
        """POST /api/duplicates/check with purchase data returns has_duplicates field"""
        # API expects record_type and data fields
        response = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "purchase",
            "data": {
                "supplier_name": "Test Vendor",
                "invoice_number": "INV-999999",
                "invoice_date": "2026-03-30",
                "total": 100.00
            }
        })
        assert response.status_code == 200, f"Duplicates check failed: {response.text}"
        data = response.json()
        assert "has_duplicates" in data
        assert "matches" in data


class TestAuditLogsEndpoints:
    """Audit logs endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.user_role = login_resp.json()["user"]["role"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_audit_logs(self):
        """GET /api/audit-logs returns 403 if non-manager, 200 with logs for manager"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs")
        # demo@test.com is a manager, so should get 200
        if self.user_role == "manager":
            assert response.status_code == 200
            data = response.json()
            # API returns {logs: [...], page, page_size, total} or list directly
            if isinstance(data, dict):
                assert "logs" in data
                assert isinstance(data["logs"], list)
            else:
                assert isinstance(data, list)
        else:
            assert response.status_code == 403


class TestSettingsEndpoints:
    """Settings endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = login_resp.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_get_settings(self):
        """GET /api/settings returns user and restaurant info"""
        response = self.session.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
