"""
Layout Parser — Phase 3
Extracts structured line items from invoice images using Tesseract OCR
with spatial analysis (row/column detection).

Pipeline:
  1. Run Tesseract → get word-level bounding boxes
  2. Group words into rows by y-coordinate clustering
  3. Detect column boundaries from header alignment
  4. Map cells into structured line items
  5. Route to vendor-specific or generic parser

NO AI/LLM calls — pure rule-based spatial analysis.
"""
import io
import re
import base64
import logging
from collections import defaultdict

import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


# ── 1. Tesseract OCR with position data ──

def run_ocr(image_bytes: bytes) -> list[dict]:
    """
    Run Tesseract on image bytes, return word-level data with bounding boxes.
    Each word: {text, left, top, width, height, conf, line_num, block_num}
    """
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 6 --dpi 300")

    words = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(data["conf"][i])
        if not text or conf < 10:
            continue
        words.append({
            "text": text,
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
            "right": int(data["left"][i]) + int(data["width"][i]),
            "bottom": int(data["top"][i]) + int(data["height"][i]),
            "conf": conf,
            "block": int(data["block_num"][i]),
            "line": int(data["line_num"][i]),
        })

    logger.info(f"OCR extracted {len(words)} words from image")
    return words


def run_ocr_from_b64(b64_image: str) -> list[dict]:
    """Run OCR from a base64-encoded image."""
    return run_ocr(base64.b64decode(b64_image))


# ── 2. Row Detection ──

def detect_rows(words: list[dict], tolerance_ratio: float = 0.4) -> list[list[dict]]:
    """
    Group words into rows by clustering their vertical center positions.
    Words within `tolerance_ratio * median_height` of each other are same row.
    Returns rows sorted top-to-bottom, words within each row sorted left-to-right.
    """
    if not words:
        return []

    # Calculate vertical center for each word
    for w in words:
        w["cy"] = w["top"] + w["height"] // 2

    # Sort by vertical position
    sorted_words = sorted(words, key=lambda w: w["cy"])

    # Median word height for tolerance
    heights = [w["height"] for w in words if w["height"] > 0]
    median_h = float(np.median(heights)) if heights else 15
    tolerance = max(median_h * tolerance_ratio, 5)

    # Cluster into rows
    rows = []
    current_row = [sorted_words[0]]
    current_cy = sorted_words[0]["cy"]

    for w in sorted_words[1:]:
        if abs(w["cy"] - current_cy) <= tolerance:
            current_row.append(w)
        else:
            rows.append(sorted(current_row, key=lambda x: x["left"]))
            current_row = [w]
            current_cy = w["cy"]

    if current_row:
        rows.append(sorted(current_row, key=lambda x: x["left"]))

    return rows


def row_text(row: list[dict]) -> str:
    """Reconstruct text from a row of words, preserving spacing."""
    if not row:
        return ""
    parts = []
    prev_right = row[0]["left"]
    for w in row:
        gap = w["left"] - prev_right
        if gap > w["height"] * 0.8:
            parts.append("  ")  # Large gap = column separator
        elif gap > 2:
            parts.append(" ")
        parts.append(w["text"])
        prev_right = w["right"]
    return "".join(parts)


# ── 3. Column Detection ──

