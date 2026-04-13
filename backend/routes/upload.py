from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List
import uuid
import re
import json
import base64
import io
from datetime import datetime, timezone

from core.database import db, UPLOADS_DIR, LLM_KEY, logger
from core.auth import get_user

router = APIRouter()


# PFG-specific keywords that indicate weight/pack info leaked into item name
_PFG_WEIGHT_PATTERNS = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*(LB|LBS|OZ|GM|KG)\b',
    re.IGNORECASE,
)
_PFG_PACK_IN_NAME = re.compile(
    r'\b\d+/\d+\s*(LB|LBS|OZ|CT|EA|GAL)\b',
    re.IGNORECASE,
)

_SERVICE_KW = {"delivery", "fuel", "surcharge", "credit", "discount", "freight",
               "handling", "service", "charge", "fee", "adjustment", "return",
               "deposit", "rebate", "refund", "coupon", "promo", "minimum"}


# ---------------------------------------------------------------------------
# Row Type Classification
# ---------------------------------------------------------------------------
# Classifies each extracted row BEFORE any numeric validation.
# Only 'line_item' and 'fee' rows participate in numeric trust logic.

_GROUP_TOTAL_PATTERNS = re.compile(
    r'(group\s*total|subtotal|sub\s*total|section\s*total|category\s*total)',
    re.IGNORECASE,
)
_SECTION_MARKER_PATTERNS = re.compile(
    r'^\*{2,}.*\*{2,}$',  # ***POULTRY***, ***FROZEN***, etc.
)
_TOTAL_LINE_PATTERNS = re.compile(
    r'^(total|grand\s*total|invoice\s*total|order\s*total|net\s*total)$',
    re.IGNORECASE,
)
_TAX_PATTERNS = re.compile(
    r'\b(sales\s*tax|tax|hst|gst|vat)\b',
    re.IGNORECASE,
)


def _classify_row_type(item: dict) -> str:
    """
    Classify a row into one of:
      line_item    — actual product line
      group_total  — section/group subtotal (e.g., "GROUP TOTAL****")
      subtotal     — invoice subtotal line
      tax          — tax line
      fee          — service fee (fuel surcharge, delivery)
      header       — section header text (no numeric value)
      unknown      — can't determine

    Rules applied in priority order (first match wins).
    """
    name = (item.get("raw_name") or "").strip()
    name_lower = name.lower()
    name_words = set(name_lower.split())
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)

    # Rule 1: GROUP TOTAL / SUBTOTAL in description
    if _GROUP_TOTAL_PATTERNS.search(name_lower):
        return "group_total"

    # Rule 2: Standalone TOTAL line
    # Strip asterisks and whitespace for matching
    name_cleaned = re.sub(r'[\*\s]+', ' ', name).strip()
    if _TOTAL_LINE_PATTERNS.match(name_cleaned):
        return "subtotal"

    # Rule 2b: ORDER SUMMARY / INVOICE SUMMARY lines
    if re.search(r'(order\s*summary|invoice\s*summary|payment\s*summary)', name_lower):
        return "subtotal"

    # Rule 3: Section markers (***POULTRY***, ***FROZEN***)
    if _SECTION_MARKER_PATTERNS.match(name.replace(" ", "")):
        return "header"

    # Rule 4: Tax line
    if _TAX_PATTERNS.search(name_lower) and len(name_words) <= 5:
        return "tax"

    # Rule 5: Service fee — description contains service keywords
    # Handle both short ("FUEL SURCHARGE") and compound ("MISC CHARGES - CHGS FOR FUEL SURCHARGE")
    if name_words & _SERVICE_KW:
        # Short description with service keywords → definitely fee
        if len(name_words) <= 4:
            return "fee"
        # Longer but dominated by service keywords (>50% are service-related)
        service_word_count = len(name_words & _SERVICE_KW)
        if service_word_count >= 2:
            return "fee"

    # Rule 6: Description contains embedded group total text
    # e.g., "CANNED & DRY GROUP TOTAL**** SYS CLS DRINK MIX"
    # or "PAPER & DISP**GROUP TOTAL****"
    if "group total" in name_lower or "group_total" in name_lower:
        return "group_total"

    # Rule 7: No name but has a total → likely a summary row
    if not name and total > 0 and qty <= 1:
        return "unknown"

    # Rule 8: qty missing (0) and price == total → likely summary, not line item
    if qty == 0 and price > 0 and total > 0 and abs(price - total) < 0.01:
        # Could be a single-qty item, but without a clear product name pattern
        # this is suspicious — mark as unknown for further review
        if len(name_words) <= 3:
            return "unknown"

    # Default: line_item
    return "line_item"


def _classify_all_row_types(items: list) -> None:
    """
    Classify all rows and set row_type on each item.
    Must run BEFORE any numeric validation or trust gates.
    """
    for item in items:
        item["row_type"] = _classify_row_type(item)


# ---------------------------------------------------------------------------
# Numeric Field Source Validation — System-Level Overrides
# ---------------------------------------------------------------------------
# GPT returns qty_source, price_source, total_source as hints.
# These heuristics OVERRIDE GPT claims when structural patterns indicate
# the field was NOT reliably read from a column.

_VALID_SOURCES = {"column_read", "inferred", "ambiguous"}


def _validate_numeric_field_sources(items: list) -> None:
    """
    System-level validation of per-field source confidence.
    Runs AFTER individual item scoring but BEFORE vendor-specific validation.

    GPT-reported sources are treated as HINTS — system heuristics can
    downgrade 'column_read' to 'ambiguous' when patterns indicate
    the value was not reliably read.

    Mutates items in place: sets qty_source, price_source, total_source,
    numeric_failure_category, and may downgrade confidence_level.
    """
    if not items:
        return

    # Step 0: Normalize GPT-reported sources (handle missing/invalid)
    for it in items:
        for field in ("qty_source", "price_source", "total_source"):
            val = (it.get(field) or "").strip().lower()
            if val not in _VALID_SOURCES:
                it[field] = "ambiguous"  # Unknown/missing → treat as ambiguous

    # Step 1: Detect all-qty-1 pattern
    # If ALL product items have qty=1, it's a strong signal the QTY column
    # was not actually read — GPT defaulted everything to 1.
    _detect_all_qty_one_pattern(items)

    # Step 2: Per-item heuristic checks
    for it in items:
        _validate_single_item_sources(it)

    # Step 3: Assign numeric failure categories
    for it in items:
        _assign_numeric_failure_category(it)

    # Step 4: Apply trust gate — no row trusted unless all sources confirmed
    for it in items:
        _apply_numeric_trust_gate(it)


def _detect_all_qty_one_pattern(items: list) -> None:
    """
    If all line_item rows have qty=1 AND none of them have qty_column_visible=true,
    downgrade ALL qty_source to 'ambiguous' — strong signal GPT defaulted quantities.

    If ANY item has qty_column_visible=true, skip this bulk downgrade — the LLM
    confirmed visual presence of digits in the QTY column, so qty=1 is likely real.
    """
    product_items = [it for it in items if it.get("row_type") == "line_item"]

    if len(product_items) < 3:
        return  # Too few items to detect pattern

    all_qty_one = all(float(it.get("quantity", 0) or 0) == 1.0 for it in product_items)
    if not all_qty_one:
        return

    # Check if ANY item has qty_column_visible=true — if so, the QTY column exists
    any_visible = any(it.get("qty_column_visible") is True for it in product_items)
    if any_visible:
        # LLM confirmed QTY column visibility on at least one row — don't bulk-downgrade
        for it in product_items:
            it.setdefault("_source_overrides", []).append(
                "system: all-qty-1 pattern detected, but qty_column_visible confirmed — keeping sources"
            )
        return

    # No item has qty_column_visible=true → likely GPT defaulted all to 1
    for it in product_items:
        it["qty_source"] = "ambiguous"
        it.setdefault("_source_overrides", []).append(
            "system: all-qty-1 pattern detected, no qty_column_visible — qty column likely not read"
        )


def _validate_single_item_sources(item: dict) -> None:
    """
    Per-item heuristic checks that override GPT-reported sources.
    Each check can downgrade a source from 'column_read' to 'ambiguous'.

    Fee rows are exempt from product-math source checks — they only need a total.
    """
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)

    overrides = item.setdefault("_source_overrides", [])

    # ── Fee rows: different validation path ──
    # Fees (fuel surcharge, delivery, etc.) are NOT products.
    # They have one meaningful number: total. qty and price are irrelevant.
    if item.get("row_type") == "fee":
        # Normalize fee fields: qty=1, price=total (for consistency)
        if total > 0:
            item["quantity"] = 1
            item["unit_price"] = total
            item["qty_source"] = "fee_implied"
            item["price_source"] = "fee_implied"
            item["total_source"] = item.get("total_source") or "column_read"
            overrides.append("system: fee row — qty=1 and price=total implied, only total matters")
        elif price > 0 and total <= 0:
            # GPT gave price but not total — use price as total
            item["total"] = price
            item["quantity"] = 1
            item["unit_price"] = price
            item["qty_source"] = "fee_implied"
            item["price_source"] = "fee_implied"
            item["total_source"] = "fee_implied"
            overrides.append("system: fee row — total missing, using price as total")
        else:
            overrides.append("system: fee row with total=0 — cannot validate")
        return  # Skip all product-math checks

    # ── Product rows: full source validation ──

    # Check 1: price == total AND qty == 1 → qty likely defaulted
    # BUT: if GPT explicitly confirmed qty_column_visible=true, trust it.
    if qty == 1.0 and price > 0 and total > 0 and abs(price - total) < 0.01:
        if item.get("qty_source") == "column_read":
            qty_visible = item.get("qty_column_visible")
            if qty_visible is True:
                overrides.append(
                    "system: price==total with qty=1, but qty_column_visible=true — keeping column_read"
                )
            else:
                item["qty_source"] = "ambiguous"
                overrides.append(
                    "system: price==total with qty=1, qty_column_visible not confirmed — downgrading"
                )

    # Check 2: If a field was zero and could be inferred — mark source
    if total == 0 and qty > 0 and price > 0:
        item["total_source"] = "inferred"
        overrides.append("system: total is zero — would need inference from qty*price")
    if price == 0 and total > 0 and qty > 0:
        item["price_source"] = "inferred"
        overrides.append("system: price is zero — would need inference from total/qty")
    if qty == 0 and total > 0 and price > 0:
        item["qty_source"] = "inferred"
        overrides.append("system: qty is zero — would need inference from total/price")

    # Check 3: Math mismatch → at least one field is wrong
    if qty > 0 and price > 0 and total > 0:
        computed = round(qty * price, 2)
        diff = abs(computed - total)
        pct = diff / total if total else 0
        if pct > 0.02 and diff > 0.50:
            for field in ("qty_source", "price_source", "total_source"):
                if item.get(field) == "column_read":
                    item[field] = "ambiguous"
            overrides.append(
                f"system: math mismatch ({qty}×{price}={computed} vs total={total}) — all sources downgraded"
            )

    # Check 4: Unrealistic values
    if qty > 500:
        item["qty_source"] = "ambiguous"
        overrides.append(f"system: qty={qty} is unrealistically high")
    if price > 5000:
        item["price_source"] = "ambiguous"
        overrides.append(f"system: price={price} is unrealistically high")


def _assign_numeric_failure_category(item: dict) -> None:
    """
    Categorize numeric failures into specific types:
    - fee_valid: fee row with total > 0 (no product math needed)
    - fee_missing_total: fee row with total = 0
    - qty_wrong: qty source is not column_read
    - price_wrong: price source is not column_read
    - both_wrong: both qty and price are unreliable
    - total_wrong_due_to_upstream: total was inferred from wrong inputs
    - none: all sources confirmed
    """
    # Fee rows have their own category
    if item.get("row_type") == "fee":
        total = float(item.get("total", 0) or 0)
        if total > 0:
            item["numeric_failure_category"] = "fee_valid"
        else:
            item["numeric_failure_category"] = "fee_missing_total"
        return

    qty_ok = item.get("qty_source") == "column_read"
    price_ok = item.get("price_source") == "column_read"
    total_ok = item.get("total_source") == "column_read"

    if qty_ok and price_ok and total_ok:
        item["numeric_failure_category"] = "none"
    elif not qty_ok and not price_ok:
        item["numeric_failure_category"] = "both_wrong"
    elif not qty_ok:
        if not total_ok and item.get("total_source") == "inferred":
            item["numeric_failure_category"] = "total_wrong_due_to_upstream"
        else:
            item["numeric_failure_category"] = "qty_wrong"
    elif not price_ok:
        if not total_ok and item.get("total_source") == "inferred":
            item["numeric_failure_category"] = "total_wrong_due_to_upstream"
        else:
            item["numeric_failure_category"] = "price_wrong"
    elif not total_ok:
        if item.get("total_source") == "inferred":
            item["numeric_failure_category"] = "total_wrong_due_to_upstream"
        else:
            item["numeric_failure_category"] = "qty_wrong"  # conservative
    else:
        item["numeric_failure_category"] = "none"


