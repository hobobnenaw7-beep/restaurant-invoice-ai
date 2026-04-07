"""
Sysco-specific extraction pipeline.

Architecture: table reconstruction → row segmentation → column mapping →
              row classification → numeric extraction → validation → trust gate

Uses Tesseract OCR for word-level bounding boxes to build structural table,
then extracts numbers from known column positions.

GPT Vision is NOT used in this pipeline. All extraction is deterministic.
"""
import base64
import io
import logging
import re
from collections import defaultdict

import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. OCR: Extract words with positions
# ---------------------------------------------------------------------------

def _extract_words(img: Image.Image) -> list[dict]:
    """
    Run Tesseract OCR and return word-level data with bounding boxes.
    Each word: {text, x, y, w, h, x_center, y_center, conf}
    Filters out empty text and very low confidence (<15).
    """
    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config="--psm 6 --dpi 300",
    )

    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not text or conf < 15:
            continue

        x = data["left"][i]
        y = data["top"][i]
        w = data["width"][i]
        h = data["height"][i]

        words.append({
            "text": text,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "x_center": x + w // 2,
            "y_center": y + h // 2,
            "x_right": x + w,
            "conf": conf,
        })

    logger.info(f"Sysco OCR: {len(words)} words extracted from {img.size[0]}x{img.size[1]}")
    return words


# ---------------------------------------------------------------------------
# 2. Row Segmentation: Group words into rows by y-position
# ---------------------------------------------------------------------------

def _segment_rows(words: list[dict], row_gap_threshold: int = 20) -> list[list[dict]]:
    """
    Group words into rows using y-position clustering.

    Words with y_center within `row_gap_threshold` pixels of each other
    belong to the same row. Rows are sorted top-to-bottom,
    words within each row sorted left-to-right.
    """
    if not words:
        return []

    # Sort words by y_center
    sorted_words = sorted(words, key=lambda w: w["y_center"])

    rows = []
    current_row = [sorted_words[0]]
    current_y = sorted_words[0]["y_center"]

    for word in sorted_words[1:]:
        if abs(word["y_center"] - current_y) <= row_gap_threshold:
            current_row.append(word)
            # Update running average y for the row
            current_y = sum(w["y_center"] for w in current_row) / len(current_row)
        else:
            rows.append(sorted(current_row, key=lambda w: w["x"]))
            current_row = [word]
            current_y = word["y_center"]

    if current_row:
        rows.append(sorted(current_row, key=lambda w: w["x"]))

    logger.info(f"Sysco rows: {len(rows)} rows segmented")
    return rows


# ---------------------------------------------------------------------------
# 3. Column Detection: Find vertical column boundaries
# ---------------------------------------------------------------------------

# Sysco invoices have a standard column layout.
# We detect columns by finding the header row and mapping known header words.

_SYSCO_HEADER_WORDS = {
    "qty": "qty",
    "quantity": "qty",
    "ordered": "qty",
    "ship": "qty",
    "qtyord": "qty",
    "pack": "pack",
    "size": "pack",
    "description": "description",
    "item": "description",
    "code": "item_code",
    "price": "unit_price",
    "unit": "unit_price",
    "amount": "total",
    "total": "total",
    "extended": "total",
    "ext": "total",
}


def _detect_columns(rows: list[list[dict]], img_width: int) -> dict:
    """
    Detect column boundaries using a hybrid approach:
    1. Try header-based detection first
    2. If header is unreliable, use data-driven column detection
       (cluster x-positions of numeric values in data region)

    Returns:
    {
        "header_row_idx": int,
        "columns": {
            "qty": {"x_left": int, "x_right": int, "x_center": int, ...},
            ...
        }
    }
    """
    # Strategy: use DATA-DRIVEN approach as primary (more reliable on Sysco)
    # Headers on Sysco invoices are often noisy, multi-line, or garbled.
    col_result = _data_driven_column_detection(rows, img_width)
    if col_result and len(col_result.get("columns", {})) >= 3:
        return col_result

    # Fallback to position-based proportional detection
    logger.warning("Sysco columns: data-driven detection failed, using proportional fallback")
    return _fallback_column_detection(img_width)


