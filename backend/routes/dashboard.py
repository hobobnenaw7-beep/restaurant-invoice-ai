from fastapi import APIRouter, Depends
import calendar
from datetime import datetime, timezone

from core.database import db
from core.auth import get_user
from services.alerts import generate_smart_alerts

router = APIRouter()


@router.get("/dashboard/summary")
async def dashboard_summary(year: int = 0, month: int = 0, user=Depends(get_user)):
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)

    sel_year = year if year > 0 else now.year
    sel_month = month

    if sel_month > 0:
        _, last_day = calendar.monthrange(sel_year, sel_month)
        period_start = f"{sel_year}-{sel_month:02d}-01"
        period_end = f"{sel_year}-{sel_month:02d}-{last_day:02d}"
        if sel_month == 1:
            prev_year, prev_mo = sel_year - 1, 12
        else:
            prev_year, prev_mo = sel_year, sel_month - 1
        _, prev_last = calendar.monthrange(prev_year, prev_mo)
        prev_start = f"{prev_year}-{prev_mo:02d}-01"
        prev_end = f"{prev_year}-{prev_mo:02d}-{prev_last:02d}"
    else:
        period_start = f"{sel_year}-01-01"
        period_end = f"{sel_year}-12-31"
        prev_start = f"{sel_year - 1}-01-01"
        prev_end = f"{sel_year - 1}-12-31"

    _approved = {"$or": [{"approval_status": {"$exists": False}}, {"approval_status": "approved"}]}
    purchases = await db.purchases.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
    salaries = await db.salaries.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
    other_exp = await db.other_expenses.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
    sales = await db.sales.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)

    def sum_p(df, dt=None):
        return sum(p["total"] for p in purchases if p.get("invoice_date", "") >= df and (not dt or p.get("invoice_date", "") <= dt))
    def sum_sal(df, dt=None):
        return sum(s["amount"] for s in salaries if s.get("payment_date", "") >= df and (not dt or s.get("payment_date", "") <= dt))
    def sum_oe(df, dt=None):
        return sum(e["amount"] for e in other_exp if e.get("expense_date", "") >= df and (not dt or e.get("expense_date", "") <= dt))
    def sum_s(df, dt=None):
        return sum(s["total_sales"] for s in sales if s.get("report_date", "") >= df and (not dt or s.get("report_date", "") <= dt))

    smart_alerts = await generate_smart_alerts(rid)

    # Milestone 4 (DSS): merge Price Intelligence alerts (only High-confidence
    # alerts are ever persisted by the backend — Medium/Low are suppressed at
    # evaluation time).
    pi_alerts = []
    pi_cursor = db.alerts.find(
        {"restaurant_id": rid, "type": "price_intelligence"}, {"_id": 0}
    ).sort("change_pct", -1)
    async for pi in pi_cursor:
        # Double-guard: skip if the cached record isn't high-confidence
        if pi.get("confidence_level") and pi.get("confidence_level") != "high":
            continue
        pi_alerts.append({
            "type": "price_increase",
            "severity": pi.get("severity", "medium"),
            "item_name": pi.get("item_name", ""),
            "vendor": pi.get("vendor", ""),
            "change_pct": pi.get("change_pct", 0),
            "old_price": pi.get("previous_price", 0),
            "new_price": pi.get("new_price", 0),
            "source": "price_intelligence",
            "confidence_level": pi.get("confidence_level", "high"),
            "confidence_score": pi.get("confidence_score", 0),
            "canonical_unit": pi.get("canonical_unit", ""),
            "message": pi.get("message", ""),
        })
    # Price intelligence alerts take priority in the bell
    smart_alerts = pi_alerts + smart_alerts

    severity_order = {"high": 0, "medium": 1, "low": 2}
    smart_alerts.sort(key=lambda a: severity_order.get(a.get("severity", "low"), 2))
    smart_alerts = smart_alerts[:5]

    all_dates = []
    for p in purchases:
        d = p.get("created_at", p.get("invoice_date", ""))
        if d:
            all_dates.append(str(d))
    for s in salaries:
        d = s.get("created_at", s.get("payment_date", ""))
        if d:
            all_dates.append(str(d))
    for e in other_exp:
        d = e.get("created_at", e.get("expense_date", ""))
        if d:
            all_dates.append(str(d))
    all_dates.sort(reverse=True)
    last_update = all_dates[0] if all_dates else now.isoformat()

    savings = []
    risks = []
    for sa in smart_alerts:
        if sa["type"] == "cheaper_vendor":
            savings.append({
                "type": "saving", "item_name": sa["item_name"],
                "vendor": sa.get("cheaper_vendor", ""), "current_vendor": sa.get("vendor", ""),
                "savings_pct": sa.get("savings_pct", 0), "cheaper_price": sa.get("cheaper_price", 0),
                "current_price": sa.get("current_price", 0),
            })
        elif sa["type"] == "price_increase":
            risks.append({
                "type": "risk", "item_name": sa["item_name"],
                "vendor": sa.get("vendor", ""), "change_pct": sa.get("change_pct", 0),
                "old_price": sa.get("old_price", 0), "new_price": sa.get("new_price", 0),
            })
    all_alerts = await generate_smart_alerts(rid)
    for sa in all_alerts:
        if sa["type"] == "cheaper_vendor" and not savings:
            savings.append({
                "type": "saving", "item_name": sa["item_name"],
                "vendor": sa.get("cheaper_vendor", ""), "current_vendor": sa.get("vendor", ""),
                "savings_pct": sa.get("savings_pct", 0), "cheaper_price": sa.get("cheaper_price", 0),
                "current_price": sa.get("current_price", 0),
            })
    best_opportunities = []
    if savings:
        best_opportunities.append(savings[0])
    if risks:
        best_opportunities.append(risks[0])
    best_opportunities = best_opportunities[:2]

    return {
        "month_raw_materials": round(sum_p(period_start, period_end), 2),
        "month_salaries": round(sum_sal(period_start, period_end), 2),
        "month_other_expenses": round(sum_oe(period_start, period_end), 2),
        "prev_month_raw_materials": round(sum_p(prev_start, prev_end), 2),
        "prev_month_salaries": round(sum_sal(prev_start, prev_end), 2),
        "prev_month_other_expenses": round(sum_oe(prev_start, prev_end), 2),
        "month_sales": round(sum_s(period_start, period_end), 2),
        "prev_month_sales": round(sum_s(prev_start, prev_end), 2),
        "smart_alerts": smart_alerts,
        "last_data_update": last_update,
        "best_opportunities": best_opportunities,
        "purchase_count": len(purchases),
        "filter_year": sel_year,
        "filter_month": sel_month,
    }


