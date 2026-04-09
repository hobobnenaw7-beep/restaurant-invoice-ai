"""
Profit Dashboard APIs — Decision Engine Backend
All calculations are deterministic. AI is explanation-only.

Data sources: sysco_trusted_extractions + user_confirmed ONLY.
"""
import math
import re
import uuid
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from typing import Optional

from core.database import db, LLM_KEY, logger
from core.auth import get_user

router = APIRouter()

# ─── Helpers ───

def _normalize_item_key(raw_name: str) -> str:
    s = (raw_name or "").strip().upper()
    s = re.sub(r"^\d{4,}\s*", "", s)
    s = re.sub(r"[^A-Z0-9\s/]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _review_reason_label(item: dict) -> str:
    nfc = item.get("numeric_failure_category", "")
    cl = item.get("confidence_level", "")
    if cl == "review_with_memory_support":
        return "Memory Supported (Qty=1)"
    if nfc == "source_not_column_read":
        return "Qty Ambiguous"
    if nfc == "math_mismatch":
        return "Price Mismatch"
    if nfc == "qty_wrong":
        return "Qty Missing"
    if nfc == "price_wrong":
        return "Price Missing"
    if nfc == "both_wrong":
        return "Qty & Price Missing"
    if nfc == "total_missing":
        return "Total Missing"
    return "Review Required"


async def _load_trusted_items(restaurant_id: str = None) -> list:
    """Load all trusted + user-confirmed items. Clean data only."""
    items = []

    # 1. sysco_trusted_extractions
    docs = await db.sysco_trusted_extractions.find(
        {}, {"_id": 0}
    ).to_list(5000)
    for doc in docs:
        vendor = doc.get("detected_vendor", "Sysco")
        inv_date = doc.get("created_at", "")[:10]
        inv_number = doc.get("invoice_number", "")
        for it in doc.get("items", []):
            if it.get("confidence_level") not in ("trusted", "review_with_memory_support"):
                continue
            items.append({
                "raw_name": it.get("raw_name", ""),
                "item_code": it.get("item_code", ""),
                "quantity": float(it.get("quantity", 0) or 0),
                "unit_price": float(it.get("unit_price", 0) or 0),
                "total": float(it.get("total", 0) or 0),
                "vendor": vendor,
                "date": inv_date,
                "invoice_number": inv_number,
                "source": "trusted_extraction",
            })

    # 2. user_confirmed
    confirmed = await db.user_confirmed.find(
        {}, {"_id": 0}
    ).to_list(5000)
    for c in confirmed:
        items.append({
            "raw_name": c.get("raw_name", ""),
            "item_code": c.get("item_code", ""),
            "quantity": float(c.get("quantity", 0) or 0),
            "unit_price": float(c.get("unit_price", 0) or 0),
            "total": float(c.get("total", 0) or 0),
            "vendor": c.get("vendor", "Sysco"),
            "date": c.get("confirmed_at", "")[:10],
            "invoice_number": c.get("invoice_number", ""),
            "source": "user_confirmed",
        })

    return items


# ─── 1. Review Queue ───

@router.get("/profit/review-queue")
async def review_queue(user=Depends(get_user)):
    """Returns all items needing review with reason labels."""
    docs = await db.sysco_review_items.find(
        {"status": "review"}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)

    items = []
    for d in docs:
        items.append({
            "id": d.get("id", ""),
            "raw_name": d.get("raw_name", ""),
            "item_code": d.get("item_code", ""),
            "quantity": d.get("quantity", 0),
            "unit_price": d.get("unit_price", 0),
            "total": d.get("total", 0),
            "vendor": d.get("vendor", "Sysco"),
            "invoice_number": d.get("invoice_number", ""),
            "invoice_date": d.get("invoice_date", ""),
            "reason_label": d.get("reason_label", "Review Required"),
            "confidence_level": d.get("confidence_level", ""),
            "numeric_failure_category": d.get("numeric_failure_category", ""),
            "review_reason": d.get("review_reason", ""),
            "created_at": d.get("created_at", ""),
        })

    return {
        "items": items,
        "total_count": len(items),
        "reason_breakdown": _count_reasons(items),
    }


def _count_reasons(items: list) -> dict:
    counts = defaultdict(int)
    for it in items:
        counts[it["reason_label"]] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ─── 2. Confirm Item ───

class ConfirmItemRequest(BaseModel):
    item_id: str
    confirmed_quantity: Optional[float] = None
    confirmed_unit_price: Optional[float] = None
    notes: Optional[str] = None


@router.post("/profit/confirm-item")
async def confirm_item(data: ConfirmItemRequest, user=Depends(get_user)):
    """
    Confirms a review item → moves to user_confirmed.
    Triggers dashboard recomputation by changing data source.
    """
    review_item = await db.sysco_review_items.find_one(
        {"id": data.item_id, "status": "review"}, {"_id": 0}
    )
    if not review_item:
        return {"error": "Item not found or already confirmed"}

    qty = data.confirmed_quantity if data.confirmed_quantity is not None else review_item.get("quantity", 0)
    price = data.confirmed_unit_price if data.confirmed_unit_price is not None else review_item.get("unit_price", 0)
    total = round(qty * price, 2)

    confirmed_doc = {
        "id": str(uuid.uuid4()),
        "original_review_id": data.item_id,
        "raw_name": review_item.get("raw_name", ""),
        "item_code": review_item.get("item_code", ""),
        "quantity": qty,
        "unit_price": price,
        "total": total,
        "vendor": review_item.get("vendor", "Sysco"),
        "invoice_number": review_item.get("invoice_number", ""),
        "invoice_date": review_item.get("invoice_date", ""),
        "original_confidence": review_item.get("confidence_level", ""),
        "original_reason": review_item.get("reason_label", ""),
        "confirmed_by": user["id"],
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "notes": data.notes or "",
    }

    await db.user_confirmed.insert_one(confirmed_doc)
    confirmed_doc.pop("_id", None)

    # Update review item status
    await db.sysco_review_items.update_one(
        {"id": data.item_id},
        {"$set": {"status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Get updated queue count
    remaining = await db.sysco_review_items.count_documents({"status": "review"})

    return {
        "confirmed": confirmed_doc,
        "remaining_review_count": remaining,
        "message": f"Item confirmed. {remaining} items remaining in review queue.",
    }


# ─── 3. Profit Intelligence ───

@router.get("/profit/intelligence")
async def profit_intelligence(days: int = 30, user=Depends(get_user)):
    """
    Deterministic profit analytics:
    - Price trends per product (7d / 30d)
    - Vendor stability (variance)
    - Top cost drivers (% of total spend)
    """
    items = await _load_trusted_items()
    if not items:
        return {
            "price_trends": [],
            "vendor_stability": [],
            "cost_drivers": [],
            "total_spend": 0,
            "data_points": 0,
            "date_window": f"Last {days} days",
        }

    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    cutoff_90 = (now - timedelta(days=90)).strftime("%Y-%m-%d")

    # ── Price Trends ──
    product_prices = defaultdict(list)  # key -> [{price, date, qty, vendor}]
    for it in items:
        if it["unit_price"] <= 0 or it["date"] < cutoff_90:
            continue
        key = it["item_code"] if it["item_code"] else _normalize_item_key(it["raw_name"])
        if not key:
            continue
        product_prices[key].append({
            "price": it["unit_price"],
            "date": it["date"],
            "qty": it["quantity"],
            "total": it["total"],
            "vendor": it["vendor"],
            "raw_name": it["raw_name"],
        })

    price_trends = []
    for key, entries in product_prices.items():
        if len(entries) < 2:
            continue

        entries.sort(key=lambda x: x["date"])
        raw_name = entries[-1]["raw_name"]

        # 30d window
        entries_30d = [e for e in entries if e["date"] >= cutoff_30]
        entries_7d = [e for e in entries if e["date"] >= cutoff_7]
        all_prices = [e["price"] for e in entries]

        # Weighted average price
        def _weighted_avg(elist):
            total_qty = sum(e["qty"] for e in elist)
            if total_qty <= 0:
                return sum(e["price"] for e in elist) / len(elist)
            return sum(e["price"] * e["qty"] for e in elist) / total_qty

        current_price = entries[-1]["price"]
        avg_all = _weighted_avg(entries)

        trend_30d = None
        if len(entries_30d) >= 2:
            old_price_30 = _weighted_avg(entries_30d[:len(entries_30d)//2])
            new_price_30 = _weighted_avg(entries_30d[len(entries_30d)//2:])
            if old_price_30 > 0:
                trend_30d = round((new_price_30 - old_price_30) / old_price_30 * 100, 1)

        trend_7d = None
        if len(entries_7d) >= 2:
            old_price_7 = _weighted_avg(entries_7d[:len(entries_7d)//2])
            new_price_7 = _weighted_avg(entries_7d[len(entries_7d)//2:])
            if old_price_7 > 0:
                trend_7d = round((new_price_7 - old_price_7) / old_price_7 * 100, 1)

        total_spent = sum(e["total"] for e in entries)
        vendors = list(set(e["vendor"] for e in entries))

        price_trends.append({
            "product": raw_name,
            "item_code": key if key != _normalize_item_key(raw_name) else "",
            "current_price": round(current_price, 2),
            "avg_price": round(avg_all, 2),
            "min_price": round(min(all_prices), 2),
            "max_price": round(max(all_prices), 2),
            "trend_7d_pct": trend_7d,
            "trend_30d_pct": trend_30d,
            "data_points": len(entries),
            "total_spent": round(total_spent, 2),
            "vendors": vendors,
        })

    price_trends.sort(key=lambda x: abs(x.get("trend_30d_pct") or 0), reverse=True)

    # ── Vendor Stability ──
    vendor_product = defaultdict(lambda: defaultdict(list))
    for it in items:
        if it["unit_price"] <= 0:
            continue
        key = it["item_code"] if it["item_code"] else _normalize_item_key(it["raw_name"])
        if not key:
            continue
        vendor_product[it["vendor"]][key].append(it["unit_price"])

    vendor_stability = []
    for vendor, products in vendor_product.items():
        variances = []
        product_details = []
        for prod_key, prices in products.items():
            if len(prices) < 3:
                continue
            mean = sum(prices) / len(prices)
            variance = sum((p - mean) ** 2 for p in prices) / len(prices)
            std_dev = math.sqrt(variance)
            cv = (std_dev / mean * 100) if mean > 0 else 0  # Coefficient of variation
            variances.append(cv)
            product_details.append({
                "product_key": prod_key,
                "mean_price": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "cv_pct": round(cv, 1),
                "data_points": len(prices),
            })

        if not variances:
            continue

        avg_cv = sum(variances) / len(variances)
        label = "Stable" if avg_cv < 5 else "Moderate" if avg_cv < 15 else "Volatile"

        vendor_stability.append({
            "vendor": vendor,
            "stability_label": label,
            "avg_cv_pct": round(avg_cv, 1),
            "products_analyzed": len(product_details),
            "product_details": sorted(product_details, key=lambda x: -x["cv_pct"])[:5],
        })

    vendor_stability.sort(key=lambda x: -x["avg_cv_pct"])

    # ── Cost Drivers ──
    product_spend = defaultdict(lambda: {"total": 0, "qty": 0, "raw_name": "", "vendors": set()})
    total_spend = 0
    for it in items:
        key = it["item_code"] if it["item_code"] else _normalize_item_key(it["raw_name"])
        if not key:
            continue
        product_spend[key]["total"] += it["total"]
        product_spend[key]["qty"] += it["quantity"]
        product_spend[key]["raw_name"] = it["raw_name"]
        product_spend[key]["vendors"].add(it["vendor"])
        total_spend += it["total"]

    cost_drivers = []
    for key, info in product_spend.items():
        pct = (info["total"] / total_spend * 100) if total_spend > 0 else 0
        cost_drivers.append({
            "product": info["raw_name"],
            "item_code": key if key != _normalize_item_key(info["raw_name"]) else "",
            "total_spent": round(info["total"], 2),
            "total_qty": round(info["qty"], 1),
            "pct_of_spend": round(pct, 1),
            "vendor_count": len(info["vendors"]),
            "vendors": list(info["vendors"]),
        })

    cost_drivers.sort(key=lambda x: -x["total_spent"])

    return {
        "price_trends": price_trends[:20],
        "vendor_stability": vendor_stability,
        "cost_drivers": cost_drivers[:10],
        "total_spend": round(total_spend, 2),
        "data_points": len(items),
        "date_window": f"Last {days} days (extended to 90d for trends)",
    }


# ─── 4. Decision Engine Search ───

@router.get("/profit/search")
async def decision_search(q: str = "", user=Depends(get_user)):
    """
    Decision engine: NOT raw data lookup.
    Returns cheapest vendor, price trend, and suggested action.
    Only uses trusted + user-confirmed data.
    """
    if not q or len(q.strip()) < 2:
        return {"results": [], "query": q}

    query_lower = q.strip().lower()
    items = await _load_trusted_items()

    # Match items
    matching = defaultdict(list)
    for it in items:
        raw = it["raw_name"]
        if query_lower in raw.lower():
            key = it["item_code"] if it["item_code"] else _normalize_item_key(raw)
            if key:
                matching[key].append(it)

    results = []
    for key, entries in matching.items():
        entries.sort(key=lambda x: x["date"])
        raw_name = entries[-1]["raw_name"]

        # Group by vendor
        vendor_data = defaultdict(list)
        for e in entries:
            vendor_data[e["vendor"]].append(e)

        vendors = []
        for vname, ventries in vendor_data.items():
            prices = [e["unit_price"] for e in ventries]
            latest_price = ventries[-1]["unit_price"]
            avg_price = sum(prices) / len(prices)
            total_qty = sum(e["quantity"] for e in ventries)
            total_spent = sum(e["total"] for e in ventries)

            # Price trend for this vendor
            trend_pct = None
            if len(prices) >= 2:
                mid = len(prices) // 2
                old_avg = sum(prices[:mid]) / mid
                new_avg = sum(prices[mid:]) / (len(prices) - mid)
                if old_avg > 0:
                    trend_pct = round((new_avg - old_avg) / old_avg * 100, 1)

            # Stability
            if len(prices) >= 3:
                mean = sum(prices) / len(prices)
                var = sum((p - mean) ** 2 for p in prices) / len(prices)
                cv = (math.sqrt(var) / mean * 100) if mean > 0 else 0
                stability = "Stable" if cv < 5 else "Moderate" if cv < 15 else "Volatile"
            else:
                stability = "Insufficient Data"
                cv = 0

            vendors.append({
                "vendor": vname,
                "latest_price": round(latest_price, 2),
                "avg_price": round(avg_price, 2),
                "min_price": round(min(prices), 2),
                "max_price": round(max(prices), 2),
                "total_qty": round(total_qty, 1),
                "total_spent": round(total_spent, 2),
                "purchase_count": len(ventries),
                "last_date": ventries[-1]["date"],
                "trend_pct": trend_pct,
                "stability": stability,
            })

        vendors.sort(key=lambda v: v["latest_price"])
        cheapest = vendors[0] if vendors else None

        # Suggested action
        action = _suggest_action(vendors, entries)

        results.append({
            "product": raw_name,
            "item_code": key if key != _normalize_item_key(raw_name) else "",
            "vendors": vendors,
            "cheapest_vendor": cheapest["vendor"] if cheapest else "",
            "cheapest_price": cheapest["latest_price"] if cheapest else 0,
            "suggested_action": action,
            "total_data_points": len(entries),
        })

    results.sort(key=lambda r: -r.get("total_data_points", 0))
    return {"results": results, "query": q, "data_source": "trusted + user_confirmed only"}


def _suggest_action(vendors: list, entries: list) -> dict:
    """Generate deterministic suggested action based on data."""
    if not vendors:
        return {"action": "No Data", "reason": "No purchase history found", "confidence": "low"}

    cheapest = vendors[0]
    all_prices = [e["unit_price"] for e in entries]

    # Check if price is trending up
    if len(all_prices) >= 4:
        mid = len(all_prices) // 2
        old_avg = sum(all_prices[:mid]) / mid
        new_avg = sum(all_prices[mid:]) / (len(all_prices) - mid)
        trend_pct = (new_avg - old_avg) / old_avg * 100 if old_avg > 0 else 0
    else:
        trend_pct = 0

    # Decision logic
    if len(vendors) == 1:
        v = vendors[0]
        if v["stability"] == "Volatile":
            return {
                "action": "Monitor",
                "reason": f"Only 1 vendor ({v['vendor']}), price is volatile (CV={round(v.get('trend_pct', 0) or 0, 1)}%). Watch for alternatives.",
                "confidence": "medium",
            }
        return {
            "action": f"Buy from {v['vendor']}",
            "reason": f"Single vendor, {v['stability'].lower()} pricing at ${v['latest_price']:.2f}",
            "confidence": "medium",
        }

    if len(vendors) >= 2:
        second = vendors[1]
        savings_pct = ((second["latest_price"] - cheapest["latest_price"]) / second["latest_price"] * 100) if second["latest_price"] > 0 else 0

        if cheapest["stability"] == "Stable" and savings_pct >= 5:
            return {
                "action": f"Buy from {cheapest['vendor']}",
                "reason": f"Cheapest at ${cheapest['latest_price']:.2f} (saves {savings_pct:.0f}% vs {second['vendor']}). Stable pricing.",
                "confidence": "high",
            }
        elif cheapest["stability"] == "Volatile":
            return {
                "action": "Wait",
                "reason": f"{cheapest['vendor']} is cheapest (${cheapest['latest_price']:.2f}) but pricing is volatile. Consider {second['vendor']} at ${second['latest_price']:.2f} for stability.",
                "confidence": "medium",
            }
        elif trend_pct > 10:
            return {
                "action": f"Buy from {cheapest['vendor']} NOW",
                "reason": f"Price trending up {trend_pct:.0f}%. Lock in ${cheapest['latest_price']:.2f} from {cheapest['vendor']} before further increases.",
                "confidence": "high",
            }
        else:
            return {
                "action": f"Buy from {cheapest['vendor']}",
                "reason": f"Cheapest at ${cheapest['latest_price']:.2f}" + (f" (saves {savings_pct:.0f}% vs {second['vendor']})" if savings_pct > 1 else ""),
                "confidence": "high" if savings_pct > 3 else "medium",
            }

    return {"action": "Monitor", "reason": "Insufficient data for recommendation", "confidence": "low"}


# ─── 5. AI Insights (Explanation Layer Only) ───

class AIInsightsRequest(BaseModel):
    dashboard_context: Optional[dict] = None


@router.post("/profit/ai-insights")
async def ai_insights(data: AIInsightsRequest = Body(default=AIInsightsRequest()), user=Depends(get_user)):
    """
    AI explanation layer. Uses PRECOMPUTED data only.
    GPT-5.2 converts deterministic results into human-readable insights.
    System functions fully without AI.
    """
    # Step 1: Compute deterministic insights
    items = await _load_trusted_items()
    computed = _compute_deterministic_insights(items)

    # Step 2: Generate auto-insights (always available, no AI needed)
    auto_insights = computed["auto_insights"]

    # Step 3: Try AI explanation (graceful degradation)
    ai_explanation = None
    if LLM_KEY:
        try:
            ai_explanation = await _generate_ai_explanation(computed, data.dashboard_context or {})
        except Exception as e:
            logger.warning(f"AI insights generation failed: {e}")

    return {
        "auto_insights": auto_insights,
        "ai_explanation": ai_explanation,
        "computed_metrics": {
            "total_spend": computed["total_spend"],
            "total_items": computed["total_items"],
            "unique_products": computed["unique_products"],
            "top_vendor": computed["top_vendor"],
        },
        "ai_available": ai_explanation is not None,
    }


def _compute_deterministic_insights(items: list) -> dict:
    """Pure deterministic computation. No AI. No inference."""
    if not items:
        return {
            "total_spend": 0, "total_items": 0, "unique_products": 0,
            "top_vendor": None, "auto_insights": [],
        }

    total_spend = sum(it["total"] for it in items)

    # Product spend
    product_spend = defaultdict(lambda: {"total": 0, "prices": [], "qty": 0, "name": ""})
    vendor_spend = defaultdict(float)
    for it in items:
        key = it["item_code"] if it["item_code"] else _normalize_item_key(it["raw_name"])
        if not key:
            continue
        product_spend[key]["total"] += it["total"]
        product_spend[key]["prices"].append(it["unit_price"])
        product_spend[key]["qty"] += it["quantity"]
        product_spend[key]["name"] = it["raw_name"]
        vendor_spend[it["vendor"]] += it["total"]

    top_vendor = max(vendor_spend.items(), key=lambda x: x[1]) if vendor_spend else ("None", 0)

    # Auto-generate insights
    auto_insights = []

    # Insight: Price increases
    for key, info in product_spend.items():
        prices = info["prices"]
        if len(prices) >= 3:
            mid = len(prices) // 2
            old_avg = sum(prices[:mid]) / mid
            new_avg = sum(prices[mid:]) / (len(prices) - mid)
            if old_avg > 0:
                change_pct = (new_avg - old_avg) / old_avg * 100
                if change_pct > 5:
                    auto_insights.append({
                        "type": "price_increase",
                        "severity": "high" if change_pct > 15 else "medium",
                        "product": info["name"],
                        "message": f"Price up {change_pct:.0f}% on {info['name']} (${old_avg:.2f} → ${new_avg:.2f})",
                        "change_pct": round(change_pct, 1),
                        "old_price": round(old_avg, 2),
                        "new_price": round(new_avg, 2),
                    })
                elif change_pct < -5:
                    auto_insights.append({
                        "type": "price_decrease",
                        "severity": "low",
                        "product": info["name"],
                        "message": f"Price down {abs(change_pct):.0f}% on {info['name']} (${old_avg:.2f} → ${new_avg:.2f})",
                        "change_pct": round(change_pct, 1),
                        "old_price": round(old_avg, 2),
                        "new_price": round(new_avg, 2),
                    })

    # Insight: High-spend concentration
    sorted_products = sorted(product_spend.items(), key=lambda x: -x[1]["total"])
    if sorted_products and total_spend > 0:
        top_product = sorted_products[0]
        pct = top_product[1]["total"] / total_spend * 100
        if pct > 20:
            auto_insights.append({
                "type": "spend_concentration",
                "severity": "high" if pct > 40 else "medium",
                "product": top_product[1]["name"],
                "message": f"{top_product[1]['name']} accounts for {pct:.0f}% of total spend (${top_product[1]['total']:.2f})",
                "pct_of_spend": round(pct, 1),
                "total_spent": round(top_product[1]["total"], 2),
            })

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    auto_insights.sort(key=lambda x: sev_order.get(x.get("severity", "low"), 2))

    return {
        "total_spend": round(total_spend, 2),
        "total_items": len(items),
        "unique_products": len(product_spend),
        "top_vendor": {"name": top_vendor[0], "spend": round(top_vendor[1], 2)},
        "auto_insights": auto_insights[:10],
        "product_spend": {k: {"total": round(v["total"], 2), "name": v["name"]} for k, v in sorted_products[:10]},
        "vendor_spend": {k: round(v, 2) for k, v in sorted(vendor_spend.items(), key=lambda x: -x[1])},
    }


async def _generate_ai_explanation(computed: dict, dashboard_context: dict) -> str:
    """GPT-5.2 converts precomputed metrics into human-readable explanation. NEVER computes."""
    insights_text = "\n".join(f"- {ins['message']}" for ins in computed.get("auto_insights", []))
    vendor_text = "\n".join(f"- {k}: ${v}" for k, v in computed.get("vendor_spend", {}).items())
    product_text = "\n".join(f"- {v['name']}: ${v['total']}" for k, v in list(computed.get("product_spend", {}).items())[:5])

    context = f"""PRECOMPUTED FINANCIAL METRICS (DO NOT recalculate — explain only):

Total Spend: ${computed['total_spend']:,.2f}
Total Items: {computed['total_items']}
Unique Products: {computed['unique_products']}
Top Vendor: {computed['top_vendor']['name']} (${computed['top_vendor']['spend']:,.2f})

DETECTED INSIGHTS:
{insights_text or 'None detected'}

TOP PRODUCTS BY SPEND:
{product_text or 'No data'}

VENDOR BREAKDOWN:
{vendor_text or 'No data'}

DASHBOARD STATE: {json.dumps(dashboard_context) if dashboard_context else 'Not provided'}"""

    system_msg = """You are a restaurant profit advisor. Your job is to EXPLAIN precomputed financial data in plain language.

RULES:
1. NEVER compute, calculate, or infer any numbers. All numbers are provided to you.
2. Focus on actionable advice: what should the owner DO?
3. Be concise — max 3-4 short paragraphs.
4. Highlight the most critical insight first.
5. Use **bold** for key numbers.
6. If data is limited, say so honestly.
7. Always reference the specific data provided."""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage as LlmUserMessage
        chat = LlmChat(
            api_key=LLM_KEY,
            session_id=f"insights-{uuid.uuid4()}",
            system_message=system_msg,
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(
            LlmUserMessage(text=f"Explain these financial metrics to the restaurant owner. Focus on profit impact and recommended actions.\n\n{context}")
        )
        return response
    except Exception as e:
        logger.error(f"AI explanation failed: {e}")
        return None
