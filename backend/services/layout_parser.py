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

# Regex for pack-size patterns in item names (e.g., "4/10 LB", "48/6 OZ", "2/5 GAL")
PACK_PATTERN = re.compile(
    r'\d+/\d+\s*(?:LB|LBS|OZ|GAL|CT|EA|DZ|ML|QT|PT|CS|PK|BX)\b',
    re.IGNORECASE
)


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
    Uses right-edge alignment of numeric values (prices/totals are right-aligned),
    filters out pack-size words, and detects pack-size columns by spatial clustering.
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
    first_num_left = col_bounds[0]["left"] if col_bounds else 9999

    # Detect pack-size column by clustering pack-size words spatially
    pack_positions = []
    for _, row in data_rows:
        for w in row:
            if _is_pack_size_word(w["text"]):
                pack_positions.append(w)

    pack_col = None
    if pack_positions:
        # Cluster pack word left-positions to find the pack column region
        pack_lefts = sorted(p["left"] for p in pack_positions)
        pack_clusters = []
        curr_cluster = [pack_lefts[0]]
        for pl in pack_lefts[1:]:
            if pl - curr_cluster[-1] < 80:
                curr_cluster.append(pl)
            else:
                pack_clusters.append(curr_cluster)
                curr_cluster = [pl]
        pack_clusters.append(curr_cluster)

        # Use the largest cluster as the pack column
        biggest = max(pack_clusters, key=len)
        if len(biggest) >= max(2, len(data_rows) * 0.3):
            pack_left = min(biggest) - 15
            pack_right = max(p["right"] for p in pack_positions if p["left"] >= min(biggest) - 10) + 15
            # Only create pack column if it's between description and numeric columns
            if pack_left < first_num_left:
                pack_col = {
                    "name": "Pack", "left": pack_left,
                    "right": pack_right, "field": "pack_size",
                }

    # Description column: left of pack column (if found) or first numeric column
    desc_right = (pack_col["left"] - 5) if pack_col else (first_num_left - 15)
    columns.append({
        "name": "Description", "left": 0,
        "right": desc_right, "field": "item_name",
    })

    # Insert pack column if detected
    if pack_col:
        columns.append(pack_col)

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
        # For numeric fields, only accept numeric-like words via nearest match
        # to prevent OCR artifacts (e.g., "lo" for "10") from poisoning numeric columns
        best_col = None
        best_dist = float("inf")
        w_text = w["text"].strip()
        w_is_numeric = bool(re.match(r'^[\d$.,]+$', w_text.replace(",", "").strip("'`\"\u2018\u2019\u201C\u201D")))
        for col in columns:
            # Skip numeric columns for non-numeric words
            if col["field"] in ("quantity", "unit_price", "total") and not w_is_numeric:
                continue
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
        # Multiple words in qty column: take the last (rightmost) value
        # This handles ORD/SHIP spillover where both values land in qty column
        qty_words = col_assignments["quantity"]
        qty_val = _parse_number(" ".join(qty_words))
        if qty_val == 0 and len(qty_words) > 1:
            # Try each word individually, take the last parseable one
            for qw in reversed(qty_words):
                v = _parse_number(qw)
                if v > 0:
                    qty_val = v
                    break
        result["quantity"] = qty_val
    if "unit_price" in col_assignments:
        result["unit_price"] = _parse_number(" ".join(col_assignments["unit_price"]))
    if "total" in col_assignments:
        result["total_price"] = _parse_number(" ".join(col_assignments["total"]))
    if "pack_size" in col_assignments:
        result["pack_size"] = " ".join(col_assignments["pack_size"])

    # Handle unknown columns — try to assign as numbers or pack sizes
    # Only fill quantity/price/total from unknown columns if there's no dedicated column for them
    has_qty_column = any(c["field"] == "quantity" for c in columns)
    has_price_column = any(c["field"] == "unit_price" for c in columns)
    has_total_column = any(c["field"] == "total" for c in columns)

    for field, words in col_assignments.items():
        if field == "unknown":
            # Check if all words are pack-size words
            all_pack = all(_is_pack_size_word(w) for w in words)
            if all_pack and not result["pack_size"]:
                result["pack_size"] = " ".join(words)
                continue
            val = _parse_number(" ".join(words))
            if val > 0:
                # Heuristic: small integers (1-999) with no decimal → likely quantity
                is_integer = val == int(val) and val < 1000
                if is_integer and result["quantity"] == 0 and not has_qty_column:
                    result["quantity"] = val
                elif result["total_price"] == 0 and not has_total_column:
                    result["total_price"] = val
                elif result["unit_price"] == 0 and not has_price_column:
                    result["unit_price"] = val
                elif result["quantity"] == 0 and not has_qty_column:
                    result["quantity"] = val

    # Post-process: extract pack-size patterns from item_name into pack_size
    if result["item_name"] and not result["pack_size"]:
        name = result["item_name"]
        pack_match = PACK_PATTERN.search(name)
        if pack_match:
            pack_str = pack_match.group()
            cleaned = name[:pack_match.start()].strip() + " " + name[pack_match.end():].strip()
            result["item_name"] = cleaned.strip()
            result["pack_size"] = pack_str

    return result


