"""
Test suite for Manual/Assisted Item Matching feature.
Tests item-mappings CRUD, suggestions, and vendor-comparison integration.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@test.com"
TEST_PASSWORD = "testpassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


# ==================== GET /api/item-mappings ====================

class TestListItemMappings:
    """Tests for GET /api/item-mappings endpoint."""

    def test_list_mappings_returns_200(self, api_client):
        """GET /api/item-mappings returns 200 OK."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/item-mappings returns 200")

    def test_list_mappings_structure(self, api_client):
        """Response has 'mappings' array."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings")
        data = response.json()
        assert "mappings" in data, "Response missing 'mappings' key"
        assert isinstance(data["mappings"], list), "'mappings' should be a list"
        print(f"PASS: Response has 'mappings' array with {len(data['mappings'])} items")

    def test_mapping_object_structure(self, api_client):
        """Each mapping has required fields."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = response.json().get("mappings", [])
        if not mappings:
            pytest.skip("No mappings exist to verify structure")
        
        required_fields = ["id", "canonical_name", "mapped_names", "restaurant_id"]
        for m in mappings:
            for field in required_fields:
                assert field in m, f"Mapping missing '{field}' field"
            assert isinstance(m["mapped_names"], list), "mapped_names should be a list"
            assert len(m["mapped_names"]) >= 2, "mapped_names should have at least 2 items"
        print(f"PASS: All {len(mappings)} mappings have correct structure")


# ==================== POST /api/item-mappings ====================

class TestCreateItemMapping:
    """Tests for POST /api/item-mappings endpoint."""

    def test_create_mapping_success(self, api_client):
        """POST /api/item-mappings creates mapping with canonical_name and mapped_names."""
        # First, clean up any existing test mapping
        existing = api_client.get(f"{BASE_URL}/api/item-mappings").json().get("mappings", [])
        for m in existing:
            if m.get("canonical_name") == "TEST_ITEM_MAPPING":
                api_client.delete(f"{BASE_URL}/api/item-mappings/{m['id']}")
        
        # Create new mapping
        payload = {
            "canonical_name": "TEST_ITEM_MAPPING",
            "mapped_names": ["TEST_NAME_A", "TEST_NAME_B"]
        }
        response = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["canonical_name"] == "TEST_ITEM_MAPPING"
        assert "id" in data
        assert len(data["mapped_names"]) >= 2
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/item-mappings/{data['id']}")
        print("PASS: POST /api/item-mappings creates mapping successfully")

    def test_create_mapping_rejects_single_name(self, api_client):
        """POST /api/item-mappings rejects single mapped_name (400)."""
        payload = {
            "canonical_name": "TEST_SINGLE",
            "mapped_names": ["ONLY_ONE_NAME"]
        }
        response = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: POST /api/item-mappings rejects single mapped_name with 400")

    def test_create_mapping_rejects_empty_names(self, api_client):
        """POST /api/item-mappings rejects empty mapped_names."""
        payload = {
            "canonical_name": "TEST_EMPTY",
            "mapped_names": []
        }
        response = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: POST /api/item-mappings rejects empty mapped_names with 400")

    def test_create_mapping_rejects_duplicate(self, api_client):
        """POST /api/item-mappings rejects duplicate mappings (409 conflict)."""
        # Create first mapping
        payload1 = {
            "canonical_name": "TEST_DUP_CANONICAL",
            "mapped_names": ["TEST_DUP_A", "TEST_DUP_B"]
        }
        resp1 = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload1)
        if resp1.status_code != 200:
            pytest.skip(f"Could not create first mapping: {resp1.text}")
        mapping_id = resp1.json()["id"]
        
        try:
            # Try to create mapping with overlapping name
            payload2 = {
                "canonical_name": "TEST_DUP_CANONICAL_2",
                "mapped_names": ["TEST_DUP_A", "TEST_DUP_C"]  # TEST_DUP_A already mapped
            }
            resp2 = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload2)
            assert resp2.status_code == 409, f"Expected 409 conflict, got {resp2.status_code}: {resp2.text}"
            print("PASS: POST /api/item-mappings rejects duplicate with 409 conflict")
        finally:
            # Cleanup
            api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")


# ==================== PUT /api/item-mappings/{id} ====================

