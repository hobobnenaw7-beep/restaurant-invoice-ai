from fastapi import APIRouter, HTTPException, Depends
import uuid
import re
from datetime import datetime, timezone

from core.database import db, logger
from core.auth import get_user
from core.models import PurchaseCreate, PurchaseUpdate
from services.audit import audit_log
from services.approval import compute_approval_status

router = APIRouter()


# ── Canonical-name enrichment (Milestone 19) ──────────────────────
# Resolves `canonical_item_id` + `variant_key` on purchase items to
# `display_name` / `canonical_name` / `variant_label` at READ time.
# This gives us automatic Canonical→Invoice propagation: editing the
# canonical item immediately changes how every linked invoice line
# appears, without touching invoice rows.
async def _enrich_purchases_with_canonical(rid: str, purchases: list) -> list:
    if not purchases:
        return purchases
    cids: set[str] = set()
    for p in purchases:
        for it in (p.get("items") or []):
            cid = it.get("canonical_item_id")
            if cid:
                cids.add(cid)
    if not cids:
        return purchases
    canon_map: dict[str, dict] = {}
    async for c in db.canonical_items.find(
        {"id": {"$in": list(cids)}, "restaurant_id": rid},
        {"_id": 0, "id": 1, "name": 1, "variants": 1, "is_archived": 1, "is_merged": 1,
         "merged_into_item_id": 1},
    ):
        canon_map[c["id"]] = c
    # Follow one merge hop so the display follows the catalog.
    merge_targets: set[str] = set()
    for c in canon_map.values():
        if c.get("is_merged") and c.get("merged_into_item_id"):
            merge_targets.add(c["merged_into_item_id"])
    if merge_targets - set(canon_map):
        async for c in db.canonical_items.find(
            {"id": {"$in": list(merge_targets - set(canon_map))}, "restaurant_id": rid},
            {"_id": 0, "id": 1, "name": 1, "variants": 1},
        ):
            canon_map[c["id"]] = c

    for p in purchases:
        for it in (p.get("items") or []):
            cid = it.get("canonical_item_id")
            if not cid:
                continue
            c = canon_map.get(cid)
            if not c:
                continue
            # Follow merge → target.
            if c.get("is_merged") and c.get("merged_into_item_id"):
                tgt = canon_map.get(c["merged_into_item_id"])
                if tgt:
                    c = tgt
            # Collect variants — prefer multi (variant_keys), fall back to legacy single (variant_key).
            vkeys_raw = it.get("variant_keys")
            if not vkeys_raw:
                lone = it.get("variant_key")
                vkeys_raw = [lone] if lone else []
            vkeys = [str(k).strip().lower() for k in (vkeys_raw or []) if k]
            variant_labels: list[str] = []
            variants_decl = c.get("variants") or []
            for vk in vkeys:
                label = vk
                for v in variants_decl:
                    if (v.get("key") or "").lower() == vk:
                        label = v.get("label") or vk
                        break
                variant_labels.append(label)
            it["canonical_name"] = c.get("name")
            it["variant_keys"] = vkeys
            it["variant_labels"] = variant_labels
            it["variant_label"] = variant_labels[0] if variant_labels else None  # legacy field
            base = c.get("name") or it.get("raw_name") or ""
            # Final display: "[Canonical Name] — v1 — v2"
            it["display_name"] = " — ".join([base, *variant_labels]) if variant_labels else base
    return purchases


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
        rows = await db.purchases.aggregate(pipeline).to_list(1000)
    else:
        rows = await db.purchases.find(query, {"_id": 0}).sort(sort_by, direction).to_list(1000)
    return await _enrich_purchases_with_canonical(user["restaurant_id"], rows)


