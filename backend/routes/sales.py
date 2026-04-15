from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from core.models import SalesCreate, SalesUpdate
from core.permissions import require_permission, apply_scope_filter, apply_soft_delete_filter
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


@router.get("/sales")
async def list_sales(
    user=Depends(require_permission("view_sales")),
    search: str = "", date_from: str = "", date_to: str = "",
    sort_by: str = "report_date", sort_order: str = "desc",
):
    query = {"restaurant_id": user["restaurant_id"]}
    apply_scope_filter(query, user, "created_by_user_id")
    apply_soft_delete_filter(query)
    if date_from:
        query.setdefault("report_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("report_date", {})["$lte"] = date_to
    direction = -1 if sort_order == "desc" else 1
    if sort_by == "report_date":
        pipeline = [
            {"$match": query},
            {"$addFields": {"_sort_date": {"$cond": [{"$gt": ["$report_date", ""]}, "$report_date", "$created_at"]}}},
            {"$sort": {"_sort_date": direction}},
            {"$project": {"_id": 0, "_sort_date": 0}},
        ]
        return await db.sales.aggregate(pipeline).to_list(1000)
    return await db.sales.find(query, {"_id": 0}).sort(sort_by, direction).to_list(1000)


@router.get("/sales/{sid}")
async def get_sale(sid: str, user=Depends(require_permission("view_sales"))):
    query = {"id": sid, "restaurant_id": user["restaurant_id"]}
    apply_scope_filter(query, user, "created_by_user_id")
    apply_soft_delete_filter(query)
    s = await db.sales.find_one(query, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    return s


@router.post("/sales")
async def create_sale(data: SalesCreate, user=Depends(require_permission("can_add_sales"))):
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
    doc["created_by_user_id"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["source_type"] = "manual"
    doc["approval_status"] = compute_approval_status(user, doc.get("total_sales", 0))
    await db.sales.insert_one(doc)
    doc.pop("_id", None)
    await audit_log(user, "CREATE", "Sale", doc["id"], f'{user["name"]} created sale ${doc.get("total_sales", 0)} ({doc.get("report_date", "")})', new_value={"total_sales": doc.get("total_sales"), "report_date": doc.get("report_date")})
    return doc


@router.put("/sales/{sid}")
async def update_sale(sid: str, data: SalesUpdate, user=Depends(require_permission("can_edit_sales"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    query = {"id": sid, "restaurant_id": user["restaurant_id"]}
    apply_soft_delete_filter(query)
    old = await db.sales.find_one(query, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    # Cashier scope: can only edit own records
    from core.permissions import _user_scope
    if _user_scope(user) == "own" and old.get("created_by_user_id") != user["id"]:
        raise HTTPException(403, "You can only edit your own records")
    old_vals = {k: old.get(k) for k in update_data}
    await db.sales.update_one({"id": sid}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Sale", sid, f'{user["name"]} updated sale ({old.get("report_date", "")})', old_value=old_vals, new_value=update_data)
    return await db.sales.find_one({"id": sid}, {"_id": 0})


@router.delete("/sales/{sid}")
async def delete_sale(sid: str, user=Depends(require_permission("can_delete_sales"))):
    """Soft-delete: marks record as deleted, preserving audit trail."""
    query = {"id": sid, "restaurant_id": user["restaurant_id"]}
    apply_soft_delete_filter(query)
    old = await db.sales.find_one(query, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.sales.update_one({"id": sid}, {"$set": {
        "status": "deleted",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by_user_id": user["id"],
        "deleted_by_name": user.get("name", ""),
    }})
    await audit_log(user, "DELETE", "Sale", sid, f'{user["name"]} deleted sale ${old.get("total_sales", 0)} ({old.get("report_date", "")})', old_value={"total_sales": old.get("total_sales"), "report_date": old.get("report_date")})
    return {"status": "deleted"}
