#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime, timedelta

class RestaurantAccountantAPITester:
    def __init__(self, base_url="https://invoice-ai-35.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.user_id = None
        self.restaurant_id = None
        
        # Test data containers
        self.created_purchase_id = None
        self.created_sale_id = None
        self.created_supplier_id = None
        self.created_item_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json() if response.text else {}
                    return success, response_data
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    # Auth Tests
    def test_register_user(self):
        """Test user registration"""
        test_user_data = {
            "email": f"test_{datetime.now().strftime('%H%M%S')}@testrestaurant.com",
            "password": "testpass123",
            "name": "Test User", 
            "restaurant_name": "Test Restaurant"
        }
        success, response = self.run_test(
            "User Registration",
            "POST", 
            "auth/register",
            200,
            data=test_user_data
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response.get('user', {}).get('id')
            self.restaurant_id = response.get('user', {}).get('restaurant_id')
        return success

    def test_login_demo_user(self):
        """Test login with demo user"""
        success, response = self.run_test(
            "Demo User Login",
            "POST",
            "auth/login", 
            200,
            data={"email": "demo@test.com", "password": "password123"}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response.get('user', {}).get('id')
            self.restaurant_id = response.get('user', {}).get('restaurant_id')
        return success

    def test_auth_me(self):
        """Test getting current user info"""
        success, response = self.run_test(
            "Auth Me",
            "GET",
            "auth/me",
            200
        )
        return success

    # Dashboard Tests
    def test_dashboard_summary(self):
        """Test dashboard summary endpoint"""
        success, response = self.run_test(
            "Dashboard Summary",
            "GET",
            "dashboard/summary",
            200
        )
        if success:
            required_fields = ['today_sales', 'today_purchases', 'week_sales', 'week_purchases', 'month_sales', 'month_purchases']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                print(f"⚠️  Missing fields in dashboard: {missing_fields}")
        return success

    def test_seed_data(self):
        """Test seed data endpoint"""
        success, response = self.run_test(
            "Seed Data Creation", 
            "POST",
            "seed",
            200
        )
        return success

    # Purchase Tests
    def test_create_purchase(self):
        """Test creating a purchase"""
        purchase_data = {
            "supplier_name": "Test Supplier",
            "invoice_number": f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "invoice_date": "2024-01-15",
            "items": [
                {
                    "raw_name": "Test Item",
                    "quantity": 10,
                    "unit": "pcs",
                    "unit_price": 5.00,
                    "total": 50.00
                }
            ],
            "subtotal": 50.00,
            "tax": 5.00,
            "total": 55.00
        }
        success, response = self.run_test(
            "Create Purchase",
            "POST",
            "purchases",
            201,
            data=purchase_data
        )
        if success and 'id' in response:
            self.created_purchase_id = response['id']
        return success

    def test_list_purchases(self):
        """Test listing purchases"""
        success, response = self.run_test(
            "List Purchases",
            "GET",
            "purchases",
            200
        )
        return success

    def test_get_purchase(self):
        """Test getting specific purchase"""
        if not self.created_purchase_id:
            print("⚠️  Skipped - No purchase ID available")
            return True
            
        success, response = self.run_test(
            "Get Purchase Details",
            "GET",
            f"purchases/{self.created_purchase_id}",
            200
        )
        return success

    def test_delete_purchase(self):
        """Test deleting a purchase"""
        if not self.created_purchase_id:
            print("⚠️  Skipped - No purchase ID available")
            return True
            
        success, response = self.run_test(
            "Delete Purchase",
            "DELETE",
            f"purchases/{self.created_purchase_id}",
            200
        )
        return success

    # Sales Tests
    def test_create_sale(self):
        """Test creating a sale"""
        sale_data = {
            "report_date": "2024-01-15",
            "total_sales": 500.00,
            "items": [
                {
                    "menu_item": "Test Menu Item",
                    "quantity": 20,
                    "revenue": 500.00
                }
            ]
        }
        success, response = self.run_test(
            "Create Sale",
            "POST",
            "sales",
            201,
            data=sale_data
        )
        if success and 'id' in response:
            self.created_sale_id = response['id']
        return success

    def test_list_sales(self):
        """Test listing sales"""
        success, response = self.run_test(
            "List Sales",
            "GET", 
            "sales",
            200
        )
        return success

    # Supplier Tests
    def test_create_supplier(self):
        """Test creating a supplier"""
        supplier_data = {
            "name": "Test Supplier Co",
            "contact_person": "John Doe",
            "phone": "123-456-7890",
            "email": "supplier@test.com",
            "address": "123 Test St"
        }
        success, response = self.run_test(
            "Create Supplier",
            "POST",
            "suppliers", 
            201,
            data=supplier_data
        )
        if success and 'id' in response:
            self.created_supplier_id = response['id']
        return success

    def test_list_suppliers(self):
        """Test listing suppliers"""
        success, response = self.run_test(
            "List Suppliers",
            "GET",
            "suppliers",
            200
        )
        return success

    def test_update_supplier(self):
        """Test updating a supplier"""
        if not self.created_supplier_id:
            print("⚠️  Skipped - No supplier ID available")
            return True
            
        update_data = {
            "name": "Updated Supplier Co",
            "contact_person": "Jane Doe",
            "phone": "123-456-7891",
            "email": "updated@test.com",
            "address": "456 Updated St"
        }
        success, response = self.run_test(
            "Update Supplier",
            "PUT",
            f"suppliers/{self.created_supplier_id}",
            200,
            data=update_data
        )
        return success

    def test_delete_supplier(self):
        """Test deleting a supplier"""
        if not self.created_supplier_id:
            print("⚠️  Skipped - No supplier ID available") 
            return True
            
        success, response = self.run_test(
            "Delete Supplier",
            "DELETE",
            f"suppliers/{self.created_supplier_id}",
            200
        )
        return success

    # Item Tests
    def test_create_item(self):
        """Test creating canonical item"""
        item_data = {
            "name": "Test Item",
            "category": "Test Category"
        }
        success, response = self.run_test(
            "Create Item",
            "POST",
            "items",
            201,
            data=item_data
        )
        if success and 'id' in response:
            self.created_item_id = response['id']
        return success

    def test_list_items(self):
        """Test listing items"""
        success, response = self.run_test(
            "List Items",
            "GET",
            "items",
            200
        )
        return success

    def test_create_alias(self):
        """Test creating item alias"""
        if not self.created_item_id:
            print("⚠️  Skipped - No item ID available")
            return True
            
        alias_data = {
            "canonical_item_id": self.created_item_id,
            "alias_name": "Test Item Alias"
        }
        success, response = self.run_test(
            "Create Item Alias",
            "POST", 
            "aliases",
            201,
            data=alias_data
        )
        return success

    # Report Tests
    def test_reports(self):
        """Test reports endpoint"""
        success_weekly, response = self.run_test(
            "Weekly Report",
            "GET",
            "reports",
            200,
            params={"report_type": "weekly"}
        )
        
        success_monthly, response = self.run_test(
            "Monthly Report", 
            "GET",
            "reports",
            200,
            params={"report_type": "monthly"}
        )
        
        success_yearly, response = self.run_test(
            "Yearly Report",
            "GET", 
            "reports",
            200,
            params={"report_type": "yearly"}
        )
        
        return success_weekly and success_monthly and success_yearly

    # Chat Tests
    def test_chat_messages(self):
        """Test getting chat messages"""
        success, response = self.run_test(
            "Get Chat Messages",
            "GET",
            "chat/messages",
            200
        )
        return success

    def test_send_chat_message(self):
        """Test sending chat message"""
        success, response = self.run_test(
            "Send Chat Message",
            "POST",
            "chat",
            200,
            data={"message": "How much did I spend this week?"}
        )
        if success:
            print("   💬 AI Response:", response.get('assistant_message', {}).get('content', '')[:100] + "...")
        return success

    # Settings Tests  
    def test_get_settings(self):
        """Test getting settings"""
        success, response = self.run_test(
            "Get Settings",
            "GET", 
            "settings",
            200
        )
        return success

    def test_update_settings(self):
        """Test updating settings"""
        success, response = self.run_test(
            "Update Settings",
            "PUT",
            "settings", 
            200,
            data={"name": "Updated Test User"}
        )
        return success

    # Alerts Tests
    def test_list_alerts(self):
        """Test listing alerts"""
        success, response = self.run_test(
            "List Alerts",
            "GET",
            "alerts",
            200
        )
        return success

def main():
    print("🧪 Restaurant Accountant AI - Backend API Testing")
    print("=" * 50)
    
    tester = RestaurantAccountantAPITester()
    
    # Test with demo user login
    print("\n📋 PHASE 1: Authentication Tests")
    if not tester.test_login_demo_user():
        print("❌ Demo login failed, trying user registration...")
        if not tester.test_register_user():
            print("❌ Authentication completely failed, stopping tests")
            return 1
    
    tester.test_auth_me()
    
    print("\n📋 PHASE 2: Dashboard & Data Tests")
    tester.test_dashboard_summary()
    tester.test_seed_data()
    
    print("\n📋 PHASE 3: Purchase Management Tests") 
    tester.test_create_purchase()
    tester.test_list_purchases()
    tester.test_get_purchase()
    
    print("\n📋 PHASE 4: Sales Management Tests")
    tester.test_create_sale()
    tester.test_list_sales()
    
    print("\n📋 PHASE 5: Supplier Management Tests")
    tester.test_create_supplier()
    tester.test_list_suppliers()
    tester.test_update_supplier()
    
    print("\n📋 PHASE 6: Item Management Tests")
    tester.test_create_item()
    tester.test_list_items()
    tester.test_create_alias()
    
    print("\n📋 PHASE 7: Reports Tests")
    tester.test_reports()
    
    print("\n📋 PHASE 8: AI Chat Tests") 
    tester.test_chat_messages()
    tester.test_send_chat_message()
    
    print("\n📋 PHASE 9: Settings & Alerts Tests")
    tester.test_get_settings()
    tester.test_update_settings()
    tester.test_list_alerts()
    
    # Cleanup tests
    print("\n📋 PHASE 10: Cleanup Tests")
    tester.test_delete_purchase() 
    tester.test_delete_supplier()
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 Backend API Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"📈 Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 85:
        print("✅ Backend APIs are working well!")
        return 0
    elif success_rate >= 70:
        print("⚠️  Backend APIs have some issues but mostly working")
        return 0
    else:
        print("❌ Backend APIs have significant issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())