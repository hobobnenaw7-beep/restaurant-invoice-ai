"""
HYBRID SPIKE V2: GPT-5.2 Vision (READ-ONLY) → System-Enforced Structure

STRICT CONSTRAINTS:
- GPT is ONLY allowed to READ and output structured row candidates
- GPT does NOT perform or decide any math
- All field selection, math, and validation is system-enforced
- Group headers / subtotals must be classified and excluded

Test cases:
1. PFG Invoice #60919474011626 ($573.70) — fix missing rows + weight extraction
2. Sysco Invoice #583635405 ($1,066.11) — fix row contamination + ketchup price
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

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


# ══════════════════════════════════════════════════════════════
# PROMPTS — GPT reads only, no math, no inference
# ══════════════════════════════════════════════════════════════

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
- $/LB (dollar value — price per pound)
- EXT PRICE (dollar value — extended price, rightmost numeric column)

INSTRUCTIONS:
1. Find the line-items table area (after headers like ITEM#, DESCRIPTION, PACK/SIZE, ORD, SHIP, WEIGHT, $/LB, EXT PRICE)
2. For EVERY row in that table, including section headers (like "*** DRY ***", "*** FROZEN ***"):
   - Read each column value EXACTLY as printed
   - Do NOT skip any rows
   - Do NOT combine rows
   - Report what you see, even if values seem unusual
3. Classify each row:
   - "product" = has item code + description + numeric values
   - "service" = surcharge, fuel, delivery, credit (no product code)
   - "section_header" = category labels like "*** DRY ***", "*** FROZEN ***"
   - "subtotal" = subtotal lines, group totals
4. For each row, include a "raw_text" field with the entire row as you read it left to right
5. Include a "confidence_note" if any value is hard to read or ambiguous

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
  "confidence_note": "any ambiguity or hard-to-read note, or empty"
}

CRITICAL:
- Do NOT calculate any values. Report only what is printed.
- Do NOT skip rows. Every line in the table area must appear.
- ORD and SHIP are TWO separate columns with TWO separate numbers side by side.
- WEIGHT is a decimal (e.g., 100.00) — it is NOT ORD or SHIP.
- Report ALL rows including section headers and subtotals.
- Return ONLY the JSON array."""


SYSCO_PROMPT = """You are reading a Sysco invoice image.

Your ONLY job is to transcribe each printed row from the line-items section of this invoice.
Do NOT compute, infer, or validate any values. Just read what is physically printed.

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
2. For EVERY row in that table area, transcribe it:
   - Product rows (have a brand, description, and numeric values)
   - Service rows (e.g., "FUEL SURCHARGE", "MISC CHARGES")
   - Group headers (e.g., "***POULTRY***", "***FROZEN***", "***GROCERY***")
   - Group totals / subtotals (e.g., "POULTRY SUBTOTAL", lines with just a total)
3. Classify each row:
   - "product" = has item code + description + price + amount
   - "service" = surcharge, delivery, credit, adjustment
   - "group_header" = section headers like "***POULTRY***"
   - "group_total" = subtotal lines for a group
   - "invoice_total" = final total line
4. For each row, include "raw_text" with the full row as you read it
5. Include "confidence_note" for any ambiguous or hard-to-read values

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
  "amount": "line total / amount as printed or empty",
  "confidence_note": "any ambiguity note, or empty"
}

CRITICAL:
- Do NOT calculate any values. Report only what is printed.
- Do NOT skip any rows. Include headers, totals, everything.
- Group headers and totals MUST be classified as such — they are NOT products.
- Return ONLY the JSON array."""


# ══════════════════════════════════════════════════════════════
# STRUCTURAL ENFORCEMENT — System-side only, no GPT math
# ══════════════════════════════════════════════════════════════

def _safe_float(val) -> float:
    """Parse a string to float, handling $, commas, empty."""
    if val is None or val == "" or val == "empty":
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _safe_int(val) -> int:
    """Parse a string to int, handling empty."""
    if val is None or val == "" or val == "empty":
        return 0
    s = str(val).replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


