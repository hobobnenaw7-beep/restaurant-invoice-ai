from fastapi import APIRouter, HTTPException, Depends
import uuid, re
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import SupplierCreate
from services.audit import audit_log

router = APIRouter()


@router.get("/suppliers")
async def list_suppliers(user=Depends(get_user), search: str = ""):
    rid = user["restaurant_id"]
    query = {"restaurant_id": rid}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    suppliers = await db.suppliers.find(query, {"_id": 0}).to_list(1000)
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0, "supplier_name": 1, "total": 1}).to_list(10000)

    seen = {}
    ids_to_delete = []
    for s in suppliers:
        key = (s.get("name") or "").strip().upper()
        if key not in seen:
            seen[key] = s
        else:
            ids_to_delete.append(s["id"])

    if ids_to_delete:
        await db.suppliers.delete_many({"restaurant_id": rid, "id": {"$in": ids_to_delete}})

    deduped = list(seen.values())
    for s in deduped:
        name = s["name"]
        matching = [p for p in purchases if (p.get("supplier_name") or "").strip().upper() == name.strip().upper()]
        s["total_spending"] = round(sum(p.get("total", 0) for p in matching), 2)
        s["invoice_count"] = len(matching)
    return deduped


@router.post("/suppliers")
async def create_supplier(data: SupplierCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Vendor", doc["id"], f'{user["name"]} created vendor {doc.get("name", "")}', new_value={"name": doc.get("name"), "contact_name": doc.get("contact_name"), "phone": doc.get("phone")})
    return doc


@router.put("/suppliers/{sid}")
async def update_supplier(sid: str, data: SupplierCreate, user=Depends(get_user)):
    rid = user["restaurant_id"]
    old = await db.suppliers.find_one({"id": sid, "restaurant_id": rid}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Vendor not found")
    update_data = data.model_dump()
    old_name = old.get("name", "")
    new_name = update_data.get("name", old_name)
    old_vals = {k: old.get(k) for k in update_data}

    if old_name and new_name and old_name != new_name:
        await db.purchases.update_many(
            {"restaurant_id": rid, "supplier_name": {"$regex": f"^{re.escape(old_name)}$", "$options": "i"}},
            {"$set": {"supplier_name": new_name}}
        )
        existing_target = await db.suppliers.find_one(
            {"restaurant_id": rid, "name": {"$regex": f"^{re.escape(new_name)}$", "$options": "i"}, "id": {"$ne": sid}},
            {"_id": 0}
        )
        if existing_target:
            await db.suppliers.delete_one({"id": sid, "restaurant_id": rid})
            await audit_log(user, "UPDATE", "Vendor", sid, f'{user["name"]} merged vendor "{old_name}" into "{new_name}"', old_value=old_vals, new_value=update_data)
            return existing_target

    await db.suppliers.update_one({"id": sid, "restaurant_id": rid}, {"$set": update_data})
    updated = await db.suppliers.find_one({"id": sid}, {"_id": 0})
    await audit_log(user, "UPDATE", "Vendor", sid, f'{user["name"]} updated vendor {old_name}', old_value=old_vals, new_value=update_data)
    return updated


@router.delete("/suppliers/{sid}")
async def delete_supplier(sid: str, user=Depends(get_user)):
    old = await db.suppliers.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.suppliers.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Vendor", sid, f'{user["name"]} deleted vendor {old.get("name", "")}', old_value={"name": old.get("name")})
    return {"status": "deleted"}


@router.get("/suppliers/{sid}/detail")
async def supplier_detail(sid: str, user=Depends(get_user)):
    rid = user["restaurant_id"]
    supplier = await db.suppliers.find_one({"id": sid, "restaurant_id": rid}, {"_id": 0})
    if not supplier:
        raise HTTPException(404, "Vendor not found")
    name = supplier["name"]
    purchases = await db.purchases.find(
        {"restaurant_id": rid, "supplier_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 0}
    ).to_list(10000)
    supplier["total_spending"] = round(sum(p.get("total", 0) for p in purchases), 2)
    supplier["invoice_count"] = len(purchases)
    return supplier


@router.get("/suppliers/{sid}/purchases")
async def supplier_purchases(sid: str, user=Depends(get_user), search: str = "", date_from: str = "", date_to: str = ""):
    rid = user["restaurant_id"]
    supplier = await db.suppliers.find_one({"id": sid, "restaurant_id": rid}, {"_id": 0})
    if not supplier:
        raise HTTPException(404, "Vendor not found")
    name = supplier["name"]
    query = {"restaurant_id": rid, "supplier_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if search:
        query["invoice_number"] = {"$regex": search, "$options": "i"}
    if date_from:
        query.setdefault("invoice_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("invoice_date", {})["$lte"] = date_to
    purchases = await db.purchases.find(query, {"_id": 0}).sort("invoice_date", -1).to_list(10000)
    return purchases
