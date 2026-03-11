# Test file: Layout Navigation and Upload Features
# Testing sidebar navigation structure, Purchases/Sales dialogs with upload options, and /upload route redirect

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthAndBasicEndpoints:
    """Authentication and basic endpoint tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "test@demo.com"
        print("Login test passed - token received")
    
    def test_auth_me_endpoint(self, auth_headers):
        """Test /auth/me returns user info"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@demo.com"
        print("Auth/me endpoint working correctly")


class TestPurchasesAPI:
    """Test Purchases CRUD endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_list_purchases(self, auth_headers):
        """Test GET /purchases returns list"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Purchases list endpoint working - returned {len(data)} items")
    
    def test_create_purchase(self, auth_headers):
        """Test POST /purchases creates a new purchase"""
        purchase_data = {
            "supplier_name": "TEST_Supplier_NavTest",
            "invoice_number": "TEST-INV-001",
            "invoice_date": "2025-01-15",
            "items": [
                {"raw_name": "Test Item", "quantity": 5, "unit": "kg", "unit_price": 10.50, "total": 52.50}
            ],
            "subtotal": 52.50,
            "tax": 5.25,
            "total": 57.75
        }
        response = requests.post(f"{BASE_URL}/api/purchases", headers=auth_headers, json=purchase_data)
        assert response.status_code == 200
        data = response.json()
        assert data["supplier_name"] == "TEST_Supplier_NavTest"
        assert data["invoice_number"] == "TEST-INV-001"
        assert "id" in data
        print(f"Purchase created successfully with id: {data['id']}")
        return data["id"]
    
    def test_get_purchase_by_id(self, auth_headers):
        """Test GET /purchases/{id} returns purchase details"""
        # First create a purchase
        purchase_data = {
            "supplier_name": "TEST_GetById_Supplier",
            "invoice_number": "TEST-GET-001",
            "invoice_date": "2025-01-15",
            "items": [{"raw_name": "Item A", "quantity": 2, "unit": "box", "unit_price": 25.00, "total": 50.00}],
            "subtotal": 50.00,
            "tax": 5.00,
            "total": 55.00
        }
        create_resp = requests.post(f"{BASE_URL}/api/purchases", headers=auth_headers, json=purchase_data)
        purchase_id = create_resp.json()["id"]
        
        # Then get it
        response = requests.get(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["supplier_name"] == "TEST_GetById_Supplier"
        print(f"Get purchase by ID working - retrieved: {data['invoice_number']}")
    
    def test_delete_purchase(self, auth_headers):
        """Test DELETE /purchases/{id} removes purchase"""
        # Create then delete
        purchase_data = {
            "supplier_name": "TEST_Delete_Supplier",
            "invoice_number": "TEST-DEL-001",
            "invoice_date": "2025-01-15",
            "items": [],
            "subtotal": 0,
            "tax": 0,
            "total": 0
        }
        create_resp = requests.post(f"{BASE_URL}/api/purchases", headers=auth_headers, json=purchase_data)
        purchase_id = create_resp.json()["id"]
        
        # Delete
        delete_resp = requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert delete_resp.status_code == 200
        
        # Verify deleted
        get_resp = requests.get(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert get_resp.status_code == 404
        print("Delete purchase working correctly")


class TestSalesAPI:
    """Test Sales CRUD endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_list_sales(self, auth_headers):
        """Test GET /sales returns list"""
        response = requests.get(f"{BASE_URL}/api/sales", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Sales list endpoint working - returned {len(data)} items")
    
    def test_create_sale(self, auth_headers):
        """Test POST /sales creates a new sale"""
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 1250.75,
            "items": [
                {"menu_item": "Burger Special", "quantity": 25, "revenue": 375.00},
                {"menu_item": "Pizza Combo", "quantity": 18, "revenue": 450.00}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/sales", headers=auth_headers, json=sale_data)
        assert response.status_code == 200
        data = response.json()
        assert data["total_sales"] == 1250.75
        assert "id" in data
        print(f"Sale created successfully with id: {data['id']}")
    
    def test_delete_sale(self, auth_headers):
        """Test DELETE /sales/{id} removes sale"""
        # Create then delete
        sale_data = {
            "report_date": "2025-01-15",
            "total_sales": 500.00,
            "items": []
        }
        create_resp = requests.post(f"{BASE_URL}/api/sales", headers=auth_headers, json=sale_data)
        sale_id = create_resp.json()["id"]
        
        # Delete
        delete_resp = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert delete_resp.status_code == 200
        
        # Verify deleted
        get_resp = requests.get(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert get_resp.status_code == 404
        print("Delete sale working correctly")


class TestUploadExtractEndpoint:
    """Test /upload/extract endpoint for OCR/AI extraction"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_upload_extract_endpoint_exists(self, auth_headers):
        """Test POST /upload/extract endpoint exists (without actual file)"""
        # Sending empty request should return error, not 404
        # This verifies the endpoint exists
        response = requests.post(f"{BASE_URL}/api/upload/extract", headers=auth_headers)
        # Expected: 422 (validation error for missing file) - NOT 404
        assert response.status_code != 404, "Upload extract endpoint should exist"
        print(f"Upload extract endpoint exists - status code: {response.status_code}")
    
    def test_upload_extract_with_document_type_purchase(self, auth_headers):
        """Test /upload/extract validates document_type=purchase_invoice"""
        # Create a minimal test image (1x1 white pixel PNG)
        import base64
        # Minimal valid PNG (1x1 white pixel)
        png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
        
        files = {'file': ('test.png', png_bytes, 'image/png')}
        data = {'document_type': 'purchase_invoice'}
        
        response = requests.post(
            f"{BASE_URL}/api/upload/extract",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=90  # AI extraction can be slow
        )
        # The endpoint should accept the request (may return extracted data or error from AI)
        # Important: should NOT be 404
        assert response.status_code != 404, "Endpoint should handle purchase_invoice document_type"
        print(f"Purchase invoice extraction endpoint responded with status: {response.status_code}")


class TestNavigationEndpoints:
    """Test all navigation-related endpoints exist"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_dashboard_summary_endpoint(self, auth_headers):
        """Test /dashboard/summary exists (for Dashboard nav)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=auth_headers)
        assert response.status_code == 200
        print("Dashboard summary endpoint working")
    
    def test_suppliers_endpoint(self, auth_headers):
        """Test /suppliers exists (for Suppliers nav)"""
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=auth_headers)
        assert response.status_code == 200
        print("Suppliers endpoint working")
    
    def test_items_endpoint(self, auth_headers):
        """Test /items exists (for Items nav)"""
        response = requests.get(f"{BASE_URL}/api/items", headers=auth_headers)
        assert response.status_code == 200
        print("Items endpoint working")
    
    def test_reports_endpoint(self, auth_headers):
        """Test /reports exists (for Reports nav)"""
        response = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        assert response.status_code == 200
        print("Reports endpoint working")
    
    def test_chat_messages_endpoint(self, auth_headers):
        """Test /chat/messages exists (for Chat Assistant nav)"""
        response = requests.get(f"{BASE_URL}/api/chat/messages", headers=auth_headers)
        assert response.status_code == 200
        print("Chat messages endpoint working")
    
    def test_settings_endpoint(self, auth_headers):
        """Test /settings exists (for Settings nav)"""
        response = requests.get(f"{BASE_URL}/api/settings", headers=auth_headers)
        assert response.status_code == 200
        print("Settings endpoint working")


class TestCleanup:
    """Cleanup test data after tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_cleanup_test_purchases(self, auth_headers):
        """Delete all TEST_ prefixed purchases"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        purchases = response.json()
        deleted = 0
        for p in purchases:
            if p.get("supplier_name", "").startswith("TEST_") or p.get("invoice_number", "").startswith("TEST"):
                requests.delete(f"{BASE_URL}/api/purchases/{p['id']}", headers=auth_headers)
                deleted += 1
        print(f"Cleaned up {deleted} test purchases")
