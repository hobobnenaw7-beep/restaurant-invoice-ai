"""
Database Migration: Backfill ownership and source fields
=========================================================
Renames created_by_id → created_by_user_id where needed.
Adds source_type, created_by_user_id, created_by_name to records missing them.
Adds data_scope to existing users.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "restaurant_ai"


async def migrate():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("=" * 60)
    print("  MIGRATION: Backfill ownership + source fields")
    print("=" * 60)

    # 1. Users: add data_scope where missing
    result = await db.users.update_many(
        {"data_scope": {"$exists": False}, "role": {"$in": ["manager", "accountant"]}},
        {"$set": {"data_scope": "all"}},
    )
    print(f"  Users (manager/accountant) → data_scope=all: {result.modified_count}")

    result = await db.users.update_many(
        {"data_scope": {"$exists": False}},
        {"$set": {"data_scope": "own"}},
    )
    print(f"  Users (other) → data_scope=own: {result.modified_count}")

    # 2. Sales: rename created_by_id → created_by_user_id
    result = await db.sales.update_many(
        {"created_by_id": {"$exists": True}, "created_by_user_id": {"$exists": False}},
        [{"$set": {"created_by_user_id": "$created_by_id"}}],
    )
    print(f"  Sales: renamed created_by_id → created_by_user_id: {result.modified_count}")

    # Sales: add source_type where missing
    result = await db.sales.update_many(
        {"source_type": {"$exists": False}},
        {"$set": {"source_type": "manual"}},
    )
    print(f"  Sales: added source_type=manual: {result.modified_count}")

    # 3. Other expenses: rename created_by_id → created_by_user_id
    result = await db.other_expenses.update_many(
        {"created_by_id": {"$exists": True}, "created_by_user_id": {"$exists": False}},
        [{"$set": {"created_by_user_id": "$created_by_id"}}],
    )
    print(f"  Other expenses: renamed created_by_id → created_by_user_id: {result.modified_count}")

    # Other expenses: add source_type
    result = await db.other_expenses.update_many(
        {"source_type": {"$exists": False}},
        {"$set": {"source_type": "manual"}},
    )
    print(f"  Other expenses: added source_type=manual: {result.modified_count}")

    # 4. Uploaded receipts: add ownership fields
    result = await db.uploaded_receipts.update_many(
        {"created_by_user_id": {"$exists": False}},
        {"$set": {
            "created_by_user_id": "system",
            "created_by_name": "System",
            "source_type": "upload",
        }},
    )
    print(f"  Uploaded receipts: added ownership: {result.modified_count}")

    # 5. Receipt extractions: add ownership fields
    result = await db.receipt_extractions.update_many(
        {"created_by_user_id": {"$exists": False}},
        {"$set": {
            "created_by_user_id": "system",
            "created_by_name": "System",
            "source_type": "upload",
        }},
    )
    print(f"  Receipt extractions: added ownership: {result.modified_count}")

    # 6. Extracted items: add ownership fields
    result = await db.extracted_items.update_many(
        {"created_by_user_id": {"$exists": False}},
        {"$set": {
            "created_by_user_id": "system",
            "created_by_name": "System",
            "source_type": "upload",
        }},
    )
    print(f"  Extracted items: added ownership: {result.modified_count}")

    # 7. Records library: add ownership fields
    result = await db.records_library.update_many(
        {"created_by_user_id": {"$exists": False}},
        {"$set": {
            "created_by_user_id": "system",
            "created_by_name": "System",
            "source_type": "upload",
        }},
    )
    print(f"  Records library: added ownership: {result.modified_count}")

    print("\n  MIGRATION COMPLETE")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
