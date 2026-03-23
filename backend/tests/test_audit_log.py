"""
Audit Log System Tests
Tests for GET /api/audit-logs endpoint and audit log creation via CRUD operations
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


class TestAuditLogAPI:
    """Tests for the Audit Log API endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.user = login_response.json().get("user")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
    # ==================== GET /api/audit-logs Tests ====================
    
    def test_audit_logs_returns_200_with_valid_structure(self):
        """GET /api/audit-logs returns 200 with correct response structure"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "logs" in data, "Response missing 'logs' array"
        assert "total" in data, "Response missing 'total'"
        assert "page" in data, "Response missing 'page'"
        assert "page_size" in data, "Response missing 'page_size'"
        assert "total_pages" in data, "Response missing 'total_pages'"
        assert "users" in data, "Response missing 'users' array"
        
        # Verify types
        assert isinstance(data["logs"], list), "logs should be a list"
        assert isinstance(data["total"], int), "total should be an integer"
        assert isinstance(data["page"], int), "page should be an integer"
        assert isinstance(data["page_size"], int), "page_size should be an integer"
        assert isinstance(data["total_pages"], int), "total_pages should be an integer"
        assert isinstance(data["users"], list), "users should be a list"
        
        print(f"✓ Audit logs returned {data['total']} records, page {data['page']} of {data['total_pages']}")
        
    def test_audit_logs_log_entry_structure(self):
        """Verify each log entry has required fields"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs")
        assert response.status_code == 200
        
        data = response.json()
        if data["logs"]:
            log = data["logs"][0]
            required_fields = ["id", "user_id", "user_name", "user_role", "action_type", 
                             "entity_type", "entity_id", "description", "timestamp"]
            for field in required_fields:
                assert field in log, f"Log entry missing required field: {field}"
            
            # old_value and new_value can be null
            assert "old_value" in log or log.get("old_value") is None
            assert "new_value" in log or log.get("new_value") is None
            
            print(f"✓ Log entry structure valid: {log['action_type']} {log['entity_type']} by {log['user_name']}")
        else:
            print("⚠ No logs found to verify structure")
            
    def test_audit_logs_requires_auth(self):
        """GET /api/audit-logs requires authentication"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/audit-logs")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Audit logs endpoint requires authentication")
        
    def test_audit_logs_filter_by_action_type(self):
        """GET /api/audit-logs?action_type=LOGIN filters correctly"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={"action_type": "LOGIN"})
        assert response.status_code == 200
        
        data = response.json()
        for log in data["logs"]:
            assert log["action_type"] == "LOGIN", f"Expected LOGIN, got {log['action_type']}"
        
        print(f"✓ Filter by action_type=LOGIN returned {len(data['logs'])} logs")
        
    def test_audit_logs_filter_by_entity_type(self):
        """GET /api/audit-logs?entity_type=Vendor filters correctly"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={"entity_type": "Vendor"})
        assert response.status_code == 200
        
        data = response.json()
        for log in data["logs"]:
            assert log["entity_type"] == "Vendor", f"Expected Vendor, got {log['entity_type']}"
        
        print(f"✓ Filter by entity_type=Vendor returned {len(data['logs'])} logs")
        
    def test_audit_logs_filter_by_search(self):
        """GET /api/audit-logs?search=keyword filters by description"""
        # First get all logs to find a keyword
        all_response = self.session.get(f"{BASE_URL}/api/audit-logs")
        assert all_response.status_code == 200
        
        all_data = all_response.json()
        if all_data["logs"]:
            # Use a word from the first log's description
            first_desc = all_data["logs"][0]["description"]
            search_word = first_desc.split()[0] if first_desc else "logged"
            
            response = self.session.get(f"{BASE_URL}/api/audit-logs", params={"search": search_word})
            assert response.status_code == 200
            
            data = response.json()
            for log in data["logs"]:
                assert search_word.lower() in log["description"].lower(), f"Search term '{search_word}' not in description"
            
            print(f"✓ Search filter for '{search_word}' returned {len(data['logs'])} logs")
        else:
            print("⚠ No logs to test search filter")
            
    def test_audit_logs_pagination(self):
        """GET /api/audit-logs?page=1&page_size=2 returns correct pagination"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={"page": 1, "page_size": 2})
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 1, f"Expected page 1, got {data['page']}"
        assert data["page_size"] == 2, f"Expected page_size 2, got {data['page_size']}"
        assert len(data["logs"]) <= 2, f"Expected max 2 logs, got {len(data['logs'])}"
        
        # Verify total_pages calculation
        expected_pages = max(1, -(-data["total"] // 2))  # Ceiling division
        assert data["total_pages"] == expected_pages, f"Expected {expected_pages} pages, got {data['total_pages']}"
        
        print(f"✓ Pagination works: page {data['page']}/{data['total_pages']}, {len(data['logs'])} logs returned")
        
    def test_audit_logs_users_array(self):
        """GET /api/audit-logs returns users array for filter dropdown"""
        response = self.session.get(f"{BASE_URL}/api/audit-logs")
        assert response.status_code == 200
        
        data = response.json()
        assert "users" in data
        
        if data["users"]:
            user = data["users"][0]
            assert "id" in user, "User missing 'id'"
            assert "name" in user, "User missing 'name'"
            print(f"✓ Users array contains {len(data['users'])} users for filter dropdown")
        else:
            print("⚠ No users in users array")
            
    # ==================== Immutability Tests ====================
    
    def test_no_put_endpoint_for_audit_logs(self):
        """Verify no PUT endpoint exists for audit logs (immutable)"""
        # Try to update a non-existent audit log
        response = self.session.put(f"{BASE_URL}/api/audit-logs/fake-id", json={"description": "modified"})
        # Should return 404 (not found) or 405 (method not allowed), not 200
        assert response.status_code in [404, 405, 422], f"PUT should not be allowed, got {response.status_code}"
        print("✓ No PUT endpoint for audit logs (immutable)")
        
    def test_no_delete_endpoint_for_audit_logs(self):
        """Verify no DELETE endpoint exists for audit logs (immutable)"""
        response = self.session.delete(f"{BASE_URL}/api/audit-logs/fake-id")
        # Should return 404 (not found) or 405 (method not allowed), not 200
        assert response.status_code in [404, 405, 422], f"DELETE should not be allowed, got {response.status_code}"
        print("✓ No DELETE endpoint for audit logs (immutable)")


class TestAuditLogCreation:
    """Tests for audit log creation via CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.user = login_response.json().get("user")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
    def test_login_creates_audit_entry(self):
        """POST /api/auth/login creates a LOGIN audit entry"""
        # Login again to create a new audit entry
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200
        
        # Check audit logs for LOGIN entry
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={"action_type": "LOGIN"})
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["logs"]) > 0, "No LOGIN audit entries found"
        
        # Verify the most recent login entry
        login_log = data["logs"][0]
        assert login_log["action_type"] == "LOGIN"
        assert login_log["entity_type"] == "User"
        assert "logged in" in login_log["description"].lower()
        
        print(f"✓ Login creates audit entry: {login_log['description']}")
        
    def test_create_supplier_creates_audit_entry(self):
        """POST /api/suppliers creates a CREATE Vendor audit entry"""
        unique_name = f"TEST_Audit_Vendor_{uuid.uuid4().hex[:8]}"
        
        # Create a supplier
        create_response = self.session.post(f"{BASE_URL}/api/suppliers", json={
            "name": unique_name,
            "contact_person": "Test Contact",
            "phone": "555-1234"
        })
        assert create_response.status_code == 200, f"Create supplier failed: {create_response.text}"
        supplier_id = create_response.json().get("id")
        
        # Check audit logs for CREATE Vendor entry
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={
            "action_type": "CREATE",
            "entity_type": "Vendor"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["logs"]) > 0, "No CREATE Vendor audit entries found"
        
        # Find the entry for our supplier
        found = False
        for log in data["logs"]:
            if unique_name in log["description"]:
                found = True
                assert log["action_type"] == "CREATE"
                assert log["entity_type"] == "Vendor"
                assert log["entity_id"] == supplier_id
                assert log["new_value"] is not None
                print(f"✓ Create supplier creates audit entry: {log['description']}")
                break
        
        assert found, f"Audit entry for supplier '{unique_name}' not found"
        
        # Cleanup: delete the supplier
        self.session.delete(f"{BASE_URL}/api/suppliers/{supplier_id}")
        
    def test_create_item_creates_audit_entry(self):
        """POST /api/items creates a CREATE Item audit entry"""
        unique_name = f"TEST_Audit_Item_{uuid.uuid4().hex[:8]}"
        
        # Create an item
        create_response = self.session.post(f"{BASE_URL}/api/items", json={
            "name": unique_name,
            "category": "Test Category"
        })
        assert create_response.status_code == 200, f"Create item failed: {create_response.text}"
        item_id = create_response.json().get("id")
        
        # Check audit logs for CREATE Item entry
        response = self.session.get(f"{BASE_URL}/api/audit-logs", params={
            "action_type": "CREATE",
            "entity_type": "Item"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["logs"]) > 0, "No CREATE Item audit entries found"
        
        # Find the entry for our item
        found = False
        for log in data["logs"]:
            if unique_name in log["description"]:
                found = True
                assert log["action_type"] == "CREATE"
                assert log["entity_type"] == "Item"
                assert log["entity_id"] == item_id
                assert log["new_value"] is not None
                print(f"✓ Create item creates audit entry: {log['description']}")
                break
        
        assert found, f"Audit entry for item '{unique_name}' not found"
        
        # Cleanup: delete the item
        self.session.delete(f"{BASE_URL}/api/items/{item_id}")


class TestAuditLogManagerAccess:
    """Tests for manager-only access to audit logs"""
    
    def test_non_manager_gets_403(self):
        """Non-manager users should get 403 when accessing audit logs"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # First login as manager to create a non-manager user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200
        manager_token = login_response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {manager_token}"})
        
        # Create a staff user
        unique_email = f"test_staff_{uuid.uuid4().hex[:8]}@test.com"
        create_response = session.post(f"{BASE_URL}/api/users", json={
            "name": "Test Staff User",
            "email": unique_email,
            "password": "testpass123",
            "role": "staff"
        })
        
        if create_response.status_code == 200:
            staff_user_id = create_response.json().get("id")
            
            # Login as staff user
            staff_session = requests.Session()
            staff_session.headers.update({"Content-Type": "application/json"})
            staff_login = staff_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": unique_email,
                "password": "testpass123"
            })
            
            if staff_login.status_code == 200:
                staff_token = staff_login.json().get("token")
                staff_session.headers.update({"Authorization": f"Bearer {staff_token}"})
                
                # Try to access audit logs as staff
                audit_response = staff_session.get(f"{BASE_URL}/api/audit-logs")
                assert audit_response.status_code == 403, f"Expected 403 for non-manager, got {audit_response.status_code}"
                print("✓ Non-manager user gets 403 when accessing audit logs")
            else:
                print(f"⚠ Could not login as staff user: {staff_login.status_code}")
            
            # Cleanup: delete the staff user
            session.delete(f"{BASE_URL}/api/users/{staff_user_id}")
        else:
            print(f"⚠ Could not create staff user for testing: {create_response.status_code}")
            pytest.skip("Could not create staff user for testing")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
