"""
Test suite for Vendor Merge/Deduplication Bug Fix
Tests the fix for: After renaming multiple vendors to the same name, 
the vendors list should show 1 merged card instead of duplicates.

Key scenarios:
1. GET /api/suppliers returns deduplicated vendors (no duplicate names)
2. PUT /api/suppliers/{id} with name change updates all associated purchases' supplier_name
3. PUT /api/suppliers/{id} rename to existing name merges: deletes renamed doc, returns existing target doc
4. After rename+merge: GET /api/suppliers shows ONE card with merged invoice count and total
5. After rename+merge: GET /api/suppliers/{id}/detail shows correct merged stats
6. After rename+merge: GET /api/suppliers/{id}/purchases returns all merged purchases
7. Rename to a new name (no existing target) works normally without merge
8. Updating non-name fields (phone, email) does NOT trigger purchase rename or merge
9. Delete vendor still works after merge
10. Creating a new vendor with a unique name still works normally
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
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Shared requests session with auth"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestVendorMergeScenario:
    """Complete vendor merge scenario test - all in one test to maintain state"""

    def test_complete_vendor_merge_scenario(self, api_client):
        """
        Complete test scenario:
        1. Create 4 vendors (V1 with 4 invoices, V2/V3/V4 with 1 each)
        2. Rename V2 to new name (verify purchases updated)
        3. Rename V3 to V1's name (verify merge)
        4. Rename V4 to V1's name (verify second merge)
        5. Verify final state: V1 has 6 invoices, $600
        """
        unique_suffix = str(uuid.uuid4())[:8]
        created_vendor_ids = []
        created_purchase_ids = []
        
        try:
            # ========== STEP 1: Create 4 vendors ==========
            print("\n=== STEP 1: Creating 4 vendors ===")
            vendors = []
            for i in range(1, 5):
                vendor_name = f"TEST_VENDOR_{i}_{unique_suffix}"
                response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                    "name": vendor_name,
                    "contact_person": f"Contact {i}",
                    "phone": f"555-000{i}",
                    "email": f"vendor{i}@test.com",
                    "address": f"Address {i}"
                })
                assert response.status_code == 200, f"Failed to create vendor {i}: {response.text}"
                vendor = response.json()
                vendors.append(vendor)
                created_vendor_ids.append(vendor["id"])
                print(f"  Created vendor {i}: {vendor['name']} (ID: {vendor['id']})")
            
            # ========== STEP 2: Create purchases ==========
            print("\n=== STEP 2: Creating purchases ===")
            # V1: 4 purchases totaling $400
            for j in range(4):
                response = api_client.post(f"{BASE_URL}/api/purchases", json={
                    "supplier_name": vendors[0]["name"],
                    "supplier_id": vendors[0]["id"],
                    "invoice_number": f"INV-V1-{j+1}-{unique_suffix}",
                    "invoice_date": "2026-01-15",
                    "items": [{"raw_name": f"Item {j+1}", "quantity": 1, "unit_price": 100, "total": 100}],
                    "subtotal": 100,
                    "tax": 0,
                    "total": 100
                })
                assert response.status_code == 200, f"Failed to create purchase for V1: {response.text}"
                created_purchase_ids.append(response.json()["id"])
            print(f"  Created 4 purchases for V1 (total: $400)")
            
            # V2, V3, V4: 1 purchase each totaling $100 each
            for i in range(1, 4):
                response = api_client.post(f"{BASE_URL}/api/purchases", json={
                    "supplier_name": vendors[i]["name"],
                    "supplier_id": vendors[i]["id"],
                    "invoice_number": f"INV-V{i+1}-1-{unique_suffix}",
                    "invoice_date": "2026-01-16",
                    "items": [{"raw_name": f"Item from V{i+1}", "quantity": 1, "unit_price": 100, "total": 100}],
                    "subtotal": 100,
                    "tax": 0,
                    "total": 100
                })
                assert response.status_code == 200, f"Failed to create purchase for V{i+1}: {response.text}"
                created_purchase_ids.append(response.json()["id"])
                print(f"  Created 1 purchase for V{i+1} (total: $100)")
            
            # Verify initial state
            response = api_client.get(f"{BASE_URL}/api/suppliers")
            assert response.status_code == 200
            all_vendors = response.json()
            test_vendors = [v for v in all_vendors if unique_suffix in v["name"]]
            assert len(test_vendors) == 4, f"Expected 4 test vendors, got {len(test_vendors)}"
            print(f"  Initial state: 4 vendors, 7 purchases total")
            
            # ========== STEP 3: Rename V2 to new name (no merge) ==========
            print("\n=== STEP 3: Rename V2 to new name (no merge) ===")
            new_name_v2 = f"TEST_VENDOR_2_RENAMED_{unique_suffix}"
            response = api_client.put(f"{BASE_URL}/api/suppliers/{vendors[1]['id']}", json={
                "name": new_name_v2,
                "contact_person": vendors[1]["contact_person"],
                "phone": vendors[1]["phone"],
                "email": vendors[1]["email"],
                "address": vendors[1]["address"]
            })
            assert response.status_code == 200, f"Failed to rename V2: {response.text}"
            print(f"  Renamed V2 from '{vendors[1]['name']}' to '{new_name_v2}'")
            
            # Verify purchase supplier_name updated
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[1]['id']}/purchases")
            assert response.status_code == 200
            v2_purchases = response.json()
            assert len(v2_purchases) == 1, f"Expected 1 purchase for V2, got {len(v2_purchases)}"
            assert v2_purchases[0]["supplier_name"] == new_name_v2, f"Purchase supplier_name not updated"
            print(f"  PASS: V2's purchase supplier_name updated to '{new_name_v2}'")
            vendors[1]["name"] = new_name_v2
            
            # ========== STEP 4: Rename V3 to V1's name (MERGE) ==========
            print("\n=== STEP 4: Rename V3 to V1's name (MERGE) ===")
            v1_name = vendors[0]["name"]
            
            # Get V1 stats before merge
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}/detail")
            assert response.status_code == 200
            v1_before = response.json()
            print(f"  V1 before merge: {v1_before['invoice_count']} invoices, ${v1_before['total_spending']}")
            
            # Rename V3 to V1's name
            response = api_client.put(f"{BASE_URL}/api/suppliers/{vendors[2]['id']}", json={
                "name": v1_name,
                "contact_person": vendors[2]["contact_person"],
                "phone": vendors[2]["phone"],
                "email": vendors[2]["email"],
                "address": vendors[2]["address"]
            })
            assert response.status_code == 200, f"Failed to merge V3 into V1: {response.text}"
            merged_result = response.json()
            print(f"  Renamed V3 to '{v1_name}' - merge triggered")
            
            # Verify merge: returned vendor should be V1
            assert merged_result["id"] == vendors[0]["id"], f"Merge should return V1's ID, got {merged_result['id']}"
            print(f"  PASS: Merge returned V1's ID")
            
            # Verify V3 is deleted
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[2]['id']}/detail")
            assert response.status_code == 404, f"V3 should be deleted after merge"
            print(f"  PASS: V3 deleted after merge")
            
            # Verify V1 now has 5 invoices and $500
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}/detail")
            assert response.status_code == 200
            v1_after_first_merge = response.json()
            assert v1_after_first_merge["invoice_count"] == 5, f"Expected 5 invoices, got {v1_after_first_merge['invoice_count']}"
            assert v1_after_first_merge["total_spending"] == 500.0, f"Expected $500, got {v1_after_first_merge['total_spending']}"
            print(f"  PASS: V1 after first merge: 5 invoices, $500")
            
            # ========== STEP 5: Rename V4 to V1's name (second MERGE) ==========
            print("\n=== STEP 5: Rename V4 to V1's name (second MERGE) ===")
            response = api_client.put(f"{BASE_URL}/api/suppliers/{vendors[3]['id']}", json={
                "name": v1_name,
                "contact_person": vendors[3]["contact_person"],
                "phone": vendors[3]["phone"],
                "email": vendors[3]["email"],
                "address": vendors[3]["address"]
            })
            assert response.status_code == 200, f"Failed to merge V4 into V1: {response.text}"
            print(f"  Renamed V4 to '{v1_name}' - merge triggered")
            
            # Verify V4 is deleted
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[3]['id']}/detail")
            assert response.status_code == 404, f"V4 should be deleted after merge"
            print(f"  PASS: V4 deleted after merge")
            
            # Verify V1 now has 6 invoices and $600
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}/detail")
            assert response.status_code == 200
            v1_final = response.json()
            assert v1_final["invoice_count"] == 6, f"Expected 6 invoices, got {v1_final['invoice_count']}"
            assert v1_final["total_spending"] == 600.0, f"Expected $600, got {v1_final['total_spending']}"
            print(f"  PASS: V1 after second merge: 6 invoices, $600")
            
            # ========== STEP 6: Verify suppliers list shows no duplicates ==========
            print("\n=== STEP 6: Verify suppliers list shows no duplicates ===")
            response = api_client.get(f"{BASE_URL}/api/suppliers")
            assert response.status_code == 200
            all_vendors = response.json()
            test_vendors = [v for v in all_vendors if unique_suffix in v["name"]]
            
            # Should have 2 vendors: V1 (merged) and V2 (renamed)
            assert len(test_vendors) == 2, f"Expected 2 test vendors, got {len(test_vendors)}: {[v['name'] for v in test_vendors]}"
            print(f"  PASS: Suppliers list shows 2 vendors (V1 merged, V2 renamed)")
            
            # Check no duplicate names
            names = [v["name"].upper() for v in test_vendors]
            assert len(names) == len(set(names)), f"Duplicate names found: {names}"
            print(f"  PASS: No duplicate vendor names")
            
            # V1 should have correct stats in list
            v1_in_list = next((v for v in test_vendors if v["id"] == vendors[0]["id"]), None)
            assert v1_in_list is not None, "V1 not found in list"
            assert v1_in_list["invoice_count"] == 6, f"V1 in list should have 6 invoices"
            assert v1_in_list["total_spending"] == 600.0, f"V1 in list should have $600"
            print(f"  PASS: V1 in list has correct merged stats")
            
            # ========== STEP 7: Verify V1's purchases include all merged ==========
            print("\n=== STEP 7: Verify V1's purchases include all merged ===")
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}/purchases")
            assert response.status_code == 200
            v1_purchases = response.json()
            assert len(v1_purchases) == 6, f"Expected 6 purchases, got {len(v1_purchases)}"
            print(f"  PASS: V1 has 6 purchases (4 original + 1 from V3 + 1 from V4)")
            
            # ========== STEP 8: Test non-name update doesn't affect merge ==========
            print("\n=== STEP 8: Test non-name update doesn't trigger merge ===")
            response = api_client.put(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}", json={
                "name": v1_name,  # Same name
                "contact_person": "Updated Contact",
                "phone": "555-9999",
                "email": "updated@test.com",
                "address": "Updated Address"
            })
            assert response.status_code == 200
            
            # Verify stats unchanged
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[0]['id']}/detail")
            assert response.status_code == 200
            v1_after_update = response.json()
            assert v1_after_update["invoice_count"] == 6, "Invoice count changed after non-name update"
            assert v1_after_update["total_spending"] == 600.0, "Total spending changed after non-name update"
            assert v1_after_update["phone"] == "555-9999", "Phone not updated"
            print(f"  PASS: Non-name update works without affecting merge stats")
            
            # ========== STEP 9: Test delete works ==========
            print("\n=== STEP 9: Test delete vendor works ===")
            response = api_client.delete(f"{BASE_URL}/api/suppliers/{vendors[1]['id']}")
            assert response.status_code == 200, f"Failed to delete V2: {response.text}"
            
            response = api_client.get(f"{BASE_URL}/api/suppliers/{vendors[1]['id']}/detail")
            assert response.status_code == 404, "V2 should be deleted"
            print(f"  PASS: Delete vendor works")
            
            # ========== STEP 10: Test create new vendor works ==========
            print("\n=== STEP 10: Test create new vendor works ===")
            new_vendor_name = f"TEST_NEW_VENDOR_{unique_suffix}"
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": new_vendor_name,
                "contact_person": "New Contact"
            })
            assert response.status_code == 200
            new_vendor = response.json()
            created_vendor_ids.append(new_vendor["id"])
            print(f"  PASS: Create new vendor works")
            
            print("\n=== ALL TESTS PASSED ===")
            
        finally:
            # Cleanup
            print("\n=== CLEANUP ===")
            for vid in created_vendor_ids:
                try:
                    api_client.delete(f"{BASE_URL}/api/suppliers/{vid}")
                except:
                    pass
            for pid in created_purchase_ids:
                try:
                    api_client.delete(f"{BASE_URL}/api/purchases/{pid}")
                except:
                    pass
            print("  Cleanup complete")


class TestDeduplicationOnList:
    """Test that GET /api/suppliers deduplicates by name"""

    def test_deduplication_cleans_duplicates(self, api_client):
        """If duplicate supplier docs exist, GET /api/suppliers should deduplicate and clean them"""
        unique_suffix = str(uuid.uuid4())[:8]
        vendor_name = f"TEST_DEDUP_{unique_suffix}"
        created_ids = []
        
        try:
            # Create first vendor
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": vendor_name,
                "contact_person": "Contact 1",
                "phone": "555-0001"
            })
            assert response.status_code == 200
            v1 = response.json()
            created_ids.append(v1["id"])
            
            # Create second vendor with same name (simulating a bug scenario)
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": vendor_name,
                "contact_person": "Contact 2",
                "phone": "555-0002"
            })
            assert response.status_code == 200
            v2 = response.json()
            created_ids.append(v2["id"])
            
            # GET /api/suppliers should return only ONE vendor with this name
            response = api_client.get(f"{BASE_URL}/api/suppliers")
            assert response.status_code == 200
            all_vendors = response.json()
            
            matching = [v for v in all_vendors if v["name"] == vendor_name]
            assert len(matching) == 1, f"Expected 1 vendor with name {vendor_name}, got {len(matching)}"
            print(f"PASS: GET /api/suppliers deduplicates vendors by name")
            
        finally:
            for vid in created_ids:
                try:
                    api_client.delete(f"{BASE_URL}/api/suppliers/{vid}")
                except:
                    pass


class TestEdgeCases:
    """Test edge cases for vendor merge"""

    def test_case_insensitive_merge(self, api_client):
        """Merge should be case-insensitive"""
        unique_suffix = str(uuid.uuid4())[:8]
        created_ids = []
        
        try:
            # Create vendor with lowercase name
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": f"test_vendor_lower_{unique_suffix}",
                "contact_person": "Contact"
            })
            assert response.status_code == 200
            v1 = response.json()
            created_ids.append(v1["id"])
            
            # Create vendor with uppercase name
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": f"TEST_VENDOR_UPPER_{unique_suffix}",
                "contact_person": "Contact"
            })
            assert response.status_code == 200
            v2 = response.json()
            created_ids.append(v2["id"])
            
            # Rename v2 to v1's name but with different case
            response = api_client.put(f"{BASE_URL}/api/suppliers/{v2['id']}", json={
                "name": f"TEST_VENDOR_LOWER_{unique_suffix}",  # Different case
                "contact_person": "Contact"
            })
            assert response.status_code == 200
            
            # v2 should be merged into v1 (case-insensitive match)
            response = api_client.get(f"{BASE_URL}/api/suppliers/{v2['id']}/detail")
            assert response.status_code == 404, "V2 should be deleted after case-insensitive merge"
            print(f"PASS: Merge is case-insensitive")
            
        finally:
            for vid in created_ids:
                try:
                    api_client.delete(f"{BASE_URL}/api/suppliers/{vid}")
                except:
                    pass

    def test_rename_to_self_no_change(self, api_client):
        """Renaming a vendor to its own name should not cause issues"""
        unique_suffix = str(uuid.uuid4())[:8]
        created_ids = []
        
        try:
            response = api_client.post(f"{BASE_URL}/api/suppliers", json={
                "name": f"TEST_SELF_RENAME_{unique_suffix}",
                "contact_person": "Contact"
            })
            assert response.status_code == 200
            v1 = response.json()
            created_ids.append(v1["id"])
            
            # Rename to same name
            response = api_client.put(f"{BASE_URL}/api/suppliers/{v1['id']}", json={
                "name": f"TEST_SELF_RENAME_{unique_suffix}",
                "contact_person": "Updated Contact"
            })
            assert response.status_code == 200
            
            # Vendor should still exist
            response = api_client.get(f"{BASE_URL}/api/suppliers/{v1['id']}/detail")
            assert response.status_code == 200
            print(f"PASS: Renaming to same name works without issues")
            
        finally:
            for vid in created_ids:
                try:
                    api_client.delete(f"{BASE_URL}/api/suppliers/{vid}")
                except:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