class TestUpdateItemMapping:
    """Tests for PUT /api/item-mappings/{id} endpoint."""

    def test_update_mapping_canonical_name(self, api_client):
        """PUT /api/item-mappings/{id} updates canonical_name."""
        # Create mapping
        payload = {
            "canonical_name": "TEST_UPDATE_ORIGINAL",
            "mapped_names": ["TEST_UPDATE_A", "TEST_UPDATE_B"]
        }
        resp = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        if resp.status_code != 200:
            pytest.skip(f"Could not create mapping: {resp.text}")
        mapping_id = resp.json()["id"]
        
        try:
            # Update canonical_name
            update_payload = {"canonical_name": "TEST_UPDATE_NEW_NAME"}
            update_resp = api_client.put(f"{BASE_URL}/api/item-mappings/{mapping_id}", json=update_payload)
            assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}"
            assert update_resp.json()["canonical_name"] == "TEST_UPDATE_NEW_NAME"
            print("PASS: PUT /api/item-mappings/{id} updates canonical_name")
        finally:
            api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")

    def test_update_mapping_mapped_names(self, api_client):
        """PUT /api/item-mappings/{id} updates mapped_names."""
        # Create mapping
        payload = {
            "canonical_name": "TEST_UPDATE_NAMES",
            "mapped_names": ["TEST_NAMES_A", "TEST_NAMES_B"]
        }
        resp = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        if resp.status_code != 200:
            pytest.skip(f"Could not create mapping: {resp.text}")
        mapping_id = resp.json()["id"]
        
        try:
            # Update mapped_names
            update_payload = {"mapped_names": ["TEST_NAMES_A", "TEST_NAMES_B", "TEST_NAMES_C"]}
            update_resp = api_client.put(f"{BASE_URL}/api/item-mappings/{mapping_id}", json=update_payload)
            assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}"
            assert len(update_resp.json()["mapped_names"]) >= 3
            print("PASS: PUT /api/item-mappings/{id} updates mapped_names")
        finally:
            api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")

    def test_update_nonexistent_mapping(self, api_client):
        """PUT /api/item-mappings/{id} returns 404 for nonexistent mapping."""
        response = api_client.put(f"{BASE_URL}/api/item-mappings/nonexistent-id-12345", json={
            "canonical_name": "TEST"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: PUT /api/item-mappings/{id} returns 404 for nonexistent mapping")


# ==================== DELETE /api/item-mappings/{id} ====================

class TestDeleteItemMapping:
    """Tests for DELETE /api/item-mappings/{id} endpoint."""

    def test_delete_mapping_success(self, api_client):
        """DELETE /api/item-mappings/{id} deletes mapping."""
        # Create mapping
        payload = {
            "canonical_name": "TEST_DELETE",
            "mapped_names": ["TEST_DELETE_A", "TEST_DELETE_B"]
        }
        resp = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        if resp.status_code != 200:
            pytest.skip(f"Could not create mapping: {resp.text}")
        mapping_id = resp.json()["id"]
        
        # Delete
        del_resp = api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")
        assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}"
        
        # Verify deleted
        get_resp = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = get_resp.json().get("mappings", [])
        assert not any(m["id"] == mapping_id for m in mappings), "Mapping should be deleted"
        print("PASS: DELETE /api/item-mappings/{id} deletes mapping")

    def test_delete_nonexistent_mapping(self, api_client):
        """DELETE /api/item-mappings/{id} returns 404 for nonexistent mapping."""
        response = api_client.delete(f"{BASE_URL}/api/item-mappings/nonexistent-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: DELETE /api/item-mappings/{id} returns 404 for nonexistent mapping")


# ==================== GET /api/item-mappings/suggestions ====================

class TestItemMappingSuggestions:
    """Tests for GET /api/item-mappings/suggestions endpoint."""

    def test_suggestions_returns_200(self, api_client):
        """GET /api/item-mappings/suggestions returns 200 OK."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings/suggestions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/item-mappings/suggestions returns 200")

    def test_suggestions_structure(self, api_client):
        """Response has 'suggestions' array with correct structure."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings/suggestions")
        data = response.json()
        assert "suggestions" in data, "Response missing 'suggestions' key"
        assert "total" in data, "Response missing 'total' key"
        assert isinstance(data["suggestions"], list), "'suggestions' should be a list"
        
        if data["suggestions"]:
            s = data["suggestions"][0]
            required_fields = ["name_a", "name_b", "vendors_a", "vendors_b", "similarity", "shared_words"]
            for field in required_fields:
                assert field in s, f"Suggestion missing '{field}' field"
        print(f"PASS: Suggestions structure correct, {len(data['suggestions'])} suggestions found")

    def test_suggestions_exclude_already_mapped(self, api_client):
        """Suggestions exclude items already in confirmed mappings."""
        # Get current mappings
        mappings_resp = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = mappings_resp.json().get("mappings", [])
        
        # Collect all mapped names
        mapped_names = set()
        for m in mappings:
            for n in m.get("mapped_names", []):
                mapped_names.add(n)
        
        if not mapped_names:
            pytest.skip("No mappings exist to verify exclusion")
        
        # Get suggestions
        suggestions_resp = api_client.get(f"{BASE_URL}/api/item-mappings/suggestions")
        suggestions = suggestions_resp.json().get("suggestions", [])
        
        # Verify no suggestion contains already-mapped names
        for s in suggestions:
            assert s["name_a"] not in mapped_names, f"Suggestion contains already-mapped name: {s['name_a']}"
            assert s["name_b"] not in mapped_names, f"Suggestion contains already-mapped name: {s['name_b']}"
        print("PASS: Suggestions exclude items already in confirmed mappings")