@router.get("/purchases/{pid}")
async def get_purchase(pid: str, user=Depends(get_user)):
    p = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    enriched = await _enrich_purchases_with_canonical(user["restaurant_id"], [p])
    return enriched[0] if enriched else p


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
        alias_text = a.get("alias_name") or a.get("alias") or ""
        if not alias_text:
            continue
        for c in canon_items:
            if c["id"] == a.get("canonical_item_id"):
                name_to_group[alias_text.lower()] = c["name"].lower()
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
                if it.get("raw_name", "").lower() in match_names and float(it.get("unit_price") or 0) > 0:
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

    # ── Milestone 4: Price Intelligence ingestion ──
    try:
        from services.price_intelligence import ingest_purchase_items
        await ingest_purchase_items(
            restaurant_id=rid,
            purchase_id=doc["id"],
            supplier_name=doc.get("supplier_name") or "",
            supplier_id=supplier_id or "",
            invoice_date=doc.get("invoice_date") or "",
            items=doc.get("items", []),
        )
        # Persist any canonical identity fields written onto items during ingest
        await db.purchases.update_one(
            {"id": doc["id"], "restaurant_id": rid},
            {"$set": {"items": doc.get("items", [])}},
        )
    except Exception as e:  # never break invoice creation over pricing analytics
        logger.warning(f"price_intelligence.ingest failed for {doc.get('id')}: {e}")

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
            # Detect edits and save corrections (explicit save only)
            # RULE: Only NAME corrections create memory entries.
            # Price/quantity edits are audit data only.
            if idx < len(old_items):
                old_item = old_items_by_idx.get(idx, {})
                old_raw = old_item.get("raw_name", "").strip()
                new_raw = item.get("raw_name", "").strip()

                name_changed = bool(old_raw and new_raw and old_raw != new_raw)

                if name_changed:
                    vendor_name = old.get("supplier_name") or old.get("detected_vendor") or ""
                    item_code = (item.get("item_code") or old_item.get("item_code") or "").strip()
                    old_pack = (old_item.get("pack_size_raw") or old_item.get("pack_size") or "").strip()
                    new_pack = (item.get("pack_size_raw") or item.get("pack_size") or "").strip()
                    unit_hint = (item.get("pack_unit") or item.get("unit") or "").strip()
                    category_hint = (item.get("category") or "").strip()
                    variant_hint = (item.get("variant") or "").strip()

                    await save_correction(
                        user_id=user["id"],
                        user_name=user.get("name", ""),
                        restaurant_id=rid,
                        canonical_vendor=vendor_name,
                        original_raw_name=old_raw,
                        corrected_name=new_raw,
                        product_code=item_code,
                        pack_size=new_pack or old_pack,
                        supplier_id=supplier_id,
                        source="user_edit",
                        variant=variant_hint,
                        unit=unit_hint,
                        category=category_hint,
                    )

                    # Catalog linkage (non-destructive)
                    try:
                        from services.catalog_linkage import link_correction_to_catalog
                        await link_correction_to_catalog(
                            restaurant_id=rid,
                            user_id=user.get("id"),
                            original_raw_name=old_raw,
                            corrected_name=new_raw,
                            unit=unit_hint,
                            category=category_hint,
                        )
                    except Exception as e:   # pragma: no cover
                        logger.warning(f"catalog linkage (PUT) failed: {e}")
        validate_purchase_items(update_data["items"])
        update_data["review_status"] = compute_review_status(update_data["items"])
    old_vals = {k: old.get(k) for k in update_data}
    await db.purchases.update_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    await audit_log(user, "UPDATE", "Expense", pid, f'{user["name"]} updated expense ({old.get("supplier_name", "")})', old_value=old_vals, new_value=update_data)

    # ── Milestone 4: Price Intelligence re-ingestion ──
    try:
        updated = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
        if updated and "items" in update_data:
            from services.price_intelligence import ingest_purchase_items
            await ingest_purchase_items(
                restaurant_id=user["restaurant_id"],
                purchase_id=pid,
                supplier_name=updated.get("supplier_name") or "",
                supplier_id=updated.get("supplier_id") or "",
                invoice_date=updated.get("invoice_date") or "",
                items=updated.get("items", []),
            )
            await db.purchases.update_one(
                {"id": pid, "restaurant_id": user["restaurant_id"]},
                {"$set": {"items": updated.get("items", [])}},
            )
    except Exception as e:
        logger.warning(f"price_intelligence.ingest (update) failed for {pid}: {e}")

    return await db.purchases.find_one({"id": pid}, {"_id": 0})


