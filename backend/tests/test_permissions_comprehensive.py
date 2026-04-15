"""
Comprehensive Permissions + Accountability System Tests
========================================================
Tests all 4 roles (Manager, Accountant, Cashier, Staff) for:
- Page visibility/access per role
- Action permissions (create/edit/delete/upload)
- Data scope enforcement (all vs own)
- Ownership rules (edit/delete only own records for restricted roles)
- Soft-delete behavior
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREDENTIALS = {
    'manager': {'email': 'demo@test.com', 'password': 'testpassword'},
    'accountant': {'email': 'accountant@test.com', 'password': 'testpass123'},
    'cashier': {'email': 'cashier@test.com', 'password': 'testpass123'},
    'staff': {'email': 'staff@test.com', 'password': 'testpass123'},
}

# Expected permissions per role
EXPECTED_PERMISSIONS = {
    'manager': {
        'visibility': ['view_dashboard', 'view_sales', 'view_expenses', 'view_records', 'view_vendors', 'view_items', 'view_users', 'view_reports'],
        'actions': ['can_add_sales', 'can_edit_sales', 'can_delete_sales', 'can_add_expenses', 'can_edit_expenses', 'can_delete_expenses', 'can_upload_files', 'can_manage_users'],
        'data_scope': 'all',
    },
    'accountant': {
        'visibility': ['view_dashboard', 'view_sales', 'view_expenses', 'view_records', 'view_vendors', 'view_items', 'view_reports'],
        'no_visibility': ['view_users'],
        'actions': ['can_add_sales', 'can_edit_sales', 'can_add_expenses', 'can_edit_expenses', 'can_upload_files'],
        'no_actions': ['can_delete_sales', 'can_delete_expenses', 'can_manage_users'],
        'data_scope': 'all',
    },
    'cashier': {
        'visibility': ['view_dashboard', 'view_sales', 'view_records', 'view_vendors', 'view_items'],
        'no_visibility': ['view_expenses', 'view_users', 'view_reports'],
        'actions': ['can_add_sales', 'can_edit_sales', 'can_upload_files'],
        'no_actions': ['can_delete_sales', 'can_add_expenses', 'can_edit_expenses', 'can_delete_expenses', 'can_manage_users'],
        'data_scope': 'own',
    },
    'staff': {
        'visibility': ['view_dashboard', 'view_records'],
        'no_visibility': ['view_sales', 'view_expenses', 'view_vendors', 'view_items', 'view_users', 'view_reports'],
        'actions': ['can_upload_files'],
        'no_actions': ['can_add_sales', 'can_edit_sales', 'can_delete_sales', 'can_add_expenses', 'can_edit_expenses', 'can_delete_expenses', 'can_manage_users'],
        'data_scope': 'own',
    },
}


class TestAuthAndPermissions:
    """Test authentication and permission retrieval for all roles"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    def test_manager_login_and_permissions(self, tokens):
        """Manager should have all 21 permissions and data_scope=all"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data['role'] == 'manager'
        assert data['data_scope'] == 'all'
        perms = data['permissions']
        for perm in EXPECTED_PERMISSIONS['manager']['visibility']:
            assert perms.get(perm) == True, f"Manager missing visibility: {perm}"
        for perm in EXPECTED_PERMISSIONS['manager']['actions']:
            assert perms.get(perm) == True, f"Manager missing action: {perm}"
        print(f"PASS: Manager has all expected permissions, data_scope=all")
    
    def test_accountant_login_and_permissions(self, tokens):
        """Accountant should have 17 permissions, no view_users, no delete, data_scope=all"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {tokens['accountant']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data['role'] == 'accountant'
        assert data['data_scope'] == 'all'
        perms = data['permissions']
        for perm in EXPECTED_PERMISSIONS['accountant']['visibility']:
            assert perms.get(perm) == True, f"Accountant missing visibility: {perm}"
        for perm in EXPECTED_PERMISSIONS['accountant'].get('no_visibility', []):
            assert perms.get(perm) == False, f"Accountant should NOT have: {perm}"
        for perm in EXPECTED_PERMISSIONS['accountant']['actions']:
            assert perms.get(perm) == True, f"Accountant missing action: {perm}"
        for perm in EXPECTED_PERMISSIONS['accountant'].get('no_actions', []):
            assert perms.get(perm) == False, f"Accountant should NOT have: {perm}"
        print(f"PASS: Accountant has correct permissions, data_scope=all")
    
    def test_cashier_login_and_permissions(self, tokens):
        """Cashier should have 9 permissions, no expenses/users, data_scope=own"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data['role'] == 'cashier'
        assert data['data_scope'] == 'own'
        perms = data['permissions']
        for perm in EXPECTED_PERMISSIONS['cashier']['visibility']:
            assert perms.get(perm) == True, f"Cashier missing visibility: {perm}"
        for perm in EXPECTED_PERMISSIONS['cashier'].get('no_visibility', []):
            assert perms.get(perm) == False, f"Cashier should NOT have: {perm}"
        for perm in EXPECTED_PERMISSIONS['cashier']['actions']:
            assert perms.get(perm) == True, f"Cashier missing action: {perm}"
        for perm in EXPECTED_PERMISSIONS['cashier'].get('no_actions', []):
            assert perms.get(perm) == False, f"Cashier should NOT have: {perm}"
        print(f"PASS: Cashier has correct permissions, data_scope=own")
    
    def test_staff_login_and_permissions(self, tokens):
        """Staff should have 4 permissions, only dashboard+records+upload, data_scope=own"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {tokens['staff']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data['role'] == 'staff'
        assert data['data_scope'] == 'own'
        perms = data['permissions']
        for perm in EXPECTED_PERMISSIONS['staff']['visibility']:
            assert perms.get(perm) == True, f"Staff missing visibility: {perm}"
        for perm in EXPECTED_PERMISSIONS['staff'].get('no_visibility', []):
            assert perms.get(perm) == False, f"Staff should NOT have: {perm}"
        for perm in EXPECTED_PERMISSIONS['staff']['actions']:
            assert perms.get(perm) == True, f"Staff missing action: {perm}"
        for perm in EXPECTED_PERMISSIONS['staff'].get('no_actions', []):
            assert perms.get(perm) == False, f"Staff should NOT have: {perm}"
        print(f"PASS: Staff has correct permissions, data_scope=own")


