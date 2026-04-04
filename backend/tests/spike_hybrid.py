"""
HYBRID SPIKE: GPT-5.2 Vision → Structural Enforcement

Purpose: Prove that GPT-5.2 can produce structured intermediate data
that the existing parser rules can enforce upon.

Test cases:
1. PFG Invoice #60919474011626 ($573.70) — currently all qty=1
2. Sysco Invoice #583635405 ($1,066.11) — currently correct but testing stability

For each invoice:
- Step 1: GPT-5.2 reads the image with a COLUMN-LEVEL extraction prompt
         (not "extract items" but "read each column separately per row")
- Step 2: Structural enforcement rules validate the output
- Step 3: Compare with current stored extraction
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


# ── PFG Column-Level Extraction Prompt ──
PFG_COLUMN_PROMPT = """You are reading a Performance Foodservice (PFG) invoice.

This invoice has a STRICT columnar layout. Read EACH COLUMN SEPARATELY for every line item row.

The columns from left to right are:
1. ITEM# — 7-digit product code (e.g., 7365011)
2. DESCRIPTION — product name (e.g., "OYSTER MEAT 18-24 GM IQF")
3. PACK/SIZE — pack specification (e.g., "6/4 LB", "1/25 LB", "2/5 OZ"). This is NOT a quantity.
4. ORD — integer: how many cases were ordered (e.g., 6, 10, 25)
5. SHIP — integer: how many cases were actually shipped/delivered (e.g., 1, 4, 10). THIS IS THE DELIVERED QUANTITY.
6. WEIGHT — decimal: total weight in pounds (e.g., 24.00, 75.00, 40.00). This is NOT a quantity.
7. $/LB — dollar amount: price per pound (e.g., $8.33, $2.97, $6.40)
8. EXT PRICE — dollar amount: extended price / line total (e.g., $199.99, $296.90)

CRITICAL RULES:
- Read ORD and SHIP as SEPARATE columns. They are two different numbers side by side.
- WEIGHT is a decimal number (often with .00). Do NOT confuse it with ORD or SHIP.
- PACK/SIZE values like "6/4 LB" are pack descriptions, NOT quantities.
- If a line says "FUEL SURCHARGE" or similar, it's a service line — report it with qty=1.

Return a JSON array where each element has EXACTLY these fields:
{
  "item_code": "7-digit code or empty",
  "description": "product name",
  "pack_size": "pack specification as written",
  "ord": integer (ordered quantity),
  "ship": integer (shipped/delivered quantity),
  "weight": decimal (total weight in LBs),
  "price_per_lb": decimal ($/LB value, without $ sign),
  "ext_price": decimal (extended price / line total, without $ sign),
  "row_type": "product" or "service"
}

Return ONLY the JSON array. No markdown, no explanation."""


# ── Sysco Column-Level Extraction Prompt ──
SYSCO_COLUMN_PROMPT = """You are reading a Sysco invoice.

This invoice has a columnar layout. Read EACH COLUMN SEPARATELY for every line item row.

The columns are:
1. PACK — pack specification (e.g., "4/10 LB", "12/44 OZ", "1508X8X3"). NOT a quantity.
2. BRAND/DESCRIPTION — product name (e.g., "SYS CLS CHICKEN CVP BRST TENDER JUMBO")
3. ITEM CODE — Sysco product code
4. SUPC — supplier code
5. PRICE — unit price per case (e.g., 60.95, 34.95)
6. QTY — integer: quantity ordered/shipped (e.g., 1, 4, 10)
7. AMOUNT/TOTAL — extended total for the line (e.g., 60.95, 139.80)

CRITICAL RULES:
- The QTY column contains small integers (1-50 typically).
- PRICE and AMOUNT are dollar values (may or may not have $ prefix).
- PACK values like "4/10 LB" or "1508X8X3" are pack descriptions.
- Group header lines (e.g., "***POULTRY***") and group total lines should be SKIPPED.
- If a line says "FUEL SURCHARGE", "MISC CHARGES", or similar, it's a service line.

Return a JSON array where each element has EXACTLY these fields:
{
  "description": "product name",
  "pack_size": "pack specification as written",
  "item_code": "product code or empty",
  "qty": integer (quantity),
  "price": decimal (unit price, without $ sign),
  "total": decimal (line total / amount, without $ sign),
  "row_type": "product" or "service"
}

