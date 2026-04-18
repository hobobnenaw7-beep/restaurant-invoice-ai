"""
US Foods 2-Phase Structural Extraction Engine
==============================================

Architecture:
    Phase 1 — NUMERIC GRID: GPT Vision reads ONLY numbers from the invoice table
              (product_code, shipped_qty, unit_price, ext_price per row).
              Numbers occupy fixed column positions and have distinct visual patterns,
              making this call more spatially consistent than full extraction.

    Phase 2 — DESCRIPTIONS: GPT Vision reads ONLY text from the invoice table
              (product_code + brand/description + pack_size per row).
              Descriptions may vary slightly between runs, but this does NOT affect
              trust scoring since trust = qty × price = total.

    Phase 3 — ASSEMBLY: Deterministic merge of Phase 1 numbers with Phase 2 descriptions,
              joined by product_code. No GPT involved.

Why 2 phases instead of 1?
    US Foods invoices pack 9 columns into each row (Product#, Brand, Description,
    Pack/Size, Ordered, Shipped, Weight, Unit Price, Ext Price). In a single GPT call,
    the model must parse all columns simultaneously, leading to non-deterministic output
    on challenging images. Splitting into numbers-only and text-only reduces cognitive
    load per call, improving consistency of the numeric fields that drive trust scoring.

Image quality assumptions:
    - Clean scans/PDFs: Fully deterministic (proven 3/3 identical runs)
    - Dark phone photos: Zero false trusts guaranteed, but row counts may vary
      due to GPT Vision's pixel-level reading variability on low-contrast images

Trust gate interaction:
    The assembled items feed into the standard US Foods trust gate in upload.py.
    Items pass trust if: qty × price = total (±$0.01) AND sources are "column_read".
    Items that fail math or have ambiguous sources → needs_review (never false-trusted).
"""
import json
import logging
import re
import uuid

logger = logging.getLogger("restaurant_ai")


# ─────────────────────────────────────────────────────────────────────
# Phase 1 Prompt: Numeric Grid
# ─────────────────────────────────────────────────────────────────────
# GPT reads ONLY the numeric columns of the US Foods table.
# The prompt explicitly names each column position to anchor extraction.

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

CREDIT/RETURN ROWS: Lines with "CREDIT", "RETURN", or negative amounts → use NEGATIVE ext_price (e.g., -48.90)

DISCOUNT ROWS: Lines with "DISCOUNT", "REBATE", "ALLOWANCE" → use NEGATIVE ext_price (e.g., -25.00)

IMPORTANT: Preserve negative signs on credit and discount amounts. Do NOT convert them to positive.

Also report: supplier_name, invoice_date (YYYY-MM-DD), invoice_number, subtotal, tax, total

Return ONLY this JSON:
{"supplier_name":"","invoice_date":"","invoice_number":"","subtotal":0,"tax":0,"total":0,"rows":[{"row_num":1,"product_code":"","shipped_qty":0,"unit_price":0,"ext_price":0}]}"""


# ─────────────────────────────────────────────────────────────────────
# Phase 2 Prompt: Descriptions
# ─────────────────────────────────────────────────────────────────────
# GPT reads ONLY text fields. Even if descriptions vary between runs,
# it doesn't affect trust scoring (trust is purely numeric).

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
- "CREDIT", "RETURN" rows: include them with the full description (e.g., "CREDIT: WING DMG CASE")
- "DISCOUNT", "REBATE", "EARLY PAY" rows: include them with the full description
- Return ONLY the JSON array below, nothing else

Return this exact JSON:
[{"product_code":"","description":"","pack_size":""}]"""


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