def _apply_numeric_trust_gate(item: dict) -> None:
    """
    Final trust gate: a row can be 'trusted' ONLY if ALL conditions pass.

    Product rows (line_item):
      1. qty_source == 'column_read'
      2. price_source == 'column_read'
      3. total_source == 'column_read'
      4. math validates (valid_calc == True)
      5. no numeric failure category

    Fee rows:
      1. total > 0
      2. row classified as fee
      (qty and price are irrelevant for fees)

    If ANY condition fails, downgrade to 'needs_review_numeric'.
    """
    current_level = item.get("confidence_level", "")

    # Only gate items that are currently "trusted" or "needs_review_light"
    if current_level not in ("trusted", "needs_review_light"):
        return

    # ── Fee row trust gate ──
    if item.get("row_type") == "fee":
        total = float(item.get("total", 0) or 0)
        if total > 0:
            item["confidence_level"] = "trusted"
            item["needs_review"] = False
            item["review_reason"] = None
            item["confidence_reason"] = "Fee row: total present, no product math required"
        else:
            item["confidence_level"] = "needs_review_numeric"
            item["needs_review"] = True
            item["review_reason"] = "Fee row: missing total amount"
            item["confidence_reason"] = "Fee row: missing total amount"
        return

    # ── Product row trust gate ──
    qty_src = item.get("qty_source", "ambiguous")
    price_src = item.get("price_source", "ambiguous")
    total_src = item.get("total_source", "ambiguous")
    failure_cat = item.get("numeric_failure_category", "none")

    all_sourced = (qty_src == "column_read" and
                   price_src == "column_read" and
                   total_src == "column_read")
    math_ok = item.get("valid_calc", False)

    if all_sourced and math_ok and failure_cat == "none":
        if current_level == "needs_review_light" and item.get("confidence_score", 0) >= 85:
            item["confidence_level"] = "trusted"
            item["needs_review"] = False
            item["review_reason"] = None
            item["confidence_reason"] = "All gates passed (field sources verified)"
        return

    # One or more conditions failed — downgrade
    reasons = []
    if qty_src != "column_read":
        reasons.append(f"qty_source={qty_src}")
    if price_src != "column_read":
        reasons.append(f"price_source={price_src}")
    if total_src != "column_read":
        reasons.append(f"total_source={total_src}")
    if not math_ok:
        reasons.append("math_not_validated")

    reason_str = "; ".join(reasons)

    item["confidence_level"] = "needs_review_numeric"
    item["needs_review"] = True
    item["review_reason"] = f"Numeric field trust: {reason_str}"
    item["confidence_reason"] = f"Numeric field trust: {reason_str}"
    item.setdefault("validation_errors", []).append(
        f"numeric_trust_gate: {reason_str} (category={failure_cat})"
    )


def _validate_pfg_extraction(items: list) -> None:
    """
    PFG-specific post-extraction validation.
    Detects and flags column confusion errors:

    1. WEIGHT leaked into QTY (qty > 50 with decimal or exact round number)
    2. PACK leaked into QTY (qty matches pack multiplier pattern)
    3. ORD used instead of SHIP
    4. All-qty=1 pattern (SHIP column not read at all)
    5. Pack info leaked into item name
    6. Service row reclassification
    """
    if not items:
        return

    product_items = [it for it in items
                     if it.get("row_type") in ("line_item", None)
                     and not (set((it.get("raw_name") or "").lower().split()) & _SERVICE_KW)]

    # Check 1: All-qty=1 pattern — SHIP column likely not read
    product_qtys = [float(it.get("quantity", 0) or 0) for it in product_items]
    if len(product_qtys) >= 3 and all(q == 1 for q in product_qtys):
        for it in product_items:
            it["needs_review"] = True
            it["confidence_level"] = "review"
            it["review_reason"] = "PFG: all quantities are 1 — SHIP column may not have been read"
            it.setdefault("validation_errors", []).append(
                "pfg_column_check: all_qty_1 — likely SHIP column missed"
            )

    for it in items:
        if it.get("row_type") not in ("line_item", "fee", None):
            continue

        name = (it.get("raw_name") or "").strip()
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        pack = (it.get("pack_size") or "").strip()
        name_lower = name.lower()
        name_words = set(name_lower.split())

        # ── Column confusion: WEIGHT as QTY ──
        # PFG SHIP values are small integers (1-50 typical).
        # WEIGHT values are larger decimals (24.00, 75.50, 120.00).
        if qty > 50:
            it.setdefault("validation_errors", []).append(
                f"pfg_column_check: qty={qty} — likely WEIGHT column value, not SHIP"
            )
            if it.get("confidence_level") not in ("needs_review_numeric", "extraction_failed"):
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["review_reason"] = f"PFG column confusion: qty={qty} is likely WEIGHT, not SHIP (SHIP is small integer)"

        # Additional WEIGHT check: qty is a decimal (SHIP is always integer)
        if qty > 0 and qty != int(qty):
            it.setdefault("validation_errors", []).append(
                f"pfg_column_check: qty={qty} is decimal — SHIP column values are integers"
            )
            if it.get("confidence_level") not in ("needs_review_numeric", "extraction_failed"):
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["review_reason"] = f"PFG column confusion: qty={qty} is decimal — SHIP values are always integers"

        # ── Column confusion: PACK multiplier as QTY ──
        # E.g., pack="6/4 LB" and qty=6 or qty=24 (6×4)
        if pack and qty > 0:
            pack_match = re.match(r'^(\d+)\s*[/X]\s*(\d+)', pack, re.IGNORECASE)
            if pack_match:
                pack_outer = int(pack_match.group(1))
                pack_inner = int(pack_match.group(2))
                if qty == pack_outer or qty == pack_outer * pack_inner:
                    it.setdefault("validation_errors", []).append(
                        f"pfg_column_check: qty={int(qty)} matches pack pattern {pack} — likely PACK value, not SHIP"
                    )

        # ── Service row reclassification ──
        if name_words & _SERVICE_KW and len(name_words) <= 4:
            it["row_type"] = "fee"

        # ── Pack info leaked into item name ──
        if _PFG_PACK_IN_NAME.search(name):
            it.setdefault("validation_errors", []).append(
                f"pfg_column_check: pack pattern found in item name '{name[:40]}'"
            )



# Sysco group/subtotal keywords that must never become product rows
_SYSCO_GROUP_KW = {"subtotal", "total", "group", "***", "---"}


def _validate_sysco_extraction(items: list) -> None:
    """
    Sysco-specific post-extraction guardrails.
    Strict deterministic validation — no ambiguity allowed.
    Only validates line_item and fee rows (row_type already classified upstream).

    Review status taxonomy:
    - needs_review_light: minor issues, math OK
    - needs_review_numeric: math mismatch or missing qty/price/total
    - extraction_failed: critical fields missing or garbled
    """
    if not items:
        return

    for it in items:
        # Skip non-line-item rows — already classified and excluded upstream
        if it.get("row_type") not in ("line_item", "fee"):
            continue

        name = (it.get("raw_name") or "").strip()
        name_lower = name.lower()
        name_words = set(name_lower.split())
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)

        # Guard 1: Missing critical fields → extraction_failed
        if not name:
            it["confidence_level"] = "extraction_failed"
            it["needs_review"] = True
            it["review_reason"] = "Missing item name"
            it.setdefault("validation_errors", []).append("sysco_missing_name")
            continue

        # Guard 2: Missing qty with total present → needs_review_numeric
        if qty == 0 and total > 0:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = f"Missing or unreadable quantity (total=${total})"
            it.setdefault("validation_errors", []).append(
                "sysco_missing_qty: quantity could not be read"
            )

        # Guard 3: Strict math validation — Decision Gate
        # qty × price must equal total within 2% or $0.50
        if qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            pct = diff / total if total else 0
            if pct > 0.02 and diff > 0.50:
                it.setdefault("validation_errors", []).append(
                    f"sysco_math_mismatch: {qty}×{price}={computed} vs total={total} (diff={pct:.1%})"
                )
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["review_reason"] = f"Math mismatch: qty({qty}) × price(${price}) = ${computed}, but total is ${total}"

        # Guard 6: Missing price or total → needs_review_numeric
        if qty > 0 and (price == 0 or total == 0):
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = f"Missing {'price' if price == 0 else 'total'}"
            it.setdefault("validation_errors", []).append(
                f"sysco_missing_{'price' if price == 0 else 'total'}"
            )

        it["vendor_status"] = "controlled_operational"
        it["extraction_source"] = "gpt_vision"


# Sysco category header keywords — these are section dividers, NOT products
_SYSCO_CATEGORY_HEADERS = re.compile(
    r'\b(poultry|seafood|frozen|dairy|canned|dry|produce|bakery|'
    r'beverage|paper|disposable|chemical|meat|deli|grocery|snack|'
    r'ice\s*cream|juice|condiment|spice|sauce)\b',
    re.IGNORECASE,
)


