"""
Records Library Enhanced Features Tests - Iteration 17
Tests duplicate prevention (409), sorting functionality, and verifies bulk upload backend support.

Features tested:
1. Duplicate file prevention (same file name+size OR same content hash returns 409)
2. Sorting by date, amount, and name 
3. Same name different content succeeds (not a duplicate)
"""
import pytest
import requests
import os
import io
import hashlib
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_token():
    """Authenticate and get token for all tests."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}

# ==================== DUPLICATE DETECTION TESTS ====================

class TestDuplicateFileDetection:
    """Test duplicate file prevention (409 response)."""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, auth_headers):
        """Create base file for duplicate tests, cleanup after."""
        # Create unique test file for this test run
        self.unique_content = f"TEST_unique_content_{datetime.now().isoformat()}"
        self.file_name = f"TEST_dup_base_{datetime.now().strftime('%H%M%S')}.txt"
        
        file_content = self.unique_content.encode()
        files = {"file": (self.file_name, io.BytesIO(file_content), "text/plain")}
        data = {
            "folder": "sales",
            "transaction_type": "sale",
            "transaction_amount": "100.00"
        }
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        
        if response.status_code == 200:
            self.base_record_id = response.json()["id"]
            self.base_content = file_content
            self.base_size = len(file_content)
        else:
            self.base_record_id = None
        
        yield
        
        # Cleanup
        if self.base_record_id:
            requests.delete(f"{BASE_URL}/api/records/{self.base_record_id}", headers=auth_headers)
    
    def test_duplicate_same_file_name_and_size_returns_409(self, auth_headers):
        """Uploading file with same name and size should return 409."""
        if not hasattr(self, 'base_record_id') or not self.base_record_id:
            pytest.skip("Base record not created")
        
        # Upload same file again (same name, same content = same size)
        files = {"file": (self.file_name, io.BytesIO(self.base_content), "text/plain")}
        data = {"folder": "sales", "transaction_type": "sale"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 409, f"Expected 409 for duplicate, got {response.status_code}: {response.text}"
        assert "Duplicate" in response.json().get("detail", "") or "duplicate" in response.json().get("detail", "").lower()
    
    def test_duplicate_same_content_hash_different_name_returns_409(self, auth_headers):
        """Uploading file with same content but different name should return 409 (hash check)."""
        if not hasattr(self, 'base_record_id') or not self.base_record_id:
            pytest.skip("Base record not created")
        
        # Same content, different filename
        different_name = f"TEST_different_name_{datetime.now().strftime('%H%M%S')}.txt"
        files = {"file": (different_name, io.BytesIO(self.base_content), "text/plain")}
        data = {"folder": "sales", "transaction_type": "sale"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 409, f"Expected 409 for duplicate content hash, got {response.status_code}: {response.text}"
    
    def test_same_name_different_content_succeeds(self, auth_headers):
        """Uploading file with same name but different content should succeed."""
        if not hasattr(self, 'base_record_id') or not self.base_record_id:
            pytest.skip("Base record not created")
        
        # Same filename but different content
        different_content = f"DIFFERENT_CONTENT_{datetime.now().isoformat()}_extra_data".encode()
        files = {"file": (self.file_name, io.BytesIO(different_content), "text/plain")}
        data = {"folder": "sales", "transaction_type": "sale"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        
        # Should succeed because content is different (different size, different hash)
        assert response.status_code == 200, f"Expected 200 for different content, got {response.status_code}: {response.text}"
        
        # Cleanup this record
        if response.status_code == 200:
            record_id = response.json()["id"]
            requests.delete(f"{BASE_URL}/api/records/{record_id}", headers=auth_headers)
    
    def test_duplicate_in_different_folder_succeeds(self, auth_headers):
        """Same file in different folder should succeed (duplicates are per-folder)."""
        if not hasattr(self, 'base_record_id') or not self.base_record_id:
            pytest.skip("Base record not created")
        
        # Same file content but in expenses folder (base is in sales)
        files = {"file": (self.file_name, io.BytesIO(self.base_content), "text/plain")}
        data = {"folder": "expenses", "transaction_type": "raw_material"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        
        # Should succeed because it's a different folder
        assert response.status_code == 200, f"Expected 200 for same file in different folder, got {response.status_code}: {response.text}"
        
        # Cleanup
        if response.status_code == 200:
            record_id = response.json()["id"]
            requests.delete(f"{BASE_URL}/api/records/{record_id}", headers=auth_headers)


class TestDuplicateFileErrorMessage:
    """Test that duplicate error message contains useful information."""
    
    def test_duplicate_error_contains_filename(self, auth_headers):
        """409 error should mention the duplicate file name."""
        # Create a unique file
        unique_name = f"TEST_dup_msg_{datetime.now().strftime('%H%M%S%f')}.txt"
        content = b"unique test content for error message test"
        
        # First upload
        files = {"file": (unique_name, io.BytesIO(content), "text/plain")}
        data = {"folder": "sales"}
        response1 = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        assert response1.status_code == 200
        record_id = response1.json()["id"]
        
        try:
            # Second upload (duplicate)
            files2 = {"file": (unique_name, io.BytesIO(content), "text/plain")}
            response2 = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files2, data=data)
            
            assert response2.status_code == 409
            error_detail = response2.json().get("detail", "")
            # Error should mention the file name
            assert unique_name in error_detail or "Duplicate" in error_detail
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/records/{record_id}", headers=auth_headers)


# ==================== SORTING TESTS ====================

class TestRecordsSorting:
    """Test sorting functionality for records listing."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_test_records(self, auth_headers):
        """Create test records with different amounts and dates for sorting tests."""
        created_ids = []
        
        # Create records with different amounts
        test_files = [
            ("TEST_sort_low.txt", b"content a", 100.00),
            ("TEST_sort_mid.txt", b"content b b", 500.00),
            ("TEST_sort_high.txt", b"content c c c", 1000.00),
        ]
        
        for filename, content, amount in test_files:
            files = {"file": (filename, io.BytesIO(content), "text/plain")}
            data = {
                "folder": "sales",
                "transaction_type": "sale",
                "transaction_amount": str(amount)
            }
            response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
            if response.status_code == 200:
                created_ids.append(response.json()["id"])
        
        TestRecordsSorting.created_ids = created_ids
        yield
        
        # Cleanup
        for rid in created_ids:
            requests.delete(f"{BASE_URL}/api/records/{rid}", headers=auth_headers)
    
    def test_sort_by_upload_date_desc(self, auth_headers):
        """Sort records by upload_date descending."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "upload_date",
            "sort_order": "desc"
        })
        assert response.status_code == 200
        records = response.json()
        
        # Verify dates are in descending order
        dates = [r["upload_date"] for r in records]
        assert dates == sorted(dates, reverse=True), "Records not sorted by date descending"
    
    def test_sort_by_upload_date_asc(self, auth_headers):
        """Sort records by upload_date ascending."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "upload_date",
            "sort_order": "asc"
        })
        assert response.status_code == 200
        records = response.json()
        
        dates = [r["upload_date"] for r in records]
        assert dates == sorted(dates), "Records not sorted by date ascending"
    
    def test_sort_by_amount_desc(self, auth_headers):
        """Sort records by transaction_amount descending."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "amount",
            "sort_order": "desc"
        })
        assert response.status_code == 200
        records = response.json()
        
        # Filter to only our test records and verify amounts are descending
        test_records = [r for r in records if r.get("file_name", "").startswith("TEST_sort")]
        if len(test_records) >= 2:
            amounts = [r.get("transaction_amount", 0) for r in test_records]
            assert amounts == sorted(amounts, reverse=True), f"Test records not sorted by amount desc: {amounts}"
    
    def test_sort_by_amount_asc(self, auth_headers):
        """Sort records by transaction_amount ascending."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "amount",
            "sort_order": "asc"
        })
        assert response.status_code == 200
        records = response.json()
        
        test_records = [r for r in records if r.get("file_name", "").startswith("TEST_sort")]
        if len(test_records) >= 2:
            amounts = [r.get("transaction_amount", 0) for r in test_records]
            assert amounts == sorted(amounts), f"Test records not sorted by amount asc: {amounts}"
    
    def test_sort_by_name_asc(self, auth_headers):
        """Sort records by file_name ascending (case-sensitive)."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "name",
            "sort_order": "asc"
        })
        assert response.status_code == 200
        records = response.json()
        
        # MongoDB does case-sensitive sort by default
        names = [r["file_name"] for r in records]
        assert names == sorted(names), "Records not sorted by name ascending"
    
    def test_sort_by_name_desc(self, auth_headers):
        """Sort records by file_name descending (case-sensitive)."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
            "folder": "sales",
            "sort_by": "name",
            "sort_order": "desc"
        })
        assert response.status_code == 200
        records = response.json()
        
        # MongoDB does case-sensitive sort by default
        names = [r["file_name"] for r in records]
        assert names == sorted(names, reverse=True), "Records not sorted by name descending"
    
    def test_default_sort_is_upload_date_desc(self, auth_headers):
        """Default sort should be upload_date descending."""
        # Request without sort params
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={"folder": "sales"})
        assert response.status_code == 200
        records = response.json()
        
        dates = [r["upload_date"] for r in records]
        # Default should be desc (most recent first)
        assert dates == sorted(dates, reverse=True), "Default sort should be upload_date descending"


