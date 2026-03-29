"""
Test suite for Raw Materials pack_weight, unit, and normalized_unit_price features.
Tests the new columns added to Raw Materials / Purchases line items.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRawMaterialsPackWeight:
    """Tests for pack_weight, unit, and normalized_unit_price in purchases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.created_purchase_ids = []
        yield
        # Cleanup created purchases
        for pid in self.created_purchase_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/purchases/{pid}")
            except:
                pass
    
    def test_create_purchase_with_pack_weight_and_unit(self):
        """Test creating a purchase with pack_weight and unit fields"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "supplier_name": f"TEST_PackWeight_Vendor_{unique_id}",
            "invoice_number": f"INV-PW-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Chicken Breast",
                    "quantity": 5,
                    "pack_weight": 10,
                    "unit": "LB",
                    "unit_price": 25.00,
                    "total": 125.00,
                    "normalized_unit_price": 2.50  # 25.00 / 10 = 2.50
                },
                {
                    "raw_name": "Ground Beef",
                    "quantity": 3,
                    "pack_weight": 5,
                    "unit": "KG",
                    "unit_price": 40.00,
                    "total": 120.00,
                    "normalized_unit_price": 8.00  # 40.00 / 5 = 8.00
                }
            ],
            "subtotal": 245.00,
            "tax": 19.60,
            "total": 264.60
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should contain purchase ID"
        self.created_purchase_ids.append(data["id"])
        
        # Verify items have pack_weight and unit
        items = data.get("items", [])
        assert len(items) == 2, "Should have 2 items"
        
        # Check first item
        assert items[0]["pack_weight"] == 10, f"First item pack_weight should be 10, got {items[0].get('pack_weight')}"
        assert items[0]["unit"] == "LB", f"First item unit should be LB, got {items[0].get('unit')}"
        assert items[0]["normalized_unit_price"] == 2.50, f"First item normalized_unit_price should be 2.50, got {items[0].get('normalized_unit_price')}"
        
        # Check second item
        assert items[1]["pack_weight"] == 5, f"Second item pack_weight should be 5, got {items[1].get('pack_weight')}"
        assert items[1]["unit"] == "KG", f"Second item unit should be KG, got {items[1].get('unit')}"
        assert items[1]["normalized_unit_price"] == 8.00, f"Second item normalized_unit_price should be 8.00, got {items[1].get('normalized_unit_price')}"
        
        print("PASS: Create purchase with pack_weight and unit fields")
    
    def test_create_purchase_with_zero_pack_weight(self):
        """Test creating a purchase with zero pack_weight (normalized_unit_price should be 0)"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "supplier_name": f"TEST_ZeroPW_Vendor_{unique_id}",
            "invoice_number": f"INV-ZPW-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Cooking Oil",
                    "quantity": 2,
                    "pack_weight": 0,  # No pack weight
                    "unit": "",  # No unit
                    "unit_price": 15.00,
                    "total": 30.00,
                    "normalized_unit_price": 0  # Should be 0 when pack_weight is 0
                }
            ],
            "subtotal": 30.00,
            "tax": 2.40,
            "total": 32.40
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        
        data = response.json()
        self.created_purchase_ids.append(data["id"])
        
        items = data.get("items", [])
        assert len(items) == 1, "Should have 1 item"
        assert items[0]["pack_weight"] == 0, "pack_weight should be 0"
        assert items[0]["normalized_unit_price"] == 0, "normalized_unit_price should be 0 when pack_weight is 0"
        
        print("PASS: Create purchase with zero pack_weight")
    
    def test_get_purchase_with_pack_weight_data(self):
        """Test retrieving a purchase and verifying pack_weight data persists"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "supplier_name": f"TEST_GetPW_Vendor_{unique_id}",
            "invoice_number": f"INV-GPW-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Salmon Fillet",
                    "quantity": 4,
                    "pack_weight": 2.5,
                    "unit": "LB",
                    "unit_price": 30.00,
                    "total": 120.00,
                    "normalized_unit_price": 12.00  # 30.00 / 2.5 = 12.00
                }
            ],
            "subtotal": 120.00,
            "tax": 9.60,
            "total": 129.60
        }
        
        # Create purchase
        create_response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert create_response.status_code == 200, f"Create purchase failed: {create_response.text}"
        purchase_id = create_response.json()["id"]
        self.created_purchase_ids.append(purchase_id)
        
        # Get purchase
        get_response = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}")
        assert get_response.status_code == 200, f"Get purchase failed: {get_response.text}"
        
        data = get_response.json()
        items = data.get("items", [])
        assert len(items) == 1, "Should have 1 item"
        
        # Verify data persisted correctly
        assert items[0]["pack_weight"] == 2.5, f"pack_weight should be 2.5, got {items[0].get('pack_weight')}"
        assert items[0]["unit"] == "LB", f"unit should be LB, got {items[0].get('unit')}"
        assert items[0]["normalized_unit_price"] == 12.00, f"normalized_unit_price should be 12.00, got {items[0].get('normalized_unit_price')}"
        
        print("PASS: Get purchase with pack_weight data persists correctly")
    
    def test_update_purchase_with_pack_weight(self):
        """Test updating a purchase with new pack_weight values"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Create initial purchase
        create_payload = {
            "supplier_name": f"TEST_UpdatePW_Vendor_{unique_id}",
            "invoice_number": f"INV-UPW-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Pork Loin",
                    "quantity": 2,
                    "pack_weight": 5,
                    "unit": "LB",
                    "unit_price": 20.00,
                    "total": 40.00,
                    "normalized_unit_price": 4.00
                }
            ],
            "subtotal": 40.00,
            "tax": 3.20,
            "total": 43.20
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/purchases", json=create_payload)
        assert create_response.status_code == 200, f"Create purchase failed: {create_response.text}"
        purchase_id = create_response.json()["id"]
        self.created_purchase_ids.append(purchase_id)
        
        # Update purchase with new pack_weight
        update_payload = {
            "items": [
                {
                    "raw_name": "Pork Loin",
                    "quantity": 3,
                    "pack_weight": 8,  # Changed from 5 to 8
                    "unit": "KG",  # Changed from LB to KG
                    "unit_price": 25.00,  # Changed price
                    "total": 75.00,
                    "normalized_unit_price": 3.125  # 25.00 / 8 = 3.125
                }
            ],
            "subtotal": 75.00,
            "tax": 6.00,
            "total": 81.00
        }
        
        update_response = self.session.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload)
        assert update_response.status_code == 200, f"Update purchase failed: {update_response.text}"
        
        # Verify update
        get_response = self.session.get(f"{BASE_URL}/api/purchases/{purchase_id}")
        assert get_response.status_code == 200, f"Get purchase failed: {get_response.text}"
        
        data = get_response.json()
        items = data.get("items", [])
        assert len(items) == 1, "Should have 1 item"
        assert items[0]["pack_weight"] == 8, f"pack_weight should be 8, got {items[0].get('pack_weight')}"
        assert items[0]["unit"] == "KG", f"unit should be KG, got {items[0].get('unit')}"
        
        print("PASS: Update purchase with pack_weight")
    
    def test_all_unit_options(self):
        """Test that all unit options are accepted: LB, KG, OZ, EA, CS, BX, GAL, L, BAG, PK"""
        unique_id = str(uuid.uuid4())[:8]
        unit_options = ['LB', 'KG', 'OZ', 'EA', 'CS', 'BX', 'GAL', 'L', 'BAG', 'PK']
        
        items = []
        for i, unit in enumerate(unit_options):
            items.append({
                "raw_name": f"Test Item {unit}",
                "quantity": 1,
                "pack_weight": 1.0,
                "unit": unit,
                "unit_price": 10.00,
                "total": 10.00,
                "normalized_unit_price": 10.00
            })
        
        payload = {
            "supplier_name": f"TEST_AllUnits_Vendor_{unique_id}",
            "invoice_number": f"INV-AU-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": items,
            "subtotal": 100.00,
            "tax": 8.00,
            "total": 108.00
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        
        data = response.json()
        self.created_purchase_ids.append(data["id"])
        
        created_items = data.get("items", [])
        assert len(created_items) == len(unit_options), f"Should have {len(unit_options)} items"
        
        for i, item in enumerate(created_items):
            assert item["unit"] == unit_options[i], f"Item {i} unit should be {unit_options[i]}, got {item.get('unit')}"
        
        print(f"PASS: All unit options accepted: {', '.join(unit_options)}")
    
    def test_list_purchases_includes_pack_weight(self):
        """Test that listing purchases includes pack_weight data"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Create a purchase with pack_weight
        payload = {
            "supplier_name": f"TEST_ListPW_Vendor_{unique_id}",
            "invoice_number": f"INV-LPW-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": [
                {
                    "raw_name": "Ribeye Steak",
                    "quantity": 10,
                    "pack_weight": 12,
                    "unit": "OZ",
                    "unit_price": 15.00,
                    "total": 150.00,
                    "normalized_unit_price": 1.25
                }
            ],
            "subtotal": 150.00,
            "tax": 12.00,
            "total": 162.00
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert create_response.status_code == 200, f"Create purchase failed: {create_response.text}"
        purchase_id = create_response.json()["id"]
        self.created_purchase_ids.append(purchase_id)
        
        # List purchases and find our created one
        list_response = self.session.get(f"{BASE_URL}/api/purchases")
        assert list_response.status_code == 200, f"List purchases failed: {list_response.text}"
        
        purchases = list_response.json()
        our_purchase = next((p for p in purchases if p["id"] == purchase_id), None)
        assert our_purchase is not None, "Created purchase should be in list"
        
        items = our_purchase.get("items", [])
        assert len(items) == 1, "Should have 1 item"
        assert items[0]["pack_weight"] == 12, f"pack_weight should be 12, got {items[0].get('pack_weight')}"
        assert items[0]["unit"] == "OZ", f"unit should be OZ, got {items[0].get('unit')}"
        
        print("PASS: List purchases includes pack_weight data")
    
    def test_normalized_unit_price_calculation(self):
        """Test that normalized_unit_price is correctly stored (unit_price / pack_weight)"""
        unique_id = str(uuid.uuid4())[:8]
        
        test_cases = [
            {"unit_price": 50.00, "pack_weight": 10, "expected_nup": 5.00},
            {"unit_price": 25.00, "pack_weight": 5, "expected_nup": 5.00},
            {"unit_price": 100.00, "pack_weight": 4, "expected_nup": 25.00},
            {"unit_price": 15.00, "pack_weight": 3, "expected_nup": 5.00},
        ]
        
        items = []
        for i, tc in enumerate(test_cases):
            items.append({
                "raw_name": f"Test Item {i}",
                "quantity": 1,
                "pack_weight": tc["pack_weight"],
                "unit": "LB",
                "unit_price": tc["unit_price"],
                "total": tc["unit_price"],
                "normalized_unit_price": tc["expected_nup"]
            })
        
        payload = {
            "supplier_name": f"TEST_NUP_Vendor_{unique_id}",
            "invoice_number": f"INV-NUP-{unique_id}",
            "invoice_date": "2026-01-15",
            "items": items,
            "subtotal": sum(tc["unit_price"] for tc in test_cases),
            "tax": 0,
            "total": sum(tc["unit_price"] for tc in test_cases)
        }
        
        response = self.session.post(f"{BASE_URL}/api/purchases", json=payload)
        assert response.status_code == 200, f"Create purchase failed: {response.text}"
        
        data = response.json()
        self.created_purchase_ids.append(data["id"])
        
        created_items = data.get("items", [])
        for i, item in enumerate(created_items):
            expected = test_cases[i]["expected_nup"]
            actual = item.get("normalized_unit_price", 0)
            assert actual == expected, f"Item {i} normalized_unit_price should be {expected}, got {actual}"
        
        print("PASS: Normalized unit price calculation stored correctly")


class TestSalesPageNotAffected:
    """Verify Sales page is NOT affected by pack_weight changes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.created_sale_ids = []
        yield
        for sid in self.created_sale_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/sales/{sid}")
            except:
                pass
    
    def test_sales_does_not_have_pack_weight(self):
        """Test that sales endpoint does not require or return pack_weight fields"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Create a sale without pack_weight fields
        payload = {
            "report_date": "2026-01-15",
            "date_from": "2026-01-15",
            "date_to": "2026-01-15",
            "total_sales": 1500.00,
            "items": [
                {
                    "menu_item": "Burger",
                    "quantity": 50,
                    "revenue": 500.00
                },
                {
                    "menu_item": "Pizza",
                    "quantity": 40,
                    "revenue": 600.00
                }
            ]
        }
        
        response = self.session.post(f"{BASE_URL}/api/sales", json=payload)
        assert response.status_code == 200, f"Create sale failed: {response.text}"
        
        data = response.json()
        self.created_sale_ids.append(data["id"])
        
        # Verify no pack_weight fields in response
        items = data.get("items", [])
        for item in items:
            # Sales items should NOT have pack_weight or normalized_unit_price
            assert "pack_weight" not in item or item.get("pack_weight") is None, "Sales items should not have pack_weight"
        
        print("PASS: Sales endpoint does not have pack_weight fields")


class TestOtherExpensesNotAffected:
    """Verify Other Expenses page is NOT affected by pack_weight changes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.created_expense_ids = []
        yield
        for eid in self.created_expense_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/other-expenses/{eid}")
            except:
                pass
    
    def test_other_expenses_does_not_have_pack_weight(self):
        """Test that other-expenses endpoint does not require or return pack_weight fields"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Create an expense without pack_weight fields
        payload = {
            "title": f"TEST_Expense_{unique_id}",
            "category": "Utilities",
            "amount": 250.00,
            "expense_date": "2026-01-15",
            "notes": "Test expense"
        }
        
        response = self.session.post(f"{BASE_URL}/api/other-expenses", json=payload)
        assert response.status_code == 200, f"Create expense failed: {response.text}"
        
        data = response.json()
        self.created_expense_ids.append(data["id"])
        
        # Verify no pack_weight fields in response
        assert "pack_weight" not in data, "Other expenses should not have pack_weight"
        assert "normalized_unit_price" not in data, "Other expenses should not have normalized_unit_price"
        
        print("PASS: Other expenses endpoint does not have pack_weight fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