def _extract_items_simple(rows: list[list[dict]], start: int = 0) -> list[dict]:
    """
    Fallback: extract items without column info.
    Assumes format: description ... [pack] qty price total (numbers on the right).
    Separates pack-size patterns (e.g., "6/5 LB") into pack_size field.
    """
    items = []
    for row in rows[start:]:
        text = row_text(row)
        if _is_separator_or_summary(text):
            continue

        # Split into text words, pack words, and numeric words
        text_parts = []
        pack_parts = []
        numbers = []
        for w in row:
            wt = w["text"].strip()
            if _is_pack_size_word(wt):
                pack_parts.append(wt)
            elif re.match(r'^[\d$.,]+$', wt.replace(",", "").strip("'`\"\u2018\u2019\u201C\u201D")):
                val = _parse_number(wt)
                if val > 0:
                    numbers.append(val)
            else:
                text_parts.append(wt)

        name = " ".join(text_parts).strip()
        if not name or len(numbers) < 2:
            continue

        pack_size = " ".join(pack_parts).strip()

        # Assign numbers: usually qty, price, total (right to left: total, price, qty)
        item = {"item_name": name, "quantity": 0, "unit_price": 0, "total_price": 0, "pack_size": pack_size}

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
                return _build_result(items, rows, raw_rows, parser_used, vendor=vendor_name)

        if document_type == "simple_receipt":
            items = _parse_receipt(rows)
            return _build_result(items, rows, raw_rows, "receipt_parser")

        # Default: structured invoice parser
        col_info = detect_columns(rows)
        items = extract_line_items(rows, col_info)

        # Check yield: if column-based extraction is unreasonably low vs data rows,
        # try simple extraction — column mapping may have garbled values
        data_start = col_info.get("data_start_idx", 0)
        data_row_count = sum(
            1 for r in rows[data_start:] if not _is_separator_or_summary(row_text(r))
        )
        low_yield = data_row_count >= 3 and len(items) < data_row_count * 0.4

        if not items or low_yield:
            fallback_items = _extract_items_simple(rows, data_start)
            if len(fallback_items) > len(items):
                items = fallback_items
                parser_used = "structured_fallback"
            elif items:
                header = col_info.get("header_row_idx", -1) >= 0
                parser_used = "structured_columnar" if header else "structured_inferred"
            else:
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


def _is_low_yield(items: list[dict], rows: list[list[dict]], col_info: dict) -> bool:
    """Check if extraction yield is unreasonably low vs available data rows."""
    data_start = col_info.get("data_start_idx", 0)
    data_row_count = sum(
        1 for r in rows[data_start:] if not _is_separator_or_summary(row_text(r))
    )
    return data_row_count >= 3 and len(items) < data_row_count * 0.4

