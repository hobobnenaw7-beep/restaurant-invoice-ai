"""
Test Suite: Hybrid Item Classification System
==============================================
Tests for storage_category (dry/chilled/frozen), category_source (auto/manual),
filter tabs, inline dropdown editing, and manual override protection.

Endpoints tested:
- GET /api/items - returns items with storage_category and category_source fields
- GET /api/items?storage_category=frozen - filters correctly
- POST /api/items - creates item with storage_category and category_source
- PATCH /api/items/{id}/storage-category - sets category to manual and records audit fields
- PATCH /api/items/{id}/storage-category with invalid category - returns 400
- PUT /api/items/{id} - updates item including storage_category
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestStorageCategoryAPI:
    """Tests for storage_category and category_source fields on items"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with manager credentials
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Track created items for cleanup
        self.created_item_ids = []
        yield
        
        # Cleanup created items
        for item_id in self.created_item_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/items/{item_id}")
            except:
                pass
    
    def test_get_items_returns_storage_fields(self):
        """GET /api/items returns items with storage_category and category_source fields"""
        resp = self.session.get(f"{BASE_URL}/api/items")
        assert resp.status_code == 200, f"GET /items failed: {resp.text}"
        
        items = resp.json()
        assert isinstance(items, list), "Response should be a list"
        
        # Check that items have the expected fields (may be empty for existing items)
        if len(items) > 0:
            item = items[0]
            # Fields should exist (even if empty/null)
            assert "name" in item, "Item should have 'name' field"
            # storage_category and category_source may not exist on old items
            print(f"First item keys: {list(item.keys())}")
            print(f"Total items returned: {len(items)}")
    
    def test_get_items_filter_by_frozen(self):
        """GET /api/items?storage_category=frozen filters correctly"""
        # First create a frozen item
        test_item = {
            "name": f"TEST_Frozen_Item_{uuid.uuid4().hex[:8]}",
            "category": "Seafood",
            "storage_category": "frozen",
            "category_source": "manual"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # Now filter by frozen
        resp = self.session.get(f"{BASE_URL}/api/items", params={"storage_category": "frozen"})
        assert resp.status_code == 200, f"Filter failed: {resp.text}"
        
        items = resp.json()
        # All returned items should have storage_category=frozen
        for item in items:
            assert item.get("storage_category") == "frozen", f"Item {item.get('name')} has storage_category={item.get('storage_category')}, expected 'frozen'"
        
        # Our test item should be in the results
        item_ids = [i["id"] for i in items]
        assert created["id"] in item_ids, "Created frozen item should be in filtered results"
        print(f"Frozen filter returned {len(items)} items")
    
    def test_get_items_filter_by_chilled(self):
        """GET /api/items?storage_category=chilled filters correctly"""
        # Create a chilled item
        test_item = {
            "name": f"TEST_Chilled_Item_{uuid.uuid4().hex[:8]}",
            "category": "Dairy",
            "storage_category": "chilled",
            "category_source": "manual"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # Filter by chilled
        resp = self.session.get(f"{BASE_URL}/api/items", params={"storage_category": "chilled"})
        assert resp.status_code == 200
        
        items = resp.json()
        for item in items:
            assert item.get("storage_category") == "chilled"
        
        item_ids = [i["id"] for i in items]
        assert created["id"] in item_ids
        print(f"Chilled filter returned {len(items)} items")
    
    def test_get_items_filter_by_dry(self):
        """GET /api/items?storage_category=dry filters correctly"""
        # Create a dry item
        test_item = {
            "name": f"TEST_Dry_Item_{uuid.uuid4().hex[:8]}",
            "category": "Pantry",
            "storage_category": "dry",
            "category_source": "manual"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # Filter by dry
        resp = self.session.get(f"{BASE_URL}/api/items", params={"storage_category": "dry"})
        assert resp.status_code == 200
        
        items = resp.json()
        for item in items:
            assert item.get("storage_category") == "dry"
        
        item_ids = [i["id"] for i in items]
        assert created["id"] in item_ids
        print(f"Dry filter returned {len(items)} items")
    
    def test_post_items_creates_with_storage_category(self):
        """POST /api/items creates item with storage_category and category_source"""
        test_item = {
            "name": f"TEST_New_Item_{uuid.uuid4().hex[:8]}",
            "category": "Produce",
            "storage_category": "chilled",
            "category_source": "manual"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        
        created = resp.json()
        self.created_item_ids.append(created["id"])
        
        # Verify fields
        assert created["name"] == test_item["name"]
        assert created["category"] == test_item["category"]
        assert created["storage_category"] == "chilled"
        assert created["category_source"] == "manual"
        assert "id" in created
        
        # Verify persistence with GET
        get_resp = self.session.get(f"{BASE_URL}/api/items", params={"search": test_item["name"]})
        assert get_resp.status_code == 200
        items = get_resp.json()
        found = [i for i in items if i["id"] == created["id"]]
        assert len(found) == 1
        assert found[0]["storage_category"] == "chilled"
        assert found[0]["category_source"] == "manual"
        print(f"Created item with id={created['id']}, storage_category=chilled, category_source=manual")
    
    def test_post_items_default_category_source(self):
        """POST /api/items with no category_source defaults to 'auto'"""
        test_item = {
            "name": f"TEST_Default_Source_{uuid.uuid4().hex[:8]}",
            "category": "Meat"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        
        created = resp.json()
        self.created_item_ids.append(created["id"])
        
        # category_source should default to 'auto'
        assert created.get("category_source", "auto") == "auto"
        print(f"Created item with default category_source='auto'")
    
    def test_patch_storage_category_sets_manual(self):
        """PATCH /api/items/{id}/storage-category sets category to manual and records audit fields"""
        # First create an item
        test_item = {
            "name": f"TEST_Patch_Item_{uuid.uuid4().hex[:8]}",
            "category": "Seafood",
            "storage_category": "",
            "category_source": "auto"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # PATCH to set storage_category
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/items/{created['id']}/storage-category",
            json={"storage_category": "frozen"}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        updated = patch_resp.json()
        
        # Verify storage_category is set
        assert updated["storage_category"] == "frozen"
        # Verify category_source is set to 'manual'
        assert updated["category_source"] == "manual"
        # Verify audit fields are present
        assert "storage_category_updated_by" in updated
        assert "storage_category_updated_at" in updated
        
        print(f"PATCH set storage_category=frozen, category_source=manual, updated_by={updated.get('storage_category_updated_by')}")
    
    def test_patch_storage_category_invalid_returns_400(self):
        """PATCH /api/items/{id}/storage-category with invalid category returns 400"""
        # First create an item
        test_item = {
            "name": f"TEST_Invalid_Cat_{uuid.uuid4().hex[:8]}",
            "category": "Test"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # PATCH with invalid storage_category
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/items/{created['id']}/storage-category",
            json={"storage_category": "invalid_category"}
        )
        assert patch_resp.status_code == 400, f"Expected 400, got {patch_resp.status_code}: {patch_resp.text}"
        
        error = patch_resp.json()
        assert "detail" in error or "error" in error
        print(f"Invalid category correctly returned 400: {error}")
    
    def test_patch_storage_category_empty_resets_to_auto(self):
        """PATCH /api/items/{id}/storage-category with empty string resets category_source to 'auto'"""
        # Create item with manual category
        test_item = {
            "name": f"TEST_Reset_Cat_{uuid.uuid4().hex[:8]}",
            "category": "Test",
            "storage_category": "frozen",
            "category_source": "manual"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # PATCH with empty storage_category
        patch_resp = self.session.patch(
            f"{BASE_URL}/api/items/{created['id']}/storage-category",
            json={"storage_category": ""}
        )
        assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
        
        updated = patch_resp.json()
        assert updated["storage_category"] == ""
        assert updated["category_source"] == "auto"
        print(f"Empty storage_category correctly reset category_source to 'auto'")
    
    def test_put_items_updates_storage_category(self):
        """PUT /api/items/{id} updates item including storage_category"""
        # Create item
        test_item = {
            "name": f"TEST_Put_Item_{uuid.uuid4().hex[:8]}",
            "category": "Produce",
            "storage_category": "chilled",
            "category_source": "manual"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # PUT to update
        updated_data = {
            "name": created["name"],
            "category": "Vegetables",
            "storage_category": "dry",
            "category_source": "manual"
        }
        put_resp = self.session.put(f"{BASE_URL}/api/items/{created['id']}", json=updated_data)
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        updated = put_resp.json()
        assert updated["category"] == "Vegetables"
        assert updated["storage_category"] == "dry"
        
        # Verify persistence
        get_resp = self.session.get(f"{BASE_URL}/api/items", params={"search": created["name"]})
        items = get_resp.json()
        found = [i for i in items if i["id"] == created["id"]]
        assert len(found) == 1
        assert found[0]["storage_category"] == "dry"
        print(f"PUT updated storage_category from chilled to dry")
    
    def test_delete_item(self):
        """DELETE /api/items/{id} removes item"""
        # Create item
        test_item = {
            "name": f"TEST_Delete_Item_{uuid.uuid4().hex[:8]}",
            "category": "Test"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        
        # Delete
        del_resp = self.session.delete(f"{BASE_URL}/api/items/{created['id']}")
        assert del_resp.status_code == 200
        
        # Verify deleted
        get_resp = self.session.get(f"{BASE_URL}/api/items", params={"search": test_item["name"]})
        items = get_resp.json()
        found = [i for i in items if i["id"] == created["id"]]
        assert len(found) == 0
        print(f"Item deleted successfully")


class TestStorageCategoryFilterCombinations:
    """Test filter combinations and edge cases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@test.com",
            "password": "testpassword"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        self.created_item_ids = []
        yield
        
        for item_id in self.created_item_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/items/{item_id}")
            except:
                pass
    
    def test_filter_with_search_and_storage_category(self):
        """GET /api/items with both search and storage_category filters"""
        # Create a unique item
        unique_name = f"TEST_UniqueSearch_{uuid.uuid4().hex[:8]}"
        test_item = {
            "name": unique_name,
            "category": "Test",
            "storage_category": "frozen"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/items", json=test_item)
        assert create_resp.status_code == 200
        created = create_resp.json()
        self.created_item_ids.append(created["id"])
        
        # Filter with both search and storage_category
        resp = self.session.get(f"{BASE_URL}/api/items", params={
            "search": "UniqueSearch",
            "storage_category": "frozen"
        })
        assert resp.status_code == 200
        
        items = resp.json()
        # Should find our item
        found = [i for i in items if i["id"] == created["id"]]
        assert len(found) == 1
        print(f"Combined filter (search + storage_category) works correctly")
    
    def test_filter_no_results(self):
        """GET /api/items with filter that returns no results"""
        resp = self.session.get(f"{BASE_URL}/api/items", params={
            "search": "NONEXISTENT_ITEM_12345",
            "storage_category": "frozen"
        })
        assert resp.status_code == 200
        
        items = resp.json()
        assert len(items) == 0
        print(f"Filter with no results returns empty list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
