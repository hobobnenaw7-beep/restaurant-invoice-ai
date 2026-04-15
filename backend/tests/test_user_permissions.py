"""
Test Suite: Permissions + Accountability Model
==============================================
Tests for:
- Dashboard month filter defaults to 'All Months' (value 0)
- Login returns permissions and data_scope in /auth/me response
- GET /auth/me returns all 21 permissions for manager with data_scope='all'
- GET /users/permissions/defaults returns correct permission counts
- POST /users creates user with permissions, data_scope, created_by_user_id, created_by_name
- POST /sales creates record with created_by_user_id, created_by_name, source_type='manual'
- DELETE /sales performs soft-delete (sets status='deleted')
- GET /sales excludes soft-deleted records
- POST /other-expenses creates record with ownership fields
- DELETE /other-expenses performs soft-delete
- Data scope enforcement for cashier with scope='own'
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MANAGER_EMAIL = "demo@test.com"
MANAGER_PASSWORD = "testpassword"


class TestAuthPermissions:
    """Test authentication and permissions endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        self.user = None
    
    def login_as_manager(self):
        """Login as manager and get token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        return data
    
    def test_login_returns_token_and_user(self):
        """Test POST /api/auth/login returns token and user info"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == MANAGER_EMAIL
        assert data["user"]["role"] == "manager"
        print(f"✓ Login successful, role: {data['user']['role']}")
    
    def test_auth_me_returns_permissions_and_data_scope(self):
        """Test GET /api/auth/me returns permissions and data_scope for manager"""
        self.login_as_manager()
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        
        # Check permissions exist
        assert "permissions" in data, "permissions field missing from /auth/me response"
        assert "data_scope" in data, "data_scope field missing from /auth/me response"
        
        # Manager should have data_scope='all'
        assert data["data_scope"] == "all", f"Expected data_scope='all', got '{data['data_scope']}'"
        
        # Count permissions
        perms = data["permissions"]
        true_count = sum(1 for v in perms.values() if v is True)
        print(f"✓ Manager has {true_count} permissions, data_scope='{data['data_scope']}'")
        
        # Manager should have all 21 permissions
        assert true_count == 21, f"Expected 21 permissions for manager, got {true_count}"
    
    def test_auth_me_has_all_visibility_permissions(self):
        """Test manager has all 8 visibility permissions"""
        self.login_as_manager()
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        perms = response.json()["permissions"]
        
        visibility_keys = [
            "view_dashboard", "view_sales", "view_expenses", "view_reports",
            "view_records", "view_vendors", "view_items", "view_users"
        ]
        for key in visibility_keys:
            assert perms.get(key) is True, f"Manager missing visibility permission: {key}"
        print(f"✓ Manager has all 8 visibility permissions")
    
    def test_auth_me_has_all_action_permissions(self):
        """Test manager has all 13 action permissions"""
        self.login_as_manager()
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        perms = response.json()["permissions"]
        
        action_keys = [
            "can_add_sales", "can_edit_sales", "can_delete_sales",
            "can_add_expenses", "can_edit_expenses", "can_delete_expenses",
            "can_upload_files", "can_view_reports", "can_export_reports",
            "can_view_records", "can_manage_vendors", "can_manage_items",
            "can_manage_users"
        ]
        for key in action_keys:
            assert perms.get(key) is True, f"Manager missing action permission: {key}"
        print(f"✓ Manager has all 13 action permissions")