def _parse_sysco(rows: list[list[dict]]) -> list[dict]:
    """
    Sysco invoices: ITEM#, DESCRIPTION, PACK SIZE, QTY, PRICE, EXT PRICE
    Header may be white-on-dark (unreadable by OCR).
    Falls back to pack-aware column inference, then simple extraction.
    Uses low-yield detection to avoid stuck on garbled column-mapped values.
    """
    header_kw = ["item", "description", "pack", "qty", "price", "total", "ext", "net"]
    col_info = detect_columns(rows, header_kw)
    items = extract_line_items(rows, col_info)
    if items and not _is_low_yield(items, rows, col_info):
        return items
    # Fallback: white-on-dark header — try inferred columns (includes pack detection)
    col_info = _infer_columns_from_data(rows)
    if col_info.get("columns"):
        items_inf = extract_line_items(rows, col_info)
        if items_inf and not _is_low_yield(items_inf, rows, col_info):
            return items_inf
        if items_inf and (not items or len(items_inf) > len(items)):
            items = items_inf
    # Final fallback: simple extraction with pack separation
    fallback = _extract_items_simple(rows)
    return fallback if len(fallback) > len(items or []) else (items or fallback)


def _parse_pfg(rows: list[list[dict]]) -> list[dict]:
    """
    PFG / Performance Foodservice invoices.
    Column layout: ITEM# | DESCRIPTION | PACK | ORD | SHIP | WEIGHT | $/LB | EXT PRICE

    Key: the correct billing quantity is SHIP, not ORD. WEIGHT is NOT quantity.
    The generic right-to-left assignment (total, price, qty) wrongly maps WEIGHT to qty.

    Strategy:
    1. Try header detection (if readable)
    2. Fallback: PFG-specific column inference — identify ORD/SHIP pair (two
       small-integer columns between pack and weight), use SHIP as quantity
    """
    header_kw = ["description", "pack", "qty", "ord", "ship", "casewt", "weight",
                 "lb", "price", "total", "ext"]
    col_info = detect_columns(rows, header_kw)
    items = extract_line_items(rows, col_info)
    if items and not _is_low_yield(items, rows, col_info):
        return items

    # Fallback: PFG-specific column inference
    items = _parse_pfg_inferred(rows)
    if items:
        return items

    # Last resort: simple extraction
    return _extract_items_simple(rows)


