"""
HYBRID SPIKE V3: SCANNED INPUT TEST

Tests GPT-5.2 vision (read-only) → structural enforcement on SCANNED PDFs.
No camera photos. This establishes the baseline for scanned input reliability.

Test cases:
1. PFG PDF Invoice #6025678020626 ($806.20)
2. Sysco PDF Invoice #583705511 ($1,040.29)
"""

import asyncio
import base64
import json
import os
import re
import sys
import uuid

sys.path.insert(0, "/app/backend")

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from pdf2image import convert_from_path
import numpy as np
import cv2

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


# ── Same prompts as V2 (read-only, no math) ──

PFG_PROMPT = """You are reading a Performance Foodservice (PFG) invoice image.

Your ONLY job is to transcribe each printed row from the line-items section of this invoice.
Do NOT compute, infer, or validate any values. Just read what is physically printed.

The invoice has these columns from left to right:
- ITEM# (7-digit code, leftmost)
- DESCRIPTION (product name text)
- PACK/SIZE (e.g., "1/25 LB", "6/4 LB", "2/5 OZ" — appears between description and the numeric columns)
- ORD (integer — ordered quantity)
- SHIP (integer — shipped quantity, immediately right of ORD)
- WEIGHT (decimal number with decimals, e.g., 100.00, 24.00, 75.00 — total weight in LBs)
- $/LB (dollar value — price per pound, e.g., $8.33, $2.97)
- EXT PRICE (dollar value — extended price, rightmost numeric column)

INSTRUCTIONS:
1. Find the line-items table area (after headers like ITEM#, DESCRIPTION, PACK/SIZE, ORD, SHIP, WEIGHT, $/LB, EXT PRICE)
2. For EVERY row in that table, including section headers (like "*** DRY ***", "*** FROZEN ***"):
   - Read each column value EXACTLY as printed
   - Do NOT skip any rows
   - Do NOT combine rows
3. Classify each row:
   - "product" = has item code + description + numeric values
   - "service" = surcharge, fuel, delivery, credit (no product code)
   - "section_header" = category labels like "*** DRY ***", "*** FROZEN ***"
   - "subtotal" = subtotal lines, group totals
4. Include "raw_text" with the entire row as read left to right
5. Include "confidence_note" if any value is hard to read

Return a JSON array. Each element:
{
  "raw_text": "full row text as read left to right",
  "row_type": "product" | "service" | "section_header" | "subtotal",
  "item_code": "7-digit code or empty",
  "description": "product name",
  "pack_size": "pack as printed or empty",
  "ord": "value as printed or empty",
  "ship": "value as printed or empty",
  "weight": "value as printed or empty",
  "price_per_lb": "value as printed or empty",
  "ext_price": "value as printed or empty",
  "confidence_note": "any ambiguity note, or empty"
}

CRITICAL:
- Do NOT calculate any values. Report only what is printed.
- Do NOT skip rows. Every line in the table must appear.
- ORD and SHIP are TWO separate columns with TWO separate numbers.
- WEIGHT is a decimal (e.g., 100.00). Do NOT confuse with ORD/SHIP.
- Return ONLY the JSON array."""


SYSCO_PROMPT = """You are reading a Sysco invoice image.

Your ONLY job is to transcribe each printed row from the line-items section of this invoice.
Do NOT compute, infer, or validate any values. Just read what is printed.

The invoice has these columns:
- QTY SHIP (integer — quantity shipped, usually leftmost numeric)
- PACK (pack specification, e.g., "4/10 LB", "12/24 OZ", "1508X8X3")
- BRAND & DESCRIPTION (product name)
- ITEM CODE (Sysco item number)
- SUPC (supplier product code)
- PRICE (unit price per case, dollar value)
- AMOUNT (extended total, dollar value, rightmost)

INSTRUCTIONS:
1. Find the line-items table area
2. For EVERY row, transcribe it:
   - Product rows, service rows, group headers, group totals
3. Classify each row:
   - "product" = has item code + description + price + amount
   - "service" = surcharge, delivery, credit, adjustment
   - "group_header" = section headers like "***POULTRY***"
   - "group_total" = subtotal lines for a group
   - "invoice_total" = final total line
4. Include "raw_text" and "confidence_note"

Return a JSON array. Each element:
{
  "raw_text": "full row text as read left to right",
  "row_type": "product" | "service" | "group_header" | "group_total" | "invoice_total",
  "qty": "value as printed or empty",
  "pack_size": "pack as printed or empty",
  "description": "product name or header text",
  "item_code": "item code or empty",
  "supc": "supplier code or empty",
  "price": "unit price as printed or empty",
  "amount": "line total as printed or empty",
  "confidence_note": "any ambiguity note, or empty"
}

CRITICAL:
- Do NOT calculate any values. Report only what is printed.
- Do NOT skip any rows. Include headers, totals, everything.
- Group headers and totals MUST be classified as such.
- Return ONLY the JSON array."""


