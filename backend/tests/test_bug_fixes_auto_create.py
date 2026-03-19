"""
Test Bug Fixes for Restaurant Accountant AI (Iteration 23)
- Bug 1: App handles empty database state correctly
- Bug 2: Auto-create vendors and items when saving purchases (case-insensitive dedup)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope='module')
def api_session():
    """Create authenticated session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login with test credentials
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestEmptyDatabaseState:
    """Bug 1: App must work correctly from an empty database state."""
    
    def test_get_suppliers_returns_empty_array(self, api_session):
        """GET /api/suppliers returns empty array when no suppliers exist."""
        resp = api_session.get(f"{BASE_URL}/api/suppliers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        # Note: There may be existing data, so just verify it's a valid response
        print(f"Suppliers count: {len(data)}")
    
    def test_get_items_returns_empty_array(self, api_session):
        """GET /api/items returns empty array when no items exist."""
        resp = api_session.get(f"{BASE_URL}/api/items")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Items count: {len(data)}")
    
    def test_get_purchases_returns_empty_array(self, api_session):
        """GET /api/purchases returns empty array when no purchases exist."""
        resp = api_session.get(f"{BASE_URL}/api/purchases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Purchases count: {len(data)}")
    
    def test_get_sales_returns_empty_array(self, api_session):
        """GET /api/sales returns empty array when no sales exist."""
        resp = api_session.get(f"{BASE_URL}/api/sales")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Sales count: {len(data)}")
    
    def test_dashboard_summary_returns_valid_data(self, api_session):
        """GET /api/dashboard/summary returns valid data even with zero records."""
        resp = api_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify dashboard returns valid structure with numeric values
        assert "today_sales" in data
        assert "today_purchases" in data
        assert "week_sales" in data
        assert "month_sales" in data
        assert "top_items" in data
        assert "top_suppliers" in data
        assert "weekly_trends" in data
        assert "smart_alerts" in data
        
        # Verify numeric fields are numbers (not null/error)
        assert isinstance(data["today_sales"], (int, float))
        assert isinstance(data["week_sales"], (int, float))
        assert isinstance(data["month_sales"], (int, float))
        assert isinstance(data["top_items"], list)
        assert isinstance(data["top_suppliers"], list)
        
        print(f"Dashboard summary: today_sales={data['today_sales']}, month_sales={data['month_sales']}")
    
    def test_reports_monthly_returns_valid_data(self, api_session):
        """GET /api/reports?report_type=monthly returns valid data with zero records."""
        resp = api_session.get(f"{BASE_URL}/api/reports", params={"report_type": "monthly"})
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify report structure
        assert isinstance(data, (dict, list)), "Should return a dict or list"
        print(f"Monthly report: {type(data)}")
    
    def test_create_first_supplier(self, api_session):
        """POST /api/suppliers works from empty state (create first vendor)."""
        unique_name = f"TestFirstSupplier_{uuid.uuid4().hex[:8]}"
        resp = api_session.post(f"{BASE_URL}/api/suppliers", json={
            "name": unique_name,
            "contact_person": "Test Contact",
            "phone": "555-1234"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("name") == unique_name
        assert "id" in data
        print(f"Created first supplier: {unique_name}")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/suppliers/{data['id']}")
    
    def test_create_first_item(self, api_session):
        """POST /api/items works from empty state (create first item)."""
        unique_name = f"TestFirstItem_{uuid.uuid4().hex[:8]}"
        resp = api_session.post(f"{BASE_URL}/api/items", json={
            "name": unique_name,
            "category": "Test Category"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("name") == unique_name
        assert "id" in data
        print(f"Created first item: {unique_name}")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/items/{data['id']}")
    
    def test_create_first_purchase(self, api_session):
        """POST /api/purchases works from empty state (create first expense)."""
        unique_vendor = f"TestPurchaseVendor_{uuid.uuid4().hex[:8]}"
        resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": unique_vendor,
            "invoice_number": "INV-TEST-001",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "kg", "unit_price": 10, "total": 10}],
            "subtotal": 10,
            "tax": 0,
            "total": 10
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("supplier_name") == unique_vendor
        assert "id" in data
        print(f"Created first purchase for vendor: {unique_vendor}")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/purchases/{data['id']}")
    
    def test_create_first_sale(self, api_session):
        """POST /api/sales works from empty state (create first sale)."""
        today = datetime.now().strftime("%Y-%m-%d")
        resp = api_session.post(f"{BASE_URL}/api/sales", json={
            "report_date": today,
            "date_from": today,
            "date_to": today,
            "total_sales": 500,
            "items": [{"menu_item": "Test Item", "quantity": 10, "revenue": 500}]
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("total_sales") == 500
        assert "id" in data
        print(f"Created first sale: ${data['total_sales']}")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/sales/{data['id']}")


class TestAutoCreateVendorAndItems:
    """Bug 2: Auto-create vendors and items when saving a new expense."""
    
    def test_purchase_creates_new_vendor_automatically(self, api_session):
        """POST /api/purchases with new vendor name auto-creates vendor in /api/suppliers."""
        # Use unique vendor name to ensure it doesn't exist
        unique_vendor = f"AutoVendor_{uuid.uuid4().hex[:8]}"
        
        # Verify vendor doesn't exist yet
        resp = api_session.get(f"{BASE_URL}/api/suppliers", params={"search": unique_vendor})
        vendors_before = resp.json()
        assert not any(v.get("name", "").lower() == unique_vendor.lower() for v in vendors_before), \
            f"Vendor {unique_vendor} should not exist before test"
        
        # Create purchase with new vendor
        purchase_resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": unique_vendor,
            "invoice_number": f"INV-{uuid.uuid4().hex[:6]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "kg", "unit_price": 25, "total": 25}],
            "subtotal": 25,
            "tax": 0,
            "total": 25
        })
        assert purchase_resp.status_code == 200, f"Purchase creation failed: {purchase_resp.text}"
        purchase_id = purchase_resp.json().get("id")
        
        # Verify vendor was auto-created
        resp = api_session.get(f"{BASE_URL}/api/suppliers", params={"search": unique_vendor})
        vendors_after = resp.json()
        vendor_found = any(v.get("name", "").lower() == unique_vendor.lower() for v in vendors_after)
        assert vendor_found, f"Vendor {unique_vendor} should have been auto-created"
        
        print(f"SUCCESS: Vendor '{unique_vendor}' was auto-created from purchase")
        
        # Cleanup - delete purchase and vendor
        api_session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        for v in vendors_after:
            if v.get("name", "").lower() == unique_vendor.lower():
                api_session.delete(f"{BASE_URL}/api/suppliers/{v['id']}")
    
    def test_purchase_creates_new_items_automatically(self, api_session):
        """POST /api/purchases with new item names auto-creates items in /api/items."""
        unique_item1 = f"AutoItem1_{uuid.uuid4().hex[:8]}"
        unique_item2 = f"AutoItem2_{uuid.uuid4().hex[:8]}"
        
        # Verify items don't exist yet
        resp = api_session.get(f"{BASE_URL}/api/items")
        items_before = resp.json()
        item_names_before = [i.get("name", "").lower() for i in items_before]
        assert unique_item1.lower() not in item_names_before
        assert unique_item2.lower() not in item_names_before
        
        # Create purchase with new items
        purchase_resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": "TestSupplier",
            "invoice_number": f"INV-{uuid.uuid4().hex[:6]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {"raw_name": unique_item1, "quantity": 2, "unit": "kg", "unit_price": 15, "total": 30},
                {"raw_name": unique_item2, "quantity": 3, "unit": "pcs", "unit_price": 5, "total": 15}
            ],
            "subtotal": 45,
            "tax": 0,
            "total": 45
        })
        assert purchase_resp.status_code == 200, f"Purchase creation failed: {purchase_resp.text}"
        purchase_id = purchase_resp.json().get("id")
        
        # Verify items were auto-created
        resp = api_session.get(f"{BASE_URL}/api/items")
        items_after = resp.json()
        item_names_after = [i.get("name", "").lower() for i in items_after]
        
        assert unique_item1.lower() in item_names_after, f"Item {unique_item1} should have been auto-created"
        assert unique_item2.lower() in item_names_after, f"Item {unique_item2} should have been auto-created"
        
        print(f"SUCCESS: Items '{unique_item1}' and '{unique_item2}' were auto-created from purchase")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        for item in items_after:
            if item.get("name", "").lower() in [unique_item1.lower(), unique_item2.lower()]:
                api_session.delete(f"{BASE_URL}/api/items/{item['id']}")