class TestSalesPermissions:
    """Test sales CRUD permissions and data scope enforcement"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    @pytest.fixture(scope='class')
    def user_ids(self, tokens):
        """Get user IDs for all roles"""
        ids = {}
        for role, token in tokens.items():
            resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {token}"})
            ids[role] = resp.json()['id']
        return ids
    
    def test_manager_can_create_sale(self, tokens):
        """Manager should be able to create a sale"""
        payload = {
            'report_date': '2026-02-10',
            'date_from': '2026-02-10',
            'date_to': '2026-02-10',
            'total_sales': 500,
            'items': [{'menu_item': 'Manager Burger', 'quantity': 10, 'unit_price': 50, 'revenue': 500}]
        }
        resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert resp.status_code == 200, f"Manager create sale failed: {resp.text}"
        data = resp.json()
        assert data['total_sales'] == 500
        assert data['created_by_name'] is not None
        print(f"PASS: Manager created sale with id={data['id']}")
        return data['id']
    
    def test_cashier_can_create_sale(self, tokens):
        """Cashier should be able to create a sale (can_add_sales=True)"""
        payload = {
            'report_date': '2026-02-11',
            'date_from': '2026-02-11',
            'date_to': '2026-02-11',
            'total_sales': 200,
            'items': [{'menu_item': 'Cashier Pizza', 'quantity': 5, 'unit_price': 40, 'revenue': 200}]
        }
        resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert resp.status_code == 200, f"Cashier create sale failed: {resp.text}"
        data = resp.json()
        assert data['total_sales'] == 200
        print(f"PASS: Cashier created sale with id={data['id']}")
        return data['id']
    
    def test_staff_cannot_create_sale(self, tokens):
        """Staff should NOT be able to create a sale (can_add_sales=False)"""
        payload = {
            'report_date': '2026-02-12',
            'date_from': '2026-02-12',
            'date_to': '2026-02-12',
            'total_sales': 100,
            'items': [{'menu_item': 'Staff Salad', 'quantity': 2, 'unit_price': 50, 'revenue': 100}]
        }
        resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['staff']}"})
        assert resp.status_code == 403, f"Staff should get 403, got {resp.status_code}: {resp.text}"
        print(f"PASS: Staff correctly denied sale creation (403)")
    
    def test_accountant_cannot_delete_sale(self, tokens):
        """Accountant should NOT be able to delete a sale (can_delete_sales=False)"""
        # First create a sale as manager
        payload = {
            'report_date': '2026-02-13',
            'date_from': '2026-02-13',
            'date_to': '2026-02-13',
            'total_sales': 300,
            'items': [{'menu_item': 'Test Item', 'quantity': 3, 'unit_price': 100, 'revenue': 300}]
        }
        create_resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert create_resp.status_code == 200
        sale_id = create_resp.json()['id']
        
        # Try to delete as accountant
        del_resp = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers={'Authorization': f"Bearer {tokens['accountant']}"})
        assert del_resp.status_code == 403, f"Accountant should get 403 on delete, got {del_resp.status_code}: {del_resp.text}"
        print(f"PASS: Accountant correctly denied sale deletion (403)")
        
        # Cleanup: delete as manager
        requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})
    
    def test_manager_soft_delete_sale(self, tokens):
        """Manager delete should soft-delete (status=deleted, record still in DB)"""
        # Create a sale
        payload = {
            'report_date': '2026-02-14',
            'date_from': '2026-02-14',
            'date_to': '2026-02-14',
            'total_sales': 400,
            'items': [{'menu_item': 'Soft Delete Test', 'quantity': 4, 'unit_price': 100, 'revenue': 400}]
        }
        create_resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert create_resp.status_code == 200
        sale_id = create_resp.json()['id']
        
        # Delete as manager
        del_resp = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert del_resp.status_code == 200
        assert del_resp.json().get('status') == 'deleted'
        
        # Verify it no longer appears in GET /sales
        list_resp = requests.get(f"{BASE_URL}/api/sales", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert list_resp.status_code == 200
        sale_ids = [s['id'] for s in list_resp.json()]
        assert sale_id not in sale_ids, "Soft-deleted sale should not appear in list"
        print(f"PASS: Manager soft-delete works correctly")


class TestDataScopeEnforcement:
    """Test that data_scope=own users only see their own records"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    @pytest.fixture(scope='class')
    def user_ids(self, tokens):
        """Get user IDs for all roles"""
        ids = {}
        for role, token in tokens.items():
            resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {token}"})
            ids[role] = resp.json()['id']
        return ids
    
    def test_scope_enforcement_sales(self, tokens, user_ids):
        """
        Test data scope enforcement:
        - Manager creates a sale
        - Cashier creates a sale
        - Cashier GET /sales should ONLY see cashier's sale
        - Manager GET /sales should see BOTH sales
        """
        # Create sale as manager
        manager_payload = {
            'report_date': '2026-02-20',
            'date_from': '2026-02-20',
            'date_to': '2026-02-20',
            'total_sales': 999,
            'items': [{'menu_item': 'Manager Scope Test', 'quantity': 1, 'unit_price': 999, 'revenue': 999}]
        }
        mgr_resp = requests.post(f"{BASE_URL}/api/sales", json=manager_payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert mgr_resp.status_code == 200
        manager_sale_id = mgr_resp.json()['id']
        
        # Create sale as cashier
        cashier_payload = {
            'report_date': '2026-02-21',
            'date_from': '2026-02-21',
            'date_to': '2026-02-21',
            'total_sales': 111,
            'items': [{'menu_item': 'Cashier Scope Test', 'quantity': 1, 'unit_price': 111, 'revenue': 111}]
        }
        cash_resp = requests.post(f"{BASE_URL}/api/sales", json=cashier_payload, headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert cash_resp.status_code == 200
        cashier_sale_id = cash_resp.json()['id']
        
        # Cashier GET /sales - should only see their own
        cashier_list = requests.get(f"{BASE_URL}/api/sales", headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert cashier_list.status_code == 200
        cashier_sale_ids = [s['id'] for s in cashier_list.json()]
        
        # Cashier should see their sale
        assert cashier_sale_id in cashier_sale_ids, "Cashier should see their own sale"
        # Cashier should NOT see manager's sale
        assert manager_sale_id not in cashier_sale_ids, "Cashier should NOT see manager's sale (scope=own)"
        
        # Manager GET /sales - should see both
        manager_list = requests.get(f"{BASE_URL}/api/sales", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert manager_list.status_code == 200
        manager_sale_ids = [s['id'] for s in manager_list.json()]
        
        assert manager_sale_id in manager_sale_ids, "Manager should see their own sale"
        assert cashier_sale_id in manager_sale_ids, "Manager should see cashier's sale (scope=all)"
        
        print(f"PASS: Data scope enforcement working correctly")
        print(f"  - Cashier sees {len(cashier_sale_ids)} sales (only own)")
        print(f"  - Manager sees {len(manager_sale_ids)} sales (all)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/sales/{manager_sale_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})
        requests.delete(f"{BASE_URL}/api/sales/{cashier_sale_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})
    
    def test_cashier_cannot_edit_others_sale(self, tokens, user_ids):
        """Cashier with scope=own should NOT be able to edit another user's sale"""
        # Create sale as manager
        manager_payload = {
            'report_date': '2026-02-22',
            'date_from': '2026-02-22',
            'date_to': '2026-02-22',
            'total_sales': 888,
            'items': [{'menu_item': 'Manager Edit Test', 'quantity': 1, 'unit_price': 888, 'revenue': 888}]
        }
        mgr_resp = requests.post(f"{BASE_URL}/api/sales", json=manager_payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert mgr_resp.status_code == 200
        manager_sale_id = mgr_resp.json()['id']
        
        # Try to edit as cashier
        edit_payload = {'total_sales': 777}
        edit_resp = requests.put(f"{BASE_URL}/api/sales/{manager_sale_id}", json=edit_payload, headers={'Authorization': f"Bearer {tokens['cashier']}"})
        
        # Should get 403 or 404 (can't see it due to scope)
        assert edit_resp.status_code in [403, 404], f"Cashier should get 403/404 editing other's sale, got {edit_resp.status_code}"
        print(f"PASS: Cashier correctly denied editing manager's sale ({edit_resp.status_code})")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/sales/{manager_sale_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})


class TestUserManagementAccess:
    """Test that only managers can access user management"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    def test_manager_can_list_users(self, tokens):
        """Manager should be able to list users"""
        resp = requests.get(f"{BASE_URL}/api/users", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert resp.status_code == 200, f"Manager list users failed: {resp.text}"
        users = resp.json()
        assert len(users) >= 4, "Should have at least 4 test users"
        print(f"PASS: Manager can list {len(users)} users")
    
    def test_accountant_cannot_list_users(self, tokens):
        """Accountant should NOT be able to list users"""
        resp = requests.get(f"{BASE_URL}/api/users", headers={'Authorization': f"Bearer {tokens['accountant']}"})
        assert resp.status_code == 403, f"Accountant should get 403, got {resp.status_code}"
        print(f"PASS: Accountant correctly denied user list (403)")
    
    def test_cashier_cannot_list_users(self, tokens):
        """Cashier should NOT be able to list users"""
        resp = requests.get(f"{BASE_URL}/api/users", headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert resp.status_code == 403, f"Cashier should get 403, got {resp.status_code}"
        print(f"PASS: Cashier correctly denied user list (403)")
    
    def test_staff_cannot_list_users(self, tokens):
        """Staff should NOT be able to list users"""
        resp = requests.get(f"{BASE_URL}/api/users", headers={'Authorization': f"Bearer {tokens['staff']}"})
        assert resp.status_code == 403, f"Staff should get 403, got {resp.status_code}"
        print(f"PASS: Staff correctly denied user list (403)")


class TestExpensesPermissions:
    """Test expenses permissions for different roles"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    def test_manager_can_access_expenses(self, tokens):
        """Manager should be able to access expenses"""
        resp = requests.get(f"{BASE_URL}/api/other-expenses", headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert resp.status_code == 200, f"Manager expenses access failed: {resp.text}"
        print(f"PASS: Manager can access expenses")
    
    def test_accountant_can_access_expenses(self, tokens):
        """Accountant should be able to access expenses"""
        resp = requests.get(f"{BASE_URL}/api/other-expenses", headers={'Authorization': f"Bearer {tokens['accountant']}"})
        assert resp.status_code == 200, f"Accountant expenses access failed: {resp.text}"
        print(f"PASS: Accountant can access expenses")
    
    def test_cashier_cannot_access_expenses(self, tokens):
        """Cashier should NOT be able to access expenses (view_expenses=False)"""
        resp = requests.get(f"{BASE_URL}/api/other-expenses", headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert resp.status_code == 403, f"Cashier should get 403, got {resp.status_code}"
        print(f"PASS: Cashier correctly denied expenses access (403)")
    
    def test_staff_cannot_access_expenses(self, tokens):
        """Staff should NOT be able to access expenses (view_expenses=False)"""
        resp = requests.get(f"{BASE_URL}/api/other-expenses", headers={'Authorization': f"Bearer {tokens['staff']}"})
        assert resp.status_code == 403, f"Staff should get 403, got {resp.status_code}"
        print(f"PASS: Staff correctly denied expenses access (403)")
    
    def test_accountant_cannot_delete_expense(self, tokens):
        """Accountant should NOT be able to delete expenses (can_delete_expenses=False)"""
        # First create an expense as manager
        payload = {
            'title': 'Test Expense',
            'amount': 100,
            'category': 'Utilities',
            'expense_date': '2026-02-15'
        }
        create_resp = requests.post(f"{BASE_URL}/api/other-expenses", json=payload, headers={'Authorization': f"Bearer {tokens['manager']}"})
        assert create_resp.status_code == 200
        expense_id = create_resp.json()['id']
        
        # Try to delete as accountant
        del_resp = requests.delete(f"{BASE_URL}/api/other-expenses/{expense_id}", headers={'Authorization': f"Bearer {tokens['accountant']}"})
        assert del_resp.status_code == 403, f"Accountant should get 403 on delete, got {del_resp.status_code}"
        print(f"PASS: Accountant correctly denied expense deletion (403)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/other-expenses/{expense_id}", headers={'Authorization': f"Bearer {tokens['manager']}"})


class TestCreatedByTracking:
    """Test that created_by_user_id and created_by_name are properly set"""
    
    @pytest.fixture(scope='class')
    def tokens(self):
        """Get auth tokens for all roles"""
        tokens = {}
        for role, creds in CREDENTIALS.items():
            resp = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert resp.status_code == 200, f"Login failed for {role}: {resp.text}"
            tokens[role] = resp.json()['token']
        return tokens
    
    @pytest.fixture(scope='class')
    def user_info(self, tokens):
        """Get user info for all roles"""
        info = {}
        for role, token in tokens.items():
            resp = requests.get(f"{BASE_URL}/api/auth/me", headers={'Authorization': f"Bearer {token}"})
            info[role] = resp.json()
        return info
    
    def test_sale_has_created_by(self, tokens, user_info):
        """Sales should have created_by_user_id and created_by_name"""
        payload = {
            'report_date': '2026-02-25',
            'date_from': '2026-02-25',
            'date_to': '2026-02-25',
            'total_sales': 123,
            'items': [{'menu_item': 'Created By Test', 'quantity': 1, 'unit_price': 123, 'revenue': 123}]
        }
        resp = requests.post(f"{BASE_URL}/api/sales", json=payload, headers={'Authorization': f"Bearer {tokens['cashier']}"})
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get('created_by_user_id') == user_info['cashier']['id'], "created_by_user_id should match cashier's ID"
        assert data.get('created_by_name') == user_info['cashier']['name'], "created_by_name should match cashier's name"
        print(f"PASS: Sale has correct created_by_user_id={data['created_by_user_id']}, created_by_name={data['created_by_name']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/sales/{data['id']}", headers={'Authorization': f"Bearer {tokens['manager']}"})


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