# ── Structural enforcement (same as V2) ──

def _safe_float(val) -> float:
    if val is None or val == "" or val == "empty":
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def _safe_int(val) -> int:
    if val is None or val == "" or val == "empty":
        return 0
    s = str(val).replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0

def enforce_pfg(raw_rows: list) -> dict:
    products = []
    skipped = []
    for row in raw_rows:
        rt = row.get("row_type", "product")
        if rt in ("section_header", "subtotal"):
            skipped.append({"raw_text": row.get("raw_text", ""), "row_type": rt})
            continue
        ship = _safe_int(row.get("ship"))
        ord_val = _safe_int(row.get("ord"))
        weight = _safe_float(row.get("weight"))
        price_lb = _safe_float(row.get("price_per_lb"))
        ext_price = _safe_float(row.get("ext_price"))
        desc = row.get("description", "").strip()
        pack = row.get("pack_size", "").strip()
        note = row.get("confidence_note", "")

        if rt == "service":
            qty = 1
        else:
            qty = ship
            if qty > 200:
                qty = ord_val if 0 < ord_val < 200 else 0
                note += " [SHIP>200, fallback to ORD]"

        total = ext_price
        unit_price = price_lb

        # System math: PFG pricing = WEIGHT × $/LB
        wt_x_plb = round(weight * price_lb, 2) if weight > 0 and price_lb > 0 else 0
        if wt_x_plb > 0 and ext_price > 0:
            diff_pct = abs(wt_x_plb - ext_price) / ext_price
            math_check = f"PASS (wt={weight}×$/LB={price_lb}={wt_x_plb})" if diff_pct < 0.02 else \
                f"WARN ({wt_x_plb} vs ext={ext_price}, diff={diff_pct:.1%})"
        else:
            math_check = f"SKIP (wt={weight}, $/LB={price_lb})"

        products.append({
            "item_name": desc, "pack_size": pack, "quantity": qty,
            "ord_qty": ord_val, "ship_qty": ship, "weight": weight,
            "unit_price": unit_price, "total": total, "row_type": rt,
            "math_check": math_check, "confidence_note": note,
            "raw_text": row.get("raw_text", ""),
        })

    return {
        "items": products,
        "skipped": skipped,
        "items_sum": round(sum(p["total"] for p in products), 2),
        "item_count": len(products),
    }

def enforce_sysco(raw_rows: list) -> dict:
    products = []
    skipped = []
    for row in raw_rows:
        rt = row.get("row_type", "product")
        if rt in ("group_header", "group_total", "invoice_total"):
            skipped.append({"raw_text": row.get("raw_text", ""), "row_type": rt})
            continue
        qty = _safe_int(row.get("qty"))
        price = _safe_float(row.get("price"))
        amount = _safe_float(row.get("amount"))
        desc = row.get("description", "").strip()
        pack = row.get("pack_size", "").strip()
        note = row.get("confidence_note", "")

        if rt == "service" and qty == 0:
            qty = 1

        computed = round(qty * price, 2) if qty > 0 and price > 0 else 0
        if computed > 0 and amount > 0:
            diff_pct = abs(computed - amount) / amount
            math_check = f"PASS ({qty}×{price}={computed})" if diff_pct < 0.02 else \
                f"FAIL ({qty}×{price}={computed} vs {amount}, diff={diff_pct:.1%})"
        else:
            math_check = f"SKIP (qty={qty}, price={price})"

        products.append({
            "item_name": desc, "pack_size": pack, "quantity": qty,
            "unit_price": price, "total": amount, "row_type": rt,
            "math_check": math_check, "confidence_note": note,
            "raw_text": row.get("raw_text", ""),
        })

    return {
        "items": products,
        "skipped": skipped,
        "items_sum": round(sum(p["total"] for p in products), 2),
        "item_count": len(products),
    }


def pdf_to_b64_images(pdf_path: str) -> list:
    """Convert PDF pages to base64 images for GPT vision."""
    pages = convert_from_path(pdf_path, dpi=300)
    images = []
    for page in pages:
        img = np.array(page)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        images.append(base64.b64encode(buf.tobytes()).decode())
    return images


