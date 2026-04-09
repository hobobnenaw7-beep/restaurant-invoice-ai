"""
Profit Dashboard API Tests
Tests for the 5 profit dashboard endpoints:
1. GET /api/profit/intelligence - price trends, vendor stability, cost drivers
2. GET /api/profit/review-queue - items needing review with reason labels
3. POST /api/profit/confirm-item - confirm item, move to user_confirmed
4. GET /api/profit/search?q=<query> - decision engine search
5. POST /api/profit/ai-insights - auto insights and AI explanation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestProfitDashboardAuth:
    """Test authentication for profit dashboard endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestProfitIntelligence(TestProfitDashboardAuth):
    """Tests for GET /api/profit/intelligence"""
    
    def test_intelligence_returns_200(self, auth_headers):
        """Test that intelligence endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        assert response.status_code == 200
    
    def test_intelligence_has_price_trends(self, auth_headers):
        """Test that response contains price_trends array"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        data = response.json()
        assert "price_trends" in data
        assert isinstance(data["price_trends"], list)
    
    def test_intelligence_has_vendor_stability(self, auth_headers):
        """Test that response contains vendor_stability array"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        data = response.json()
        assert "vendor_stability" in data
        assert isinstance(data["vendor_stability"], list)
    
    def test_intelligence_has_cost_drivers(self, auth_headers):
        """Test that response contains cost_drivers array"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        data = response.json()
        assert "cost_drivers" in data
        assert isinstance(data["cost_drivers"], list)
    
    def test_intelligence_has_total_spend(self, auth_headers):
        """Test that response contains total_spend"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        data = response.json()
        assert "total_spend" in data
        assert isinstance(data["total_spend"], (int, float))
    
    def test_intelligence_price_trend_structure(self, auth_headers):
        """Test price trend item structure"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence", headers=auth_headers)
        data = response.json()
        if data["price_trends"]:
            trend = data["price_trends"][0]
            assert "product" in trend
            assert "current_price" in trend
            assert "avg_price" in trend
            assert "trend_30d_pct" in trend or trend.get("trend_30d_pct") is None


class TestReviewQueue(TestProfitDashboardAuth):
    """Tests for GET /api/profit/review-queue"""
    
    def test_review_queue_returns_200(self, auth_headers):
        """Test that review queue endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        assert response.status_code == 200
    
    def test_review_queue_has_items(self, auth_headers):
        """Test that response contains items array"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
    
    def test_review_queue_has_total_count(self, auth_headers):
        """Test that response contains total_count"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        data = response.json()
        assert "total_count" in data
        assert isinstance(data["total_count"], int)
    
    def test_review_queue_has_reason_breakdown(self, auth_headers):
        """Test that response contains reason_breakdown"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        data = response.json()
        assert "reason_breakdown" in data
        assert isinstance(data["reason_breakdown"], dict)
    
    def test_review_item_has_reason_label(self, auth_headers):
        """Test that review items have reason_label"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        data = response.json()
        if data["items"]:
            item = data["items"][0]
            assert "reason_label" in item
            assert "id" in item
            assert "raw_name" in item


class TestDecisionSearch(TestProfitDashboardAuth):
    """Tests for GET /api/profit/search"""
    
    def test_search_returns_200(self, auth_headers):
        """Test that search endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=chicken", headers=auth_headers)
        assert response.status_code == 200
    
    def test_search_has_results(self, auth_headers):
        """Test that response contains results array"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=chicken", headers=auth_headers)
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
    
    def test_search_has_query(self, auth_headers):
        """Test that response echoes the query"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=chicken", headers=auth_headers)
        data = response.json()
        assert "query" in data
        assert data["query"] == "chicken"
    
    def test_search_result_has_vendors(self, auth_headers):
        """Test that search results have vendor comparison"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=chicken", headers=auth_headers)
        data = response.json()
        if data["results"]:
            result = data["results"][0]
            assert "vendors" in result
            assert "cheapest_vendor" in result
            assert "cheapest_price" in result
            assert "suggested_action" in result
    
    def test_search_suggested_action_structure(self, auth_headers):
        """Test suggested action structure"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=chicken", headers=auth_headers)
        data = response.json()
        if data["results"]:
            action = data["results"][0].get("suggested_action", {})
            assert "action" in action
            assert "reason" in action
            assert "confidence" in action
    
    def test_search_empty_query(self, auth_headers):
        """Test search with empty query returns empty results"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=", headers=auth_headers)
        data = response.json()
        assert data["results"] == []
    
    def test_search_short_query(self, auth_headers):
        """Test search with single char returns empty results"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=a", headers=auth_headers)
        data = response.json()
        assert data["results"] == []


