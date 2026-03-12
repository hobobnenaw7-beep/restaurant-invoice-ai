"""
Tests for Upload Excel feature - parsing CSV, XLSX files for purchases and sales
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestExcelUpload:
    """Test /api/upload/parse-excel endpoint for CSV and XLSX parsing"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token before each test"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    # =========== CSV Purchase Tests ===========
    def test_parse_csv_purchase_invoice_status(self):
        """Test CSV parsing for purchase_invoice returns 200"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_parse_csv_purchase_extracts_supplier(self):
        """Test CSV parsing extracts supplier name correctly"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()
        assert "extracted_data" in data
        assert data["extracted_data"]["supplier_name"] == "Fresh Farms"
    
    def test_parse_csv_purchase_extracts_items(self):
        """Test CSV parsing extracts items array with correct structure"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()["extracted_data"]
        items = data["items"]
        assert len(items) == 3, f"Expected 3 items in first group, got {len(items)}"
        # Check first item structure
        assert items[0]["raw_name"] == "Tomatoes"
        assert items[0]["quantity"] == 25.0
        assert items[0]["unit"] == "kg"
        assert items[0]["unit_price"] == 3.5
        assert items[0]["total"] == 87.5
    
    def test_parse_csv_purchase_groups_multiple_suppliers(self):
        """Test CSV parsing detects multiple supplier groups"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()
        # CSV has 2 suppliers: Fresh Farms (3 items), City Meats (2 items)
        assert data.get("purchase_groups") == 2, f"Expected 2 purchase groups, got {data.get('purchase_groups')}"
        assert data.get("row_count") == 5, f"Expected 5 total items, got {data.get('row_count')}"
        assert "message" in data, "Should have message about multiple purchases"
    
    def test_parse_csv_purchase_calculates_totals(self):
        """Test CSV parsing calculates subtotal and total correctly"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()["extracted_data"]
        # Fresh Farms total: 87.50 + 42.00 + 60.00 = 189.50
        assert data["subtotal"] == 189.5, f"Expected subtotal 189.5, got {data['subtotal']}"
        assert data["total"] == 189.5, f"Expected total 189.5, got {data['total']}"
    
    # =========== XLSX Purchase Tests ===========
    def test_parse_xlsx_purchase_invoice_status(self):
        """Test XLSX parsing for purchase_invoice returns 200"""
        with open('/tmp/test_purchases.xlsx', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"document_type": "purchase_invoice"}
            )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_parse_xlsx_purchase_extracts_data(self):
        """Test XLSX parsing extracts supplier and items correctly"""
        with open('/tmp/test_purchases.xlsx', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()["extracted_data"]
        assert data["supplier_name"] == "Ocean Foods"
        assert data["invoice_number"] == "INV-601"
        assert data["invoice_date"] == "2026-03-11"
        assert len(data["items"]) == 3
    
    def test_parse_xlsx_purchase_maps_column_headers(self):
        """Test XLSX correctly maps column headers with spaces (e.g., 'Item Name' -> item_name)"""
        with open('/tmp/test_purchases.xlsx', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"document_type": "purchase_invoice"}
            )
        data = response.json()["extracted_data"]
        items = data["items"]
        # Verify each item has correct fields from header mapping
        for item in items:
            assert "raw_name" in item, "item_name should map to raw_name"
            assert "quantity" in item, "quantity column should map"
            assert "unit" in item, "unit column should map"
            assert "unit_price" in item, "price column should map to unit_price"
            assert "total" in item, "total column should map"
    
    # =========== CSV Sales Tests ===========
    def test_parse_csv_sales_report_status(self):
        """Test CSV parsing for sales_report returns 200"""
        with open('/tmp/test_sales.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_sales.csv", f, "text/csv")},
                data={"document_type": "sales_report"}
            )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_parse_csv_sales_extracts_items(self):
        """Test CSV parsing extracts sales items with menu_item field"""
        with open('/tmp/test_sales.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_sales.csv", f, "text/csv")},
                data={"document_type": "sales_report"}
            )
        data = response.json()["extracted_data"]
        assert len(data["items"]) == 3
        # Check first sales item
        assert data["items"][0]["menu_item"] == "Grilled Salmon"
        assert data["items"][0]["quantity"] == 45.0
        assert data["items"][0]["revenue"] == 675.0
    
    def test_parse_csv_sales_calculates_total(self):
        """Test CSV parsing calculates total_sales correctly"""
        with open('/tmp/test_sales.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_sales.csv", f, "text/csv")},
                data={"document_type": "sales_report"}
            )
        data = response.json()["extracted_data"]
        # Total: 675 + 256 + 336 = 1267
        assert data["total_sales"] == 1267.0, f"Expected 1267.0, got {data['total_sales']}"
    
    def test_parse_csv_sales_extracts_date(self):
        """Test CSV parsing extracts report_date correctly"""
        with open('/tmp/test_sales.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_sales.csv", f, "text/csv")},
                data={"document_type": "sales_report"}
            )
        data = response.json()["extracted_data"]
        assert data["report_date"] == "2026-03-10"
    
    # =========== Error Handling Tests ===========
    def test_parse_unsupported_file_type(self):
        """Test that unsupported file types return 400"""
        fake_txt = io.BytesIO(b"just some text")
        response = requests.post(
            f"{BASE_URL}/api/upload/parse-excel",
            headers=self.headers,
            files={"file": ("test.txt", fake_txt, "text/plain")},
            data={"document_type": "purchase_invoice"}
        )
        assert response.status_code == 400, f"Expected 400 for unsupported file, got {response.status_code}"
    
    def test_parse_excel_requires_auth(self):
        """Test that parse-excel endpoint requires authentication"""
        with open('/tmp/test_purchases.csv', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                # No auth header
                files={"file": ("test.csv", f, "text/csv")},
                data={"document_type": "purchase_invoice"}
            )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"


class TestSavePurchaseFromExcel:
    """Test creating purchase from extracted Excel data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@demo.com",
            "password": "password123"
        })
        assert login_response.status_code == 200
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_create_purchase_from_excel_data(self):
        """Test full flow: parse Excel -> create purchase -> verify persistence"""
        # Step 1: Parse Excel
        with open('/tmp/test_purchases.xlsx', 'rb') as f:
            parse_response = requests.post(
                f"{BASE_URL}/api/upload/parse-excel",
                headers=self.headers,
                files={"file": ("test_purchases.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"document_type": "purchase_invoice"}
            )
        assert parse_response.status_code == 200
        extracted = parse_response.json()["extracted_data"]
        
        # Step 2: Create purchase with extracted data
        purchase_data = {
            "supplier_name": extracted["supplier_name"],
            "invoice_number": f"TEST_EXCEL_{extracted['invoice_number']}",  # Prefix for cleanup
            "invoice_date": extracted["invoice_date"],
            "items": extracted["items"],
            "subtotal": extracted["subtotal"],
            "tax": extracted["tax"],
            "total": extracted["total"]
        }
        create_response = requests.post(
            f"{BASE_URL}/api/purchases",
            headers={**self.headers, "Content-Type": "application/json"},
            json=purchase_data
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        created = create_response.json()
        purchase_id = created["id"]
        
        # Step 3: Verify persistence
        get_response = requests.get(
            f"{BASE_URL}/api/purchases/{purchase_id}",
            headers=self.headers
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["supplier_name"] == "Ocean Foods"
        assert len(fetched["items"]) == 3
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/purchases/{purchase_id}", headers=self.headers)