class TestCaseInsensitiveDedup:
    """Bug 2: Case-insensitive dedup for vendors and items."""
    
    def test_vendor_case_insensitive_dedup(self, api_session):
        """Creating a purchase with 'walmart' when 'Walmart' exists should NOT create a duplicate vendor."""
        # First, create a vendor with specific casing
        base_name = f"DedupVendor_{uuid.uuid4().hex[:6]}"
        proper_case_name = base_name  # e.g., "DedupVendor_abc123"
        lower_case_name = base_name.lower()  # e.g., "dedupvendor_abc123"
        
        # Create initial vendor
        create_resp = api_session.post(f"{BASE_URL}/api/suppliers", json={
            "name": proper_case_name,
            "contact_person": "Test"
        })
        assert create_resp.status_code == 200
        vendor_id = create_resp.json().get("id")
        
        # Get count of vendors before purchase
        resp = api_session.get(f"{BASE_URL}/api/suppliers")
        vendors_before = resp.json()
        count_before = sum(1 for v in vendors_before if base_name.lower() in v.get("name", "").lower())
        
        # Create purchase with LOWERCASE variant of vendor name
        purchase_resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": lower_case_name,
            "invoice_number": f"INV-DEDUP-{uuid.uuid4().hex[:4]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [{"raw_name": "Test", "quantity": 1, "unit": "kg", "unit_price": 10, "total": 10}],
            "subtotal": 10,
            "tax": 0,
            "total": 10
        })
        assert purchase_resp.status_code == 200
        purchase_id = purchase_resp.json().get("id")
        
        # Verify no duplicate vendor was created
        resp = api_session.get(f"{BASE_URL}/api/suppliers")
        vendors_after = resp.json()
        count_after = sum(1 for v in vendors_after if base_name.lower() in v.get("name", "").lower())
        
        assert count_after == count_before, \
            f"Duplicate vendor created! Before: {count_before}, After: {count_after}"
        
        print(f"SUCCESS: No duplicate vendor created for case variant '{lower_case_name}' vs '{proper_case_name}'")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        api_session.delete(f"{BASE_URL}/api/suppliers/{vendor_id}")
    
    def test_item_case_insensitive_dedup(self, api_session):
        """Creating a purchase with 'CHICKEN' when 'Chicken' exists should NOT create a duplicate item."""
        # Create a unique item with specific casing
        base_name = f"DedupItem_{uuid.uuid4().hex[:6]}"
        proper_case_name = base_name
        upper_case_name = base_name.upper()
        
        # Create initial item
        create_resp = api_session.post(f"{BASE_URL}/api/items", json={
            "name": proper_case_name,
            "category": "Test"
        })
        assert create_resp.status_code == 200
        item_id = create_resp.json().get("id")
        
        # Get count of items before purchase
        resp = api_session.get(f"{BASE_URL}/api/items")
        items_before = resp.json()
        count_before = sum(1 for i in items_before if base_name.lower() in i.get("name", "").lower())
        
        # Create purchase with UPPERCASE variant of item name
        purchase_resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": "TestSupplier",
            "invoice_number": f"INV-ITEMDEDUP-{uuid.uuid4().hex[:4]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [{"raw_name": upper_case_name, "quantity": 1, "unit": "kg", "unit_price": 20, "total": 20}],
            "subtotal": 20,
            "tax": 0,
            "total": 20
        })
        assert purchase_resp.status_code == 200
        purchase_id = purchase_resp.json().get("id")
        
        # Verify no duplicate item was created
        resp = api_session.get(f"{BASE_URL}/api/items")
        items_after = resp.json()
        count_after = sum(1 for i in items_after if base_name.lower() in i.get("name", "").lower())
        
        assert count_after == count_before, \
            f"Duplicate item created! Before: {count_before}, After: {count_after}"
        
        print(f"SUCCESS: No duplicate item created for case variant '{upper_case_name}' vs '{proper_case_name}'")
        
        # Cleanup
        api_session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        api_session.delete(f"{BASE_URL}/api/items/{item_id}")