async def _apply_sysco_math_first_gate(extracted: dict) -> None:
    """
    Sysco math-first trust gate.

    Phase 1: Row filtering — exclude non-product rows
    Phase 2: Per-row math validation — qty × price = total (tolerance $0.01)
    Phase 3: Invoice-level validation — merchandise subtotal check
    Phase 4: Trust assignment — trusted only if ALL gates pass

    No inferred/hallucinated values can be trusted.
    """
    items = extracted.get("items", [])
    if not items:
        return

    # ── Phase 1: Enhanced row filtering for Sysco ──
    for it in items:
        if it.get("row_type") not in ("line_item", "fee"):
            continue

        name = (it.get("raw_name") or "").strip()
        name_lower = name.lower()

        # Filter: category headers that slipped through row classification
        # Short text (1-3 words) matching category keywords → header
        name_words = name_lower.split()
        if len(name_words) <= 3 and _SYSCO_CATEGORY_HEADERS.search(name_lower):
            qty = float(it.get("quantity", 0) or 0)
            price = float(it.get("unit_price", 0) or 0)
            total = float(it.get("total", 0) or 0)
            # Only reclassify if it has no real numeric data
            if qty == 0 and price == 0 and total == 0:
                it["row_type"] = "header"
                it["confidence_level"] = "excluded"
                it["needs_review"] = False
                it["review_reason"] = f"Sysco category header: '{name}'"
                it["numeric_failure_category"] = "n/a"
                continue

        # Filter: text with asterisks (section markers)
        if name.count("*") >= 2 and len(name_words) <= 4:
            it["row_type"] = "header"
            it["confidence_level"] = "excluded"
            it["needs_review"] = False
            it["review_reason"] = f"Sysco section marker: '{name}'"
            it["numeric_failure_category"] = "n/a"
            continue

        # Filter: text is garbage/noise (no meaningful alpha chars)
        alpha_count = sum(1 for c in name if c.isalpha())
        if alpha_count < 3:
            it["row_type"] = "unknown"
            it["confidence_level"] = "excluded"
            it["needs_review"] = False
            it["review_reason"] = f"Unreadable row text: '{name[:30]}'"
            it["numeric_failure_category"] = "n/a"
            continue

    # ── Phase 2: Per-row strict math validation ──
    # Tolerance: $0.01 — no rounding ambiguity
    line_items = [it for it in items
                  if it.get("row_type") in ("line_item", "fee")
                  and it.get("confidence_level") != "excluded"]

    for it in line_items:
        # ── Fee rows: validate with total > 0 only ──
        if it.get("row_type") == "fee":
            total = float(it.get("total", 0) or 0)
            # Normalize fee: qty=1, price=total
            if total > 0:
                it["quantity"] = 1
                it["unit_price"] = total
                it["valid_calc"] = True
            elif it.get("unit_price") and float(it["unit_price"]) > 0:
                # GPT gave price but not total — use price as total
                it["total"] = float(it["unit_price"])
                it["quantity"] = 1
                total = it["total"]
                it["valid_calc"] = True
            else:
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["review_reason"] = "Fee row: missing total amount"
                it["valid_calc"] = False
                it.setdefault("validation_errors", []).append("sysco_math_gate: fee missing total")
            continue

        # ── Product rows: full qty × price = total validation ──
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)

        # All three fields must be present
        if qty <= 0:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = f"Missing quantity (qty=0, total=${total})"
            it["valid_calc"] = False
            it.setdefault("validation_errors", []).append("sysco_math_gate: qty missing")
            continue

        if price <= 0:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = f"Missing unit price (price=0, total=${total})"
            it["valid_calc"] = False
            it.setdefault("validation_errors", []).append("sysco_math_gate: price missing")
            continue

        if total <= 0:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = f"Missing extended price (total=0)"
            it["valid_calc"] = False
            it.setdefault("validation_errors", []).append("sysco_math_gate: total missing")
            continue

        # Math validation: qty × price = total (tolerance $0.01)
        computed = round(qty * price, 2)
        diff = abs(computed - total)

        if diff > 0.01:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            it["review_reason"] = (
                f"Math mismatch: {qty} × ${price:.2f} = ${computed:.2f}, "
                f"but extended price is ${total:.2f} (diff=${diff:.2f})"
            )
            it["valid_calc"] = False
            it.setdefault("validation_errors", []).append(
                f"sysco_math_gate: {qty}×{price}={computed} ≠ {total} (diff={diff})"
            )
        else:
            it["valid_calc"] = True

        # Source check: no inferred values can be trusted
        for field, source_key in [("qty", "qty_source"), ("price", "price_source"), ("total", "total_source")]:
            src = (it.get(source_key) or "").strip().lower()
            if src == "inferred":
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["review_reason"] = f"Inferred {field} value cannot be trusted"
                it["valid_calc"] = False
                it.setdefault("validation_errors", []).append(
                    f"sysco_math_gate: {field}_source=inferred"
                )

    # ── Phase 3: Invoice-level merchandise subtotal (INFORMATIONAL ONLY) ──
    # Classifies the invoice as complete/partial/over_extracted.
    # This NEVER affects row-level trust. Row correctness is independent.
    validated_items = [it for it in line_items
                       if it.get("valid_calc") is True
                       and it.get("row_type") == "line_item"]  # Fees excluded from merchandise subtotal
    items_sum = round(sum(float(it.get("total", 0) or 0) for it in validated_items), 2)

    declared_subtotal = float(extracted.get("subtotal", 0) or 0)
    is_partial_page = False
    invoice_completeness = "unknown"

    if items_sum > 0 and declared_subtotal > 0:
        subtotal_diff = abs(items_sum - declared_subtotal)
        subtotal_pct = subtotal_diff / declared_subtotal if declared_subtotal else 0

        if subtotal_diff <= 0.01 or subtotal_pct <= 0.05:
            invoice_completeness = "complete"
        elif items_sum < declared_subtotal:
            is_partial_page = True
            invoice_completeness = "partial"
        else:
            # items_sum > declared_subtotal — informational flag only
            invoice_completeness = "over_extracted"

    extracted["_sysco_merchandise_subtotal"] = items_sum
    extracted["_sysco_subtotal_match"] = invoice_completeness in ("complete", "partial")
    extracted["_sysco_is_partial_page"] = is_partial_page
    extracted["_invoice_completeness_phase3"] = invoice_completeness

    # ── Phase 4: Trust assignment ──
    # A row is trusted ONLY if ALL conditions pass
    for it in line_items:
        if it.get("confidence_level") == "excluded":
            continue

        # ── Fee rows: trust if total > 0 ──
        if it.get("row_type") == "fee":
            total = float(it.get("total", 0) or 0)
            has_name = bool((it.get("raw_name") or "").strip())
            if total > 0 and has_name and it.get("valid_calc", False):
                it["confidence_level"] = "trusted"
                it["needs_review"] = False
                it["review_reason"] = None
                it["numeric_failure_category"] = "fee_valid"
                it["confidence_reason"] = "Fee row: total present, no product math required"
            else:
                if it.get("confidence_level") not in ("needs_review_numeric", "extraction_failed"):
                    it["confidence_level"] = "needs_review_numeric"
                    it["needs_review"] = True
                it["numeric_failure_category"] = "fee_missing_total"
                if not it.get("review_reason"):
                    it["review_reason"] = f"Fee row: missing total (total={total})"
            continue

        # ── Product rows: full trust gate ──
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        math_ok = it.get("valid_calc", False)
        has_name = bool((it.get("raw_name") or "").strip())
        alpha_count = sum(1 for c in (it.get("raw_name") or "") if c.isalpha())
        readable = alpha_count >= 3

        # Check all sources are column_read (not inferred or ambiguous)
        qty_src = (it.get("qty_source") or "").strip().lower()
        price_src = (it.get("price_source") or "").strip().lower()
        total_src = (it.get("total_source") or "").strip().lower()
        all_column_read = (qty_src == "column_read" and
                           price_src == "column_read" and
                           total_src == "column_read")

        if (math_ok and has_name and readable
                and qty > 0 and price > 0 and total > 0
                and all_column_read):
            it["confidence_level"] = "trusted"
            it["needs_review"] = False
            it["review_reason"] = None
            it["numeric_failure_category"] = "none"
            it["confidence_reason"] = "Sysco math-first: all fields present, math validated, all sources column_read"
        else:
            # Already marked as needs_review from earlier phases
            if it.get("confidence_level") not in ("needs_review_numeric", "extraction_failed"):
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True

            # Assign failure category
            if qty <= 0 and price <= 0:
                it["numeric_failure_category"] = "both_wrong"
            elif qty <= 0:
                it["numeric_failure_category"] = "qty_wrong"
            elif price <= 0:
                it["numeric_failure_category"] = "price_wrong"
            elif total <= 0:
                it["numeric_failure_category"] = "total_missing"
            elif not math_ok:
                it["numeric_failure_category"] = "math_mismatch"
            elif not all_column_read:
                it["numeric_failure_category"] = "source_not_column_read"
            else:
                it["numeric_failure_category"] = "unknown"

    # ── Phase 5: Product Memory Cross-Validation (support layer) ──
    # Build memory from trusted items in THIS invoice + DB history.
    # Does NOT promote to trusted. Only upgrades to review_with_memory_support.
    # V2: Item code-first matching, fuzzy description fallback, controlled qty=1 support.
    from services.product_memory import ProductMemory

    memory = ProductMemory()

    # Build from DB history (past trusted Sysco extractions)
    try:
        from core.database import db as mongo_db
        await memory.build_from_db(mongo_db)
    except Exception as e:
        logger.debug(f"Product memory: skipped DB build: {e}")

    # Build from current invoice's trusted items
    memory.build_from_trusted_items(items, source_label="current_invoice")

    memory_stats = {
        "memory_size": memory.size,
        "unique_products": memory.unique_products,
        "unique_item_codes": memory.unique_item_codes,
        "matches_found": 0,
        "upgraded_to_memory_support": 0,
        "inconsistencies": [],
        "match_methods": {"item_code": 0, "exact_key": 0, "fuzzy": 0},
    }

    # Check ambiguous rows against memory
    for it in line_items:
        if it.get("confidence_level") == "excluded":
            continue
        if it.get("numeric_failure_category") != "source_not_column_read":
            continue

        # Only apply to the specific pattern: qty=ambiguous, price=column_read, total=column_read
        qty_src = (it.get("qty_source") or "").lower()
        price_src = (it.get("price_source") or "").lower()
        total_src = (it.get("total_source") or "").lower()

        if qty_src != "ambiguous" or price_src != "column_read" or total_src != "column_read":
            continue

        raw_name = (it.get("raw_name") or "").strip()
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        qty = float(it.get("quantity", 0) or 0)
        item_code = (it.get("item_code") or "").strip()

        if price <= 0 or total <= 0:
            continue

        match = memory.lookup(raw_name, price, item_code=item_code)

        if not match.get("matched"):
            continue

        memory_stats["matches_found"] += 1
        match_method = match.get("match_method", "unknown")
        if match_method in memory_stats["match_methods"]:
            memory_stats["match_methods"][match_method] += 1
        it["_memory_match"] = match

        # Calculated qty (consistency check only — NOT used as source of truth)
        calc_qty = round(total / price, 2) if price > 0 else 0

        if match["consistency"] == "stable" and match["stable_qty"] is not None:
            stable_qty = match["stable_qty"]

            if calc_qty == stable_qty:
                # Strong memory match: product+price seen before, calculated qty matches stable pattern
                it["confidence_level"] = "review_with_memory_support"
                it["needs_review"] = True
                it["review_reason"] = (
                    f"Memory match ({match_method}): '{raw_name[:30]}' at ${price:.2f} has stable qty={int(stable_qty)} "
                    f"({match['price_matches']} prior occurrences). "
                    f"Calculated qty ({calc_qty}) matches. Structural confirmation still needed."
                )
                it["_memory_stable_qty"] = stable_qty
                it["_memory_calc_qty"] = calc_qty
                memory_stats["upgraded_to_memory_support"] += 1
            else:
                # Inconsistency: memory says one qty, math says another
                inconsistency = {
                    "product": raw_name[:40],
                    "price": price,
                    "total": total,
                    "memory_stable_qty": stable_qty,
                    "calculated_qty": calc_qty,
                    "current_qty": qty,
                    "match_method": match_method,
                }
                memory_stats["inconsistencies"].append(inconsistency)
                it["_memory_inconsistency"] = True
                it["review_reason"] = (
                    f"Memory inconsistency: '{raw_name[:30]}' at ${price:.2f} — "
                    f"memory expects qty={int(stable_qty)} but total/price suggests qty={calc_qty}"
                )

        elif calc_qty == 1.0 and match.get("seen_at_this_price"):
            # ── Controlled qty=1 memory support ──
            # Product+price has been seen before (at any qty), and calc suggests qty=1.
            # Ordering 1 case is valid. Upgrade to review_with_memory_support (NOT trusted).
            it["confidence_level"] = "review_with_memory_support"
            it["needs_review"] = True
            it["review_reason"] = (
                f"Memory support ({match_method}): '{raw_name[:30]}' at ${price:.2f} recognized "
                f"({match['price_matches']} prior at this price, {match['occurrences']} total). "
                f"Qty=1 is plausible. Human review recommended."
            )
            it["_memory_stable_qty"] = None
            it["_memory_calc_qty"] = calc_qty
            it["_memory_qty1_support"] = True
            memory_stats["upgraded_to_memory_support"] += 1

        elif calc_qty == 1.0 and match.get("seen_at_any_price") and not match.get("seen_at_this_price"):
            # Product known but at a different price — weaker signal
            it["_memory_match_weak"] = True
            it["_memory_note"] = f"Product known but price ${price:.2f} not seen before (known prices: {match.get('qty_pattern', {})})"

        elif match["consistency"] == "insufficient":
            # Product seen but not enough data for stable pattern
            it["_memory_match_weak"] = True

    extracted["_product_memory_stats"] = memory_stats

    # ── Phase 6: Unit Normalization ──
    # Converts pack_size into normalized quantity (lb or piece) and price_per_unit.
    # Runs after all validation. Does NOT affect trust status.
    from services.unit_normalizer import normalize_items as _normalize_items
    unit_stats = _normalize_items(items)
    extracted["_unit_normalization_stats"] = unit_stats



# ═══════════════════════════════════════════════════════════
# PFG MATH-FIRST TRUST GATE
# ═══════════════════════════════════════════════════════════
# PFG Columns: ITEM# | QTY | PK | SIZE | DESCRIPTION | BRAND | UNIT PRC | EXT TOTAL
# Math rule: QTY × UNIT PRC = EXT TOTAL (±$0.01)
# Fee rows: total > 0 only
# Column confusion: WEIGHT-as-qty, decimal qty, pack-as-qty (already checked in _validate_pfg_extraction)

