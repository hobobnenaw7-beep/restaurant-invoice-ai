"""
Backend API tests for Smart Alerts feature on Dashboard
Tests: /api/dashboard/summary - smart_alerts array, /api/chat - alerts context
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSmartAlerts:
    """Test Smart Alerts in Dashboard API"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_dashboard_returns_smart_alerts_array(self, headers):
        """Dashboard API should return smart_alerts as an array"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify smart_alerts field exists and is a list
        assert "smart_alerts" in data, "smart_alerts field missing from dashboard response"
        assert isinstance(data["smart_alerts"], list), "smart_alerts should be an array"
    
    def test_smart_alerts_have_required_fields(self, headers):
        """Each smart alert should have type, severity, title, detail"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        if len(smart_alerts) == 0:
            pytest.skip("No smart alerts present - demo data may not have triggering conditions")
        
        for i, alert in enumerate(smart_alerts):
            assert "type" in alert, f"Alert {i} missing 'type' field"
            assert "severity" in alert, f"Alert {i} missing 'severity' field"
            assert "title" in alert, f"Alert {i} missing 'title' field"
            assert "detail" in alert, f"Alert {i} missing 'detail' field"
    
    def test_smart_alert_types_are_valid(self, headers):
        """Smart alert types should be: low_stock, cost_increase, or margin_drop"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        valid_types = {"low_stock", "cost_increase", "margin_drop"}
        
        for alert in smart_alerts:
            assert alert["type"] in valid_types, f"Invalid alert type: {alert['type']}"
    
    def test_smart_alert_severity_values(self, headers):
        """Smart alert severity should be 'high' or 'medium'"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        valid_severities = {"high", "medium"}
        
        for alert in smart_alerts:
            assert alert["severity"] in valid_severities, f"Invalid severity: {alert['severity']}"
    
    def test_cost_increase_alert_has_price_fields(self, headers):
        """cost_increase alerts should have old_price, new_price, change_pct"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        cost_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "cost_increase"]
        if not cost_alerts:
            pytest.skip("No cost_increase alerts to test")
        
        for alert in cost_alerts:
            assert "old_price" in alert, "cost_increase alert missing old_price"
            assert "new_price" in alert, "cost_increase alert missing new_price"
            assert "change_pct" in alert, "cost_increase alert missing change_pct"
            assert "item" in alert, "cost_increase alert missing item name"
            # Verify change_pct > 5 (threshold)
            assert alert["change_pct"] > 5, f"change_pct should be >5%, got {alert['change_pct']}"
    
    def test_margin_drop_alert_has_margin_fields(self, headers):
        """margin_drop alerts should have current_margin, previous_margin, drop_pp"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        margin_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "margin_drop"]
        if not margin_alerts:
            pytest.skip("No margin_drop alerts to test")
        
        for alert in margin_alerts:
            assert "current_margin" in alert, "margin_drop alert missing current_margin"
            assert "previous_margin" in alert, "margin_drop alert missing previous_margin"
            assert "drop_pp" in alert, "margin_drop alert missing drop_pp"
            # Verify drop_pp > 3 (threshold)
            assert alert["drop_pp"] > 3, f"drop_pp should be >3pp, got {alert['drop_pp']}"
    
    def test_dashboard_still_returns_kpi_data(self, headers):
        """Dashboard should still return all KPI fields alongside smart_alerts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify core KPI fields exist
        required_fields = [
            "today_sales", "today_purchases",
            "week_sales", "week_purchases",
            "month_sales", "month_purchases",
            "prev_week_sales", "prev_week_purchases",
            "prev_month_sales", "prev_month_purchases",
            "top_items", "top_suppliers", "weekly_trends"
        ]
        for field in required_fields:
            assert field in data, f"Missing KPI field: {field}"
    
    def test_dashboard_weekly_trends_data(self, headers):
        """Weekly trends should have proper structure for charts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        trends = data.get("weekly_trends", [])
        assert len(trends) > 0, "weekly_trends should not be empty"
        
        for trend in trends:
            assert "week" in trend, "Weekly trend missing 'week' field"
            assert "purchases" in trend, "Weekly trend missing 'purchases' field"
            assert "sales" in trend, "Weekly trend missing 'sales' field"


class TestChatWithSmartAlerts:
    """Test Chat API includes smart alerts context"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_chat_responds_to_cost_question(self, headers):
        """Chat should respond to questions about cost increases"""
        response = requests.post(f"{BASE_URL}/api/chat", headers=headers, json={
            "message": "Which items have increased in price recently?"
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        assert "assistant_message" in data, "Chat response missing assistant_message"
        assert "content" in data["assistant_message"], "Assistant message missing content"
        
        # Response should mention price or cost increases
        content = data["assistant_message"]["content"].lower()
        assert any(word in content for word in ["price", "cost", "increase", "up", "$", "salmon", "beef", "flour"]), \
            f"Chat response doesn't seem to address cost increases: {content[:200]}"
    
    def test_chat_responds_to_margin_question(self, headers):
        """Chat should respond to questions about profit margins"""
        response = requests.post(f"{BASE_URL}/api/chat", headers=headers, json={
            "message": "How is my profit margin this week vs last week?"
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        assert "assistant_message" in data
        content = data["assistant_message"]["content"].lower()
        
        # Should mention margin or profit in response
        assert any(word in content for word in ["margin", "profit", "%", "week"]), \
            f"Chat response doesn't seem to address margins: {content[:200]}"
    
    def test_chat_returns_proper_structure(self, headers):
        """Chat API should return user_message and assistant_message"""
        response = requests.post(f"{BASE_URL}/api/chat", headers=headers, json={
            "message": "What are my current alerts?"
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        assert "user_message" in data
        assert "assistant_message" in data
        
        # Verify message structure
        user_msg = data["user_message"]
        assert "id" in user_msg
        assert "role" in user_msg
        assert user_msg["role"] == "user"
        assert "content" in user_msg
        
        asst_msg = data["assistant_message"]
        assert "id" in asst_msg
        assert "role" in asst_msg
        assert asst_msg["role"] == "assistant"
        assert "content" in asst_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
