from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import OtherExpenseCreate, OtherExpenseUpdate
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


@router.get("/other-expenses")
async def list_other_expenses(user=Depends(get_user), category: str = "", date_from: str = "", date_to: str = "", sort_by: str = "expense_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if category:
        query["category"] = category
    if date_from:
        query.setdefault("expense_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("expense_date", {})["$lte"] = date_to
    return await db.other_expenses.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)


@router.post("/other-expenses")
async def create_other_expense(data: OtherExpenseCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by_id"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["approval_status"] = compute_approval_status(user, doc.get("amount", 0))
    await db.other_expenses.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Expense", doc["id"], f'{user["name"]} created expense ${doc.get("amount", 0)} ({doc.get("title", "")})', new_value={"title": doc.get("title"), "amount": doc.get("amount"), "category": doc.get("category")})
    return doc


@router.delete("/other-expenses/{eid}")
async def delete_other_expense(eid: str, user=Depends(get_user)):
    old = await db.other_expenses.find_one({"id": eid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.other_expenses.delete_one({"id": eid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Expense", eid, f'{user["name"]} deleted expense ${old.get("amount", 0)} ({old.get("title", "")})', old_value={"title": old.get("title"), "amount": old.get("amount"), "category": old.get("category")})
    return {"status": "deleted"}


@router.put("/other-expenses/{eid}")
async def update_other_expense(eid: str, data: OtherExpenseUpdate, user=Depends(get_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    old = await db.other_expenses.find_one({"id": eid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    old_vals = {k: old.get(k) for k in update_data}
    await db.other_expenses.update_one({"id": eid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Expense", eid, f'{user["name"]} updated expense ({old.get("title", "")})', old_value=old_vals, new_value=update_data)
    return await db.other_expenses.find_one({"id": eid}, {"_id": 0})
