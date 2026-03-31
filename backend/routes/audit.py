from fastapi import APIRouter, Depends
from core.database import db
from core.auth import get_user, require_manager

router = APIRouter()


@router.get("/audit-logs")
async def list_audit_logs(
    user=Depends(get_user),
    page: int = 1,
    page_size: int = 25,
    action_type: str = "",
    entity_type: str = "",
    user_id: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
):
    """List audit logs with filtering and pagination. Manager only."""
    require_manager(user)
    rid = user["restaurant_id"]
    query = {"restaurant_id": rid}
    if action_type:
        query["action_type"] = action_type
    if entity_type:
        query["entity_type"] = entity_type
    if user_id:
        query["user_id"] = user_id
    if search:
        query["description"] = {"$regex": search, "$options": "i"}
    if date_from:
        query.setdefault("timestamp", {})["$gte"] = date_from
    if date_to:
        query.setdefault("timestamp", {})["$lte"] = date_to + "T23:59:59"

    total = await db.audit_logs.count_documents(query)
    skip = (max(page, 1) - 1) * page_size
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(page_size).to_list(page_size)

    user_ids = await db.audit_logs.distinct("user_id", {"restaurant_id": rid})
    users_list = []
    for uid in user_ids:
        u = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "name": 1})
        if u:
            users_list.append({"id": u["id"], "name": u["name"]})

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "users": users_list,
    }
