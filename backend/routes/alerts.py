from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta

from core.database import db
from core.auth import get_user

router = APIRouter()


@router.get("/alerts/prices")
async def list_price_alerts(user=Depends(get_user)):
    """Get price increase alerts, newest first."""
    return await db.alerts.find(
        {"restaurant_id": user["restaurant_id"], "type": "price_increase"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)


@router.delete("/alerts/prices/{aid}")
async def dismiss_price_alert(aid: str, user=Depends(get_user)):
    result = await db.alerts.delete_one({"id": aid, "restaurant_id": user["restaurant_id"], "type": "price_increase"})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}


@router.get("/alerts")
async def list_alerts(user=Depends(get_user)):
    return await db.alerts.find({"restaurant_id": user["restaurant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.put("/alerts/{aid}/read")
async def mark_alert_read(aid: str, user=Depends(get_user)):
    await db.alerts.update_one({"id": aid, "restaurant_id": user["restaurant_id"]}, {"$set": {"is_read": True}})
    return {"status": "ok"}


@router.get("/purchase-decisions")
async def smart_purchase_decisions(user=Depends(get_user)):
    """Generate smart purchase insights from real purchase data."""
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)
    purchases = await db.purchases.find(
        {"restaurant_id": rid, "$or": [{"approval_status": {"$exists": False}}, {"approval_status": "approved"}]},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}
    ).to_list(10000)

    if not purchases:
        return {"items": [], "insights": [], "weekly_changes": [], "potential_savings": 0, "total_items": 0}

    this_week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    last_week_start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y-%m-%d")
    last_week_end = (now - timedelta(days=now.weekday() + 1)).strftime("%Y-%m-%d")

    item_vendor_data = {}
    for p in purchases:
        vendor = p.get("supplier_name", "")
        inv_date = p.get("invoice_date", "")
        for it in p.get("items", []):
            raw = it.get("raw_name", "").strip()
            price = float(it.get("unit_price", 0) or 0)
            qty = float(it.get("quantity", 0) or 0)
            if raw and price > 0:
                item_vendor_data.setdefault(raw, {}).setdefault(vendor, []).append({
                    "price": price, "date": inv_date, "qty": qty, "unit": it.get("unit", "")
                })

    items_out = []
    insights = []
    weekly_changes = []
    total_potential_savings = 0

    for item_name, vendors_data in sorted(item_vendor_data.items()):
        vendor_summaries = []
        all_prices = []
        for vendor_name, entries in vendors_data.items():
            entries.sort(key=lambda x: x["date"])
            latest = entries[-1]
            avg_price = round(sum(e["price"] for e in entries) / len(entries), 2)
            vendor_summaries.append({
                "vendor": vendor_name, "latest_price": round(latest["price"], 2),
                "avg_price": avg_price, "latest_date": latest["date"],
                "purchase_count": len(entries), "unit": latest.get("unit", ""),
            })
            all_prices.extend(entries)

        vendor_summaries.sort(key=lambda x: x["latest_price"])
        best = vendor_summaries[0]

        this_week_prices = [e["price"] for e in all_prices if e["date"] >= this_week_start]
        last_week_prices = [e["price"] for e in all_prices if last_week_start <= e["date"] <= last_week_end]

        week_change = None
        if this_week_prices and last_week_prices:
            tw_avg = sum(this_week_prices) / len(this_week_prices)
            lw_avg = sum(last_week_prices) / len(last_week_prices)
            if lw_avg > 0:
                change_pct = round(((tw_avg - lw_avg) / lw_avg) * 100, 1)
                if abs(change_pct) > 1:
                    week_change = {
                        "item": item_name, "this_week_avg": round(tw_avg, 2),
                        "last_week_avg": round(lw_avg, 2), "change_pct": change_pct,
                        "direction": "up" if change_pct > 0 else "down",
                        "unit": best.get("unit", ""),
                    }
                    weekly_changes.append(week_change)

        saving_per_unit = 0
        if len(vendor_summaries) > 1:
            worst = vendor_summaries[-1]
            saving_per_unit = round(worst["latest_price"] - best["latest_price"], 2)
            worst_entries = vendors_data.get(worst["vendor"], [])
            avg_qty = sum(e["qty"] for e in worst_entries) / max(len(worst_entries), 1)
            total_potential_savings += round(saving_per_unit * avg_qty, 2)

            if saving_per_unit > 0:
                insights.append({
                    "type": "best_vendor", "item": item_name,
                    "best_vendor": best["vendor"], "best_price": best["latest_price"],
                    "worst_vendor": worst["vendor"], "worst_price": worst["latest_price"],
                    "saving_per_unit": saving_per_unit, "unit": best.get("unit", ""),
                    "pct": round((saving_per_unit / worst["latest_price"]) * 100, 1) if worst["latest_price"] > 0 else 0,
                })

        items_out.append({
            "item": item_name, "vendors": vendor_summaries,
            "best_vendor": best["vendor"], "best_price": best["latest_price"],
            "saving_per_unit": saving_per_unit, "vendor_count": len(vendor_summaries),
            "unit": best.get("unit", ""), "week_change": week_change,
        })

    for wc in weekly_changes:
        if wc["direction"] == "up" and wc["change_pct"] > 3:
            insights.append({
                "type": "price_increase", "item": wc["item"],
                "change_pct": wc["change_pct"], "this_week": wc["this_week_avg"],
                "last_week": wc["last_week_avg"], "unit": wc.get("unit", ""),
            })

    insights.sort(key=lambda x: -(x.get("saving_per_unit", 0) or x.get("change_pct", 0)))

    return {
        "items": items_out, "insights": insights[:20],
        "weekly_changes": sorted(weekly_changes, key=lambda x: -abs(x["change_pct"])),
        "potential_savings": round(total_potential_savings, 2), "total_items": len(items_out),
    }