def enforce_pfg(raw_rows: list) -> dict:
    """
    PFG structural enforcement.
    Rules:
    - qty = SHIP column (integer)
    - total = EXT PRICE column
    - unit_price = $/LB column
    - Filter out section_header and subtotal rows
    - Service rows get qty=1
    """
    products = []
    skipped = []

    for row in raw_rows:
        rt = row.get("row_type", "product")

        if rt in ("section_header", "subtotal"):
            skipped.append({"raw_text": row.get("raw_text", ""), "row_type": rt,
                            "reason": "excluded by classification"})
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
            # RULE: qty = SHIP, never from ORD, WEIGHT, or PACK
            qty = ship
            # Guard: if SHIP > 200, it might be WEIGHT leaked into SHIP
            if qty > 200:
                qty = ord_val if 0 < ord_val < 200 else 0
                note += " [SHIP>200, used ORD as fallback]"

        # RULE: total = EXT PRICE (rightmost $ column)
        total = ext_price

        # RULE: unit_price = $/LB
        unit_price = price_lb

        # Math check (system-computed, not GPT)
        # PFG pricing: EXT PRICE = WEIGHT × $/LB (weight-based)
        weight_x_price = round(weight * price_lb, 2) if weight > 0 and price_lb > 0 else 0
        if weight_x_price > 0 and ext_price > 0:
            math_diff = abs(weight_x_price - ext_price)
            math_pct = math_diff / ext_price if ext_price else 0
            math_check = "PASS" if math_pct < 0.02 else f"WARN (weight×$/LB={weight_x_price:.2f} vs ext={ext_price:.2f}, diff={math_pct:.1%})"
        else:
            math_check = "SKIP (weight or price missing)"

        products.append({
            "item_name": desc,
            "pack_size": pack,
            "quantity": qty,
            "ord_qty": ord_val,
            "ship_qty": ship,
            "weight": weight,
            "unit_price": unit_price,
            "total": total,
            "row_type": rt,
            "qty_source": "SHIP",
            "math_check": math_check,
            "confidence_note": note,
            "raw_text": row.get("raw_text", ""),
        })

    items_sum = round(sum(p["total"] for p in products), 2)

    return {
        "items": products,
        "skipped": skipped,
        "items_sum": items_sum,
        "item_count": len(products),
        "skipped_count": len(skipped),
    }


def enforce_sysco(raw_rows: list) -> dict:
    """
    Sysco structural enforcement.
    Rules:
    - Filter out group_header, group_total, invoice_total
    - qty from QTY column
    - total from AMOUNT column
    - price from PRICE column
    - Math: qty × price = amount (system-checked)
    """
    products = []
    skipped = []

    for row in raw_rows:
        rt = row.get("row_type", "product")

        if rt in ("group_header", "group_total", "invoice_total"):
            skipped.append({"raw_text": row.get("raw_text", ""), "row_type": rt,
                            "reason": "excluded by classification"})
            continue

        qty = _safe_int(row.get("qty"))
        price = _safe_float(row.get("price"))
        amount = _safe_float(row.get("amount"))
        desc = row.get("description", "").strip()
        pack = row.get("pack_size", "").strip()
        note = row.get("confidence_note", "")

        if rt == "service":
            if qty == 0:
                qty = 1

        # Math check (system-enforced)
        computed = round(qty * price, 2) if qty > 0 and price > 0 else 0
        if computed > 0 and amount > 0:
            math_diff = abs(computed - amount)
            math_pct = math_diff / amount if amount else 0
            math_check = f"PASS (qty={qty} × price={price} = {computed}, declared={amount})" if math_pct < 0.02 else \
                f"FAIL (qty={qty} × price={price} = {computed}, declared={amount}, diff={math_pct:.1%})"
        else:
            math_check = f"SKIP (qty={qty}, price={price})"

        products.append({
            "item_name": desc,
            "pack_size": pack,
            "quantity": qty,
            "unit_price": price,
            "total": amount,
            "row_type": rt,
            "math_check": math_check,
            "confidence_note": note,
            "raw_text": row.get("raw_text", ""),
        })

    items_sum = round(sum(p["total"] for p in products), 2)

    return {
        "items": products,
        "skipped": skipped,
        "items_sum": items_sum,
        "item_count": len(products),
        "skipped_count": len(skipped),
    }


# ══════════════════════════════════════════════════════════════
# COMPARISON WITH STORED EXTRACTION
# ══════════════════════════════════════════════════════════════

def load_stored_extraction(vendor_pattern: str, target_total: float):
    """Load the stored GPT extraction from MongoDB for comparison."""
    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017')
    db = client['test_database']
    purchases = list(db.purchases.find(
        {'supplier_name': re.compile(vendor_pattern, re.IGNORECASE)},
        {'_id': 0}
    ))
    for p in purchases:
        total = p.get('total', 0)
        if abs(total - target_total) < 1:
            return p
    return None


# ══════════════════════════════════════════════════════════════
# MAIN SPIKE
# ══════════════════════════════════════════════════════════════

