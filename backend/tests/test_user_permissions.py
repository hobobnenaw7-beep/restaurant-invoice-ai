"""
Test User Permissions API endpoints (iteration 20)
Tests the 13 granular permissions system for users:
- GET /api/users/permissions/defaults - returns default permissions for all 4 roles
- POST /api/users with permissions - stores custom permissions
- PUT /api/users/{id} with permissions - updates permissions
- PUT /api/users/{id}/permissions - dedicated endpoint for permissions update
- GET /api/users - returns permissions field for each user
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# All 13 permission keys
ALL_PERMISSIONS = [
    "can_add_sales", "can_edit_sales", "can_delete_sales",
    "can_add_expenses", "can_edit_expenses", "can_delete_expenses",
    "can_upload_files", "can_view_reports", "can_export_reports",
    "can_view_records", "can_manage_vendors", "can_manage_items",
    "can_manage_users",
]

class TestUserPermissions:
    """User Permissions API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth token for manager user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        token = response.json().get("token")
        user = response.json().get("user")
        return {"Authorization": f"Bearer {token}"}, user
    
    # ========== GET /api/users/permissions/defaults tests ==========
    
    def test_defaults_endpoint_returns_all_roles(self, auth_headers):
        """Test that defaults endpoint returns permissions for all 4 roles"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "manager" in data, "Should have manager defaults"
        assert "accountant" in data, "Should have accountant defaults"
        assert "cashier" in data, "Should have cashier defaults"
        assert "staff" in data, "Should have staff defaults"
        print("GET /api/users/permissions/defaults: All 4 roles returned")
    
    def test_defaults_has_all_13_permission_keys(self, auth_headers):
        """Test that each role has all 13 permission keys"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        data = response.json()
        for role in ["manager", "accountant", "cashier", "staff"]:
            for perm in ALL_PERMISSIONS:
                assert perm in data[role], f"{role} missing permission: {perm}"
        print("GET /api/users/permissions/defaults: All 13 keys present for each role")
    
    def test_manager_defaults_all_true(self, auth_headers):
        """Test that manager defaults have all 13 permissions true"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        data = response.json()
        manager_perms = data["manager"]
        true_count = sum(1 for v in manager_perms.values() if v)
        assert true_count == 13, f"Manager should have 13/13 true, got {true_count}"
        print("Manager defaults: 13/13 permissions true")
    
    def test_accountant_defaults_10_true(self, auth_headers):
        """Test that accountant defaults have 10/13 true (no delete sales, delete expenses, manage users)"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        data = response.json()
        acct_perms = data["accountant"]
        true_count = sum(1 for v in acct_perms.values() if v)
        assert true_count == 10, f"Accountant should have 10/13 true, got {true_count}"
        # Verify specific false permissions
        assert acct_perms["can_delete_sales"] == False, "Accountant should not have can_delete_sales"
        assert acct_perms["can_delete_expenses"] == False, "Accountant should not have can_delete_expenses"
        assert acct_perms["can_manage_users"] == False, "Accountant should not have can_manage_users"
        print("Accountant defaults: 10/13 permissions true (correct)")
    
    def test_cashier_defaults_1_true(self, auth_headers):
        """Test that cashier defaults have 1/13 true (can_add_sales only)"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        data = response.json()
        cashier_perms = data["cashier"]
        true_count = sum(1 for v in cashier_perms.values() if v)
        assert true_count == 1, f"Cashier should have 1/13 true, got {true_count}"
        assert cashier_perms["can_add_sales"] == True, "Cashier should have can_add_sales"
        print("Cashier defaults: 1/13 permissions true (can_add_sales)")
    
    def test_staff_defaults_1_true(self, auth_headers):
        """Test that staff defaults have 1/13 true (can_upload_files only)"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users/permissions/defaults", headers=headers)
        data = response.json()
        staff_perms = data["staff"]
        true_count = sum(1 for v in staff_perms.values() if v)
        assert true_count == 1, f"Staff should have 1/13 true, got {true_count}"
        assert staff_perms["can_upload_files"] == True, "Staff should have can_upload_files"
        print("Staff defaults: 1/13 permissions true (can_upload_files)")
    
    # ========== POST /api/users with permissions tests ==========
    
    def test_create_user_with_custom_permissions(self, auth_headers):
        """Test creating a user with custom permissions stores them correctly"""
        headers, _ = auth_headers
        unique_email = f"test_custom_perms_{uuid.uuid4().hex[:8]}@test.com"
        custom_perms = {
            "can_add_sales": True,
            "can_edit_sales": True,
            "can_delete_sales": False,
            "can_add_expenses": True,
            "can_edit_expenses": False,
            "can_delete_expenses": False,
            "can_upload_files": True,
            "can_view_reports": True,
            "can_export_reports": True,
            "can_view_records": False,
            "can_manage_vendors": False,
            "can_manage_items": False,
            "can_manage_users": False,
        }
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Custom Perms User",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff",
            "permissions": custom_perms
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        
        # Verify permissions stored correctly
        assert "permissions" in user, "User should have permissions field"
        stored_perms = user["permissions"]
        for key, value in custom_perms.items():
            assert stored_perms[key] == value, f"Permission {key} should be {value}, got {stored_perms[key]}"
        
        true_count = sum(1 for v in stored_perms.values() if v)
        assert true_count == 6, f"Should have 6 true permissions, got {true_count}"
        print(f"POST /api/users with custom permissions: Success (6/13 true)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    def test_create_user_without_permissions_gets_role_defaults(self, auth_headers):
        """Test that user created without permissions field gets role defaults"""
        headers, _ = auth_headers
        unique_email = f"test_default_perms_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Default Perms User",
            "email": unique_email,
            "password": "testpass123",
            "role": "cashier"
        })
        assert response.status_code == 200
        user = response.json()
        
        # Should have cashier defaults (1/13 - can_add_sales only)
        assert "permissions" in user
        true_count = sum(1 for v in user["permissions"].values() if v)
        assert true_count == 1, f"Cashier should have 1/13 true by default, got {true_count}"
        assert user["permissions"]["can_add_sales"] == True
        print(f"POST /api/users without permissions: Gets role defaults (1/13 for cashier)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    # ========== PUT /api/users/{id} with permissions tests ==========
    
    def test_update_user_permissions_via_user_endpoint(self, auth_headers):
        """Test updating user permissions via PUT /api/users/{id}"""
        headers, _ = auth_headers
        unique_email = f"test_update_perms_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create user with default staff permissions (1/13)
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Update Perms Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        initial_count = sum(1 for v in create_resp.json()["permissions"].values() if v)
        assert initial_count == 1, f"Initial should be 1, got {initial_count}"
        
        # Update to grant more permissions
        new_perms = {p: True for p in ALL_PERMISSIONS}
        new_perms["can_manage_users"] = False  # 12/13
        
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "permissions": new_perms
        })
        assert update_resp.status_code == 200
        updated_count = sum(1 for v in update_resp.json()["permissions"].values() if v)
        assert updated_count == 12, f"Updated should be 12, got {updated_count}"
        print(f"PUT /api/users with permissions: Updated from 1 to 12 permissions")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    # ========== PUT /api/users/{id}/permissions tests ==========
    
    def test_update_permissions_via_dedicated_endpoint(self, auth_headers):
        """Test updating permissions via PUT /api/users/{id}/permissions endpoint"""
        headers, _ = auth_headers
        unique_email = f"test_perms_endpoint_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create user
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Perms Endpoint Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "manager"  # Starts with 13/13
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Update via dedicated endpoint - set only 3 permissions
        new_perms = {p: False for p in ALL_PERMISSIONS}
        new_perms["can_add_sales"] = True
        new_perms["can_view_reports"] = True
        new_perms["can_upload_files"] = True
        
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}/permissions", headers=headers, json=new_perms)
        assert update_resp.status_code == 200
        
        final_count = sum(1 for v in update_resp.json()["permissions"].values() if v)
        assert final_count == 3, f"Should have 3 permissions, got {final_count}"
        assert update_resp.json()["permissions"]["can_add_sales"] == True
        assert update_resp.json()["permissions"]["can_view_reports"] == True
        assert update_resp.json()["permissions"]["can_upload_files"] == True
        print(f"PUT /api/users/{'{id}'}/permissions: Success (3/13 permissions)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_permissions_endpoint_requires_manager(self, auth_headers):
        """Test that permissions endpoint requires manager access"""
        headers, _ = auth_headers
        unique_email = f"test_perms_403_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create a staff user
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Staff User",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        user_id = create_resp.json()["id"]
        
        # Login as staff user
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        staff_token = login_resp.json()["token"]
        staff_headers = {"Authorization": f"Bearer {staff_token}"}
        
        # Try to update permissions - should fail
        perms_resp = requests.put(f"{BASE_URL}/api/users/{user_id}/permissions", headers=staff_headers, json={
            "can_add_sales": True
        })
        assert perms_resp.status_code == 403, f"Expected 403, got {perms_resp.status_code}"
        print("PUT /api/users/{id}/permissions: 403 for non-manager")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    # ========== GET /api/users returns permissions tests ==========
    
    def test_list_users_includes_permissions(self, auth_headers):
        """Test that GET /api/users returns permissions field for each user"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        assert response.status_code == 200
        users = response.json()
        
        for user in users:
            assert "permissions" in user, f"User {user['email']} missing permissions field"
            assert "password_hash" not in user, f"User {user['email']} should not expose password_hash"
            # Verify all 13 keys present
            for perm in ALL_PERMISSIONS:
                assert perm in user["permissions"], f"User {user['email']} missing permission key: {perm}"
        
        print(f"GET /api/users: All {len(users)} users have permissions field")
    
    def test_user_without_stored_permissions_gets_role_defaults(self, auth_headers):
        """Test that users without stored permissions get role defaults via _safe_user"""
        headers, _ = auth_headers
        # The demo user may or may not have stored permissions
        # If not stored, should get manager defaults (13/13)
        response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        users = response.json()
        
        # Find the demo user (manager)
        demo_user = next((u for u in users if u["email"] == "demo@test.com"), None)
        assert demo_user is not None, "Demo user should exist"
        assert demo_user["role"] == "manager"
        
        # Should have permissions (either stored or defaulted)
        true_count = sum(1 for v in demo_user["permissions"].values() if v)
        assert true_count == 13, f"Manager should have 13/13 permissions, got {true_count}"
        print("Demo user (manager): Has 13/13 permissions as expected")


class TestPermissionEdgeCases:
    """Edge case tests for permissions system"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth token for manager user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_permissions_sanitized_on_update(self, auth_headers):
        """Test that permissions are sanitized when updating via dedicated endpoint"""
        headers = auth_headers
        unique_email = f"test_sanitize_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create a user first
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Sanitize Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Try to update with invalid keys via dedicated endpoint - these are sanitized
        invalid_perms = {p: True for p in ALL_PERMISSIONS}
        invalid_perms["invalid_permission"] = True
        invalid_perms["can_hack_system"] = True
        
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}/permissions", headers=headers, json=invalid_perms)
        assert update_resp.status_code == 200
        updated_perms = update_resp.json()["permissions"]
        
        # Invalid keys should not be stored on update via permissions endpoint
        assert "invalid_permission" not in updated_perms, "Invalid keys should be sanitized on update"
        assert "can_hack_system" not in updated_perms, "Invalid keys should be sanitized on update"
        # Valid keys should be stored
        assert len(updated_perms) == 13
        print("Permissions sanitized on update via /permissions endpoint")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_missing_permission_keys_default_to_false(self, auth_headers):
        """Test that missing permission keys default to false on update"""
        headers = auth_headers
        unique_email = f"test_missing_keys_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create user
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Missing Keys Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        user_id = create_resp.json()["id"]
        
        # Update with partial permissions (only 2 keys)
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}/permissions", headers=headers, json={
            "can_add_sales": True,
            "can_upload_files": True
        })
        assert update_resp.status_code == 200
        
        # All other keys should be false
        perms = update_resp.json()["permissions"]
        true_count = sum(1 for v in perms.values() if v)
        assert true_count == 2, f"Should have 2 true, got {true_count}"
        assert perms["can_add_sales"] == True
        assert perms["can_upload_files"] == True
        assert perms["can_manage_users"] == False
        print("Missing permission keys default to false")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