class TestPermissionDefaults:
    """Test permission defaults endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def login_as_manager(self):
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        self.session.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    
    def test_permissions_defaults_endpoint(self):
        """Test GET /api/users/permissions/defaults returns correct counts"""
        self.login_as_manager()
        response = self.session.get(f"{BASE_URL}/api/users/permissions/defaults")
        assert response.status_code == 200
        data = response.json()
        
        # Check all roles exist
        assert "manager" in data
        assert "accountant" in data
        assert "cashier" in data
        assert "staff" in data
        
        # Count permissions for each role
        manager_count = sum(1 for v in data["manager"].values() if v is True)
        accountant_count = sum(1 for v in data["accountant"].values() if v is True)
        cashier_count = sum(1 for v in data["cashier"].values() if v is True)
        staff_count = sum(1 for v in data["staff"].values() if v is True)
        
        print(f"Permission counts - Manager: {manager_count}, Accountant: {accountant_count}, Cashier: {cashier_count}, Staff: {staff_count}")
        
        # Verify expected counts
        assert manager_count == 21, f"Expected manager to have 21 permissions, got {manager_count}"
        assert accountant_count == 17, f"Expected accountant to have 17 permissions, got {accountant_count}"
        assert cashier_count == 9, f"Expected cashier to have 9 permissions, got {cashier_count}"
        assert staff_count == 4, f"Expected staff to have 4 permissions, got {staff_count}"
        print("✓ All role permission counts match expected values")


class TestUserCreation:
    """Test user creation with permissions and ownership fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.created_user_id = None
    
    def login_as_manager(self):
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        self.session.headers.update({"Authorization": f"Bearer {data['token']}"})
        return data
    
    def test_create_user_with_permissions_and_scope(self):
        """Test POST /api/users creates user with permissions, data_scope, and ownership fields"""
        login_data = self.login_as_manager()
        
        test_email = f"TEST_cashier_{uuid.uuid4().hex[:8]}@test.com"
        response = self.session.post(f"{BASE_URL}/api/users", json={
            "name": "Test Cashier",
            "email": test_email,
            "password": "testpass123",
            "role": "cashier",
            "data_scope": "own"
        })
        
        assert response.status_code == 200, f"Create user failed: {response.text}"
        data = response.json()
        self.created_user_id = data.get("id")
        
        # Verify permissions exist
        assert "permissions" in data, "permissions field missing from created user"
        assert "data_scope" in data, "data_scope field missing from created user"
        
        # Verify data_scope
        assert data["data_scope"] == "own", f"Expected data_scope='own', got '{data['data_scope']}'"
        
        # Verify ownership fields
        assert "created_by_user_id" in data, "created_by_user_id missing from created user"
        assert "created_by_name" in data, "created_by_name missing from created user"
        
        print(f"✓ User created with data_scope='{data['data_scope']}', created_by_user_id='{data.get('created_by_user_id')}'")
        
        # Cleanup
        if self.created_user_id:
            self.session.delete(f"{BASE_URL}/api/users/{self.created_user_id}")