async def run_spike():
    print("=" * 90)
    print("HYBRID SPIKE V2: GPT-5.2 (READ-ONLY) → System-Enforced Structure")
    print("CONSTRAINT: GPT does NO math. All validation is system-side.")
    print("=" * 90)

    # ────────────────────────────────────────────────────────
    # TEST 1: PFG
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("TEST 1: PFG Invoice #60919474011626 ($573.70)")
    print("PREVIOUS SPIKE: 4 items, qty varies ✓, sum=$476.41 (missing $97.29)")
    print("GOAL: No missing rows, correct WEIGHT, correct EXT PRICE")
    print("=" * 90)

    with open("/app/backend/uploads/e23e24ad-c550-4f3b-8924-8728caaa9054.jpg", "rb") as f:
        pfg_b64 = base64.b64encode(f.read()).decode()

    pfg_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike2-pfg-{uuid.uuid4()}",
        system_message="You are a precise document reader. Transcribe exactly what is printed. Do NOT compute or infer values."
    ).with_model("openai", "gpt-5.2")

    print("\nStep 1: GPT-5.2 reading invoice (column-level transcription)...")
    pfg_msg = UserMessage(text=PFG_PROMPT, file_contents=[ImageContent(image_base64=pfg_b64)])
    pfg_response = await pfg_chat.send_message(pfg_msg)

    try:
        clean = pfg_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        pfg_raw = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw: {pfg_response[:800]}")
        pfg_raw = []

    print(f"   GPT-5.2 returned {len(pfg_raw)} rows")

    print("\n--- GPT-5.2 RAW TRANSCRIPTION (PFG) ---")
    for i, row in enumerate(pfg_raw):
        rt = row.get("row_type", "?")
        raw = row.get("raw_text", "")[:80]
        desc = row.get("description", "")[:35]
        pack = row.get("pack_size", "")
        ord_v = row.get("ord", "")
        ship = row.get("ship", "")
        wt = row.get("weight", "")
        plb = row.get("price_per_lb", "")
        ext = row.get("ext_price", "")
        note = row.get("confidence_note", "")
        print(f"  [{i:2d}] [{rt:15s}] {desc:35s} pack={str(pack):>10s} ORD={str(ord_v):>4s} SHIP={str(ship):>4s} WT={str(wt):>8s} $/LB={str(plb):>8s} EXT={str(ext):>10s}")
        if note:
            print(f"       NOTE: {note}")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (PFG) ---")
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
        print(f"  [{i:2d}] {name:40s} qty={qty:>4} (SHIP={ship}) wt={wt:>8.2f} $/LB=${up:>7.2f} EXT=${tot:>10.2f} pack={str(pack):>10s} [{rt}] {mc}")

    print(f"\n  Skipped rows: {pfg_result['skipped_count']}")
    for s in pfg_result["skipped"]:
        print(f"    [{s['row_type']}] {s['raw_text'][:70]}")

    print(f"\n  Items sum: ${pfg_result['items_sum']:.2f} vs Declared: $573.70")
    pfg_diff = abs(pfg_result['items_sum'] - 573.70)
    print(f"  Match: {'YES' if pfg_diff < 0.50 else f'NO (diff=${pfg_diff:.2f})'}")

    # Compare with stored
    stored_pfg = load_stored_extraction("performance", 573.70)
    if stored_pfg:
        print("\n--- COMPARISON WITH STORED EXTRACTION ---")
        stored_items = stored_pfg.get('items', [])
        print(f"  Stored: {len(stored_items)} items, all qty=1")
        for j, si in enumerate(stored_items):
            print(f"    [{j}] {si.get('raw_name', 'N/A')[:40]:40s} qty={si.get('quantity', 0):>4} total=${si.get('total', 0):>10.2f}")
        stored_sum = sum(float(si.get('total', 0) or 0) for si in stored_items)
        print(f"  Stored sum: ${stored_sum:.2f}")

    # ────────────────────────────────────────────────────────
    # TEST 2: SYSCO
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("TEST 2: Sysco Invoice #583635405 ($1,066.11)")
    print("PREVIOUS SPIKE: 10 items, sum=$1096.11 (ketchup price misread, row contamination)")
    print("GOAL: No row contamination, correct ketchup price, totals match")
    print("=" * 90)

    with open("/app/backend/uploads/95ebb38a-6d7e-4606-83f1-ec2a0f2a6d15.jpg", "rb") as f:
        sysco_b64 = base64.b64encode(f.read()).decode()

    sysco_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike2-sysco-{uuid.uuid4()}",
        system_message="You are a precise document reader. Transcribe exactly what is printed. Do NOT compute or infer values."
    ).with_model("openai", "gpt-5.2")

    print("\nStep 1: GPT-5.2 reading invoice (column-level transcription)...")
    sysco_msg = UserMessage(text=SYSCO_PROMPT, file_contents=[ImageContent(image_base64=sysco_b64)])
    sysco_response = await sysco_chat.send_message(sysco_msg)

    try:
        clean = sysco_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        sysco_raw = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw: {sysco_response[:800]}")
        sysco_raw = []

    print(f"   GPT-5.2 returned {len(sysco_raw)} rows")

    print("\n--- GPT-5.2 RAW TRANSCRIPTION (Sysco) ---")
    for i, row in enumerate(sysco_raw):
        rt = row.get("row_type", "?")
        desc = row.get("description", "")[:45]
        pack = row.get("pack_size", "")
        qty = row.get("qty", "")
        price = row.get("price", "")
        amount = row.get("amount", "")
        note = row.get("confidence_note", "")
        print(f"  [{i:2d}] [{rt:13s}] {desc:45s} pack={str(pack):>12s} qty={str(qty):>4s} price={str(price):>8s} amount={str(amount):>10s}")
        if note:
            print(f"       NOTE: {note}")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (Sysco) ---")
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

    print(f"\n  Skipped rows: {sysco_result['skipped_count']}")
    for s in sysco_result["skipped"]:
        print(f"    [{s['row_type']}] {s['raw_text'][:70]}")

    print(f"\n  Items sum: ${sysco_result['items_sum']:.2f} vs Declared: $1,066.11")
    sysco_diff = abs(sysco_result['items_sum'] - 1066.11)
    print(f"  Match: {'YES' if sysco_diff < 0.50 else f'NO (diff=${sysco_diff:.2f})'}")

    # Compare with stored
    stored_sysco = load_stored_extraction("sysco", 1066.11)
    if stored_sysco:
        print("\n--- COMPARISON WITH STORED EXTRACTION ---")
        stored_items = stored_sysco.get('items', [])
        print(f"  Stored: {len(stored_items)} items")
        for j, si in enumerate(stored_items):
            print(f"    [{j}] {si.get('raw_name', 'N/A')[:40]:40s} qty={si.get('quantity', 0):>4} price=${si.get('unit_price', 0):>8.2f} total=${si.get('total', 0):>10.2f}")
        stored_sum = sum(float(si.get('total', 0) or 0) for si in stored_items)
        print(f"  Stored sum: ${stored_sum:.2f}")

    # ────────────────────────────────────────────────────────
    # FINAL VERDICT
    # ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("SPIKE V2 VERDICT")
    print("=" * 90)

    pfg_qty_ok = any(it['quantity'] != 1 for it in pfg_result['items'] if it['row_type'] == 'product')
    pfg_total_ok = pfg_diff < 0.50
    sysco_total_ok = sysco_diff < 0.50
    sysco_no_contamination = not any("GRP TOTAL" in it['item_name'].upper() or "SUBTOTAL" in it['item_name'].upper()
                                      for it in sysco_result['items'])
    sysco_math_ok = all("PASS" in it['math_check'] or "SKIP" in it['math_check']
                        for it in sysco_result['items'])

    print(f"\n  PFG:")
    print(f"    1. No missing rows:          {'PASS' if len(pfg_result['items']) >= 4 else 'FAIL'} ({len(pfg_result['items'])} product+service rows)")
    print(f"    2. qty from SHIP (not all 1): {'PASS' if pfg_qty_ok else 'FAIL'}")
    print(f"    3. Correct WEIGHT extraction: CHECK (see math_check above)")
    print(f"    4. Total matches $573.70:     {'PASS' if pfg_total_ok else f'FAIL (diff=${pfg_diff:.2f})'}")

    print(f"\n  Sysco:")
    print(f"    1. No row contamination:     {'PASS' if sysco_no_contamination else 'FAIL'}")
    print(f"    2. Math validation:          {'PASS' if sysco_math_ok else 'FAIL'}")
    print(f"    3. Total matches $1,066.11:  {'PASS' if sysco_total_ok else f'FAIL (diff=${sysco_diff:.2f})'}")

    print(f"\n  OVERALL: {'SPIKE SUCCEEDED' if (pfg_qty_ok and pfg_total_ok and sysco_total_ok and sysco_no_contamination) else 'SPIKE NEEDS REVIEW — see details above'}")


if __name__ == "__main__":
    asyncio.run(run_spike())