def detect_columns(rows: list[list[dict]], header_keywords: list[str] = None) -> dict:
    """
    Detect column boundaries from header row and data alignment.

    Returns: {
        'header_row_idx': int,
        'columns': [{'name': str, 'left': int, 'right': int, 'field': str}],
        'data_start_idx': int,
    }
    """
    if not rows:
        return {"header_row_idx": -1, "columns": [], "data_start_idx": 0}

    if header_keywords is None:
        header_keywords = [
            "item", "description", "product", "qty", "quantity",
            "price", "unit", "total", "ext", "amount", "pack", "case",
            "each", "cost", "net", "uom", "size",
            "ttem", "ltem", "aty", "qiy",  # OCR misreads
        ]

    # Find header row: the row that contains the most header keywords
    best_idx = -1
    best_score = 0

    for i, row in enumerate(rows):
        text = " ".join(w["text"].lower() for w in row)
        score = sum(1 for kw in header_keywords if kw in text)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score < 2:
        # No clear header found — try to infer columns from data
        return _infer_columns_from_data(rows)

    header_row = rows[best_idx]
    columns = _parse_header_columns(header_row)

    # Ensure item_name column exists — if missing, create one at the left
    has_item_name = any(c["field"] == "item_name" for c in columns)
    if not has_item_name and columns:
        first_col_left = min(c["left"] for c in columns)
        if first_col_left > 20:
            # There's space to the left of the first column → insert description
            columns.insert(0, {
                "name": "Description",
                "left": 0,
                "right": first_col_left - 10,
                "field": "item_name",
            })
        else:
            # The first "unknown" column is likely item_name
            for c in columns:
                if c["field"] == "unknown":
                    c["field"] = "item_name"
                    break

    return {
        "header_row_idx": best_idx,
        "columns": columns,
        "data_start_idx": best_idx + 1,
    }


def _parse_header_columns(header_words: list[dict]) -> list[dict]:
    """
    Parse header row words into column definitions.
    Groups adjacent header words into column names and detects field type.
    """
    # Field type mapping (includes common OCR misreads)
    field_map = {
        "item": "item_name", "description": "item_name", "product": "item_name",
        "name": "item_name", "desc": "item_name",
        "ttem": "item_name", "ltem": "item_name",  # OCR misreads of Item
        "qty": "quantity", "quantity": "quantity", "qnty": "quantity",
        "aty": "quantity", "qiy": "quantity", "oty": "quantity",  # OCR misreads of Qty
        "ordered": "quantity", "ship": "quantity", "shipped": "quantity",
        "pack": "pack_size", "size": "pack_size", "case": "pack_size",
        "uom": "pack_size", "um": "pack_size",
        "price": "unit_price", "unit": "unit_price", "each": "unit_price",
        "cost": "unit_price", "net": "unit_price",
        "total": "total", "ext": "total", "amount": "total",
        "extended": "total",
    }

    # Group adjacent words into column headers
    columns = []
    current_group = [header_words[0]]

    for w in header_words[1:]:
        gap = w["left"] - current_group[-1]["right"]
        if gap > current_group[-1]["height"] * 1.5:
            # New column
            columns.append(_finalize_column(current_group, field_map))
            current_group = [w]
        else:
            current_group.append(w)

    columns.append(_finalize_column(current_group, field_map))

    return columns


def _finalize_column(word_group: list[dict], field_map: dict) -> dict:
    """Create a column definition from a group of header words."""
    name = " ".join(w["text"] for w in word_group)
    left = word_group[0]["left"]
    right = word_group[-1]["right"]

    # Determine field type
    lower_words = [w["text"].lower() for w in word_group]
    field = "unknown"
    for lw in lower_words:
        for key, ftype in field_map.items():
            if key in lw:
                field = ftype
                break
        if field != "unknown":
            break

    return {"name": name, "left": left, "right": right, "field": field}


def _is_pack_size_word(text: str) -> bool:
    """Check if a word looks like a pack-size component (not qty/price/total)."""
    t = text.strip()
    # Pack patterns: "6/5", "4/10", "24/12OZ", "48/6"
    if re.match(r'^\d+/\d+', t):
        return True
    # Unit words that appear in pack columns
    if t.upper() in {"LB", "LBS", "OZ", "GAL", "CT", "EA", "DZ", "ML", "QT", "PT", "CS", "PK", "BX"}:
        return True
    return False


def _is_price_like(text: str) -> bool:
    """Check if a word looks like a price or quantity (pure number or $-prefixed)."""
    t = text.strip().strip("'`\"\u2018\u2019\u201C\u201D")
    return bool(re.match(r'^[\d$.,]+$', t)) and not _is_pack_size_word(text)