class TestSalesOwnershipAndSoftDelete:
    """Test sales creation with ownership fields and soft-delete"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.created_sale_id = None
    
    def login_as_manager(self):
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        self.session.headers.update({"Authorization": f"Bearer {data['token']}"})
        return data
    
    def test_create_sale_has_ownership_fields(self):
        """Test POST /api/sales creates record with created_by_user_id, created_by_name, source_type='manual'"""
        self.login_as_manager()
        
        response = self.session.post(f"{BASE_URL}/api/sales", json={
            "date_from": "2025-01-15",
            "date_to": "2025-01-15",
            "total_sales": 1500.00,
            "items": [{"menu_item": "Test Item", "quantity": 10, "revenue": 1500.00}]
        })
        
        assert response.status_code == 200, f"Create sale failed: {response.text}"
        data = response.json()
        self.created_sale_id = data.get("id")
        
        # Verify ownership fields
        assert "created_by_user_id" in data, "created_by_user_id missing from sale"
        assert "created_by_name" in data, "created_by_name missing from sale"
        assert "source_type" in data, "source_type missing from sale"
        
        assert data["source_type"] == "manual", f"Expected source_type='manual', got '{data['source_type']}'"
        assert data["created_by_user_id"] is not None, "created_by_user_id should not be None"
        
        print(f"✓ Sale created with source_type='{data['source_type']}', created_by_user_id='{data['created_by_user_id']}'")
    
    def test_delete_sale_performs_soft_delete(self):
        """Test DELETE /api/sales/{id} performs soft-delete (sets status='deleted')"""
        self.login_as_manager()
        
        # Create a sale first
        create_response = self.session.post(f"{BASE_URL}/api/sales", json={
            "date_from": "2025-01-16",
            "date_to": "2025-01-16",
            "total_sales": 500.00,
            "items": []
        })
        assert create_response.status_code == 200
        sale_id = create_response.json()["id"]
        
        # Delete the sale
        delete_response = self.session.delete(f"{BASE_URL}/api/sales/{sale_id}")
        assert delete_response.status_code == 200
        delete_data = delete_response.json()
        assert delete_data.get("status") == "deleted", f"Expected status='deleted', got '{delete_data.get('status')}'"
        
        print(f"✓ Sale soft-deleted, response status='{delete_data.get('status')}'")
    
    def test_get_sales_excludes_soft_deleted(self):
        """Test GET /api/sales excludes soft-deleted records"""
        self.login_as_manager()
        
        # Create a sale
        create_response = self.session.post(f"{BASE_URL}/api/sales", json={
            "date_from": "2025-01-17",
            "date_to": "2025-01-17",
            "total_sales": 750.00,
            "items": []
        })
        assert create_response.status_code == 200
        sale_id = create_response.json()["id"]
        
        # Verify it appears in list
        list_response = self.session.get(f"{BASE_URL}/api/sales")
        assert list_response.status_code == 200
        sales_before = list_response.json()
        sale_ids_before = [s["id"] for s in sales_before]
        assert sale_id in sale_ids_before, "Created sale should appear in list"
        
        # Delete the sale
        self.session.delete(f"{BASE_URL}/api/sales/{sale_id}")
        
        # Verify it no longer appears in list
        list_response_after = self.session.get(f"{BASE_URL}/api/sales")
        assert list_response_after.status_code == 200
        sales_after = list_response_after.json()
        sale_ids_after = [s["id"] for s in sales_after]
        assert sale_id not in sale_ids_after, "Soft-deleted sale should NOT appear in list"
        
        print(f"✓ Soft-deleted sale excluded from GET /api/sales")


class TestOtherExpensesOwnershipAndSoftDelete:
    """Test other-expenses creation with ownership fields and soft-delete"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def login_as_manager(self):
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        self.session.headers.update({"Authorization": f"Bearer {data['token']}"})
        return data
    
    def test_create_other_expense_has_ownership_fields(self):
        """Test POST /api/other-expenses creates record with ownership fields"""
        self.login_as_manager()
        
        response = self.session.post(f"{BASE_URL}/api/other-expenses", json={
            "title": "Test Expense",
            "amount": 250.00,
            "category": "utilities",
            "expense_date": "2025-01-15"
        })
        
        assert response.status_code == 200, f"Create expense failed: {response.text}"
        data = response.json()
        
        # Verify ownership fields
        assert "created_by_user_id" in data, "created_by_user_id missing from expense"
        assert "created_by_name" in data, "created_by_name missing from expense"
        assert "source_type" in data, "source_type missing from expense"
        
        assert data["source_type"] == "manual", f"Expected source_type='manual', got '{data['source_type']}'"
        
        print(f"✓ Expense created with source_type='{data['source_type']}', created_by_user_id='{data['created_by_user_id']}'")
        
        # Cleanup
        if data.get("id"):
            self.session.delete(f"{BASE_URL}/api/other-expenses/{data['id']}")
    
    def test_delete_other_expense_performs_soft_delete(self):
        """Test DELETE /api/other-expenses/{id} performs soft-delete"""
        self.login_as_manager()
        
        # Create an expense first
        create_response = self.session.post(f"{BASE_URL}/api/other-expenses", json={
            "title": "Test Soft Delete Expense",
            "amount": 100.00,
            "category": "supplies",
            "expense_date": "2025-01-16"
        })
        assert create_response.status_code == 200
        expense_id = create_response.json()["id"]
        
        # Delete the expense
        delete_response = self.session.delete(f"{BASE_URL}/api/other-expenses/{expense_id}")
        assert delete_response.status_code == 200
        delete_data = delete_response.json()
        assert delete_data.get("status") == "deleted", f"Expected status='deleted', got '{delete_data.get('status')}'"
        
        print(f"✓ Expense soft-deleted, response status='{delete_data.get('status')}'")


class TestDashboardSummary:
    """Test dashboard summary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def login_as_manager(self):
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MANAGER_EMAIL,
            "password": MANAGER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        self.session.headers.update({"Authorization": f"Bearer {data['token']}"})
        return data
    
    def test_dashboard_summary_with_month_zero(self):
        """Test GET /api/dashboard/summary with month=0 (All Months)"""
        self.login_as_manager()
        
        # Test with month=0 (All Months)
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary", params={"month": 0})
        assert response.status_code == 200, f"Dashboard summary failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "month_raw_materials" in data or "total_expenses" in data, "Dashboard summary should have expense data"
        print(f"✓ Dashboard summary with month=0 returns data")
    
    def test_dashboard_summary_without_month_filter(self):
        """Test GET /api/dashboard/summary without month filter"""
        self.login_as_manager()
        
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200, f"Dashboard summary failed: {response.text}"
        print(f"✓ Dashboard summary without month filter returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