@router.patch("/purchases/{pid}/items/{item_index}")
async def patch_purchase_item(pid: str, item_index: int, updates: dict, user=Depends(get_user)):
    """
    Phase 6: Inline edit a single line item with audit trail and revalidation.
    - Stores previous/new values + timestamp in edit_history
    - Re-runs client-compatible validation on the updated item
    - Returns the updated item with validation delta (better/worse/same)
    """
    from preprocessing import enrich_item_with_pack_size, validate_and_score_item, sanitize_extracted_item
    from services.normalization import normalize_item

    purchase = await db.purchases.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not purchase:
        raise HTTPException(404, "Purchase not found")

    items = purchase.get("items", [])
    if item_index < 0 or item_index >= len(items):
        raise HTTPException(400, f"Item index {item_index} out of range (0-{len(items)-1})")

    old_item = dict(items[item_index])

    # Allowed editable fields
    editable = {"raw_name", "quantity", "unit_price", "total", "pack_size"}
    changes = {}
    for field in editable:
        if field in updates and updates[field] is not None:
            old_val = old_item.get(field)
            new_val = updates[field]
            # Coerce numeric fields
            if field in ("quantity", "unit_price", "total"):
                new_val = float(new_val) if new_val else 0
                old_val = float(old_val or 0)
                if abs(old_val - new_val) > 0.001:
                    changes[field] = {"previous": old_val, "new": new_val}
            else:
                old_val = str(old_val or "")
                new_val = str(new_val or "")
                if old_val != new_val:
                    changes[field] = {"previous": old_val, "new": new_val}

    if not changes:
        return {"item": old_item, "validation_delta": "unchanged", "changes": {}}

    # Apply changes
    updated_item = dict(old_item)
    for field, vals in changes.items():
        updated_item[field] = vals["new"]

    # Store old validation state for delta comparison
    old_needs_review = old_item.get("needs_review", False)
    old_confidence = old_item.get("confidence_level", "")
    old_errors = old_item.get("validation_errors", [])

    # Re-run validation pipeline on the updated item
    sanitize_extracted_item(updated_item)
    enrich_item_with_pack_size(updated_item)
    normalize_item(updated_item)
    validate_and_score_item(updated_item)

    new_needs_review = updated_item.get("needs_review", False)
    new_confidence = updated_item.get("confidence_level", "")
    new_errors = updated_item.get("validation_errors", [])

    # Compute validation delta
    if old_needs_review and not new_needs_review:
        validation_delta = "improved"
    elif not old_needs_review and new_needs_review:
        validation_delta = "degraded"
    elif len(new_errors) < len(old_errors):
        validation_delta = "improved"
    elif len(new_errors) > len(old_errors):
        validation_delta = "degraded"
    else:
        validation_delta = "unchanged"

    # Build edit history entry
    edit_entry = {
        "item_index": item_index,
        "changes": changes,
        "validation_delta": validation_delta,
        "old_status": {"needs_review": old_needs_review, "confidence_level": old_confidence, "error_count": len(old_errors)},
        "new_status": {"needs_review": new_needs_review, "confidence_level": new_confidence, "error_count": len(new_errors)},
        "edited_by": user.get("name", user["id"]),
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }

    # Update the item in the array and append to edit_history
    items[item_index] = updated_item

    # Recompute review_status for the whole purchase
    from preprocessing import compute_review_status
    review_status = compute_review_status(items)

    # Recalculate subtotal/total
    subtotal = round(sum(float(it.get("total", 0) or 0) for it in items), 2)
    tax = float(purchase.get("tax", 0) or 0)
    total = round(subtotal + tax, 2)

    await db.purchases.update_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]},
        {
            "$set": {
                "items": items,
                "review_status": review_status,
                "subtotal": subtotal,
                "total": total,
            },
            "$push": {"edit_history": edit_entry},
        },
    )

    # Save correction to memory (explicit save via PATCH = user confirmed)
    # RULE: Only NAME corrections create correction_memory entries.
    # Price/quantity edits are stored as audit data only.
    # RULE: Unit corrections (price on needs_review items) save to unit_memory.
    catalog_linkage = None
    if changes:
        name_changed = "raw_name" in changes
        if name_changed:
            from services.correction_memory import save_correction
            from services.catalog_linkage import link_correction_to_catalog
            old_raw = old_item.get("raw_name", "").strip()
            new_raw = updated_item.get("raw_name", "").strip()
            vendor_name = purchase.get("supplier_name") or purchase.get("detected_vendor") or ""
            item_code = (updated_item.get("item_code") or old_item.get("item_code") or "").strip()
            pack = (updated_item.get("pack_size") or updated_item.get("pack_size_raw") or "").strip()
            # Extract optional metadata already resolved by normalize_item()
            unit_hint = (updated_item.get("pack_unit") or updated_item.get("unit") or "").strip()
            category_hint = (updated_item.get("category") or "").strip()
            variant_hint = (updated_item.get("variant") or "").strip()

            await save_correction(
                user_id=user["id"],
                user_name=user.get("name", ""),
                restaurant_id=user["restaurant_id"],
                canonical_vendor=vendor_name,
                original_raw_name=old_raw,
                corrected_name=new_raw,
                product_code=item_code,
                pack_size=pack,
                source="user_edit",
                variant=variant_hint,
                unit=unit_hint,
                category=category_hint,
            )

            # Catalog linkage — lightweight, non-destructive.
            try:
                catalog_linkage = await link_correction_to_catalog(
                    restaurant_id=user["restaurant_id"],
                    user_id=user.get("id"),
                    original_raw_name=old_raw,
                    corrected_name=new_raw,
                    unit=unit_hint,
                    category=category_hint,
                )
            except Exception as e:   # pragma: no cover
                logger.warning(f"catalog linkage failed: {e}")

        # Unit memory sync: when user fills in price/total on a review item,
        # AND the item has normalization data, save as user_corrected truth.
        price_or_total_changed = "unit_price" in changes or "total" in changes
        item_code = (updated_item.get("item_code") or "").strip()
        has_norm = updated_item.get("canonical_unit") and updated_item.get("normalization_multiplier")
        was_review = old_item.get("unit_status") == "review" or old_item.get("_unit_source") == "conflict"

        if price_or_total_changed and item_code and has_norm:
            from services.unit_normalizer import save_unit_memory
            vendor_name = purchase.get("supplier_name") or purchase.get("detected_vendor") or ""
            await save_unit_memory(
                vendor=vendor_name,
                product_code=item_code,
                restaurant_id=user["restaurant_id"],
                canonical_unit=updated_item["canonical_unit"],
                multiplier=updated_item["normalization_multiplier"],
                pack_size=(updated_item.get("pack_size") or "").strip(),
                parse_method="user_corrected",
                source="user_corrected",
                corrected_by_user_id=user["id"],
                corrected_by_name=user.get("name", ""),
            )
        elif was_review and item_code and not has_norm:
            # User resolved a review item — try to derive multiplier from the edit
            new_total = float(updated_item.get("total", 0) or 0)
            new_price = float(updated_item.get("unit_price", 0) or 0)
            new_qty = float(updated_item.get("quantity", 0) or 0)
            pack_str = (updated_item.get("pack_size") or "").strip()

            if new_total > 0 and new_qty > 0 and new_price > 0 and pack_str:
                from services.unit_normalizer import parse_pack_size, save_unit_memory
                parsed = parse_pack_size(pack_str)
                if parsed["parsed"]:
                    mult = parsed.get("total_weight_lb") or parsed.get("total_pieces")
                    unit_type = parsed.get("unit_type")
                    canon_map = {"lb": "lb", "piece": "piece", "gallon": "gal"}
                    canon = canon_map.get(unit_type, "")
                    if mult and canon:
                        vendor_name = purchase.get("supplier_name") or purchase.get("detected_vendor") or ""
                        await save_unit_memory(
                            vendor=vendor_name,
                            product_code=item_code,
                            restaurant_id=user["restaurant_id"],
                            canonical_unit=canon,
                            multiplier=float(mult),
                            pack_size=pack_str,
                            parse_method="user_corrected",
                            source="user_corrected",
                            corrected_by_user_id=user["id"],
                            corrected_by_name=user.get("name", ""),
                        )

    return {
        "item": {k: v for k, v in updated_item.items() if k != "_id"},
        "item_index": item_index,
        "validation_delta": validation_delta,
        "changes": changes,
        "edit_entry": edit_entry,
        "purchase_totals": {"subtotal": subtotal, "tax": tax, "total": total},
        "review_status": review_status,
        "catalog_linkage": catalog_linkage,
        "price_intelligence": await _reingest_price_intelligence(pid, user["restaurant_id"]),
    }