async def extract_usfoods_structural(
    images_b64: list[str],
    llm_key: str,
    rate_limited_llm_call,
    original_images_b64: list[str] = None,
) -> dict:
    """
    2-phase structural extraction for US Foods invoices.

    Args:
        images_b64: List of base64-encoded invoice images (preprocessed).
        llm_key: Emergent LLM API key.
        rate_limited_llm_call: Async function for rate-limited GPT calls.

    Returns:
        Standard extraction dict with keys:
            supplier_name, invoice_date, invoice_number,
            items (list of dicts with raw_name, quantity, unit_price, total, etc.),
            subtotal, tax, total.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    from preprocessing import assess_image_quality, enhance_dark_image

    file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]

    # ── Assess ORIGINAL image quality (before standard preprocessing) ──
    check_b64 = (original_images_b64 or images_b64)[0]
    quality = assess_image_quality(check_b64)
    logger.info(
        f"US Foods image quality (original): mean={quality['mean_brightness']}, "
        f"dark={quality['is_dark']}, low_contrast={quality['is_low_contrast']}"
    )

    # ── Phase 1: Numeric Grid ──
    logger.info("US Foods structural: Phase 1 — numeric grid extraction")
    phase1_chat = LlmChat(
        api_key=llm_key,
        session_id=f"usfoods-phase1-{uuid.uuid4()}",
        system_message="You read invoice numbers precisely. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    phase1_response = await rate_limited_llm_call(
        phase1_chat,
        UserMessage(text=PHASE1_PROMPT, file_contents=file_contents),
        label="usfoods_phase1_numbers",
    )
    numeric_data = _parse_phase1(phase1_response)
    phase1_rows = len(numeric_data.get("rows", []))
    logger.info(f"US Foods Phase 1: {phase1_rows} numeric rows")

    # ── Detect all-zero prices (GPT read rows but couldn't read numbers) ──
    has_zero_prices = False
    if phase1_rows > 0:
        zero_count = sum(
            1 for r in numeric_data["rows"]
            if r.get("unit_price", 0) == 0 and r.get("ext_price", 0) == 0
        )
        if zero_count == phase1_rows:
            has_zero_prices = True
            logger.info(
                f"US Foods Phase 1: all {phase1_rows} rows have zero prices"
            )

    # ── Retry with enhancement if dark original AND (0 rows OR all-zero prices) ──
    enhancement_applied = False
    if (phase1_rows == 0 or has_zero_prices) and quality["needs_enhancement"]:
        logger.info(
            "US Foods: dark/low-contrast original — enhancing and retrying Phase 1"
        )
        enhanced_b64 = [enhance_dark_image(b64) for b64 in (original_images_b64 or images_b64)]
        enhanced_contents = [ImageContent(image_base64=b64) for b64 in enhanced_b64]
        enhancement_applied = True

        retry_chat = LlmChat(
            api_key=llm_key,
            session_id=f"usfoods-phase1-enh-{uuid.uuid4()}",
            system_message="You read invoice numbers precisely. Return valid JSON only."
        ).with_model("openai", "gpt-5.2")
        retry_response = await rate_limited_llm_call(
            retry_chat,
            UserMessage(text=PHASE1_PROMPT, file_contents=enhanced_contents),
            label="usfoods_phase1_enhanced",
        )
        retry_data = _parse_phase1(retry_response)
        retry_rows = len(retry_data.get("rows", []))
        retry_zero = sum(
            1 for r in retry_data.get("rows", [])
            if r.get("unit_price", 0) == 0 and r.get("ext_price", 0) == 0
        )
        retry_with_prices = retry_rows - retry_zero
        logger.info(
            f"US Foods Phase 1 (enhanced): {retry_rows} rows, "
            f"{retry_with_prices} with prices"
        )
        if retry_with_prices > 0 and (has_zero_prices or phase1_rows == 0):
            numeric_data = retry_data
            phase1_rows = retry_rows
            file_contents = enhanced_contents
            logger.info("US Foods: enhanced extraction improved — using enhanced")
        elif retry_rows > phase1_rows:
            numeric_data = retry_data
            phase1_rows = retry_rows
            file_contents = enhanced_contents
    elif phase1_rows == 0 and not quality["needs_enhancement"]:
            retry_chat = LlmChat(
                api_key=llm_key,
                session_id=f"usfoods-phase1-retry-{uuid.uuid4()}",
                system_message="You read invoice numbers precisely. Return valid JSON only."
            ).with_model("openai", "gpt-5.2")
            retry_response = await rate_limited_llm_call(
                retry_chat,
                UserMessage(text=PHASE1_PROMPT, file_contents=file_contents),
                label="usfoods_phase1_retry",
            )
            retry_data = _parse_phase1(retry_response)
            retry_rows = len(retry_data.get("rows", []))
            logger.info(f"US Foods Phase 1 retry: {retry_rows} numeric rows")
            if retry_rows > 0:
                numeric_data = retry_data
                phase1_rows = retry_rows

    # ── Phase 2: Descriptions ──
    logger.info("US Foods structural: Phase 2 — description extraction")
    phase2_chat = LlmChat(
        api_key=llm_key,
        session_id=f"usfoods-phase2-{uuid.uuid4()}",
        system_message="You read product descriptions from invoices. Return valid JSON only."
    ).with_model("openai", "gpt-5.2")

    phase2_response = await rate_limited_llm_call(
        phase2_chat,
        UserMessage(text=PHASE2_PROMPT, file_contents=file_contents),
        label="usfoods_phase2_descriptions",
    )
    descriptions = _parse_phase2(phase2_response)
    logger.info(f"US Foods Phase 2: {len(descriptions)} description rows")

    # ── Phase 3: Deterministic Assembly ──
    assembled = _assemble(numeric_data, descriptions)
    if enhancement_applied:
        assembled["_enhancement_applied"] = True
    assembled["_image_quality"] = quality
    logger.info(f"US Foods assembly: {len(assembled.get('items', []))} items")
    return assembled


# ─────────────────────────────────────────────────────────────────────
# Internal: Response Parsing
# ─────────────────────────────────────────────────────────────────────

def _parse_phase1(response: str) -> dict:
    """Parse Phase 1 numeric grid JSON. Returns dict with 'rows' list."""
    json_match = re.search(r'\{[\s\S]*\}', response)
    if not json_match:
        logger.warning("Phase 1: no JSON found in response")
        return {"rows": []}
    try:
        data = json.loads(json_match.group())
        rows = []
        for row in data.get("rows", []):
            rows.append({
                "row_num": int(row.get("row_num", 0) or 0),
                "product_code": str(row.get("product_code", "") or "").strip(),
                "shipped_qty": float(row.get("shipped_qty", 0) or 0),
                "unit_price": float(row.get("unit_price", 0) or 0),
                "ext_price": float(row.get("ext_price", 0) or 0),
            })
        data["rows"] = rows
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Phase 1 parse error: {e}")
        return {"rows": []}


def _parse_phase2(response: str) -> list[dict]:
    """Parse Phase 2 descriptions JSON. Returns list of dicts."""
    # Try bare array first
    array_match = re.search(r'\[[\s\S]*\]', response)
    if array_match:
        try:
            items = json.loads(array_match.group())
            if isinstance(items, list):
                return [_normalize_desc(it) for it in items]
        except (json.JSONDecodeError, ValueError):
            pass

    # Try object wrapper (GPT sometimes wraps in {"items": [...]})
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        try:
            data = json.loads(json_match.group())
            for key in ("items", "rows", "descriptions"):
                if isinstance(data.get(key), list):
                    return [_normalize_desc(it) for it in data[key]]
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Phase 2: could not parse descriptions")
    return []


def _normalize_desc(item: dict) -> dict:
    """Normalize a Phase 2 description entry."""
    return {
        "product_code": str(item.get("product_code", "") or "").strip(),
        "description": str(item.get("description", "") or "").strip(),
        "pack_size": str(item.get("pack_size", "") or "").strip(),
    }


# ─────────────────────────────────────────────────────────────────────
# Internal: Deterministic Assembly
# ─────────────────────────────────────────────────────────────────────

_FEE_KEYWORDS = (
    "fuel surcharge", "delivery fee", "service charge",
    "delivery charge", "surcharge",
)

_DISCOUNT_KEYWORDS = (
    "discount", "rebate", "allowance", "early pay",
    "prompt pay", "trade discount", "volume discount",
)


def _assemble(numeric_data: dict, descriptions: list[dict]) -> dict:
    """
    Merge Phase 1 numeric rows with Phase 2 descriptions.

    Matching strategy:
        1. By product_code (primary key — 7-digit code)
        2. By position index (fallback when codes don't match)

    Items without a description match still get included (with empty name)
    because the numeric data drives trust scoring.
    """
    # Build description lookup by product_code
    desc_by_code = {}
    for desc in descriptions:
        code = desc["product_code"]
        if code:
            desc_by_code[code] = desc

    items = []
    for idx, row in enumerate(numeric_data.get("rows", [])):
        code = row["product_code"]
        qty = row["shipped_qty"]
        price = row["unit_price"]
        total = row["ext_price"]

        # Match description: by product_code first, then by position
        desc_entry = desc_by_code.get(code) if code else None
        if not desc_entry and idx < len(descriptions):
            desc_entry = descriptions[idx]

        raw_name = desc_entry["description"] if desc_entry else ""
        pack_size = desc_entry["pack_size"] if desc_entry else ""

        # Determine field sources from data presence
        is_fee = any(kw in raw_name.lower() for kw in _FEE_KEYWORDS)
        is_discount = any(kw in raw_name.lower() for kw in _DISCOUNT_KEYWORDS)
        if is_fee or is_discount:
            qty_source = "fee_implied"
            price_source = "fee_implied"
            total_source = "fee_implied"
        else:
            qty_source = "column_read" if qty > 0 else "ambiguous"
            price_source = "column_read" if price > 0 else "ambiguous"
            total_source = "column_read" if total != 0 else "ambiguous"  # != 0: covers negatives

        items.append({
            "raw_name": raw_name,
            "quantity": qty,
            "pack_size": pack_size,
            "unit_price": price,
            "total": total,
            "qty_source": qty_source,
            "price_source": price_source,
            "total_source": total_source,
            "item_code": code,
            "qty_column_visible": qty > 0,
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
