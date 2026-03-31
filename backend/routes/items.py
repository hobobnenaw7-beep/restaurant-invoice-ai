from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import CanonicalItemCreate, ItemAliasCreate
from services.audit import audit_log

router = APIRouter()


@router.get("/items")
async def list_items(user=Depends(get_user), search: str = ""):
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    items = await db.canonical_items.find(query, {"_id": 0}).to_list(1000)
    for item in items:
        item["aliases"] = await db.item_aliases.find({"canonical_item_id": item["id"], "restaurant_id": user["restaurant_id"]}, {"_id": 0}).to_list(100)
    return items


@router.post("/items")
async def create_item(data: CanonicalItemCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.canonical_items.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Item", doc["id"], f'{user["name"]} created item {doc.get("name", "")}', new_value={"name": doc.get("name"), "unit": doc.get("unit"), "category": doc.get("category")})
    return doc


@router.put("/items/{iid}")
async def update_item(iid: str, data: CanonicalItemCreate, user=Depends(get_user)):
    old = await db.canonical_items.find_one({"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    update_data = data.model_dump()
    old_vals = {k: old.get(k) for k in update_data} if old else {}
    await db.canonical_items.update_one({"id": iid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Item", iid, f'{user["name"]} updated item {old.get("name", "") if old else ""}', old_value=old_vals, new_value=update_data)
    return await db.canonical_items.find_one({"id": iid}, {"_id": 0})


@router.delete("/items/{iid}")
async def delete_item(iid: str, user=Depends(get_user)):
    old = await db.canonical_items.find_one({"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    await db.canonical_items.delete_one({"id": iid, "restaurant_id": user["restaurant_id"]})
    await db.item_aliases.delete_many({"canonical_item_id": iid})
    await audit_log(user, "DELETE", "Item", iid, f'{user["name"]} deleted item {old.get("name", "") if old else ""}', old_value={"name": old.get("name")} if old else None)
    return {"status": "deleted"}


@router.post("/aliases")
async def create_alias(data: ItemAliasCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.item_aliases.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/aliases/{aid}")
async def delete_alias(aid: str, user=Depends(get_user)):
    await db.item_aliases.delete_one({"id": aid, "restaurant_id": user["restaurant_id"]})
    return {"status": "deleted"}


@router.get("/items/{item_id}/price-history")
async def item_price_history(item_id: str, user=Depends(get_user)):
    """Get price history for a canonical item by scanning all purchases matching its name + aliases."""
    rid = user["restaurant_id"]
    item = await db.canonical_items.find_one({"id": item_id, "restaurant_id": rid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")

    names = {item["name"].lower()}
    aliases = await db.item_aliases.find({"canonical_item_id": item_id, "restaurant_id": rid}, {"_id": 0}).to_list(200)
    for a in aliases:
        names.add(a["alias_name"].lower())

    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}).to_list(10000)

    records = []
    for p in purchases:
        vendor = p.get("supplier_name", "Unknown")
        date = p.get("invoice_date", "")
        for it in p.get("items", []):
            raw = it.get("raw_name", "").lower()
            if raw in names:
                records.append({
                    "vendor": vendor, "date": date,
                    "unit_price": round(float(it.get("unit_price", 0)), 2),
                    "quantity": float(it.get("quantity", 0)),
                    "unit": it.get("unit", ""), "raw_name": it.get("raw_name", ""),
                })

    records.sort(key=lambda x: x["date"])

    date_prices = {}
    for r in records:
        date_prices.setdefault(r["date"], []).append(r["unit_price"])
    trend = [{"date": d, "avg_price": round(sum(ps) / len(ps), 2)} for d, ps in sorted(date_prices.items())]

    all_prices = [r["unit_price"] for r in records if r["unit_price"] > 0]
    summary = {
        "total_records": len(records),
        "avg_price": round(sum(all_prices) / len(all_prices), 2) if all_prices else 0,
        "min_price": round(min(all_prices), 2) if all_prices else 0,
        "max_price": round(max(all_prices), 2) if all_prices else 0,
        "vendors": list(set(r["vendor"] for r in records)),
    }

    return {"item_name": item["name"], "records": records, "trend": trend, "summary": summary}