async def run_spike():
    print("=" * 90)
    print("HYBRID SPIKE V3: SCANNED PDF INPUT")
    print("Testing GPT-5.2 read-only → structural enforcement on SCANNED invoices")
    print("=" * 90)

    # ────────────────────────────────────────────────────────
    # TEST 1: PFG SCANNED PDF
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("TEST 1: PFG SCANNED PDF — Invoice #6025678020626 ($806.20)")
    print("=" * 90)

    pfg_images = pdf_to_b64_images("/app/backend/uploads/c749f241-3a5f-4e9d-9240-81ed985bec0e.pdf")
    print(f"  PDF pages: {len(pfg_images)}")

    pfg_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike3-pfg-{uuid.uuid4()}",
        system_message="You are a precise document reader. Transcribe exactly what is printed. Do NOT compute or infer values."
    ).with_model("openai", "gpt-5.2")

    print("\nStep 1: GPT-5.2 reading scanned PFG invoice...")
    file_contents = [ImageContent(image_base64=b64) for b64 in pfg_images]
    pfg_msg = UserMessage(text=PFG_PROMPT, file_contents=file_contents)
    pfg_response = await pfg_chat.send_message(pfg_msg)

    try:
        clean = pfg_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        pfg_raw = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw: {pfg_response[:1000]}")
        pfg_raw = []

    print(f"   GPT-5.2 returned {len(pfg_raw)} rows")

    print("\n--- GPT-5.2 RAW TRANSCRIPTION (PFG SCANNED) ---")
    for i, row in enumerate(pfg_raw):
        rt = row.get("row_type", "?")
        desc = row.get("description", "")[:40]
        pack = row.get("pack_size", "")
        ord_v = row.get("ord", "")
        ship = row.get("ship", "")
        wt = row.get("weight", "")
        plb = row.get("price_per_lb", "")
        ext = row.get("ext_price", "")
        note = row.get("confidence_note", "")
        print(f"  [{i:2d}] [{rt:15s}] {desc:40s} pack={str(pack):>12s} ORD={str(ord_v):>4s} SHIP={str(ship):>4s} WT={str(wt):>8s} $/LB={str(plb):>8s} EXT={str(ext):>10s}")
        if note:
            print(f"       NOTE: {note}")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (PFG SCANNED) ---")
    pfg_result = enforce_pfg(pfg_raw)
    for i, item in enumerate(pfg_result["items"]):
        name = item['item_name'][:40]
        qty = item['quantity']
        ship = item['ship_qty']
        wt = item['weight']
        up = item['unit_price']
        tot = item['total']
        pack = item['pack_size']
        rt = item['row_type']
        mc = item['math_check']
        print(f"  [{i:2d}] {name:40s} qty={qty:>4} (SHIP={ship}) wt={wt:>8.2f} $/LB=${up:>7.2f} EXT=${tot:>10.2f} pack={str(pack):>12s} [{rt}] {mc}")

    print(f"\n  Skipped: {len(pfg_result['skipped'])} rows")
    for s in pfg_result["skipped"]:
        print(f"    [{s['row_type']}] {s['raw_text'][:70]}")

    pfg_sum = pfg_result['items_sum']
    pfg_target = 806.20
    pfg_diff = abs(pfg_sum - pfg_target)
    print(f"\n  Items sum: ${pfg_sum:.2f} vs Declared: ${pfg_target:.2f}")
    print(f"  Match: {'YES' if pfg_diff < 0.50 else f'NO (diff=${pfg_diff:.2f})'}")

    # ────────────────────────────────────────────────────────
    # TEST 2: SYSCO SCANNED PDF
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("TEST 2: SYSCO SCANNED PDF — Invoice #583705511 ($1,040.29)")
    print("=" * 90)

    sysco_images = pdf_to_b64_images("/app/backend/uploads/44c261e2-6a53-4a84-8210-1c568a840696.pdf")
    print(f"  PDF pages: {len(sysco_images)}")

    sysco_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike3-sysco-{uuid.uuid4()}",
        system_message="You are a precise document reader. Transcribe exactly what is printed. Do NOT compute or infer values."
    ).with_model("openai", "gpt-5.2")

    print("\nStep 1: GPT-5.2 reading scanned Sysco invoice...")
    file_contents = [ImageContent(image_base64=b64) for b64 in sysco_images]
    sysco_msg = UserMessage(text=SYSCO_PROMPT, file_contents=file_contents)
    sysco_response = await sysco_chat.send_message(sysco_msg)

    try:
        clean = sysco_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        sysco_raw = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw: {sysco_response[:1000]}")
        sysco_raw = []

    print(f"   GPT-5.2 returned {len(sysco_raw)} rows")

    print("\n--- GPT-5.2 RAW TRANSCRIPTION (SYSCO SCANNED) ---")
    for i, row in enumerate(sysco_raw):
        rt = row.get("row_type", "?")
        desc = row.get("description", "")[:45]
        pack = row.get("pack_size", "")
        qty = row.get("qty", "")
        price = row.get("price", "")
        amount = row.get("amount", "")
        note = row.get("confidence_note", "")
        print(f"  [{i:2d}] [{rt:13s}] {desc:45s} pack={str(pack):>12s} qty={str(qty):>4s} price={str(price):>8s} amt={str(amount):>10s}")
        if note:
            print(f"       NOTE: {note}")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (SYSCO SCANNED) ---")
    sysco_result = enforce_sysco(sysco_raw)
    for i, item in enumerate(sysco_result["items"]):
        name = item['item_name'][:45]
        qty = item['quantity']
        up = item['unit_price']
        tot = item['total']
        pack = item['pack_size']
        rt = item['row_type']
        mc = item['math_check']
        print(f"  [{i:2d}] {name:45s} qty={qty:>4} × ${up:>8.2f} = ${tot:>10.2f} pack={str(pack):>12s} [{rt}] {mc}")

    print(f"\n  Skipped: {len(sysco_result['skipped'])} rows")
    for s in sysco_result["skipped"]:
        print(f"    [{s['row_type']}] {s['raw_text'][:70]}")

    sysco_sum = sysco_result['items_sum']
    sysco_target = 1040.29
    sysco_diff = abs(sysco_sum - sysco_target)
    print(f"\n  Items sum: ${sysco_sum:.2f} vs Declared: ${sysco_target:.2f}")
    print(f"  Match: {'YES' if sysco_diff < 0.50 else f'NO (diff=${sysco_diff:.2f})'}")

    # ────────────────────────────────────────────────────────
    # VERDICT
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("SPIKE V3 — SCANNED INPUT VERDICT")
    print("=" * 90)

    pfg_qty_ok = any(it['quantity'] != 1 for it in pfg_result['items'] if it['row_type'] == 'product')
    pfg_math_checks = [it['math_check'] for it in pfg_result['items'] if it['row_type'] == 'product']
    pfg_math_pass = sum(1 for mc in pfg_math_checks if "PASS" in mc)

    sysco_no_contam = not any("GRP TOTAL" in it['item_name'].upper() or "SUBTOTAL" in it['item_name'].upper()
                               for it in sysco_result['items'])
    sysco_math_checks = [it['math_check'] for it in sysco_result['items']]
    sysco_math_pass = sum(1 for mc in sysco_math_checks if "PASS" in mc)
    sysco_math_fail = sum(1 for mc in sysco_math_checks if "FAIL" in mc)

    print(f"\n  PFG SCANNED:")
    print(f"    Items extracted:     {pfg_result['item_count']}")
    print(f"    qty from SHIP:       {'PASS' if pfg_qty_ok else 'FAIL (all qty=1)'}")
    print(f"    Math validation:     {pfg_math_pass}/{len(pfg_math_checks)} PASS")
    print(f"    Total match:         {'PASS' if pfg_diff < 0.50 else f'FAIL (${pfg_sum:.2f} vs ${pfg_target:.2f}, diff=${pfg_diff:.2f})'}")

    print(f"\n  SYSCO SCANNED:")
    print(f"    Items extracted:     {sysco_result['item_count']}")
    print(f"    No contamination:    {'PASS' if sysco_no_contam else 'FAIL'}")
    print(f"    Math validation:     {sysco_math_pass}/{len(sysco_math_checks)} PASS, {sysco_math_fail} FAIL")
    print(f"    Total match:         {'PASS' if sysco_diff < 0.50 else f'FAIL (${sysco_sum:.2f} vs ${sysco_target:.2f}, diff=${sysco_diff:.2f})'}")

    overall = pfg_qty_ok and pfg_diff < 1.0 and sysco_no_contam and sysco_diff < 1.0
    print(f"\n  OVERALL: {'SCANNED INPUT VIABLE' if overall else 'NEEDS FURTHER INVESTIGATION'}")


if __name__ == "__main__":
    asyncio.run(run_spike())
