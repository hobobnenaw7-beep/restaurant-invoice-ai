from fastapi import APIRouter, HTTPException, Depends, Body
import uuid, re
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user

router = APIRouter()


def _conservative_item_key(raw_name: str) -> str:
    """Conservative name normalization for item grouping. EXACT match after cleanup only."""
    s = (raw_name or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def _word_similarity(name1: str, name2: str) -> float:
    """Jaccard similarity on word sets. Returns 0.0-1.0."""
    w1 = set(name1.upper().split())
    w2 = set(name2.upper().split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def _collect_qualifying_entries(purchases: list, normalizable_units: set) -> tuple:
    """Extract qualifying entries from purchases. Returns (groups_dict, total_qualifying, all_item_vendors)."""
    groups = {}
    total_qualifying = 0
    item_vendors = {}

    for p in purchases:
        vendor = (p.get("supplier_name") or "Unknown").strip()
        inv_date = p.get("invoice_date", "")

        for item in p.get("items", []):
            nplb = item.get("normalized_price_per_lb")
            pack_unit = (item.get("pack_unit") or "").upper()
            tcw = item.get("total_case_weight")

            if not nplb or nplb <= 0:
                continue
            if pack_unit not in normalizable_units:
                continue
            if not tcw or tcw <= 0:
                continue

            total_qualifying += 1
            raw_name = item.get("raw_name", "")
            item_key = _conservative_item_key(raw_name)
            if not item_key:
                continue

            item_vendors.setdefault(item_key, set()).add(vendor)
            group_key = (item_key, "LB")
            entry = {
                "vendor": vendor,
                "raw_name": raw_name,
                "pack_size_raw": item.get("pack_size_raw") or item.get("pack_size", ""),
                "unit_price": round(float(item.get("unit_price", 0) or 0), 2),
                "total_case_weight": tcw,
                "pack_unit": pack_unit,
                "normalized_price_per_lb": round(nplb, 4),
                "invoice_date": inv_date,
            }
            groups.setdefault(group_key, []).append(entry)

    return groups, total_qualifying, item_vendors


@router.get("/item-mappings")
async def list_item_mappings(user=Depends(get_user)):
    """List all confirmed item mappings."""
    mappings = await db.item_mappings.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).to_list(1000)
    return {"mappings": mappings}


@router.post("/item-mappings")
async def create_item_mapping(data: dict = Body(...), user=Depends(get_user)):
    """Create a confirmed item mapping. Body: {canonical_name, mapped_names: [str]}"""
    rid = user["restaurant_id"]
    canonical = (data.get("canonical_name") or "").strip()
    raw_names = data.get("mapped_names", [])
    mapped = sorted(set(_conservative_item_key(n) for n in raw_names if n.strip()))

    if not canonical or len(mapped) < 2:
        raise HTTPException(400, "Need canonical_name and at least 2 mapped_names")

    existing = await db.item_mappings.find({"restaurant_id": rid}, {"_id": 0}).to_list(500)
    already_mapped = set()
    for m in existing:
        for n in m.get("mapped_names", []):
            already_mapped.add(n)
    conflicts = [n for n in mapped if n in already_mapped]
    if conflicts:
        raise HTTPException(409, f"Already mapped: {', '.join(conflicts)}")

    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": rid,
        "canonical_name": canonical,
        "mapped_names": mapped,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.item_mappings.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/item-mappings/{mid}")
async def update_item_mapping(mid: str, data: dict = Body(...), user=Depends(get_user)):
    """Update mapping. Body: {canonical_name?, mapped_names?: [str]}"""
    rid = user["restaurant_id"]
    existing = await db.item_mappings.find_one({"id": mid, "restaurant_id": rid})
    if not existing:
        raise HTTPException(404, "Mapping not found")

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "canonical_name" in data and data["canonical_name"].strip():
        updates["canonical_name"] = data["canonical_name"].strip()
    if "mapped_names" in data:
        mapped = sorted(set(_conservative_item_key(n) for n in data["mapped_names"] if n.strip()))
        if len(mapped) < 2:
            raise HTTPException(400, "Need at least 2 mapped_names")
        all_mappings = await db.item_mappings.find({"restaurant_id": rid, "id": {"$ne": mid}}, {"_id": 0}).to_list(500)
        already_mapped = set()
        for m in all_mappings:
            for n in m.get("mapped_names", []):
                already_mapped.add(n)
        conflicts = [n for n in mapped if n in already_mapped]
        if conflicts:
            raise HTTPException(409, f"Already mapped elsewhere: {', '.join(conflicts)}")
        updates["mapped_names"] = mapped

    await db.item_mappings.update_one({"id": mid, "restaurant_id": rid}, {"$set": updates})
    result = await db.item_mappings.find_one({"id": mid, "restaurant_id": rid}, {"_id": 0})
    return result


@router.delete("/item-mappings/{mid}")
async def delete_item_mapping(mid: str, user=Depends(get_user)):
    result = await db.item_mappings.delete_one({"id": mid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}


@router.get("/item-mappings/suggestions")
async def item_mapping_suggestions(user=Depends(get_user)):
    """Suggest similar item names from qualifying purchase data."""
    rid = user["restaurant_id"]
    purchases = await db.purchases.find(
        {"restaurant_id": rid},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}
    ).to_list(10000)

    from preprocessing import NORMALIZABLE_UNITS
    _, _, item_vendors = _collect_qualifying_entries(purchases, NORMALIZABLE_UNITS)

    mappings = await db.item_mappings.find({"restaurant_id": rid}, {"_id": 0}).to_list(500)
    name_to_mapping = {}
    for m in mappings:
        for n in m.get("mapped_names", []):
            name_to_mapping[n] = m["id"]

    item_keys = sorted(item_vendors.keys())
    suggestions = []
    for i in range(len(item_keys)):
        for j in range(i + 1, len(item_keys)):
            a, b = item_keys[i], item_keys[j]
            if a in name_to_mapping and b in name_to_mapping and name_to_mapping[a] == name_to_mapping[b]:
                continue
            if a in name_to_mapping or b in name_to_mapping:
                continue
            sim = _word_similarity(a, b)
            if sim >= 0.4:
                suggestions.append({
                    "name_a": a, "name_b": b,
                    "vendors_a": sorted(item_vendors[a]),
                    "vendors_b": sorted(item_vendors[b]),
                    "similarity": round(sim, 3),
                    "shared_words": sorted(set(a.split()) & set(b.split())),
                })

    suggestions.sort(key=lambda s: -s["similarity"])
    return {"suggestions": suggestions, "total": len(suggestions)}


@router.get("/vendor-comparison/normalized")
async def normalized_vendor_comparison(user=Depends(get_user)):
    """Vendor price comparison using ONLY strictly parsed, normalized $/LB values."""
    rid = user["restaurant_id"]
    purchases = await db.purchases.find(
        {"restaurant_id": rid},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}
    ).to_list(10000)

    from preprocessing import NORMALIZABLE_UNITS
    groups, total_qualifying, _ = _collect_qualifying_entries(purchases, NORMALIZABLE_UNITS)

    mappings = await db.item_mappings.find({"restaurant_id": rid}, {"_id": 0}).to_list(500)
    name_to_canonical = {}
    for m in mappings:
        canon = m["canonical_name"]
        for n in m.get("mapped_names", []):
            name_to_canonical[n] = canon

    merged_groups = {}
    group_source = {}

    for (item_key, comp_unit), entries in groups.items():
        canonical = name_to_canonical.get(item_key)
        if canonical:
            merge_key = (canonical, comp_unit)
            source = "user_confirmed"
        else:
            merge_key = (item_key, comp_unit)
            source = "exact"

        if merge_key not in merged_groups:
            merged_groups[merge_key] = []
            group_source[merge_key] = source
        else:
            if source == "user_confirmed":
                group_source[merge_key] = "user_confirmed"
        merged_groups[merge_key].extend(entries)

    comparisons = []
    multi_vendor_count = 0
    vendors_seen = set()

    for (item_key, comp_unit), entries in sorted(merged_groups.items()):
        entry_vendors = set(e["vendor"] for e in entries)
        vendors_seen.update(entry_vendors)
        is_multi = len(entry_vendors) > 1
        if is_multi:
            multi_vendor_count += 1

        entries_sorted = sorted(entries, key=lambda e: e["normalized_price_per_lb"])
        best = entries_sorted[0]["normalized_price_per_lb"]
        worst = entries_sorted[-1]["normalized_price_per_lb"]
        spread_pct = round((worst - best) / best * 100, 1) if best > 0 and len(entries_sorted) > 1 else 0

        raw_names_in_group = sorted(set(e["raw_name"] for e in entries))

        comparisons.append({
            "item_key": item_key,
            "comparison_unit": comp_unit,
            "match_source": group_source[(item_key, comp_unit)],
            "entries": entries_sorted,
            "raw_names_in_group": raw_names_in_group,
            "best_price": best,
            "worst_price": worst,
            "spread_pct": spread_pct,
            "entry_count": len(entries_sorted),
            "vendor_count": len(entry_vendors),
            "is_multi_vendor": is_multi,
        })

    comparisons.sort(key=lambda c: (-c["vendor_count"], -c["spread_pct"], c["item_key"]))

    confirmed_groups = sum(1 for c in comparisons if c["match_source"] == "user_confirmed")

    return {
        "comparisons": comparisons,
        "stats": {
            "total_qualifying_items": total_qualifying,
            "total_groups": len(comparisons),
            "multi_vendor_groups": multi_vendor_count,
            "single_vendor_groups": len(comparisons) - multi_vendor_count,
            "vendors_represented": len(vendors_seen),
            "user_confirmed_groups": confirmed_groups,
        },
    }