def _data_driven_column_detection(rows: list[list[dict]], img_width: int) -> dict | None:
    """
    Detect columns by analyzing where numbers appear in the data region.

    Strategy:
    1. Find the data region (skip first ~5 rows = headers)
    2. Collect x-positions of all numeric words
    3. Cluster them into column groups
    4. Assign column types based on x-position order:
       leftmost numeric cluster → qty
       second-to-rightmost → unit_price
       rightmost → total
    5. Text between qty and unit_price → description
    """
    # Skip header rows (first 5-8 rows typically)
    # Find the first row with numeric values as a heuristic for data start
    data_start = 0
    for idx, row in enumerate(rows):
        nums_in_row = sum(1 for w in row if _is_numeric_word(w["text"]))
        if nums_in_row >= 2 and idx >= 3:  # At least 2 numbers, past headers
            data_start = idx
            break

    if data_start == 0:
        data_start = min(5, len(rows) // 3)

    # Collect x_center positions of all numeric words in data region
    numeric_positions = []
    for row in rows[data_start:]:
        for word in row:
            if _is_numeric_word(word["text"]) and word["conf"] > 25:
                numeric_positions.append(word["x_center"])

    if len(numeric_positions) < 5:
        return None

    # Cluster x-positions using simple gap-based clustering
    clusters = _cluster_x_positions(sorted(numeric_positions), min_gap=80)

    if len(clusters) < 2:
        return None

    # Sort clusters by x position
    clusters.sort(key=lambda c: c["center"])

    # Assign column types based on analysis of clusters
    # Strategy:
    #   - Total column: the cluster with the MOST numeric values in the right half of the image
    #   - Unit price: the next cluster to the LEFT of total
    #   - QTY: the leftmost cluster (small numbers, far from price/total)
    columns = {}

    # Find total: rightmost cluster with the most numeric values (>= 5 values)
    right_half_clusters = [c for c in clusters if c["center"] > img_width * 0.4]
    if right_half_clusters:
        # Pick the cluster with the most values in the right portion
        total_cluster = max(right_half_clusters, key=lambda c: c["count"])
        columns["total"] = {
            "x_left": total_cluster["x_min"] - 30,
            "x_right": total_cluster["x_max"] + 30,
            "x_center": total_cluster["center"],
            "zone_left": 0,
            "zone_right": img_width,
            "header_text": "TOTAL",
        }

        # Unit price: the cluster immediately LEFT of total (in right half)
        price_candidates = [c for c in right_half_clusters
                            if c["center"] < total_cluster["center"] - 100
                            and c["count"] >= 3]
        if price_candidates:
            price_cluster = max(price_candidates, key=lambda c: c["center"])  # closest to total
            columns["unit_price"] = {
                "x_left": price_cluster["x_min"] - 20,
                "x_right": price_cluster["x_max"] + 20,
                "x_center": price_cluster["center"],
                "zone_left": 0,
                "zone_right": 0,
                "header_text": "PRICE",
            }

    # QTY: leftmost cluster (must be in left 20% of image, small numbers)
    left_clusters = [c for c in clusters if c["center"] < img_width * 0.15 and c["count"] >= 3]
    if left_clusters:
        qty_cluster = left_clusters[0]  # leftmost
        # Verify it's far from price/total
        if "unit_price" in columns:
            gap = columns["unit_price"]["x_center"] - qty_cluster["center"]
            if gap > img_width * 0.2:
                columns["qty"] = {
                    "x_left": max(0, qty_cluster["x_min"] - 30),
                    "x_right": qty_cluster["x_max"] + 30,
                    "x_center": qty_cluster["center"],
                    "zone_left": 0,
                    "zone_right": 0,
                    "header_text": "QTY",
                }

    # Description zone: between qty (or left edge) and unit_price
    qty_right = columns.get("qty", {}).get("x_right", 0)
    price_left = columns.get("unit_price", {}).get("x_left", img_width)
    desc_zone_left = qty_right + 20 if "qty" in columns else 0
    desc_zone_right = price_left - 20

    if desc_zone_right - desc_zone_left > img_width * 0.1:
        columns["description"] = {
            "x_left": desc_zone_left,
            "x_right": desc_zone_right,
            "x_center": (desc_zone_left + desc_zone_right) // 2,
            "zone_left": desc_zone_left,
            "zone_right": desc_zone_right,
            "header_text": "DESCRIPTION",
        }

    # Set zones properly
    _expand_column_boundaries(columns, img_width)

    # Find approximate header row
    header_idx = max(0, data_start - 1)

    logger.info(
        f"Sysco data-driven columns: data starts at row {data_start}, "
        f"detected: {list(columns.keys())}, "
        f"{len(numeric_positions)} numeric words analyzed, "
        f"{len(clusters)} clusters found"
    )

    return {"header_row_idx": header_idx, "columns": columns}


def _is_numeric_word(text: str) -> bool:
    """Check if a word looks like a number (price, qty, total)."""
    s = text.strip().strip("|[]{}();:")
    s = s.replace("$", "").replace(",", "").replace(")", "").replace("(", "")
    # Must have at least one digit
    if not any(c.isdigit() for c in s):
        return False
    # Remove all digits, dots, minus — remaining should be minimal
    non_numeric = re.sub(r"[0-9.\-]", "", s)
    return len(non_numeric) <= 1  # Allow 1 stray character (OCR artifact)


def _cluster_x_positions(positions: list[int], min_gap: int = 80) -> list[dict]:
    """
    Cluster sorted x-positions into groups using gap-based splitting.
    Adjacent positions within `min_gap` pixels belong to the same cluster.
    """
    if not positions:
        return []

    clusters = []
    current = [positions[0]]

    for pos in positions[1:]:
        if pos - current[-1] <= min_gap:
            current.append(pos)
        else:
            clusters.append({
                "center": sum(current) // len(current),
                "x_min": min(current),
                "x_max": max(current),
                "count": len(current),
            })
            current = [pos]

    if current:
        clusters.append({
            "center": sum(current) // len(current),
            "x_min": min(current),
            "x_max": max(current),
            "count": len(current),
        })

    # Filter out clusters with very few hits (likely noise)
    return [c for c in clusters if c["count"] >= 2]


def _trim_footer_rows(structured: list[dict]) -> None:
    """
    Mark rows after the last group_total/subtotal as footer (unknown).
    Sysco invoices: all line items come BEFORE the ORDER SUMMARY.
    Everything after is footer text (signatures, legal disclaimers, remit info).
    """
    last_group_total_idx = -1
    last_subtotal_idx = -1

    for i, row in enumerate(structured):
        if row["row_type"] == "group_total":
            last_group_total_idx = i
        elif row["row_type"] == "subtotal":
            last_subtotal_idx = i

    # Use the later of group_total or subtotal as the cutoff
    cutoff = max(last_group_total_idx, last_subtotal_idx)

    if cutoff > 0:
        for row in structured[cutoff + 1:]:
            if row["row_type"] in ("line_item", "fee"):
                row["row_type"] = "unknown"
                row["_trimmed"] = "footer_after_summary"


def _expand_column_boundaries(columns: dict, img_width: int) -> None:
    """
    Expand column boundaries to create non-overlapping zones.
    Each column zone extends from midpoint-to-previous to midpoint-to-next.
    """
    if not columns:
        return

    # Sort columns by x_center
    sorted_cols = sorted(columns.items(), key=lambda kv: kv[1]["x_center"])

    for i, (col_type, col) in enumerate(sorted_cols):
        # Left boundary: midpoint to previous column, or 0
        if i == 0:
            col["zone_left"] = 0
        else:
            prev_right = sorted_cols[i - 1][1]["x_right"]
            col["zone_left"] = (prev_right + col["x_left"]) // 2

        # Right boundary: midpoint to next column, or image width
        if i == len(sorted_cols) - 1:
            col["zone_right"] = img_width
        else:
            next_left = sorted_cols[i + 1][1]["x_left"]
            col["zone_right"] = (col["x_right"] + next_left) // 2


def _fallback_column_detection(img_width: int) -> dict:
    """
    Position-based fallback when no header row is found.
    Uses typical Sysco column proportions relative to image width.

    Typical layout (proportional):
    QTY: 0-5%  |  PACK: 5-15%  |  DESC: 15-50%  |  CODE: 50-60%  |  PRICE: 60-70%  |  TOTAL: 70-85%
    """
    def pct(p):
        return int(img_width * p / 100)

    columns = {
        "qty": {"x_left": 0, "x_right": pct(5), "x_center": pct(3),
                "zone_left": 0, "zone_right": pct(7), "header_text": "QTY"},
        "pack": {"x_left": pct(7), "x_right": pct(15), "x_center": pct(10),
                 "zone_left": pct(7), "zone_right": pct(15), "header_text": "PACK"},
        "description": {"x_left": pct(15), "x_right": pct(50), "x_center": pct(30),
                         "zone_left": pct(15), "zone_right": pct(50), "header_text": "DESCRIPTION"},
        "item_code": {"x_left": pct(50), "x_right": pct(60), "x_center": pct(55),
                       "zone_left": pct(50), "zone_right": pct(60), "header_text": "CODE"},
        "unit_price": {"x_left": pct(60), "x_right": pct(70), "x_center": pct(65),
                        "zone_left": pct(60), "zone_right": pct(73), "header_text": "PRICE"},
        "total": {"x_left": pct(73), "x_right": pct(85), "x_center": pct(78),
                   "zone_left": pct(73), "zone_right": pct(90), "header_text": "TOTAL"},
    }

    return {"header_row_idx": -1, "columns": columns}


# ---------------------------------------------------------------------------
# 4. Assign words to columns
# ---------------------------------------------------------------------------

def _assign_word_to_column(word: dict, columns: dict) -> str | None:
    """
    Assign a word to its column based on x_center position.
    Returns column name or None if outside all zones.
    """
    x = word["x_center"]
    for col_type, col in columns.items():
        if col.get("zone_left", col["x_left"]) <= x <= col.get("zone_right", col["x_right"]):
            return col_type
    return None


# ---------------------------------------------------------------------------
# 5. Build structured rows
# ---------------------------------------------------------------------------

def _build_structured_rows(
    rows: list[list[dict]],
    columns: dict,
    header_row_idx: int,
) -> list[dict]:
    """
    Build structured row dicts from OCR word rows + column mapping.

    For each data row (after header), assign words to columns
    and extract text/numeric values.

    Returns list of:
    {
        "row_idx": int,
        "y_avg": float,
        "cells": {col_type: [words]},
        "raw_text": str,          # all words concatenated
        "description_text": str,   # just description column
        "qty_text": str,
        "price_text": str,
        "total_text": str,
    }
    """
    data_start = header_row_idx + 1 if header_row_idx >= 0 else 0
    structured = []

    for row_idx, row_words in enumerate(rows[data_start:], start=data_start):
        cells = defaultdict(list)
        for word in row_words:
            col = _assign_word_to_column(word, columns)
            if col:
                cells[col].append(word)

        # Build text for each cell
        def cell_text(col_type):
            words_in_cell = cells.get(col_type, [])
            return " ".join(w["text"] for w in sorted(words_in_cell, key=lambda w: w["x"]))

        structured.append({
            "row_idx": row_idx,
            "y_avg": sum(w["y_center"] for w in row_words) / len(row_words) if row_words else 0,
            "cells": dict(cells),
            "raw_text": " ".join(w["text"] for w in row_words),
            "description_text": cell_text("description"),
            "qty_text": cell_text("qty"),
            "pack_text": cell_text("pack"),
            "price_text": cell_text("unit_price"),
            "total_text": cell_text("total"),
            "code_text": cell_text("item_code"),
            "word_count": len(row_words),
        })

    return structured


# ---------------------------------------------------------------------------
# 6. Row Classification
# ---------------------------------------------------------------------------

_GROUP_TOTAL_RE = re.compile(r"group\s*total|subtotal|sub\s*total", re.IGNORECASE)
_SECTION_HEADER_RE = re.compile(r"^\*{2,}.*\*{2,}$")
_ORDER_SUMMARY_RE = re.compile(r"order\s*summary|invoice\s*summary|payment\s*summary", re.IGNORECASE)
_TAX_RE = re.compile(r"\b(sales\s*tax|tax|hst|gst|vat)\b", re.IGNORECASE)
_FEE_KEYWORDS = {"delivery", "fuel", "surcharge", "credit", "discount", "freight",
                  "handling", "service", "charge", "fee", "adjustment"}
_TOTAL_LINE_RE = re.compile(r"^(total|grand\s*total|invoice\s*total|order\s*total)$", re.IGNORECASE)


def _classify_structured_row(row: dict) -> str:
    """
    Classify a structured row into one of:
      line_item, group_total, subtotal, tax, fee, header, unknown
    """
    raw = row["raw_text"]
    desc = row["description_text"]
    raw_lower = raw.lower()
    desc_lower = desc.lower()

    # Rule 1: GROUP TOTAL / SUBTOTAL
    if _GROUP_TOTAL_RE.search(raw_lower):
        return "group_total"

    # Rule 2: ORDER SUMMARY
    if _ORDER_SUMMARY_RE.search(raw_lower):
        return "subtotal"

    # Rule 3: Standalone TOTAL line
    cleaned = re.sub(r"[\*\s]+", " ", raw).strip()
    if _TOTAL_LINE_RE.match(cleaned):
        return "subtotal"

    # Rule 4: Section headers (***POULTRY***, etc.)
    if _SECTION_HEADER_RE.match(raw.replace(" ", "")):
        return "header"
    # Also catch "***word***" patterns even with spaces
    if raw.count("*") >= 4 and not any(c.isdigit() for c in raw):
        return "header"

    # Rule 5: Tax line
    if _TAX_RE.search(raw_lower) and row["word_count"] <= 6:
        return "tax"

    # Rule 6: Fee / service charge
    desc_words = set(desc_lower.split())
    raw_words = set(raw_lower.split())
    fee_matches = raw_words & _FEE_KEYWORDS
    if fee_matches and len(raw_words) <= 6:
        return "fee"
    if len(fee_matches) >= 2:
        return "fee"

    # Rule 7: Empty or header-like rows (very few words, no numbers)
    if row["word_count"] <= 2 and not any(c.isdigit() for c in raw):
        return "header"

    # Rule 8: Rows with no description content — likely separators or blank rows
    if not desc.strip() and not row["qty_text"].strip() and not row["total_text"].strip():
        return "unknown"

    # Rule 9: Very short or garbled description (< 3 alpha chars) with no numbers
    alpha_count = sum(1 for c in desc if c.isalpha())
    if alpha_count < 3 and not row["total_text"].strip():
        return "unknown"

    # Default: line_item
    return "line_item"


# ---------------------------------------------------------------------------
# 7. Numeric Extraction
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> float | None:
    """
    Parse a numeric string from OCR output.
    Handles: $, commas, parentheses (negative), trailing garbage.
    Returns float or None if not parseable.
    """
    if not text or not text.strip():
        return None

    s = text.strip()

    # Remove common OCR artifacts around numbers
    s = s.strip("|[]{}") 
    s = s.rstrip(";:)")
    s = s.lstrip("$")

    # Handle negative in parens: (123.45) → -123.45
    neg = False
    if "(" in text and ")" in text:
        # Extract just the number between parens
        m = re.search(r"\(([0-9.,]+)\)", text)
        if m:
            neg = True
            s = m.group(1)

    # Remove $ and commas
    s = s.replace("$", "").replace(",", "")

    # Remove trailing non-numeric chars (OCR artifacts)
    s = re.sub(r"[^0-9.\-]+$", "", s)
    s = re.sub(r"^[^0-9.\-]+", "", s)

    if not s:
        return None

    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def _extract_numerics(items: list[dict]) -> None:
    """
    Extract numeric values from text cells for each line_item row.
    Sets: quantity, unit_price, total, qty_source, price_source, total_source.
    """
    for item in items:
        if item.get("row_type") not in ("line_item", "fee"):
            continue

        # Quantity
        qty_val = _parse_number(item.get("qty_text", ""))
        if qty_val is not None and qty_val > 0:
            item["quantity"] = qty_val
            item["qty_source"] = "column_read"
        else:
            item["quantity"] = 0
            item["qty_source"] = "ambiguous"

        # Unit price
        price_val = _parse_number(item.get("price_text", ""))
        if price_val is not None and price_val > 0:
            item["unit_price"] = round(price_val, 2)
            item["price_source"] = "column_read"
        else:
            item["unit_price"] = 0
            item["price_source"] = "ambiguous"

        # Total / extended price
        total_val = _parse_number(item.get("total_text", ""))
        if total_val is not None:
            item["total"] = round(total_val, 2)
            item["total_source"] = "column_read"
        else:
            item["total"] = 0
            item["total_source"] = "ambiguous"

        # Name
        item["raw_name"] = item.get("description_text", "").strip()

        # Pack
        item["pack_size"] = item.get("pack_text", "").strip()


# ---------------------------------------------------------------------------
# 8. Numeric Validation
# ---------------------------------------------------------------------------

def _validate_item_math(item: dict) -> None:
    """
    Validate qty × unit_price ≈ total for a single item.
    Sets: valid_calc, math_error, validation_errors.
    """
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)

    item["valid_calc"] = False
    item["validation_errors"] = item.get("validation_errors", [])

    if qty > 0 and price > 0 and total > 0:
        expected = round(qty * price, 2)
        tolerance = max(0.50, 0.02 * total)  # 2% or $0.50
        diff = abs(expected - total)

        if diff <= tolerance:
            item["valid_calc"] = True
        else:
            item["validation_errors"].append(
                f"math_mismatch: {qty}×${price:.2f}=${expected:.2f} ≠ total ${total:.2f} (diff=${diff:.2f})"
            )
    elif total > 0:
        if qty == 0:
            item["validation_errors"].append("missing_qty: total exists but qty=0")
        if price == 0:
            item["validation_errors"].append("missing_price: total exists but price=0")
    else:
        item["validation_errors"].append("missing_total: no total extracted")