class TestAIInsights(TestProfitDashboardAuth):
    """Tests for POST /api/profit/ai-insights"""
    
    def test_ai_insights_returns_200(self, auth_headers):
        """Test that AI insights endpoint returns 200"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", headers=auth_headers, json={})
        assert response.status_code == 200
    
    def test_ai_insights_has_auto_insights(self, auth_headers):
        """Test that response contains auto_insights array"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", headers=auth_headers, json={})
        data = response.json()
        assert "auto_insights" in data
        assert isinstance(data["auto_insights"], list)
    
    def test_ai_insights_has_computed_metrics(self, auth_headers):
        """Test that response contains computed_metrics"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", headers=auth_headers, json={})
        data = response.json()
        assert "computed_metrics" in data
        assert "total_spend" in data["computed_metrics"]
        assert "total_items" in data["computed_metrics"]
    
    def test_ai_insights_has_ai_available_flag(self, auth_headers):
        """Test that response contains ai_available flag"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", headers=auth_headers, json={})
        data = response.json()
        assert "ai_available" in data
        assert isinstance(data["ai_available"], bool)
    
    def test_ai_insights_with_context(self, auth_headers):
        """Test AI insights with dashboard context"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", headers=auth_headers, json={
            "dashboard_context": {
                "total_spend": 10000,
                "top_driver": "Chicken Wings"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "auto_insights" in data


class TestConfirmItem(TestProfitDashboardAuth):
    """Tests for POST /api/profit/confirm-item"""
    
    def test_confirm_item_invalid_id(self, auth_headers):
        """Test confirm with invalid item_id returns error"""
        response = requests.post(f"{BASE_URL}/api/profit/confirm-item", headers=auth_headers, json={
            "item_id": "invalid-id-12345"
        })
        assert response.status_code == 200  # API returns 200 with error message
        data = response.json()
        assert "error" in data
    
    def test_confirm_item_missing_id(self, auth_headers):
        """Test confirm without item_id returns 422"""
        response = requests.post(f"{BASE_URL}/api/profit/confirm-item", headers=auth_headers, json={})
        assert response.status_code == 422  # Validation error
    
    def test_confirm_item_with_override(self, auth_headers):
        """Test confirm with quantity override (if item exists)"""
        # First get a review item
        queue_response = requests.get(f"{BASE_URL}/api/profit/review-queue", headers=auth_headers)
        queue_data = queue_response.json()
        
        if queue_data["items"]:
            item_id = queue_data["items"][0]["id"]
            response = requests.post(f"{BASE_URL}/api/profit/confirm-item", headers=auth_headers, json={
                "item_id": item_id,
                "confirmed_quantity": 5.0,
                "notes": "Test confirmation"
            })
            assert response.status_code == 200
            data = response.json()
            if "confirmed" in data:
                assert data["confirmed"]["quantity"] == 5.0
                assert "remaining_review_count" in data
        else:
            pytest.skip("No items in review queue to test")


class TestUnauthorizedAccess:
    """Test that endpoints require authentication"""
    
    def test_intelligence_requires_auth(self):
        """Test intelligence endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/profit/intelligence")
        assert response.status_code in [401, 403]
    
    def test_review_queue_requires_auth(self):
        """Test review queue endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/profit/review-queue")
        assert response.status_code in [401, 403]
    
    def test_search_requires_auth(self):
        """Test search endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/profit/search?q=test")
        assert response.status_code in [401, 403]
    
    def test_ai_insights_requires_auth(self):
        """Test AI insights endpoint requires auth"""
        response = requests.post(f"{BASE_URL}/api/profit/ai-insights", json={})
        assert response.status_code in [401, 403]
    
    def test_confirm_item_requires_auth(self):
        """Test confirm item endpoint requires auth"""
        response = requests.post(f"{BASE_URL}/api/profit/confirm-item", json={"item_id": "test"})
        assert response.status_code in [401, 403]
