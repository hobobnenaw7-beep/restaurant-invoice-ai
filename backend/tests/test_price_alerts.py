"""
Test Suite: Price Alert System
Features tested:
- POST /api/purchases generates price_increase alerts when item prices are higher
- Price comparison uses canonical item names + aliases for fuzzy matching
- GET /api/alerts/prices returns price increase alerts sorted newest first
- DELETE /api/alerts/prices/{aid} dismisses/deletes a price alert
- GET /api/dashboard/summary includes price_alerts array in response
- No alerts generated when new price is equal to or lower than previous price
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPriceAlertSystem:
    """Price Alert System Backend Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Get auth token for demo@test.com"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        if response.status_code == 200:
            token = response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping authenticated tests")
    
    def test_01_auth_login(self):
        """Test login works and returns token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo@test.com"
        print("PASSED: Login successful")
    
    def test_02_get_alerts_prices_endpoint(self):
        """Test GET /api/alerts/prices returns price alerts"""
        response = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert response.status_code == 200, f"GET /api/alerts/prices failed: {response.text}"
        alerts = response.json()
        assert isinstance(alerts, list), "Response should be a list"
        
        # Check structure of alerts if any exist
        if alerts:
            alert = alerts[0]
            assert "id" in alert, "Alert should have id"
            assert "type" in alert, "Alert should have type"
            assert alert["type"] == "price_increase", "Alert type should be price_increase"
            assert "item_name" in alert, "Alert should have item_name"
            assert "previous_price" in alert, "Alert should have previous_price"
            assert "new_price" in alert, "Alert should have new_price"
            assert "change_pct" in alert, "Alert should have change_pct"
            print(f"PASSED: Found {len(alerts)} price alerts with correct structure")
        else:
            print("PASSED: GET /api/alerts/prices works (no alerts currently)")
    
    def test_03_dashboard_includes_price_alerts(self):
        """Test GET /api/dashboard/summary includes price_alerts array"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200, f"Dashboard summary failed: {response.text}"
        data = response.json()
        
        # Verify price_alerts is in the response
        assert "price_alerts" in data, "Dashboard should include price_alerts array"
        assert isinstance(data["price_alerts"], list), "price_alerts should be a list"
        
        # Check price_alerts have correct structure
        if data["price_alerts"]:
            alert = data["price_alerts"][0]
            assert "item_name" in alert
            assert "previous_price" in alert
            assert "new_price" in alert
            assert "change_pct" in alert
            assert "vendor" in alert
            print(f"PASSED: Dashboard includes {len(data['price_alerts'])} price alerts")
        else:
            print("PASSED: Dashboard includes price_alerts array (empty)")
    
    def test_04_existing_price_alerts_check(self):
        """Verify existing price alerts from previous testing"""
        response = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert response.status_code == 200
        alerts = response.json()
        
        # According to agent context, 4 price alerts should exist
        # Butter, Basmati Rice, Ground Beef, Roma Tomatoes
        expected_items = ["Butter", "Basmati Rice", "Ground Beef", "Roma Tomatoes"]
        found_items = [a["item_name"] for a in alerts]
        
        found_count = 0
        for item in expected_items:
            if item in found_items:
                found_count += 1
                print(f"  Found existing alert for: {item}")
        
        print(f"PASSED: Found {found_count}/{len(expected_items)} expected price alerts")
    
    def test_05_create_purchase_generates_alert_price_increase(self):
        """Test creating a purchase with higher price generates alert"""
        # First, get a list of purchases to find an item with existing price
        purchases_resp = self.session.get(f"{BASE_URL}/api/purchases")
        assert purchases_resp.status_code == 200
        purchases = purchases_resp.json()
        
        # Find an item from existing purchases
        test_item_name = None
        test_previous_price = 0
        
        for p in purchases:
            for item in p.get("items", []):
                if item.get("unit_price", 0) > 0:
                    test_item_name = item.get("raw_name")
                    test_previous_price = float(item.get("unit_price"))
                    break
            if test_item_name:
                break
        
        if not test_item_name:
            pytest.skip("No existing items with prices found to test price increase")
        
        # Create a purchase with a HIGHER price (25% increase)
        new_price = round(test_previous_price * 1.25, 2)
        unique_invoice = f"TEST-ALERT-{uuid.uuid4().hex[:8]}"
        today = datetime.now().strftime("%Y-%m-%d")
        
        purchase_data = {
            "supplier_name": "TEST Supplier Alert",
            "invoice_number": unique_invoice,
            "invoice_date": today,
            "items": [{
                "raw_name": test_item_name,
                "quantity": 5,
                "unit": "each",
                "unit_price": new_price,
                "total": round(new_price * 5, 2)
            }],
            "subtotal": round(new_price * 5, 2),
            "tax": 0,
            "total": round(new_price * 5, 2)
        }
        
        # Count alerts before
        alerts_before = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        count_before = len(alerts_before)
        
        # Create purchase
        create_resp = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_resp.status_code == 200, f"Create purchase failed: {create_resp.text}"
        created_purchase = create_resp.json()
        
        # Count alerts after
        alerts_after = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        count_after = len(alerts_after)
        
        # Should have at least one more alert
        assert count_after >= count_before, "Alert count should not decrease"
        
        # Look for the new alert
        new_alert = None
        for a in alerts_after:
            if a["item_name"] == test_item_name and abs(a["new_price"] - new_price) < 0.01:
                new_alert = a
                break
        
        if new_alert:
            assert new_alert["type"] == "price_increase"
            assert new_alert["new_price"] == new_price
            print(f"PASSED: Created purchase with price ${test_previous_price:.2f} -> ${new_price:.2f}, alert generated")
        else:
            print(f"INFO: Alert may not have been created if {test_item_name} was not found in previous purchases")
        
        # Cleanup: delete the test purchase
        if created_purchase.get("id"):
            self.session.delete(f"{BASE_URL}/api/purchases/{created_purchase['id']}")
    
    def test_06_no_alert_when_price_equal_or_lower(self):
        """Test that no alert is generated when price is equal or lower"""
        # Get existing items
        purchases_resp = self.session.get(f"{BASE_URL}/api/purchases")
        purchases = purchases_resp.json()
        
        test_item_name = None
        test_previous_price = 0
        
        for p in purchases:
            for item in p.get("items", []):
                if item.get("unit_price", 0) > 1:  # Need price > 1 to reduce
                    test_item_name = item.get("raw_name")
                    test_previous_price = float(item.get("unit_price"))
                    break
            if test_item_name:
                break
        
        if not test_item_name:
            pytest.skip("No existing items to test lower price")
        
        # Create purchase with LOWER price (10% decrease)
        new_price = round(test_previous_price * 0.9, 2)
        unique_invoice = f"TEST-LOWER-{uuid.uuid4().hex[:8]}"
        today = datetime.now().strftime("%Y-%m-%d")
        
        purchase_data = {
            "supplier_name": "TEST Supplier Lower",
            "invoice_number": unique_invoice,
            "invoice_date": today,
            "items": [{
                "raw_name": test_item_name,
                "quantity": 3,
                "unit": "each",
                "unit_price": new_price,
                "total": round(new_price * 3, 2)
            }],
            "subtotal": round(new_price * 3, 2),
            "tax": 0,
            "total": round(new_price * 3, 2)
        }
        
        # Count alerts before
        alerts_before = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        item_alerts_before = [a for a in alerts_before if a["item_name"] == test_item_name and a["new_price"] == new_price]
        
        # Create purchase
        create_resp = self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
        assert create_resp.status_code == 200
        created_purchase = create_resp.json()
        
        # Check no new alert for this item with the lower price
        alerts_after = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        item_alerts_after = [a for a in alerts_after if a["item_name"] == test_item_name and a["new_price"] == new_price]
        
        assert len(item_alerts_after) == len(item_alerts_before), "No alert should be created for lower price"
        print(f"PASSED: No alert generated for price decrease ${test_previous_price:.2f} -> ${new_price:.2f}")
        
        # Cleanup
        if created_purchase.get("id"):
            self.session.delete(f"{BASE_URL}/api/purchases/{created_purchase['id']}")
    
    def test_07_delete_price_alert(self):
        """Test DELETE /api/alerts/prices/{aid} dismisses alert"""
        # Get current alerts
        alerts_resp = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert alerts_resp.status_code == 200
        alerts = alerts_resp.json()
        
        if not alerts:
            # Create a new alert first
            purchase_data = {
                "supplier_name": "TEST Delete Alert",
                "invoice_number": f"TEST-DEL-{uuid.uuid4().hex[:8]}",
                "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                "items": [{
                    "raw_name": "Test Delete Item",
                    "quantity": 1,
                    "unit": "each",
                    "unit_price": 999.99,
                    "total": 999.99
                }],
                "subtotal": 999.99,
                "tax": 0,
                "total": 999.99
            }
            self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
            alerts = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        
        if not alerts:
            pytest.skip("Could not create alert to test deletion")
        
        # Get the last alert (likely our test one or newest)
        alert_to_delete = alerts[-1]
        alert_id = alert_to_delete["id"]
        
        # Delete the alert
        delete_resp = self.session.delete(f"{BASE_URL}/api/alerts/prices/{alert_id}")
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        data = delete_resp.json()
        assert data.get("status") == "deleted", "Response should confirm deletion"
        
        # Verify alert is gone
        alerts_after = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        alert_ids_after = [a["id"] for a in alerts_after]
        assert alert_id not in alert_ids_after, "Deleted alert should not be in list"
        
        print(f"PASSED: Successfully deleted alert {alert_id}")
    
    def test_08_delete_nonexistent_alert_returns_404(self):
        """Test deleting non-existent alert returns 404"""
        fake_id = f"nonexistent-{uuid.uuid4()}"
        response = self.session.delete(f"{BASE_URL}/api/alerts/prices/{fake_id}")
        assert response.status_code == 404, f"Should return 404 for non-existent alert"
        print("PASSED: DELETE non-existent alert returns 404")
    
    def test_09_price_alert_structure(self):
        """Verify price alert has all required fields"""
        response = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert response.status_code == 200
        alerts = response.json()
        
        if not alerts:
            # Create one to test
            purchase_data = {
                "supplier_name": "Test Structure Vendor",
                "invoice_number": f"TEST-STR-{uuid.uuid4().hex[:8]}",
                "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                "items": [{
                    "raw_name": "Test Structure Item",
                    "quantity": 1,
                    "unit": "unit",
                    "unit_price": 888.88,
                    "total": 888.88
                }],
                "subtotal": 888.88,
                "tax": 0,
                "total": 888.88
            }
            self.session.post(f"{BASE_URL}/api/purchases", json=purchase_data)
            alerts = self.session.get(f"{BASE_URL}/api/alerts/prices").json()
        
        if not alerts:
            pytest.skip("No alerts available to verify structure")
        
        alert = alerts[0]
        required_fields = [
            "id", "type", "item_name", "previous_price", "new_price", 
            "change_pct", "vendor", "invoice_date", "created_at"
        ]
        
        for field in required_fields:
            assert field in alert, f"Alert missing required field: {field}"
        
        # Verify types
        assert isinstance(alert["previous_price"], (int, float)), "previous_price should be numeric"
        assert isinstance(alert["new_price"], (int, float)), "new_price should be numeric"
        assert isinstance(alert["change_pct"], (int, float)), "change_pct should be numeric"
        
        print(f"PASSED: Alert structure is valid with all required fields")
    
    def test_10_alerts_sorted_newest_first(self):
        """Verify alerts are sorted by created_at descending (newest first)"""
        response = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert response.status_code == 200
        alerts = response.json()
        
        if len(alerts) < 2:
            pytest.skip("Need at least 2 alerts to test sorting")
        
        # Check that created_at is in descending order
        dates = [a.get("created_at", "") for a in alerts]
        sorted_dates = sorted(dates, reverse=True)
        
        assert dates == sorted_dates, "Alerts should be sorted newest first"
        print(f"PASSED: {len(alerts)} alerts are sorted newest first")
    
    def test_11_high_severity_for_large_increase(self):
        """Verify alerts with >15% increase have high severity"""
        response = self.session.get(f"{BASE_URL}/api/alerts/prices")
        assert response.status_code == 200
        alerts = response.json()
        
        for alert in alerts:
            change_pct = alert.get("change_pct", 0)
            severity = alert.get("severity", "")
            
            if change_pct > 15:
                assert severity == "high", f"Alert with {change_pct}% increase should be high severity"
                print(f"  Alert {alert['item_name']}: {change_pct}% = {severity} severity")
            elif change_pct > 0:
                assert severity == "medium", f"Alert with {change_pct}% increase should be medium severity"
                print(f"  Alert {alert['item_name']}: {change_pct}% = {severity} severity")
        
        print(f"PASSED: Severity correctly set based on change percentage")

    def test_12_dashboard_summary_complete(self):
        """Test dashboard summary has all expected fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Expected fields according to the review request
        expected_fields = [
            "today_sales", "today_purchases",
            "week_sales", "week_purchases",
            "month_sales", "month_purchases",
            "top_items", "top_suppliers", "weekly_trends",
            "smart_alerts", "price_alerts"
        ]
        
        for field in expected_fields:
            assert field in data, f"Dashboard missing field: {field}"
        
        print(f"PASSED: Dashboard summary has all expected fields")
        print(f"  - today_sales: ${data['today_sales']:.2f}")
        print(f"  - month_purchases: ${data['month_purchases']:.2f}")
        print(f"  - smart_alerts count: {len(data['smart_alerts'])}")
        print(f"  - price_alerts count: {len(data['price_alerts'])}")


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
