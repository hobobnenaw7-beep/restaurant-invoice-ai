from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
import base64
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import SettingsUpdate

router = APIRouter()

SETTINGS_DEFAULTS = {
    "currency": "USD", "default_tax_rate": 0, "default_expense_category": "Rent",
    "alerts_enabled": True, "alert_price_increase": True, "alert_cheaper_vendor": True, "alert_not_ordered": True,
    "language": "en", "date_format": "YYYY-MM-DD",
}


@router.get("/settings")
async def get_settings(user=Depends(get_user)):
    r = await db.restaurants.find_one({"id": user["restaurant_id"]}, {"_id": 0}) or {}
    settings = {k: r.get(k, v) for k, v in SETTINGS_DEFAULTS.items()}
    return {
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        "restaurant": {**r, **settings},
    }


@router.put("/settings")
async def update_settings(data: SettingsUpdate, user=Depends(get_user)):
    if data.name:
        await db.users.update_one({"id": user["id"]}, {"$set": {"name": data.name}})
    rid = user["restaurant_id"]
    update_fields = {}
    if data.restaurant_name is not None: update_fields["name"] = data.restaurant_name
    if data.address is not None: update_fields["address"] = data.address
    if data.phone is not None: update_fields["phone"] = data.phone
    if data.email is not None: update_fields["email"] = data.email
    if data.currency is not None: update_fields["currency"] = data.currency
    if data.default_tax_rate is not None: update_fields["default_tax_rate"] = data.default_tax_rate
    if data.default_expense_category is not None: update_fields["default_expense_category"] = data.default_expense_category
    if data.alerts_enabled is not None: update_fields["alerts_enabled"] = data.alerts_enabled
    if data.alert_price_increase is not None: update_fields["alert_price_increase"] = data.alert_price_increase
    if data.alert_cheaper_vendor is not None: update_fields["alert_cheaper_vendor"] = data.alert_cheaper_vendor
    if data.alert_not_ordered is not None: update_fields["alert_not_ordered"] = data.alert_not_ordered
    if data.language is not None: update_fields["language"] = data.language
    if data.date_format is not None: update_fields["date_format"] = data.date_format
    if update_fields:
        await db.restaurants.update_one({"id": rid}, {"$set": update_fields})
    updated_user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return await get_settings(updated_user)


@router.post("/settings/reset-data")
async def reset_all_data(user=Depends(get_user)):
    rid = user["restaurant_id"]
    for coll_name in ["purchases", "sales", "salaries", "other_expenses", "suppliers", "canonical_items", "item_aliases", "alerts", "records_library"]:
        await db[coll_name].delete_many({"restaurant_id": rid})
    await db.chat_messages.delete_many({"user_id": user["id"]})
    return {"status": "All data has been reset"}


@router.post("/settings/upload-logo")
async def upload_logo(file: UploadFile = File(...), user=Depends(get_user)):
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(400, "Logo must be under 2MB")
    b64 = base64.b64encode(content).decode()
    mime = file.content_type or "image/png"
    data_url = f"data:{mime};base64,{b64}"
    await db.restaurants.update_one({"id": user["restaurant_id"]}, {"$set": {"logo": data_url}})
    return {"logo": data_url}


@router.post("/seed")
async def seed_data(user=Depends(get_user)):
    from seed_data import generate_seed_data
    await generate_seed_data(db, user["restaurant_id"])
    return {"status": "Seed data created successfully"}
