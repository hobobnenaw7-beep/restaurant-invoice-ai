from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Response
import uuid
import hashlib
from datetime import datetime, timezone

from core.database import db, UPLOADS_DIR
from core.auth import get_user
from core.permissions import require_permission, apply_scope_filter, apply_soft_delete_filter

router = APIRouter()


@router.post("/records/upload")
async def upload_record(
    file: UploadFile = File(...),
    folder: str = Form(...),
    transaction_type: str = Form(""),
    transaction_id: str = Form(""),
    transaction_date: str = Form(""),
    transaction_amount: float = Form(0),
    transaction_notes: str = Form(""),
    vendor_name: str = Form(""),
    user=Depends(require_permission("can_upload_files")),
):
    """Upload a file to the Records Library."""
    rid = user["restaurant_id"]
    if folder not in ("sales", "expenses"):
        raise HTTPException(400, "folder must be 'sales' or 'expenses'")

    content = await file.read()
    file_size = len(content)
    original_name = file.filename or "untitled"
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    mime = file.content_type or "application/octet-stream"
    file_hash = hashlib.sha256(content).hexdigest()

    dup = await db.records_library.find_one({
        "restaurant_id": rid, "folder": folder,
        "$or": [
            {"file_hash": file_hash},
            {"file_name": original_name, "file_size": file_size},
        ]
    }, {"_id": 0, "id": 1, "file_name": 1, "upload_date": 1})
    if dup:
        raise HTTPException(
            409,
            f"Duplicate file detected: \"{dup['file_name']}\" (uploaded {dup.get('upload_date', 'previously')})"
        )

    record_id = str(uuid.uuid4())
    stored_name = f"{record_id}.{ext}" if ext else record_id

    file_path = UPLOADS_DIR / stored_name
    with open(file_path, "wb") as f:
        f.write(content)

    doc = {
        "id": record_id,
        "restaurant_id": rid,
        "folder": folder,
        "file_name": original_name,
        "file_type": mime,
        "file_extension": ext,
        "file_size": file_size,
        "file_hash": file_hash,
        "stored_name": stored_name,
        "upload_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "transaction_type": transaction_type,
        "transaction_id": transaction_id,
        "transaction_date": transaction_date,
        "transaction_amount": transaction_amount,
        "transaction_notes": transaction_notes,
        "vendor_name": vendor_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_user_id": user["id"],
        "created_by_name": user.get("name", ""),
        "source_type": "upload",
    }
    await db.records_library.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/records")
async def list_records(
    user=Depends(require_permission("can_view_records")),
    folder: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    file_type: str = "",
    expense_category: str = "",
    sort_by: str = "upload_date",
    sort_order: str = "desc",
):
    """List records in the library with scope enforcement."""
    query = {"restaurant_id": user["restaurant_id"]}
    apply_scope_filter(query, user, "created_by_user_id")
    if folder:
        query["folder"] = folder
    if search:
        query["file_name"] = {"$regex": search, "$options": "i"}
    if date_from:
        query.setdefault("upload_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("upload_date", {})["$lte"] = date_to
    if file_type and file_type != "all":
        if file_type == "image":
            query["file_type"] = {"$regex": "^image/", "$options": "i"}
        elif file_type == "pdf":
            query["file_extension"] = "pdf"
        elif file_type == "excel":
            query["file_extension"] = {"$in": ["xlsx", "xls", "csv"]}
    if expense_category and expense_category != "all":
        query["transaction_type"] = expense_category

    sort_field_map = {"upload_date": "upload_date", "amount": "transaction_amount", "name": "file_name"}
    sort_f = sort_field_map.get(sort_by, "upload_date")
    sort_d = -1 if sort_order == "desc" else 1

    records = await db.records_library.find(query, {"_id": 0}).sort(sort_f, sort_d).to_list(5000)
    return records


@router.get("/records/{record_id}")
async def get_record(record_id: str, user=Depends(require_permission("can_view_records"))):
    query = {"id": record_id, "restaurant_id": user["restaurant_id"]}
    apply_scope_filter(query, user, "created_by_user_id")
    rec = await db.records_library.find_one(query, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Record not found")
    return rec


@router.get("/records/{record_id}/file")
async def serve_record_file(record_id: str, user=Depends(require_permission("can_view_records"))):
    """Serve the actual file for preview or download."""
    query = {"id": record_id, "restaurant_id": user["restaurant_id"]}
    apply_scope_filter(query, user, "created_by_user_id")
    rec = await db.records_library.find_one(query, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Record not found")
    file_path = UPLOADS_DIR / rec["stored_name"]
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    content = file_path.read_bytes()
    return Response(
        content=content,
        media_type=rec.get("file_type", "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{rec["file_name"]}"'}
    )


@router.delete("/records/{record_id}")
async def delete_record(record_id: str, user=Depends(require_permission("can_manage_users"))):
    """Soft-delete a record (manager only)."""
    query = {"id": record_id, "restaurant_id": user["restaurant_id"]}
    rec = await db.records_library.find_one(query, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Record not found")
    await db.records_library.update_one({"id": record_id}, {"$set": {
        "status": "deleted",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by_user_id": user["id"],
        "deleted_by_name": user.get("name", ""),
    }})
    return {"status": "deleted"}
