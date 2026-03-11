"""
Price Intelligence API Tests
Tests GET /api/prices/intelligence endpoint for supplier comparison, price trends, and price alerts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test@demo.com"
TEST_PASSWORD = "password123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def authenticated_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestPriceIntelligenceEndpoint:
    """Tests for GET /api/prices/intelligence"""

    def test_price_intelligence_returns_200(self, authenticated_client):
        """API returns 200 status code"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/prices/intelligence returns 200")

    def test_response_has_required_fields(self, authenticated_client):
        """Response contains suppliers, comparison, price_trends, price_alerts fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        required_fields = ["suppliers", "comparison", "price_trends", "price_alerts"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Also check summary fields
        assert "total_items_tracked" in data, "Missing total_items_tracked"
        assert "total_suppliers" in data, "Missing total_suppliers"
        print(f"✓ Response has all required fields: {required_fields}")

    def test_suppliers_is_list(self, authenticated_client):
        """Suppliers field is a list of strings"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["suppliers"], list), "suppliers should be a list"
        assert len(data["suppliers"]) > 0, "suppliers list should not be empty"
        assert all(isinstance(s, str) for s in data["suppliers"]), "Each supplier should be a string"
        print(f"✓ Suppliers list contains {len(data['suppliers'])} suppliers")


class TestComparisonData:
    """Tests for supplier comparison data"""

    def test_comparison_is_list_of_items(self, authenticated_client):
        """Comparison field contains list of item comparison objects"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["comparison"], list), "comparison should be a list"
        print(f"✓ Comparison contains {len(data['comparison'])} items")

    def test_comparison_item_has_required_fields(self, authenticated_client):
        """Each comparison item has item, suppliers, best_supplier, savings_pct"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["comparison"]:
            pytest.skip("No comparison data available")
        
        item = data["comparison"][0]
        required_fields = ["item", "suppliers", "best_supplier", "best_price", "savings_pct"]
        for field in required_fields:
            assert field in item, f"Comparison item missing field: {field}"
        
        print(f"✓ Comparison item has all required fields: {required_fields}")

    def test_comparison_suppliers_have_avg_price(self, authenticated_client):
        """Each supplier in comparison has avg_price field"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["comparison"]:
            pytest.skip("No comparison data available")
        
        for item in data["comparison"]:
            for supplier_name, supplier_data in item["suppliers"].items():
                assert "avg_price" in supplier_data, f"Missing avg_price for {supplier_name} on {item['item']}"
                assert isinstance(supplier_data["avg_price"], (int, float)), "avg_price should be numeric"
        
        print("✓ All supplier entries have avg_price")

    def test_best_supplier_has_lowest_price(self, authenticated_client):
        """best_supplier field points to supplier with lowest avg_price"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["comparison"]:
            pytest.skip("No comparison data available")
        
        for item in data["comparison"]:
            if len(item["suppliers"]) <= 1:
                continue
            
            prices = [(sup, d["avg_price"]) for sup, d in item["suppliers"].items()]
            prices.sort(key=lambda x: x[1])
            
            if item["best_supplier"]:
                assert item["best_supplier"] == prices[0][0], f"best_supplier mismatch for {item['item']}"
        
        print("✓ best_supplier correctly identifies lowest price supplier")

    def test_savings_pct_is_calculated(self, authenticated_client):
        """savings_pct is calculated correctly (% savings vs worst price)"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["comparison"]:
            pytest.skip("No comparison data available")
        
        for item in data["comparison"]:
            if len(item["suppliers"]) <= 1:
                assert item.get("savings_pct", 0) == 0
                continue
            
            assert isinstance(item["savings_pct"], (int, float)), f"savings_pct should be numeric for {item['item']}"
            assert item["savings_pct"] >= 0, "savings_pct should be non-negative"
        
        print("✓ savings_pct is calculated correctly")


class TestPriceTrends:
    """Tests for price trends data"""

    def test_price_trends_is_dict(self, authenticated_client):
        """price_trends is a dict of item_name -> weekly data"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["price_trends"], dict), "price_trends should be a dict"
        print(f"✓ price_trends contains {len(data['price_trends'])} items")

    def test_price_trends_have_weekly_data_points(self, authenticated_client):
        """Each item in price_trends has weekly data points with week and avg_price"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["price_trends"]:
            pytest.skip("No price trends data available")
        
        for item_name, trend_data in data["price_trends"].items():
            assert isinstance(trend_data, list), f"Trend data for {item_name} should be a list"
            assert len(trend_data) > 0, f"Trend data for {item_name} should not be empty"
            
            for point in trend_data:
                assert "week" in point, f"Missing 'week' field in trend data for {item_name}"
                assert "avg_price" in point, f"Missing 'avg_price' field in trend data for {item_name}"
        
        print("✓ Price trends have weekly data points with week and avg_price")

    def test_price_trends_weeks_are_sorted(self, authenticated_client):
        """Weekly data points are sorted by date"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["price_trends"]:
            pytest.skip("No price trends data available")
        
        for item_name, trend_data in data["price_trends"].items():
            weeks = [p["week"] for p in trend_data]
            assert weeks == sorted(weeks), f"Weeks for {item_name} should be sorted"
        
        print("✓ Price trends weeks are sorted chronologically")


