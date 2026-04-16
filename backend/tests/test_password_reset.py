"""
Password Reset Flow Tests
=========================
Tests for:
- Forgot password endpoint (manager-only, rate limiting, generic responses)
- Token verification endpoint
- Password reset endpoint (validation, token invalidation)
- Login verification after reset

NOTE: Rate limit is 3 requests per email per hour. Tests are structured to minimize token usage.
"""
import pytest
import requests
import os
import time
import subprocess
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MANAGER_EMAIL = "demo@test.com"
MANAGER_PASSWORD = "testpassword"
CASHIER_EMAIL = "cashier@test.com"
CASHIER_PASSWORD = "testpass123"
UNKNOWN_EMAIL = "nonexistent@test.com"


def get_latest_token_from_logs():
    """Extract the most recent reset token from backend logs."""
    try:
        result = subprocess.run(
            ["tail", "-100", "/var/log/supervisor/backend.err.log"],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stderr if result.stderr else result.stdout
        # Find all tokens and return the last one
        tokens = re.findall(r'token=([a-f0-9]{64})', output)
        if tokens:
            return tokens[-1]  # Return the most recent token
        return None
    except Exception as e:
        print(f"Error extracting token: {e}")
        return None


def request_reset_and_get_token(email):
    """Request a password reset and return the token from logs."""
    # Get current token count before request
    result = subprocess.run(
        ["tail", "-100", "/var/log/supervisor/backend.err.log"],
        capture_output=True,
        text=True,
        timeout=5
    )
    output_before = result.stderr if result.stderr else result.stdout
    tokens_before = re.findall(r'token=([a-f0-9]{64})', output_before)
    
    # Make the request
    response = requests.post(
        f"{BASE_URL}/api/auth/forgot-password",
        json={"email": email}
    )
    
    # Wait for log to be written
    time.sleep(1)
    
    # Get tokens after request
    result = subprocess.run(
        ["tail", "-100", "/var/log/supervisor/backend.err.log"],
        capture_output=True,
        text=True,
        timeout=5
    )
    output_after = result.stderr if result.stderr else result.stdout
    tokens_after = re.findall(r'token=([a-f0-9]{64})', output_after)
    
    # Find new token (if any)
    new_tokens = [t for t in tokens_after if t not in tokens_before]
    
    return response, new_tokens[-1] if new_tokens else None


def clear_rate_limit_tokens():
    """Clear all password reset tokens from database to reset rate limit."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    
    async def _clear():
        client = AsyncIOMotorClient('mongodb://localhost:27017')
        db = client['test_database']
        result = await db.password_reset_tokens.delete_many({})
        client.close()
        return result.deleted_count
    
    return asyncio.run(_clear())


class TestForgotPasswordEndpoint:
    """Tests for POST /api/auth/forgot-password - No tokens consumed"""
    
    def test_manager_email_returns_generic_success(self):
        """Manager email should return generic success message"""
        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": MANAGER_EMAIL}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "If the account is eligible, a reset link has been sent."
        print(f"PASS: Manager email returns generic success: {data['message']}")
    
    def test_cashier_email_returns_same_generic_message(self):
        """Non-manager (cashier) should get same generic message (no token created)"""
        response, token = request_reset_and_get_token(CASHIER_EMAIL)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "If the account is eligible, a reset link has been sent."
        # Cashier should NOT get a token
        assert token is None, "Cashier should not receive a reset token"
        print(f"PASS: Cashier email returns same generic message, no token created")
    
    def test_unknown_email_returns_same_generic_message(self):
        """Unknown email should get same generic message"""
        response, token = request_reset_and_get_token(UNKNOWN_EMAIL)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "If the account is eligible, a reset link has been sent."
        # Unknown email should NOT get a token
        assert token is None, "Unknown email should not receive a reset token"
        print(f"PASS: Unknown email returns same generic message, no token created")


class TestVerifyResetToken:
    """Tests for GET /api/auth/verify-reset-token"""
    
    def test_invalid_token_returns_valid_false(self):
        """Invalid token should return {valid: false, reason: invalid}"""
        response = requests.get(
            f"{BASE_URL}/api/auth/verify-reset-token",
            params={"token": "invalid_token_12345"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == False
        assert data.get("reason") == "invalid"
        print(f"PASS: Invalid token returns valid=false, reason=invalid")


class TestFullPasswordResetFlow:
    """
    Comprehensive test of the full password reset flow.
    Uses a single token to test: verify, short password rejection, successful reset, 
    token invalidation, login with new password, login with old password fails.
    Then restores original password.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear rate limit before running these tests"""
        deleted = clear_rate_limit_tokens()
        print(f"Cleared {deleted} tokens before test")
    
    def test_full_password_reset_flow(self):
        """
        Complete flow test:
        1. Request reset token for manager
        2. Verify token is valid
        3. Try reset with short password (should fail)
        4. Reset with valid password (should succeed)
        5. Verify token is now invalid
        6. Login with new password (should work)
        7. Login with old password (should fail)
        8. Restore original password
        """
        # Step 1: Request reset token
        response, token = request_reset_and_get_token(MANAGER_EMAIL)
        assert response.status_code == 200
        assert token is not None, "Token should be created for manager"
        assert len(token) == 64, "Token should be 64-char hex"
        print(f"Step 1 PASS: Token created for manager: {token[:16]}...")
        
        # Step 2: Verify token is valid
        verify_response = requests.get(
            f"{BASE_URL}/api/auth/verify-reset-token",
            params={"token": token}
        )
        assert verify_response.status_code == 200
        assert verify_response.json().get("valid") == True
        print(f"Step 2 PASS: Token verified as valid")
        
        # Step 3: Try reset with short password
        short_pw_response = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={"token": token, "new_password": "12345"}  # 5 chars
        )
        assert short_pw_response.status_code == 400
        assert "6 characters" in short_pw_response.json().get("detail", "")
        print(f"Step 3 PASS: Short password rejected: {short_pw_response.json().get('detail')}")
        
        # Step 4: Reset with valid password
        new_password = "newpassword123"
        reset_response = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={"token": token, "new_password": new_password}
        )
        assert reset_response.status_code == 200
        assert "successfully" in reset_response.json().get("message", "").lower()
        print(f"Step 4 PASS: Password reset successful")
        
        # Step 5: Verify token is now invalid
        verify_after = requests.get(
            f"{BASE_URL}/api/auth/verify-reset-token",
            params={"token": token}
        )
        assert verify_after.status_code == 200
        assert verify_after.json().get("valid") == False
        print(f"Step 5 PASS: Token invalidated after use")
        
        # Step 6: Login with new password
        login_new = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": MANAGER_EMAIL, "password": new_password}
        )
        assert login_new.status_code == 200
        assert "token" in login_new.json()
        print(f"Step 6 PASS: Login with new password works")
        
        # Step 7: Login with old password should fail
        login_old = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD}
        )
        assert login_old.status_code == 401
        print(f"Step 7 PASS: Login with old password fails (401)")
        
        # Step 8: Restore original password
        # Need a new token for this
        restore_response, restore_token = request_reset_and_get_token(MANAGER_EMAIL)
        assert restore_token is not None, "Need token to restore password"
        
        restore_reset = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={"token": restore_token, "new_password": MANAGER_PASSWORD}
        )
        assert restore_reset.status_code == 200
        
        # Verify original password works
        login_restored = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD}
        )
        assert login_restored.status_code == 200
        print(f"Step 8 PASS: Original password restored and verified")
        
        print("\n=== ALL STEPS PASSED ===")


class TestRateLimiting:
    """Test rate limiting behavior (3 requests per hour per email)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear rate limit before running these tests"""
        deleted = clear_rate_limit_tokens()
        print(f"Cleared {deleted} tokens before rate limit test")
    
    def test_rate_limiting_after_3_requests(self):
        """4th request within 1 hour should still return generic message but no new token"""
        # Make 3 requests (should all create tokens)
        tokens = []
        for i in range(3):
            response, token = request_reset_and_get_token(MANAGER_EMAIL)
            assert response.status_code == 200
            assert token is not None, f"Request {i+1} should create a token"
            tokens.append(token)
            print(f"Request {i+1}: Token created")
        
        # 4th request should return same message but no new token
        response, token = request_reset_and_get_token(MANAGER_EMAIL)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "If the account is eligible, a reset link has been sent."
        assert token is None, "4th request should NOT create a new token (rate limited)"
        print(f"Request 4: Rate limited - same message, no new token")
        
        print("PASS: Rate limiting works correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