def _parse_pfg_inferred(rows: list[list[dict]]) -> list[dict]:
    """
    PFG-specific column inference.
    Identifies the ORD/SHIP pair and WEIGHT column to correctly assign qty.

    PFG layout (by x-position):
    - ITEM# (x≈16-65): 7-digit number
    - DESCRIPTION (x≈86-300): text words
    - PACK (x≈366-419): pack-size words (e.g., "6/4 LB")
    - ORD (x≈466-480): small integer (ordered qty)
    - SHIP (x≈526-540): small integer (shipped qty) ← THIS IS THE CORRECT QTY
    - WEIGHT (x≈596-633): decimal (total weight in LBs)
    - $/LB (x≈686-740): $-prefixed price per pound
    - EXT PRICE (x≈796-862): $-prefixed total

    Detection logic:
    - Find ALL numeric columns by spatial clustering
    - Identify the $-prefixed columns (price + total) from the right
    - Among the remaining numeric columns, find the ORD/SHIP pair:
      two adjacent small-integer columns between pack zone and weight zone
    - SHIP is the second of the pair (closer to weight)
    - WEIGHT is the decimal column just before $/LB
    """
    # Find data rows
    data_rows = []
    for i, row in enumerate(rows):
        nums = [w for w in row if _is_price_like(w["text"])]
        if len(nums) >= 3:
            data_rows.append((i, row))

    if not data_rows:
        return []

    # Cluster ALL numeric words by x-position
    num_positions = []  # (left, right, text, row_idx)
    for ri, row in data_rows:
        for w in row:
            if _is_price_like(w["text"]):
                num_positions.append((w["left"], w["right"], w["text"], ri))

    # Cluster by left position
    from collections import defaultdict
    pos_sorted = sorted(num_positions, key=lambda x: x[0])
    clusters = []
    curr = [pos_sorted[0]]
    for p in pos_sorted[1:]:
        if p[0] - curr[-1][0] < 40:
            curr.append(p)
        else:
            clusters.append(curr)
            curr = [p]
    clusters.append(curr)

    # Classify each cluster
    # $-prefixed clusters are price/total, decimal clusters could be weight,
    # small-integer clusters are qty candidates
    cluster_info = []
    for cl in clusters:
        avg_left = int(np.mean([p[0] for p in cl]))
        avg_right = int(np.mean([p[1] for p in cl]))
        texts = [p[2] for p in cl]
        has_dollar = any("$" in t for t in texts)
        values = []
        for t in texts:
            v = _parse_number(t)
            if v > 0:
                values.append(v)
        avg_val = np.mean(values) if values else 0
        max_val = max(values) if values else 0
        # Distinguish true small integers (1, 4, 25) from decimal-formatted values (24.00, 80.00)
        # "24.00" is int-valued but written with decimals → it's a weight/decimal column, not qty
        texts_have_decimal = any("." in t.replace("$", "") for t in texts)
        is_small_integer = (not texts_have_decimal and
                            all(v == int(v) and v < 200 for v in values)) if values else False

        cluster_info.append({
            "left": avg_left, "right": avg_right,
            "has_dollar": has_dollar, "is_small_integer": is_small_integer,
            "texts_have_decimal": texts_have_decimal,
            "avg_val": avg_val, "max_val": max_val,
            "count": len(cl), "texts": texts,
        })

    # Sort clusters left-to-right
    cluster_info.sort(key=lambda c: c["left"])

    # Identify: rightmost $-prefixed = total, second rightmost $-prefixed = $/LB
    dollar_clusters = [c for c in cluster_info if c["has_dollar"]]
    non_dollar = [c for c in cluster_info if not c["has_dollar"]]

    if len(dollar_clusters) < 2:
        return []  # Can't identify price+total

    dollar_clusters.sort(key=lambda c: c["left"])
    price_col_info = dollar_clusters[-2]  # $/LB
    total_col_info = dollar_clusters[-1]  # EXT PRICE

    # Among non-dollar clusters, identify:
    # - ITEM# (leftmost, 7-digit numbers)
    # - ORD/SHIP pair (two adjacent small-integer columns, max_val < 200)
    # - WEIGHT (decimal column, between SHIP and $/LB)
    qty_candidates = []
    weight_candidate = None

    for c in non_dollar:
        # Skip if it's the leftmost (likely ITEM#)
        if c["left"] < 100:
            continue
        # Skip if right of price column
        if c["left"] > price_col_info["left"]:
            continue

        if c["is_small_integer"] and c["max_val"] < 200:
            qty_candidates.append(c)
        elif c["texts_have_decimal"] and c["avg_val"] > 5:
            weight_candidate = c

    # The SHIP column is the one closest to (but left of) the WEIGHT column
    # If we have exactly 2 qty candidates, SHIP = the right one
    ship_col = None
    if len(qty_candidates) >= 2:
        qty_candidates.sort(key=lambda c: c["left"])
        ship_col = qty_candidates[-1]  # Rightmost small-integer = SHIP
    elif len(qty_candidates) == 1:
        ship_col = qty_candidates[0]

    if not ship_col:
        return []  # Can't find qty column

    # Build column definitions
    # Find pack zone
    pack_positions = []
    for _, row in data_rows:
        for w in row:
            if _is_pack_size_word(w["text"]):
                pack_positions.append(w)
    pack_right = max(p["right"] for p in pack_positions) + 10 if pack_positions else ship_col["left"] - 20

    columns = [
        {"name": "Description", "left": 0, "right": pack_right - 5 if pack_positions else ship_col["left"] - 20, "field": "item_name"},
    ]
    if pack_positions:
        pack_left = min(p["left"] for p in pack_positions) - 10
        columns.append({"name": "Pack", "left": pack_left, "right": pack_right, "field": "pack_size"})

    columns.append({"name": "Ship Qty", "left": ship_col["left"] - 10, "right": ship_col["right"] + 10, "field": "quantity"})

    if weight_candidate:
        columns.append({"name": "Weight", "left": weight_candidate["left"] - 10, "right": weight_candidate["right"] + 10, "field": "unknown"})

    columns.append({"name": "$/LB", "left": price_col_info["left"] - 10, "right": price_col_info["right"] + 10, "field": "unit_price"})
    columns.append({"name": "Ext Price", "left": total_col_info["left"] - 10, "right": total_col_info["right"] + 10, "field": "total"})

    columns.sort(key=lambda c: c["left"])

    col_info = {
        "header_row_idx": -1,
        "columns": columns,
        "data_start_idx": data_rows[0][0],
    }

    return extract_line_items(rows, col_info)


