from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta

from core.database import db
from core.auth import get_user

router = APIRouter()


@router.get("/prices/intelligence")
async def price_intelligence(user=Depends(get_user)):
    """Comprehensive price tracking: supplier comparison, trends, and alerts."""
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)

    item_supplier_prices = {}
    for p in purchases:
        supplier = p.get("supplier_name", "Unknown")
        inv_date = p.get("invoice_date", "")
        for it in p.get("items", []):
            name = it.get("raw_name", "Unknown")
            price = float(it.get("unit_price", 0))
            qty = float(it.get("quantity", 0))
            if price > 0:
                item_supplier_prices.setdefault(name, {}).setdefault(supplier, []).append({
                    "price": price, "date": inv_date, "qty": qty
                })

    all_suppliers = set()
    for p in purchases:
        sn = p.get("supplier_name", "").strip()
        if sn:
            all_suppliers.add(sn)
    all_suppliers = sorted(all_suppliers)

    comparison_items = []
    for item_name, suppliers_data in sorted(item_supplier_prices.items()):
        row = {"item": item_name, "suppliers": {}, "best_supplier": None, "best_price": None, "worst_price": None}
        for sup, entries in suppliers_data.items():
            avg_p = round(sum(e["price"] for e in entries) / len(entries), 2)
            latest_p = entries[-1]["price"] if entries else 0
            total_qty = sum(e["qty"] for e in entries)
            row["suppliers"][sup] = {"avg_price": avg_p, "latest_price": round(latest_p, 2), "purchase_count": len(entries), "total_qty": round(total_qty, 1)}
        prices_list = [(sup, d["avg_price"]) for sup, d in row["suppliers"].items()]
        if prices_list:
            prices_list.sort(key=lambda x: x[1])
            row["best_supplier"] = prices_list[0][0]
            row["best_price"] = prices_list[0][1]
            row["worst_price"] = prices_list[-1][1]
            if len(prices_list) > 1 and prices_list[-1][1] > 0:
                row["savings_pct"] = round((1 - prices_list[0][1] / prices_list[-1][1]) * 100, 1)
            else:
                row["savings_pct"] = 0
        comparison_items.append(row)

    comparison_items.sort(key=lambda x: (-len(x["suppliers"]), -(x.get("savings_pct", 0))))

    item_weekly = {}
    for item_name, suppliers_data in item_supplier_prices.items():
        all_entries = []
        for entries in suppliers_data.values():
            all_entries.extend(entries)
        all_entries.sort(key=lambda x: x["date"])
        weekly = {}
        for e in all_entries:
            if e["date"]:
                try:
                    d = datetime.strptime(e["date"], "%Y-%m-%d")
                    week_key = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
                    weekly.setdefault(week_key, []).append(e["price"])
                except ValueError:
                    pass
        if weekly:
            item_weekly[item_name] = [{"week": k, "avg_price": round(sum(v) / len(v), 2)} for k, v in sorted(weekly.items())]

    item_total_spend = {}
    for p in purchases:
        for it in p.get("items", []):
            name = it.get("raw_name", "Unknown")
            item_total_spend[name] = item_total_spend.get(name, 0) + float(it.get("total", 0))
    top_trend_items = sorted(item_total_spend.items(), key=lambda x: -x[1])[:8]
    price_trends = {name: item_weekly.get(name, []) for name, _ in top_trend_items if name in item_weekly}

    thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    sixty_days_ago = (now - timedelta(days=60)).strftime("%Y-%m-%d")

    recent_avg = {}
    older_avg = {}
    for item_name, suppliers_data in item_supplier_prices.items():
        recent_prices = []
        older_prices = []
        for entries in suppliers_data.values():
            for e in entries:
                if e["date"] >= thirty_days_ago:
                    recent_prices.append(e["price"])
                elif e["date"] >= sixty_days_ago:
                    older_prices.append(e["price"])
        if recent_prices:
            recent_avg[item_name] = sum(recent_prices) / len(recent_prices)
        if older_prices:
            older_avg[item_name] = sum(older_prices) / len(older_prices)

    price_alerts = []
    for name, cur in recent_avg.items():
        prev = older_avg.get(name)
        if prev and prev > 0:
            pct = ((cur - prev) / prev) * 100
            if pct > 10:
                price_alerts.append({
                    "item": name, "current_avg": round(cur, 2), "previous_avg": round(prev, 2),
                    "change_pct": round(pct, 1), "severity": "high" if pct > 20 else "medium",
                })
    price_alerts.sort(key=lambda x: -x["change_pct"])

    return {
        "suppliers": all_suppliers, "comparison": comparison_items[:30],
        "price_trends": price_trends, "price_alerts": price_alerts[:15],
        "total_items_tracked": len(item_supplier_prices), "total_suppliers": len(all_suppliers),
    }


@router.get("/prices/vendor-comparison")
async def vendor_price_comparison(user=Depends(get_user)):
    """Per-item, per-vendor latest price comparison with best vendor highlighted."""
    rid = user["restaurant_id"]
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}).to_list(10000)

    canonical = await db.canonical_items.find({"restaurant_id": rid}, {"_id": 0}).to_list(1000)
    aliases = await db.item_aliases.find({"restaurant_id": rid}, {"_id": 0}).to_list(5000)
    alias_to_canonical = {}
    for a in aliases:
        for c in canonical:
            if c["id"] == a["canonical_item_id"]:
                alias_to_canonical[a["alias_name"].lower()] = c["name"]
                break
    for c in canonical:
        alias_to_canonical[c["name"].lower()] = c["name"]

    item_vendor_prices = {}
    for p in purchases:
        vendor = p.get("supplier_name", "Unknown")
        inv_date = p.get("invoice_date", "")
        for it in p.get("items", []):
            raw = it.get("raw_name", "")
            price = float(it.get("unit_price", 0))
            if price <= 0:
                continue
            canon = alias_to_canonical.get(raw.lower(), raw)
            item_vendor_prices.setdefault(canon, {}).setdefault(vendor, []).append({
                "price": price, "date": inv_date, "raw_name": raw,
                "quantity": float(it.get("quantity", 0)), "unit": it.get("unit", ""),
            })

    items_out = []
    for item_name, vendors_data in sorted(item_vendor_prices.items()):
        vendors_list = []
        for vendor_name, entries in sorted(vendors_data.items()):
            entries.sort(key=lambda x: x["date"], reverse=True)
            latest = entries[0]
            avg = round(sum(e["price"] for e in entries) / len(entries), 2)
            vendors_list.append({
                "vendor": vendor_name, "latest_price": round(latest["price"], 2),
                "latest_date": latest["date"], "avg_price": avg,
                "purchase_count": len(entries), "unit": latest.get("unit", ""),
            })

        vendors_list.sort(key=lambda x: x["latest_price"])
        best_vendor = vendors_list[0]["vendor"] if vendors_list else None
        best_price = vendors_list[0]["latest_price"] if vendors_list else 0
        worst_price = vendors_list[-1]["latest_price"] if len(vendors_list) > 1 else best_price
        savings_pct = round((1 - best_price / worst_price) * 100, 1) if worst_price > 0 and len(vendors_list) > 1 else 0

        items_out.append({
            "item": item_name, "vendors": vendors_list, "best_vendor": best_vendor,
            "best_price": best_price, "savings_pct": savings_pct, "vendor_count": len(vendors_list),
        })

    items_out.sort(key=lambda x: (-x["vendor_count"], -x["savings_pct"]))
    return {"items": items_out, "total_items": len(items_out)}
