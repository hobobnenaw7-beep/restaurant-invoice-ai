from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import SalaryCreate, SalaryUpdate
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


@router.get("/salaries")
async def list_salaries(user=Depends(get_user), date_from: str = "", date_to: str = "", sort_by: str = "payment_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if date_from:
        query.setdefault("payment_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("payment_date", {})["$lte"] = date_to
    direction = -1 if sort_order == "desc" else 1
    if sort_by == "payment_date":
        pipeline = [
            {"$match": query},
            {"$addFields": {"_sort_date": {"$cond": [{"$gt": ["$payment_date", ""]}, "$payment_date", "$created_at"]}}},
            {"$sort": {"_sort_date": direction}},
            {"$project": {"_id": 0, "_sort_date": 0}},
        ]
        return await db.salaries.aggregate(pipeline).to_list(1000)
    return await db.salaries.find(query, {"_id": 0}).sort(sort_by, direction).to_list(1000)


@router.post("/salaries")
async def create_salary(data: SalaryCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by_id"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["approval_status"] = compute_approval_status(user, doc.get("amount", 0))
    await db.salaries.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Expense", doc["id"], f'{user["name"]} created salary ${doc.get("amount", 0)} ({doc.get("employee_name", "")})', new_value={"employee": doc.get("employee_name"), "amount": doc.get("amount"), "payment_date": doc.get("payment_date")})
    return doc


@router.delete("/salaries/{sid}")
async def delete_salary(sid: str, user=Depends(get_user)):
    old = await db.salaries.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.salaries.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Expense", sid, f'{user["name"]} deleted salary ${old.get("amount", 0)} ({old.get("employee_name", "")})', old_value={"employee": old.get("employee_name"), "amount": old.get("amount")})
    return {"status": "deleted"}


@router.put("/salaries/{sid}")
async def update_salary(sid: str, data: SalaryUpdate, user=Depends(get_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    old = await db.salaries.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    old_vals = {k: old.get(k) for k in update_data}
    await db.salaries.update_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Expense", sid, f'{user["name"]} updated salary ({old.get("employee_name", "")})', old_value=old_vals, new_value=update_data)
    return await db.salaries.find_one({"id": sid}, {"_id": 0})
