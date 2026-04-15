"""
Test Reset All Data endpoint security
- Manager role enforcement
- Password verification
- RESET confirmation word validation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
MANAGER_EMAIL = "demo@test.com"
MANAGER_PASSWORD = "testpassword"
ACCOUNTANT_EMAIL = "accountant@test.com"
ACCOUNTANT_PASSWORD = "testpass123"
CASHIER_EMAIL = "cashier@test.com"
CASHIER_PASSWORD = "testpass123"
STAFF_EMAIL = "staff@test.com"
STAFF_PASSWORD = "testpass123"


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def get_auth_token(api_client, email, password):
    """Helper to get auth token for a user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": password
    })
    if response.status_code == 200:
        return response.json().get("token")
    return None


class TestResetDataSecurity:
    """Test Reset All Data endpoint security features"""
    
    def test_non_manager_rejected_accountant(self, api_client):
        """Accountant role should be rejected with 403 'Manager access required'"""
        token = get_auth_token(api_client, ACCOUNTANT_EMAIL, ACCOUNTANT_PASSWORD)
        assert token is not None, "Failed to get accountant token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": ACCOUNTANT_PASSWORD,
            "confirmation": "RESET"
        })
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Manager access required" in data.get("detail", ""), f"Expected 'Manager access required', got {data}"
        print(f"PASS: Accountant rejected with 403 - {data.get('detail')}")
    
    def test_non_manager_rejected_cashier(self, api_client):
        """Cashier role should be rejected with 403 'Manager access required'"""
        token = get_auth_token(api_client, CASHIER_EMAIL, CASHIER_PASSWORD)
        assert token is not None, "Failed to get cashier token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": CASHIER_PASSWORD,
            "confirmation": "RESET"
        })
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Manager access required" in data.get("detail", ""), f"Expected 'Manager access required', got {data}"
        print(f"PASS: Cashier rejected with 403 - {data.get('detail')}")
    
    def test_non_manager_rejected_staff(self, api_client):
        """Staff role should be rejected with 403 'Manager access required'"""
        token = get_auth_token(api_client, STAFF_EMAIL, STAFF_PASSWORD)
        assert token is not None, "Failed to get staff token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": STAFF_PASSWORD,
            "confirmation": "RESET"
        })
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Manager access required" in data.get("detail", ""), f"Expected 'Manager access required', got {data}"
        print(f"PASS: Staff rejected with 403 - {data.get('detail')}")
    
    def test_manager_wrong_password_rejected(self, api_client):
        """Manager with wrong password should be rejected with 403 'Incorrect password'"""
        token = get_auth_token(api_client, MANAGER_EMAIL, MANAGER_PASSWORD)
        assert token is not None, "Failed to get manager token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": "wrongpassword123",
            "confirmation": "RESET"
        })
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Incorrect password" in data.get("detail", ""), f"Expected 'Incorrect password', got {data}"
        print(f"PASS: Manager with wrong password rejected with 403 - {data.get('detail')}")
    
    def test_manager_wrong_confirmation_rejected(self, api_client):
        """Manager with wrong confirmation word should be rejected with 400"""
        token = get_auth_token(api_client, MANAGER_EMAIL, MANAGER_PASSWORD)
        assert token is not None, "Failed to get manager token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": MANAGER_PASSWORD,
            "confirmation": "DELETE"  # Wrong confirmation word
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "RESET" in data.get("detail", ""), f"Expected error about RESET confirmation, got {data}"
        print(f"PASS: Manager with wrong confirmation rejected with 400 - {data.get('detail')}")
    
    def test_manager_empty_password_rejected(self, api_client):
        """Manager with empty password should be rejected"""
        token = get_auth_token(api_client, MANAGER_EMAIL, MANAGER_PASSWORD)
        assert token is not None, "Failed to get manager token"
        
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": "",
            "confirmation": "RESET"
        })
        
        # Empty password should fail verification
        assert response.status_code in [400, 403, 422], f"Expected 400/403/422, got {response.status_code}"
        print(f"PASS: Manager with empty password rejected with {response.status_code}")
    
    def test_unauthenticated_request_rejected(self, api_client):
        """Unauthenticated request should be rejected with 401"""
        # Remove any auth header
        api_client.headers.pop("Authorization", None)
        
        response = api_client.post(f"{BASE_URL}/api/settings/reset-data", json={
            "password": "anypassword",
            "confirmation": "RESET"
        })
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Unauthenticated request rejected with 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