Return ONLY the JSON array. No markdown, no explanation."""


# ── Structural Enforcement ──

def enforce_pfg_structure(raw_items: list) -> list:
    """
    Apply PFG structural rules to GPT-5.2 column-level output.
    Key rule: quantity = SHIP column, NOT ORD, NOT WEIGHT, NOT PACK.
    """
    enforced = []
    for item in raw_items:
        ship = item.get("ship", 0)
        ord_val = item.get("ord", 0)
        weight = item.get("weight", 0)
        ext_price = item.get("ext_price", 0)
        price_lb = item.get("price_per_lb", 0)
        row_type = item.get("row_type", "product")

        # STRUCTURAL RULE 1: qty comes from SHIP only
        qty = ship if ship and ship > 0 else 0

        # STRUCTURAL RULE 2: If qty=0 but ord>0, item was not delivered
        if qty == 0 and ord_val > 0:
            qty = 0  # Not shipped = not delivered

        # STRUCTURAL RULE 3: Service rows get qty=1
        if row_type == "service":
            qty = 1

        # STRUCTURAL RULE 4: Validate ship is NOT a weight value
        # SHIP should be a small integer (1-200), WEIGHT is decimal > SHIP typically
        if qty > 200:
            # Likely WEIGHT leaked into SHIP
            qty = ord_val if ord_val and 0 < ord_val < 200 else 1

        # STRUCTURAL RULE 5: Price/total source integrity
        # For PFG: ext_price is always from the rightmost $ column
        # price_per_lb is always the second-rightmost $ column
        unit_price = price_lb if price_lb else 0
        total = ext_price if ext_price else 0

        enforced.append({
            "item_name": item.get("description", ""),
            "pack_size": item.get("pack_size", ""),
            "quantity": qty,
            "ord_qty": ord_val,
            "ship_qty": ship,
            "weight": weight,
            "unit_price": unit_price,
            "total": total,
            "row_type": row_type,
            # Validation
            "qty_source": "SHIP",
            "qty_validated": qty == ship if row_type == "product" else True,
        })
    return enforced


def enforce_sysco_structure(raw_items: list) -> list:
    """
    Apply Sysco structural rules to GPT-5.2 column-level output.
    """
    enforced = []
    for item in raw_items:
        qty = item.get("qty", 0)
        price = item.get("price", 0)
        total = item.get("total", 0)
        row_type = item.get("row_type", "product")

        # STRUCTURAL RULE 1: Math validation
        if qty > 0 and price > 0:
            computed = round(qty * price, 2)
            math_ok = abs(computed - total) < max(0.5, total * 0.02)
        else:
            computed = 0
            math_ok = row_type == "service"

        enforced.append({
            "item_name": item.get("description", ""),
            "pack_size": item.get("pack_size", ""),
            "quantity": qty,
            "unit_price": price,
            "total": total,
            "row_type": row_type,
            "math_check": f"{'PASS' if math_ok else 'FAIL'} (qty={qty} × price={price} = {computed}, declared={total})",
        })
    return enforced


async def run_spike():
    print("=" * 80)
    print("HYBRID SPIKE: GPT-5.2 Vision → Structural Enforcement")
    print("=" * 80)

    # ── PFG INVOICE ──
    print("\n\n" + "=" * 80)
    print("TEST 1: PFG Invoice #60919474011626 ($573.70)")
    print("Current extraction: ALL qty=1 (4 items)")
    print("=" * 80)

    with open("/app/backend/uploads/e23e24ad-c550-4f3b-8924-8728caaa9054.jpg", "rb") as f:
        pfg_b64 = base64.b64encode(f.read()).decode()

    pfg_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike-pfg-{uuid.uuid4()}",
        system_message="You read invoices with precise column-level accuracy. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    pfg_msg = UserMessage(
        text=PFG_COLUMN_PROMPT,
        file_contents=[ImageContent(image_base64=pfg_b64)]
    )

    print("\nStep 1: GPT-5.2 column-level extraction...")
    pfg_response = await pfg_chat.send_message(pfg_msg)

    # Parse JSON response
    try:
        # Strip markdown fences if present
        clean = pfg_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        pfg_raw = json.loads(clean)
        print(f"   GPT-5.2 returned {len(pfg_raw)} rows")
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw response: {pfg_response[:500]}")
        pfg_raw = []

    print("\n--- GPT-5.2 RAW COLUMN-LEVEL OUTPUT (PFG) ---")
    for i, item in enumerate(pfg_raw):
        desc = item.get('description', 'N/A')[:45]
        pack = item.get('pack_size', '')
        ord_v = item.get('ord', 0)
        ship = item.get('ship', 0)
        wt = item.get('weight', 0)
        plb = item.get('price_per_lb', 0)
        ext = item.get('ext_price', 0)
        rtype = item.get('row_type', 'product')
        print(f"  [{i}] {desc:45s} pack={str(pack):>10s} ORD={ord_v:>4} SHIP={ship:>4} WEIGHT={wt:>8.2f} $/LB=${plb:>7.2f} EXT=${ext:>10.2f} [{rtype}]")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (PFG) ---")
    pfg_enforced = enforce_pfg_structure(pfg_raw)
    pfg_sum = 0
    for i, item in enumerate(pfg_enforced):
        name = item['item_name'][:45]
        qty = item['quantity']
        up = item['unit_price']
        tot = item['total']
        pack = item['pack_size']
        src = item['qty_source']
        rtype = item['row_type']
        pfg_sum += tot
        print(f"  [{i}] {name:45s} qty={qty:>4} (from {src}) × ${up:>7.2f} = ${tot:>10.2f}  pack={str(pack):>10s} [{rtype}]")

    print(f"\n  Items sum: ${pfg_sum:.2f} vs Declared: $573.70")
    print(f"  Match: {'YES' if abs(pfg_sum - 573.70) < 0.10 else 'NO (diff=$' + f'{abs(pfg_sum - 573.70):.2f})'}")

    # Compare with current extraction
    print("\n--- COMPARISON WITH CURRENT STORED EXTRACTION ---")
    print("  CURRENT: 4 items, ALL qty=1, sum=$573.70")
    pfg_qty_fixed = any(item['quantity'] != 1 for item in pfg_enforced if item['row_type'] == 'product')
    print(f"  SPIKE:   {len(pfg_enforced)} items, qty varies: {pfg_qty_fixed}")
    if pfg_qty_fixed:
        print("  ✓ SUCCESS: qty no longer collapses to 1")
    else:
        print("  ✗ FAIL: qty still 1 for all items")

    # ── SYSCO INVOICE ──
    print("\n\n" + "=" * 80)
    print("TEST 2: Sysco Invoice #583635405 ($1,066.11)")
    print("Current extraction: 10 items, all correct, sum=$1,066.11")
    print("=" * 80)

    with open("/app/backend/uploads/95ebb38a-6d7e-4606-83f1-ec2a0f2a6d15.jpg", "rb") as f:
        sysco_b64 = base64.b64encode(f.read()).decode()

    sysco_chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"spike-sysco-{uuid.uuid4()}",
        system_message="You read invoices with precise column-level accuracy. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    sysco_msg = UserMessage(
        text=SYSCO_COLUMN_PROMPT,
        file_contents=[ImageContent(image_base64=sysco_b64)]
    )

    print("\nStep 1: GPT-5.2 column-level extraction...")
    sysco_response = await sysco_chat.send_message(sysco_msg)

    try:
        clean = sysco_response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        sysco_raw = json.loads(clean)
        print(f"   GPT-5.2 returned {len(sysco_raw)} rows")
    except json.JSONDecodeError as e:
        print(f"   JSON parse error: {e}")
        print(f"   Raw response: {sysco_response[:500]}")
        sysco_raw = []

    print("\n--- GPT-5.2 RAW COLUMN-LEVEL OUTPUT (Sysco) ---")
    for i, item in enumerate(sysco_raw):
        desc = item.get('description', 'N/A')[:45]
        pack = item.get('pack_size', '')
        qty = item.get('qty', 0)
        price = item.get('price', 0)
        total = item.get('total', 0)
        rtype = item.get('row_type', 'product')
        print(f"  [{i}] {desc:45s} pack={str(pack):>12s} qty={qty:>4} price=${price:>8.2f} total=${total:>10.2f} [{rtype}]")

    print("\n--- AFTER STRUCTURAL ENFORCEMENT (Sysco) ---")
    sysco_enforced = enforce_sysco_structure(sysco_raw)
    sysco_sum = 0
    for i, item in enumerate(sysco_enforced):
        name = item['item_name'][:45]
        qty = item['quantity']
        up = item['unit_price']
        tot = item['total']
        pack = item['pack_size']
        rtype = item['row_type']
        math = item['math_check']
        sysco_sum += tot
        print(f"  [{i}] {name:45s} qty={qty:>4} × ${up:>8.2f} = ${tot:>10.2f}  pack={str(pack):>12s} [{rtype}] {math}")

    print(f"\n  Items sum: ${sysco_sum:.2f} vs Declared: $1,066.11")
    print(f"  Match: {'YES' if abs(sysco_sum - 1066.11) < 0.10 else 'NO (diff=$' + f'{abs(sysco_sum - 1066.11):.2f})'}")

    # Summary
    print("\n\n" + "=" * 80)
    print("SPIKE RESULTS SUMMARY")
    print("=" * 80)
    print(f"  PFG:   {len(pfg_enforced)} items extracted, qty varies: {pfg_qty_fixed}, sum match: {abs(pfg_sum - 573.70) < 0.10}")
    print(f"  Sysco: {len(sysco_enforced)} items extracted, sum match: {abs(sysco_sum - 1066.11) < 0.10}")

    # Check success criteria
    print("\n  SUCCESS CRITERIA:")
    print(f"  1. PFG qty no longer collapses to 1: {'PASS' if pfg_qty_fixed else 'FAIL'}")
    sysco_math_pass = all('PASS' in item['math_check'] for item in sysco_enforced)
    print(f"  2. Sysco row isolation and column assignment stable: {'PASS' if sysco_math_pass else 'FAIL'}")
    print(f"  3. No regression in totals:")
    print(f"     PFG:   ${pfg_sum:.2f} vs $573.70 → {'PASS' if abs(pfg_sum - 573.70) < 1 else 'FAIL'}")
    print(f"     Sysco: ${sysco_sum:.2f} vs $1,066.11 → {'PASS' if abs(sysco_sum - 1066.11) < 1 else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(run_spike())