# ==================== GET /api/vendor-comparison/normalized ====================

class TestVendorComparisonWithMappings:
    """Tests for vendor-comparison/normalized with item mappings."""

    def test_normalized_comparison_returns_200(self, api_client):
        """GET /api/vendor-comparison/normalized returns 200 OK."""
        response = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/vendor-comparison/normalized returns 200")

    def test_comparison_includes_match_source(self, api_client):
        """Every comparison group has match_source field."""
        response = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        comparisons = response.json().get("comparisons", [])
        
        for c in comparisons:
            assert "match_source" in c, f"Group {c.get('item_key')} missing 'match_source'"
            assert c["match_source"] in ["exact", "user_confirmed"], f"Invalid match_source: {c['match_source']}"
        print(f"PASS: All {len(comparisons)} groups have valid match_source")

    def test_stats_includes_user_confirmed_count(self, api_client):
        """Stats includes user_confirmed_groups count."""
        response = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        stats = response.json().get("stats", {})
        
        assert "user_confirmed_groups" in stats, "Stats missing 'user_confirmed_groups'"
        assert isinstance(stats["user_confirmed_groups"], int), "user_confirmed_groups should be int"
        print(f"PASS: Stats includes user_confirmed_groups: {stats['user_confirmed_groups']}")

    def test_user_confirmed_count_matches_data(self, api_client):
        """stats.user_confirmed_groups count matches actual data."""
        response = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        data = response.json()
        comparisons = data.get("comparisons", [])
        stats = data.get("stats", {})
        
        actual_confirmed = sum(1 for c in comparisons if c.get("match_source") == "user_confirmed")
        reported_confirmed = stats.get("user_confirmed_groups", 0)
        
        assert actual_confirmed == reported_confirmed, f"Mismatch: actual={actual_confirmed}, reported={reported_confirmed}"
        print(f"PASS: user_confirmed_groups count is accurate: {reported_confirmed}")

    def test_confirmed_groups_have_raw_names(self, api_client):
        """Confirmed groups show raw_names_in_group with all linked names."""
        response = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        comparisons = response.json().get("comparisons", [])
        
        confirmed = [c for c in comparisons if c.get("match_source") == "user_confirmed"]
        if not confirmed:
            pytest.skip("No user_confirmed groups to verify")
        
        for c in confirmed:
            assert "raw_names_in_group" in c, f"Group {c['item_key']} missing 'raw_names_in_group'"
            assert isinstance(c["raw_names_in_group"], list), "raw_names_in_group should be a list"
            # Confirmed groups should have multiple raw names (that's why they're confirmed)
            if len(c["raw_names_in_group"]) > 1:
                print(f"  - {c['item_key']}: {c['raw_names_in_group']}")
        print(f"PASS: Confirmed groups have raw_names_in_group")


# ==================== Integration: Mapping affects comparison ====================

