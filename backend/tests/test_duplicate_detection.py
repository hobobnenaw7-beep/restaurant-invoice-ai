"""
Test suite for Duplicate Detection Feature
Tests POST /api/duplicates/check endpoint for all record types: purchase, sale, salary, other_expense
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"

class TestDuplicateDetection:
    """Duplicate detection API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
    # ========== PURCHASE DUPLICATE TESTS ==========
    
    def test_purchase_duplicate_by_invoice_number(self):
        """Test: Detect duplicate purchase by invoice number"""
        # First, get existing purchases to find an invoice number
        purchases_res = self.session.get(f"{BASE_URL}/api/purchases")
        assert purchases_res.status_code == 200
        purchases = purchases_res.json()
        
        if not purchases:
            pytest.skip("No existing purchases to test duplicate detection")
        
        # Use an existing invoice number
        existing = purchases[0]
        existing_invoice = existing.get("invoice_number", "")
        
        if not existing_invoice:
            pytest.skip("No invoice number in existing purchase")
        
        # Check for duplicate with same invoice number
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "purchase",
            "data": {
                "invoice_number": existing_invoice,
                "supplier_name": "Test Vendor",
                "invoice_date": "2026-01-15",
                "total": 100.00
            }
        })
        
        assert check_res.status_code == 200, f"Duplicate check failed: {check_res.text}"
        data = check_res.json()
        assert "has_duplicates" in data
        assert data["has_duplicates"] == True, "Should detect duplicate by invoice number"
        assert "matches" in data
        assert len(data["matches"]) > 0, "Should have at least one match"
        # Verify match type
        match = data["matches"][0]
        assert "reason" in match
        assert "invoice_number" in match.get("match_type", "") or existing_invoice.lower() in match.get("reason", "").lower()
        print(f"SUCCESS: Detected duplicate purchase by invoice number '{existing_invoice}'")
    
    def test_purchase_duplicate_by_vendor_date_amount(self):
        """Test: Detect duplicate purchase by vendor + date + amount"""
        # Get existing purchases
        purchases_res = self.session.get(f"{BASE_URL}/api/purchases")
        assert purchases_res.status_code == 200
        purchases = purchases_res.json()
        
        if not purchases:
            pytest.skip("No existing purchases to test")
        
        existing = purchases[0]
        vendor = existing.get("supplier_name", "")
        date = existing.get("invoice_date", "")
        total = existing.get("total", 0)
        
        if not vendor or not date or not total:
            pytest.skip("Existing purchase missing required fields")
        
        # Check for duplicate with same vendor/date/amount but different invoice
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "purchase",
            "data": {
                "invoice_number": "UNIQUE-" + str(uuid.uuid4())[:8],  # Different invoice
                "supplier_name": vendor,
                "invoice_date": date,
                "total": total
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == True, "Should detect duplicate by vendor+date+amount"
        print(f"SUCCESS: Detected duplicate purchase by vendor '{vendor}', date '{date}', amount ${total}")
    
    def test_purchase_unique_record_no_duplicates(self):
        """Test: Unique purchase should return no duplicates"""
        unique_invoice = f"UNIQUE-TEST-{uuid.uuid4()}"
        
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "purchase",
            "data": {
                "invoice_number": unique_invoice,
                "supplier_name": "Completely New Vendor " + str(uuid.uuid4())[:8],
                "invoice_date": "2099-12-31",
                "total": 999999.99
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == False, "Unique purchase should not detect duplicates"
        assert len(data.get("matches", [])) == 0, "Matches should be empty for unique record"
        print(f"SUCCESS: Unique purchase correctly returns has_duplicates=false")
    
    # ========== SALE DUPLICATE TESTS ==========
    
    def test_sale_duplicate_by_date(self):
        """Test: Detect duplicate sale by date"""
        # Get existing sales
        sales_res = self.session.get(f"{BASE_URL}/api/sales")
        assert sales_res.status_code == 200
        sales = sales_res.json()
        
        if not sales:
            pytest.skip("No existing sales to test")
        
        existing = sales[0]
        report_date = existing.get("report_date", "")
        
        if not report_date:
            pytest.skip("Existing sale missing report_date")
        
        # Check for duplicate with same date
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "sale",
            "data": {
                "report_date": report_date,
                "total_sales": 1000.00  # Different amount
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == True, f"Should detect duplicate sale for date {report_date}"
        assert len(data["matches"]) > 0
        print(f"SUCCESS: Detected duplicate sale by date '{report_date}'")
    
    def test_sale_unique_date_no_duplicates(self):
        """Test: Sale with unique date should not detect duplicates"""
        unique_date = "2099-12-31"
        
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "sale",
            "data": {
                "report_date": unique_date,
                "total_sales": 1000.00
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == False, "Unique date should not detect duplicates"
        print(f"SUCCESS: Unique sale date correctly returns has_duplicates=false")
    
    # ========== SALARY DUPLICATE TESTS ==========
    
    def test_salary_duplicate_by_employee_date(self):
        """Test: Detect duplicate salary by employee + date"""
        # Get existing salaries
        salaries_res = self.session.get(f"{BASE_URL}/api/salaries")
        assert salaries_res.status_code == 200
        salaries = salaries_res.json()
        
        if not salaries:
            pytest.skip("No existing salaries to test")
        
        existing = salaries[0]
        employee = existing.get("employee_name", "")
        pay_date = existing.get("payment_date", "")
        
        if not employee or not pay_date:
            pytest.skip("Existing salary missing required fields")
        
        # Check for duplicate with same employee + date
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "salary",
            "data": {
                "employee_name": employee,
                "payment_date": pay_date,
                "amount": 5000.00  # Different amount
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == True, f"Should detect duplicate salary for {employee} on {pay_date}"
        print(f"SUCCESS: Detected duplicate salary by employee '{employee}' and date '{pay_date}'")
    
    def test_salary_unique_employee_date_no_duplicates(self):
        """Test: Salary with unique employee+date should not detect duplicates"""
        unique_employee = f"TEST-EMPLOYEE-{uuid.uuid4()}"
        
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "salary",
            "data": {
                "employee_name": unique_employee,
                "payment_date": "2099-12-31",
                "amount": 5000.00
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == False, "Unique employee+date should not detect duplicates"
        print(f"SUCCESS: Unique salary correctly returns has_duplicates=false")
    
    # ========== OTHER EXPENSE DUPLICATE TESTS ==========
    
    def test_other_expense_duplicate_by_title_date(self):
        """Test: Detect duplicate other expense by title + date"""
        # Get existing other expenses
        expenses_res = self.session.get(f"{BASE_URL}/api/other-expenses")
        assert expenses_res.status_code == 200
        expenses = expenses_res.json()
        
        if not expenses:
            pytest.skip("No existing other expenses to test")
        
        existing = expenses[0]
        title = existing.get("title", "")
        exp_date = existing.get("expense_date", "")
        
        if not title or not exp_date:
            pytest.skip("Existing expense missing required fields")
        
        # Check for duplicate with same title + date
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "other_expense",
            "data": {
                "title": title,
                "expense_date": exp_date,
                "amount": 999.99  # Different amount
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == True, f"Should detect duplicate expense for '{title}' on {exp_date}"
        print(f"SUCCESS: Detected duplicate other expense by title '{title}' and date '{exp_date}'")
    
    def test_other_expense_unique_title_date_no_duplicates(self):
        """Test: Other expense with unique title+date should not detect duplicates"""
        unique_title = f"TEST-EXPENSE-{uuid.uuid4()}"
        
        check_res = self.session.post(f"{BASE_URL}/api/duplicates/check", json={
            "record_type": "other_expense",
            "data": {
                "title": unique_title,
                "expense_date": "2099-12-31",
                "amount": 500.00
            }
        })
        
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["has_duplicates"] == False, "Unique title+date should not detect duplicates"
        print(f"SUCCESS: Unique other expense correctly returns has_duplicates=false")
    
    # ========== CRUD STILL WORKS TESTS ==========
    
    def test_purchase_crud_still_works(self):
        """Test: Existing purchase CRUD functionality still works"""
        # Create
        create_data = {
            "supplier_name": "TEST_DuplicateTest_Vendor",
            "invoice_number": f"TEST-DUP-{str(uuid.uuid4())[:8]}",
            "invoice_date": "2026-01-15",
            "items": [{"raw_name": "Test Item", "quantity": 1, "unit": "kg", "unit_price": 10.00, "total": 10.00}],
            "subtotal": 10.00,
            "tax": 0.00,
            "total": 10.00
        }
        create_res = self.session.post(f"{BASE_URL}/api/purchases", json=create_data)
        assert create_res.status_code == 200, f"Create purchase failed: {create_res.text}"
        created = create_res.json()
        assert "id" in created
        
        # Read
        get_res = self.session.get(f"{BASE_URL}/api/purchases/{created['id']}")
        assert get_res.status_code == 200
        
        # Delete (cleanup)
        del_res = self.session.delete(f"{BASE_URL}/api/purchases/{created['id']}")
        assert del_res.status_code == 200
        print("SUCCESS: Purchase CRUD operations still work correctly")
    
    def test_sale_crud_still_works(self):
        """Test: Existing sale CRUD functionality still works"""
        create_data = {
            "report_date": "2099-06-15",
            "total_sales": 1500.00,
            "items": []
        }
        create_res = self.session.post(f"{BASE_URL}/api/sales", json=create_data)
        assert create_res.status_code == 200, f"Create sale failed: {create_res.text}"
        created = create_res.json()
        
        # Delete (cleanup)
        del_res = self.session.delete(f"{BASE_URL}/api/sales/{created['id']}")
        assert del_res.status_code == 200
        print("SUCCESS: Sale CRUD operations still work correctly")
    
    def test_salary_crud_still_works(self):
        """Test: Existing salary CRUD functionality still works"""
        create_data = {
            "employee_name": "TEST_DuplicateTest_Employee",
            "position": "Tester",
            "amount": 3000.00,
            "payment_date": "2099-06-15",
            "notes": ""
        }
        create_res = self.session.post(f"{BASE_URL}/api/salaries", json=create_data)
        assert create_res.status_code == 200, f"Create salary failed: {create_res.text}"
        created = create_res.json()
        
        # Delete (cleanup)
        del_res = self.session.delete(f"{BASE_URL}/api/salaries/{created['id']}")
        assert del_res.status_code == 200
        print("SUCCESS: Salary CRUD operations still work correctly")
    
    def test_other_expense_crud_still_works(self):
        """Test: Existing other expense CRUD functionality still works"""
        create_data = {
            "title": "TEST_DuplicateTest_Expense",
            "category": "Other",
            "amount": 250.00,
            "expense_date": "2099-06-15",
            "notes": ""
        }
        create_res = self.session.post(f"{BASE_URL}/api/other-expenses", json=create_data)
        assert create_res.status_code == 200, f"Create other expense failed: {create_res.text}"
        created = create_res.json()
        
        # Delete (cleanup)
        del_res = self.session.delete(f"{BASE_URL}/api/other-expenses/{created['id']}")
        assert del_res.status_code == 200
        print("SUCCESS: Other expense CRUD operations still work correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
