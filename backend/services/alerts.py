from datetime import datetime, timezone, timedelta

from core.database import db


async def generate_smart_alerts(rid):
    """Analyze real purchase history and generate actionable smart alerts."""
    now = datetime.now(timezone.utc)

    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    if not purchases:
        return []

    alerts = []

    # --- 1. ITEMS NOT ORDERED FOR A LONG TIME ---
    recent_cutoff = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    older_cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")

    item_last_purchase = {}
    for p in sorted(purchases, key=lambda x: x.get("invoice_date", "")):
        d = p.get("invoice_date", "")
        for it in p.get("items", []):
            name = it.get("raw_name", "").strip()
            if not name:
                continue
            item_last_purchase[name] = {
                "date": d,
                "vendor": p.get("supplier_name", ""),
                "price": float(it.get("unit_price", 0)),
            }

    for item_name, info in item_last_purchase.items():
        if info["date"] < recent_cutoff and info["date"] >= older_cutoff:
            days_ago = (now - datetime.strptime(info["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
            severity = "high" if days_ago > 21 else ("medium" if days_ago > 14 else "low")
            alerts.append({
                "type": "not_ordered",
                "severity": severity,
                "item_name": item_name,
                "vendor": info["vendor"],
                "days_since": days_ago,
                "last_date": info["date"],
                "last_price": info["price"],
            })

    not_ordered = [a for a in alerts if a["type"] == "not_ordered"]
    not_ordered.sort(key=lambda x: -x["days_since"])
    alerts = not_ordered[:8]

    # --- 2. PRICE INCREASES ---
    item_price_history = {}
    for p in sorted(purchases, key=lambda x: x.get("invoice_date", "")):
        d = p.get("invoice_date", "")
        vendor = p.get("supplier_name", "")
        for it in p.get("items", []):
            name = it.get("raw_name", "").strip()
            price = float(it.get("unit_price", 0))
            if name and price > 0:
                item_price_history.setdefault(name, []).append({"date": d, "price": price, "vendor": vendor})

    price_alerts = []
    for name, history in item_price_history.items():
        if len(history) < 2:
            continue
        latest = history[-1]
        previous = history[-2]
        if latest["price"] > previous["price"] and previous["price"] > 0:
            pct = ((latest["price"] - previous["price"]) / previous["price"]) * 100
            if pct > 3:
                severity = "high" if pct > 15 else ("medium" if pct > 8 else "low")
                price_alerts.append({
                    "type": "price_increase",
                    "severity": severity,
                    "item_name": name,
                    "vendor": latest["vendor"],
                    "old_price": previous["price"],
                    "new_price": latest["price"],
                    "change_pct": round(pct, 1),
                    "old_date": previous["date"],
                    "new_date": latest["date"],
                    "old_vendor": previous["vendor"],
                })

    price_alerts.sort(key=lambda x: -x["change_pct"])
    alerts += price_alerts[:8]

    # --- 3. CHEAPER VENDOR ALTERNATIVES ---
    item_vendor_prices = {}
    for p in sorted(purchases, key=lambda x: x.get("invoice_date", "")):
        d = p.get("invoice_date", "")
        vendor = p.get("supplier_name", "")
        for it in p.get("items", []):
            name = it.get("raw_name", "").strip()
            price = float(it.get("unit_price", 0))
            if name and price > 0:
                item_vendor_prices.setdefault(name, {})[vendor] = {"price": price, "date": d}

    cheaper_alerts = []
    for name, vendors in item_vendor_prices.items():
        if len(vendors) < 2:
            continue
        sorted_vendors = sorted(vendors.items(), key=lambda x: x[1]["price"])
        cheapest_vendor, cheapest_info = sorted_vendors[0]
        last_purchase = item_price_history.get(name, [])
        if not last_purchase:
            continue
        last = last_purchase[-1]
        if last["vendor"] != cheapest_vendor and last["price"] > cheapest_info["price"]:
            savings_pct = ((last["price"] - cheapest_info["price"]) / last["price"]) * 100
            if savings_pct > 3:
                severity = "high" if savings_pct > 20 else ("medium" if savings_pct > 10 else "low")
                cheaper_alerts.append({
                    "type": "cheaper_vendor",
                    "severity": severity,
                    "item_name": name,
                    "vendor": last["vendor"],
                    "current_price": last["price"],
                    "cheaper_vendor": cheapest_vendor,
                    "cheaper_price": cheapest_info["price"],
                    "savings_pct": round(savings_pct, 1),
                    "last_cheap_date": cheapest_info["date"],
                })

    cheaper_alerts.sort(key=lambda x: -x["savings_pct"])
    alerts += cheaper_alerts[:8]

    sev_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: sev_order.get(a["severity"], 9))

    return alerts
