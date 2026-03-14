"""
Test Sales Date Range Feature:
- POST /api/sales with date_from=date_to creates a sale with is_single_day=true
- POST /api/sales with date_from!=date_to creates a sale with is_single_day=false
- POST /api/sales with date_to before date_from returns 400 error
- POST /api/sales with only report_date (backward compat) still works
- GET /api/sales returns records with date_from, date_to, is_single_day fields
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

class TestSalesDateRange:
    """Test sales date range functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client, auth_token):
        """Setup for each test"""
        self.client = api_client
        self.token = auth_token
        self.client.headers.update({"Authorization": f"Bearer {auth_token}"})
        self.created_sale_ids = []
        yield
        # Cleanup: delete created test sales
        for sale_id in self.created_sale_ids:
            try:
                self.client.delete(f"{BASE_URL}/api/sales/{sale_id}")
            except:
                pass
    
    def test_single_day_entry_same_dates(self):
        """POST /api/sales with date_from=date_to creates is_single_day=true"""
        payload = {
            "date_from": "2026-05-01",
            "date_to": "2026-05-01",
            "total_sales": 1500.00,
            "items": []
        }
        response = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        self.created_sale_ids.append(data["id"])
        
        # Verify is_single_day is True
        assert data.get("is_single_day") == True, f"Expected is_single_day=True, got {data.get('is_single_day')}"
        assert data.get("date_from") == "2026-05-01"
        assert data.get("date_to") == "2026-05-01"
        assert data.get("total_sales") == 1500.00
        print("✓ Single day entry (same dates) creates is_single_day=true")
    
    def test_multi_day_range_different_dates(self):
        """POST /api/sales with date_from!=date_to creates is_single_day=false"""
        payload = {
            "date_from": "2026-05-01",
            "date_to": "2026-05-07",
            "total_sales": 8500.00,
            "items": []
        }
        response = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        self.created_sale_ids.append(data["id"])
        
        # Verify is_single_day is False
        assert data.get("is_single_day") == False, f"Expected is_single_day=False, got {data.get('is_single_day')}"
        assert data.get("date_from") == "2026-05-01"
        assert data.get("date_to") == "2026-05-07"
        assert data.get("total_sales") == 8500.00
        print("✓ Multi-day range (different dates) creates is_single_day=false")
    
    def test_date_validation_to_before_from_returns_400(self):
        """POST /api/sales with date_to before date_from returns 400 error"""
        payload = {
            "date_from": "2026-05-10",
            "date_to": "2026-05-05",  # Earlier than date_from - should fail
            "total_sales": 2000.00,
            "items": []
        }
        response = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        # Verify error message
        data = response.json()
        error_msg = data.get("detail", "")
        assert "To Date cannot be earlier than From Date" in error_msg, f"Expected specific error message, got: {error_msg}"
        print("✓ To Date before From Date returns 400 with correct error message")
    
    def test_backward_compatibility_report_date_only(self):
        """POST /api/sales with only report_date (backward compat) sets date_from=date_to=report_date"""
        payload = {
            "report_date": "2026-05-15",
            "total_sales": 3000.00,
            "items": []
        }
        response = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        self.created_sale_ids.append(data["id"])
        
        # Verify backward compatibility behavior
        assert data.get("is_single_day") == True, f"Expected is_single_day=True for legacy data, got {data.get('is_single_day')}"
        assert data.get("date_from") == "2026-05-15", f"Expected date_from=2026-05-15, got {data.get('date_from')}"
        assert data.get("date_to") == "2026-05-15", f"Expected date_to=2026-05-15, got {data.get('date_to')}"
        assert data.get("report_date") == "2026-05-15"
        print("✓ Backward compatibility: report_date only sets date_from=date_to=report_date, is_single_day=true")
    
    def test_get_sales_returns_date_fields(self):
        """GET /api/sales returns records with date_from, date_to, is_single_day fields"""
        # First create a sale
        payload = {
            "date_from": "2026-05-20",
            "date_to": "2026-05-22",
            "total_sales": 5000.00,
            "items": []
        }
        create_res = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert create_res.status_code in [200, 201]
        created = create_res.json()
        self.created_sale_ids.append(created["id"])
        
        # Get sales list
        response = self.client.get(f"{BASE_URL}/api/sales")
        assert response.status_code == 200
        
        sales_list = response.json()
        assert isinstance(sales_list, list)
        
        # Find our created sale
        found_sale = next((s for s in sales_list if s.get("id") == created["id"]), None)
        assert found_sale is not None, "Created sale not found in list"
        
        # Verify fields exist
        assert "date_from" in found_sale
        assert "date_to" in found_sale
        assert "is_single_day" in found_sale
        print("✓ GET /api/sales returns records with date_from, date_to, is_single_day fields")
    
    def test_get_single_sale_returns_date_fields(self):
        """GET /api/sales/{id} returns date_from, date_to, is_single_day fields"""
        # Create a sale first
        payload = {
            "date_from": "2026-06-01",
            "date_to": "2026-06-01",
            "total_sales": 2500.00,
            "items": []
        }
        create_res = self.client.post(f"{BASE_URL}/api/sales", json=payload)
        assert create_res.status_code in [200, 201]
        created = create_res.json()
        self.created_sale_ids.append(created["id"])
        
        # Get single sale
        response = self.client.get(f"{BASE_URL}/api/sales/{created['id']}")
        assert response.status_code == 200
        
        sale = response.json()
        assert sale.get("date_from") == "2026-06-01"
        assert sale.get("date_to") == "2026-06-01"
        assert sale.get("is_single_day") == True
        print("✓ GET /api/sales/{id} returns correct date fields")


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
