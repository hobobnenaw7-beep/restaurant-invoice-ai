"""
US Foods Raw Extraction Diagnostic
Sends a US Foods image and captures the RAW GPT response BEFORE any backend processing.
"""
import asyncio
import base64
import json
import os
import sys
sys.path.insert(0, "/app/backend")

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent


async def raw_extract(image_path: str):
    """Send image to GPT with the current generic prompt and capture raw response."""
    LLM_KEY = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("LLM_KEY") or ""

    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()

    # Use the EXACT same generic prompt the pipeline uses for non-Sysco vendors
    prompt = """You are an expert at reading restaurant purchase invoices from camera phone photos. Use semantic understanding to interpret the document structure even if the image has noise, skew, shadows, or perspective distortion.

Extract ALL data into this exact JSON format:
{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0,"qty_source":"","price_source":"","total_source":"","item_code":""}],"subtotal":0,"tax":0,"total":0}

CRITICAL rules for line items:
- Scan the HEADER ROW to dynamically identify column positions
- In columnar layouts, match quantity + unit price + total from the same row
- Use 0 for any truly missing numeric values
- Extract item_code from the ITEM/CODE column if visible
- Do NOT treat section headers or category dividers as line items
- Do NOT default quantity to 1 when uncertain — read the QTY column

NUMERIC FIELD SOURCE (for each item):
- qty_source: "column_read" / "inferred" / "ambiguous"
- price_source: "column_read" / "inferred" / "ambiguous"
- total_source: "column_read" / "inferred" / "ambiguous"

- Return ONLY the JSON object, no other text.

US FOODS INVOICE — SEMANTIC EXTRACTION GUIDE:
COLUMN LAYOUT (identify from the HEADER ROW):
- NUMBER/ITEM#: 7-digit product code
- BRAND: brand name
- DESCRIPTION: product name
- PACK/SIZE: pack specification. NOT the quantity.
- ORDERED: quantity ordered (integer)
- SHIPPED: quantity actually delivered. THIS IS the correct quantity to extract.
- WEIGHT: total weight in pounds (decimal). NOT the quantity.
- PRICE/UNIT PRICE: unit price per case
- EXTENSION/EXT PRICE: extended total for the line

CRITICAL US FOODS RULES:
1. ALWAYS extract item_code from the NUMBER column
2. quantity MUST come from SHIPPED column, NOT from ORDERED, PACK, or WEIGHT
3. WEIGHT column shows total pounds — do NOT use as quantity
4. Description and Brand may appear merged — extract the full text as raw_name"""

    chat_obj = LlmChat(api_key=LLM_KEY, session_id=f"diag-usfoods", system_message="You read invoices. Return ONLY valid JSON.").with_model("openai", "gpt-5.2")
    user_msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=img_data)])
    response = await chat_obj.send_message(user_msg)
    return response


async def main():
    image_path = "/app/backend/uploads/receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg"

    print(f"Image: {os.path.basename(image_path)}")
    print(f"Size: {os.path.getsize(image_path) / 1024:.0f} KB")
    print()

    raw = await raw_extract(image_path)

    # Parse and analyze
    try:
        # Strip markdown code block if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Raw response (first 2000 chars):\n{raw[:2000]}")
        return

    items = data.get("items", [])
    print(f"Supplier: {data.get('supplier_name', '?')}")
    print(f"Invoice: {data.get('invoice_number', '?')}")
    print(f"Total items: {len(items)}")
    print(f"Subtotal: {data.get('subtotal', 0)}")
    print(f"Tax: {data.get('tax', 0)}")
    print(f"Total: {data.get('total', 0)}")
    print()

    # Categorize items
    has_price = 0
    no_price = 0
    has_total = 0
    no_total = 0
    has_item_code = 0

    print(f"{'#':>3} {'Name':45s} {'Code':>8s} {'Qty':>5s} {'QSrc':>12s} {'Price':>8s} {'PSrc':>12s} {'Total':>8s} {'TSrc':>12s}")
    print(f"{'─'*3} {'─'*45} {'─'*8} {'─'*5} {'─'*12} {'─'*8} {'─'*12} {'─'*8} {'─'*12}")

    for idx, it in enumerate(items):
        name = (it.get("raw_name") or "")[:45]
        code = (it.get("item_code") or "")[:8]
        qty = it.get("quantity", 0)
        price = it.get("unit_price", 0)
        total = it.get("total", 0)
        qs = (it.get("qty_source") or "?")[:12]
        ps = (it.get("price_source") or "?")[:12]
        ts = (it.get("total_source") or "?")[:12]

        price_str = f"{price:.2f}" if price else "0"
        total_str = f"{total:.2f}" if total else "0"

        marker = ""
        if price == 0 and total == 0:
            marker = " ← ZERO"
        elif price == 0:
            marker = " ← NO PRICE"
        elif total == 0:
            marker = " ← NO TOTAL"

        print(f"{idx+1:>3} {name:45s} {code:>8s} {qty:>5} {qs:>12s} {price_str:>8s} {ps:>12s} {total_str:>8s} {ts:>12s}{marker}")

        if price > 0:
            has_price += 1
        else:
            no_price += 1
        if total > 0:
            has_total += 1
        else:
            no_total += 1
        if code:
            has_item_code += 1

    print()
    print(f"Items with price > 0: {has_price}/{len(items)}")
    print(f"Items with total > 0: {has_total}/{len(items)}")
    print(f"Items with item_code: {has_item_code}/{len(items)}")
    print(f"Items with price=0 AND total=0: {sum(1 for it in items if it.get('unit_price', 0) == 0 and it.get('total', 0) == 0)}/{len(items)}")


if __name__ == "__main__":
    asyncio.run(main())
