from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import SalesCreate, SalesUpdate
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


@router.get("/sales")
async def list_sales(user=Depends(get_user), search: str = "", date_from: str = "", date_to: str = "", sort_by: str = "report_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if date_from:
        query.setdefault("report_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("report_date", {})["$lte"] = date_to
    return await db.sales.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)


@router.get("/sales/{sid}")
async def get_sale(sid: str, user=Depends(get_user)):
    s = await db.sales.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    return s


@router.post("/sales")
async def create_sale(data: SalesCreate, user=Depends(get_user)):
    doc = data.model_dump()
    if doc.get("date_from") and doc.get("date_to"):
        if doc["date_to"] < doc["date_from"]:
            raise HTTPException(400, "To Date cannot be earlier than From Date")
        doc["report_date"] = doc["date_from"]
        doc["is_single_day"] = doc["date_from"] == doc["date_to"]
    elif doc.get("report_date"):
        doc["date_from"] = doc["report_date"]
        doc["date_to"] = doc["report_date"]
        doc["is_single_day"] = True
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by_id"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["approval_status"] = compute_approval_status(user, doc.get("total_sales", 0))
    await db.sales.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Sale", doc["id"], f'{user["name"]} created sale ${doc.get("total_sales", 0)} ({doc.get("report_date", "")})', new_value={"total_sales": doc.get("total_sales"), "report_date": doc.get("report_date")})
    return doc


@router.put("/sales/{sid}")
async def update_sale(sid: str, data: SalesUpdate, user=Depends(get_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    old = await db.sales.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    old_vals = {k: old.get(k) for k in update_data}
    await db.sales.update_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Sale", sid, f'{user["name"]} updated sale ({old.get("report_date", "")})', old_value=old_vals, new_value=update_data)
    return await db.sales.find_one({"id": sid}, {"_id": 0})


@router.delete("/sales/{sid}")
async def delete_sale(sid: str, user=Depends(get_user)):
    old = await db.sales.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.sales.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Sale", sid, f'{user["name"]} deleted sale ${old.get("total_sales", 0)} ({old.get("report_date", "")})', old_value={"total_sales": old.get("total_sales"), "report_date": old.get("report_date")})
    return {"status": "deleted"}