def _parse_usfoods(rows: list[list[dict]]) -> list[dict]:
    """US Foods invoices: similar to Sysco columnar layout.
    Falls back to pack-aware column inference, then simple extraction.
    Uses low-yield detection to avoid stuck on garbled column-mapped values."""
    header_kw = ["item", "description", "qty", "pack", "size", "price", "total", "ext",
                 "product", "extended", "ttem", "ltem", "aty"]
    col_info = detect_columns(rows, header_kw)
    items = extract_line_items(rows, col_info)
    if items and not _is_low_yield(items, rows, col_info):
        return items
    # Fallback: try inferred columns (includes pack detection)
    col_info = _infer_columns_from_data(rows)
    if col_info.get("columns"):
        items_inf = extract_line_items(rows, col_info)
        if items_inf and not _is_low_yield(items_inf, rows, col_info):
            return items_inf
        if items_inf and (not items or len(items_inf) > len(items)):
            items = items_inf
    # Final fallback: simple extraction with pack separation
    fallback = _extract_items_simple(rows)
    return fallback if len(fallback) > len(items or []) else (items or fallback)


# ── 8. Numeric Validation ──

def validate_line_item(item: dict) -> dict:
    """
    Validate a single parsed line item. Returns a validation dict with:
    - status: "pass", "warning", or "needs_review"
    - issues: list of specific problem descriptions
    - computed_total: qty × unit_price (for comparison)
    - total_diff: absolute difference between computed and parsed total
    - total_diff_pct: percentage difference
    """
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total_price", 0) or 0)
    name = (item.get("item_name", "") or "").strip()

    issues = []
    status = "pass"

    # Check for missing critical fields
    if not name:
        issues.append("missing_item_name")
    if qty == 0:
        issues.append("missing_quantity")
    if price == 0 and total == 0:
        issues.append("missing_price_and_total")
    elif price == 0 and qty > 0 and total > 0:
        issues.append("missing_unit_price")
    elif total == 0 and qty > 0 and price > 0:
        issues.append("missing_total")

    # Cross-check: qty × unit_price ≈ total_price
    computed_total = round(qty * price, 2) if qty > 0 and price > 0 else 0
    total_diff = abs(computed_total - total) if computed_total > 0 and total > 0 else 0
    total_diff_pct = (total_diff / total * 100) if total > 0 else 0

    if computed_total > 0 and total > 0:
        if total_diff <= 0.02:
            pass  # Perfect or rounding match
        elif total_diff <= 0.50 or total_diff_pct <= 2.0:
            issues.append(f"math_close: qty({qty})×price({price})={computed_total} vs total({total}), diff=${total_diff:.2f}")
            status = "warning"
        else:
            issues.append(f"math_mismatch: qty({qty})×price({price})={computed_total} vs total({total}), diff=${total_diff:.2f} ({total_diff_pct:.1f}%)")
            status = "needs_review"

    # Reasonableness checks
    if qty > 0 and qty != int(qty) and qty < 1:
        issues.append(f"fractional_qty: {qty}")
    if price > 0 and total > 0 and total < price:
        issues.append(f"total_less_than_price: total({total}) < price({price})")
        if status != "needs_review":
            status = "warning"

    # Determine final status from issues
    if not issues:
        status = "pass"
    elif status == "pass" and issues:
        status = "warning"

    return {
        "status": status,
        "issues": issues,
        "computed_total": computed_total,
        "total_diff": round(total_diff, 2),
        "total_diff_pct": round(total_diff_pct, 1),
    }