async def _reingest_price_intelligence(pid: str, restaurant_id: str) -> dict:
    """Milestone 4: Re-ingest price observations after an inline item edit."""
    try:
        updated = await db.purchases.find_one(
            {"id": pid, "restaurant_id": restaurant_id}, {"_id": 0}
        )
        if not updated:
            return {"inserted": 0, "skipped": 0, "new_alerts": []}
        from services.price_intelligence import ingest_purchase_items
        stats = await ingest_purchase_items(
            restaurant_id=restaurant_id,
            purchase_id=pid,
            supplier_name=updated.get("supplier_name") or "",
            supplier_id=updated.get("supplier_id") or "",
            invoice_date=updated.get("invoice_date") or "",
            items=updated.get("items", []),
        )
        await db.purchases.update_one(
            {"id": pid, "restaurant_id": restaurant_id},
            {"$set": {"items": updated.get("items", [])}},
        )
        return stats
    except Exception as e:
        logger.warning(f"price_intelligence.ingest (patch) failed for {pid}: {e}")
        return {"inserted": 0, "skipped": 0, "new_alerts": [], "error": str(e)}


@router.get("/purchases/{pid}/edit-history")
async def get_edit_history(pid: str, user=Depends(get_user)):
    """Phase 6: Return the edit audit trail for a purchase."""
    purchase = await db.purchases.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]},
        {"_id": 0, "edit_history": 1, "id": 1},
    )
    if not purchase:
        raise HTTPException(404, "Purchase not found")
    return {"id": pid, "edit_history": purchase.get("edit_history", [])}



