"""
Test Correction Memory UI Feature - Backend API Tests

Tests the Correction Memory management endpoints:
- GET /api/corrections/vendors - List vendors with correction counts
- GET /api/corrections/by-vendor/{supplier_id} - Get corrections for a vendor
- DELETE /api/corrections/{correction_id} - Delete a correction
- PATCH /api/corrections/{correction_id}/toggle - Enable/disable a correction
- PATCH /api/corrections/{correction_id} - Edit a correction
- Disabled corrections excluded from /api/correction-hints
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestCorrectionMemoryAPI:
    """Tests for Correction Memory management endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        yield
        
        # Cleanup: Delete any TEST_ corrections created during tests
        try:
            vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
            for v in vendors:
                if v.get("supplier_name", "").startswith("TEST_"):
                    corrections = self.session.get(
                        f"{BASE_URL}/api/corrections/by-vendor/{v['supplier_id']}"
                    ).json()
                    for c in corrections:
                        self.session.delete(f"{BASE_URL}/api/corrections/{c['id']}")
        except:
            pass
    
    def test_get_vendors_with_corrections(self):
        """GET /api/corrections/vendors returns vendor list with counts"""
        response = self.session.get(f"{BASE_URL}/api/corrections/vendors")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        # Check structure of vendor entries
        if len(data) > 0:
            vendor = data[0]
            assert "supplier_id" in vendor
            assert "supplier_name" in vendor
            assert "correction_count" in vendor
            assert "enabled_count" in vendor
            assert "total_usage" in vendor
            assert "last_updated" in vendor
            
            # Verify counts are integers
            assert isinstance(vendor["correction_count"], int)
            assert isinstance(vendor["enabled_count"], int)
            assert isinstance(vendor["total_usage"], int)
    
    def test_get_corrections_by_vendor(self):
        """GET /api/corrections/by-vendor/{supplier_id} returns corrections"""
        # First get a vendor with corrections
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        assert len(vendors) > 0, "No vendors with corrections found"
        
        vendor = vendors[0]
        supplier_id = vendor["supplier_id"]
        
        response = self.session.get(f"{BASE_URL}/api/corrections/by-vendor/{supplier_id}")
        assert response.status_code == 200
        
        corrections = response.json()
        assert isinstance(corrections, list)
        assert len(corrections) > 0
        
        # Check correction structure
        correction = corrections[0]
        assert "id" in correction
        assert "normalized_key" in correction
        assert "original_raw_name" in correction
        assert "corrected_name" in correction
        assert "corrected_specs" in correction
        assert "created_at" in correction
        assert "updated_at" in correction
        # No _id field (MongoDB ObjectId excluded)
        assert "_id" not in correction
    
    def test_toggle_correction_disable(self):
        """PATCH /api/corrections/{id}/toggle disables a correction"""
        # Get a correction to toggle
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), vendors[0])
        
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        correction_id = correction["id"]
        
        # Disable the correction
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["enabled"] == False
        
        # Verify it's disabled
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        updated = next(c for c in corrections if c["id"] == correction_id)
        assert updated.get("enabled") == False
        
        # Re-enable for cleanup
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": True}
        )
    
    def test_toggle_correction_enable(self):
        """PATCH /api/corrections/{id}/toggle enables a correction"""
        # Get a correction
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), vendors[0])
        
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        correction_id = correction["id"]
        
        # First disable
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": False}
        )
        
        # Then enable
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["enabled"] == True
    
    def test_edit_correction_name(self):
        """PATCH /api/corrections/{id} edits corrected_name"""
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), vendors[0])
        
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        correction_id = correction["id"]
        original_name = correction["corrected_name"]
        
        # Edit the name
        new_name = f"TEST_EDITED_{uuid.uuid4().hex[:8]}"
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}",
            json={"corrected_name": new_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["corrected_name"] == new_name
        
        # Revert
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}",
            json={"corrected_name": original_name}
        )
    
    def test_edit_correction_specs(self):
        """PATCH /api/corrections/{id} edits corrected_specs"""
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), vendors[0])
        
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        correction_id = correction["id"]
        original_specs = correction.get("corrected_specs", {})
        
        # Edit specs
        new_specs = {
            "unit_price": 99.99,
            "pack_size": "TEST_PACK",
            "total": 199.99
        }
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}",
            json={"corrected_specs": new_specs}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["corrected_specs"]["unit_price"] == 99.99
        assert data["corrected_specs"]["pack_size"] == "TEST_PACK"
        assert data["corrected_specs"]["total"] == 199.99
        
        # Revert
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}",
            json={"corrected_specs": original_specs}
        )
    
    def test_edit_correction_no_fields_returns_400(self):
        """PATCH /api/corrections/{id} with no fields returns 400"""
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = vendors[0]
        
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{correction['id']}",
            json={}
        )
        assert response.status_code == 400
    
    def test_disabled_corrections_excluded_from_hints(self):
        """Disabled corrections are excluded from /api/correction-hints"""
        # Get Quick Review Test Vendor
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), None)
        
        if not vendor:
            pytest.skip("Quick Review Test Vendor not found")
        
        supplier_name = vendor["supplier_name"]
        
        # Get initial hints count
        hints_before = self.session.get(
            f"{BASE_URL}/api/correction-hints",
            params={"supplier_name": supplier_name}
        ).json()
        count_before = len(hints_before)
        
        # Get a correction and disable it
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        correction_id = correction["id"]
        
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": False}
        )
        
        # Check hints count decreased
        hints_after = self.session.get(
            f"{BASE_URL}/api/correction-hints",
            params={"supplier_name": supplier_name}
        ).json()
        count_after = len(hints_after)
        
        assert count_after < count_before, "Disabled correction should be excluded from hints"
        
        # Re-enable
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction_id}/toggle",
            json={"enabled": True}
        )
    
    def test_delete_correction_not_found(self):
        """DELETE /api/corrections/{id} returns 404 for non-existent correction"""
        fake_id = str(uuid.uuid4())
        response = self.session.delete(f"{BASE_URL}/api/corrections/{fake_id}")
        assert response.status_code == 404
    
    def test_toggle_correction_not_found(self):
        """PATCH /api/corrections/{id}/toggle returns 404 for non-existent correction"""
        fake_id = str(uuid.uuid4())
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{fake_id}/toggle",
            json={"enabled": False}
        )
        assert response.status_code == 404
    
    def test_edit_correction_not_found(self):
        """PATCH /api/corrections/{id} returns 404 for non-existent correction"""
        fake_id = str(uuid.uuid4())
        response = self.session.patch(
            f"{BASE_URL}/api/corrections/{fake_id}",
            json={"corrected_name": "Test"}
        )
        assert response.status_code == 404
    
    def test_vendor_enabled_count_updates(self):
        """Vendor enabled_count updates when corrections are toggled"""
        vendors = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor = next((v for v in vendors if "Quick Review" in v.get("supplier_name", "")), vendors[0])
        
        initial_enabled = vendor["enabled_count"]
        
        # Get a correction and disable it
        corrections = self.session.get(
            f"{BASE_URL}/api/corrections/by-vendor/{vendor['supplier_id']}"
        ).json()
        correction = corrections[0]
        
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction['id']}/toggle",
            json={"enabled": False}
        )
        
        # Check enabled_count decreased
        vendors_after = self.session.get(f"{BASE_URL}/api/corrections/vendors").json()
        vendor_after = next(v for v in vendors_after if v["supplier_id"] == vendor["supplier_id"])
        
        assert vendor_after["enabled_count"] == initial_enabled - 1
        
        # Re-enable
        self.session.patch(
            f"{BASE_URL}/api/corrections/{correction['id']}/toggle",
            json={"enabled": True}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