def _infer_columns_from_data(rows: list[list[dict]]) -> dict:
    """
    When no header is found, infer columns from data alignment.
    Uses right-edge alignment of numeric values (prices/totals are right-aligned)
    and filters out pack-size words to avoid false column detection.
    """
    # Find rows that look like data (contain numbers that aren't pack sizes)
    data_rows = []
    for i, row in enumerate(rows):
        price_nums = [w for w in row if _is_price_like(w["text"])]
        if len(price_nums) >= 2:
            data_rows.append((i, row))

    if not data_rows:
        return {"header_row_idx": -1, "columns": [], "data_start_idx": 0}

    first_data_idx = data_rows[0][0]

    # Collect right-edge positions of numeric words across data rows
    # (right-alignment is more stable than left-position for prices)
    num_right_positions = []
    for _, row in data_rows:
        for w in row:
            if _is_price_like(w["text"]):
                num_right_positions.append(w["right"])

    if not num_right_positions:
        return {"header_row_idx": -1, "columns": [], "data_start_idx": 0}

    num_right_positions.sort()

    # Cluster by right-edge position (prices in same column align right)
    col_rights = []
    current = [num_right_positions[0]]
    for p in num_right_positions[1:]:
        if p - current[-1] < 60:
            current.append(p)
        else:
            col_rights.append(int(np.mean(current)))
            current = [p]
    col_rights.append(int(np.mean(current)))

    # Now find left boundaries for each numeric column
    # by looking at the left-most numeric word that aligns to each right cluster
    col_bounds = []
    for cr in col_rights:
        lefts = []
        for _, row in data_rows:
            for w in row:
                if _is_price_like(w["text"]) and abs(w["right"] - cr) < 60:
                    lefts.append(w["left"])
        col_left = min(lefts) if lefts else cr - 80
        col_bounds.append({"left": col_left, "right": cr})

    # Determine column order by x-position and assign fields
    # Rightmost = total, then unit_price, then quantity
    col_bounds.sort(key=lambda c: c["right"])
    field_names_rtl = ["total", "unit_price", "quantity"]  # right-to-left assignment

    columns = []
    # Description column: everything left of the first numeric column
    first_num_left = col_bounds[0]["left"] if col_bounds else 9999
    columns.append({
        "name": "Description", "left": 0,
        "right": first_num_left - 15, "field": "item_name",
    })

    for j, cb in enumerate(reversed(col_bounds)):
        field_idx = j
        field = field_names_rtl[field_idx] if field_idx < len(field_names_rtl) else "unknown"
        columns.append({
            "name": f"Col{len(col_bounds) - j}",
            "left": cb["left"] - 15,
            "right": cb["right"] + 15,
            "field": field,
        })

    # Sort columns left to right for consistent processing
    columns.sort(key=lambda c: c["left"])

    return {
        "header_row_idx": -1,
        "columns": columns,
        "data_start_idx": max(0, first_data_idx),
    }


# ── 4. Line Item Extraction ──

def extract_line_items(
    rows: list[list[dict]],
    col_info: dict,
) -> list[dict]:
    """
    Extract structured line items by mapping row cells to columns.
    Returns list of {item_name, quantity, unit_price, total_price}.
    """
    columns = col_info.get("columns", [])
    start = col_info.get("data_start_idx", 0)

    if not columns:
        return _extract_items_simple(rows, start)

    items = []
    for row in rows[start:]:
        text_full = row_text(row)

        # Skip separator/summary rows
        if _is_separator_or_summary(text_full):
            continue

        item = _map_words_to_columns(row, columns)

        # Must have a name and at least one numeric value
        if item["item_name"] and (item["quantity"] or item["unit_price"] or item["total_price"]):
            items.append(item)

    return items


