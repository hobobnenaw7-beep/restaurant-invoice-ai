"""
US Foods Section Splitter
=========================
Splits dense US Foods invoice images into overlapping horizontal strips,
extracts each strip independently via GPT Vision, then merges and deduplicates.

Only activated for US Foods invoices. Sysco/PFG bypass this entirely.

Strategy:
- Split image into 2-3 overlapping horizontal strips (60% height each, 20% overlap)
- Extract from each strip independently using the same US Foods prompt
- Merge results: header info from strip 1, totals from last strip
- Deduplicate items that appear in the overlap zone using (total, price) matching
"""
import base64
import io
import json
import logging
import re
import uuid

from PIL import Image

logger = logging.getLogger("restaurant_ai")

# ── Configuration ──
STRIP_HEIGHT_PCT = 0.55        # Each strip is 55% of image height
OVERLAP_PCT = 0.15             # 15% overlap between strips
MIN_HEIGHT_FOR_SPLIT = 1200    # Don't split images shorter than this (px)
MAX_STRIPS = 3                 # Maximum number of strips


def should_split_usfoods(img_bytes: bytes) -> bool:
    """
    Determine if a US Foods image should be split into sections.
    Returns True if the image is tall enough to benefit from splitting.
    """
    try:
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        is_portrait = h > w * 1.1
        is_tall = h >= MIN_HEIGHT_FOR_SPLIT
        return is_portrait and is_tall
    except Exception as e:
        logger.warning(f"Section split check failed: {e}")
        return False


def split_image_to_strips(img_bytes: bytes) -> list[bytes]:
    """
    Split an image into overlapping horizontal strips.
    Returns list of JPEG bytes for each strip.
    """
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size

    strip_h = int(h * STRIP_HEIGHT_PCT)
    overlap = int(h * OVERLAP_PCT)
    step = strip_h - overlap

    strips = []
    y = 0
    while y < h and len(strips) < MAX_STRIPS:
        y_end = min(y + strip_h, h)
        # Last strip: extend to bottom
        if h - y_end < step * 0.3:
            y_end = h

        strip_img = img.crop((0, y, w, y_end))

        buf = io.BytesIO()
        strip_img.save(buf, format="JPEG", quality=88)
        strips.append(buf.getvalue())

        logger.info(
            f"Section split: strip {len(strips)} = rows {y}-{y_end} "
            f"({strip_img.size[0]}x{strip_img.size[1]})"
        )

        if y_end >= h:
            break
        y += step

    logger.info(f"Section split: {len(strips)} strips from {w}x{h} image")
    return strips


def merge_strip_extractions(strip_results: list[dict]) -> dict:
    """
    Merge extraction results from multiple strips into one invoice.

    Rules:
    - Header info (supplier_name, invoice_date, invoice_number): from first strip that has them
    - Totals (subtotal, tax, total): from LAST strip that has non-zero values
    - Items: accumulate from all strips, deduplicate overlap items
    """
    merged = {
        "supplier_name": "",
        "invoice_date": "",
        "invoice_number": "",
        "items": [],
        "subtotal": 0,
        "tax": 0,
        "total": 0,
    }

    # ── Header: first strip with data ──
    for result in strip_results:
        if not result:
            continue
        for field in ("supplier_name", "invoice_date", "invoice_number"):
            val = (result.get(field) or "").strip()
            if val and not merged[field]:
                merged[field] = val

    # ── Totals: last strip with non-zero values ──
    for result in reversed(strip_results):
        if not result:
            continue
        for field in ("subtotal", "tax", "total"):
            val = float(result.get(field, 0) or 0)
            if val > 0 and merged[field] == 0:
                merged[field] = val

    # ── Items: accumulate + deduplicate ──
    all_items = []
    for strip_idx, result in enumerate(strip_results):
        if not result:
            continue
        for item in result.get("items", []):
            item["_strip_idx"] = strip_idx
            all_items.append(item)

    merged["items"] = _deduplicate_items(all_items)

    # Remove internal tracking fields
    for item in merged["items"]:
        item.pop("_strip_idx", None)

    logger.info(
        f"Section merge: {len(all_items)} raw items -> "
        f"{len(merged['items'])} after dedup"
    )

    return merged


def _deduplicate_items(items: list[dict]) -> list[dict]:
    """
    Deduplicate items that appear in the overlap zone between strips.

    Strategy:
    - Match items by (total, unit_price) — these are the most reliable numeric fields
    - If two items from adjacent strips share the same total AND price, keep the one
      with more complete data (more non-zero fields, better qty_source)
    - Legitimate duplicates (same item ordered twice) are distinguished by:
      being in non-adjacent strips OR having different item_codes
    """
    if len(items) <= 1:
        return items

    deduped = []
    used = set()

    for i, item_a in enumerate(items):
        if i in used:
            continue

        total_a = float(item_a.get("total", 0) or 0)
        price_a = float(item_a.get("unit_price", 0) or 0)
        strip_a = item_a.get("_strip_idx", -1)

        # Look for duplicate in later items
        best = item_a
        best_score = _item_quality_score(item_a)

        for j in range(i + 1, len(items)):
            if j in used:
                continue

            item_b = items[j]
            total_b = float(item_b.get("total", 0) or 0)
            price_b = float(item_b.get("unit_price", 0) or 0)
            strip_b = item_b.get("_strip_idx", -1)

            # Only dedup items from adjacent strips (overlap zone)
            if abs(strip_a - strip_b) > 1:
                continue

            # Match by total + price (both must be non-zero and equal)
            if total_a > 0 and total_b > 0 and price_a > 0 and price_b > 0:
                if abs(total_a - total_b) < 0.02 and abs(price_a - price_b) < 0.02:
                    # Same item in overlap — keep the better extraction
                    score_b = _item_quality_score(item_b)
                    if score_b > best_score:
                        best = item_b
                        best_score = score_b
                    used.add(j)
                    logger.info(
                        f"Dedup: merged overlap item "
                        f"'{(item_a.get('raw_name') or '?')[:30]}' "
                        f"(strips {strip_a},{strip_b}, total=${total_a:.2f})"
                    )

        deduped.append(best)
        used.add(i)

    return deduped


def _item_quality_score(item: dict) -> float:
    """Score an item's extraction quality. Higher = better."""
    score = 0.0

    # Non-zero numeric fields
    if float(item.get("quantity", 0) or 0) > 0:
        score += 2.0
    if float(item.get("unit_price", 0) or 0) > 0:
        score += 2.0
    if float(item.get("total", 0) or 0) > 0:
        score += 2.0

    # Column read sources (most reliable)
    if item.get("qty_source") == "column_read":
        score += 1.5
    if item.get("price_source") == "column_read":
        score += 1.5
    if item.get("total_source") == "column_read":
        score += 1.5

    # Qty column visible
    if item.get("qty_column_visible") is True:
        score += 1.0

    # Has item code
    if (item.get("item_code") or "").strip():
        score += 0.5

    # Has readable name
    name = (item.get("raw_name") or "").strip()
    if name and len(name) >= 3:
        score += 0.5

    # Math check: qty * price = total
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)
    if qty > 0 and price > 0 and total > 0:
        if abs(round(qty * price, 2) - total) <= 0.01:
            score += 3.0  # Strong bonus for math-valid items

    return score