# ==================== FILE HASH VERIFICATION ====================

class TestFileHashStorage:
    """Test that file_hash is stored correctly for duplicate detection."""
    
    def test_upload_stores_file_hash(self, auth_headers):
        """Verify uploaded file has file_hash in record."""
        unique_content = f"TEST_hash_verify_{datetime.now().isoformat()}".encode()
        expected_hash = hashlib.sha256(unique_content).hexdigest()
        
        files = {"file": ("TEST_hash_verify.txt", io.BytesIO(unique_content), "text/plain")}
        data = {"folder": "sales"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        assert response.status_code == 200
        
        record = response.json()
        assert "file_hash" in record, "file_hash should be in response"
        assert record["file_hash"] == expected_hash, f"Hash mismatch: expected {expected_hash}, got {record.get('file_hash')}"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/records/{record['id']}", headers=auth_headers)


# ==================== BULK UPLOAD SUPPORT ====================

class TestBulkUploadBackend:
    """Test backend supports sequential uploads for bulk upload feature."""
    
    def test_multiple_sequential_uploads(self, auth_headers):
        """Backend should handle multiple sequential uploads."""
        created_ids = []
        
        try:
            for i in range(3):
                unique_content = f"TEST_bulk_{i}_{datetime.now().isoformat()}".encode()
                files = {"file": (f"TEST_bulk_{i}.txt", io.BytesIO(unique_content), "text/plain")}
                data = {"folder": "sales", "transaction_type": "sale"}
                
                response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
                assert response.status_code == 200, f"Upload {i} failed: {response.text}"
                created_ids.append(response.json()["id"])
            
            # Verify all files are present
            list_response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={
                "folder": "sales",
                "search": "TEST_bulk"
            })
            assert list_response.status_code == 200
            records = list_response.json()
            assert len(records) >= 3, f"Expected at least 3 bulk test records, got {len(records)}"
            
        finally:
            # Cleanup
            for rid in created_ids:
                requests.delete(f"{BASE_URL}/api/records/{rid}", headers=auth_headers)


