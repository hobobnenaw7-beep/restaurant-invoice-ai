"""
US Foods Structural Extraction Engine
======================================
2-phase GPT Vision extraction designed for determinism:

Phase 1 — NUMERIC GRID: GPT reads ONLY numbers (product_code, shipped_qty, unit_price, ext_price)
Phase 2 — DESCRIPTIONS: GPT reads ONLY text (product_code + description)
Phase 3 — ASSEMBLY: Deterministic merge by product_code + trust gate

Why 2 phases?
- Single-call extraction asks GPT to parse 9 columns simultaneously → non-deterministic
- Splitting into numbers-only and text-only reduces cognitive load per call
- Numbers have fixed spatial positions → more consistent extraction
- Description errors don't affect trust scoring (trust = qty × price = total)
"""
import json
import logging
import re
import uuid

logger = logging.getLogger("restaurant_ai")


# ── Phase 1: Numeric Grid Extraction ──
# Simplified prompt: ask GPT to READ the table as a grid, one row per line.
# This is closer to how GPT Vision naturally processes tables.

PHASE1_PROMPT = """You are reading a US Foods restaurant purchase invoice. Extract the NUMERIC DATA from the product table.

Read the table from top to bottom. For each product line, report these 4 numbers:
1. product_code — the 7-digit number at the start of the row
2. shipped_qty — the integer from the SHIPPED column (small number, usually 1-50)
3. unit_price — the dollar amount from the UNIT PRICE column
4. ext_price — the dollar amount from the EXTENSION column (rightmost dollar column)

CRITICAL COLUMN RULES:
- SHIPPED is the quantity column (small integers). Do NOT use ORDERED or WEIGHT.
- WEIGHT has decimal values like 24.00 or 40.00 — this is NOT the quantity
- UNIT PRICE is the second-to-last dollar column
- EXTENSION / EXT PRICE is the last dollar column (rightmost)
- If any number is unreadable, use 0

SKIP these rows:
- SUBTOTAL, TOTAL, AMOUNT DUE, TAX (summary rows)
- Section headers like DRY, FROZEN, REFRIGERATED

FEE ROWS: "FUEL SURCHARGE" or "DELIVERY FEE" → use shipped_qty=1

Also report: supplier_name, invoice_date (YYYY-MM-DD), invoice_number, subtotal, tax, total

Return ONLY this JSON:
{"supplier_name":"","invoice_date":"","invoice_number":"","subtotal":0,"tax":0,"total":0,"rows":[{"row_num":1,"product_code":"","shipped_qty":0,"unit_price":0,"ext_price":0}]}"""


# ── Phase 2: Description Extraction ──

PHASE2_PROMPT = """You are reading a US Foods restaurant purchase invoice. Your ONLY task is to extract the PRODUCT DESCRIPTIONS from the invoice table.

For each product row, extract:
- product_code: the 7-digit product number (same as the leftmost column)
- description: the full product description (combine Brand + Description columns)
- pack_size: the pack/size specification (e.g., "4/5 LB", "6/10 CT") — copy verbatim

RULES:
- Do NOT read any dollar amounts or quantities — only text fields
- Do NOT include summary rows (SUBTOTAL, TOTAL)
- Do NOT include section headers
- "FUEL SURCHARGE", "DELIVERY FEE" rows: use description="FUEL SURCHARGE" etc.
- Return ONLY the JSON array below, nothing else

Return this exact JSON:
[{"product_code":"","description":"","pack_size":""}]"""


