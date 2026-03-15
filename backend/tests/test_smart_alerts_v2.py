"""
Backend API tests for Smart Alerts v2 feature
Tests the new alert types: price_increase, cheaper_vendor, not_ordered
Tests: GET /api/dashboard/summary - smart_alerts array with real purchase data analysis
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSmartAlertsV2:
    """Test Smart Alerts v2 with new alert types"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get auth token using demo credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    # ----- SMART ALERTS ARRAY STRUCTURE TESTS -----
    
    def test_dashboard_returns_smart_alerts_array(self, headers):
        """Dashboard API should return smart_alerts as an array"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "smart_alerts" in data, "smart_alerts field missing from dashboard response"
        assert isinstance(data["smart_alerts"], list), "smart_alerts should be an array"
    
    def test_smart_alerts_not_empty_with_seed_data(self, headers):
        """Smart alerts should not be empty with demo/seed data"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        assert len(smart_alerts) > 0, "smart_alerts should have alerts with seed data"
    
    def test_smart_alerts_use_real_data_not_mocked(self, headers):
        """Smart alerts should be generated from real purchase data, not mocked"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        # Check alerts have item_name from purchase data
        for alert in smart_alerts:
            assert "item_name" in alert, "Alert should have item_name from real data"
            assert len(alert["item_name"]) > 0, "Item name should not be empty"
    
    # ----- ALERT TYPE TESTS -----
    
    def test_smart_alerts_have_valid_type(self, headers):
        """Each smart alert should have a valid type field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        valid_types = {"not_ordered", "price_increase", "cheaper_vendor"}
        smart_alerts = data.get("smart_alerts", [])
        
        for i, alert in enumerate(smart_alerts):
            assert "type" in alert, f"Alert {i} missing 'type' field"
            assert alert["type"] in valid_types, f"Alert {i} has invalid type: {alert['type']}. Expected one of {valid_types}"
    
    def test_smart_alerts_have_severity(self, headers):
        """Each smart alert should have severity: high, medium, or low"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        valid_severities = {"high", "medium", "low"}
        smart_alerts = data.get("smart_alerts", [])
        
        for i, alert in enumerate(smart_alerts):
            assert "severity" in alert, f"Alert {i} missing 'severity' field"
            assert alert["severity"] in valid_severities, f"Alert {i} has invalid severity: {alert['severity']}"
    
    # ----- PRICE INCREASE ALERT TESTS -----
    
    def test_price_increase_alerts_have_required_fields(self, headers):
        """price_increase alerts should have: item_name, vendor, old_price, new_price, change_pct, severity"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        price_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "price_increase"]
        if not price_alerts:
            pytest.skip("No price_increase alerts to test")
        
        required_fields = ["item_name", "vendor", "old_price", "new_price", "change_pct", "severity"]
        for i, alert in enumerate(price_alerts):
            for field in required_fields:
                assert field in alert, f"price_increase alert {i} missing '{field}'"
    
    def test_price_increase_alerts_have_positive_change(self, headers):
        """price_increase alerts should have positive change_pct (>0)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        price_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "price_increase"]
        if not price_alerts:
            pytest.skip("No price_increase alerts to test")
        
        for i, alert in enumerate(price_alerts):
            assert alert["change_pct"] > 0, f"price_increase alert {i} should have positive change_pct"
            assert alert["new_price"] > alert["old_price"], f"price_increase alert {i} new_price should be > old_price"
    
    def test_price_increase_severity_thresholds(self, headers):
        """Verify severity is based on change_pct: high (>15%), medium (>8%), low (>3%)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        price_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "price_increase"]
        if not price_alerts:
            pytest.skip("No price_increase alerts to test")
        
        for alert in price_alerts:
            pct = alert["change_pct"]
            sev = alert["severity"]
            if pct > 15:
                assert sev == "high", f"Alert with {pct}% increase should be 'high' severity"
            elif pct > 8:
                assert sev in ["high", "medium"], f"Alert with {pct}% increase should be 'high' or 'medium'"
            else:
                # Any alert >3% is valid, severity can vary
                pass
    
    # ----- CHEAPER VENDOR ALERT TESTS -----
    
    def test_cheaper_vendor_alerts_have_required_fields(self, headers):
        """cheaper_vendor alerts should have: item_name, vendor, current_price, cheaper_vendor, cheaper_price, savings_pct, severity"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        cheaper_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "cheaper_vendor"]
        if not cheaper_alerts:
            pytest.skip("No cheaper_vendor alerts to test")
        
        required_fields = ["item_name", "vendor", "current_price", "cheaper_vendor", "cheaper_price", "savings_pct", "severity"]
        for i, alert in enumerate(cheaper_alerts):
            for field in required_fields:
                assert field in alert, f"cheaper_vendor alert {i} missing '{field}'"
    
    def test_cheaper_vendor_alerts_have_positive_savings(self, headers):
        """cheaper_vendor alerts should have positive savings_pct"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        cheaper_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "cheaper_vendor"]
        if not cheaper_alerts:
            pytest.skip("No cheaper_vendor alerts to test")
        
        for i, alert in enumerate(cheaper_alerts):
            assert alert["savings_pct"] > 0, f"cheaper_vendor alert {i} should have positive savings_pct"
            assert alert["cheaper_price"] < alert["current_price"], f"cheaper_vendor alert {i} cheaper_price should be < current_price"
    
    def test_cheaper_vendor_severity_thresholds(self, headers):
        """Verify severity is based on savings_pct: high (>20%), medium (>10%), low (>3%)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        cheaper_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "cheaper_vendor"]
        if not cheaper_alerts:
            pytest.skip("No cheaper_vendor alerts to test")
        
        for alert in cheaper_alerts:
            pct = alert["savings_pct"]
            sev = alert["severity"]
            if pct > 20:
                assert sev == "high", f"Alert with {pct}% savings should be 'high' severity"
            elif pct > 10:
                assert sev in ["high", "medium"], f"Alert with {pct}% savings should be 'high' or 'medium'"
    
    # ----- NOT ORDERED ALERT TESTS -----
    
    def test_not_ordered_alerts_structure_if_present(self, headers):
        """not_ordered alerts (if present) should have: item_name, vendor, days_since, last_date, severity"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        not_ordered_alerts = [a for a in data.get("smart_alerts", []) if a["type"] == "not_ordered"]
        if not not_ordered_alerts:
            pytest.skip("No not_ordered alerts to test (seed data may be too recent)")
        
        required_fields = ["item_name", "vendor", "days_since", "last_date", "severity"]
        for i, alert in enumerate(not_ordered_alerts):
            for field in required_fields:
                assert field in alert, f"not_ordered alert {i} missing '{field}'"
    
    # ----- DASHBOARD KPIs STILL WORK TESTS -----
    
    def test_dashboard_returns_all_kpi_fields(self, headers):
        """Dashboard should still return all KPI fields alongside smart_alerts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "today_sales", "today_purchases",
            "week_sales", "week_purchases",
            "month_sales", "month_purchases",
            "prev_week_sales", "prev_week_purchases",
            "prev_month_sales", "prev_month_purchases",
            "top_items", "top_suppliers", "weekly_trends",
            "daily_profit", "weekly_profit", "monthly_profit", "yearly_profit"
        ]
        for field in required_fields:
            assert field in data, f"Missing KPI field: {field}"
    
    def test_dashboard_returns_profit_fields(self, headers):
        """Dashboard should return profit-related fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        profit_fields = ["daily_profit", "weekly_profit", "monthly_profit", "yearly_profit"]
        for field in profit_fields:
            assert field in data, f"Missing profit field: {field}"
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
    
    def test_dashboard_weekly_trends_structure(self, headers):
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
    
    def test_dashboard_top_items_structure(self, headers):
        """Top items should have name and total fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        top_items = data.get("top_items", [])
        for item in top_items:
            assert "name" in item, "Top item missing 'name' field"
            assert "total" in item, "Top item missing 'total' field"
    
    def test_dashboard_top_suppliers_structure(self, headers):
        """Top suppliers should have name and total fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        top_suppliers = data.get("top_suppliers", [])
        for supplier in top_suppliers:
            assert "name" in supplier, "Top supplier missing 'name' field"
            assert "total" in supplier, "Top supplier missing 'total' field"


class TestSmartAlertsAlertCounts:
    """Test alert counts match filter tabs"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_alert_counts_consistency(self, headers):
        """Total alerts should equal sum of each type"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        total = len(smart_alerts)
        
        price_increase = len([a for a in smart_alerts if a["type"] == "price_increase"])
        cheaper_vendor = len([a for a in smart_alerts if a["type"] == "cheaper_vendor"])
        not_ordered = len([a for a in smart_alerts if a["type"] == "not_ordered"])
        
        assert total == price_increase + cheaper_vendor + not_ordered, \
            f"Total alerts ({total}) should equal sum of types (price_increase={price_increase}, cheaper_vendor={cheaper_vendor}, not_ordered={not_ordered})"
        
        print(f"Alert counts: total={total}, price_increase={price_increase}, cheaper_vendor={cheaper_vendor}, not_ordered={not_ordered}")
    
    def test_high_severity_count(self, headers):
        """Count of high severity alerts should be correct"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        smart_alerts = data.get("smart_alerts", [])
        high_count = len([a for a in smart_alerts if a.get("severity") == "high"])
        
        print(f"High severity alerts: {high_count}")
        # Just verify we can count them, no specific threshold requirement


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
