from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, uuid, base64, json, re, io
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("JWT_SECRET", "fallback-secret")
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)
LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    restaurant_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class PurchaseCreate(BaseModel):
    supplier_name: str
    supplier_id: Optional[str] = None
    invoice_number: str
    invoice_date: str
    items: List[Dict[str, Any]]
    subtotal: float
    tax: float
    total: float

class PurchaseUpdate(BaseModel):
    supplier_name: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

class SalesCreate(BaseModel):
    report_date: str
    total_sales: float
    items: Optional[List[Dict[str, Any]]] = []

class SalesUpdate(BaseModel):
    report_date: Optional[str] = None
    total_sales: Optional[float] = None
    items: Optional[List[Dict[str, Any]]] = None

class SupplierCreate(BaseModel):
    name: str
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""

class CanonicalItemCreate(BaseModel):
    name: str
    category: Optional[str] = ""

class ItemAliasCreate(BaseModel):
    canonical_item_id: str
    alias_name: str

class ChatMessageIn(BaseModel):
    message: str

class SalaryCreate(BaseModel):
    employee_name: str
    position: Optional[str] = ""
    amount: float
    payment_date: str
    notes: Optional[str] = ""

class OtherExpenseCreate(BaseModel):
    title: str
    category: str
    amount: float
    expense_date: str
    notes: Optional[str] = ""

class SettingsUpdate(BaseModel):
    name: Optional[str] = None
    restaurant_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

# ==================== AUTH UTILITIES ====================

def hash_pw(pw):
    return pwd_context.hash(pw)

def verify_pw(pw, h):
    return pwd_context.verify(pw, h)

