"""
Test suite for Approval Rules and Approvals system.
Tests user approval_rule settings, auto-approval logic, approvals endpoint functionality,
and dashboard/reports filtering by approval_status.
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestApprovalRulesSetup:
    """Setup and test user creation with approval rules"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get manager auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        """Create authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_create_user_with_pending_all_rule(self, api_client):
        """Test creating user with pending_all approval rule"""
        user_data = {
            "name": "TEST_PendingAllUser",
            "email": f"TEST_pending_all_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all",
            "auto_approve_limit": None
        }
        response = api_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200, f"Failed to create user: {response.text}"
        data = response.json()
        assert data["approval_rule"] == "pending_all"
        assert data["auto_approve_limit"] is None
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/users/{data['id']}")
        print(f"Created and cleaned up user with pending_all rule: {data['id']}")

    def test_create_user_with_auto_approve_all_rule(self, api_client):
        """Test creating user with auto_approve_all rule"""
        user_data = {
            "name": "TEST_AutoApproveAllUser",
            "email": f"TEST_auto_all_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "accountant",
            "approval_rule": "auto_approve_all"
        }
        response = api_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200, f"Failed to create user: {response.text}"
        data = response.json()
        assert data["approval_rule"] == "auto_approve_all"
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/users/{data['id']}")
        print(f"Created and cleaned up user with auto_approve_all rule: {data['id']}")

    def test_create_user_with_auto_approve_below_limit(self, api_client):
        """Test creating user with auto_approve_below and limit"""
        user_data = {
            "name": "TEST_AutoApproveBelowUser",
            "email": f"TEST_auto_below_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "staff",
            "approval_rule": "auto_approve_below",
            "auto_approve_limit": 500.00
        }
        response = api_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200, f"Failed to create user: {response.text}"
        data = response.json()
        assert data["approval_rule"] == "auto_approve_below"
        assert data["auto_approve_limit"] == 500.00
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/users/{data['id']}")
        print(f"Created and cleaned up user with auto_approve_below rule: {data['id']}")

    def test_update_user_approval_rule(self, api_client):
        """Test updating user's approval rule"""
        # Create user first
        user_data = {
            "name": "TEST_UpdateRuleUser",
            "email": f"TEST_update_rule_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all"
        }
        create_resp = api_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Update approval rule
        update_resp = api_client.put(f"{BASE_URL}/api/users/{user_id}", json={
            "approval_rule": "auto_approve_below",
            "auto_approve_limit": 200.00
        })
        assert update_resp.status_code == 200, f"Failed to update user: {update_resp.text}"
        data = update_resp.json()
        assert data["approval_rule"] == "auto_approve_below"
        assert data["auto_approve_limit"] == 200.00
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/users/{user_id}")
        print(f"Updated and cleaned up user approval rule: {user_id}")