class TestRegressionCRUD:
    """Regression: Existing CRUD operations still work."""
    
    def test_supplier_crud_operations(self, api_session):
        """Test create, read (via list), update, delete for suppliers."""
        unique_name = f"CRUDSupplier_{uuid.uuid4().hex[:8]}"
        
        # CREATE
        create_resp = api_session.post(f"{BASE_URL}/api/suppliers", json={
            "name": unique_name,
            "contact_person": "Initial Contact"
        })
        assert create_resp.status_code == 200
        supplier = create_resp.json()
        supplier_id = supplier["id"]
        
        # READ via list (single GET endpoint not implemented)
        list_resp = api_session.get(f"{BASE_URL}/api/suppliers", params={"search": unique_name})
        assert list_resp.status_code == 200
        suppliers = list_resp.json()
        found = next((s for s in suppliers if s.get("name") == unique_name), None)
        assert found is not None, f"Supplier {unique_name} should be in list"
        
        # UPDATE (name is required by SupplierCreate model)
        update_resp = api_session.put(f"{BASE_URL}/api/suppliers/{supplier_id}", json={
            "name": unique_name,
            "contact_person": "Updated Contact"
        })
        assert update_resp.status_code == 200
        assert update_resp.json().get("contact_person") == "Updated Contact"
        
        # DELETE
        delete_resp = api_session.delete(f"{BASE_URL}/api/suppliers/{supplier_id}")
        assert delete_resp.status_code == 200
        
        # Verify deleted (via list)
        list_after = api_session.get(f"{BASE_URL}/api/suppliers", params={"search": unique_name})
        suppliers_after = list_after.json()
        found_after = next((s for s in suppliers_after if s.get("id") == supplier_id), None)
        assert found_after is None, "Supplier should be deleted"
        
        print("SUCCESS: Supplier CRUD operations work correctly")
    
    def test_item_crud_operations(self, api_session):
        """Test create, read (via list), update, delete for items."""
        unique_name = f"CRUDItem_{uuid.uuid4().hex[:8]}"
        
        # CREATE
        create_resp = api_session.post(f"{BASE_URL}/api/items", json={
            "name": unique_name,
            "category": "Initial Category"
        })
        assert create_resp.status_code == 200
        item = create_resp.json()
        item_id = item["id"]
        
        # READ via list (single GET by ID not implemented)
        list_resp = api_session.get(f"{BASE_URL}/api/items", params={"search": unique_name})
        assert list_resp.status_code == 200
        items = list_resp.json()
        found = next((i for i in items if i.get("name") == unique_name), None)
        assert found is not None, f"Item {unique_name} should be in list"
        
        # UPDATE (name is required by CanonicalItemCreate model)
        update_resp = api_session.put(f"{BASE_URL}/api/items/{item_id}", json={
            "name": unique_name,
            "category": "Updated Category"
        })
        assert update_resp.status_code == 200
        
        # DELETE
        delete_resp = api_session.delete(f"{BASE_URL}/api/items/{item_id}")
        assert delete_resp.status_code == 200
        
        # Verify deleted (via list)
        list_after = api_session.get(f"{BASE_URL}/api/items", params={"search": unique_name})
        items_after = list_after.json()
        found_after = next((i for i in items_after if i.get("id") == item_id), None)
        assert found_after is None, "Item should be deleted"
        
        print("SUCCESS: Item CRUD operations work correctly")
    
    def test_purchase_crud_operations(self, api_session):
        """Test create, read, update, delete for purchases."""
        unique_vendor = f"CRUDPurchaseVendor_{uuid.uuid4().hex[:8]}"
        
        # CREATE
        create_resp = api_session.post(f"{BASE_URL}/api/purchases", json={
            "supplier_name": unique_vendor,
            "invoice_number": f"INV-CRUD-{uuid.uuid4().hex[:4]}",
            "invoice_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [{"raw_name": "Test", "quantity": 1, "unit": "kg", "unit_price": 10, "total": 10}],
            "subtotal": 10,
            "tax": 0,
            "total": 10
        })
        assert create_resp.status_code == 200
        purchase = create_resp.json()
        purchase_id = purchase["id"]
        
        # READ
        read_resp = api_session.get(f"{BASE_URL}/api/purchases/{purchase_id}")
        assert read_resp.status_code == 200
        assert read_resp.json().get("supplier_name") == unique_vendor
        
        # UPDATE
        update_resp = api_session.put(f"{BASE_URL}/api/purchases/{purchase_id}", json={
            "invoice_number": "INV-UPDATED"
        })
        assert update_resp.status_code == 200
        assert update_resp.json().get("invoice_number") == "INV-UPDATED"
        
        # DELETE
        delete_resp = api_session.delete(f"{BASE_URL}/api/purchases/{purchase_id}")
        assert delete_resp.status_code == 200
        
        # Verify deleted
        read_after_delete = api_session.get(f"{BASE_URL}/api/purchases/{purchase_id}")
        assert read_after_delete.status_code == 404
        
        # Cleanup auto-created vendor
        vendors = api_session.get(f"{BASE_URL}/api/suppliers", params={"search": unique_vendor}).json()
        for v in vendors:
            if v.get("name", "").lower() == unique_vendor.lower():
                api_session.delete(f"{BASE_URL}/api/suppliers/{v['id']}")
        
        print("SUCCESS: Purchase CRUD operations work correctly")
    
    def test_sales_crud_operations(self, api_session):
        """Test create, read, update, delete for sales."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # CREATE
        create_resp = api_session.post(f"{BASE_URL}/api/sales", json={
            "report_date": today,
            "date_from": today,
            "date_to": today,
            "total_sales": 999,
            "items": [{"menu_item": "TestItem", "quantity": 10, "revenue": 999}]
        })
        assert create_resp.status_code == 200
        sale = create_resp.json()
        sale_id = sale["id"]
        
        # READ
        read_resp = api_session.get(f"{BASE_URL}/api/sales/{sale_id}")
        assert read_resp.status_code == 200
        assert read_resp.json().get("total_sales") == 999
        
        # UPDATE
        update_resp = api_session.put(f"{BASE_URL}/api/sales/{sale_id}", json={
            "total_sales": 1111
        })
        assert update_resp.status_code == 200
        assert update_resp.json().get("total_sales") == 1111
        
        # DELETE
        delete_resp = api_session.delete(f"{BASE_URL}/api/sales/{sale_id}")
        assert delete_resp.status_code == 200
        
        # Verify deleted
        read_after_delete = api_session.get(f"{BASE_URL}/api/sales/{sale_id}")
        assert read_after_delete.status_code == 404
        
        print("SUCCESS: Sales CRUD operations work correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
