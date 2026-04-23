from fastapi import APIRouter, HTTPException, Depends
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel

from core.database import db
from core.auth import get_user
from core.models import CanonicalItemCreate, ItemAliasCreate
from services.audit import audit_log

router = APIRouter()


@router.get("/items")
async def list_items(
    user=Depends(get_user),
    search: str = "",
    storage_category: str = "",
    status: str = "",   # "" | "suggested" | "approved" | "archived"
):
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if storage_category and storage_category in ("dry", "chilled", "frozen", "uncategorized"):
        query["storage_category"] = storage_category
    if status == "suggested":
        query["is_suggested"] = True
        query["is_archived"] = {"$ne": True}
    elif status == "approved":
        query["is_suggested"] = {"$ne": True}
        query["is_archived"] = {"$ne": True}
    elif status == "archived":
        query["is_archived"] = True
    else:
        # default list: exclude archived items (keeps history intact but hides noise)
        query["is_archived"] = {"$ne": True}
    items = await db.canonical_items.find(query, {"_id": 0}).to_list(1000)
    for item in items:
        item["aliases"] = await db.item_aliases.find(
            {"canonical_item_id": item["id"], "restaurant_id": user["restaurant_id"], "is_archived": {"$ne": True}},
            {"_id": 0},
        ).to_list(100)
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


@router.patch("/items/{iid}/storage-category")
async def update_storage_category(iid: str, body: dict, user=Depends(get_user)):
    """
    Set storage_category on an item. When called from the UI, this is a manual
    override — category_source is set to 'manual', which protects the value
    from being overwritten by future auto-extraction.
    """
    new_cat = (body.get("storage_category") or "").strip().lower()
    if new_cat not in ("dry", "chilled", "frozen", "uncategorized", ""):
        raise HTTPException(400, f"Invalid storage_category: '{new_cat}'. Must be dry, chilled, frozen, or uncategorized.")

    old = await db.canonical_items.find_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not old:
        raise HTTPException(404, "Item not found")

    old_cat = old.get("storage_category", "")
    updates = {
        "storage_category": new_cat,
        "category_source": "manual" if new_cat else "auto",
        "storage_category_updated_by": user["id"],
        "storage_category_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.canonical_items.update_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]},
        {"$set": updates},
    )
    await audit_log(
        user, "UPDATE", "Item", iid,
        f'{user["name"]} set storage category to "{new_cat}" (manual)',
        old_value={"storage_category": old_cat, "category_source": old.get("category_source", "auto")},
        new_value={"storage_category": new_cat, "category_source": "manual"},
    )
    updated = await db.canonical_items.find_one({"id": iid}, {"_id": 0})
    return updated




@router.delete("/items/{iid}")
async def delete_item(iid: str, user=Depends(get_user)):
    old = await db.canonical_items.find_one({"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    await db.canonical_items.delete_one({"id": iid, "restaurant_id": user["restaurant_id"]})
    await db.item_aliases.delete_many({"canonical_item_id": iid})
    await audit_log(user, "DELETE", "Item", iid, f'{user["name"]} deleted item {old.get("name", "") if old else ""}', old_value={"name": old.get("name")} if old else None)
    return {"status": "deleted"}


# ─── Suggested catalog governance (review layer) ────────────────────
@router.post("/items/{iid}/promote")
async def promote_suggested_item(iid: str, user=Depends(get_user)):
    """
    Promote a suggested canonical item to an approved catalog entry.
    Preserves aliases and correction_memory history — only clears the
    suggestion markers so the item is treated as fully approved.
    """
    existing = await db.canonical_items.find_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(404, "item_not_found")
    if not existing.get("is_suggested"):
        raise HTTPException(400, "not_a_suggested_item")

    now = datetime.now(timezone.utc).isoformat()
    await db.canonical_items.update_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]},
        {"$set": {
            "is_suggested": False,
            "promoted_at": now,
            "promoted_by_user_id": user.get("id"),
            "promoted_by_name": user.get("name", ""),
        }},
    )
    await audit_log(
        user, "PROMOTE", "Item", iid,
        f'{user["name"]} promoted suggested item "{existing.get("name", "")}"',
        new_value={"name": existing.get("name"), "is_suggested": False},
    )
    updated = await db.canonical_items.find_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    return {"status": "promoted", "item": updated}


@router.post("/items/{iid}/dismiss")
async def dismiss_suggested_item(iid: str, user=Depends(get_user)):
    """
    Dismiss a suggested item safely.
    NON-DESTRUCTIVE: soft-archive via is_archived=true (hidden from default listing).
    Aliases are also archived rather than deleted so past correction_memory records
    stay readable and re-linkable.
    """
    existing = await db.canonical_items.find_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(404, "item_not_found")
    if not existing.get("is_suggested"):
        raise HTTPException(400, "not_a_suggested_item")

    now = datetime.now(timezone.utc).isoformat()
    await db.canonical_items.update_one(
        {"id": iid, "restaurant_id": user["restaurant_id"]},
        {"$set": {
            "is_archived": True,
            "archived_at": now,
            "archived_by_user_id": user.get("id"),
            "archived_by_name": user.get("name", ""),
        }},
    )
    await db.item_aliases.update_many(
        {"canonical_item_id": iid, "restaurant_id": user["restaurant_id"]},
        {"$set": {"is_archived": True, "archived_at": now}},
    )
    await audit_log(
        user, "DISMISS", "Item", iid,
        f'{user["name"]} dismissed suggested item "{existing.get("name", "")}"',
        old_value={"name": existing.get("name"), "is_suggested": True},
    )
    return {"status": "dismissed", "id": iid}