@router.get("/dashboard/item-search")
async def dashboard_item_search(q: str = "", user=Depends(get_user)):
    """Search for an item across all purchases and return vendor/price comparison."""
    rid = user["restaurant_id"]
    if not q or len(q.strip()) < 2:
        return {"results": []}

    query_lower = q.strip().lower()
    _approved = {"$or": [{"approval_status": {"$exists": False}}, {"approval_status": "approved"}]}
    purchases = await db.purchases.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)

    item_vendor_data = {}
    for p in purchases:
        vendor = p.get("supplier_name", "Unknown")
        inv_date = p.get("invoice_date", "")
        for it in p.get("items", []):
            raw_name = it.get("raw_name", "")
            if not raw_name or query_lower not in raw_name.lower():
                continue
            key = raw_name.lower()
            if key not in item_vendor_data:
                item_vendor_data[key] = {"name": raw_name, "vendors": {}}
            vd = item_vendor_data[key]["vendors"]
            if vendor not in vd:
                vd[vendor] = {"prices": [], "dates": [], "unit": it.get("unit", "")}
            unit_price = float(it.get("unit_price", 0))
            if unit_price > 0:
                vd[vendor]["prices"].append(unit_price)
                vd[vendor]["dates"].append(inv_date)

    results = []
    for key, item_data in item_vendor_data.items():
        vendors = []
        for vname, vinfo in item_data["vendors"].items():
            if not vinfo["prices"]:
                continue
            latest_idx = vinfo["dates"].index(max(vinfo["dates"])) if vinfo["dates"] else 0
            vendors.append({
                "vendor": vname,
                "latest_price": round(vinfo["prices"][latest_idx], 2),
                "avg_price": round(sum(vinfo["prices"]) / len(vinfo["prices"]), 2),
                "min_price": round(min(vinfo["prices"]), 2),
                "max_price": round(max(vinfo["prices"]), 2),
                "purchase_count": len(vinfo["prices"]),
                "last_date": max(vinfo["dates"]) if vinfo["dates"] else "",
                "unit": vinfo["unit"],
            })
        if not vendors:
            continue
        vendors.sort(key=lambda v: v["latest_price"])
        cheapest = vendors[0]
        results.append({
            "item_name": item_data["name"],
            "vendors": vendors,
            "cheapest_vendor": cheapest["vendor"],
            "cheapest_price": cheapest["latest_price"],
            "vendor_count": len(vendors),
        })

    results.sort(key=lambda r: r["item_name"].lower())
    return {"results": results}


