from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from core.database import db
from core.auth import get_user
from core.models import DuplicateCheckRequest

router = APIRouter()


@router.post("/duplicates/check")
async def check_duplicates(req: DuplicateCheckRequest, user=Depends(get_user)):
    """Check for possible duplicate records before saving."""
    rid = user["restaurant_id"]
    rt = req.record_type
    d = req.data
    matches = []

    if rt == "purchase":
        query = {"restaurant_id": rid}
        inv_no = d.get("invoice_number", "").strip()
        if inv_no:
            existing = await db.purchases.find(
                {**query, "invoice_number": {"$regex": f"^{inv_no}$", "$options": "i"}}, {"_id": 0, "id": 1, "supplier_name": 1, "invoice_number": 1, "invoice_date": 1, "total": 1}
            ).to_list(10)
            for e in existing:
                matches.append({"reason": f"Same invoice number: {inv_no}", "match_type": "invoice_number", **e})

        vendor = d.get("supplier_name", "").strip()
        inv_date = d.get("invoice_date", "")
        total = d.get("total", 0)
        if vendor and inv_date and total:
            existing = await db.purchases.find(
                {**query, "supplier_name": {"$regex": f"^{vendor}$", "$options": "i"}, "invoice_date": inv_date, "total": {"$gte": total * 0.99, "$lte": total * 1.01}},
                {"_id": 0, "id": 1, "supplier_name": 1, "invoice_number": 1, "invoice_date": 1, "total": 1}
            ).to_list(10)
            for e in existing:
                if not any(m.get("id") == e.get("id") for m in matches):
                    matches.append({"reason": f"Same vendor ({vendor}), date ({inv_date}), and amount (${total:.2f})", "match_type": "vendor_date_amount", **e})

    elif rt == "sale":
        report_date = d.get("report_date", "")
        total_sales = d.get("total_sales", 0)
        if report_date:
            existing = await db.sales.find(
                {"restaurant_id": rid, "report_date": report_date, "total_sales": {"$gte": total_sales * 0.99, "$lte": total_sales * 1.01}},
                {"_id": 0, "id": 1, "report_date": 1, "total_sales": 1}
            ).to_list(10)
            for e in existing:
                matches.append({"reason": f"Same date ({report_date}) and total (${total_sales:.2f})", "match_type": "date_amount", **e})

            if not matches:
                existing = await db.sales.find(
                    {"restaurant_id": rid, "report_date": report_date},
                    {"_id": 0, "id": 1, "report_date": 1, "total_sales": 1}
                ).to_list(10)
                for e in existing:
                    matches.append({"reason": f"A sales record already exists for {report_date}", "match_type": "date_only", **e})

    elif rt == "salary":
        employee = d.get("employee_name", "").strip()
        pay_date = d.get("payment_date", "")
        if employee and pay_date:
            existing = await db.salaries.find(
                {"restaurant_id": rid, "employee_name": {"$regex": f"^{employee}$", "$options": "i"}, "payment_date": pay_date},
                {"_id": 0, "id": 1, "employee_name": 1, "payment_date": 1, "amount": 1, "position": 1}
            ).to_list(10)
            for e in existing:
                matches.append({"reason": f"Same employee ({employee}) and date ({pay_date})", "match_type": "employee_date", **e})

    elif rt == "other_expense":
        title = d.get("title", "").strip()
        exp_date = d.get("expense_date", "")
        amount = d.get("amount", 0)
        if title and exp_date:
            existing = await db.other_expenses.find(
                {"restaurant_id": rid, "title": {"$regex": f"^{title}$", "$options": "i"}, "expense_date": exp_date},
                {"_id": 0, "id": 1, "title": 1, "expense_date": 1, "amount": 1, "category": 1}
            ).to_list(10)
            for e in existing:
                matches.append({"reason": f"Same title ({title}) and date ({exp_date})", "match_type": "title_date", **e})

        if not matches and amount and exp_date:
            existing = await db.other_expenses.find(
                {"restaurant_id": rid, "expense_date": exp_date, "amount": {"$gte": amount * 0.99, "$lte": amount * 1.01}},
                {"_id": 0, "id": 1, "title": 1, "expense_date": 1, "amount": 1, "category": 1}
            ).to_list(10)
            for e in existing:
                if not any(m.get("id") == e.get("id") for m in matches):
                    matches.append({"reason": f"Same date ({exp_date}) and amount (${amount:.2f})", "match_type": "date_amount", **e})

    return {"has_duplicates": len(matches) > 0, "matches": matches}