@router.patch("/purchases/{pid}/verify")
async def verify_purchase(pid: str, user=Depends(get_user)):
    """
    Mark a purchase as verified after all review items have been resolved.
    Sets review_status='verified' and records verification metadata.
    """
    purchase = await db.purchases.find_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0}
    )
    if not purchase:
        raise HTTPException(404, "Purchase not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "review_status": "verified",
        "approval_status": "approved",
        "verified_by_user_id": user["id"],
        "verified_by_name": user.get("name", ""),
        "verified_at": now,
    }
    await db.purchases.update_one(
        {"id": pid, "restaurant_id": user["restaurant_id"]},
        {"$set": updates},
    )
    await audit_log(
        user, "VERIFY", "Expense", pid,
        f'{user["name"]} verified expense ${purchase.get("total", 0)} ({purchase.get("supplier_name", "")})',
    )
    return {"status": "verified", "verified_at": now, "verified_by": user.get("name", "")}





@router.delete("/purchases/{pid}")
async def delete_purchase(pid: str, user=Depends(get_user)):
    old = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    await db.purchases.delete_one({"id": pid, "restaurant_id": user["restaurant_id"]})
    await audit_log(user, "DELETE", "Expense", pid, f'{user["name"]} deleted expense ${old.get("total", 0)} ({old.get("supplier_name", "")})', old_value={"supplier": old.get("supplier_name"), "total": old.get("total"), "invoice_date": old.get("invoice_date")})
    return {"status": "deleted"}