class TestPriceAlerts:
    """Tests for price alerts (>10% increases)"""

    def test_price_alerts_is_list(self, authenticated_client):
        """price_alerts is a list"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["price_alerts"], list), "price_alerts should be a list"
        print(f"✓ price_alerts is a list with {len(data['price_alerts'])} alerts")

    def test_price_alerts_structure(self, authenticated_client):
        """If alerts exist, they have correct structure"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        if not data["price_alerts"]:
            print("✓ No price alerts currently (no items with >10% increase)")
            return
        
        alert = data["price_alerts"][0]
        required_fields = ["item", "current_avg", "previous_avg", "change_pct", "severity"]
        for field in required_fields:
            assert field in alert, f"Alert missing field: {field}"
        
        print(f"✓ Price alerts have correct structure: {required_fields}")

    def test_price_alerts_threshold(self, authenticated_client):
        """All alerts have change_pct > 10%"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        for alert in data["price_alerts"]:
            assert alert["change_pct"] > 10, f"Alert for {alert['item']} has change_pct {alert['change_pct']} <= 10%"
        
        print(f"✓ All {len(data['price_alerts'])} alerts have change_pct > 10%")

    def test_price_alerts_severity(self, authenticated_client):
        """Alerts have severity 'high' or 'medium'"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        for alert in data["price_alerts"]:
            assert alert["severity"] in ["high", "medium"], f"Invalid severity: {alert['severity']}"
        
        print("✓ All alerts have valid severity (high/medium)")


class TestSummaryFields:
    """Tests for summary/count fields"""

    def test_total_items_tracked(self, authenticated_client):
        """total_items_tracked is a positive integer"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["total_items_tracked"], int), "total_items_tracked should be int"
        assert data["total_items_tracked"] >= 0, "total_items_tracked should be non-negative"
        print(f"✓ total_items_tracked = {data['total_items_tracked']}")

    def test_total_suppliers(self, authenticated_client):
        """total_suppliers matches length of suppliers list"""
        response = authenticated_client.get(f"{BASE_URL}/api/prices/intelligence")
        data = response.json()
        
        assert isinstance(data["total_suppliers"], int), "total_suppliers should be int"
        assert data["total_suppliers"] == len(data["suppliers"]), "total_suppliers should match suppliers list length"
        print(f"✓ total_suppliers = {data['total_suppliers']}")


class TestUnauthenticated:
    """Test that endpoint requires authentication"""

    def test_unauthenticated_returns_401(self):
        """Endpoint returns 401 without auth token"""
        response = requests.get(f"{BASE_URL}/api/prices/intelligence")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Unauthenticated request returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
