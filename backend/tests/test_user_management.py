"""
Test User Management API endpoints (iteration 19)
Tests CRUD operations for users: create, read, update, delete
Tests self-protection rules and role/status management
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestUserManagement:
    """User Management API tests - Manager role required"""
    
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
    
    # ========== GET /api/users tests ==========
    
    def test_list_users_success(self, auth_headers):
        """Test listing all users returns array without password_hash"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        users = response.json()
        assert isinstance(users, list), "Expected list of users"
        assert len(users) >= 1, "Should have at least one user (the manager)"
        # Check password_hash is not exposed
        for user in users:
            assert "password_hash" not in user, "password_hash should not be exposed"
            assert "id" in user, "User should have id"
            assert "email" in user, "User should have email"
            assert "name" in user, "User should have name"
            assert "role" in user, "User should have role"
            assert "status" in user, "User should have status"
            assert "created_at" in user, "User should have created_at"
        print(f"GET /api/users: {len(users)} users returned")
    
    def test_list_users_requires_auth(self):
        """Test listing users without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/users")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("GET /api/users without auth: 401 as expected")
    
    # ========== POST /api/users tests ==========
    
    def test_create_user_manager_role(self, auth_headers):
        """Test creating a user with manager role"""
        headers, _ = auth_headers
        unique_email = f"test_manager_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Test Manager",
            "email": unique_email,
            "password": "testpass123",
            "role": "manager"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        assert user["role"] == "manager", f"Expected role 'manager', got {user['role']}"
        assert user["status"] == "active", "New user should be active"
        assert "password_hash" not in user, "password_hash should not be in response"
        print(f"POST /api/users manager role: Created user {unique_email}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    def test_create_user_accountant_role(self, auth_headers):
        """Test creating a user with accountant role"""
        headers, _ = auth_headers
        unique_email = f"test_accountant_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Test Accountant",
            "email": unique_email,
            "password": "testpass123",
            "role": "accountant"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        assert user["role"] == "accountant", f"Expected role 'accountant', got {user['role']}"
        print(f"POST /api/users accountant role: Created user {unique_email}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    def test_create_user_cashier_role(self, auth_headers):
        """Test creating a user with cashier role"""
        headers, _ = auth_headers
        unique_email = f"test_cashier_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Test Cashier",
            "email": unique_email,
            "password": "testpass123",
            "role": "cashier"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        assert user["role"] == "cashier", f"Expected role 'cashier', got {user['role']}"
        print(f"POST /api/users cashier role: Created user {unique_email}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    def test_create_user_staff_role(self, auth_headers):
        """Test creating a user with staff role (default)"""
        headers, _ = auth_headers
        unique_email = f"test_staff_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Test Staff",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        assert user["role"] == "staff", f"Expected role 'staff', got {user['role']}"
        print(f"POST /api/users staff role: Created user {unique_email}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user['id']}", headers=headers)
    
    def test_create_user_duplicate_email(self, auth_headers):
        """Test creating user with duplicate email returns 400"""
        headers, _ = auth_headers
        # Try to create user with same email as demo user
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Duplicate User",
            "email": "demo@test.com",
            "password": "testpass123",
            "role": "staff"
        })
        assert response.status_code == 400, f"Expected 400 for duplicate email, got {response.status_code}"
        assert "already" in response.json().get("detail", "").lower(), "Should mention email already in use"
        print("POST /api/users duplicate email: 400 as expected")
    
    def test_create_user_short_password(self, auth_headers):
        """Test creating user with password < 6 chars returns 400"""
        headers, _ = auth_headers
        unique_email = f"test_short_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Short Password",
            "email": unique_email,
            "password": "12345",
            "role": "staff"
        })
        assert response.status_code == 400, f"Expected 400 for short password, got {response.status_code}"
        assert "6 char" in response.json().get("detail", "").lower(), "Should mention 6 character minimum"
        print("POST /api/users short password: 400 as expected")
    
    def test_create_user_invalid_role(self, auth_headers):
        """Test creating user with invalid role returns 400"""
        headers, _ = auth_headers
        unique_email = f"test_invalid_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Invalid Role",
            "email": unique_email,
            "password": "testpass123",
            "role": "superadmin"
        })
        assert response.status_code == 400, f"Expected 400 for invalid role, got {response.status_code}"
        print("POST /api/users invalid role: 400 as expected")
    
    # ========== PUT /api/users tests ==========
    
    def test_update_user_name_email(self, auth_headers):
        """Test updating user name and email"""
        headers, _ = auth_headers
        # First create a test user
        unique_email = f"test_update_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Original Name",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Update name and email
        new_email = f"test_updated_{uuid.uuid4().hex[:8]}@test.com"
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "name": "Updated Name",
            "email": new_email
        })
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        updated = update_resp.json()
        assert updated["name"] == "Updated Name", "Name should be updated"
        assert updated["email"] == new_email, "Email should be updated"
        print(f"PUT /api/users update name/email: Success")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_update_user_password(self, auth_headers):
        """Test updating user password"""
        headers, _ = auth_headers
        # Create test user
        unique_email = f"test_pwupdate_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Password Update Test",
            "email": unique_email,
            "password": "oldpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Update password
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "password": "newpass456"
        })
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}"
        
        # Verify new password works for login
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "newpass456"
        })
        assert login_resp.status_code == 200, "Login with new password should succeed"
        print(f"PUT /api/users password update: Success")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_update_user_role(self, auth_headers):
        """Test updating user role"""
        headers, _ = auth_headers
        unique_email = f"test_roleupdate_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Role Update Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Update role to accountant
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "role": "accountant"
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["role"] == "accountant"
        print(f"PUT /api/users role update: Success")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_update_user_status_deactivate(self, auth_headers):
        """Test deactivating a user"""
        headers, _ = auth_headers
        unique_email = f"test_deactivate_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Deactivate Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Deactivate user
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "status": "inactive"
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "inactive"
        print(f"PUT /api/users deactivate: Success")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_deactivated_user_cannot_login(self, auth_headers):
        """Test that a deactivated user cannot login"""
        headers, _ = auth_headers
        unique_email = f"test_inactive_login_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Inactive Login Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Deactivate user
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "status": "inactive"
        })
        assert update_resp.status_code == 200
        
        # Try to login as deactivated user - should get 403
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 403, f"Expected 403 for inactive user login, got {login_resp.status_code}"
        print("Deactivated user login: 403 as expected")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_reactivated_user_can_login(self, auth_headers):
        """Test that a reactivated user can login again"""
        headers, _ = auth_headers
        unique_email = f"test_reactivate_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Reactivate Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Deactivate
        requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={"status": "inactive"})
        
        # Reactivate
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={"status": "active"})
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "active"
        
        # Login should work again
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 200, f"Expected 200 for reactivated user login, got {login_resp.status_code}"
        print("Reactivated user login: Success")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    def test_update_user_duplicate_email(self, auth_headers):
        """Test updating user with duplicate email returns 400"""
        headers, _ = auth_headers
        unique_email = f"test_dupemail_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Dup Email Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Try to update email to existing email
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", headers=headers, json={
            "email": "demo@test.com"
        })
        assert update_resp.status_code == 400, f"Expected 400 for duplicate email, got {update_resp.status_code}"
        print("PUT /api/users duplicate email: 400 as expected")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
    
    # ========== Self-protection tests ==========
    
    def test_cannot_deactivate_self(self, auth_headers):
        """Test manager cannot deactivate themselves"""
        headers, current_user = auth_headers
        update_resp = requests.put(f"{BASE_URL}/api/users/{current_user['id']}", headers=headers, json={
            "status": "inactive"
        })
        assert update_resp.status_code == 400, f"Expected 400, got {update_resp.status_code}"
        assert "yourself" in update_resp.json().get("detail", "").lower()
        print("Self-deactivation prevention: 400 as expected")
    
    def test_cannot_delete_self(self, auth_headers):
        """Test manager cannot delete themselves"""
        headers, current_user = auth_headers
        delete_resp = requests.delete(f"{BASE_URL}/api/users/{current_user['id']}", headers=headers)
        assert delete_resp.status_code == 400, f"Expected 400, got {delete_resp.status_code}"
        assert "yourself" in delete_resp.json().get("detail", "").lower()
        print("Self-deletion prevention: 400 as expected")
    
    def test_cannot_change_own_role(self, auth_headers):
        """Test manager cannot change their own role away from manager"""
        headers, current_user = auth_headers
        update_resp = requests.put(f"{BASE_URL}/api/users/{current_user['id']}", headers=headers, json={
            "role": "staff"
        })
        assert update_resp.status_code == 400, f"Expected 400, got {update_resp.status_code}"
        assert "role" in update_resp.json().get("detail", "").lower()
        print("Self-role change prevention: 400 as expected")
    
    # ========== DELETE /api/users tests ==========
    
    def test_delete_user(self, auth_headers):
        """Test deleting a user"""
        headers, _ = auth_headers
        unique_email = f"test_delete_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Delete Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Delete the user
        delete_resp = requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)
        assert delete_resp.status_code == 200, f"Expected 200, got {delete_resp.status_code}"
        assert delete_resp.json().get("status") == "deleted"
        
        # Verify user is gone
        list_resp = requests.get(f"{BASE_URL}/api/users", headers=headers)
        users = list_resp.json()
        user_ids = [u["id"] for u in users]
        assert user_id not in user_ids, "Deleted user should not be in list"
        print("DELETE /api/users: Success")
    
    def test_delete_nonexistent_user(self, auth_headers):
        """Test deleting nonexistent user returns 404"""
        headers, _ = auth_headers
        fake_id = str(uuid.uuid4())
        delete_resp = requests.delete(f"{BASE_URL}/api/users/{fake_id}", headers=headers)
        assert delete_resp.status_code == 404, f"Expected 404, got {delete_resp.status_code}"
        print("DELETE /api/users nonexistent: 404 as expected")
    
    # ========== GET /api/auth/me tests ==========
    
    def test_auth_me_returns_role(self, auth_headers):
        """Test GET /api/auth/me returns role field"""
        headers, _ = auth_headers
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        user = response.json()
        assert "role" in user, "role field should be in /auth/me response"
        assert user["role"] in ["manager", "accountant", "cashier", "staff"], f"Invalid role: {user['role']}"
        print(f"GET /api/auth/me: role = {user['role']}")
    
    # ========== Non-manager access tests ==========
    
    def test_non_manager_cannot_access_users(self, auth_headers):
        """Test non-manager role cannot access user management endpoints"""
        headers, _ = auth_headers
        # Create a staff user
        unique_email = f"test_staff_access_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "name": "Staff Access Test",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]
        
        # Login as staff user
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert login_resp.status_code == 200
        staff_token = login_resp.json()["token"]
        staff_headers = {"Authorization": f"Bearer {staff_token}"}
        
        # Try to list users - should fail with 403
        list_resp = requests.get(f"{BASE_URL}/api/users", headers=staff_headers)
        assert list_resp.status_code == 403, f"Expected 403 for non-manager, got {list_resp.status_code}"
        
        # Try to create user - should fail with 403
        create_user_resp = requests.post(f"{BASE_URL}/api/users", headers=staff_headers, json={
            "name": "Test",
            "email": "test123@test.com",
            "password": "testpass",
            "role": "staff"
        })
        assert create_user_resp.status_code == 403
        print("Non-manager access restriction: 403 as expected")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