def _apply_pfg_trust_gate(extracted: dict) -> None:
    """
    PFG trust gate — mirrors Sysco structure.
    Trusts rows where:
      1. row_type == 'line_item' AND math validates AND all sources column_read AND no column errors
      2. row_type == 'fee' AND total > 0
    """
    items = extracted.get("items", [])
    line_items = [it for it in items if it.get("row_type") in ("line_item", "fee")]

    for it in line_items:
        if it.get("confidence_level") == "excluded":
            continue

        # ── Fee rows: trust if total > 0 ──
        if it.get("row_type") == "fee":
            total = float(it.get("total", 0) or 0)
            has_name = bool((it.get("raw_name") or "").strip())
            if total > 0 and has_name:
                it["quantity"] = 1
                it["unit_price"] = total
                it["valid_calc"] = True
                it["confidence_level"] = "trusted"
                it["needs_review"] = False
                it["review_reason"] = None
                it["numeric_failure_category"] = "fee_valid"
                it["confidence_reason"] = "PFG fee: total present, no product math required"
            else:
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["numeric_failure_category"] = "fee_missing_total"
                it["review_reason"] = f"PFG fee: missing total (total={total})"
            it["vendor_status"] = "controlled_operational"
            it["extraction_source"] = "gpt_vision_pfg"
            continue

        # ── Product rows: full trust gate ──
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        has_name = bool((it.get("raw_name") or "").strip())
        alpha_count = sum(1 for c in (it.get("raw_name") or "") if c.isalpha())
        readable = alpha_count >= 3

        # Math check
        if qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            it["valid_calc"] = diff <= 0.01
        else:
            it["valid_calc"] = False

        # Source check
        qty_src = (it.get("qty_source") or "").strip().lower()
        price_src = (it.get("price_source") or "").strip().lower()
        total_src = (it.get("total_source") or "").strip().lower()
        all_column_read = (qty_src == "column_read" and
                           price_src == "column_read" and
                           total_src == "column_read")

        # Column confusion errors are blocking (not just warnings)
        errors = it.get("validation_errors", [])
        column_errors = [e for e in errors if "pfg_column_check" in e]
        has_blocking_errors = len(column_errors) > 0

        math_ok = it.get("valid_calc", False)

        if (math_ok and has_name and readable
                and qty > 0 and price > 0 and total > 0
                and all_column_read and not has_blocking_errors):
            it["confidence_level"] = "trusted"
            it["needs_review"] = False
            it["review_reason"] = None
            it["numeric_failure_category"] = "none"
            it["confidence_reason"] = "PFG math-first: all fields present, math validated, all sources column_read"
        else:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            reasons = []
            if not math_ok:
                reasons.append("math_fail")
            if not all_column_read:
                bad_srcs = []
                if qty_src != "column_read":
                    bad_srcs.append(f"qty={qty_src}")
                if price_src != "column_read":
                    bad_srcs.append(f"price={price_src}")
                if total_src != "column_read":
                    bad_srcs.append(f"total={total_src}")
                reasons.append(f"source({','.join(bad_srcs)})")
            if has_blocking_errors:
                reasons.append(f"column_confusion({len(column_errors)})")
            if not has_name or not readable:
                reasons.append("unreadable_name")
            missing = []
            if qty <= 0:
                missing.append("qty")
            if price <= 0:
                missing.append("price")
            if total <= 0:
                missing.append("total")
            if missing:
                reasons.append(f"missing({','.join(missing)})")

            reason_str = "; ".join(reasons)
            it["review_reason"] = f"PFG review: {reason_str}"
            it["numeric_failure_category"] = "pfg_" + (reasons[0].split("(")[0] if reasons else "unknown")
            it["confidence_reason"] = f"PFG review: {reason_str}"

        it["vendor_status"] = "controlled_operational"
        it["extraction_source"] = "gpt_vision_pfg"


# ═══════════════════════════════════════════════════════════
# US FOODS MATH-FIRST TRUST GATE
# ═══════════════════════════════════════════════════════════
# US Foods Columns: Product Number | Qty | Unit | Description | Weight | Unit Price | Extended Price
# Math rule: Qty × Unit Price = Extended Price (±$0.01)
# Fee rows: total > 0 only
# Column confusion: WEIGHT-as-qty, decimal qty, ORDERED-vs-SHIPPED (already checked in _validate_usfoods_extraction)

def _apply_usfoods_trust_gate(extracted: dict) -> None:
    """
    US Foods trust gate — mirrors Sysco/PFG structure.
    Trusts rows where:
      1. row_type == 'line_item' AND math validates AND all sources column_read AND no column errors
      2. row_type == 'fee' AND total > 0
    """
    items = extracted.get("items", [])
    line_items = [it for it in items if it.get("row_type") in ("line_item", "fee")]

    for it in line_items:
        if it.get("confidence_level") == "excluded":
            continue

        # ── Fee rows: trust if total > 0 ──
        if it.get("row_type") == "fee":
            total = float(it.get("total", 0) or 0)
            has_name = bool((it.get("raw_name") or "").strip())
            if total > 0 and has_name:
                it["quantity"] = 1
                it["unit_price"] = total
                it["valid_calc"] = True
                it["confidence_level"] = "trusted"
                it["needs_review"] = False
                it["review_reason"] = None
                it["numeric_failure_category"] = "fee_valid"
                it["confidence_reason"] = "US Foods fee: total present, no product math required"
            else:
                it["confidence_level"] = "needs_review_numeric"
                it["needs_review"] = True
                it["numeric_failure_category"] = "fee_missing_total"
                it["review_reason"] = f"US Foods fee: missing total (total={total})"
            it["vendor_status"] = "controlled_operational"
            it["extraction_source"] = "gpt_vision_usfoods"
            continue

        # ── Product rows: full trust gate ──
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        has_name = bool((it.get("raw_name") or "").strip())
        alpha_count = sum(1 for c in (it.get("raw_name") or "") if c.isalpha())
        readable = alpha_count >= 3

        # Math check
        if qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            it["valid_calc"] = diff <= 0.01
        else:
            it["valid_calc"] = False

        # Source check
        qty_src = (it.get("qty_source") or "").strip().lower()
        price_src = (it.get("price_source") or "").strip().lower()
        total_src = (it.get("total_source") or "").strip().lower()
        all_column_read = (qty_src == "column_read" and
                           price_src == "column_read" and
                           total_src == "column_read")

        # Column confusion errors are blocking
        errors = it.get("validation_errors", [])
        column_errors = [e for e in errors if "usfoods_column_check" in e]
        has_blocking_errors = len(column_errors) > 0

        math_ok = it.get("valid_calc", False)

        if (math_ok and has_name and readable
                and qty > 0 and price > 0 and total > 0
                and all_column_read and not has_blocking_errors):
            it["confidence_level"] = "trusted"
            it["needs_review"] = False
            it["review_reason"] = None
            it["numeric_failure_category"] = "none"
            it["confidence_reason"] = "US Foods math-first: all fields present, math validated, all sources column_read"
        else:
            it["confidence_level"] = "needs_review_numeric"
            it["needs_review"] = True
            reasons = []
            if not math_ok:
                reasons.append("math_fail")
            if not all_column_read:
                bad_srcs = []
                if qty_src != "column_read":
                    bad_srcs.append(f"qty={qty_src}")
                if price_src != "column_read":
                    bad_srcs.append(f"price={price_src}")
                if total_src != "column_read":
                    bad_srcs.append(f"total={total_src}")
                reasons.append(f"source({','.join(bad_srcs)})")
            if has_blocking_errors:
                reasons.append(f"column_confusion({len(column_errors)})")
            if not has_name or not readable:
                reasons.append("unreadable_name")
            missing = []
            if qty <= 0:
                missing.append("qty")
            if price <= 0:
                missing.append("price")
            if total <= 0:
                missing.append("total")
            if missing:
                reasons.append(f"missing({','.join(missing)})")

            reason_str = "; ".join(reasons)
            it["review_reason"] = f"US Foods review: {reason_str}"
            it["numeric_failure_category"] = "usfoods_" + (reasons[0].split("(")[0] if reasons else "unknown")
            it["confidence_reason"] = f"US Foods review: {reason_str}"

        it["vendor_status"] = "controlled_operational"
        it["extraction_source"] = "gpt_vision_usfoods"



# ── US Foods Row Classification Keywords ──
_USFOODS_EXCLUDE_PATTERNS = re.compile(
    r'\b(subtotal|sub\s*total|total|invoice\s*total|amount\s*due|'
    r'sales\s*tax|tax|'
    r'credit|adjustment|balance\s*due|payment|remit)\b',
    re.IGNORECASE,
)

_USFOODS_CATEGORY_HEADERS = re.compile(
    r'\b(frozen|dairy|produce|bakery|beverages?|paper|chemical|'
    r'meat|deli|grocery|dry\s*goods?|canned|seafood|poultry)\b',
    re.IGNORECASE,
)


def _validate_usfoods_extraction(items: list) -> None:
    """
    US Foods post-extraction validation.
    Structural column mapping checks + row classification + math gate.

    Column confusion checks:
    1. ORDERED vs SHIPPED: detect if qty came from ORDERED instead of SHIPPED
    2. WEIGHT as QTY: detect decimal/large qty values from WEIGHT column
    3. ITEM# extraction: verify item_code is a 7-digit number
    4. Fee row handling: fuel surcharge etc. use total-only validation
    """
    if not items:
        return

    for it in items:
        if it.get("row_type") not in ("line_item", "fee", None):
            continue

        name = (it.get("raw_name") or "").strip()
        name_lower = name.lower()
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        item_code = (it.get("item_code") or "").strip()

        # ── Fee row handling (BEFORE exclude patterns) ──
        # Fees like fuel surcharge should NOT be excluded as summary rows
        name_words = set(name_lower.split())
        if name_words & _SERVICE_KW and len(name_words) <= 5:
            it["row_type"] = "fee"
            if total > 0:
                it["quantity"] = 1
                it["unit_price"] = total
                it["valid_calc"] = True
            elif price > 0:
                it["total"] = price
                it["quantity"] = 1
                it["unit_price"] = price
                it["valid_calc"] = True
            else:
                it["valid_calc"] = False
            it["vendor_status"] = "pending"
            it["extraction_source"] = "gpt_vision_usfoods"
            continue

        # ── Row classification: catch misclassified summary/header rows ──
        if _USFOODS_EXCLUDE_PATTERNS.search(name_lower):
            name_words = name_lower.split()
            if len(name_words) <= 4:
                it["row_type"] = "summary"
                it["confidence_level"] = "excluded"
                it["needs_review"] = False
                it["review_reason"] = f"US Foods summary row: '{name}'"
                continue

        if _USFOODS_CATEGORY_HEADERS.search(name_lower):
            name_words = name_lower.split()
            if len(name_words) <= 3 and qty == 0 and price == 0 and total == 0:
                it["row_type"] = "header"
                it["confidence_level"] = "excluded"
                it["needs_review"] = False
                it["review_reason"] = f"US Foods category header: '{name}'"
                continue

        # ── Column confusion: WEIGHT as QTY ──
        # US Foods SHIPPED values are small integers (1-50).
        # WEIGHT values are larger decimals (24.00, 75.50).
        if qty > 50:
            it.setdefault("validation_errors", []).append(
                f"usfoods_column_check: qty={qty} — likely WEIGHT column, not SHIPPED"
            )

        # SHIPPED is always integer; decimal qty = WEIGHT column
        if qty > 0 and qty != int(qty):
            it.setdefault("validation_errors", []).append(
                f"usfoods_column_check: qty={qty} is decimal — SHIPPED is always integer"
            )

        # ── Column confusion: ORDERED vs SHIPPED ──
        # If qty > 0 but total = 0, the item may have been ordered but not shipped
        # (SHIPPED=0 but ORDERED was extracted as qty)
        if qty > 0 and total == 0 and price > 0:
            it.setdefault("validation_errors", []).append(
                "usfoods_column_check: qty>0 but total=0 — may have used ORDERED instead of SHIPPED"
            )

        # ── Item code validation ──
        if item_code:
            digits_only = re.sub(r'[^0-9]', '', item_code)
            if len(digits_only) < 5 or len(digits_only) > 9:
                it.setdefault("validation_errors", []).append(
                    f"usfoods_column_check: item_code '{item_code}' not standard 7-digit format"
                )

        # ── Math validation ($0.01 tolerance) ──
        if qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            it["valid_calc"] = diff <= 0.01
            if not it["valid_calc"]:
                it.setdefault("validation_errors", []).append(
                    f"usfoods_math: {qty}x{price}={computed} != {total}"
                )
        else:
            it["valid_calc"] = False
            missing = []
            if qty <= 0:
                missing.append("qty")
            if price <= 0:
                missing.append("price")
            if total <= 0:
                missing.append("total")
            it.setdefault("validation_errors", []).append(
                f"usfoods_missing: {','.join(missing)}"
            )

        it["vendor_status"] = "pending"
        it["extraction_source"] = "gpt_vision_usfoods"