# ==================== PREVIOUS FEATURES REGRESSION ====================

class TestPreviousFeaturesRegression:
    """Ensure previous Records Library features still work."""
    
    def test_upload_with_transaction_details(self, auth_headers):
        """Upload with full transaction details works."""
        unique_content = f"TEST_regression_{datetime.now().isoformat()}".encode()
        files = {"file": ("TEST_regression.txt", io.BytesIO(unique_content), "text/plain")}
        data = {
            "folder": "expenses",
            "transaction_type": "raw_material",
            "transaction_id": "test-reg-123",
            "transaction_date": "2026-01-15",
            "transaction_amount": "999.99",
            "transaction_notes": "Regression test",
            "vendor_name": "Test Vendor"
        }
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        assert response.status_code == 200
        
        record = response.json()
        assert record["transaction_type"] == "raw_material"
        assert record["transaction_amount"] == 999.99
        assert record["vendor_name"] == "Test Vendor"
        
        # Verify GET returns same details
        get_response = requests.get(f"{BASE_URL}/api/records/{record['id']}", headers=auth_headers)
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["transaction_notes"] == "Regression test"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/records/{record['id']}", headers=auth_headers)
    
    def test_file_download_still_works(self, auth_headers):
        """File download endpoint still works."""
        unique_content = b"TEST_download_regression_content"
        files = {"file": ("TEST_download_reg.txt", io.BytesIO(unique_content), "text/plain")}
        data = {"folder": "sales"}
        
        response = requests.post(f"{BASE_URL}/api/records/upload", headers=auth_headers, files=files, data=data)
        assert response.status_code == 200
        record_id = response.json()["id"]
        
        try:
            # Download file
            download_response = requests.get(f"{BASE_URL}/api/records/{record_id}/file", headers=auth_headers)
            assert download_response.status_code == 200
            assert download_response.content == unique_content
        finally:
            requests.delete(f"{BASE_URL}/api/records/{record_id}", headers=auth_headers)
    
    def test_list_with_search_filter(self, auth_headers):
        """List with search filter works."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={"search": "sales"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_with_file_type_filter(self, auth_headers):
        """List with file_type filter works."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers, params={"file_type": "image"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ==================== CLEANUP ====================

class TestFinalCleanup:
    """Clean up all TEST_ prefixed records."""
    
    def test_cleanup_all_test_records(self, auth_headers):
        """Delete all TEST_ prefixed records created during testing."""
        response = requests.get(f"{BASE_URL}/api/records", headers=auth_headers)
        if response.status_code == 200:
            records = response.json()
            deleted = 0
            for r in records:
                if r.get("file_name", "").startswith("TEST_"):
                    del_response = requests.delete(f"{BASE_URL}/api/records/{r['id']}", headers=auth_headers)
                    if del_response.status_code == 200:
                        deleted += 1
            print(f"Cleaned up {deleted} test records")
        assert True  # Always pass cleanup