def _validate_subtotal(line_items: list[dict], group_totals: list[dict]) -> dict:
    """
    Validate sum of line_item totals against detected group totals / subtotal.
    Returns validation summary.
    """
    items_sum = round(sum(float(it.get("total", 0) or 0) for it in line_items), 2)

    # Find the largest group total as the likely invoice subtotal
    gt_values = []
    for gt in group_totals:
        val = _parse_number(gt.get("total_text", ""))
        if val is not None and val > 0:
            gt_values.append(val)

    declared_subtotal = max(gt_values) if gt_values else 0

    result = {
        "items_sum": items_sum,
        "declared_subtotal": declared_subtotal,
        "subtotal_match": False,
        "subtotal_diff_pct": 0,
    }

    if items_sum > 0 and declared_subtotal > 0:
        diff_pct = abs(items_sum - declared_subtotal) / declared_subtotal
        result["subtotal_diff_pct"] = round(diff_pct * 100, 1)
        result["subtotal_match"] = diff_pct <= 0.05  # 5% tolerance

    return result


# ---------------------------------------------------------------------------
# 9. Trust Gate
# ---------------------------------------------------------------------------

def _apply_trust_gate(item: dict) -> None:
    """
    Strict trust gate: a row is trusted ONLY if:
    1. qty_source == column_read
    2. price_source == column_read
    3. total_source == column_read
    4. valid_calc == True
    5. raw_name is present

    Otherwise → needs_review_numeric with specific category.
    """
    qty_src = item.get("qty_source", "ambiguous")
    price_src = item.get("price_source", "ambiguous")
    total_src = item.get("total_source", "ambiguous")
    math_ok = item.get("valid_calc", False)
    has_name = bool((item.get("raw_name") or "").strip())

    all_sourced = (qty_src == "column_read" and
                   price_src == "column_read" and
                   total_src == "column_read")

    # Determine failure category
    if all_sourced and math_ok and has_name:
        item["confidence_level"] = "trusted"
        item["needs_review"] = False
        item["review_reason"] = None
        item["numeric_failure_category"] = "none"
        item["confidence_reason"] = "All fields column_read + math validated"
        return

    # Not trusted — determine why
    reasons = []
    if qty_src != "column_read":
        reasons.append(f"qty_source={qty_src}")
    if price_src != "column_read":
        reasons.append(f"price_source={price_src}")
    if total_src != "column_read":
        reasons.append(f"total_source={total_src}")
    if not math_ok:
        reasons.append("math_not_validated")
    if not has_name:
        reasons.append("missing_name")

    # Failure category
    qty_ok = qty_src == "column_read"
    price_ok = price_src == "column_read"
    total_ok = total_src == "column_read"

    if not qty_ok and not price_ok:
        category = "both_wrong"
    elif not qty_ok:
        category = "qty_wrong"
    elif not price_ok:
        category = "price_wrong"
    elif not total_ok:
        category = "total_wrong_due_to_upstream"
    elif not math_ok:
        category = "qty_wrong"  # conservative — math mismatch
    else:
        category = "qty_wrong"

    item["confidence_level"] = "needs_review_numeric"
    item["needs_review"] = True
    item["review_reason"] = f"Numeric field trust: {'; '.join(reasons)}"
    item["numeric_failure_category"] = category
    item["confidence_reason"] = f"Numeric field trust: {'; '.join(reasons)}"