class MergeSuggestedBody(BaseModel):
    target_item_id: str


@router.post("/items/{iid}/merge")
async def merge_suggested_item(
    iid: str,
    body: MergeSuggestedBody,
    user=Depends(get_user),
):
    """
    Merge a suggested canonical item into an existing approved canonical item.

    Non-destructive:
      - Transfer all of the suggested item's aliases to the target (via update_many
        of canonical_item_id). If a (target, alias) pair already exists, increment
        usage_count on the existing alias and drop the duplicate alias row.
      - Add the suggested item's own `name` as an alias on the target (if not
        already present).
      - Mark suggested item as `is_merged=True`, `is_archived=True`, record
        `merged_into_item_id`, `merged_at`, `merged_by_user_id/name`.
      - correction_memory is NOT touched — rows remain readable; future writes
        will find the existing target via catalog_linkage contains/exact match.
    """
    rid = user["restaurant_id"]

    suggested = await db.canonical_items.find_one(
        {"id": iid, "restaurant_id": rid}, {"_id": 0}
    )
    if not suggested:
        raise HTTPException(404, "item_not_found")
    if not suggested.get("is_suggested"):
        raise HTTPException(400, "not_a_suggested_item")

    target = await db.canonical_items.find_one(
        {"id": body.target_item_id, "restaurant_id": rid}, {"_id": 0}
    )
    if not target:
        raise HTTPException(404, "target_item_not_found")
    if target.get("is_archived"):
        raise HTTPException(400, "target_is_archived")
    if target.get("is_suggested"):
        raise HTTPException(400, "target_must_be_approved")
    if target["id"] == iid:
        raise HTTPException(400, "cannot_merge_into_self")

    now = datetime.now(timezone.utc).isoformat()

    # 1) Transfer aliases from suggested → target, de-duping.
    suggested_aliases = await db.item_aliases.find(
        {"canonical_item_id": iid, "restaurant_id": rid},
        {"_id": 0},
    ).to_list(500)
    transferred, deduped = 0, 0
    for a in suggested_aliases:
        alias_text = (a.get("alias") or "").strip()
        if not alias_text:
            continue
        existing_target_alias = await db.item_aliases.find_one(
            {
                "canonical_item_id": target["id"],
                "restaurant_id": rid,
                "alias": alias_text,
            },
            {"_id": 0},
        )
        if existing_target_alias:
            await db.item_aliases.update_one(
                {"id": existing_target_alias["id"]},
                {"$set": {"last_used_at": now},
                 "$inc": {"usage_count": int(a.get("usage_count") or 1)}},
            )
            await db.item_aliases.delete_one({"id": a["id"]})
            deduped += 1
        else:
            await db.item_aliases.update_one(
                {"id": a["id"]},
                {"$set": {"canonical_item_id": target["id"], "last_used_at": now}},
            )
            transferred += 1

    # 2) Add the suggested item's own `name` as an alias on the target (if new).
    suggested_name = (suggested.get("name") or "").strip()
    if suggested_name:
        exists = await db.item_aliases.find_one(
            {
                "canonical_item_id": target["id"],
                "restaurant_id": rid,
                "alias": suggested_name,
            },
            {"_id": 0},
        )
        if not exists:
            await db.item_aliases.insert_one({
                "id": str(uuid.uuid4()),
                "restaurant_id": rid,
                "canonical_item_id": target["id"],
                "alias": suggested_name,
                "source": "merge",
                "created_by_user_id": user.get("id"),
                "created_at": now,
                "last_used_at": now,
                "usage_count": 1,
            })

    # 3) Mark suggested as merged + archived (non-destructive).
    await db.canonical_items.update_one(
        {"id": iid, "restaurant_id": rid},
        {"$set": {
            "is_merged": True,
            "is_archived": True,
            "merged_into_item_id": target["id"],
            "merged_at": now,
            "merged_by_user_id": user.get("id"),
            "merged_by_name": user.get("name", ""),
        }},
    )

    await audit_log(
        user, "MERGE", "Item", iid,
        f'{user["name"]} merged suggested "{suggested.get("name", "")}" into "{target.get("name", "")}"',
        new_value={"merged_into_item_id": target["id"],
                   "target_name": target.get("name"),
                   "aliases_transferred": transferred,
                   "aliases_deduped": deduped},
    )

    # Return refreshed target so the UI can update inline.
    refreshed_target = await db.canonical_items.find_one(
        {"id": target["id"], "restaurant_id": rid}, {"_id": 0}
    )
    refreshed_target["aliases"] = await db.item_aliases.find(
        {"canonical_item_id": target["id"], "restaurant_id": rid, "is_archived": {"$ne": True}},
        {"_id": 0},
    ).to_list(200)

    return {
        "status": "merged",
        "suggested_id": iid,
        "target": refreshed_target,
        "aliases_transferred": transferred,
        "aliases_deduped": deduped,
    }


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
