import uuid
import random
from datetime import datetime, timezone, timedelta


async def generate_seed_data(db, restaurant_id):
    rid = restaurant_id
    now = datetime.now(timezone.utc)

    for col in ['suppliers', 'purchases', 'sales', 'canonical_items', 'item_aliases', 'alerts']:
        await db[col].delete_many({"restaurant_id": rid})

    suppliers = [
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "name": "Sysco Restaurant Supply", "contact_person": "John Smith", "phone": "(555) 123-4567", "email": "orders@sysco.example.com", "address": "100 Industrial Blvd", "created_at": now.isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "name": "Fresh Farms Produce", "contact_person": "Maria Garcia", "phone": "(555) 234-5678", "email": "sales@freshfarms.example.com", "address": "45 Farm Road", "created_at": now.isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "name": "City Meats & Poultry", "contact_person": "Ahmed Hassan", "phone": "(555) 345-6789", "email": "orders@citymeats.example.com", "address": "200 Market St", "created_at": now.isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "name": "Ocean Blue Seafood", "contact_person": "Lisa Chen", "phone": "(555) 456-7890", "email": "orders@oceanblue.example.com", "address": "78 Harbor Dr", "created_at": now.isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "name": "Mediterranean Imports", "contact_person": "Nikos Papadopoulos", "phone": "(555) 567-8901", "email": "sales@medimports.example.com", "address": "320 Olive Ave", "created_at": now.isoformat()},
    ]
    await db.suppliers.insert_many(suppliers)

    items_data = [
        ("Beef", "Meat", ["Ground Beef", "Beef 80/20", "Fresh Beef"]),
        ("Chicken Breast", "Meat", ["Chicken Breasts", "Boneless Chicken"]),
        ("Salmon Fillet", "Seafood", ["Fresh Salmon", "Atlantic Salmon"]),
        ("Rice", "Grains", ["Jasmine Rice", "White Rice", "Basmati Rice"]),
        ("Olive Oil", "Oils", ["Extra Virgin Olive Oil", "EVOO"]),
        ("Tomatoes", "Vegetables", ["Roma Tomatoes", "Fresh Tomatoes", "Cherry Tomatoes"]),
        ("Onions", "Vegetables", ["Yellow Onions", "White Onions"]),
        ("All-Purpose Flour", "Baking", ["Flour", "AP Flour"]),
        ("Butter", "Dairy", ["Unsalted Butter", "Sweet Cream Butter"]),
        ("Mozzarella", "Dairy", ["Cheese Mozzarella", "Fresh Mozzarella"]),
    ]

    canonical_items = []
    for name, cat, aliases in items_data:
        item_id = str(uuid.uuid4())
        canonical_items.append({"id": item_id, "restaurant_id": rid, "name": name, "category": cat, "created_at": now.isoformat()})
        for alias in aliases:
            await db.item_aliases.insert_one({"id": str(uuid.uuid4()), "canonical_item_id": item_id, "restaurant_id": rid, "alias_name": alias, "created_at": now.isoformat()})
    await db.canonical_items.insert_many(canonical_items)

    item_prices = {
        "Ground Beef": (8.5, "lb"), "Chicken Breasts": (5.99, "lb"), "Fresh Salmon": (14.99, "lb"),
        "Jasmine Rice": (2.49, "lb"), "Extra Virgin Olive Oil": (12.99, "bottle"),
        "Roma Tomatoes": (2.99, "lb"), "Yellow Onions": (1.49, "lb"), "Flour": (3.99, "bag"),
        "Unsalted Butter": (4.99, "lb"), "Cheese Mozzarella": (6.99, "lb"),
    }

    menu_items = ["Grilled Steak", "Chicken Parmesan", "Salmon Bowl", "Caesar Salad", "Margherita Pizza", "Pasta Bolognese", "Fish Tacos", "Burger Deluxe", "Mushroom Risotto", "Seafood Platter"]

    purchases = []
    for day_offset in range(60):
        if random.random() < 0.65:
            date = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            supplier = random.choice(suppliers)
            items = []
            for _ in range(random.randint(2, 6)):
                item_name, (base_price, unit) = random.choice(list(item_prices.items()))
                price_mult = 1.0 + random.uniform(-0.05, 0.15) if day_offset < 14 else 1.0 + random.uniform(-0.05, 0.05)
                price = round(base_price * price_mult, 2)
                qty = random.randint(5, 50)
                items.append({"raw_name": item_name, "quantity": qty, "unit": unit, "unit_price": price, "total": round(price * qty, 2)})
            subtotal = round(sum(i["total"] for i in items), 2)
            tax = round(subtotal * 0.08, 2)
            purchases.append({
                "id": str(uuid.uuid4()), "restaurant_id": rid, "supplier_name": supplier["name"],
                "supplier_id": supplier["id"], "invoice_number": f"INV-{random.randint(10000, 99999)}",
                "invoice_date": date, "items": items, "subtotal": subtotal, "tax": tax,
                "total": round(subtotal + tax, 2), "created_at": now.isoformat()
            })
    if purchases:
        await db.purchases.insert_many(purchases)

    sales_list = []
    for day_offset in range(60):
        date = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        day_of_week = (now - timedelta(days=day_offset)).weekday()
        items = []
        for menu_item in random.sample(menu_items, random.randint(5, 10)):
            qty = random.randint(10, 60)
            price = random.uniform(12, 35)
            if day_of_week >= 4:
                qty = int(qty * 1.4)
            items.append({"menu_item": menu_item, "quantity": qty, "revenue": round(qty * price, 2)})
        total_sales = round(sum(i["revenue"] for i in items), 2)
        sales_list.append({
            "id": str(uuid.uuid4()), "restaurant_id": rid, "report_date": date,
            "total_sales": total_sales, "items": items, "created_at": now.isoformat()
        })
    if sales_list:
        await db.sales.insert_many(sales_list)

    alerts = [
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "price_increase", "message": "Ground Beef price increased by 12% compared to last week", "severity": "high", "item_name": "Ground Beef", "supplier_name": "City Meats & Poultry", "is_read": False, "created_at": (now - timedelta(days=1)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "price_increase", "message": "Fresh Salmon price increased by 15% compared to last week", "severity": "high", "item_name": "Fresh Salmon", "supplier_name": "Ocean Blue Seafood", "is_read": False, "created_at": (now - timedelta(days=2)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "supplier_spending", "message": "Spending at Sysco Restaurant Supply increased by 25% this month", "severity": "medium", "supplier_name": "Sysco Restaurant Supply", "is_read": False, "created_at": (now - timedelta(days=3)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "price_increase", "message": "Extra Virgin Olive Oil price increased by 11%", "severity": "medium", "item_name": "Olive Oil", "supplier_name": "Mediterranean Imports", "is_read": False, "created_at": (now - timedelta(days=4)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "purchase_sales_mismatch", "message": "Purchases increased 18% while sales decreased 5% this week", "severity": "high", "is_read": False, "created_at": (now - timedelta(days=5)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "price_increase", "message": "Chicken Breasts price increased by 10%", "severity": "low", "item_name": "Chicken Breast", "supplier_name": "City Meats & Poultry", "is_read": True, "created_at": (now - timedelta(days=7)).isoformat()},
        {"id": str(uuid.uuid4()), "restaurant_id": rid, "alert_type": "supplier_spending", "message": "Spending at Ocean Blue Seafood increased by 30% this month", "severity": "high", "supplier_name": "Ocean Blue Seafood", "is_read": True, "created_at": (now - timedelta(days=10)).isoformat()},
    ]
    await db.alerts.insert_many(alerts)
    return True
