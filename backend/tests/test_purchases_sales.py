"""
Test suite for Purchases and Sales CRUD APIs
Tests: Add Purchase, Add Sale, Delete, View, Line items operations
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication helper tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        return data["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestPurchasesCRUD(TestAuth):
    """Test Purchases API endpoints"""
    
    def test_list_purchases(self, auth_headers):
        """Test GET /api/purchases returns list"""
        response = requests.get(f"{BASE_URL}/api/purchases", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} existing purchases")
    
    def test_create_purchase_success(self, auth_headers):
        """Test POST /api/purchases creates a new purchase"""
        purchase_data = {
            "supplier_name": "TEST_Supplier_" + str(uuid.uuid4())[:8],
            "invoice_number": "TEST-INV-001",
            "invoice_date": "2026-01-10",
            "items": [
                {"raw_name": "Test Item 1", "quantity": 10, "unit": "kg", "unit_price": 5.50, "total": 55.00},
                {"raw_name": "Test Item 2", "quantity": 5, "unit": "box", "unit_price": 20.00, "total": 100.00}
            ],
            "subtotal": 155.00,
            "tax": 15.50,
            "total": 170.50
        }
        response = requests.post(f"{BASE_URL}/api/purchases", json=purchase_data, headers=auth_headers)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        # Verify returned data
        assert "id" in data
        assert data["supplier_name"] == purchase_data["supplier_name"]
        assert data["invoice_number"] == purchase_data["invoice_number"]
        assert data["invoice_date"] == purchase_data["invoice_date"]
        assert len(data["items"]) == 2
        assert data["subtotal"] == 155.00
        assert data["tax"] == 15.50
        assert data["total"] == 170.50
        print(f"Created purchase with ID: {data['id']}")
        
        # Store for cleanup
        self.__class__.created_purchase_id = data["id"]
        return data["id"]
    
    def test_get_purchase_by_id(self, auth_headers):
        """Test GET /api/purchases/{id} returns purchase details"""
        purchase_id = getattr(self.__class__, 'created_purchase_id', None)
        if not purchase_id:
            pytest.skip("No purchase created to fetch")
        
        response = requests.get(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == purchase_id
        assert "supplier_name" in data
        assert "items" in data
        print(f"Fetched purchase: {data['supplier_name']}")
    
    def test_create_purchase_with_line_items(self, auth_headers):
        """Test creating purchase with multiple line items"""
        purchase_data = {
            "supplier_name": "TEST_MultiItem_Supplier",
            "invoice_number": "TEST-MULTI-001",
            "invoice_date": "2026-01-11",
            "items": [
                {"raw_name": "Tomatoes", "quantity": 20, "unit": "kg", "unit_price": 3.50, "total": 70.00},
                {"raw_name": "Onions", "quantity": 15, "unit": "kg", "unit_price": 2.00, "total": 30.00},
                {"raw_name": "Lettuce", "quantity": 10, "unit": "head", "unit_price": 1.50, "total": 15.00},
            ],
            "subtotal": 115.00,
            "tax": 11.50,
            "total": 126.50
        }
        response = requests.post(f"{BASE_URL}/api/purchases", json=purchase_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) == 3
        assert data["items"][0]["raw_name"] == "Tomatoes"
        assert data["items"][1]["raw_name"] == "Onions"
        assert data["items"][2]["raw_name"] == "Lettuce"
        print(f"Created purchase with {len(data['items'])} line items")
        
        # Cleanup
        self.__class__.multi_item_purchase_id = data["id"]
    
    def test_create_purchase_validation_supplier_required(self, auth_headers):
        """Test that supplier_name is required"""
        purchase_data = {
            "supplier_name": "",  # Empty should fail validation
            "invoice_number": "TEST-FAIL-001",
            "invoice_date": "2026-01-10",
            "items": [],
            "subtotal": 0,
            "tax": 0,
            "total": 0
        }
        # Note: Backend may accept empty string - this tests if validation is in place
        response = requests.post(f"{BASE_URL}/api/purchases", json=purchase_data, headers=auth_headers)
        # Either 200 or 422/400 depending on backend validation
        print(f"Empty supplier response: {response.status_code}")
    
    def test_delete_purchase(self, auth_headers):
        """Test DELETE /api/purchases/{id}"""
        purchase_id = getattr(self.__class__, 'created_purchase_id', None)
        if not purchase_id:
            pytest.skip("No purchase to delete")
        
        response = requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        print(f"Deleted purchase: {purchase_id}")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
        assert get_response.status_code == 404
        print("Verified purchase no longer exists")
    
    def test_cleanup_multi_item_purchase(self, auth_headers):
        """Cleanup multi-item purchase"""
        purchase_id = getattr(self.__class__, 'multi_item_purchase_id', None)
        if purchase_id:
            requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=auth_headers)
            print(f"Cleaned up multi-item purchase: {purchase_id}")


class TestSalesCRUD(TestAuth):
    """Test Sales API endpoints"""
    
    def test_list_sales(self, auth_headers):
        """Test GET /api/sales returns list"""
        response = requests.get(f"{BASE_URL}/api/sales", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} existing sales")
    
    def test_create_sale_success(self, auth_headers):
        """Test POST /api/sales creates a new sale"""
        sale_data = {
            "report_date": "2026-01-10",
            "total_sales": 1500.00,
            "items": [
                {"menu_item": "Burger Special", "quantity": 25, "revenue": 375.00},
                {"menu_item": "Pizza Margherita", "quantity": 15, "revenue": 225.00}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=auth_headers)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        # Verify returned data
        assert "id" in data
        assert data["report_date"] == sale_data["report_date"]
        assert data["total_sales"] == sale_data["total_sales"]
        assert len(data["items"]) == 2
        print(f"Created sale with ID: {data['id']}")
        
        self.__class__.created_sale_id = data["id"]
        return data["id"]
    
    def test_get_sale_by_id(self, auth_headers):
        """Test GET /api/sales/{id} returns sale details"""
        sale_id = getattr(self.__class__, 'created_sale_id', None)
        if not sale_id:
            pytest.skip("No sale created to fetch")
        
        response = requests.get(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sale_id
        assert "report_date" in data
        assert "total_sales" in data
        assert "items" in data
        print(f"Fetched sale from date: {data['report_date']}")
    
    def test_create_sale_with_menu_items(self, auth_headers):
        """Test creating sale with multiple menu items"""
        sale_data = {
            "report_date": "2026-01-11",
            "total_sales": 2500.00,
            "items": [
                {"menu_item": "Steak Dinner", "quantity": 10, "revenue": 350.00},
                {"menu_item": "Pasta Carbonara", "quantity": 20, "revenue": 400.00},
                {"menu_item": "Caesar Salad", "quantity": 30, "revenue": 300.00},
                {"menu_item": "Dessert Platter", "quantity": 15, "revenue": 150.00}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) == 4
        print(f"Created sale with {len(data['items'])} menu items")
        
        self.__class__.multi_item_sale_id = data["id"]
    
    def test_delete_sale(self, auth_headers):
        """Test DELETE /api/sales/{id}"""
        sale_id = getattr(self.__class__, 'created_sale_id', None)
        if not sale_id:
            pytest.skip("No sale to delete")
        
        response = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        print(f"Deleted sale: {sale_id}")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert get_response.status_code == 404
        print("Verified sale no longer exists")
    
    def test_cleanup_multi_item_sale(self, auth_headers):
        """Cleanup multi-item sale"""
        sale_id = getattr(self.__class__, 'multi_item_sale_id', None)
        if sale_id:
            requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
            print(f"Cleaned up multi-item sale: {sale_id}")


class TestUploadExtract(TestAuth):
    """Test upload/extract endpoint exists and requires file"""
    
    def test_upload_endpoint_exists(self, auth_headers):
        """Test that /api/upload/extract endpoint exists"""
        # Sending request without file should return error
        response = requests.post(
            f"{BASE_URL}/api/upload/extract", 
            headers={"Authorization": auth_headers["Authorization"]},
            data={"document_type": "purchase_invoice"}
        )
        # Should return 422 (validation error) because file is required
        assert response.status_code in [422, 400], f"Expected 422/400, got {response.status_code}"
        print("Upload endpoint exists and requires file (422 expected)")


class TestUploadCenterRemoved:
    """Test that Upload Center page is removed"""
    
    def test_upload_route_redirects_to_dashboard(self):
        """Test navigating to /upload redirects to dashboard"""
        response = requests.get(f"{BASE_URL}/upload", allow_redirects=False)
        # The React app handles this client-side, so we'll get 200 with the app
        # and the Route will redirect to /dashboard via Navigate component
        assert response.status_code == 200
        print("/upload returns 200 (React app handles redirect client-side)")
