from fastapi import APIRouter, HTTPException, Depends
import uuid, re
from datetime import datetime, timezone

from core.database import db, logger
from core.auth import get_user
from core.models import PurchaseCreate, PurchaseUpdate
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


@router.get("/purchases")
async def list_purchases(user=Depends(get_user), search: str = "", supplier: str = "", date_from: str = "", date_to: str = "", sort_by: str = "invoice_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["$or"] = [{"supplier_name": {"$regex": search, "$options": "i"}}, {"invoice_number": {"$regex": search, "$options": "i"}}]
    if supplier:
        query["supplier_name"] = {"$regex": supplier, "$options": "i"}
    if date_from:
        query.setdefault("invoice_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("invoice_date", {})["$lte"] = date_to
    direction = -1 if sort_order == "desc" else 1
    # Sort by date field with fallback to created_at when date is missing/empty
    if sort_by == "invoice_date":
        pipeline = [
            {"$match": query},
            {"$addFields": {"_sort_date": {"$cond": [{"$gt": ["$invoice_date", ""]}, "$invoice_date", "$created_at"]}}},
            {"$sort": {"_sort_date": direction}},
            {"$project": {"_id": 0, "_sort_date": 0}},
        ]
        return await db.purchases.aggregate(pipeline).to_list(1000)
    return await db.purchases.find(query, {"_id": 0}).sort(sort_by, direction).to_list(1000)


@router.get("/purchases/{pid}")
async def get_purchase(pid: str, user=Depends(get_user)):
    p = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    return p


@router.post("/purchases")
async def create_purchase(data: PurchaseCreate, user=Depends(get_user)):
    from preprocessing import enrich_item_with_pack_size, validate_and_score_item, validate_purchase_items, compute_review_status, sanitize_extracted_item
    from services.normalization import normalize_item
    from services.correction_memory import apply_corrections
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by_id"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["approval_status"] = compute_approval_status(user, doc.get("total", 0))
    rid = user["restaurant_id"]
    supplier_id = doc.get("supplier_id") or ""
    if not supplier_id:
        supplier_name = doc.get("supplier_name", "").strip()
        if supplier_name:
            sup = await db.suppliers.find_one(
                {"restaurant_id": rid, "name": {"$regex": f"^{re.escape(supplier_name)}$", "$options": "i"}},
                {"_id": 0, "id": 1},
            )
            if sup:
                supplier_id = sup["id"]
    for item in doc.get("items", []):
        sanitize_extracted_item(item)  # Sanitize first to handle None, negatives, type coercion
        enrich_item_with_pack_size(item)
        normalize_item(item)
        validate_and_score_item(item)
    if supplier_id:
        await apply_corrections(doc.get("items", []), rid, supplier_id)
    validate_purchase_items(doc.get("items", []))
    doc["review_status"] = compute_review_status(doc.get("items", []))
    await db.purchases.insert_one(doc)
    doc.pop("_id", None)

    rid = user["restaurant_id"]
    supplier_name = doc.get("supplier_name", "").strip()
    if supplier_name:
        existing_vendor = await db.suppliers.find_one({
            "restaurant_id": rid,
            "name": {"$regex": f"^{re.escape(supplier_name)}$", "$options": "i"}
        })
        if not existing_vendor:
            vendor_doc = {
                "id": str(uuid.uuid4()),
                "restaurant_id": rid,
                "name": supplier_name,
                "contact_name": "", "phone": "", "email": "", "address": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.suppliers.insert_one(vendor_doc)
            vendor_doc.pop("_id", None)
            logger.info(f"Auto-created vendor: {supplier_name}")

    for item in doc.get("items", []):
        raw_name = item.get("raw_name", "").strip()
        if not raw_name:
            continue
        existing_item = await db.canonical_items.find_one({
            "restaurant_id": rid,
            "name": {"$regex": f"^{re.escape(raw_name)}$", "$options": "i"}
        })
        if not existing_item:
            item_doc = {
                "id": str(uuid.uuid4()),
                "restaurant_id": rid,
                "name": raw_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.canonical_items.insert_one(item_doc)
            item_doc.pop("_id", None)
            logger.info(f"Auto-created item: {raw_name}")

    existing = await db.purchases.find(
        {"restaurant_id": rid, "id": {"$ne": doc["id"]}},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}
    ).to_list(10000)

    canon_items = await db.canonical_items.find({"restaurant_id": rid}, {"_id": 0}).to_list(1000)
    alias_list = await db.item_aliases.find({"restaurant_id": rid}, {"_id": 0}).to_list(5000)
    name_to_group = {}
    for c in canon_items:
        group_key = c["name"].lower()
        name_to_group[group_key] = group_key
    for a in alias_list:
        for c in canon_items:
            if c["id"] == a["canonical_item_id"]:
                name_to_group[a["alias_name"].lower()] = c["name"].lower()
                break

    for item in doc.get("items", []):
        raw = item.get("raw_name", "").strip()
        new_price = float(item.get("unit_price") or 0)
        if not raw or new_price <= 0:
            continue

        group_key = name_to_group.get(raw.lower(), raw.lower())
        match_names = {group_key}
        for k, v in name_to_group.items():
            if v == group_key:
                match_names.add(k)
        match_names.add(raw.lower())

        prev_record = None
        for p in sorted(existing, key=lambda x: x.get("invoice_date", ""), reverse=True):
            for it in p.get("items", []):
                if it.get("raw_name", "").lower() in match_names and float(it.get("unit_price", 0)) > 0:
                    prev_record = {"price": float(it["unit_price"]), "vendor": p.get("supplier_name", "Unknown"), "date": p.get("invoice_date", "")}
                    break
            if prev_record:
                break

        if prev_record and new_price > prev_record["price"]:
            pct = round(((new_price - prev_record["price"]) / prev_record["price"]) * 100, 1)
            alert_doc = {
                "id": str(uuid.uuid4()),
                "restaurant_id": rid,
                "type": "price_increase",
                "severity": "high" if pct > 15 else "medium",
                "item_name": raw,
                "previous_price": round(prev_record["price"], 2),
                "new_price": round(new_price, 2),
                "change_pct": pct,
                "vendor": doc.get("supplier_name", "Unknown"),
                "previous_vendor": prev_record["vendor"],
                "invoice_date": doc.get("invoice_date", ""),
                "message": f"Price increase detected for {raw}.\nPrevious price: ${prev_record['price']:.2f}\nNew price: ${new_price:.2f}",
                "is_read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.alerts.insert_one(alert_doc)

    await audit_log(user, "CREATE", "Expense", doc["id"], f'{user["name"]} created expense ${doc.get("total", 0)} ({doc.get("supplier_name", "")})', new_value={"supplier": doc.get("supplier_name"), "total": doc.get("total"), "invoice_date": doc.get("invoice_date"), "items_count": len(doc.get("items", []))})
    return doc


@router.put("/purchases/{pid}")
async def update_purchase(pid: str, data: PurchaseUpdate, user=Depends(get_user)):
    from preprocessing import enrich_item_with_pack_size, validate_and_score_item, validate_purchase_items, compute_review_status, sanitize_extracted_item
    from services.normalization import normalize_item
    from services.correction_memory import save_correction
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    old = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    rid = user["restaurant_id"]
    supplier_id = old.get("supplier_id") or ""
    if not supplier_id:
        supplier_name = old.get("supplier_name", "").strip()
        if supplier_name:
            sup = await db.suppliers.find_one(
                {"restaurant_id": rid, "name": {"$regex": f"^{re.escape(supplier_name)}$", "$options": "i"}},
                {"_id": 0, "id": 1},
            )
            if sup:
                supplier_id = sup["id"]
    if "items" in update_data:
        old_items = old.get("items", [])
        old_items_by_idx = {i: it for i, it in enumerate(old_items)}
        for idx, item in enumerate(update_data["items"]):
            sanitize_extracted_item(item)  # Sanitize first to handle None, negatives, type coercion
            enrich_item_with_pack_size(item)
            normalize_item(item)
            validate_and_score_item(item)
            # Detect edits and save corrections
            if supplier_id and idx < len(old_items):
                old_item = old_items_by_idx.get(idx, {})
                old_raw = old_item.get("raw_name", "").strip()
                new_raw = item.get("raw_name", "").strip()
                old_norm = old_item.get("norm", {})
                old_key = old_norm.get("strict_match_key", "")
                new_norm = item.get("norm", {})
                new_key = new_norm.get("strict_match_key", "")
                if old_raw and new_raw and old_raw != new_raw and old_key:
                    await save_correction(
                        user_id=user["id"],
                        restaurant_id=rid,
                        supplier_id=supplier_id,
                        original_raw_name=old_raw,
                        normalized_key=old_key,
                        corrected_name=new_raw,
                        corrected_specs=new_norm.get("specs"),
                    )
        validate_purchase_items(update_data["items"])
        update_data["review_status"] = compute_review_status(update_data["items"])
    old_vals = {k: old.get(k) for k in update_data}
    await db.purchases.update_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Expense", pid, f'{user["name"]} updated expense ({old.get("supplier_name", "")})', old_value=old_vals, new_value=update_data)
    return await db.purchases.find_one({"id": pid}, {"_id": 0})


@router.delete("/purchases/{pid}")
async def delete_purchase(pid: str, user=Depends(get_user)):
    old = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.purchases.delete_one({"id": pid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Expense", pid, f'{user["name"]} deleted expense ${old.get("total", 0)} ({old.get("supplier_name", "")})', old_value={"supplier": old.get("supplier_name"), "total": old.get("total"), "invoice_date": old.get("invoice_date")})
    return {"status": "deleted"}