class TestApprovalStatusOnRecordCreation:
    """Test approval_status is set correctly when records are created"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        """Get manager auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        """Create manager authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_manager_creates_approved_records(self, manager_client):
        """Manager creates records that are automatically approved"""
        # Create a sale as manager
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 1500.00,
            "items": []
        }
        response = manager_client.post(f"{BASE_URL}/api/sales", json=sale_data)
        assert response.status_code == 200, f"Failed to create sale: {response.text}"
        data = response.json()
        assert data.get("approval_status") == "approved", f"Manager sale should be approved but got: {data.get('approval_status')}"
        print(f"Manager created sale with approval_status: {data.get('approval_status')}")
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/sales/{data['id']}")

    def test_manager_creates_approved_purchase(self, manager_client):
        """Manager creates purchase that is automatically approved"""
        purchase_data = {
            "supplier_name": "TEST_Supplier",
            "invoice_number": f"TEST_INV_{uuid.uuid4().hex[:8]}",
            "invoice_date": "2025-01-15",
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "kg", "unit_price": 10.00, "total": 10.00}],
            "subtotal": 10.00,
            "tax": 0,
            "total": 10.00
        }
        response = manager_client.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert response.status_code == 200, f"Failed to create purchase: {response.text}"
        data = response.json()
        assert data.get("approval_status") == "approved"
        print(f"Manager created purchase with approval_status: {data.get('approval_status')}")
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/purchases/{data['id']}")


class TestApprovalStatusForNonManager:
    """Test approval_status based on non-manager user's approval_rule"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        """Get manager auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        """Create manager authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session
    
    @pytest.fixture(scope="class")
    def pending_all_user(self, manager_client):
        """Create user with pending_all rule"""
        user_data = {
            "name": "TEST_PendingCashier",
            "email": f"TEST_pending_cashier_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all",
            "permissions": {"can_add_sales": True}
        }
        response = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200, f"Failed to create user: {response.text}"
        user = response.json()
        yield user
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")

    @pytest.fixture(scope="class")
    def auto_approve_all_user(self, manager_client):
        """Create user with auto_approve_all rule"""
        user_data = {
            "name": "TEST_AutoAllAccountant",
            "email": f"TEST_auto_all_acc_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "accountant",
            "approval_rule": "auto_approve_all",
            "permissions": {"can_add_sales": True, "can_add_expenses": True}
        }
        response = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200
        user = response.json()
        yield user
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")

    @pytest.fixture(scope="class")
    def auto_approve_below_user(self, manager_client):
        """Create user with auto_approve_below rule (limit $500)"""
        user_data = {
            "name": "TEST_AutoBelowStaff",
            "email": f"TEST_auto_below_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "staff",
            "approval_rule": "auto_approve_below",
            "auto_approve_limit": 500.00,
            "permissions": {"can_add_sales": True, "can_add_expenses": True}
        }
        response = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert response.status_code == 200
        user = response.json()
        yield user
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")

    def test_pending_all_user_creates_pending_sale(self, pending_all_user):
        """User with pending_all creates sale -> status=pending"""
        # Login as user
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": pending_all_user["email"],
            "password": "testpassword123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        
        # Create sale
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 200.00,
            "items": []
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=headers)
        assert response.status_code == 200, f"Failed to create sale: {response.text}"
        data = response.json()
        assert data.get("approval_status") == "pending", f"Expected 'pending' but got: {data.get('approval_status')}"
        print(f"Pending_all user created sale with approval_status: {data.get('approval_status')}")
        
        # Cleanup (as manager)
        manager_token = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"}).json().get("token")
        requests.delete(f"{BASE_URL}/api/sales/{data['id']}", headers={"Authorization": f"Bearer {manager_token}"})

    def test_auto_approve_all_user_creates_approved_sale(self, auto_approve_all_user):
        """User with auto_approve_all creates sale -> status=approved"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": auto_approve_all_user["email"],
            "password": "testpassword123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 9999.00,
            "items": []
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("approval_status") == "approved", f"Expected 'approved' but got: {data.get('approval_status')}"
        print(f"Auto_approve_all user created sale with approval_status: {data.get('approval_status')}")
        
        # Cleanup
        manager_token = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"}).json().get("token")
        requests.delete(f"{BASE_URL}/api/sales/{data['id']}", headers={"Authorization": f"Bearer {manager_token}"})

    def test_auto_approve_below_limit_creates_approved(self, auto_approve_below_user):
        """User with auto_approve_below creates sale below limit -> approved"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": auto_approve_below_user["email"],
            "password": "testpassword123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        # Amount below limit ($500)
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 300.00,  # Below $500 limit
            "items": []
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("approval_status") == "approved", f"Expected 'approved' for amount below limit but got: {data.get('approval_status')}"
        print(f"Auto_approve_below user created $300 sale (below $500 limit): approval_status={data.get('approval_status')}")
        
        # Cleanup
        manager_token = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"}).json().get("token")
        requests.delete(f"{BASE_URL}/api/sales/{data['id']}", headers={"Authorization": f"Bearer {manager_token}"})

    def test_auto_approve_below_limit_creates_pending_above(self, auto_approve_below_user):
        """User with auto_approve_below creates sale above limit -> pending"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": auto_approve_below_user["email"],
            "password": "testpassword123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        # Amount above limit ($500)
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 750.00,  # Above $500 limit
            "items": []
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("approval_status") == "pending", f"Expected 'pending' for amount above limit but got: {data.get('approval_status')}"
        print(f"Auto_approve_below user created $750 sale (above $500 limit): approval_status={data.get('approval_status')}")
        
        # Cleanup
        manager_token = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"}).json().get("token")
        requests.delete(f"{BASE_URL}/api/sales/{data['id']}", headers={"Authorization": f"Bearer {manager_token}"})


class TestApprovalsEndpoints:
    """Test GET/PUT /api/approvals endpoints"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        """Get manager auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        """Create manager authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    @pytest.fixture(scope="class")
    def test_user_with_pending_sale(self, manager_client):
        """Create user with pending_all rule and a pending sale"""
        # Create user
        user_data = {
            "name": "TEST_ApprovalTestUser",
            "email": f"TEST_approval_test_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all",
            "permissions": {"can_add_sales": True}
        }
        user_resp = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert user_resp.status_code == 200
        user = user_resp.json()
        
        # Login as user and create sale
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user["email"],
            "password": "testpassword123"
        })
        token = login_resp.json().get("token")
        
        sale_data = {"report_date": "2025-01-15", "total_sales": 500.00, "items": []}
        sale_resp = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        assert sale_resp.status_code == 200
        sale = sale_resp.json()
        
        yield {"user": user, "sale": sale}
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/sales/{sale['id']}")
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")

    def test_get_approvals_returns_pending_records(self, manager_client, test_user_with_pending_sale):
        """GET /api/approvals returns pending records"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"status": "pending"})
        assert response.status_code == 200, f"Failed to get approvals: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        
        # Check our test sale is in the list
        test_sale_id = test_user_with_pending_sale["sale"]["id"]
        found = any(r.get("record_id") == test_sale_id for r in data)
        assert found, f"Test sale {test_sale_id} not found in pending approvals"
        print(f"GET /api/approvals returned {len(data)} pending records, including test sale")

    def test_get_approvals_counts(self, manager_client, test_user_with_pending_sale):
        """GET /api/approvals/counts returns pending counts"""
        response = manager_client.get(f"{BASE_URL}/api/approvals/counts")
        assert response.status_code == 200, f"Failed to get counts: {response.text}"
        data = response.json()
        assert "total" in data
        assert "sale" in data
        assert "purchase" in data
        assert "salary" in data
        assert "other_expense" in data
        assert data["total"] >= 1  # At least our test sale
        print(f"GET /api/approvals/counts: {data}")

    def test_approve_record(self, manager_client, test_user_with_pending_sale):
        """PUT /api/approvals/{type}/{id} with action=approve"""
        sale = test_user_with_pending_sale["sale"]
        response = manager_client.put(f"{BASE_URL}/api/approvals/sale/{sale['id']}", json={
            "action": "approve"
        })
        assert response.status_code == 200, f"Failed to approve: {response.text}"
        data = response.json()
        assert data.get("approval_status") == "approved"
        print(f"Approved sale {sale['id']}: status={data.get('approval_status')}")

    def test_get_approved_records(self, manager_client):
        """GET /api/approvals with status=approved"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"status": "approved"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # All returned records should be approved
        for r in data:
            assert r.get("approval_status") == "approved", f"Expected approved but got: {r.get('approval_status')}"
        print(f"GET /api/approvals status=approved returned {len(data)} records")


class TestApprovalRejection:
    """Test rejection flow"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_reject_record_with_reason(self, manager_client):
        """PUT /api/approvals/{type}/{id} with action=reject and reason"""
        # Create user with pending_all and create a pending sale
        user_data = {
            "name": "TEST_RejectTestUser",
            "email": f"TEST_reject_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all",
            "permissions": {"can_add_sales": True}
        }
        user_resp = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert user_resp.status_code == 200
        user = user_resp.json()
        
        # Login as user and create pending sale
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user["email"],
            "password": "testpassword123"
        })
        token = login_resp.json().get("token")
        
        sale_data = {"report_date": "2025-01-15", "total_sales": 999.00, "items": []}
        sale_resp = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        assert sale_resp.status_code == 200
        sale = sale_resp.json()
        
        # Reject the sale
        reject_resp = manager_client.put(f"{BASE_URL}/api/approvals/sale/{sale['id']}", json={
            "action": "reject",
            "reason": "Amount seems incorrect, please verify"
        })
        assert reject_resp.status_code == 200, f"Failed to reject: {reject_resp.text}"
        data = reject_resp.json()
        assert data.get("approval_status") == "rejected"
        assert data.get("rejection_reason") == "Amount seems incorrect, please verify"
        print(f"Rejected sale {sale['id']}: status={data.get('approval_status')}, reason={data.get('rejection_reason')}")
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/sales/{sale['id']}")
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")

    def test_get_rejected_records(self, manager_client):
        """GET /api/approvals with status=rejected"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"status": "rejected"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for r in data:
            assert r.get("approval_status") == "rejected"
        print(f"GET /api/approvals status=rejected returned {len(data)} records")


class TestApprovalsFilterByType:
    """Test filtering approvals by record_type"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_filter_by_sale_type(self, manager_client):
        """Filter approvals to only show sales"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"record_type": "sale"})
        assert response.status_code == 200
        data = response.json()
        for r in data:
            assert r.get("record_type") == "sale", f"Expected sale but got {r.get('record_type')}"
        print(f"Filter by sale type returned {len(data)} records")

    def test_filter_by_purchase_type(self, manager_client):
        """Filter approvals to only show purchases"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"record_type": "purchase"})
        assert response.status_code == 200
        data = response.json()
        for r in data:
            assert r.get("record_type") == "purchase"
        print(f"Filter by purchase type returned {len(data)} records")

    def test_filter_by_salary_type(self, manager_client):
        """Filter approvals to only show salaries"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"record_type": "salary"})
        assert response.status_code == 200
        data = response.json()
        for r in data:
            assert r.get("record_type") == "salary"
        print(f"Filter by salary type returned {len(data)} records")

    def test_filter_by_other_expense_type(self, manager_client):
        """Filter approvals to only show other_expense"""
        response = manager_client.get(f"{BASE_URL}/api/approvals", params={"record_type": "other_expense"})
        assert response.status_code == 200
        data = response.json()
        for r in data:
            assert r.get("record_type") == "other_expense"
        print(f"Filter by other_expense type returned {len(data)} records")


class TestDashboardOnlyApprovedRecords:
    """Test that dashboard/reports only count approved records"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_dashboard_excludes_pending_from_totals(self, manager_client):
        """Create pending record and verify dashboard doesn't count it"""
        # Create user with pending_all
        user_data = {
            "name": "TEST_DashboardTestUser",
            "email": f"TEST_dashboard_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "cashier",
            "approval_rule": "pending_all",
            "permissions": {"can_add_sales": True}
        }
        user_resp = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        assert user_resp.status_code == 200
        user = user_resp.json()
        
        # Get initial dashboard summary
        initial_summary = manager_client.get(f"{BASE_URL}/api/dashboard/summary").json()
        initial_month_sales = initial_summary.get("month_sales", 0)
        
        # Login as user and create pending sale
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user["email"],
            "password": "testpassword123"
        })
        token = login_resp.json().get("token")
        
        # Use today's date so it counts in month_sales
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        sale_data = {"report_date": today, "total_sales": 5000.00, "items": []}
        sale_resp = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        assert sale_resp.status_code == 200
        sale = sale_resp.json()
        assert sale.get("approval_status") == "pending"
        
        # Get updated dashboard summary
        updated_summary = manager_client.get(f"{BASE_URL}/api/dashboard/summary").json()
        updated_month_sales = updated_summary.get("month_sales", 0)
        
        # Month sales should NOT include the pending $5000 sale
        assert updated_month_sales == initial_month_sales, f"Dashboard should exclude pending sale. Initial: {initial_month_sales}, After: {updated_month_sales}"
        print(f"Dashboard correctly excludes pending sale: month_sales stayed at {initial_month_sales}")
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/sales/{sale['id']}")
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")