@router.get("/dashboard/drill-down/{category}")
async def dashboard_drill_down(category: str, date_from: str = "", date_to: str = "", user=Depends(get_user)):
    """Drill-down data for a spending/sales category with optional date filters."""
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)
    df = date_from or now.strftime("%Y-%m-01")
    dt = date_to or now.strftime("%Y-%m-%d")
    _approved = {"$or": [{"approval_status": {"$exists": False}}, {"approval_status": "approved"}]}

    if category == "raw_materials":
        purchases = await db.purchases.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
        filtered = [p for p in purchases if df <= p.get("invoice_date", "") <= dt]
        item_map = {}
        for p in filtered:
            vendor = p.get("supplier_name", "Unknown")
            supplier_id = p.get("supplier_id", "")
            inv_date = p.get("invoice_date", "")
            for it in p.get("items", []):
                name = it.get("raw_name", "Unknown")
                key = name.lower()
                if key not in item_map:
                    item_map[key] = {"name": name, "total_spent": 0, "vendors": {}}
                item_map[key]["total_spent"] += float(it.get("total", 0))
                vd = item_map[key]["vendors"]
                if vendor not in vd:
                    vd[vendor] = {"prices": [], "dates": [], "unit": it.get("unit", ""), "supplier_id": supplier_id}
                up = float(it.get("unit_price", 0))
                if up > 0:
                    vd[vendor]["prices"].append(up)
                    vd[vendor]["dates"].append(inv_date)
        items = []
        for key, im in item_map.items():
            vendors = []
            for vname, vi in im["vendors"].items():
                if not vi["prices"]:
                    continue
                latest_idx = vi["dates"].index(max(vi["dates"])) if vi["dates"] else 0
                vendors.append({
                    "vendor": vname, "supplier_id": vi["supplier_id"],
                    "latest_price": round(vi["prices"][latest_idx], 2),
                    "avg_price": round(sum(vi["prices"]) / len(vi["prices"]), 2),
                    "min_price": round(min(vi["prices"]), 2), "max_price": round(max(vi["prices"]), 2),
                    "purchase_count": len(vi["prices"]),
                    "last_date": max(vi["dates"]) if vi["dates"] else "", "unit": vi["unit"],
                })
            vendors.sort(key=lambda v: v["latest_price"])
            cheapest = vendors[0]["vendor"] if vendors else ""
            items.append({"item_name": im["name"], "total_spent": round(im["total_spent"], 2), "vendors": vendors, "cheapest_vendor": cheapest, "vendor_count": len(vendors)})
        items.sort(key=lambda x: -x["total_spent"])
        return {"category": "raw_materials", "items": items, "total": round(sum(i["total_spent"] for i in items), 2), "date_from": df, "date_to": dt}

    elif category == "salaries":
        sals = await db.salaries.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
        filtered = [s for s in sals if df <= s.get("payment_date", "") <= dt]
        employees = []
        for s in filtered:
            employees.append({
                "name": s.get("employee_name", "Unknown"), "position": s.get("position", ""),
                "amount": round(s.get("amount", 0), 2), "payment_date": s.get("payment_date", ""),
                "payment_method": s.get("payment_method", ""),
            })
        employees.sort(key=lambda e: -e["amount"])
        return {"category": "salaries", "employees": employees, "total": round(sum(e["amount"] for e in employees), 2), "date_from": df, "date_to": dt}

    elif category == "other":
        expenses = await db.other_expenses.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
        filtered = [e for e in expenses if df <= e.get("expense_date", "") <= dt]
        by_cat = {}
        for e in filtered:
            cat = e.get("category", "Uncategorized") or "Uncategorized"
            if cat not in by_cat:
                by_cat[cat] = {"items": [], "total": 0}
            by_cat[cat]["items"].append({
                "title": e.get("title", "Untitled"), "amount": round(e.get("amount", 0), 2),
                "expense_date": e.get("expense_date", ""), "vendor": e.get("vendor", ""), "notes": e.get("notes", ""),
            })
            by_cat[cat]["total"] += e.get("amount", 0)
        categories = []
        for cname, cdata in sorted(by_cat.items(), key=lambda x: -x[1]["total"]):
            cdata["items"].sort(key=lambda x: -x["amount"])
            categories.append({"category_name": cname, "total": round(cdata["total"], 2), "items": cdata["items"]})
        return {"category": "other", "categories": categories, "total": round(sum(c["total"] for c in categories), 2), "date_from": df, "date_to": dt}

    elif category == "sales":
        sales_data = await db.sales.find({"restaurant_id": rid, **_approved}, {"_id": 0}).to_list(10000)
        filtered = [s for s in sales_data if df <= s.get("report_date", "") <= dt]
        records = []
        for s in filtered:
            records.append({
                "id": s.get("id", ""), "report_date": s.get("report_date", ""),
                "total_sales": round(s.get("total_sales", 0), 2),
                "total_tax": round(s.get("total_tax", 0) or 0, 2),
                "total_tips": round(s.get("total_tips", 0) or 0, 2),
                "source": s.get("source", ""), "notes": s.get("notes", ""),
            })
        records.sort(key=lambda r: r["report_date"], reverse=True)
        return {"category": "sales", "records": records, "total": round(sum(r["total_sales"] for r in records), 2), "date_from": df, "date_to": dt}

    return {"error": "Invalid category. Use: raw_materials, salaries, other, sales"}
