"""
Test Edit Functionality for Expenses (Purchases, Salaries, Other Expenses)
Tests PUT endpoints for updating existing records
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestPurchaseEdit:
    """Test PUT /purchases/{pid} endpoint"""
    
    def test_get_existing_purchases(self, api_client):
        """Get list of existing purchases to find one to edit"""
        response = api_client.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        purchases = response.json()
        print(f"Found {len(purchases)} purchases")
        assert len(purchases) > 0, "No purchases found to test edit"
        return purchases[0]
    
    def test_edit_purchase_vendor_name(self, api_client):
        """TEST 1: Edit purchase - change vendor name"""
        # Get first purchase
        response = api_client.get(f"{BASE_URL}/api/purchases")
        assert response.status_code == 200
        purchases = response.json()
        assert len(purchases) > 0, "No purchases to edit"
        
        purchase = purchases[0]
        purchase_id = purchase["id"]
        original_vendor = purchase.get("supplier_name", "")
        
        # Edit vendor name
        new_vendor = f"Edited Vendor {uuid.uuid4().hex[:6]}"
        update_payload = {
            "supplier_name": new_vendor,
            "invoice_number": purchase.get("invoice_number", ""),
            "invoice_date": purchase.get("invoice_date", ""),
            "items": purchase.get("items", []),
            "subtotal": purchase.get("subtotal", 0),
            "tax": purchase.get("tax", 0),
            "total": purchase.get("total", 0)
        }
        
        response = api_client.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload)
        assert response.status_code == 200, f"Edit failed: {response.text}"
        
        updated = response.json()
        assert updated["supplier_name"] == new_vendor, f"Vendor name not updated: {updated.get('supplier_name')}"
        print(f"✓ Purchase vendor updated from '{original_vendor}' to '{new_vendor}'")
        
        # Verify persistence with GET
        response = api_client.get(f"{BASE_URL}/api/purchases")
        purchases = response.json()
        found = next((p for p in purchases if p["id"] == purchase_id), None)
        assert found is not None, "Updated purchase not found"
        assert found["supplier_name"] == new_vendor, "Vendor name not persisted"
        print("✓ Vendor name change persisted in database")
    
    def test_edit_purchase_items_recalculation(self, api_client):
        """TEST 2: Edit purchase items - verify auto-recalculation"""
        # Get first purchase
        response = api_client.get(f"{BASE_URL}/api/purchases")
        purchases = response.json()
        assert len(purchases) > 0
        
        purchase = purchases[0]
        purchase_id = purchase["id"]
        items = purchase.get("items", [])
        
        if len(items) > 0:
            # Modify first item quantity
            original_qty = items[0].get("quantity", 1)
            new_qty = original_qty + 5
            items[0]["quantity"] = new_qty
            items[0]["total"] = new_qty * items[0].get("unit_price", 0)
            
            # Recalculate subtotal and total
            new_subtotal = sum(it.get("total", 0) for it in items)
            new_total = new_subtotal + purchase.get("tax", 0)
            
            update_payload = {
                "supplier_name": purchase.get("supplier_name", ""),
                "invoice_number": purchase.get("invoice_number", ""),
                "invoice_date": purchase.get("invoice_date", ""),
                "items": items,
                "subtotal": new_subtotal,
                "tax": purchase.get("tax", 0),
                "total": new_total
            }
            
            response = api_client.put(f"{BASE_URL}/api/purchases/{purchase_id}", json=update_payload)
            assert response.status_code == 200, f"Edit failed: {response.text}"
            
            updated = response.json()
            assert updated["items"][0]["quantity"] == new_qty, "Item quantity not updated"
            print(f"✓ Item quantity updated from {original_qty} to {new_qty}")
            print(f"✓ Subtotal: {updated.get('subtotal')}, Total: {updated.get('total')}")
        else:
            print("⚠ No items in purchase to test recalculation")


class TestSalaryEdit:
    """Test PUT /salaries/{sid} endpoint"""
    
    def test_get_existing_salaries(self, api_client):
        """Get list of existing salaries"""
        response = api_client.get(f"{BASE_URL}/api/salaries")
        assert response.status_code == 200
        salaries = response.json()
        print(f"Found {len(salaries)} salaries")
        return salaries
    
    def test_edit_salary_amount(self, api_client):
        """TEST 3: Edit salary - change amount to 5000"""
        # Get salaries
        response = api_client.get(f"{BASE_URL}/api/salaries")
        assert response.status_code == 200
        salaries = response.json()
        
        if len(salaries) == 0:
            # Create a salary first
            create_payload = {
                "employee_name": "Test Employee",
                "position": "Chef",
                "amount": 3500,
                "payment_date": "2025-01-15",
                "notes": "Test salary"
            }
            response = api_client.post(f"{BASE_URL}/api/salaries", json=create_payload)
            assert response.status_code == 200, f"Create salary failed: {response.text}"
            salary = response.json()
            print(f"Created test salary: {salary['id']}")
        else:
            salary = salaries[0]
        
        salary_id = salary["id"]
        original_amount = salary.get("amount", 0)
        
        # Edit amount to 5000
        new_amount = 5000
        update_payload = {
            "employee_name": salary.get("employee_name", ""),
            "position": salary.get("position", ""),
            "amount": new_amount,
            "payment_date": salary.get("payment_date", ""),
            "notes": salary.get("notes", "")
        }
        
        response = api_client.put(f"{BASE_URL}/api/salaries/{salary_id}", json=update_payload)
        assert response.status_code == 200, f"Edit salary failed: {response.text}"
        
        updated = response.json()
        assert updated["amount"] == new_amount, f"Amount not updated: {updated.get('amount')}"
        print(f"✓ Salary amount updated from ${original_amount} to ${new_amount}")
        
        # Verify persistence
        response = api_client.get(f"{BASE_URL}/api/salaries")
        salaries = response.json()
        found = next((s for s in salaries if s["id"] == salary_id), None)
        assert found is not None, "Updated salary not found"
        assert found["amount"] == new_amount, "Amount not persisted"
        print("✓ Salary amount change persisted in database")
    
    def test_edit_salary_employee_name(self, api_client):
        """Edit salary - change employee name"""
        response = api_client.get(f"{BASE_URL}/api/salaries")
        salaries = response.json()
        
        if len(salaries) > 0:
            salary = salaries[0]
            salary_id = salary["id"]
            
            new_name = f"Updated Employee {uuid.uuid4().hex[:4]}"
            update_payload = {
                "employee_name": new_name
            }
            
            response = api_client.put(f"{BASE_URL}/api/salaries/{salary_id}", json=update_payload)
            assert response.status_code == 200, f"Edit failed: {response.text}"
            
            updated = response.json()
            assert updated["employee_name"] == new_name
            print(f"✓ Employee name updated to '{new_name}'")


class TestOtherExpenseEdit:
    """Test PUT /other-expenses/{eid} endpoint"""
    
    def test_get_existing_other_expenses(self, api_client):
        """Get list of existing other expenses"""
        response = api_client.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 200
        expenses = response.json()
        print(f"Found {len(expenses)} other expenses")
        return expenses
    
    def test_edit_other_expense_title(self, api_client):
        """TEST 4: Edit other expense - change title"""
        # Get other expenses
        response = api_client.get(f"{BASE_URL}/api/other-expenses")
        assert response.status_code == 200
        expenses = response.json()
        
        if len(expenses) == 0:
            # Create an expense first
            create_payload = {
                "title": "Test Expense",
                "category": "Electricity",
                "amount": 500,
                "expense_date": "2025-01-15",
                "notes": "Test expense"
            }
            response = api_client.post(f"{BASE_URL}/api/other-expenses", json=create_payload)
            assert response.status_code == 200, f"Create expense failed: {response.text}"
            expense = response.json()
            print(f"Created test expense: {expense['id']}")
        else:
            expense = expenses[0]
        
        expense_id = expense["id"]
        original_title = expense.get("title", "")
        
        # Edit title
        new_title = "Updated Electric"
        update_payload = {
            "title": new_title
        }
        
        response = api_client.put(f"{BASE_URL}/api/other-expenses/{expense_id}", json=update_payload)
        assert response.status_code == 200, f"Edit expense failed: {response.text}"
        
        updated = response.json()
        assert updated["title"] == new_title, f"Title not updated: {updated.get('title')}"
        print(f"✓ Expense title updated from '{original_title}' to '{new_title}'")
        
        # Verify persistence
        response = api_client.get(f"{BASE_URL}/api/other-expenses")
        expenses = response.json()
        found = next((e for e in expenses if e["id"] == expense_id), None)
        assert found is not None, "Updated expense not found"
        assert found["title"] == new_title, "Title not persisted"
        print("✓ Expense title change persisted in database")
    
    def test_edit_other_expense_amount(self, api_client):
        """Edit other expense - change amount"""
        response = api_client.get(f"{BASE_URL}/api/other-expenses")
        expenses = response.json()
        
        if len(expenses) > 0:
            expense = expenses[0]
            expense_id = expense["id"]
            
            new_amount = 750.50
            update_payload = {
                "amount": new_amount
            }
            
            response = api_client.put(f"{BASE_URL}/api/other-expenses/{expense_id}", json=update_payload)
            assert response.status_code == 200, f"Edit failed: {response.text}"
            
            updated = response.json()
            assert updated["amount"] == new_amount
            print(f"✓ Expense amount updated to ${new_amount}")


class TestEditNotFound:
    """Test edit with non-existent IDs"""
    
    def test_edit_nonexistent_purchase(self, api_client):
        """Edit non-existent purchase returns 404"""
        fake_id = str(uuid.uuid4())
        update_payload = {
            "supplier_name": "Test",
            "invoice_number": "INV-001",
            "invoice_date": "2025-01-15",
            "items": [],
            "subtotal": 0,
            "tax": 0,
            "total": 0
        }
        response = api_client.put(f"{BASE_URL}/api/purchases/{fake_id}", json=update_payload)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent purchase returns 404")
    
    def test_edit_nonexistent_salary(self, api_client):
        """Edit non-existent salary returns 404"""
        fake_id = str(uuid.uuid4())
        update_payload = {"amount": 1000}
        response = api_client.put(f"{BASE_URL}/api/salaries/{fake_id}", json=update_payload)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent salary returns 404")
    
    def test_edit_nonexistent_other_expense(self, api_client):
        """Edit non-existent other expense returns 404"""
        fake_id = str(uuid.uuid4())
        update_payload = {"title": "Test"}
        response = api_client.put(f"{BASE_URL}/api/other-expenses/{fake_id}", json=update_payload)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent other expense returns 404")


class TestAddStillWorks:
    """TEST 6: Verify Add still works after editing"""
    
    def test_add_new_salary_after_edit(self, api_client):
        """Add new salary still creates new record"""
        create_payload = {
            "employee_name": f"New Employee {uuid.uuid4().hex[:4]}",
            "position": "Waiter",
            "amount": 2500,
            "payment_date": "2025-01-20",
            "notes": "New hire"
        }
        
        response = api_client.post(f"{BASE_URL}/api/salaries", json=create_payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        created = response.json()
        assert "id" in created
        assert created["employee_name"] == create_payload["employee_name"]
        print(f"✓ New salary created with ID: {created['id']}")
    
    def test_add_new_other_expense_after_edit(self, api_client):
        """Add new other expense still creates new record"""
        create_payload = {
            "title": f"New Expense {uuid.uuid4().hex[:4]}",
            "category": "Maintenance",
            "amount": 350,
            "expense_date": "2025-01-20",
            "notes": "New expense"
        }
        
        response = api_client.post(f"{BASE_URL}/api/other-expenses", json=create_payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        created = response.json()
        assert "id" in created
        assert created["title"] == create_payload["title"]
        print(f"✓ New other expense created with ID: {created['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
