"""
Test suite for Smart Purchase Decisions feature
Tests GET /api/purchase-decisions endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for testing"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestPurchaseDecisionsEndpoint:
    """Tests for GET /api/purchase-decisions endpoint"""

    def test_endpoint_returns_200(self, api_client):
        """Test that endpoint returns 200 status"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Endpoint returns 200")

    def test_response_has_required_fields(self, api_client):
        """Test response contains all required top-level fields"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["items", "insights", "weekly_changes", "potential_savings", "total_items"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: Response has all required fields: {required_fields}")

    def test_items_is_list(self, api_client):
        """Test that items is a list"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        assert isinstance(data["items"], list), "items should be a list"
        print(f"PASS: items is a list with {len(data['items'])} items")

    def test_insights_is_list(self, api_client):
        """Test that insights is a list"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        assert isinstance(data["insights"], list), "insights should be a list"
        print(f"PASS: insights is a list with {len(data['insights'])} insights")

    def test_weekly_changes_is_list(self, api_client):
        """Test that weekly_changes is a list"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        assert isinstance(data["weekly_changes"], list), "weekly_changes should be a list"
        print(f"PASS: weekly_changes is a list with {len(data['weekly_changes'])} changes")

    def test_potential_savings_is_number(self, api_client):
        """Test that potential_savings is a number"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        assert isinstance(data["potential_savings"], (int, float)), "potential_savings should be a number"
        print(f"PASS: potential_savings is {data['potential_savings']}")

    def test_total_items_is_integer(self, api_client):
        """Test that total_items is an integer"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        assert isinstance(data["total_items"], int), "total_items should be an integer"
        print(f"PASS: total_items is {data['total_items']}")


class TestItemsStructure:
    """Tests for items array structure"""

    def test_item_has_required_fields(self, api_client):
        """Test each item has required fields"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No items in response - need purchase data")
        
        required_item_fields = ["item", "vendors", "best_vendor", "best_price", "saving_per_unit", "vendor_count"]
        for item in data["items"][:5]:  # Check first 5 items
            for field in required_item_fields:
                assert field in item, f"Item missing field: {field}"
        print(f"PASS: Items have all required fields: {required_item_fields}")

    def test_vendors_array_structure(self, api_client):
        """Test vendors array has correct structure"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No items in response")
        
        vendor_fields = ["vendor", "latest_price", "avg_price", "purchase_count"]
        for item in data["items"][:5]:
            assert isinstance(item["vendors"], list), "vendors should be a list"
            for vendor in item["vendors"]:
                for field in vendor_fields:
                    assert field in vendor, f"Vendor missing field: {field}"
        print(f"PASS: Vendors have required fields: {vendor_fields}")

    def test_items_sorted_alphabetically(self, api_client):
        """Test items are sorted alphabetically by item name"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["items"]) < 2:
            pytest.skip("Need at least 2 items to test sorting")
        
        item_names = [item["item"] for item in data["items"]]
        sorted_names = sorted(item_names)
        assert item_names == sorted_names, f"Items not sorted alphabetically"
        print(f"PASS: Items are sorted alphabetically ({len(item_names)} items)")


class TestInsightsStructure:
    """Tests for insights array structure"""

    def test_best_vendor_insight_structure(self, api_client):
        """Test best_vendor insights have correct structure"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        best_vendor_insights = [i for i in data["insights"] if i.get("type") == "best_vendor"]
        if len(best_vendor_insights) == 0:
            pytest.skip("No best_vendor insights found")
        
        required_fields = ["type", "item", "best_vendor", "best_price", "worst_vendor", "saving_per_unit", "pct"]
        for insight in best_vendor_insights[:5]:
            for field in required_fields:
                assert field in insight, f"best_vendor insight missing field: {field}"
            assert insight["saving_per_unit"] > 0, "saving_per_unit should be positive"
        print(f"PASS: best_vendor insights have correct structure ({len(best_vendor_insights)} found)")

    def test_price_increase_insight_structure(self, api_client):
        """Test price_increase insights have correct structure"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        price_increase_insights = [i for i in data["insights"] if i.get("type") == "price_increase"]
        if len(price_increase_insights) == 0:
            pytest.skip("No price_increase insights found")
        
        required_fields = ["type", "item", "change_pct", "this_week", "last_week"]
        for insight in price_increase_insights[:5]:
            for field in required_fields:
                assert field in insight, f"price_increase insight missing field: {field}"
        print(f"PASS: price_increase insights have correct structure ({len(price_increase_insights)} found)")

    def test_insights_sorted_by_impact(self, api_client):
        """Test insights are sorted by impact (saving_per_unit or change_pct)"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["insights"]) < 2:
            pytest.skip("Need at least 2 insights to test sorting")
        
        # Insights should be sorted by impact (descending)
        impacts = [i.get("saving_per_unit", 0) or i.get("change_pct", 0) for i in data["insights"]]
        assert impacts == sorted(impacts, reverse=True), "Insights not sorted by impact"
        print(f"PASS: Insights are sorted by impact ({len(data['insights'])} insights)")


class TestWeeklyChangesStructure:
    """Tests for weekly_changes array structure"""

    def test_weekly_change_structure(self, api_client):
        """Test weekly_changes have correct structure"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["weekly_changes"]) == 0:
            pytest.skip("No weekly changes found")
        
        required_fields = ["item", "this_week_avg", "last_week_avg", "change_pct", "direction"]
        for change in data["weekly_changes"][:5]:
            for field in required_fields:
                assert field in change, f"weekly_change missing field: {field}"
            assert change["direction"] in ["up", "down"], f"Invalid direction: {change['direction']}"
        print(f"PASS: weekly_changes have correct structure ({len(data['weekly_changes'])} found)")


class TestPotentialSavings:
    """Tests for potential_savings calculation"""

    def test_potential_savings_non_negative(self, api_client):
        """Test potential_savings is non-negative"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        assert data["potential_savings"] >= 0, "potential_savings should be non-negative"
        print(f"PASS: potential_savings is non-negative: ${data['potential_savings']}")

    def test_potential_savings_positive_when_cheaper_vendors_exist(self, api_client):
        """Test potential_savings is positive when there are cheaper vendor alternatives"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        best_vendor_insights = [i for i in data["insights"] if i.get("type") == "best_vendor"]
        if len(best_vendor_insights) > 0:
            assert data["potential_savings"] > 0, "potential_savings should be positive when cheaper vendors exist"
            print(f"PASS: potential_savings is positive (${data['potential_savings']}) with {len(best_vendor_insights)} vendor switch opportunities")
        else:
            print(f"SKIP: No vendor switch opportunities found")


class TestDataConsistency:
    """Tests for data consistency"""

    def test_total_items_matches_items_length(self, api_client):
        """Test total_items matches actual items array length"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        assert data["total_items"] == len(data["items"]), f"total_items ({data['total_items']}) doesn't match items length ({len(data['items'])})"
        print(f"PASS: total_items ({data['total_items']}) matches items array length")

    def test_vendor_count_matches_vendors_array(self, api_client):
        """Test vendor_count matches vendors array length for each item"""
        response = api_client.get(f"{BASE_URL}/api/purchase-decisions")
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No items to test")
        
        for item in data["items"]:
            assert item["vendor_count"] == len(item["vendors"]), f"vendor_count mismatch for {item['item']}"
        print(f"PASS: vendor_count matches vendors array length for all items")


class TestUnauthorizedAccess:
    """Tests for unauthorized access"""

    def test_endpoint_requires_auth(self):
        """Test endpoint returns 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/purchase-decisions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Endpoint requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