async def extract_usfoods_structural(
    images_b64: list[str],
    llm_key: str,
    rate_limited_llm_call,
    vendor_hint: str = "",
    builtin_vendor_hint: str = "",
) -> dict:
    """
    2-phase structural extraction for US Foods invoices.
    Returns a standard extracted dict with items[].
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Numeric Grid
    # ═══════════════════════════════════════════════════════════
    logger.info("US Foods structural: Phase 1 — numeric grid extraction")

    phase1_chat = LlmChat(
        api_key=llm_key,
        session_id=f"usfoods-phase1-{uuid.uuid4()}",
        system_message="You read invoice numbers precisely. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    phase1_msg = UserMessage(text=PHASE1_PROMPT, file_contents=file_contents)
    phase1_response = await rate_limited_llm_call(
        phase1_chat, phase1_msg, label="usfoods_phase1_numbers"
    )

    numeric_data = _parse_phase1(phase1_response)
    logger.info(
        f"US Foods Phase 1: {len(numeric_data.get('rows', []))} numeric rows extracted"
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Descriptions
    # ═══════════════════════════════════════════════════════════
    logger.info("US Foods structural: Phase 2 — description extraction")

    phase2_chat = LlmChat(
        api_key=llm_key,
        session_id=f"usfoods-phase2-{uuid.uuid4()}",
        system_message="You read product descriptions from invoices. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    phase2_msg = UserMessage(text=PHASE2_PROMPT, file_contents=file_contents)
    phase2_response = await rate_limited_llm_call(
        phase2_chat, phase2_msg, label="usfoods_phase2_descriptions"
    )

    descriptions = _parse_phase2(phase2_response)
    logger.info(
        f"US Foods Phase 2: {len(descriptions)} description rows extracted"
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Deterministic Assembly
    # ═══════════════════════════════════════════════════════════
    assembled = _assemble(numeric_data, descriptions)
    logger.info(
        f"US Foods structural assembly: {len(assembled.get('items', []))} items"
    )

    return assembled


def _parse_phase1(response: str) -> dict:
    """Parse Phase 1 numeric grid response."""
    json_match = re.search(r'\{[\s\S]*\}', response)
    if not json_match:
        logger.warning("Phase 1: no JSON found in response")
        return {"rows": []}

    try:
        data = json.loads(json_match.group())
        # Validate rows structure
        rows = data.get("rows", [])
        valid_rows = []
        for row in rows:
            valid_rows.append({
                "row_num": int(row.get("row_num", 0) or 0),
                "product_code": str(row.get("product_code", "") or "").strip(),
                "shipped_qty": float(row.get("shipped_qty", 0) or 0),
                "unit_price": float(row.get("unit_price", 0) or 0),
                "ext_price": float(row.get("ext_price", 0) or 0),
            })
        data["rows"] = valid_rows
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Phase 1 JSON parse error: {e}")
        return {"rows": []}


def _parse_phase2(response: str) -> list[dict]:
    """Parse Phase 2 descriptions response."""
    # Try array first
    array_match = re.search(r'\[[\s\S]*\]', response)
    if array_match:
        try:
            items = json.loads(array_match.group())
            if isinstance(items, list):
                return [
                    {
                        "product_code": str(it.get("product_code", "") or "").strip(),
                        "description": str(it.get("description", "") or "").strip(),
                        "pack_size": str(it.get("pack_size", "") or "").strip(),
                    }
                    for it in items
                ]
        except (json.JSONDecodeError, ValueError):
            pass

    # Try object with array inside
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            for key in ("items", "rows", "descriptions"):
                if isinstance(data.get(key), list):
                    return [
                        {
                            "product_code": str(it.get("product_code", "") or "").strip(),
                            "description": str(it.get("description", "") or "").strip(),
                            "pack_size": str(it.get("pack_size", "") or "").strip(),
                        }
                        for it in data[key]
                    ]
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Phase 2: could not parse descriptions")
    return []


def _assemble(numeric_data: dict, descriptions: list[dict]) -> dict:
    """
    Deterministic assembly: merge numeric rows with descriptions by product_code.
    Items without a description match still get included (with empty name).
    """
    # Build description lookup by product_code
    desc_by_code = {}
    for desc in descriptions:
        code = desc["product_code"]
        if code:
            desc_by_code[code] = desc

    # Also build a by-position lookup for fallback matching
    desc_by_position = {i: desc for i, desc in enumerate(descriptions)}

    items = []
    rows = numeric_data.get("rows", [])

    for idx, row in enumerate(rows):
        code = row["product_code"]
        qty = row["shipped_qty"]
        price = row["unit_price"]
        total = row["ext_price"]

        # Match description by product_code first, then by position
        desc_entry = desc_by_code.get(code) if code else None
        if not desc_entry and idx < len(descriptions):
            desc_entry = desc_by_position.get(idx)

        raw_name = desc_entry["description"] if desc_entry else ""
        pack_size = desc_entry["pack_size"] if desc_entry else ""

        # Determine qty_source based on value
        qty_source = "column_read" if qty > 0 else "ambiguous"
        price_source = "column_read" if price > 0 else "ambiguous"
        total_source = "column_read" if total > 0 else "ambiguous"

        # Detect fee rows
        name_lower = raw_name.lower()
        is_fee = any(kw in name_lower for kw in (
            "fuel surcharge", "delivery fee", "service charge",
            "delivery charge", "surcharge",
        ))

        items.append({
            "raw_name": raw_name,
            "quantity": qty,
            "pack_size": pack_size,
            "unit_price": price,
            "total": total,
            "qty_source": "fee_implied" if is_fee else qty_source,
            "price_source": "fee_implied" if is_fee else price_source,
            "total_source": "fee_implied" if is_fee else total_source,
            "item_code": code,
            "qty_column_visible": qty > 0,
            "_extraction_method": "usfoods_structural_2phase",
        })

    return {
        "supplier_name": str(numeric_data.get("supplier_name", "") or "").strip(),
        "invoice_date": str(numeric_data.get("invoice_date", "") or "").strip(),
        "invoice_number": str(numeric_data.get("invoice_number", "") or "").strip(),
        "items": items,
        "subtotal": float(numeric_data.get("subtotal", 0) or 0),
        "tax": float(numeric_data.get("tax", 0) or 0),
        "total": float(numeric_data.get("total", 0) or 0),
    }
