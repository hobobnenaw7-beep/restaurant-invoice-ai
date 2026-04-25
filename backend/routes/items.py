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
    # Only update fields explicitly provided by the caller. Pydantic v2:
    # exclude_unset captures that. Plus drop None for fields the client
    # sends as null to avoid wiping persisted state unintentionally.
    update_data = data.model_dump(exclude_unset=True)
    update_data = {k: v for k, v in update_data.items() if v is not None}
    # Normalise variants (key → lowercase, dedupe) when provided.
    if "variants" in update_data:
        seen = set()
        cleaned = []
        for v in (update_data.get("variants") or []):
            if isinstance(v, dict):
                key = (v.get("key") or "").strip().lower()
                label = (v.get("label") or key).strip() or key
            else:
                key = (getattr(v, "key", "") or "").strip().lower()
                label = (getattr(v, "label", "") or key).strip() or key
            if key and key not in seen:
                seen.add(key)
                cleaned.append({"key": key, "label": label})
        update_data["variants"] = cleaned
    old_vals = {k: old.get(k) for k in update_data} if old else {}
    if update_data:
        await db.canonical_items.update_one(
            {"id": iid, "restaurant_id": user["restaurant_id"]},
            {"$set": update_data},
        )
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




@router.get("/items/{iid}/linkage-audit")
async def item_linkage_audit(iid: str, user=Depends(get_user)):
    """
    Returns how many existing invoices reference this canonical item.
    Used by the Items page to (a) prove a rename has propagated, and
    (b) safely block deletion when linked rows still exist.
    """
    rid = user["restaurant_id"]
    item = await db.canonical_items.find_one({"id": iid, "restaurant_id": rid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "item_not_found")
    # Run the read-time auto-resolver first so audit reflects the latest
    # link state (newly-resolvable rows get linked + persisted now).
    from routes.purchases import _enrich_purchases_with_canonical
    rows = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    await _enrich_purchases_with_canonical(rid, rows)

    linked_invoices: set[str] = set()
    vendors: set[str] = set()
    dates: list[str] = []
    samples: list[dict] = []
    total_rows = 0
    for p in rows:
        invoice_id = p.get("id")
        invoice_no = p.get("invoice_number")
        vendor = p.get("supplier_name")
        d = p.get("invoice_date")
        for it in (p.get("items") or []):
            if it.get("canonical_item_id") == iid:
                total_rows += 1
                if invoice_id:
                    linked_invoices.add(invoice_id)
                if vendor:
                    vendors.add(vendor)
                if d:
                    dates.append(d)
                if len(samples) < 5:
                    samples.append({
                        "invoice_id": invoice_id,
                        "invoice_number": invoice_no,
                        "vendor": vendor,
                        "date": d,
                        "raw_name": it.get("raw_name"),
                        "display_name": it.get("display_name"),
                        "canonical_name": it.get("canonical_name"),
                    })
    dates_sorted = sorted([d for d in dates if d])
    return {
        "canonical_item_id": iid,
        "canonical_name": item.get("name"),
        "is_archived": bool(item.get("is_archived")),
        "is_suggested": bool(item.get("is_suggested")),
        "total_linked_rows": total_rows,
        "total_linked_invoices": len(linked_invoices),
        "vendors": sorted(vendors),
        "date_range": {
            "first": dates_sorted[0] if dates_sorted else None,
            "last": dates_sorted[-1] if dates_sorted else None,
        },
        "samples": samples,
    }


@router.delete("/items/{iid}")
async def delete_item(iid: str, user=Depends(get_user)):
    rid = user["restaurant_id"]
    old = await db.canonical_items.find_one({"id": iid, "restaurant_id": rid}, {"_id": 0})
    if not old:
        raise HTTPException(404, "item_not_found")

    # Refuse delete when this canonical is linked to existing invoice rows.
    # We run the auto-resolver first so the count reflects current reality,
    # then count linked rows / invoices for the error payload.
    from routes.purchases import _enrich_purchases_with_canonical
    rows = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    await _enrich_purchases_with_canonical(rid, rows)
    linked_rows = 0
    linked_invoices: set[str] = set()
    for p in rows:
        for it in (p.get("items") or []):
            if it.get("canonical_item_id") == iid:
                linked_rows += 1
                if p.get("id"):
                    linked_invoices.add(p["id"])
    if linked_rows > 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ITEM_IN_USE",
                "linked_invoices": len(linked_invoices),
                "linked_rows": linked_rows,
                "canonical_name": old.get("name"),
                "actions": ["archive", "merge", "cancel"],
            },
        )

    await db.canonical_items.delete_one({"id": iid, "restaurant_id": rid})
    await db.item_aliases.delete_many({"canonical_item_id": iid})
    await audit_log(user, "DELETE", "Item", iid, f'{user["name"]} deleted item {old.get("name", "")}', old_value={"name": old.get("name")})
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


