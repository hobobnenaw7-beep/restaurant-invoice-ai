import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

async def patch():
    r = await db.users.update_many(
        {"role": {"$exists": False}},
        {"$set": {"role": "manager", "status": "active"}}
    )
    print(f"Updated {r.modified_count} users with role/status")

asyncio.run(patch())