def make_token(uid):
    return jwt.encode({"user_id": uid, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)

async def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0})
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/register")
async def register(data: UserRegister):
    if await db.users.find_one({"email": data.email}):
        raise HTTPException(400, "Email already registered")
    rid = str(uuid.uuid4())
    await db.restaurants.insert_one({"id": rid, "name": data.restaurant_name, "address": "", "phone": "", "created_at": datetime.now(timezone.utc).isoformat()})
    uid = str(uuid.uuid4())
    await db.users.insert_one({"id": uid, "email": data.email, "password_hash": hash_pw(data.password), "name": data.name, "restaurant_id": rid, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"token": make_token(uid), "user": {"id": uid, "email": data.email, "name": data.name, "restaurant_id": rid, "restaurant_name": data.restaurant_name}}

@api_router.post("/auth/login")
async def login(data: UserLogin):
    u = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not u or not verify_pw(data.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    r = await db.restaurants.find_one({"id": u["restaurant_id"]}, {"_id": 0})
    return {"token": make_token(u["id"]), "user": {"id": u["id"], "email": u["email"], "name": u["name"], "restaurant_id": u["restaurant_id"], "restaurant_name": r["name"] if r else ""}}

@api_router.get("/auth/me")
async def me(user=Depends(get_user)):
    r = await db.restaurants.find_one({"id": user["restaurant_id"]}, {"_id": 0})
    return {"id": user["id"], "email": user["email"], "name": user["name"], "restaurant_id": user["restaurant_id"], "restaurant_name": r["name"] if r else ""}

# ==================== SMART ALERTS ENGINE ====================

async def _generate_smart_alerts(rid):
    """Analyze financial data and generate real-time smart alerts."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    prev_week_start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y-%m-%d")
    prev_week_end = (now - timedelta(days=now.weekday() + 1)).strftime("%Y-%m-%d")
    prev_month = now.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month.strftime("%Y-%m-01")
    prev_month_end = prev_month.strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    sales = await db.sales.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)

    alerts = []

    # --- 1. LOW STOCK: Items purchased regularly before but not in last 10 days ---
    recent_cutoff = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    older_cutoff = (now - timedelta(days=45)).strftime("%Y-%m-%d")

    # Items purchased in last 45 days but before 10 days ago
    older_items = set()
    recent_items = set()
    for p in purchases:
        d = p.get("invoice_date", "")
        for it in p.get("items", []):
            name = it.get("raw_name", "Unknown")
            if d >= older_cutoff and d < recent_cutoff:
                older_items.add(name)
            if d >= recent_cutoff:
                recent_items.add(name)

    missing_items = older_items - recent_items
    for item_name in sorted(missing_items)[:5]:
        # Find last purchase date
        last_date = ""
        for p in sorted(purchases, key=lambda x: x.get("invoice_date", ""), reverse=True):
            for it in p.get("items", []):
                if it.get("raw_name") == item_name:
                    last_date = p.get("invoice_date", "")
                    break
            if last_date:
                break
        days_ago = (now - datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days if last_date else 0
        alerts.append({
            "type": "low_stock",
            "severity": "high" if days_ago > 14 else "medium",
            "title": f"{item_name} — not ordered in {days_ago} days",
            "detail": f"Last purchased on {last_date}. This item was being ordered regularly before.",
            "item": item_name,
            "days_since": days_ago,
        })

    # --- 2. COST INCREASES: Compare avg prices this week vs previous week ---
    def avg_prices_in_range(plist, start, end):
        prices = {}
        for p in plist:
            d = p.get("invoice_date", "")
            if d >= start and d <= end:
                for it in p.get("items", []):
                    name = it.get("raw_name", "Unknown")
                    price = float(it.get("unit_price", 0))
                    if price > 0:
                        prices.setdefault(name, []).append(price)
        return {n: round(sum(v) / len(v), 2) for n, v in prices.items()}

    cur_prices = avg_prices_in_range(purchases, two_weeks_ago, today)
    prev_prices = avg_prices_in_range(purchases, (now - timedelta(days=42)).strftime("%Y-%m-%d"), two_weeks_ago)

    for name, cur_p in cur_prices.items():
        prev_p = prev_prices.get(name)
        if prev_p and prev_p > 0:
            pct = ((cur_p - prev_p) / prev_p) * 100
            if pct > 5:
                alerts.append({
                    "type": "cost_increase",
                    "severity": "high" if pct > 15 else "medium",
                    "title": f"{name} up {pct:.1f}%",
                    "detail": f"Price went from ${prev_p:.2f} to ${cur_p:.2f} per unit.",
                    "item": name,
                    "change_pct": round(pct, 1),
                    "old_price": prev_p,
                    "new_price": cur_p,
                })

    # Sort cost increases by severity
    cost_alerts = [a for a in alerts if a["type"] == "cost_increase"]
    cost_alerts.sort(key=lambda x: -x["change_pct"])
    alerts = [a for a in alerts if a["type"] != "cost_increase"] + cost_alerts[:5]

    # --- 3. PROFIT MARGIN DROP ---
    def sum_p(df, dt=None):
        return sum(p["total"] for p in purchases if p.get("invoice_date", "") >= df and (not dt or p.get("invoice_date", "") <= dt))
    def sum_s(df, dt=None):
        return sum(s["total_sales"] for s in sales if s.get("report_date", "") >= df and (not dt or s.get("report_date", "") <= dt))

    # Weekly margin comparison
    cur_week_s = sum_s(week_start)
    cur_week_p = sum_p(week_start)
    prev_week_s = sum_s(prev_week_start, prev_week_end)
    prev_week_p = sum_p(prev_week_start, prev_week_end)

    cur_week_margin = ((cur_week_s - cur_week_p) / cur_week_s * 100) if cur_week_s > 0 else 0
    prev_week_margin = ((prev_week_s - prev_week_p) / prev_week_s * 100) if prev_week_s > 0 else 0

    if prev_week_margin > 0 and cur_week_margin < prev_week_margin:
        margin_drop = prev_week_margin - cur_week_margin
        if margin_drop > 3:
            alerts.append({
                "type": "margin_drop",
                "severity": "high" if margin_drop > 10 else "medium",
                "title": f"Weekly margin dropped {margin_drop:.1f}pp",
                "detail": f"This week: {cur_week_margin:.1f}% vs last week: {prev_week_margin:.1f}%. Review cost drivers.",
                "current_margin": round(cur_week_margin, 1),
                "previous_margin": round(prev_week_margin, 1),
                "drop_pp": round(margin_drop, 1),
            })

    # Monthly margin comparison
    cur_month_s = sum_s(month_start)
    cur_month_p = sum_p(month_start)
    prev_month_s = sum_s(prev_month_start, prev_month_end)
    prev_month_p = sum_p(prev_month_start, prev_month_end)

    cur_month_margin = ((cur_month_s - cur_month_p) / cur_month_s * 100) if cur_month_s > 0 else 0
    prev_month_margin = ((prev_month_s - prev_month_p) / prev_month_s * 100) if prev_month_s > 0 else 0

    if prev_month_margin > 0 and cur_month_margin < prev_month_margin:
        margin_drop = prev_month_margin - cur_month_margin
        if margin_drop > 3:
            alerts.append({
                "type": "margin_drop",
                "severity": "high" if margin_drop > 10 else "medium",
                "title": f"Monthly margin dropped {margin_drop:.1f}pp",
                "detail": f"This month: {cur_month_margin:.1f}% vs last month: {prev_month_margin:.1f}%.",
                "current_margin": round(cur_month_margin, 1),
                "previous_margin": round(prev_month_margin, 1),
                "drop_pp": round(margin_drop, 1),
            })

    # Sort: high severity first, then by type priority
    type_order = {"margin_drop": 0, "cost_increase": 1, "low_stock": 2}
    alerts.sort(key=lambda a: (0 if a["severity"] == "high" else 1, type_order.get(a["type"], 9)))

    return alerts

# ==================== DASHBOARD ====================

@api_router.get("/dashboard/summary")
async def dashboard_summary(user=Depends(get_user)):
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    year_start = now.strftime("%Y-01-01")
    prev_week_start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y-%m-%d")
    prev_week_end = (now - timedelta(days=now.weekday() + 1)).strftime("%Y-%m-%d")
    prev_month = now.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month.strftime("%Y-%m-01")
    prev_month_end = prev_month.strftime("%Y-%m-%d")
    prev_year_start = f"{now.year - 1}-01-01"
    prev_year_end = f"{now.year - 1}-12-31"

    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    sales = await db.sales.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    salaries = await db.salaries.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)
    other_exp = await db.other_expenses.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)

    def sum_p(df, dt=None):
        return sum(p["total"] for p in purchases if p.get("invoice_date", "") >= df and (not dt or p.get("invoice_date", "") <= dt))
    def sum_s(df, dt=None):
        return sum(s["total_sales"] for s in sales if s.get("report_date", "") >= df and (not dt or s.get("report_date", "") <= dt))
    def sum_sal(df, dt=None):
        return sum(s["amount"] for s in salaries if s.get("payment_date", "") >= df and (not dt or s.get("payment_date", "") <= dt))
    def sum_oe(df, dt=None):
        return sum(e["amount"] for e in other_exp if e.get("expense_date", "") >= df and (not dt or e.get("expense_date", "") <= dt))

    def total_expenses(df, dt=None):
        return sum_p(df, dt) + sum_sal(df, dt) + sum_oe(df, dt)

    def profit(df, dt=None):
        return round(sum_s(df, dt) - total_expenses(df, dt), 2)

    item_spend = {}
    for p in purchases:
        for it in p.get("items", []):
            n = it.get("raw_name", "Unknown")
            item_spend[n] = item_spend.get(n, 0) + float(it.get("total", 0))
    top_items = [{"name": n, "total": round(t, 2)} for n, t in sorted(item_spend.items(), key=lambda x: -x[1])[:5]]

    sup_spend = {}
    for p in purchases:
        n = p.get("supplier_name", "Unknown")
        sup_spend[n] = sup_spend.get(n, 0) + p["total"]
    top_suppliers = [{"name": n, "total": round(t, 2)} for n, t in sorted(sup_spend.items(), key=lambda x: -x[1])[:5]]

    weekly_trends = []
    for i in range(7, -1, -1):
        ws = (now - timedelta(weeks=i, days=now.weekday())).strftime("%Y-%m-%d")
        we = (now - timedelta(weeks=i, days=now.weekday() - 6)).strftime("%Y-%m-%d")
        weekly_trends.append({"week": f"W{8-i}", "purchases": round(sum_p(ws, we), 2), "sales": round(sum_s(ws, we), 2)})

    alerts = await db.alerts.find({"restaurant_id": rid}, {"_id": 0}).sort("created_at", -1).to_list(10)
    smart_alerts = await _generate_smart_alerts(rid)
    price_alerts = await db.alerts.find(
        {"restaurant_id": rid, "type": "price_increase"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    return {
        "today_sales": round(sum_s(today), 2), "today_purchases": round(sum_p(today), 2),
        "week_sales": round(sum_s(week_start), 2), "week_purchases": round(sum_p(week_start), 2),
        "month_sales": round(sum_s(month_start), 2), "month_purchases": round(sum_p(month_start), 2),
        "prev_week_sales": round(sum_s(prev_week_start, prev_week_end), 2),
        "prev_week_purchases": round(sum_p(prev_week_start, prev_week_end), 2),
        "prev_month_sales": round(sum_s(prev_month_start, prev_month_end), 2),
        "prev_month_purchases": round(sum_p(prev_month_start, prev_month_end), 2),
        "month_raw_materials": round(sum_p(month_start), 2),
        "month_salaries": round(sum_sal(month_start), 2),
        "month_other_expenses": round(sum_oe(month_start), 2),
        "prev_month_raw_materials": round(sum_p(prev_month_start, prev_month_end), 2),
        "prev_month_salaries": round(sum_sal(prev_month_start, prev_month_end), 2),
        "prev_month_other_expenses": round(sum_oe(prev_month_start, prev_month_end), 2),
        "top_items": top_items, "top_suppliers": top_suppliers,
        "weekly_trends": weekly_trends, "alerts": alerts,
        "smart_alerts": smart_alerts,
        "price_alerts": price_alerts,
        "daily_profit": profit(today),
        "weekly_profit": profit(week_start),
        "monthly_profit": profit(month_start),
        "yearly_profit": profit(year_start),
        "prev_weekly_profit": profit(prev_week_start, prev_week_end),
        "prev_monthly_profit": profit(prev_month_start, prev_month_end),
        "prev_yearly_profit": profit(prev_year_start, prev_year_end),
        "daily_expenses": round(total_expenses(today), 2),
        "weekly_expenses": round(total_expenses(week_start), 2),
        "monthly_expenses": round(total_expenses(month_start), 2),
        "yearly_expenses": round(total_expenses(year_start), 2),
        "yearly_sales": round(sum_s(year_start), 2),
    }

# ==================== UPLOAD / EXTRACT ====================

@api_router.post("/upload/parse-excel")
async def parse_excel(file: UploadFile = File(...), document_type: str = Form("purchase_invoice"), user=Depends(get_user)):
    """Parse Excel/CSV files and extract purchase or sales data."""
    import openpyxl, csv as csv_mod
    try:
        content = await file.read()
        fname = (file.filename or "").lower()
        rows = []

        if fname.endswith('.csv'):
            text = content.decode('utf-8', errors='replace')
            reader = csv_mod.reader(text.strip().splitlines())
            for r in reader:
                rows.append(r)
        elif fname.endswith('.xlsx') or fname.endswith('.xls'):
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else '' for c in r])
            wb.close()
        else:
            raise HTTPException(400, "Unsupported file type. Use .xlsx, .xls, or .csv")

        if len(rows) < 2:
            raise HTTPException(400, "File has no data rows")

        # Normalize headers
        headers_raw = [str(h).strip().lower().replace(' ', '_') for h in rows[0]]
        col_map = {}
        for i, h in enumerate(headers_raw):
            for key, aliases in {
                'supplier': ['supplier', 'supplier_name', 'vendor', 'vendor_name', 'from'],
                'date': ['date', 'invoice_date', 'inv_date', 'purchase_date', 'order_date', 'report_date'],
                'invoice_number': ['invoice', 'invoice_number', 'inv_no', 'invoice_no', 'inv_number', 'invoice#', 'inv#', 'ref', 'reference'],
                'item_name': ['item', 'item_name', 'product', 'product_name', 'description', 'raw_name', 'name', 'menu_item', 'ingredient'],
                'quantity': ['quantity', 'qty', 'count'],
                'unit': ['unit', 'uom', 'measure', 'unit_of_measure'],
                'unit_price': ['price', 'unit_price', 'unit_cost', 'cost', 'rate'],
                'total': ['total', 'line_total', 'subtotal', 'ext_price', 'extended_price', 'revenue', 'amount'],
            }.items():
                if h in aliases and key not in col_map:
                    col_map[key] = i

        data_rows = rows[1:]

        def safe_float(val):
            try:
                s = str(val).replace('$', '').replace(',', '').strip()
                return float(s) if s else 0
            except (ValueError, TypeError):
                return 0

        def safe_date(val):
            s = str(val).strip()
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(s[:10], fmt).strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    continue
            return datetime.now(timezone.utc).strftime('%Y-%m-%d')

        if document_type == "purchase_invoice":
            # Group by supplier + date + invoice to create purchases
            items_parsed = []
            for row in data_rows:
                if len(row) <= max(col_map.values(), default=0):
                    row.extend([''] * (max(col_map.values(), default=0) + 1 - len(row)))
                item_name = row[col_map['item_name']].strip() if 'item_name' in col_map else ''
                if not item_name:
                    continue
                qty = safe_float(row[col_map['quantity']]) if 'quantity' in col_map else 1
                up = safe_float(row[col_map['unit_price']]) if 'unit_price' in col_map else 0
                tot = safe_float(row[col_map['total']]) if 'total' in col_map else (qty * up)
                if tot == 0 and qty > 0 and up > 0:
                    tot = qty * up
                if up == 0 and tot > 0 and qty > 0:
                    up = tot / qty

                items_parsed.append({
                    "supplier": row[col_map['supplier']].strip() if 'supplier' in col_map else '',
                    "date": safe_date(row[col_map['date']]) if 'date' in col_map else datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    "invoice_number": row[col_map['invoice_number']].strip() if 'invoice_number' in col_map else '',
                    "raw_name": item_name,
                    "quantity": qty,
                    "unit": row[col_map['unit']].strip() if 'unit' in col_map else '',
                    "unit_price": round(up, 2),
                    "total": round(tot, 2),
                })

            # Group into purchases by supplier+date+invoice
            groups = {}
            for it in items_parsed:
                key = (it['supplier'] or 'Unknown', it['date'], it['invoice_number'])
                groups.setdefault(key, []).append(it)

            if not groups and items_parsed:
                groups[('Unknown', items_parsed[0]['date'], '')] = items_parsed

            # If only one group or no grouping columns, return single purchase
            if len(groups) <= 1:
                all_items = [it for items in groups.values() for it in items]
                first = all_items[0] if all_items else {}
                subtotal = round(sum(it['total'] for it in all_items), 2)
                return {"extracted_data": {
                    "supplier_name": first.get('supplier', ''),
                    "invoice_date": first.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')),
                    "invoice_number": first.get('invoice_number', ''),
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "unit": it['unit'], "unit_price": it['unit_price'], "total": it['total']} for it in all_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(all_items)}
            else:
                # Multiple purchases - return first one and indicate more
                first_key = list(groups.keys())[0]
                first_items = groups[first_key]
                subtotal = round(sum(it['total'] for it in first_items), 2)
                return {"extracted_data": {
                    "supplier_name": first_key[0],
                    "invoice_date": first_key[1],
                    "invoice_number": first_key[2],
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "unit": it['unit'], "unit_price": it['unit_price'], "total": it['total']} for it in first_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(items_parsed), "purchase_groups": len(groups),
                   "message": f"Found {len(groups)} purchases with {len(items_parsed)} total items. Showing the first purchase."}
        else:
            # Sales report
            items_parsed = []
            for row in data_rows:
                if len(row) <= max(col_map.values(), default=0):
                    row.extend([''] * (max(col_map.values(), default=0) + 1 - len(row)))
                item_name = row[col_map['item_name']].strip() if 'item_name' in col_map else ''
                if not item_name:
                    continue
                qty = safe_float(row[col_map['quantity']]) if 'quantity' in col_map else 1
                revenue = safe_float(row[col_map['total']]) if 'total' in col_map else 0
                items_parsed.append({"menu_item": item_name, "quantity": qty, "revenue": round(revenue, 2)})

            total_sales = round(sum(it['revenue'] for it in items_parsed), 2)
            report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if 'date' in col_map and data_rows:
                report_date = safe_date(data_rows[0][col_map['date']])

            return {"extracted_data": {
                "report_date": report_date,
                "total_sales": total_sales,
                "items": items_parsed,
            }, "document_type": document_type, "row_count": len(items_parsed)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excel parse error: {e}")
        raise HTTPException(500, f"Failed to parse file: {str(e)}")

@api_router.post("/upload/extract")
async def extract_document(file: UploadFile = File(...), document_type: str = Form(...), user=Depends(get_user)):
    try:
        content = await file.read()
        mime = file.content_type or "image/jpeg"

        if "pdf" in mime.lower():
            import fitz
            pdf_doc = fitz.open(stream=content, filetype="pdf")
            page = pdf_doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            pdf_doc.close()
            b64 = base64.b64encode(img_bytes).decode()
        else:
            b64 = base64.b64encode(content).decode()

        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        if document_type == "purchase_invoice":
            prompt = """Extract from this purchase invoice image. Return ONLY valid JSON:
{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{"raw_name":"","quantity":0,"unit":"","unit_price":0,"total":0}],"subtotal":0,"tax":0,"total":0}
If a field is unreadable, use reasonable defaults. Return ONLY the JSON object."""
        else:
            prompt = """Extract from this sales report image. Return ONLY valid JSON:
{"report_date":"YYYY-MM-DD","total_sales":0,"items":[{"menu_item":"","quantity":0,"revenue":0}]}
If a field is unreadable, use reasonable defaults. Return ONLY the JSON object."""

        chat = LlmChat(api_key=LLM_KEY, session_id=f"extract-{uuid.uuid4()}", system_message="You are an expert at reading restaurant documents. Extract data accurately and return valid JSON only.").with_model("openai", "gpt-5.2")
        image_content = ImageContent(image_base64=b64)
        user_msg = UserMessage(text=prompt, file_contents=[image_content])
        response = await chat.send_message(user_msg)

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            extracted = json.loads(json_match.group())
        else:
            extracted = {"error": "Could not parse extraction results"}

        return {"extracted_data": extracted, "document_type": document_type}
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(500, f"Extraction failed: {str(e)}")

# ==================== PURCHASES CRUD ====================

@api_router.get("/purchases")
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
    return await db.purchases.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)

@api_router.get("/purchases/{pid}")
async def get_purchase(pid: str, user=Depends(get_user)):
    p = await db.purchases.find_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    return p

@api_router.post("/purchases")
async def create_purchase(data: PurchaseCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.purchases.insert_one(doc)
    doc.pop("_id", None)

    # --- Generate price alerts for items with price increases ---
    rid = user["restaurant_id"]
    existing = await db.purchases.find(
        {"restaurant_id": rid, "id": {"$ne": doc["id"]}},
        {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}
    ).to_list(10000)

    # Build alias mapping for fuzzy matching
    canon_items = await db.canonical_items.find({"restaurant_id": rid}, {"_id": 0}).to_list(1000)
    alias_list = await db.item_aliases.find({"restaurant_id": rid}, {"_id": 0}).to_list(5000)
    name_to_group = {}
    for c in canon_items:
        group_key = c["name"].lower()
        name_to_group[group_key] = group_key
    for a in alias_list:
        for c in canon_items:
            if c["id"] == a["canonical_item_id"]:
                name_to_group[a["alias_name"].lower()] = c["name"].lower()
                break

    for item in doc.get("items", []):
        raw = item.get("raw_name", "").strip()
        new_price = float(item.get("unit_price", 0))
        if not raw or new_price <= 0:
            continue

        # Determine the group of names to match against
        group_key = name_to_group.get(raw.lower(), raw.lower())
        match_names = {group_key}
        for k, v in name_to_group.items():
            if v == group_key:
                match_names.add(k)
        match_names.add(raw.lower())

        # Find the most recent previous price for this item across all purchases
        prev_record = None
        for p in sorted(existing, key=lambda x: x.get("invoice_date", ""), reverse=True):
            for it in p.get("items", []):
                if it.get("raw_name", "").lower() in match_names and float(it.get("unit_price", 0)) > 0:
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

    return doc

@api_router.put("/purchases/{pid}")
async def update_purchase(pid: str, data: PurchaseUpdate, user=Depends(get_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    result = await db.purchases.update_one({"id": pid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(404, "Not found")
    return await db.purchases.find_one({"id": pid}, {"_id": 0})

@api_router.delete("/purchases/{pid}")
async def delete_purchase(pid: str, user=Depends(get_user)):
    result = await db.purchases.delete_one({"id": pid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

# ==================== SALARIES CRUD ====================

@api_router.get("/salaries")
async def list_salaries(user=Depends(get_user), date_from: str = "", date_to: str = "", sort_by: str = "payment_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if date_from:
        query.setdefault("payment_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("payment_date", {})["$lte"] = date_to
    return await db.salaries.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)

@api_router.post("/salaries")
async def create_salary(data: SalaryCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.salaries.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/salaries/{sid}")
async def delete_salary(sid: str, user=Depends(get_user)):
    result = await db.salaries.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

# ==================== OTHER EXPENSES CRUD ====================

@api_router.get("/other-expenses")
async def list_other_expenses(user=Depends(get_user), category: str = "", date_from: str = "", date_to: str = "", sort_by: str = "expense_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if category:
        query["category"] = category
    if date_from:
        query.setdefault("expense_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("expense_date", {})["$lte"] = date_to
    return await db.other_expenses.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)

@api_router.post("/other-expenses")
async def create_other_expense(data: OtherExpenseCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.other_expenses.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/other-expenses/{eid}")
async def delete_other_expense(eid: str, user=Depends(get_user)):
    result = await db.other_expenses.delete_one({"id": eid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

# ==================== SALES CRUD ====================

@api_router.get("/sales")
async def list_sales(user=Depends(get_user), search: str = "", date_from: str = "", date_to: str = "", sort_by: str = "report_date", sort_order: str = "desc"):
    query = {"restaurant_id": user["restaurant_id"]}
    if date_from:
        query.setdefault("report_date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("report_date", {})["$lte"] = date_to
    return await db.sales.find(query, {"_id": 0}).sort(sort_by, -1 if sort_order == "desc" else 1).to_list(1000)

@api_router.get("/sales/{sid}")
async def get_sale(sid: str, user=Depends(get_user)):
    s = await db.sales.find_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    return s

@api_router.post("/sales")
async def create_sale(data: SalesCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.sales.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/sales/{sid}")
async def update_sale(sid: str, data: SalesUpdate, user=Depends(get_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data")
    await db.sales.update_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"$set": update_data})
    return await db.sales.find_one({"id": sid}, {"_id": 0})

@api_router.delete("/sales/{sid}")
async def delete_sale(sid: str, user=Depends(get_user)):
    result = await db.sales.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

# ==================== SUPPLIERS CRUD ====================

@api_router.get("/suppliers")
async def list_suppliers(user=Depends(get_user), search: str = ""):
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    suppliers = await db.suppliers.find(query, {"_id": 0}).to_list(1000)
    purchases = await db.purchases.find({"restaurant_id": user["restaurant_id"]}, {"_id": 0, "supplier_name": 1, "total": 1}).to_list(10000)
    for s in suppliers:
        s["total_spending"] = round(sum(p["total"] for p in purchases if p.get("supplier_name") == s["name"]), 2)
        s["invoice_count"] = sum(1 for p in purchases if p.get("supplier_name") == s["name"])
    return suppliers

@api_router.post("/suppliers")
async def create_supplier(data: SupplierCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/suppliers/{sid}")
async def update_supplier(sid: str, data: SupplierCreate, user=Depends(get_user)):
    await db.suppliers.update_one({"id": sid, "restaurant_id": user["restaurant_id"]}, {"$set": data.model_dump()})
    return await db.suppliers.find_one({"id": sid}, {"_id": 0})

@api_router.delete("/suppliers/{sid}")
async def delete_supplier(sid: str, user=Depends(get_user)):
    result = await db.suppliers.delete_one({"id": sid, "restaurant_id": user["restaurant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

# ==================== ITEMS & ALIASES ====================

@api_router.get("/items")
async def list_items(user=Depends(get_user), search: str = ""):
    query = {"restaurant_id": user["restaurant_id"]}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    items = await db.canonical_items.find(query, {"_id": 0}).to_list(1000)
    for item in items:
        item["aliases"] = await db.item_aliases.find({"canonical_item_id": item["id"], "restaurant_id": user["restaurant_id"]}, {"_id": 0}).to_list(100)
    return items

@api_router.post("/items")
async def create_item(data: CanonicalItemCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.canonical_items.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/items/{iid}")
async def update_item(iid: str, data: CanonicalItemCreate, user=Depends(get_user)):
    await db.canonical_items.update_one({"id": iid, "restaurant_id": user["restaurant_id"]}, {"$set": data.model_dump()})
    return await db.canonical_items.find_one({"id": iid}, {"_id": 0})

@api_router.delete("/items/{iid}")
async def delete_item(iid: str, user=Depends(get_user)):
    await db.canonical_items.delete_one({"id": iid, "restaurant_id": user["restaurant_id"]})
    await db.item_aliases.delete_many({"canonical_item_id": iid})
    return {"status": "deleted"}

@api_router.post("/aliases")
async def create_alias(data: ItemAliasCreate, user=Depends(get_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["restaurant_id"] = user["restaurant_id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.item_aliases.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/aliases/{aid}")
async def delete_alias(aid: str, user=Depends(get_user)):
    await db.item_aliases.delete_one({"id": aid, "restaurant_id": user["restaurant_id"]})
    return {"status": "deleted"}

# ==================== ITEM PRICE HISTORY ====================

@api_router.get("/items/{item_id}/price-history")
async def item_price_history(item_id: str, user=Depends(get_user)):
    """Get price history for a canonical item by scanning all purchases matching its name + aliases."""
    rid = user["restaurant_id"]
    item = await db.canonical_items.find_one({"id": item_id, "restaurant_id": rid}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")

    # Collect all names to match: canonical name + all aliases
    names = {item["name"].lower()}
    aliases = await db.item_aliases.find({"canonical_item_id": item_id, "restaurant_id": rid}, {"_id": 0}).to_list(200)
    for a in aliases:
        names.add(a["alias_name"].lower())

    # Scan purchases for matching line items
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}).to_list(10000)

    records = []
    for p in purchases:
        vendor = p.get("supplier_name", "Unknown")
        date = p.get("invoice_date", "")
        for it in p.get("items", []):
            raw = it.get("raw_name", "").lower()
            if raw in names:
                records.append({
                    "vendor": vendor,
                    "date": date,
                    "unit_price": round(float(it.get("unit_price", 0)), 2),
                    "quantity": float(it.get("quantity", 0)),
                    "unit": it.get("unit", ""),
                    "raw_name": it.get("raw_name", ""),
                })

    records.sort(key=lambda x: x["date"])

    # Build trend data: average price per date
    date_prices = {}
    for r in records:
        date_prices.setdefault(r["date"], []).append(r["unit_price"])
    trend = [{"date": d, "avg_price": round(sum(ps) / len(ps), 2)} for d, ps in sorted(date_prices.items())]

    # Summary stats
    all_prices = [r["unit_price"] for r in records if r["unit_price"] > 0]
    summary = {
        "total_records": len(records),
        "avg_price": round(sum(all_prices) / len(all_prices), 2) if all_prices else 0,
        "min_price": round(min(all_prices), 2) if all_prices else 0,
        "max_price": round(max(all_prices), 2) if all_prices else 0,
        "vendors": list(set(r["vendor"] for r in records)),
    }

    return {"item_name": item["name"], "records": records, "trend": trend, "summary": summary}

# ==================== REPORTS ====================

def _parse_report_dates(report_type, date, now):
    if report_type == "weekly":
        start = datetime.strptime(date, "%Y-%m-%d") if date else now - timedelta(days=now.weekday())
        start_str = start.strftime("%Y-%m-%d")
        end_str = (start + timedelta(days=6)).strftime("%Y-%m-%d")
        # previous period
        prev_start = (start - timedelta(days=7)).strftime("%Y-%m-%d")
        prev_end = (start - timedelta(days=1)).strftime("%Y-%m-%d")
    elif report_type == "monthly":
        start = datetime.strptime(date[:7] + "-01", "%Y-%m-%d") if date else now.replace(day=1)
        start_str = start.strftime("%Y-%m-%d")
        end = (start.replace(month=start.month + 1, day=1) if start.month < 12 else start.replace(year=start.year + 1, month=1, day=1)) - timedelta(days=1)
        end_str = end.strftime("%Y-%m-%d")
        prev_month = start - timedelta(days=1)
        prev_start = prev_month.replace(day=1).strftime("%Y-%m-%d")
        prev_end = prev_month.strftime("%Y-%m-%d")
    else:
        year = int(date) if date else now.year
        start_str, end_str = f"{year}-01-01", f"{year}-12-31"
        prev_start, prev_end = f"{year-1}-01-01", f"{year-1}-12-31"
    return start_str, end_str, prev_start, prev_end

async def _build_report(rid, report_type, date):
    now = datetime.now(timezone.utc)
    start_str, end_str, prev_start, prev_end = _parse_report_dates(report_type, date, now)

    purchases = await db.purchases.find({"restaurant_id": rid, "invoice_date": {"$gte": start_str, "$lte": end_str}}, {"_id": 0}).to_list(10000)
    sales = await db.sales.find({"restaurant_id": rid, "report_date": {"$gte": start_str, "$lte": end_str}}, {"_id": 0}).to_list(10000)
    prev_purchases = await db.purchases.find({"restaurant_id": rid, "invoice_date": {"$gte": prev_start, "$lte": prev_end}}, {"_id": 0}).to_list(10000)
    prev_sales = await db.sales.find({"restaurant_id": rid, "report_date": {"$gte": prev_start, "$lte": prev_end}}, {"_id": 0}).to_list(10000)

    total_p = round(sum(p["total"] for p in purchases), 2)
    total_s = round(sum(s["total_sales"] for s in sales), 2)
    prev_p = round(sum(p["total"] for p in prev_purchases), 2)
    prev_s = round(sum(s["total_sales"] for s in prev_sales), 2)

    sup_spend = {}
    sup_invoice_count = {}
    for p in purchases:
        n = p.get("supplier_name", "Unknown")
        sup_spend[n] = sup_spend.get(n, 0) + p["total"]
        sup_invoice_count[n] = sup_invoice_count.get(n, 0) + 1

    item_spend = {}
    for p in purchases:
        for it in p.get("items", []):
            n = it.get("raw_name", "Unknown")
            item_spend[n] = item_spend.get(n, 0) + float(it.get("total", 0))

    # Price changes: compare avg unit_price in current vs previous period
    def item_prices(plist):
        prices = {}
        for p in plist:
            for it in p.get("items", []):
                n = it.get("raw_name", "Unknown")
                price = float(it.get("unit_price", 0))
                qty = float(it.get("quantity", 0))
                if price > 0:
                    prices.setdefault(n, []).append(price)
        return {n: round(sum(v)/len(v), 2) for n, v in prices.items()}

    cur_prices = item_prices(purchases)
    prev_prices = item_prices(prev_purchases)
    price_changes = []
    for name, cur_p in cur_prices.items():
        prev_p_val = prev_prices.get(name)
        if prev_p_val and prev_p_val > 0:
            pct = round(((cur_p - prev_p_val) / prev_p_val) * 100, 1)
            if abs(pct) > 0:
                price_changes.append({"item": name, "current_price": cur_p, "previous_price": prev_p_val, "change_pct": pct})
    price_changes.sort(key=lambda x: -abs(x["change_pct"]))

    daily = {}
    for p in purchases:
        d = p.get("invoice_date", "")
        daily.setdefault(d, {"date": d, "purchases": 0, "sales": 0})
        daily[d]["purchases"] += p["total"]
    for s in sales:
        d = s.get("report_date", "")
        daily.setdefault(d, {"date": d, "purchases": 0, "sales": 0})
        daily[d]["sales"] += s["total_sales"]

    alerts = await db.alerts.find({"restaurant_id": rid}, {"_id": 0}).to_list(100)

    return {
        "report_type": report_type, "date_range": {"start": start_str, "end": end_str},
        "prev_date_range": {"start": prev_start, "end": prev_end},
        "total_purchases": total_p, "total_sales": total_s, "profit": round(total_s - total_p, 2),
        "prev_purchases": prev_p, "prev_sales": prev_s, "prev_profit": round(prev_s - prev_p, 2),
        "margin_pct": round((total_s - total_p) / total_s * 100, 1) if total_s > 0 else 0,
        "spending_by_supplier": [{"name": n, "total": round(t, 2), "invoices": sup_invoice_count.get(n, 0)} for n, t in sorted(sup_spend.items(), key=lambda x: -x[1])],
        "top_items": [{"name": n, "total": round(t, 2)} for n, t in sorted(item_spend.items(), key=lambda x: -x[1])[:10]],
        "price_changes": price_changes[:20],
        "daily_breakdown": sorted(daily.values(), key=lambda x: x["date"]),
        "alerts": alerts, "purchase_count": len(purchases), "sales_count": len(sales)
    }

@api_router.get("/reports")
async def get_reports(user=Depends(get_user), report_type: str = "weekly", date: str = ""):
    return await _build_report(user["restaurant_id"], report_type, date)

@api_router.get("/reports/download")
async def download_report(user=Depends(get_user), report_type: str = "weekly", date: str = "", fmt: str = "excel"):
    report = await _build_report(user["restaurant_id"], report_type, date)

    if fmt == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=16, spaceAfter=6)
        sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
        section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=12, spaceBefore=14, spaceAfter=6)

        elements = []
        elements.append(Paragraph("Restaurant Financial Report", title_style))
        elements.append(Paragraph(f"{report_type.title()} &bull; {report['date_range']['start']} to {report['date_range']['end']}", sub_style))
        elements.append(Spacer(1, 8*mm))

        # KPIs table
        kpi_data = [['Revenue', 'Purchases', 'Profit', 'Margin'],
                     [f"${report['total_sales']:,.2f}", f"${report['total_purchases']:,.2f}", f"${report['profit']:,.2f}", f"{report['margin_pct']}%"]]
        t = Table(kpi_data, colWidths=[45*mm]*4)
        t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTSIZE', (0,0), (-1,-1), 9), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
        elements.append(t)

        # Supplier table
        if report['spending_by_supplier']:
            elements.append(Paragraph("Spending by Supplier", section_style))
            sup_data = [['Supplier', 'Total', 'Invoices']] + [[s['name'], f"${s['total']:,.2f}", str(s['invoices'])] for s in report['spending_by_supplier'][:10]]
            t = Table(sup_data, colWidths=[80*mm, 45*mm, 30*mm])
            t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')), ('FONTSIZE', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
            elements.append(t)

        # Price changes
        if report['price_changes']:
            elements.append(Paragraph("Price Changes", section_style))
            pc_data = [['Item', 'Previous', 'Current', 'Change']] + [[p['item'], f"${p['previous_price']:,.2f}", f"${p['current_price']:,.2f}", f"{p['change_pct']:+.1f}%"] for p in report['price_changes'][:15]]
            t = Table(pc_data, colWidths=[60*mm, 35*mm, 35*mm, 30*mm])
            t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')), ('FONTSIZE', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
            elements.append(t)

        doc.build(elements)
        buf.seek(0)
        filename = f"report_{report_type}_{report['date_range']['start']}.pdf"
        return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})

    else:  # excel
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        header_font = Font(bold=True, size=10, color="FFFFFF")
        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        thin_border = Border(bottom=Side(style='thin', color='E2E8F0'))

        # Summary sheet
        ws = wb.active
        ws.title = "Summary"
        ws.append(["Restaurant Financial Report"])
        ws['A1'].font = Font(bold=True, size=14)
        ws.append([f"{report_type.title()} Report: {report['date_range']['start']} to {report['date_range']['end']}"])
        ws.append([])
        ws.append(["Metric", "Current Period", "Previous Period", "Change"])
        for col in range(1, 5):
            cell = ws.cell(row=4, column=col)
            cell.font = header_font
            cell.fill = header_fill
        def pct_chg(cur, prev):
            return f"{((cur - prev) / prev * 100):+.1f}%" if prev else "N/A"
        ws.append(["Revenue", report['total_sales'], report['prev_sales'], pct_chg(report['total_sales'], report['prev_sales'])])
        ws.append(["Purchases", report['total_purchases'], report['prev_purchases'], pct_chg(report['total_purchases'], report['prev_purchases'])])
        ws.append(["Profit", report['profit'], report['prev_profit'], pct_chg(report['profit'], report['prev_profit']) if report['prev_profit'] != 0 else "N/A"])
        ws.append(["Margin %", f"{report['margin_pct']}%", "", ""])
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 14

        # Suppliers sheet
        ws2 = wb.create_sheet("Suppliers")
        ws2.append(["Supplier", "Total Spent", "Invoices"])
        for col in range(1, 4):
            cell = ws2.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
        for s in report['spending_by_supplier']:
            ws2.append([s['name'], s['total'], s['invoices']])
        ws2.column_dimensions['A'].width = 30
        ws2.column_dimensions['B'].width = 15
        ws2.column_dimensions['C'].width = 12

        # Price changes sheet
        ws3 = wb.create_sheet("Price Changes")
        ws3.append(["Item", "Previous Price", "Current Price", "Change %"])
        for col in range(1, 5):
            cell = ws3.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
        for p in report['price_changes']:
            ws3.append([p['item'], p['previous_price'], p['current_price'], p['change_pct']])
        ws3.column_dimensions['A'].width = 25
        ws3.column_dimensions['B'].width = 15
        ws3.column_dimensions['C'].width = 15
        ws3.column_dimensions['D'].width = 12

        # Daily breakdown
        ws4 = wb.create_sheet("Daily Breakdown")
        ws4.append(["Date", "Purchases", "Sales"])
        for col in range(1, 4):
            cell = ws4.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
        for d in report['daily_breakdown']:
            ws4.append([d['date'], round(d['purchases'], 2), round(d['sales'], 2)])
        ws4.column_dimensions['A'].width = 15
        ws4.column_dimensions['B'].width = 15
        ws4.column_dimensions['C'].width = 15

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"report_{report_type}_{report['date_range']['start']}.xlsx"
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})

# ==================== PRICE INTELLIGENCE ====================

@api_router.get("/prices/intelligence")
async def price_intelligence(user=Depends(get_user)):
    """Comprehensive price tracking: supplier comparison, trends, and alerts."""
    rid = user["restaurant_id"]
    now = datetime.now(timezone.utc)
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0}).to_list(10000)

    # --- 1. Per-item, per-supplier price tracking ---
    # Structure: {item_name: {supplier: [{price, date, qty}]}}
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

    # --- 2. Supplier comparison table ---
    # For each item: avg price per supplier, best supplier, potential savings
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
        # Find best/worst
        prices_list = [(sup, d["avg_price"]) for sup, d in row["suppliers"].items()]
        if prices_list:
            prices_list.sort(key=lambda x: x[1])
            row["best_supplier"] = prices_list[0][0]
            row["best_price"] = prices_list[0][1]
            row["worst_price"] = prices_list[-1][1]
            if len(prices_list) > 1 and prices_list[-1][1] > 0:
                # Savings if always bought from cheapest
                row["savings_pct"] = round((1 - prices_list[0][1] / prices_list[-1][1]) * 100, 1)
            else:
                row["savings_pct"] = 0
        comparison_items.append(row)

    # Sort by number of suppliers (multi-supplier items first), then by savings
    comparison_items.sort(key=lambda x: (-len(x["suppliers"]), -(x.get("savings_pct", 0))))

    # --- 3. Price trends over time ---
    # Group prices by item and date (weekly buckets)
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

    # Pick top 8 items by total spend for trend charts
    item_total_spend = {}
    for p in purchases:
        for it in p.get("items", []):
            name = it.get("raw_name", "Unknown")
            item_total_spend[name] = item_total_spend.get(name, 0) + float(it.get("total", 0))
    top_trend_items = sorted(item_total_spend.items(), key=lambda x: -x[1])[:8]
    price_trends = {name: item_weekly.get(name, []) for name, _ in top_trend_items if name in item_weekly}

    # --- 4. Price increase alerts (>10%) ---
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
                    "item": name,
                    "current_avg": round(cur, 2),
                    "previous_avg": round(prev, 2),
                    "change_pct": round(pct, 1),
                    "severity": "high" if pct > 20 else "medium",
                })
    price_alerts.sort(key=lambda x: -x["change_pct"])

    return {
        "suppliers": all_suppliers,
        "comparison": comparison_items[:30],
        "price_trends": price_trends,
        "price_alerts": price_alerts[:15],
        "total_items_tracked": len(item_supplier_prices),
        "total_suppliers": len(all_suppliers),
    }

# ==================== VENDOR PRICE COMPARISON ====================

@api_router.get("/prices/vendor-comparison")
async def vendor_price_comparison(user=Depends(get_user)):
    """Per-item, per-vendor latest price comparison with best vendor highlighted."""
    rid = user["restaurant_id"]
    purchases = await db.purchases.find({"restaurant_id": rid}, {"_id": 0, "supplier_name": 1, "invoice_date": 1, "items": 1}).to_list(10000)

    # Resolve canonical names: build alias->canonical mapping
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

    # Structure: {canonical_name: {vendor: [{price, date, raw_name}]}}
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
                "vendor": vendor_name,
                "latest_price": round(latest["price"], 2),
                "latest_date": latest["date"],
                "avg_price": avg,
                "purchase_count": len(entries),
                "unit": latest.get("unit", ""),
            })

        vendors_list.sort(key=lambda x: x["latest_price"])
        best_vendor = vendors_list[0]["vendor"] if vendors_list else None
        best_price = vendors_list[0]["latest_price"] if vendors_list else 0
        worst_price = vendors_list[-1]["latest_price"] if len(vendors_list) > 1 else best_price
        savings_pct = round((1 - best_price / worst_price) * 100, 1) if worst_price > 0 and len(vendors_list) > 1 else 0

        items_out.append({
            "item": item_name,
            "vendors": vendors_list,
            "best_vendor": best_vendor,
            "best_price": best_price,
            "savings_pct": savings_pct,
            "vendor_count": len(vendors_list),
        })

    items_out.sort(key=lambda x: (-x["vendor_count"], -x["savings_pct"]))
    return {"items": items_out, "total_items": len(items_out)}

# ==================== ALERTS ====================

@api_router.get("/alerts/prices")
async def list_price_alerts(user=Depends(get_user)):
    """Get price increase alerts, newest first."""
    return await db.alerts.find(
        {"restaurant_id": user["restaurant_id"], "type": "price_increase"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)

@api_router.delete("/alerts/prices/{aid}")
async def dismiss_price_alert(aid: str, user=Depends(get_user)):
    result = await db.alerts.delete_one({"id": aid, "restaurant_id": user["restaurant_id"], "type": "price_increase"})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"status": "deleted"}

@api_router.get("/alerts")
async def list_alerts(user=Depends(get_user)):
    return await db.alerts.find({"restaurant_id": user["restaurant_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)

@api_router.put("/alerts/{aid}/read")
async def mark_alert_read(aid: str, user=Depends(get_user)):
    await db.alerts.update_one({"id": aid, "restaurant_id": user["restaurant_id"]}, {"$set": {"is_read": True}})
    return {"status": "ok"}

# ==================== CHAT ====================

@api_router.get("/chat/messages")
async def get_chat_messages(user=Depends(get_user)):
    return await db.chat_messages.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(100)

@api_router.post("/chat")
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

    # Build period-based summaries
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

    # Item price tracking for alerts
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

    # Smart alerts for chat context
    smart_alerts = await _generate_smart_alerts(rid)
    smart_alerts_ctx = ""
    if smart_alerts:
        sa_lines = []
        for sa in smart_alerts:
            sa_lines.append(f"- [{sa['type'].upper()}] {sa['title']} — {sa['detail']}")
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

@api_router.delete("/chat/messages")
async def clear_chat(user=Depends(get_user)):
    await db.chat_messages.delete_many({"user_id": user["id"]})
    return {"status": "cleared"}

# ==================== SETTINGS ====================

@api_router.get("/settings")
async def get_settings(user=Depends(get_user)):
    r = await db.restaurants.find_one({"id": user["restaurant_id"]}, {"_id": 0})
    return {"user": {"id": user["id"], "email": user["email"], "name": user["name"]}, "restaurant": r}

@api_router.put("/settings")
async def update_settings(data: SettingsUpdate, user=Depends(get_user)):
    if data.name:
        await db.users.update_one({"id": user["id"]}, {"$set": {"name": data.name}})
    if data.restaurant_name:
        await db.restaurants.update_one({"id": user["restaurant_id"]}, {"$set": {"name": data.restaurant_name}})
    if data.address is not None:
        await db.restaurants.update_one({"id": user["restaurant_id"]}, {"$set": {"address": data.address}})
    if data.phone is not None:
        await db.restaurants.update_one({"id": user["restaurant_id"]}, {"$set": {"phone": data.phone}})
    return await get_settings(user)

# ==================== SEED ====================

@api_router.post("/seed")
async def seed_data(user=Depends(get_user)):
    from seed_data import generate_seed_data
    await generate_seed_data(db, user["restaurant_id"])
    return {"status": "Seed data created successfully"}

# ==================== APP SETUP ====================

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