# ---------------------------------------------------------------------------
# 10. Main Pipeline Entry Point
# ---------------------------------------------------------------------------

def run_sysco_pipeline(image_b64: str) -> dict:
    """
    Run the full Sysco extraction pipeline.

    Input: base64-encoded preprocessed image.
    Output: {
        "items": [...],           # Extracted line items
        "excluded_rows": [...],   # Non-line-item rows (group totals, headers, etc.)
        "subtotal_validation": {...},
        "pipeline_meta": {...},
    }
    """
    # Decode image
    img_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    img_width, img_height = img.size

    # Step 1: OCR — extract words with positions
    words = _extract_words(img)
    if not words:
        logger.warning("Sysco pipeline: no words extracted from OCR")
        return _empty_result("No words extracted from OCR")

    # Step 2: Row segmentation
    # Dynamic threshold based on image height
    row_gap = max(12, min(30, img_height // 120))
    rows = _segment_rows(words, row_gap_threshold=row_gap)
    if not rows:
        return _empty_result("No rows segmented")

    # Step 3: Column detection from header
    col_result = _detect_columns(rows, img_width)
    columns = col_result["columns"]
    header_idx = col_result["header_row_idx"]

    # Step 4: Build structured rows
    structured = _build_structured_rows(rows, columns, header_idx)

    # Step 5: Row classification
    for row in structured:
        row["row_type"] = _classify_structured_row(row)

    # Step 5b: Detect data region boundaries
    # After the last group_total, the remaining rows are footer/legal text.
    # Mark them as 'unknown' to exclude from extraction.
    _trim_footer_rows(structured)

    # Step 6: Extract numerics for line_item/fee rows
    _extract_numerics(structured)

    # Step 7: Validate math per item
    line_items = [r for r in structured if r["row_type"] in ("line_item", "fee")]
    for item in line_items:
        _validate_item_math(item)

    # Step 8: Trust gate
    for item in line_items:
        _apply_trust_gate(item)

    # Step 9: Subtotal validation
    group_totals = [r for r in structured if r["row_type"] == "group_total"]
    subtotal_result = _validate_subtotal(line_items, group_totals)

    # Only downgrade if the subtotal is a reasonable comparison
    # (within 50% — major discrepancies mean we're comparing wrong numbers)
    if (not subtotal_result["subtotal_match"]
            and subtotal_result["declared_subtotal"] > 0
            and 5 < subtotal_result["subtotal_diff_pct"] <= 50):
        for item in line_items:
            if item.get("confidence_level") == "trusted":
                item["confidence_level"] = "needs_review_numeric"
                item["needs_review"] = True
                item["review_reason"] = (
                    f"Subtotal mismatch: items sum ${subtotal_result['items_sum']:.2f} "
                    f"vs declared ${subtotal_result['declared_subtotal']:.2f} "
                    f"({subtotal_result['subtotal_diff_pct']:.0f}% off)"
                )

    # Build clean output items (strip internal fields)
    output_items = []
    for item in line_items:
        output_items.append({
            "raw_name": item.get("raw_name", ""),
            "quantity": float(item.get("quantity", 0) or 0),
            "pack_size": item.get("pack_size", ""),
            "unit_price": float(item.get("unit_price", 0) or 0),
            "total": float(item.get("total", 0) or 0),
            "qty_source": item.get("qty_source", "ambiguous"),
            "price_source": item.get("price_source", "ambiguous"),
            "total_source": item.get("total_source", "ambiguous"),
            "valid_calc": item.get("valid_calc", False),
            "validation_errors": item.get("validation_errors", []),
            "confidence_level": item.get("confidence_level", "needs_review_numeric"),
            "needs_review": item.get("needs_review", True),
            "review_reason": item.get("review_reason"),
            "confidence_reason": item.get("confidence_reason", ""),
            "numeric_failure_category": item.get("numeric_failure_category", "none"),
            "row_type": item.get("row_type", "line_item"),
            "vendor_status": "controlled_operational",
            "extraction_source": "ocr_table_reconstruction",
        })

    excluded = []
    for row in structured:
        if row["row_type"] not in ("line_item", "fee"):
            excluded.append({
                "row_type": row["row_type"],
                "raw_text": row["raw_text"][:80],
                "total_text": row.get("total_text", ""),
            })

    # Stats
    trusted_count = sum(1 for it in output_items if it["confidence_level"] == "trusted")
    review_count = sum(1 for it in output_items if "review" in it.get("confidence_level", ""))

    meta = {
        "pipeline": "sysco_table_reconstruction",
        "ocr_words": len(words),
        "rows_segmented": len(rows),
        "header_row_idx": header_idx,
        "columns_detected": list(columns.keys()),
        "line_items": len(output_items),
        "excluded_rows": len(excluded),
        "trusted": trusted_count,
        "needs_review": review_count,
        "subtotal_match": subtotal_result["subtotal_match"],
    }

    logger.info(
        f"Sysco pipeline complete: {len(output_items)} items "
        f"({trusted_count} trusted, {review_count} review), "
        f"{len(excluded)} excluded"
    )

    return {
        "items": output_items,
        "excluded_rows": excluded,
        "subtotal_validation": subtotal_result,
        "pipeline_meta": meta,
    }


def _empty_result(reason: str) -> dict:
    return {
        "items": [],
        "excluded_rows": [],
        "subtotal_validation": {"items_sum": 0, "declared_subtotal": 0, "subtotal_match": False},
        "pipeline_meta": {"pipeline": "sysco_table_reconstruction", "error": reason},
    }
