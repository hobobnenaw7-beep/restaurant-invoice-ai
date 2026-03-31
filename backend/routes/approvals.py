from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Dict

from core.database import db
from core.auth import get_user, require_manager
from core.models import ApprovalAction
from services.audit import audit_log

router = APIRouter()


@router.get("/approvals")
async def list_pending_records(
    user=Depends(get_user),
    record_type: str = "",
    status: str = "pending",
    created_by: str = "",
    date_from: str = "",
    date_to: str = "",
):
    """List records pending approval (Manager only)."""
    require_manager(user)
    rid = user["restaurant_id"]
    results = []

    collections = {
        "sale": ("sales", "total_sales", "report_date"),
        "purchase": ("purchases", "total", "invoice_date"),
        "salary": ("salaries", "amount", "payment_date"),
        "other_expense": ("other_expenses", "amount", "expense_date"),
    }

    types_to_check = [record_type] if record_type and record_type in collections else list(collections.keys())

    for rtype in types_to_check:
        coll_name, amt_field, date_field = collections[rtype]
        coll = db[coll_name]
        query = {"restaurant_id": rid}
        if status:
            query["approval_status"] = status
        if created_by:
            query["created_by_id"] = created_by
        if date_from:
            query.setdefault(date_field, {})["$gte"] = date_from
        if date_to:
            query.setdefault(date_field, {})["$lte"] = date_to

        docs = await coll.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
        for d in docs:
            results.append({
                "record_type": rtype,
                "record_id": d.get("id", ""),
                "date": d.get(date_field, ""),
                "amount": d.get(amt_field, 0),
                "created_by_id": d.get("created_by_id", ""),
                "created_by_name": d.get("created_by_name", "Unknown"),
                "approval_status": d.get("approval_status", "approved"),
                "rejection_reason": d.get("rejection_reason", ""),
                "notes": d.get("notes", d.get("transaction_notes", "")),
                "created_at": d.get("created_at", ""),
                "supplier_name": d.get("supplier_name", ""),
                "employee_name": d.get("employee_name", ""),
                "title": d.get("title", ""),
                "category": d.get("category", ""),
                "invoice_number": d.get("invoice_number", ""),
            })

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


@router.get("/approvals/counts")
async def approval_counts(user=Depends(get_user)):
    """Get count of pending records per type."""
    require_manager(user)
    rid = user["restaurant_id"]
    counts = {}
    for rtype, (coll_name, _, _) in {"sale": ("sales", "", ""), "purchase": ("purchases", "", ""), "salary": ("salaries", "", ""), "other_expense": ("other_expenses", "", "")}.items():
        counts[rtype] = await db[coll_name].count_documents({"restaurant_id": rid, "approval_status": "pending"})
    counts["total"] = sum(counts.values())
    return counts


@router.put("/approvals/{record_type}/{record_id}")
async def process_approval(record_type: str, record_id: str, data: ApprovalAction, user=Depends(get_user)):
    """Approve or reject a record."""
    require_manager(user)
    rid = user["restaurant_id"]

    coll_map = {"sale": "sales", "purchase": "purchases", "salary": "salaries", "other_expense": "other_expenses"}
    coll_name = coll_map.get(record_type)
    if not coll_name:
        raise HTTPException(400, "Invalid record_type")

    if data.action not in ("approve", "reject"):
        raise HTTPException(400, "Action must be 'approve' or 'reject'")

    coll = db[coll_name]
    rec = await coll.find_one({"id": record_id, "restaurant_id": rid}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Record not found")

    updates = {
        "approval_status": "approved" if data.action == "approve" else "rejected",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("name", ""),
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.action == "reject" and data.reason:
        updates["rejection_reason"] = data.reason

    await coll.update_one({"id": record_id}, {"$set": updates})
    updated = await coll.find_one({"id": record_id}, {"_id": 0})
    action = "APPROVE" if data.action == "approve" else "REJECT"
    entity_label = record_type.replace("_", " ").title()
    amt = rec.get("total", rec.get("amount", rec.get("total_sales", "")))
    desc = f'{user["name"]} {data.action}d {entity_label} ${amt}' if amt else f'{user["name"]} {data.action}d {entity_label}'
    await audit_log(user, action, entity_label, record_id, desc, old_value={"approval_status": rec.get("approval_status", "pending")}, new_value={"approval_status": updates["approval_status"]})
    return updated
