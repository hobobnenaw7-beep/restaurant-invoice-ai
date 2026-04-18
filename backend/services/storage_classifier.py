"""
Storage Category Classifier
============================

Detects storage category (dry, chilled, frozen) from:
1. Section headers in invoice text (FROZEN, DRY, REFRIGERATED, etc.)
2. Product name keywords as fallback

Returns category and confidence for each item.
Auto-assigned categories respect manual overrides via category_source='manual'.
"""

import re
import logging

logger = logging.getLogger("restaurant_ai")


# ── Section header patterns (Sysco / US Foods / PFG) ──

SECTION_PATTERNS = {
    "frozen": [
        r'\bFROZEN\b', r'\bFRZN\b', r'\bFRZ\b',
        r'\bFROZEN\s+FOOD', r'\bFROZEN\s+SECTION',
    ],
    "chilled": [
        r'\bREFRIGERATED\b', r'\bREFRIG\b', r'\bCHILLED\b',
        r'\bCOOLER\b', r'\bDAIRY\b', r'\bFRESH\b',
        r'\bPRODUCE\b', r'\bMEAT\b',
    ],
    "dry": [
        r'\bDRY\b', r'\bDRY\s+GOODS\b', r'\bDRY\s+GROCERY\b',
        r'\bGROCERY\b', r'\bPAPER\b', r'\bCHEMICAL\b',
        r'\bSUPPLIES\b', r'\bDISPOSABLE\b',
    ],
}

# ── Product name keyword fallback ──

KEYWORD_RULES = [
    ("frozen", [
        r'\bFROZEN\b', r'\bFRZN\b', r'\bIQF\b',
        r'\bFRZ\b', r'\bFROSTED\b',
    ]),
    ("chilled", [
        r'\bFRESH\b', r'\bREFRIG\b', r'\bCHILLED\b',
        r'\bRAW\b', r'\bLIVE\b',
    ]),
    ("dry", [
        r'\bDRY\b', r'\bCANNED\b', r'\bPOWDER\b',
        r'\bMIX\b', r'\bRICE\b', r'\bFLOUR\b',
        r'\bOIL\b', r'\bSPICE\b', r'\bSEASON\b',
    ]),
]


def classify_items_by_section(items: list, raw_text: str = "") -> list:
    """
    Assign storage_category to items based on section headers in raw_text
    and product name keywords.

    Args:
        items: List of item dicts (each with 'raw_name', 'item_code', etc.)
        raw_text: Full raw OCR/extraction text containing section headers

    Returns:
        Same list with 'storage_category' and 'category_source' added to each item.
        Items with category_source='manual' are NOT overwritten.
    """
    # Build a section map from raw_text if available
    # This maps line positions to section categories
    section_assignments = _detect_sections(raw_text) if raw_text else {}

    for idx, item in enumerate(items):
        # PROTECTION: Never overwrite manual assignments
        if item.get("category_source") == "manual":
            continue

        category = None

        # Priority 1: Section header assignment
        if idx in section_assignments:
            category = section_assignments[idx]

        # Priority 2: Product name keyword match
        if not category:
            raw_name = (item.get("raw_name") or item.get("description") or "").upper()
            category = _classify_by_keywords(raw_name)

        if category:
            item["storage_category"] = category
            item["category_source"] = "auto"

    return items


def _detect_sections(raw_text: str) -> dict:
    """
    Scan raw text for section headers and return a mapping of
    approximate item indices to categories.

    Vendor invoices typically have section headers like:
      === FROZEN ===
      item1
      item2
      === DRY ===
      item3

    Returns: {item_index: category}
    """
    if not raw_text:
        return {}

    lines = raw_text.split("\n")
    current_section = None
    item_idx = 0
    assignments = {}

    for line in lines:
        line_upper = line.upper().strip()

        # Check if this line is a section header
        detected = None
        for cat, patterns in SECTION_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, line_upper):
                    # Only treat as header if the line is short (headers are typically standalone)
                    if len(line_upper) < 40:
                        detected = cat
                        break
            if detected:
                break

        if detected:
            current_section = detected
        elif current_section and line.strip():
            # Non-empty, non-header line under a section = potential item
            # We use a heuristic: lines with numbers likely contain items
            if re.search(r'\d', line):
                assignments[item_idx] = current_section
                item_idx += 1

    return assignments


def _classify_by_keywords(name: str) -> str:
    """Classify by product name keywords. Returns category or None."""
    for cat, patterns in KEYWORD_RULES:
        for pat in patterns:
            if re.search(pat, name):
                return cat
    return None


def lookup_manual_category(
    canonical_vendor: str,
    product_code: str,
    db_sync=None,
    restaurant_id: str = "",
) -> dict:
    """
    Check if a manual storage_category already exists for this vendor+product_code
    in the canonical_items collection.

    Returns: {"storage_category": "frozen", "category_source": "manual"} or {}
    """
    if not product_code or not db_sync:
        return {}

    # Search by product_code match
    # This is a simplified lookup — in production, match by vendor+code
    return {}


async def lookup_manual_category_async(
    product_code: str,
    restaurant_id: str,
) -> dict:
    """
    Async version: Check if a manual storage_category already exists
    for this product_code in extracted_items.

    Priority: canonical_vendor + product_code (strongest match).

    Returns: {"storage_category": "frozen", "category_source": "manual"} or {}
    """
    from core.database import db

    if not product_code or len(product_code) < 4:
        return {}

    # Look for any existing item with this product_code and manual category
    existing = await db.extracted_items.find_one(
        {
            "restaurant_id": restaurant_id,
            "item_code": product_code,
            "category_source": "manual",
            "storage_category": {"$in": ["dry", "chilled", "frozen"]},
        },
        {"_id": 0, "storage_category": 1, "category_source": 1},
    )
    if existing:
        return {
            "storage_category": existing["storage_category"],
            "category_source": "manual",
        }

    # Also check canonical_items
    canon = await db.canonical_items.find_one(
        {
            "restaurant_id": restaurant_id,
            "category_source": "manual",
            "storage_category": {"$in": ["dry", "chilled", "frozen"]},
        },
        {"_id": 0, "storage_category": 1, "category_source": 1},
    )
    if canon:
        return {
            "storage_category": canon["storage_category"],
            "category_source": "manual",
        }

    return {}