def validate_invoice(items: list[dict]) -> dict:
    """
    Invoice-level validation across all parsed line items.
    Returns a validation summary with flagged items and aggregate checks.
    """
    total_items = len(items)
    valid_count = 0
    warning_count = 0
    review_count = 0
    flagged_indices = []
    invoice_issues = []

    items_sum = 0.0
    for i, item in enumerate(items):
        validation = validate_line_item(item)
        item["validation"] = validation

        if validation["status"] == "pass":
            valid_count += 1
        elif validation["status"] == "warning":
            warning_count += 1
            flagged_indices.append(i)
        else:
            review_count += 1
            flagged_indices.append(i)

        items_sum += float(item.get("total_price", 0) or 0)

    items_sum = round(items_sum, 2)

    # Check for duplicate items (same name, similar values)
    seen_names = {}
    for i, item in enumerate(items):
        name = (item.get("item_name", "") or "").strip().upper()
        if not name:
            continue
        if name in seen_names:
            prev_i = seen_names[name]
            prev = items[prev_i]
            if (float(prev.get("total_price", 0)) == float(item.get("total_price", 0))
                    and float(prev.get("quantity", 0)) == float(item.get("quantity", 0))):
                invoice_issues.append(f"possible_duplicate: items[{prev_i}] and items[{i}] ('{name}')")
                if i not in flagged_indices:
                    flagged_indices.append(i)
        seen_names[name] = i

    # Check for all-zero items
    zero_total_count = sum(1 for it in items if float(it.get("total_price", 0) or 0) == 0)
    if zero_total_count > 0 and total_items > 0:
        invoice_issues.append(f"zero_totals: {zero_total_count}/{total_items} items have $0 total")

    # Check for missing quantities
    zero_qty_count = sum(1 for it in items if float(it.get("quantity", 0) or 0) == 0)
    if zero_qty_count > 0 and total_items > 0:
        invoice_issues.append(f"zero_quantities: {zero_qty_count}/{total_items} items have qty=0")

    return {
        "total_items": total_items,
        "valid_items": valid_count,
        "warning_items": warning_count,
        "needs_review_items": review_count,
        "flagged_indices": sorted(set(flagged_indices)),
        "items_sum": items_sum,
        "invoice_issues": invoice_issues,
        "overall_status": (
            "pass" if review_count == 0 and warning_count == 0 and not invoice_issues
            else "needs_review" if review_count > 0
            else "warning"
        ),
    }


# ── 9. Result builders ──

def _build_result(items, rows, raw_rows, parser_used, col_info=None, vendor=None):
    # Run numeric validation on all items
    validation_summary = validate_invoice(items)

    # Run semantic validation (Phase 4)
    from services.semantic_validator import run_semantic_validation
    semantic_summary = run_semantic_validation(items, vendor=vendor)

    return {
        "items": items,
        "row_count": len(rows),
        "column_count": len(col_info["columns"]) if col_info else 0,
        "header_detected": (col_info or {}).get("header_row_idx", -1) >= 0,
        "parser_used": parser_used,
        "raw_rows": raw_rows,
        "validation_summary": validation_summary,
        "semantic_summary": semantic_summary,
    }


def _empty_result(reason):
    return {
        "items": [],
        "row_count": 0,
        "column_count": 0,
        "header_detected": False,
        "parser_used": f"none ({reason})",
        "raw_rows": [],
        "validation_summary": {
            "total_items": 0,
            "valid_items": 0,
            "warning_items": 0,
            "needs_review_items": 0,
            "flagged_indices": [],
            "items_sum": 0,
            "invoice_issues": [],
            "overall_status": "pass",
        },
        "semantic_summary": {
            "semantic_issues_total": 0,
            "suspicious_count": 0,
            "needs_review_count": 0,
            "flagged_indices": [],
            "checks_run": [],
        },
    }