def _normalize_date(raw: str) -> str:
    """Try to parse various date formats and return YYYY-MM-DD."""
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()
    from dateutil import parser as dateparser
    try:
        dt = dateparser.parse(raw, dayfirst=False)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        dt = dateparser.parse(raw, dayfirst=True)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return raw


@router.post("/upload/parse-excel")
async def parse_excel(file: UploadFile = File(...), document_type: str = Form("purchase_invoice"), user=Depends(get_user)):
    """Parse Excel/CSV files and extract purchase or sales data."""
    import openpyxl
    import csv as csv_mod
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
                'pack_size': ['pack_weight', 'weight', 'pack_size', 'size', 'pack_wt', 'net_weight', 'pack'],
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

                pack_size_raw = str(row[col_map['pack_size']]).strip() if 'pack_size' in col_map else ''
                unit_raw = row[col_map['unit']].strip().upper() if 'unit' in col_map else ''
                if unit_raw and not pack_size_raw:
                    pack_size_raw = unit_raw

                items_parsed.append({
                    "supplier": row[col_map['supplier']].strip() if 'supplier' in col_map else '',
                    "date": safe_date(row[col_map['date']]) if 'date' in col_map else datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    "invoice_number": row[col_map['invoice_number']].strip() if 'invoice_number' in col_map else '',
                    "raw_name": item_name,
                    "quantity": qty,
                    "pack_size": pack_size_raw,
                    "unit_price": round(up, 2),
                    "total": round(tot, 2),
                })

            groups = {}
            for it in items_parsed:
                key = (it['supplier'] or 'Unknown', it['date'], it['invoice_number'])
                groups.setdefault(key, []).append(it)

            if not groups and items_parsed:
                groups[('Unknown', items_parsed[0]['date'], '')] = items_parsed

            if len(groups) <= 1:
                all_items = [it for items in groups.values() for it in items]
                first = all_items[0] if all_items else {}
                subtotal = round(sum(it['total'] for it in all_items), 2)
                return {"extracted_data": {
                    "supplier_name": first.get('supplier', ''),
                    "invoice_date": first.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')),
                    "invoice_number": first.get('invoice_number', ''),
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "pack_size": it.get('pack_size', ''), "unit_price": it['unit_price'], "total": it['total']} for it in all_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(all_items)}
            else:
                first_key = list(groups.keys())[0]
                first_items = groups[first_key]
                subtotal = round(sum(it['total'] for it in first_items), 2)
                return {"extracted_data": {
                    "supplier_name": first_key[0],
                    "invoice_date": first_key[1],
                    "invoice_number": first_key[2],
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "pack_size": it.get('pack_size', ''), "unit_price": it['unit_price'], "total": it['total']} for it in first_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(items_parsed), "purchase_groups": len(groups),
                   "message": f"Found {len(groups)} purchases with {len(items_parsed)} total items. Showing the first purchase."}
        else:
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


