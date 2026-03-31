from fastapi import APIRouter, Depends
import uuid, json
from datetime import datetime, timezone, timedelta

from core.database import db, LLM_KEY, logger
from core.auth import get_user
from core.models import ChatMessageIn
from services.alerts import generate_smart_alerts

router = APIRouter()


@router.get("/chat/messages")
async def get_chat_messages(user=Depends(get_user)):
    return await db.chat_messages.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(100)


@router.post("/chat")
async def send_chat(data: ChatMessageIn, user=Depends(get_user)):
    rid = user["restaurant_id"]
    user_msg = {"id": str(uuid.uuid4()), "user_id": user["id"], "restaurant_id": rid, "role": "user", "content": data.message, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.chat_messages.insert_one(user_msg)
    user_msg.pop("_id", None)

    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    sales = await db.sales.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    suppliers = await db.suppliers.find({"restaurant_id": rid}, {"_id": 0}).to_list(100)
    alerts = await db.alerts.find({"restaurant_id": rid}, {"_id": 0}).to_list(50)
    now = datetime.now(timezone.utc)

    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    year_start = now.strftime("%Y-01-01")
    prev_week_start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y-%m-%d")
    prev_week_end = (now - timedelta(days=now.weekday() + 1)).strftime("%Y-%m-%d")
    prev_month = now.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month.strftime("%Y-%m-01")
    prev_month_end = prev_month.strftime("%Y-%m-%d")

    def sum_p(df, dt=None):
        return sum(p["total"] for p in purchases if p.get("invoice_date", "") >= df and (not dt or p.get("invoice_date", "") <= dt))
    def sum_s(df, dt=None):
        return sum(s["total_sales"] for s in sales if s.get("report_date", "") >= df and (not dt or s.get("report_date", "") <= dt))

    item_prices = {}
    for p in sorted(purchases, key=lambda x: x.get("invoice_date", "")):
        for it in p.get("items", []):
            name = it.get("raw_name", "Unknown")
            price = float(it.get("unit_price", 0))
            if price > 0:
                item_prices.setdefault(name, []).append({"price": price, "date": p.get("invoice_date", "")})

    price_changes = []
    for name, prices in item_prices.items():
        if len(prices) >= 2:
            old, new = prices[-2]["price"], prices[-1]["price"]
            if old > 0:
                pct = ((new - old) / old) * 100
                if abs(pct) > 5:
                    price_changes.append({"item": name, "old": old, "new": new, "change_pct": round(pct, 1)})

    sup_spend = {}
    for p in purchases:
        n = p.get("supplier_name", "Unknown")
        sup_spend[n] = sup_spend.get(n, 0) + p["total"]
    top_suppliers = sorted(sup_spend.items(), key=lambda x: -x[1])[:5]

    item_spend = {}
    for p in purchases:
        for it in p.get("items", []):
            n = it.get("raw_name", "Unknown")
            item_spend[n] = item_spend.get(n, 0) + float(it.get("total", 0))
    top_items = sorted(item_spend.items(), key=lambda x: -x[1])[:10]

    smart_alerts = await generate_smart_alerts(rid)
    smart_alerts_ctx = ""
    if smart_alerts:
        sa_lines = []
        for sa in smart_alerts:
            t = sa.get("type", "")
            if t == "price_increase":
                sa_lines.append(f"- [PRICE INCREASE] {sa.get('item_name','')} went from ${sa.get('old_price',0):.2f} to ${sa.get('new_price',0):.2f} (+{sa.get('change_pct',0)}%) at {sa.get('vendor','')}")
            elif t == "cheaper_vendor":
                sa_lines.append(f"- [CHEAPER VENDOR] Save {sa.get('savings_pct',0)}% on {sa.get('item_name','')} -- switch from {sa.get('vendor','')} (${sa.get('current_price',0):.2f}) to {sa.get('cheaper_vendor','')} (${sa.get('cheaper_price',0):.2f})")
            elif t == "not_ordered":
                sa_lines.append(f"- [NOT ORDERED] {sa.get('item_name','')} not ordered in {sa.get('days_since',0)} days (last from {sa.get('vendor','')} at ${sa.get('last_price',0):.2f})")
        smart_alerts_ctx = "\nSMART ALERTS (active issues detected):\n" + "\n".join(sa_lines)

    context = f"""RESTAURANT FINANCIAL DATA (as of {now.strftime('%A, %B %d, %Y')}):

WEEKLY SNAPSHOT (This Week starting {week_start}):
- Purchases: ${sum_p(week_start):,.2f} | Sales: ${sum_s(week_start):,.2f}
- Gross Margin: ${sum_s(week_start) - sum_p(week_start):,.2f}

PREVIOUS WEEK ({prev_week_start} to {prev_week_end}):
- Purchases: ${sum_p(prev_week_start, prev_week_end):,.2f} | Sales: ${sum_s(prev_week_start, prev_week_end):,.2f}

MONTHLY SNAPSHOT (This Month starting {month_start}):
- Purchases: ${sum_p(month_start):,.2f} | Sales: ${sum_s(month_start):,.2f}
- Gross Margin: ${sum_s(month_start) - sum_p(month_start):,.2f}

PREVIOUS MONTH ({prev_month_start} to {prev_month_end}):
- Purchases: ${sum_p(prev_month_start, prev_month_end):,.2f} | Sales: ${sum_s(prev_month_start, prev_month_end):,.2f}

YEAR-TO-DATE ({year_start}):
- Total Purchases: ${sum_p(year_start):,.2f} | Total Sales: ${sum_s(year_start):,.2f}
- Net Margin: ${sum_s(year_start) - sum_p(year_start):,.2f}

ALL-TIME OVERVIEW:
- {len(purchases)} purchase invoices totaling ${sum(p['total'] for p in purchases):,.2f}
- {len(sales)} sales reports totaling ${sum(s['total_sales'] for s in sales):,.2f}
- {len(suppliers)} active suppliers

TOP SUPPLIERS BY SPEND: {json.dumps([{"name": n, "total": round(t, 2)} for n, t in top_suppliers])}
TOP ITEMS BY COST: {json.dumps([{"name": n, "total": round(t, 2)} for n, t in top_items])}
RECENT PRICE CHANGES (>5%): {json.dumps(price_changes[:10]) if price_changes else "None detected"}
ACTIVE ALERTS: {len([a for a in alerts if not a.get('is_read')])}
RECENT PURCHASES: {json.dumps([{'date': p['invoice_date'], 'supplier': p['supplier_name'], 'total': p['total']} for p in sorted(purchases, key=lambda x: x.get('invoice_date',''), reverse=True)[:8]])}
RECENT SALES: {json.dumps([{'date': s['report_date'], 'total': s['total_sales']} for s in sorted(sales, key=lambda x: x.get('report_date',''), reverse=True)[:8]])}
{smart_alerts_ctx}"""

    system_msg = f"""You are Restaurant Accountant AI, a senior financial analyst for restaurants. Follow these rules strictly:

1. STYLE: Be concise and data-driven. Lead with key numbers. Use short paragraphs and bullet points.
2. FORMAT: Use **bold** for key figures and metrics. Use bullet points for lists. Keep responses under 200 words unless the question requires detail.
3. PERIODS: Always reference specific time periods (this week, this month, YTD, etc.) when discussing finances. Compare to previous periods when relevant.
4. INSIGHTS: Don't just report numbers - provide brief actionable insights (e.g., "Spending is up 12% WoW - driven mainly by produce costs").
5. CURRENCY: Always format dollar amounts with commas (e.g., $1,234.56).
6. SMART ALERTS: You have access to a smart alerts system that detects low stock ingredients, cost increases, and profit margin drops. When users ask about stock, costs, margins, or alerts, reference the specific alert data provided. Be proactive about mentioning relevant alerts even if the user doesn't ask directly.
7. If you don't have enough data to answer precisely, say so honestly and suggest what data would help.

{context}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage as LlmUserMessage
        chat = LlmChat(api_key=LLM_KEY, session_id=f"chat-{user['id']}-{uuid.uuid4()}", system_message=system_msg).with_model("openai", "gpt-5.2")
        response = await chat.send_message(LlmUserMessage(text=data.message))
    except Exception as e:
        logger.error(f"Chat error: {e}")
        response = f"I'm having trouble connecting to the AI service right now. Please try again later."

    asst_msg = {"id": str(uuid.uuid4()), "user_id": user["id"], "restaurant_id": rid, "role": "assistant", "content": response, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.chat_messages.insert_one(asst_msg)
    asst_msg.pop("_id", None)
    return {"user_message": user_msg, "assistant_message": asst_msg}


@router.delete("/chat/messages")
async def clear_chat(user=Depends(get_user)):
    await db.chat_messages.delete_many({"user_id": user["id"]})
    return {"status": "cleared"}