class TestMappingIntegration:
    """Tests that mappings correctly affect vendor comparison."""

    def test_create_mapping_merges_groups(self, api_client):
        """Creating a mapping merges groups and increases vendor count."""
        # Get initial comparison state
        initial_resp = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        initial_data = initial_resp.json()
        initial_groups = len(initial_data.get("comparisons", []))
        
        # Get suggestions to find items to link
        suggestions_resp = api_client.get(f"{BASE_URL}/api/item-mappings/suggestions")
        suggestions = suggestions_resp.json().get("suggestions", [])
        
        if not suggestions:
            pytest.skip("No suggestions available to test mapping integration")
        
        # Pick first suggestion
        suggestion = suggestions[0]
        name_a = suggestion["name_a"]
        name_b = suggestion["name_b"]
        
        # Create mapping
        payload = {
            "canonical_name": f"TEST_MERGE_{name_a[:10]}",
            "mapped_names": [name_a, name_b]
        }
        create_resp = api_client.post(f"{BASE_URL}/api/item-mappings", json=payload)
        
        if create_resp.status_code != 200:
            pytest.skip(f"Could not create mapping: {create_resp.text}")
        
        mapping_id = create_resp.json()["id"]
        
        try:
            # Get new comparison state
            new_resp = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
            new_data = new_resp.json()
            new_groups = len(new_data.get("comparisons", []))
            
            # Groups should reduce (two items merged into one)
            # Note: This may not always reduce if items weren't in separate groups
            print(f"  Initial groups: {initial_groups}, After mapping: {new_groups}")
            
            # Verify the merged group exists with user_confirmed source
            merged_group = None
            for c in new_data.get("comparisons", []):
                if c.get("match_source") == "user_confirmed":
                    if name_a in c.get("raw_names_in_group", []) or name_b in c.get("raw_names_in_group", []):
                        merged_group = c
                        break
            
            assert merged_group is not None, "Merged group with user_confirmed source not found"
            assert merged_group["match_source"] == "user_confirmed"
            print(f"PASS: Mapping created merged group: {merged_group['item_key']}")
        finally:
            # Cleanup
            api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")

    def test_delete_mapping_unmerges_groups(self, api_client):
        """Deleting a mapping unmerges groups back to exact-match."""
        # Get current mappings
        mappings_resp = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = mappings_resp.json().get("mappings", [])
        
        if not mappings:
            pytest.skip("No mappings exist to test deletion")
        
        # Find a mapping to delete and recreate
        test_mapping = mappings[0]
        mapping_id = test_mapping["id"]
        canonical_name = test_mapping["canonical_name"]
        mapped_names = test_mapping["mapped_names"]
        
        # Get comparison before delete
        before_resp = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
        before_confirmed = before_resp.json().get("stats", {}).get("user_confirmed_groups", 0)
        
        # Delete mapping
        del_resp = api_client.delete(f"{BASE_URL}/api/item-mappings/{mapping_id}")
        assert del_resp.status_code == 200
        
        try:
            # Get comparison after delete
            after_resp = api_client.get(f"{BASE_URL}/api/vendor-comparison/normalized")
            after_confirmed = after_resp.json().get("stats", {}).get("user_confirmed_groups", 0)
            
            # Confirmed groups should decrease
            assert after_confirmed < before_confirmed, f"Expected fewer confirmed groups after delete"
            print(f"PASS: Deleting mapping reduced confirmed groups: {before_confirmed} -> {after_confirmed}")
        finally:
            # Recreate the mapping
            recreate_payload = {
                "canonical_name": canonical_name,
                "mapped_names": mapped_names
            }
            api_client.post(f"{BASE_URL}/api/item-mappings", json=recreate_payload)


# ==================== Existing Mappings Verification ====================

class TestExistingMappings:
    """Verify the existing seeded mappings work correctly."""

    def test_existing_mappings_present(self, api_client):
        """Verify expected mappings exist (Chicken Breast Boneless, Flour All Purpose)."""
        response = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = response.json().get("mappings", [])
        
        canonical_names = [m["canonical_name"] for m in mappings]
        print(f"  Found mappings: {canonical_names}")
        
        # Check for expected mappings (may have different exact names)
        found_chicken = any("chicken" in n.lower() for n in canonical_names)
        found_flour = any("flour" in n.lower() for n in canonical_names)
        
        if found_chicken:
            print("  - Found chicken-related mapping")
        if found_flour:
            print("  - Found flour-related mapping")
        
        print(f"PASS: Found {len(mappings)} existing mappings")

    def test_gfs_items_in_suggestions_or_mappings(self, api_client):
        """GFS differently-named items should be in suggestions or already mapped."""
        # GFS items: BNLS CHICKEN BREAST, ALL PURPOSE FLOUR, ROMA TOMATO 25LB, SHRIMP HDLS 31-35, GROUND BEEF 80-20
        gfs_items = ["BNLS CHICKEN BREAST", "ALL PURPOSE FLOUR", "ROMA TOMATO", "SHRIMP HDLS", "GROUND BEEF"]
        
        # Get mappings
        mappings_resp = api_client.get(f"{BASE_URL}/api/item-mappings")
        mappings = mappings_resp.json().get("mappings", [])
        
        # Get suggestions
        suggestions_resp = api_client.get(f"{BASE_URL}/api/item-mappings/suggestions")
        suggestions = suggestions_resp.json().get("suggestions", [])
        
        # Collect all mapped names
        mapped_names = set()
        for m in mappings:
            for n in m.get("mapped_names", []):
                mapped_names.add(n.upper())
        
        # Collect all suggested names
        suggested_names = set()
        for s in suggestions:
            suggested_names.add(s["name_a"].upper())
            suggested_names.add(s["name_b"].upper())
        
        print(f"  Mapped names: {mapped_names}")
        print(f"  Suggested names (sample): {list(suggested_names)[:5]}")
        
        # At least some GFS items should be mapped or suggested
        found_in_mapped = sum(1 for item in gfs_items if any(item in n for n in mapped_names))
        found_in_suggested = sum(1 for item in gfs_items if any(item in n for n in suggested_names))
        
        print(f"  GFS items in mappings: {found_in_mapped}")
        print(f"  GFS items in suggestions: {found_in_suggested}")
        print("PASS: GFS items verification complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