@router.post("/upload/extract")
async def extract_document(files: List[UploadFile] = File(None), file: UploadFile = File(None), document_type: str = Form(...), user=Depends(get_user)):
    try:
        all_files = []
        if files:
            all_files.extend(files)
        if file and file not in all_files:
            all_files.append(file)
        if not all_files:
            raise HTTPException(400, "No files uploaded")

        logger.info(f"Extract: received {len(all_files)} file(s), document_type={document_type}")
        rid = user["restaurant_id"]

        from preprocessing import preprocess_image, get_last_preprocess_meta

        images_b64 = []
        first_content = None
        first_fname = ""
        first_mime = ""
        preprocess_evidence = []  # Track preprocessing for each image

        for idx, f in enumerate(all_files):
            content = await f.read()
            mime = f.content_type or "image/jpeg"
            fname = (f.filename or "").lower()

            if idx == 0:
                first_content = content
                first_fname = fname
                first_mime = mime

            if "pdf" in mime.lower() or fname.endswith(".pdf"):
                import fitz
                pdf_doc = fitz.open(stream=content, filetype="pdf")
                for page_num in range(min(len(pdf_doc), 5)):
                    page = pdf_doc[page_num]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("png")
                    artifact_id = str(uuid.uuid4())[:8]
                    img_bytes = preprocess_image(img_bytes, save_artifacts=True, artifact_id=artifact_id)
                    preprocess_evidence.append(get_last_preprocess_meta())
                    images_b64.append(base64.b64encode(img_bytes).decode())
                pdf_doc.close()
            else:
                artifact_id = str(uuid.uuid4())[:8]
                processed = preprocess_image(content, save_artifacts=True, artifact_id=artifact_id)
                preprocess_evidence.append(get_last_preprocess_meta())
                images_b64.append(base64.b64encode(processed).decode())

        logger.info(f"Extract: {len(images_b64)} total image(s) to process")

        # ── Document Classification (Phase 2) ──
        from services.document_classifier import classify_document, get_parser_route

        file_format = "pdf" if any(
            ("pdf" in (f.content_type or "").lower() or (f.filename or "").lower().endswith(".pdf"))
            for f in (all_files if hasattr(all_files[0], 'content_type') else [])
        ) else "image"
        # Determine file format from stored metadata
        if first_fname.endswith(".pdf") or "pdf" in first_mime.lower():
            file_format = "pdf"

        # Classification happens before vendor detection (vendor info added later)
        doc_classification = classify_document(
            images_b64=images_b64,
            file_format=file_format,
            page_count=len(images_b64),
        )
        parser_route = get_parser_route(doc_classification)
        logger.info(
            f"Classification: {doc_classification['document_type']} "
            f"({doc_classification['confidence_reason']}), route={parser_route}"
        )

        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        from services.llm_rate_limiter import rate_limited_llm_call

        vendor_hint = ""
        vendor_pattern = None
        detect_chat = LlmChat(api_key=LLM_KEY, session_id=f"detect-{uuid.uuid4()}", system_message="You read receipts. Return ONLY the vendor/supplier company name, nothing else. If unclear, return UNKNOWN.").with_model("openai", "gpt-5.2")
        detect_msg = UserMessage(text="What is the vendor/supplier name on this receipt?", file_contents=[ImageContent(image_base64=images_b64[0])])
        detected_vendor = (await rate_limited_llm_call(detect_chat, detect_msg, label="vendor_detect")).strip().strip('"').strip("'")
        logger.info(f"Detected vendor: {detected_vendor}")

        if detected_vendor and detected_vendor.upper() != "UNKNOWN":
            norm_vendor = detected_vendor.lower().strip()
            vp = await db.vendor_patterns.find_one(
                {"restaurant_id": rid, "vendor_name_lower": {"$regex": f".*{re.escape(norm_vendor[:20])}.*", "$options": "i"}},
                {"_id": 0}
            )
            if not vp:
                sup = await db.suppliers.find_one(
                    {"restaurant_id": rid, "name": {"$regex": f".*{re.escape(norm_vendor[:20])}.*", "$options": "i"}},
                    {"_id": 0, "id": 1}
                )
                if sup:
                    vp = await db.vendor_patterns.find_one({"restaurant_id": rid, "vendor_id": sup["id"]}, {"_id": 0})
            if vp:
                vendor_pattern = vp
                hints = vp.get("hints", {})
                hint_parts = []
                if hints.get("date_position"):
                    hint_parts.append(f"Date is usually found {hints['date_position']}")
                if hints.get("line_format"):
                    hint_parts.append(f"Line items are typically formatted as: {hints['line_format']}")
                if hints.get("has_tax"):
                    hint_parts.append("This vendor usually includes tax")
                if hints.get("typical_items"):
                    hint_parts.append(f"Common items from this vendor: {', '.join(hints['typical_items'][:10])}")
                if hints.get("notes"):
                    hint_parts.append(f"Additional notes: {hints['notes']}")
                if hint_parts:
                    vendor_hint = "\n\nVENDOR-SPECIFIC HINTS (from previous receipts):\n" + "\n".join(f"- {h}" for h in hint_parts)

        parsing_method = "vendor" if vendor_pattern else "general"

        # ── Built-in vendor-specific extraction guidance ──
        # Hardcoded layout knowledge for known distributors.
        # This supplements any stored vendor_patterns hints.
        builtin_vendor_hint = ""
        if detected_vendor and detected_vendor.upper() != "UNKNOWN":
            dv_lower = detected_vendor.lower()
            if "performance" in dv_lower or "pfg" in dv_lower:
                builtin_vendor_hint = """

PERFORMANCE FOODSERVICE (PFG) COLUMN LAYOUT:
This is a PFG invoice with a specific columnar format. Read carefully:
- ITEM# (leftmost): 7-digit product code
- DESCRIPTION: product name (text words)
- PACK/SIZE: pack specification like "6/4 LB", "1/25 LB", "4/10 LB", "2/5 OZ". This is NOT the quantity.
- ORD: ordered quantity (integer). This is NOT the shipped quantity.
- SHIP: shipped quantity (integer). THIS IS THE CORRECT QUANTITY to extract.
- WEIGHT: total weight in LBs (decimal). This is NOT the quantity.
- $/LB: price per pound ($-prefixed). This is the unit_price.
- EXT PRICE: extended price ($-prefixed). This is the total.

CRITICAL PFG RULES:
1. quantity MUST come from the SHIP column ONLY, NOT from ORD, PACK, or WEIGHT
2. Pack values like "6/4 LB" or "1/25 LB" are pack specifications, NOT quantities
3. The WEIGHT column shows total weight (e.g., 24.00, 40.00) — do NOT confuse with quantity
4. A "FUEL SURCHARGE" or "SURCHARGE" line is a service charge, not a product
5. If a row has SHIP=0 but ORD>0, it was not delivered — use quantity=0
6. Do NOT default quantity to 1 when uncertain — look at the SHIP column carefully
7. qty_column_visible: set to true if you can SEE a printed number in the SHIP column for this row, false if that column is blank/unreadable"""

            elif "sysco" in dv_lower:
                builtin_vendor_hint = """

SYSCO INVOICE — HORIZONTAL ANCHORING GUIDE:
You are reading a Sysco restaurant supply invoice. The table has a consistent grid layout.

COLUMN ORDER (left to right):
ITEM/CODE | DESCRIPTION | PACK | QTY | PRICE | AMOUNT/TOTAL

ANCHORING STRATEGY:
- The PRICE column and AMOUNT/TOTAL column are the WIDEST and most LEGIBLE columns (right side of the grid)
- For each row, first read the PRICE (second from right) and AMOUNT/TOTAL (rightmost dollar column)
- Then trace LEFT along that same horizontal line to find the QTY value
- QTY is a small integer (typically 1-15) in a narrow column between PACK and PRICE
- PACK contains descriptors like "6/#10", "4/5 LB" — these are NOT quantities

SUB-CATEGORY HEADERS (do NOT treat as line items):
- Lines like ***POULTRY***, ***SEAFOOD***, ***FROZEN***, ***DAIRY***, ***CANNED & DRY*** are section headers — SKIP them
- "GROUP TOTAL" lines are section subtotals — SKIP them
- "SUBTOTAL", "ORDER TOTAL", "INVOICE TOTAL" are summary lines — SKIP them

CRITICAL RULES:
1. quantity comes from the QTY column — it is a small integer, NOT a dollar amount and NOT a pack descriptor
2. If you can see a number at the QTY position, report qty_source="column_read" AND qty_column_visible=true, even if that number is 1
3. If the QTY position is truly unreadable (blurry, cut off, shadowed), use quantity=0, qty_source="ambiguous", qty_column_visible=false
4. NEVER default quantity to 1 — use 0 if unreadable
5. Pack values like "6/#10" are case descriptors, not quantities
6. "FUEL SURCHARGE", "DELIVERY", "SERVICE CHARGE" are service items — extract with quantity=1, qty_source="column_read", qty_column_visible=true
7. Identify columns by their HEADER TEXT, not by fixed pixel positions
8. qty_column_visible is about whether you can SEE a printed digit in the QTY column area — true even when that digit is 1"""

            elif "us foods" in dv_lower or "usfoods" in dv_lower or "us food" in dv_lower:
                builtin_vendor_hint = """

US FOODS INVOICE — STRUCTURAL FIELD MAPPING:
You are reading a US Foods restaurant supply invoice. Extract field values by reading the document grid structure.

COLUMN LAYOUT (identify from the HEADER ROW):
- NUMBER/ITEM#: 7-digit product code (e.g., "1234567", "9876543"). Extract this as item_code — it is SEPARATE from the description.
- BRAND: brand name (e.g., "MONARCH", "CHEF'S LINE", "METRO DELI")
- DESCRIPTION: product name (may merge with adjacent columns when text is dense)
- PACK/SIZE: pack specification (e.g., "4/5 LB", "6/10 CT", "1/15 LB"). This is NOT the quantity.
- ORDERED: quantity ordered (integer)
- SHIPPED: quantity actually delivered. THIS IS the correct quantity to extract.
- WEIGHT: total weight in pounds (decimal). This is NOT the quantity.
- PRICE/UNIT PRICE: unit price per case ($-prefixed)
- EXTENSION/EXT PRICE: extended total for the line ($-prefixed)

ROW CLASSIFICATION:
- Product line items: rows with item code + description + numeric values → extract normally
- "SUBTOTAL" or "SUB-TOTAL": merchandise subtotal → put in "subtotal" field, do NOT extract as line item
- "TAX" or "SALES TAX": tax amount → put in "tax" field, do NOT extract as line item
- "TOTAL" or "INVOICE TOTAL" or "AMOUNT DUE": full total → put in "total" field, do NOT extract as line item
- "FUEL SURCHARGE" or "DELIVERY FEE" or "SERVICE CHARGE": service charges → do NOT include in subtotal
- Section headers (category names like "FROZEN", "DAIRY") → SKIP entirely
- Credit/return lines (negative amounts): extract with negative total

CRITICAL US FOODS RULES:
1. ALWAYS extract item_code from the NUMBER column — it is the 7-digit code at the start of each row
2. quantity MUST come from SHIPPED column, NOT from ORDERED, PACK, or WEIGHT
3. If SHIPPED is 0 but ORDERED > 0, the item was not delivered — use quantity=0
4. WEIGHT column shows total pounds — do NOT use as quantity
5. NEVER default quantity to 1 if SHIPPED column is not readable — use 0 with qty_source="ambiguous"
6. Description and Brand may appear merged — extract the full text as raw_name
7. Pack values like "4/5 LB" mean "4 bags of 5 LB each" — copy verbatim as pack_size
8. qty_column_visible: set to true if you can SEE a printed number in the SHIPPED column for this row, false if that column is blank/unreadable
9. "FUEL SURCHARGE", "DELIVERY FEE", "SERVICE CHARGE" are fee rows — extract with quantity=1, qty_column_visible=true"""

            elif "performance" in dv_lower or "pfg" in dv_lower:
                # Override the existing PFG hint with enhanced version
                builtin_vendor_hint = """

PERFORMANCE FOODSERVICE (PFG) INVOICE — SEMANTIC EXTRACTION GUIDE:
You are reading a PFG invoice. Use semantic understanding to extract data accurately from camera phone photos.

COLUMN LAYOUT (dynamically identify from header row):
- ITEM#: 7-digit product code (leftmost numeric column)
- DESCRIPTION: product name (text words, may be multi-line)
- PACK/SIZE: pack specification like "6/4 LB", "1/25 LB", "4/10 LB", "2/5 OZ". This is NOT the quantity.
- ORD: ordered quantity (integer). This is NOT the shipped quantity.
- SHIP: shipped quantity (integer). THIS IS THE CORRECT QUANTITY to extract.
- WEIGHT: total weight in LBs (decimal). This is NOT the quantity.
- $/LB or UNIT PRICE: price per pound or per unit ($-prefixed). This is the unit_price.
- EXT PRICE or EXTENSION: extended price ($-prefixed). This is the total.

CRITICAL PFG RULES:
1. quantity MUST come from the SHIP column ONLY, NOT from ORD, PACK, or WEIGHT
2. unit_price comes from the $/LB or UNIT PRICE column — identify by header text
3. total comes from the EXT PRICE or EXTENSION column — the rightmost dollar column
4. Pack values like "6/4 LB" or "1/25 LB" are pack specifications, NOT quantities
5. The WEIGHT column shows total weight (e.g., 24.00, 40.00) — do NOT confuse with quantity
6. "FUEL SURCHARGE" or "SURCHARGE" line is a service charge, not a product
7. If a row has SHIP=0 but ORD>0, it was not delivered — use quantity=0
8. Do NOT default quantity to 1 when uncertain — look at the SHIP column carefully
9. $/LB and EXT PRICE are separate columns — read each from its own position
10. qty_column_visible: set to true if you can SEE a printed number in the SHIP column for this row, false if that column is blank/unreadable"""

        # Update classification with vendor info now that we know it
        if vendor_pattern and detected_vendor.upper() != "UNKNOWN":
            doc_classification = classify_document(
                images_b64=images_b64,
                file_format=file_format,
                page_count=len(images_b64),
                vendor_name=detected_vendor,
                has_vendor_pattern=True,
            )
            parser_route = get_parser_route(doc_classification)
            logger.info(f"Classification updated with vendor: {doc_classification['document_type']}")

        page_types = None
        if len(images_b64) > 1 and document_type == "purchase_invoice":
            from preprocessing import classify_pages, build_page_aware_prompt
            page_types = await classify_pages(images_b64, LLM_KEY)
            prompt = build_page_aware_prompt(page_types, vendor_hint)
            logger.info(f"Multi-page purchase: {len(images_b64)} pages, types={page_types}")
        else:
            multi_hint = ""
            if len(images_b64) > 1:
                multi_hint = f"""

MULTI-IMAGE DOCUMENT ({len(images_b64)} images):
These images are parts of ONE document. They may be:
- Separate pages of a multi-page invoice, OR
- Overlapping photos of a long receipt
CRITICAL: Produce ONE unified result. If the same line item appears in multiple images, include it ONLY ONCE. Use the LAST occurrence of subtotal/tax/total. Do NOT duplicate items."""

            if document_type == "purchase_invoice":
                is_sysco_vendor = "sysco" in (detected_vendor or "").lower()

                if is_sysco_vendor:
                    # ── SYSCO STRICT READ-ONLY PROMPT WITH HORIZONTAL ANCHORING ──
                    # LLM Vision extracts candidate rows ONLY. No math. No inference. No defaults.
                    # Horizontal anchoring: use Price/Total columns (wider, more legible) to locate the Qty column.
                    prompt = f"""You are reading a Sysco restaurant purchase invoice from a camera phone photo. READ the document exactly as printed. Do NOT compute or infer any numbers.

Extract into this exact JSON format:
{{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0,"qty_source":"","price_source":"","total_source":"","item_code":"","qty_column_visible":false}}],"subtotal":0,"tax":0,"total":0}}

HORIZONTAL ANCHORING TECHNIQUE:
Sysco invoices have a consistent columnar grid. The PRICE and AMOUNT/TOTAL columns are on the right side and contain wider, more legible dollar values. Use them as anchors:
1. First, identify the PRICE column and AMOUNT/TOTAL column — these are the two rightmost numeric columns with dollar values
2. For each row where you can clearly read the PRICE and AMOUNT/TOTAL values, trace horizontally LEFT along that same row
3. The QTY column is typically a narrow column between PACK and PRICE containing a small integer (usually 1-15 for restaurant orders)
4. Look carefully at the QTY column position for that row — the number should be a small integer
5. If you can see a number at the QTY column position for that row, report it with qty_source="column_read"
6. If the QTY area is obscured, blurry, or the number is not visually distinct, use qty_source="ambiguous" and quantity=0

STRICT READING RULES:
- Scan the HEADER ROW to dynamically identify column positions (QTY, PACK, DESCRIPTION, PRICE, AMOUNT, etc.)
- For each line item, READ quantity, unit_price, and total DIRECTLY from their respective columns
- If you CANNOT clearly read a number from its column, use 0 — do NOT calculate it from other fields
- Do NOT compute total from qty x price
- Do NOT compute qty from total / price
- Do NOT compute price from total / qty
- Do NOT default quantity to 1 when you cannot see it — use 0 with qty_source="ambiguous"
- NEVER assume quantity is 1. If you cannot see the number, it is 0 with source "ambiguous"
- Read pack_size verbatim from the PACK column. Leave "" if not visible.
- Extract item_code from the ITEM/CODE column if visible
- Dates must be in YYYY-MM-DD format

ROW EXCLUSION — Do NOT extract these as line items:
- Lines containing "GROUP TOTAL", "SUBTOTAL", "ORDER TOTAL", "INVOICE TOTAL", "ORDER SUMMARY", "INVOICE SUMMARY"
- Section/category headers: ***POULTRY***, ***SEAFOOD***, ***FROZEN***, ***DAIRY***, ***CANNED & DRY***, etc.
- Any row that is clearly a summary, total, or section header — SKIP it entirely

NON-PRODUCT ROWS — Extract these separately if visible:
- "subtotal" field: the merchandise/product subtotal (sum of product line items ONLY, before tax/fees)
- "tax" field: sales tax amount
- "total" field: full invoice total including tax
- Do NOT include fuel surcharge, delivery fees, or service charges in the subtotal

FIELD SOURCE (for each item):
- qty_source: "column_read" if you can see a distinct number at the QTY column position for this row, "ambiguous" if the QTY area is obscured/blurry/uncertain
- price_source: "column_read" if you clearly see it in the PRICE column, "ambiguous" if uncertain
- total_source: "column_read" if you clearly see it in the AMOUNT/TOTAL column, "ambiguous" if uncertain
- NEVER use "inferred" — you are not allowed to infer any values

QTY COLUMN VISIBILITY (critical for qty=1 items):
- qty_column_visible: Set to true if you can VISUALLY SEE a number printed in the QTY column position for this row, even if that number is "1". Set to false if the QTY column area is blank, obscured, cut off, or you cannot distinguish any printed digit there.
- This field is about VISUAL PRESENCE of a digit in the QTY column, NOT about whether you are confident in the value.
- Example: If you see a printed "1" in the QTY column → qty_column_visible=true, quantity=1, qty_source="column_read"
- Example: If the QTY column area is blank or unreadable → qty_column_visible=false, quantity=0, qty_source="ambiguous"

- Return ONLY the JSON object, no other text.{vendor_hint}{builtin_vendor_hint}{multi_hint}"""
                else:
                    # ── GENERIC PROMPT (non-Sysco vendors) ──
                    prompt = f"""You are an expert at reading restaurant purchase invoices from camera phone photos. Use semantic understanding to interpret the document structure even if the image has noise, skew, shadows, or perspective distortion.

Extract ALL data into this exact JSON format:
{{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0,"qty_source":"","price_source":"","total_source":"","item_code":""}}],"subtotal":0,"tax":0,"total":0}}

CRITICAL rules for line items:
- Scan the HEADER ROW to dynamically identify column positions
- Look for patterns like: "2 x 5.00", "5.00 x 2", "2 @ 5.00", "Qty 2 Price 5.00"
- In columnar layouts, match quantity + unit price + total from the same row
- total = quantity * unit_price for each line item
- If unit_price is missing but total and quantity are known: unit_price = total / quantity
- If quantity is missing but total and unit_price are known: quantity = total / unit_price
- subtotal = sum of all item totals
- total = subtotal + tax
- Dates must be in YYYY-MM-DD format. Convert any date format you see.
- Use 0 for any truly missing numeric values
- Extract item_code from the ITEM/CODE column if visible
- pack_size: The pack/case size EXACTLY as shown on the invoice. Common formats: "10/4 LB" (10 packs of 4 LB), "6/5 LB", "BAG 50 LB", "150 EA", "1 GAL", "2/17.5 LB", "1/25 LB", "12/1 QT", "50 LB", "10#". Copy this field verbatim. Leave empty string "" if not visible.
- Do NOT treat section headers or category dividers as line items
- Do NOT default quantity to 1 when uncertain — read the QTY column

NUMERIC FIELD SOURCE (for each item):
- qty_source: How was this quantity determined?
  "column_read" = clearly visible number in the QTY/ORDERED/SHIP column
  "inferred" = calculated from other fields (e.g. total / unit_price)
  "ambiguous" = number exists but uncertain which column it belongs to
- price_source: How was this unit_price determined?
  "column_read" = clearly visible number in the PRICE/UNIT PRICE column
  "inferred" = calculated from other fields (e.g. total / quantity)
  "ambiguous" = number exists but uncertain which column it belongs to
- total_source: How was this total determined?
  "column_read" = clearly visible number in the TOTAL/AMOUNT/EXT PRICE column
  "inferred" = calculated from other fields (e.g. quantity * unit_price)
  "ambiguous" = number exists but uncertain which column it belongs to

- Return ONLY the JSON object, no other text.{vendor_hint}{builtin_vendor_hint}{multi_hint}"""
            elif document_type == "salary_document":
                prompt = f"""You are reading a payroll document, salary slip, or payment record for restaurant staff. Extract data into this exact JSON format:
{{"employee_name":"","position":"","amount":0,"payment_date":"YYYY-MM-DD","notes":"","pay_period":"","deductions":0,"gross_amount":0}}

Rules:
- employee_name: the person being paid
- position: their role/title if mentioned (e.g., Chef, Server, Manager)
- amount: the NET pay amount (after deductions). This is the most important field.
- payment_date: date of payment in YYYY-MM-DD format
- notes: any relevant details (payment method, reference number, etc.)
- pay_period: the period covered (e.g., "March 2026", "March 1-15")
- deductions: total deductions if shown, else 0
- gross_amount: gross pay before deductions if shown, else 0
- If this is a summary with multiple employees, extract the FIRST/PRIMARY employee
- Dates must be in YYYY-MM-DD format
- Use 0 for missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""
            elif document_type == "other_expense":
                prompt = f"""You are reading a utility bill, tax document, service invoice, maintenance bill, or general expense document for a restaurant. Extract data into this exact JSON format:
{{"title":"","category":"","amount":0,"expense_date":"YYYY-MM-DD","notes":"","vendor_name":"","reference_number":""}}

