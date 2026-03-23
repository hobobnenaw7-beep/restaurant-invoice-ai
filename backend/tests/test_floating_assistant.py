"""
Test suite for Floating AI Assistant - Chat API endpoints
Tests: POST /api/chat, GET /api/chat/messages, DELETE /api/chat/messages
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestChatEndpoints:
    """Chat API endpoint tests for Floating AI Assistant"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test credentials and get auth token"""
        self.email = "demo@test.com"
        self.password = "testpassword"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.email,
            "password": self.password
        })
        if login_response.status_code == 200:
            token = login_response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.authenticated = True
        else:
            self.authenticated = False
            pytest.skip("Authentication failed - skipping authenticated tests")
    
    # ==================== Authentication Tests ====================
    
    def test_chat_requires_auth(self):
        """POST /api/chat returns 401 without authentication"""
        unauthenticated_session = requests.Session()
        unauthenticated_session.headers.update({"Content-Type": "application/json"})
        
        response = unauthenticated_session.post(f"{BASE_URL}/api/chat", json={
            "message": "Test message"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/chat returns 401 without authentication")
    
    def test_get_messages_requires_auth(self):
        """GET /api/chat/messages returns 401 without authentication"""
        unauthenticated_session = requests.Session()
        response = unauthenticated_session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /api/chat/messages returns 401 without authentication")
    
    def test_delete_messages_requires_auth(self):
        """DELETE /api/chat/messages returns 401 without authentication"""
        unauthenticated_session = requests.Session()
        response = unauthenticated_session.delete(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: DELETE /api/chat/messages returns 401 without authentication")
    
    # ==================== GET /api/chat/messages Tests ====================
    
    def test_get_chat_messages_returns_array(self):
        """GET /api/chat/messages returns an array"""
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: GET /api/chat/messages returns array with {len(data)} messages")
    
    # ==================== DELETE /api/chat/messages Tests ====================
    
    def test_clear_chat_messages(self):
        """DELETE /api/chat/messages clears chat history"""
        response = self.session.delete(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "cleared", f"Expected status 'cleared', got {data}"
        
        # Verify messages are cleared
        get_response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert get_response.status_code == 200
        messages = get_response.json()
        assert len(messages) == 0, f"Expected 0 messages after clear, got {len(messages)}"
        print("PASS: DELETE /api/chat/messages clears chat history")
    
    # ==================== POST /api/chat Tests ====================
    
    def test_chat_where_should_i_buy_today(self):
        """POST /api/chat with 'Where should I buy today?' returns AI response"""
        # Clear chat first
        self.session.delete(f"{BASE_URL}/api/chat/messages")
        
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": "Where should I buy today?"
        }, timeout=60)  # LLM calls can take time
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "user_message" in data, "Response missing 'user_message'"
        assert "assistant_message" in data, "Response missing 'assistant_message'"
        
        user_msg = data["user_message"]
        asst_msg = data["assistant_message"]
        
        # Verify user message structure
        assert user_msg.get("id"), "User message missing 'id'"
        assert user_msg.get("role") == "user", f"Expected role 'user', got {user_msg.get('role')}"
        assert user_msg.get("content") == "Where should I buy today?", "User message content mismatch"
        assert user_msg.get("created_at"), "User message missing 'created_at'"
        
        # Verify assistant message structure
        assert asst_msg.get("id"), "Assistant message missing 'id'"
        assert asst_msg.get("role") == "assistant", f"Expected role 'assistant', got {asst_msg.get('role')}"
        assert asst_msg.get("content"), "Assistant message missing 'content'"
        assert asst_msg.get("created_at"), "Assistant message missing 'created_at'"
        
        # Verify AI generated actual content (not placeholder)
        content = asst_msg.get("content", "")
        assert len(content) > 20, f"AI response too short: {len(content)} chars"
        assert "placeholder" not in content.lower(), "Response contains placeholder text"
        assert "mock" not in content.lower(), "Response contains mock text"
        
        print(f"PASS: POST /api/chat 'Where should I buy today?' - AI response: {content[:100]}...")
    
    def test_chat_price_increases_this_week(self):
        """POST /api/chat with 'What prices increased this week?' returns relevant data"""
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": "What prices increased this week?"
        }, timeout=60)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "user_message" in data, "Response missing 'user_message'"
        assert "assistant_message" in data, "Response missing 'assistant_message'"
        
        asst_msg = data["assistant_message"]
        content = asst_msg.get("content", "")
        
        # Verify AI generated actual content
        assert len(content) > 20, f"AI response too short: {len(content)} chars"
        
        print(f"PASS: POST /api/chat 'What prices increased this week?' - AI response: {content[:100]}...")
    
    def test_chat_find_cheapest_supplier(self):
        """POST /api/chat with 'Find cheapest supplier for salmon' returns relevant data"""
        response = self.session.post(f"{BASE_URL}/api/chat", json={
            "message": "Find cheapest supplier for salmon"
        }, timeout=60)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "user_message" in data, "Response missing 'user_message'"
        assert "assistant_message" in data, "Response missing 'assistant_message'"
        
        asst_msg = data["assistant_message"]
        content = asst_msg.get("content", "")
        
        # Verify AI generated actual content
        assert len(content) > 20, f"AI response too short: {len(content)} chars"
        
        print(f"PASS: POST /api/chat 'Find cheapest supplier for salmon' - AI response: {content[:100]}...")
    
    def test_chat_messages_persist(self):
        """Verify chat messages are persisted and retrievable"""
        # Get messages after previous tests
        response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert response.status_code == 200
        messages = response.json()
        
        # Should have messages from previous tests
        assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"
        
        # Verify message structure
        for msg in messages:
            assert "id" in msg, "Message missing 'id'"
            assert "role" in msg, "Message missing 'role'"
            assert "content" in msg, "Message missing 'content'"
            assert msg["role"] in ["user", "assistant"], f"Invalid role: {msg['role']}"
        
        print(f"PASS: Chat messages persist - found {len(messages)} messages")
    
    def test_clear_and_verify_empty(self):
        """Clear chat and verify empty state"""
        # Clear
        clear_response = self.session.delete(f"{BASE_URL}/api/chat/messages")
        assert clear_response.status_code == 200
        
        # Verify empty
        get_response = self.session.get(f"{BASE_URL}/api/chat/messages")
        assert get_response.status_code == 200
        messages = get_response.json()
        assert len(messages) == 0, f"Expected 0 messages, got {len(messages)}"
        
        print("PASS: Clear chat and verify empty state")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