def _map_words_to_columns(row: list[dict], columns: list[dict]) -> dict:
    """
    Map words in a row to their respective columns.
    Uses strict boundary matching: a word is assigned to the column whose
    boundaries contain its center. Only falls back to nearest-center if
    no column boundary matches.
    """
    result = {"item_name": "", "quantity": 0, "unit_price": 0, "total_price": 0, "pack_size": ""}
    if not columns:
        return result

    # Build expanded column boundaries for matching
    # Expand each column boundary slightly, but don't overlap with neighbors
    expanded = []
    for i, col in enumerate(columns):
        pad_left = 40
        pad_right = 40
        # Don't overlap with neighboring columns
        if i > 0:
            gap = col["left"] - columns[i - 1]["right"]
            pad_left = min(pad_left, gap // 2)
        if i < len(columns) - 1:
            gap = columns[i + 1]["left"] - col["right"]
            pad_right = min(pad_right, gap // 2)
        expanded.append((col["left"] - pad_left, col["right"] + pad_right))

    col_assignments = defaultdict(list)
    for w in row:
        w_center = w["left"] + w["width"] // 2

        # Phase 1: Strict boundary match
        bounded_col = None
        bounded_dist = float("inf")
        for i, col in enumerate(columns):
            el, er = expanded[i]
            if el <= w_center <= er:
                col_center = (col["left"] + col["right"]) // 2
                dist = abs(w_center - col_center)
                if dist < bounded_dist:
                    bounded_dist = dist
                    bounded_col = col

        if bounded_col:
            col_assignments[bounded_col["field"]].append(w["text"])
            continue

        # Phase 2: Fallback — nearest column center (only if no boundary match)
        best_col = None
        best_dist = float("inf")
        for col in columns:
            col_center = (col["left"] + col["right"]) // 2
            dist = abs(w_center - col_center)
            if dist < best_dist:
                best_dist = dist
                best_col = col
        if best_col:
            col_assignments[best_col["field"]].append(w["text"])

    # Build result from assignments
    if "item_name" in col_assignments:
        result["item_name"] = " ".join(col_assignments["item_name"])
    if "quantity" in col_assignments:
        result["quantity"] = _parse_number(" ".join(col_assignments["quantity"]))
    if "unit_price" in col_assignments:
        result["unit_price"] = _parse_number(" ".join(col_assignments["unit_price"]))
    if "total" in col_assignments:
        result["total_price"] = _parse_number(" ".join(col_assignments["total"]))
    if "pack_size" in col_assignments:
        result["pack_size"] = " ".join(col_assignments["pack_size"])

    # Handle unknown columns — try to assign as numbers
    for field, words in col_assignments.items():
        if field == "unknown":
            val = _parse_number(" ".join(words))
            if val > 0:
                # Heuristic: small integers (1-999) with no decimal → likely quantity
                is_integer = val == int(val) and val < 1000
                if is_integer and result["quantity"] == 0:
                    result["quantity"] = val
                elif result["total_price"] == 0:
                    result["total_price"] = val
                elif result["unit_price"] == 0:
                    result["unit_price"] = val
                elif result["quantity"] == 0:
                    result["quantity"] = val

    return result


def _extract_items_simple(rows: list[list[dict]], start: int = 0) -> list[dict]:
    """
    Fallback: extract items without column info.
    Assumes format: description ... qty price total (numbers on the right).
    Filters pack-size patterns (e.g., "6/5", "LB") from numeric extraction.
    """
    items = []
    for row in rows[start:]:
        text = row_text(row)
        if _is_separator_or_summary(text):
            continue

        # Split into text words, pack words, and numeric words
        text_parts = []
        numbers = []
        for w in row:
            wt = w["text"].strip()
            if _is_pack_size_word(wt):
                text_parts.append(wt)  # Pack sizes go into description
            elif re.match(r'^[\d$.,]+$', wt.replace(",", "").strip("'`\"\u2018\u2019\u201C\u201D")):
                val = _parse_number(wt)
                if val > 0:
                    numbers.append(val)
            else:
                text_parts.append(wt)

        name = " ".join(text_parts).strip()
        if not name or len(numbers) < 2:
            continue

        # Assign numbers: usually qty, price, total (right to left: total, price, qty)
        item = {"item_name": name, "quantity": 0, "unit_price": 0, "total_price": 0, "pack_size": ""}

        if len(numbers) >= 3:
            item["quantity"] = numbers[-3]
            item["unit_price"] = numbers[-2]
            item["total_price"] = numbers[-1]
        elif len(numbers) == 2:
            # Could be qty+total or price+total
            if numbers[0] < 100 and numbers[1] > numbers[0]:
                item["quantity"] = numbers[0]
                item["total_price"] = numbers[1]
                if item["quantity"] > 0:
                    item["unit_price"] = round(item["total_price"] / item["quantity"], 2)
            else:
                item["unit_price"] = numbers[0]
                item["total_price"] = numbers[1]

        items.append(item)

    return items


# ── 5. Helper functions ──

def _parse_number(text: str) -> float:
    """Parse a numeric string, handling $, commas, and common OCR artifacts."""
    # Strip common OCR artifacts (ASCII and Unicode quotes, spaces)
    cleaned = text.replace("$", "").replace(",", "").strip()
    # Remove ASCII and Unicode quote chars
    cleaned = cleaned.strip("'`\"\u2018\u2019\u201C\u201D")
    # OCR substitutions for common digit confusions
    cleaned = _ocr_digit_fix(cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _ocr_digit_fix(text: str) -> str:
    """Fix common OCR digit misreads in text expected to be numeric.
    Applied after $ and , stripping, so the input should be mostly digits."""
    if not text:
        return text
    # Common OCR digit confusions
    mapping = {'l': '1', 'I': '1', 'O': '0', 'o': '0', 'S': '5', 'B': '8'}
    result = []
    has_digit = any(c.isdigit() or c == '.' for c in text)
    for ch in text:
        if ch in mapping and (has_digit or len(text) <= 3):
            result.append(mapping[ch])
        else:
            result.append(ch)
    return ''.join(result)


def _is_separator_or_summary(text: str) -> bool:
    """Check if a row is a separator line or summary (subtotal/tax/total)."""
    t = text.strip().lower()
    if not t:
        return True
    # Separator lines (----, ====, etc.)
    if re.match(r'^[-=_*]{3,}$', t.replace(" ", "")):
        return True
    # Don't filter header-like rows (contain multiple column keywords)
    header_words = ["item", "description", "product", "qty", "quantity", "price",
                    "pack", "size", "total", "amount", "ext", "unit", "each"]
    header_hits = sum(1 for hw in header_words if hw in t)
    if header_hits >= 2:
        return False
    # Summary lines — only if the row STARTS with a summary keyword
    # (data rows may contain words like "total" in product names)
    summary_start_patterns = [
        r'^\s*subtotal\b', r'^\s*sub\s*total\b', r'^\s*tax\b', r'^\s*balance\b',
        r'^\s*amount\s*due\b', r'^\s*thank\s*you\b', r'^\s*terms:',
        r'^\s*net\s*\d+\b', r'^\s*page\s+\d', r'^\s*invoice\s+total\b',
    ]
    for sp in summary_start_patterns:
        if re.search(sp, t):
            return True
    # A row that is ONLY "total: $X" (no item data) — short row
    if re.match(r'^total[:\s]+\$?[\d,.]+ *$', t):
        return True
    # Very short rows that are just a keyword + number
    words = t.split()
    if len(words) <= 3 and any(kw in t for kw in ["total", "subtotal", "tax", "balance"]):
        return True
    return False


# ── 6. Main parse function ──

def parse_invoice_layout(
    b64_image: str,
    document_type: str = "structured_invoice",
    vendor_name: str = None,
) -> dict:
    """
    Full layout parsing pipeline for a single invoice image.

    Returns: {
        'items': [{'item_name', 'quantity', 'unit_price', 'total_price', 'pack_size'}],
        'row_count': int,
        'column_count': int,
        'header_detected': bool,
        'parser_used': str,
        'raw_rows': [str],
    }
    """
    try:
        image_bytes = base64.b64decode(b64_image)
        words = run_ocr(image_bytes)

        if not words:
            logger.warning("No words extracted from OCR")
            return _empty_result("no_ocr_words")

        rows = detect_rows(words)
        if not rows:
            logger.warning("No rows detected")
            return _empty_result("no_rows")

        raw_rows = [row_text(r) for r in rows]

        # Route to appropriate parser
        if vendor_name:
            items, parser_used = _parse_vendor_specific(rows, vendor_name)
            if items:
                return _build_result(items, rows, raw_rows, parser_used)

        if document_type == "simple_receipt":
            items = _parse_receipt(rows)
            return _build_result(items, rows, raw_rows, "receipt_parser")

        # Default: structured invoice parser
        col_info = detect_columns(rows)
        items = extract_line_items(rows, col_info)
        if not items:
            # Column detection may have failed — fall back to simple extraction
            items = _extract_items_simple(rows)
            parser_used = "structured_fallback"
        else:
            header = col_info.get("header_row_idx", -1) >= 0
            parser_used = "structured_columnar" if header else "structured_inferred"
        return _build_result(items, rows, raw_rows, parser_used, col_info)

    except Exception as e:
        logger.error(f"Layout parsing failed: {e}")
        return _empty_result(f"error: {e}")


def _parse_receipt(rows: list[list[dict]]) -> list[dict]:
    """Parse simple receipt format — no formal columns. Use simple extraction."""
    return _extract_items_simple(rows)


def _parse_vendor_specific(rows: list[list[dict]], vendor_name: str) -> tuple:
    """
    Route to vendor-specific parser if available.
    Returns (items, parser_name) or (None, None) if no vendor parser matched.
    """
    vn = vendor_name.lower()

    if "sysco" in vn:
        return _parse_sysco(rows), "vendor_sysco"
    if "performance" in vn or "pfg" in vn:
        return _parse_pfg(rows), "vendor_pfg"
    if "us foods" in vn or "usfoods" in vn:
        return _parse_usfoods(rows), "vendor_usfoods"

    return None, None


# ── 7. Vendor-Specific Parsers ──

def _parse_sysco(rows: list[list[dict]]) -> list[dict]:
    """
    Sysco invoices: ITEM#, DESCRIPTION, PACK SIZE, QTY, PRICE, EXT PRICE
    Header may be white-on-dark (unreadable by OCR). Falls back to simple extraction.
    """
    header_kw = ["item", "description", "pack", "qty", "price", "total", "ext", "net"]
    col_info = detect_columns(rows, header_kw)
    items = extract_line_items(rows, col_info)
    if items:
        return items
    # Fallback: white-on-dark header may not be readable
    return _extract_items_simple(rows)


def _parse_pfg(rows: list[list[dict]]) -> list[dict]:
    """
    PFG invoices: DESCRIPTION, PACK, QTY, CASEWT, $/LB, TOTAL
    Weight-based pricing: total = qty × caseWT × $/LB
    """
    header_kw = ["description", "pack", "qty", "casewt", "weight", "lb", "price", "total", "ext"]
    col_info = detect_columns(rows, header_kw)
    return extract_line_items(rows, col_info)


def _parse_usfoods(rows: list[list[dict]]) -> list[dict]:
    """US Foods invoices: similar to Sysco columnar layout."""
    header_kw = ["item", "description", "qty", "pack", "size", "price", "total", "ext",
                 "product", "extended", "ttem", "ltem", "aty"]
    col_info = detect_columns(rows, header_kw)
    items = extract_line_items(rows, col_info)
    if items:
        return items
    # Fallback: header may be white-on-dark and unreadable
    return _extract_items_simple(rows)


# ── 8. Result builders ──

def _build_result(items, rows, raw_rows, parser_used, col_info=None):
    return {
        "items": items,
        "row_count": len(rows),
        "column_count": len(col_info["columns"]) if col_info else 0,
        "header_detected": (col_info or {}).get("header_row_idx", -1) >= 0,
        "parser_used": parser_used,
        "raw_rows": raw_rows,
    }


def _empty_result(reason):
    return {
        "items": [],
        "row_count": 0,
        "column_count": 0,
        "header_detected": False,
        "parser_used": f"none ({reason})",
        "raw_rows": [],
    }