@router.post("/items/{iid}/archive")
async def archive_item(iid: str, user=Depends(get_user)):
    """
    Soft-archive an APPROVED canonical item. Used as the safe alternative
    when DELETE is blocked because invoice rows still reference it.
    Aliases are archived (not deleted) so past correction memory remains
    readable. Existing invoices keep their canonical link intact, so the
    display follows the catalog: rows continue to show the (archived)
    canonical name until the user merges them into another item.
    """
    rid = user["restaurant_id"]
    existing = await db.canonical_items.find_one({"id": iid, "restaurant_id": rid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "item_not_found")
    if existing.get("is_archived"):
        return {"status": "already_archived", "id": iid}
    now = datetime.now(timezone.utc).isoformat()
    await db.canonical_items.update_one(
        {"id": iid, "restaurant_id": rid},
        {"$set": {
            "is_archived": True,
            "archived_at": now,
            "archived_by_user_id": user.get("id"),
            "archived_by_name": user.get("name", ""),
        }},
    )
    await db.item_aliases.update_many(
        {"canonical_item_id": iid, "restaurant_id": rid},
        {"$set": {"is_archived": True, "archived_at": now}},
    )
    await audit_log(
        user, "ARCHIVE", "Item", iid,
        f'{user["name"]} archived item "{existing.get("name", "")}"',
        old_value={"name": existing.get("name"), "is_archived": False},
    )
    return {"status": "archived", "id": iid}




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
    # Allow merging suggested OR approved canonicals — merging an approved
    # canonical into another is the safe alternative when DELETE is blocked
    # by linked invoice rows. The merged-from item is archived (not deleted)
    # and existing invoice canonical_item_id pointers follow one merge hop
    # via the enrichment layer.
    if suggested.get("is_archived"):
        raise HTTPException(400, "source_is_archived")

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
    """Price history for a canonical item.

    Milestone 20 — identity-based join: any purchase-line whose
    `canonical_item_id` points at this item (directly or via one merge
    hop) contributes. Falls back to name + alias matching for legacy
    rows that have not yet been linked.
    """
    from services.identity_resolver import build_canonical_index, GROUP_PREFIX_CANON
    rid = user["restaurant_id"]
    item = await db.canonical_items.find_one({"id": item_id, "restaurant_id": rid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")

    idx = await build_canonical_index(rid)
    # Target group_key(s) for this canonical (variant lines roll up by
    # prefix match on `canon::<id>`).
    target_prefix = f"{GROUP_PREFIX_CANON}{item_id}"

    # Back-compat name/alias fallback set — covers legacy rows without
    # canonical_item_id that resolve via the canonical index anyway.
    names_fallback = {item["name"].lower()}
    aliases = await db.item_aliases.find(
        {"canonical_item_id": item_id, "restaurant_id": rid, "is_archived": {"$ne": True}},
        {"_id": 0},
    ).to_list(200)
    for a in aliases:
        nm = a.get("alias_name") or a.get("alias") or ""
        if nm:
            names_fallback.add(nm.lower())

    purchases = await db.purchases.find(
        {"restaurant_id": rid},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1},
    ).to_list(10000)

    records = []
    for p in purchases:
        vendor = p.get("supplier_name", "Unknown")
        date = p.get("invoice_date", "")
        for it in p.get("items", []):
            gkey, _, _ = idx.resolve(it)
            matched = False
            if gkey == target_prefix or gkey.startswith(target_prefix + "::"):
                matched = True
            else:
                # Last-chance backwards compat for rows not covered by idx
                raw = (it.get("raw_name") or "").lower()
                if raw and raw in names_fallback:
                    matched = True
            if not matched:
                continue
            records.append({
                "vendor": vendor, "date": date,
                "unit_price": round(float(it.get("unit_price", 0) or 0), 2),
                "quantity": float(it.get("quantity", 0) or 0),
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