class TestApprovalMetadata:
    """Test that approval records include all metadata"""
    
    @pytest.fixture(scope="class")
    def manager_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def manager_client(self, manager_token):
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {manager_token}",
            "Content-Type": "application/json"
        })
        return session

    def test_approval_record_has_metadata(self, manager_client):
        """Verify approval record contains all expected fields"""
        # Create user with pending_all and create pending purchase
        user_data = {
            "name": "TEST_MetadataTestUser",
            "email": f"TEST_metadata_{uuid.uuid4().hex[:8]}@test.com",
            "password": "testpassword123",
            "role": "accountant",
            "approval_rule": "pending_all",
            "permissions": {"can_add_expenses": True}
        }
        user_resp = manager_client.post(f"{BASE_URL}/api/users", json=user_data)
        user = user_resp.json()
        
        # Login as user and create pending purchase
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user["email"],
            "password": "testpassword123"
        })
        token = login_resp.json().get("token")
        
        purchase_data = {
            "supplier_name": "TEST_MetaSupplier",
            "invoice_number": f"TEST_META_{uuid.uuid4().hex[:8]}",
            "invoice_date": "2025-01-15",
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "kg", "unit_price": 100.00, "total": 100.00}],
            "subtotal": 100.00,
            "tax": 10.00,
            "total": 110.00
        }
        purchase_resp = requests.post(f"{BASE_URL}/api/purchases", json=purchase_data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        assert purchase_resp.status_code == 200
        purchase = purchase_resp.json()
        
        # Get approvals and find our purchase
        approvals_resp = manager_client.get(f"{BASE_URL}/api/approvals", params={"status": "pending", "record_type": "purchase"})
        data = approvals_resp.json()
        
        found_purchase = None
        for r in data:
            if r.get("record_id") == purchase["id"]:
                found_purchase = r
                break
        
        assert found_purchase is not None, f"Purchase {purchase['id']} not found in approvals"
        
        # Check metadata fields
        assert "record_type" in found_purchase
        assert "record_id" in found_purchase
        assert "date" in found_purchase
        assert "amount" in found_purchase
        assert "created_by_id" in found_purchase
        assert "created_by_name" in found_purchase
        assert "approval_status" in found_purchase
        assert "supplier_name" in found_purchase
        assert found_purchase["supplier_name"] == "TEST_MetaSupplier"
        assert found_purchase["amount"] == 110.00
        print(f"Approval record has all metadata: {found_purchase}")
        
        # Cleanup
        manager_client.delete(f"{BASE_URL}/api/purchases/{purchase['id']}")
        manager_client.delete(f"{BASE_URL}/api/users/{user['id']}")
