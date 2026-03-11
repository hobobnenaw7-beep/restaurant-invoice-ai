"""
Test suite for Chat Assistant API endpoints
Testing: /api/chat, /api/chat/messages, DELETE /api/chat/messages
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test@demo.com"
TEST_PASSWORD = "password123"


class TestChatAPI:
    """Tests for chat assistant endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test by getting auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        self.token = data["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        # Cleanup: Clear chat messages after each test
        self.session.delete(f"{BASE_URL}/api/chat/messages")

    def test_auth_login_works(self):
        """Test that login endpoint returns valid token and user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", 
            headers={"Content-Type": "application/json"},
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        print(f"✓ Login successful for {TEST_EMAIL}")

    def test_get_chat_messages_empty(self):
        """Test GET /api/chat/messages returns empty list initially"""
        # Clear first
        self.session.delete(f"{BASE_URL}/api/chat/messages")
        
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/chat/messages returned {len(data)} messages")

    def test_post_chat_message(self):
        """Test POST /api/chat sends message and gets AI response"""
        test_message = "What's my spending this week?"
        
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": test_message
        }, timeout=60)  # Longer timeout for AI response
        
        assert response.status_code == 200, f"Chat POST failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "user_message" in data, "Response should contain user_message"
        assert "assistant_message" in data, "Response should contain assistant_message"
        
        # Verify user message
        user_msg = data["user_message"]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == test_message
        assert "id" in user_msg
        assert "created_at" in user_msg
        
        # Verify assistant message
        asst_msg = data["assistant_message"]
        assert asst_msg["role"] == "assistant"
        assert len(asst_msg["content"]) > 0, "Assistant should return non-empty response"
        assert "id" in asst_msg
        assert "created_at" in asst_msg
        
        print(f"✓ Chat message sent and received AI response")
        print(f"  User: {test_message[:50]}...")
        print(f"  AI: {asst_msg['content'][:100]}...")

    def test_chat_messages_persist(self):
        """Test that chat messages are persisted and can be retrieved"""
        # Send a message
        test_message = "TEST_Show my top expenses"
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": test_message
        }, timeout=60)
        assert response.status_code == 200
        
        # Retrieve messages
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        messages = response.json()
        
        assert len(messages) >= 2, "Should have at least user and assistant messages"
        
        # Find user message
        user_msgs = [m for m in messages if m["role"] == "user" and test_message in m["content"]]
        assert len(user_msgs) > 0, "User message should be persisted"
        
        # Find assistant message
        asst_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(asst_msgs) > 0, "Assistant message should be persisted"
        
        print(f"✓ Messages persisted correctly ({len(messages)} messages)")

    def test_delete_chat_messages(self):
        """Test DELETE /api/chat/messages clears all messages"""
        # First send a message
        self.session.post(f"{BASE_URL}/api/chat", json={
            "message": "TEST_Hello"
        }, timeout=60)
        
        # Verify message exists
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        initial_count = len(response.json())
        assert initial_count > 0, "Should have messages before clearing"
        
        # Delete all messages
        response = self.session.delete(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "cleared", "Should return cleared status"
        
        # Verify messages are gone
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 0, "Messages should be cleared"
        
        print(f"✓ Chat messages cleared successfully (was {initial_count}, now 0)")

    def test_chat_without_auth_fails(self):
        """Test that chat endpoints require authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        unauth_session.headers.update({"Content-Type": "application/json"})
        
        # Try to get messages without auth
        response = unauth_session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 401, "Should return 401 without auth"
        
        # Try to send chat without auth
        response = unauth_session.post(f"{BASE_URL}/api/chat", json={"message": "test"})
        assert response.status_code == 401, "Should return 401 without auth"
        
        print("✓ Chat endpoints properly require authentication")

    def test_chat_ai_response_contains_financial_data(self):
        """Test that AI response contains financial data/numbers"""
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": "What's my year-to-date profit?"
        }, timeout=60)
        
        assert response.status_code == 200
        data = response.json()
        content = data["assistant_message"]["content"]
        
        # Check for dollar signs or numbers (indicating financial data)
        has_dollar = "$" in content
        has_numbers = any(char.isdigit() for char in content)
        
        assert has_dollar or has_numbers, "AI response should contain financial data"
        print(f"✓ AI response contains financial data: {content[:150]}...")


class TestChatEdgeCases:
    """Edge case tests for chat functionality"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test by getting auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.delete(f"{BASE_URL}/api/chat/messages")

    def test_empty_message_handled(self):
        """Test that empty message is handled gracefully"""
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": ""
        }, timeout=60)
        
        # Should either reject or handle gracefully
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"
        print(f"✓ Empty message handled with status {response.status_code}")

    def test_long_message_handled(self):
        """Test that long messages are handled"""
        long_message = "Tell me about my expenses. " * 100
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": long_message
        }, timeout=90)
        
        # Should handle long messages
        assert response.status_code in [200, 400], f"Long message failed: {response.status_code}"
        print(f"✓ Long message handled with status {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