Rules:
- title: a short description of the expense (e.g., "March Electricity Bill", "Kitchen Equipment Repair")
- category: classify as EXACTLY one of: Utilities, Taxes, Maintenance & Repairs, Software & Subscriptions, Services, Rent / Facility, Miscellaneous
  - Utilities: electricity, water, gas, internet, phone bills
  - Taxes: tax payments, filings, government fees
  - Maintenance & Repairs: equipment repair, plumbing, HVAC, cleaning services
  - Software & Subscriptions: POS systems, accounting software, delivery apps
  - Services: legal, accounting, consulting, pest control, security
  - Rent / Facility: rent, lease, property insurance, facility costs
  - Miscellaneous: anything that doesn't fit above
- amount: the total amount due/paid
- expense_date: the bill date or due date in YYYY-MM-DD format
- notes: any useful details (account number, meter readings, service description)
- vendor_name: the company/provider name
- reference_number: invoice/bill/reference number if shown
- This may be a simple summary document, not an itemized receipt
- Dates must be in YYYY-MM-DD format
- Use 0 for missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""
            else:
                prompt = f"""You are reading a restaurant sales report or receipt. Extract ALL data into this exact JSON format:
{{"report_date":"YYYY-MM-DD","total_sales":0,"items":[{{"menu_item":"","quantity":0,"revenue":0}}]}}

Rules:
- total_sales should be the grand total
- For each item, revenue is the total amount for that item
- Dates must be in YYYY-MM-DD format
- Use 0 for any truly missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""

        # ── GPT Vision Extraction (all vendors) ──
        chat = LlmChat(api_key=LLM_KEY, session_id=f"extract-{uuid.uuid4()}", system_message="You are an expert at reading restaurant invoices and receipts. Extract data accurately by reading the document. Return valid JSON only, no markdown fences.").with_model("openai", "gpt-5.2")
        file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]
        user_msg = UserMessage(text=prompt, file_contents=file_contents)
        response = await rate_limited_llm_call(chat, user_msg, label="extract_invoice")

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                extracted = json.loads(json_match.group())
            except json.JSONDecodeError:
                from preprocessing import salvage_partial_extraction
                extracted = salvage_partial_extraction(response)
                logger.warning(f"JSON decode failed, salvaged partial extraction: {list(extracted.keys())}")
        else:
            from preprocessing import salvage_partial_extraction
            extracted = salvage_partial_extraction(response)
            logger.warning(f"No JSON found in response, salvaged: {list(extracted.keys())}")

        receipt_id = str(uuid.uuid4())

        # ── Layout parsing (Phase 3) — runs in parallel with LLM ──
        layout_parse_result = None
        try:
            from services.layout_parser import parse_invoice_layout
            if document_type == "purchase_invoice" and images_b64:
                layout_parse_result = parse_invoice_layout(
                    b64_image=images_b64[0],
                    document_type=doc_classification.get("document_type", "structured_invoice"),
                    vendor_name=detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
                )
                logger.info(
                    f"Layout parser: {layout_parse_result['parser_used']}, "
                    f"{len(layout_parse_result['items'])} items, "
                    f"{layout_parse_result['row_count']} rows, "
                    f"header={'yes' if layout_parse_result['header_detected'] else 'no'}"
                )
        except Exception as e:
            logger.warning(f"Layout parsing failed (non-fatal): {e}")

        receipt_doc = {
            "id": receipt_id,
            "restaurant_id": rid,
            "file_name": first_fname or "untitled",
            "file_type": first_mime,
            "file_count": len(all_files),
            "page_types": page_types,
            "document_classification": doc_classification,
            "parser_route": parser_route,
            "layout_parse": {
                "parser_used": layout_parse_result["parser_used"],
                "item_count": len(layout_parse_result["items"]),
                "row_count": layout_parse_result["row_count"],
                "column_count": layout_parse_result["column_count"],
                "header_detected": layout_parse_result["header_detected"],
                "validation_summary": layout_parse_result.get("validation_summary"),
                "semantic_summary": layout_parse_result.get("semantic_summary"),
            } if layout_parse_result else None,
            "raw_ocr_text": response[:5000],
            "detected_vendor": detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
            "vendor_id": vendor_pattern.get("vendor_id") if vendor_pattern else None,
            "parsing_method": parsing_method,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        ext = first_fname.rsplit(".", 1)[-1] if "." in first_fname else "jpg"
        stored_name = f"receipt_{receipt_id}.{ext}"
        file_path = UPLOADS_DIR / stored_name
        with open(file_path, "wb") as f:
            f.write(first_content)
        receipt_doc["file_url"] = f"/uploads/{stored_name}"
        await db.uploaded_receipts.insert_one(receipt_doc)

        extraction_meta = None

        if "error" not in extracted:
            if document_type == "purchase_invoice":
                from preprocessing import (
                    enrich_item_with_pack_size, validate_and_score_item,
                    validate_purchase_items, sanitize_extracted_item,
                    compute_extraction_meta,
                )
                from services.normalization import normalize_item

                warnings = []
                processed_items = []
                is_sysco = "sysco" in (detected_vendor or "").lower()

                for idx, item in enumerate(extracted.get("items", [])):
                    try:
                        sanitize_extracted_item(item)

                        qty = float(item.get("quantity", 0) or 0)
                        up = float(item.get("unit_price", 0) or 0)
                        tot = float(item.get("total", 0) or 0)
                        item_warnings = []

                        # ── Math infill — DISABLED for Sysco (strict read-only) ──
                        if is_sysco:
                            if tot == 0 and (qty > 0 or up > 0):
                                item_warnings.append("total is zero (not infilled — Sysco strict mode)")
                            if up == 0 and tot > 0:
                                item_warnings.append("unit_price is zero (not infilled — Sysco strict mode)")
                            if qty == 0 and tot > 0:
                                item_warnings.append("quantity is zero (not infilled — Sysco strict mode)")
                        else:
                            if tot == 0 and qty > 0 and up > 0:
                                item["total"] = round(qty * up, 2)
                                item["total_source"] = "inferred"
                                tot = item["total"]
                            elif up == 0 and tot > 0 and qty > 0:
                                item["unit_price"] = round(tot / qty, 2)
                                item["price_source"] = "inferred"
                                up = item["unit_price"]
                            elif qty == 0 and tot > 0 and up > 0:
                                item["quantity"] = round(tot / up, 2)
                                item["qty_source"] = "inferred"
                                qty = item["quantity"]

                        if qty > 0 and up > 0 and tot > 0:
                            expected = round(qty * up, 2)
                            if abs(expected - tot) > 0.02:
                                item_warnings.append(f"qty*price={expected} but total={tot}")
                                item["_warning"] = True

                        if qty == 0:
                            item_warnings.append("missing quantity")
                            item["_warning"] = True
                        if up == 0 and tot == 0:
                            item_warnings.append("missing price and total")
                            item["_warning"] = True
                        if not item.get("raw_name", "").strip():
                            item_warnings.append("missing item name")
                            item["_warning"] = True

                        pack_raw = item.get("pack_size", "") or ""
                        if pack_raw:
                            item["pack_size"] = pack_raw
                            enrich_item_with_pack_size(item)

                        normalize_item(item)
                        validate_and_score_item(item)

                        if item.get("_parse_issues"):
                            item_warnings.extend(item["_parse_issues"])

                        if item_warnings:
                            item["_warning_detail"] = "; ".join(item_warnings)
                            warnings.extend(item_warnings)

                        processed_items.append(item)
                    except Exception as item_err:
                        logger.error(f"Item {idx} processing failed: {item_err}")
                        item["_warning"] = True
                        item["_warning_detail"] = f"Processing error: {str(item_err)}"
                        item["confidence_level"] = "extraction_failed"
                        item["confidence_score"] = 0
                        item["needs_review"] = True
                        item["review_reason"] = f"Processing error: {str(item_err)}"
                        warnings.append(f"Item {idx}: processing error")
                        processed_items.append(item)

                extracted["items"] = processed_items

                # ── Row Type Classification (FIRST) ──
                _classify_all_row_types(extracted["items"])

                # ── System-level numeric source validation ──
                scoreable_items = [it for it in extracted["items"]
                                   if it.get("row_type") in ("line_item", "fee")]
                _validate_numeric_field_sources(scoreable_items)

                # Non-line-item rows: mark as excluded
                for it in extracted["items"]:
                    if it.get("row_type") not in ("line_item", "fee"):
                        it["confidence_level"] = "excluded"
                        it["needs_review"] = False
                        it["review_reason"] = f"Row type '{it.get('row_type')}' excluded from trust evaluation"
                        it["numeric_failure_category"] = "n/a"

                # ── Vendor-specific post-extraction validation ──
                dv_lower = (detected_vendor or "").lower()

                if "performance" in dv_lower or "pfg" in dv_lower:
                    _validate_pfg_extraction(extracted["items"])
                    _apply_pfg_trust_gate(extracted)
                    for it in extracted.get("items", []):
                        if it.get("row_type") in ("line_item", "fee"):
                            it["vendor_status"] = "controlled_operational"
                            it["extraction_source"] = "gpt_vision_pfg"

                elif "us foods" in dv_lower or "usfoods" in dv_lower or "us food" in dv_lower:
                    # ── US FOODS: Structural mapping + math gate + trust assignment ──
                    _validate_usfoods_extraction(extracted["items"])
                    _apply_usfoods_trust_gate(extracted)
                    for it in extracted.get("items", []):
                        if it.get("row_type") in ("line_item", "fee"):
                            it["vendor_status"] = "controlled_operational"
                            it["extraction_source"] = "gpt_vision_usfoods"

                elif "sysco" in dv_lower:
                    # ── SYSCO STRICT MATH-FIRST VALIDATION ──
                    _validate_sysco_extraction(extracted["items"])
                    await _apply_sysco_math_first_gate(extracted)
                    for it in extracted.get("items", []):
                        if it.get("row_type") in ("line_item", "fee"):
                            it["vendor_status"] = "controlled_operational"
                            it["extraction_source"] = "gpt_vision_strict"

                else:
                    # ── ALL OTHER VENDORS: Vendor Logic Pending ──
                    # Run math validation but do NOT grant Trusted status
                    for it in extracted.get("items", []):
                        if it.get("row_type") in ("line_item", "fee"):
                            it["confidence_level"] = "vendor_logic_pending"
                            it["needs_review"] = True
                            vendor_label = detected_vendor if detected_vendor.upper() != "UNKNOWN" else "Unknown vendor"
                            if not it.get("review_reason"):
                                it["review_reason"] = f"Review Required (Vendor Logic Pending) — {vendor_label} trust gate not yet implemented"
                            it["vendor_status"] = "pending"
                            it["extraction_source"] = "gpt_vision"

                # ── Trust Decision Audit Trail ──
                # Every row gets a structured trust_decision showing:
                # row_type, extracted fields, validation results, final status, reason
                for it in extracted.get("items", []):
                    qty = float(it.get("quantity", 0) or 0)
                    price = float(it.get("unit_price", 0) or 0)
                    total = float(it.get("total", 0) or 0)
                    rt = it.get("row_type", "unknown")
                    conf = it.get("confidence_level", "unknown")

                    # Build gates summary
                    gates = {}
                    if rt in ("line_item", "fee"):
                        if rt == "fee":
                            gates["fee_total_present"] = total > 0
                            gates["fee_math_rule"] = "total > 0 (no qty×price required)"
                        else:
                            gates["qty_source"] = it.get("qty_source", "?")
                            gates["price_source"] = it.get("price_source", "?")
                            gates["total_source"] = it.get("total_source", "?")
                            gates["math_check"] = it.get("valid_calc", False)
                            if it.get("qty_column_visible") is not None:
                                gates["qty_column_visible"] = it.get("qty_column_visible")

                        gates["vendor_check"] = it.get("vendor_status", "none")
                        errors = it.get("validation_errors", [])
                        if errors:
                            gates["validation_errors"] = errors

                    it["trust_decision"] = {
                        "row_type": rt,
                        "extracted": {
                            "raw_name": (it.get("raw_name") or "")[:60],
                            "item_code": (it.get("item_code") or "")[:15],
                            "quantity": qty,
                            "unit_price": price,
                            "total": total,
                            "pack_size": (it.get("pack_size") or "")[:20],
                        },
                        "gates": gates,
                        "final_status": conf,
                        "failure_category": it.get("numeric_failure_category", "n/a"),
                        "reason": it.get("confidence_reason") or it.get("review_reason") or "n/a",
                    }

                # ── Subtotal validation (all vendors) ──
                line_items_for_sum = [it for it in extracted.get("items", [])
                                      if it.get("row_type") in ("line_item", "fee")]
                items_sum = round(sum(float(it.get("total", 0) or 0) for it in line_items_for_sum), 2)
                if not extracted.get("subtotal") and items_sum > 0:
                    extracted["subtotal"] = items_sum
                if not extracted.get("total") and items_sum > 0:
                    extracted["total"] = round(items_sum + float(extracted.get("tax", 0) or 0), 2)

                if "sysco" in dv_lower:
                    # Sysco-specific subtotal validation with partial-page awareness
                    subtotal = float(extracted.get("subtotal", 0) or 0)
                    if items_sum > 0 and subtotal > 0 and abs(items_sum - subtotal) > 0.10:
                        pct_diff = abs(items_sum - subtotal) / subtotal if subtotal else 0

                        if items_sum < subtotal:
                            extracted["_invoice_completeness"] = "partial"
                            extracted["_partial_reason"] = (
                                f"Items sum ${items_sum:.2f} is {pct_diff:.0%} below declared subtotal "
                                f"${subtotal:.2f} — likely a partial page photo"
                            )
                            warnings.append(
                                f"Partial page: items sum (${items_sum:.2f}) < subtotal (${subtotal:.2f}). "
                                f"Row-level trust preserved; invoice-level subtotal unverified."
                            )
                            extracted["_subtotal_warning"] = True
                        else:
                            # Over-extraction: items_sum > declared subtotal.
                            # Mark the INVOICE as over_extracted (informational only).
                            # DO NOT downgrade individually validated rows.
                            # Valid data stays valid — row correctness is independent of invoice-level sums.
                            extracted["_invoice_completeness"] = "over_extracted"
                            warnings.append(
                                f"Invoice-level note: items sum (${items_sum:.2f}) exceeds "
                                f"declared subtotal (${subtotal:.2f}) by {pct_diff:.0%}. "
                                f"Row-level trust preserved."
                            )
                            extracted["_subtotal_warning"] = True
                    else:
                        extracted["_invoice_completeness"] = "complete" if subtotal > 0 else "unknown"

                    total = float(extracted.get("total", 0) or 0)
                    tax = float(extracted.get("tax", 0) or 0)
                    if subtotal > 0 and total > 0:
                        expected_total = round(subtotal + tax, 2)
                        if abs(expected_total - total) > 0.10:
                            warnings.append(f"subtotal+tax={expected_total} but total={total}")
                            extracted["_total_warning"] = True

                raw_date = extracted.get("invoice_date", "")
                if raw_date:
                    normalized = _normalize_date(raw_date)
                    if normalized != raw_date:
                        extracted["invoice_date"] = normalized
                        if not normalized:
                            warnings.append(f"Could not parse date: {raw_date}")
                            extracted["_date_warning"] = True

                extracted["_warnings"] = warnings
                extracted["_has_warnings"] = len(warnings) > 0

                # Cross-item validation
                validate_purchase_items(extracted["items"])

                # Compute invoice-level extraction quality (both paths)
                extraction_meta = compute_extraction_meta(extracted["items"], extracted)

        extraction_id = str(uuid.uuid4())
        ext_doc = {
            "id": extraction_id,
            "receipt_id": receipt_id,
            "restaurant_id": rid,
            "date": extracted.get("invoice_date", "") if document_type == "purchase_invoice" else extracted.get("report_date", ""),
            "total": float(extracted.get("total", 0) or extracted.get("total_sales", 0) or 0),
            "parsing_method": parsing_method,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.receipt_extractions.insert_one(ext_doc)

        items_to_store = extracted.get("items", [])
        if items_to_store:
            item_docs = []
            for it in items_to_store:
                item_docs.append({
                    "id": str(uuid.uuid4()),
                    "extraction_id": extraction_id,
                    "item_name": it.get("raw_name", "") or it.get("menu_item", ""),
                    "quantity": float(it.get("quantity", 0) or 0),
                    "unit_price": float(it.get("unit_price", 0) or 0),
                    "total": float(it.get("total", 0) or it.get("revenue", 0) or 0),
                })
            await db.extracted_items.insert_many(item_docs)

        # ── Persist Sysco trusted extraction for Product Memory ──
        if document_type == "purchase_invoice" and detected_vendor and "sysco" in (detected_vendor or "").lower():
            trusted_items_for_memory = []
            for it in items_to_store:
                if it.get("confidence_level") == "trusted" or it.get("confidence_level") == "review_with_memory_support":
                    trusted_items_for_memory.append({
                        "raw_name": (it.get("raw_name") or "").strip(),
                        "item_code": (it.get("item_code") or "").strip(),
                        "quantity": float(it.get("quantity", 0) or 0),
                        "unit_price": float(it.get("unit_price", 0) or 0),
                        "total": float(it.get("total", 0) or 0),
                        "pack_size": (it.get("pack_size") or "").strip(),
                        "confidence_level": it.get("confidence_level", ""),
                        "row_type": it.get("row_type", ""),
                        "qty_source": it.get("qty_source", ""),
                        "price_source": it.get("price_source", ""),
                        "total_source": it.get("total_source", ""),
                        "normalized_quantity": it.get("normalized_quantity"),
                        "normalized_unit": it.get("normalized_unit"),
                        "price_per_unit": it.get("price_per_unit"),
                        "unit_status": it.get("unit_status"),
                    })
            if trusted_items_for_memory:
                await db.sysco_trusted_extractions.insert_one({
                    "detected_vendor": detected_vendor,
                    "supplier_name": extracted.get("supplier_name", ""),
                    "invoice_number": extracted.get("invoice_number", ""),
                    "extraction_id": extraction_id,
                    "items": trusted_items_for_memory,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

            # ── Save review items for Review Queue ──
            review_items_for_queue = []
            for it in items_to_store:
                cl = it.get("confidence_level", "")
                if cl in ("trusted", "excluded", "review_with_memory_support"):
                    continue
                if it.get("needs_review") or cl in ("needs_review_numeric", "needs_review"):
                    nfc = it.get("numeric_failure_category", "")
                    reason_label = "Review Required"
                    if cl == "review_with_memory_support":
                        reason_label = "Memory Supported (Qty=1)"
                    elif nfc == "source_not_column_read":
                        reason_label = "Qty Ambiguous"
                    elif nfc == "math_mismatch":
                        reason_label = "Price Mismatch"
                    elif nfc == "qty_wrong":
                        reason_label = "Qty Missing"
                    elif nfc == "price_wrong":
                        reason_label = "Price Missing"
                    elif nfc == "both_wrong":
                        reason_label = "Qty & Price Missing"
                    elif nfc == "total_missing":
                        reason_label = "Total Missing"

                    review_items_for_queue.append({
                        "id": str(uuid.uuid4()),
                        "extraction_id": extraction_id,
                        "raw_name": (it.get("raw_name") or "").strip(),
                        "item_code": (it.get("item_code") or "").strip(),
                        "quantity": float(it.get("quantity", 0) or 0),
                        "unit_price": float(it.get("unit_price", 0) or 0),
                        "total": float(it.get("total", 0) or 0),
                        "vendor": detected_vendor or "Unknown",
                        "invoice_number": extracted.get("invoice_number", ""),
                        "invoice_date": extracted.get("invoice_date", ""),
                        "confidence_level": cl,
                        "numeric_failure_category": nfc,
                        "reason_label": reason_label,
                        "review_reason": (it.get("review_reason") or "")[:200],
                        "status": "review",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            if review_items_for_queue:
                await db.sysco_review_items.insert_many(review_items_for_queue)

        if isinstance(extracted.get("items"), list) and document_type != "purchase_invoice":
            from preprocessing import validate_purchase_items
            validate_purchase_items(extracted["items"])

        # Apply correction memory (supplier-scoped, strict_match_key only)
        if document_type == "purchase_invoice" and isinstance(extracted.get("items"), list):
            from services.correction_memory import apply_corrections
            supplier_id_for_correction = ""
            detected_name = (detected_vendor or "").strip()
            if detected_name and detected_name.upper() != "UNKNOWN":
                sup = await db.suppliers.find_one(
                    {"restaurant_id": rid, "name": {"$regex": f".*{re.escape(detected_name[:20])}.*", "$options": "i"}},
                    {"_id": 0, "id": 1},
                )
                if sup:
                    supplier_id_for_correction = sup["id"]
            if supplier_id_for_correction:
                await apply_corrections(extracted["items"], rid, supplier_id_for_correction)

        result = {
            "extracted_data": extracted,
            "document_type": document_type,
            "receipt_id": receipt_id,
            "parsing_method": parsing_method,
            "page_types": page_types,
            "document_classification": doc_classification,
            "parser_route": parser_route,
            "layout_parse": {
                "parser_used": layout_parse_result["parser_used"],
                "items": layout_parse_result["items"],
                "row_count": layout_parse_result["row_count"],
                "column_count": layout_parse_result["column_count"],
                "header_detected": layout_parse_result["header_detected"],
                "validation_summary": layout_parse_result.get("validation_summary"),
                "semantic_summary": layout_parse_result.get("semantic_summary"),
            } if layout_parse_result else None,
            "detected_vendor": detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
            "preprocess_evidence": preprocess_evidence,
            "message": f"Data extracted using {parsing_method} parsing" + (" (vendor pattern matched)" if parsing_method == "vendor" else "") + (f" -- pages classified as {page_types}" if page_types else ""),
        }

        # Attach extraction quality metadata for purchase invoices
        if document_type == "purchase_invoice":
            if extraction_meta is None:
                from preprocessing import compute_extraction_meta
                extraction_meta = compute_extraction_meta(extracted.get("items", []) if isinstance(extracted.get("items"), list) else [], extracted)
            result["extraction_meta"] = extraction_meta

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(500, f"Extraction failed: {str(e)}")


@router.get("/llm-stats")
async def get_llm_stats_endpoint():
    """Return LLM rate limiter statistics."""
    from services.llm_rate_limiter import get_llm_stats
    return get_llm_stats()
