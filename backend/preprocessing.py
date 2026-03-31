"""
Image preprocessing and multi-page classification for invoice extraction.
Phase 1: lightweight, safe, plugs into existing pipeline.
"""
import base64
import io
import json
import re
import logging
import uuid
import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Image Preprocessing
# ---------------------------------------------------------------------------

def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Lightweight preprocessing to improve OCR accuracy.
    Returns processed PNG bytes.  Falls back to original on ANY error.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # 1. Auto-rotate from EXIF (fixes phone-camera orientation)
        img = ImageOps.exif_transpose(img)

        # 2. Convert to RGB (strips alpha, normalises palette images)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 3. Simple deskew (projection-profile on grayscale)
        img = _deskew(img)

        # 4. Auto-contrast – equalises faded/dark scans
        img = ImageOps.autocontrast(img, cutoff=0.5)

        # 5. Crop empty margins
        img = _crop_margins(img)

        # 6. Light sharpening (slightly blurry scans)
        img = ImageEnhance.Sharpness(img).enhance(1.3)

        # 7. Slight contrast bump
        img = ImageEnhance.Contrast(img).enhance(1.1)

        # 8. Noise reduction – gentle median keeps edges
        img = img.filter(ImageFilter.MedianFilter(size=3))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        processed = buf.getvalue()
        logger.info(
            f"Preprocessed image: {len(image_bytes)}→{len(processed)} bytes "
            f"({img.size[0]}x{img.size[1]})"
        )
        return processed
    except Exception as e:
        logger.warning(f"Image preprocessing failed, using original: {e}")
        return image_bytes


def _deskew(img: Image.Image, max_angle: float = 5.0) -> Image.Image:
    """
    Estimate and correct small skew angles (±5°) using horizontal
    projection-profile variance.  Fast: tests 21 angles in ~50 ms
    on a typical receipt image.
    """
    try:
        # Work on a small grayscale thumbnail for speed
        thumb = img.convert("L").resize((400, int(400 * img.height / img.width)))
        arr = np.array(thumb)
        # Binarise (Otsu-like simple threshold)
        threshold = int(arr.mean()) - 20
        binary = (arr < max(threshold, 80)).astype(np.float32)

        best_angle = 0.0
        best_score = -1.0
        for angle_10x in range(int(-max_angle * 10), int(max_angle * 10) + 1, 5):
            angle = angle_10x / 10.0
            rotated = _rotate_array(binary, angle)
            profile = rotated.sum(axis=1)
            score = float(np.var(profile))
            if score > best_score:
                best_score = score
                best_angle = angle

        if abs(best_angle) < 0.3:
            return img  # negligible skew

        logger.info(f"Deskew: correcting {best_angle:.1f}° skew")
        return img.rotate(best_angle, resample=Image.BICUBIC,
                          expand=True, fillcolor=(255, 255, 255))
    except Exception as e:
        logger.warning(f"Deskew failed, skipping: {e}")
        return img


def _rotate_array(arr: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate a 2-D array by a small angle using Pillow (avoids scipy)."""
    img = Image.fromarray((arr * 255).astype(np.uint8), mode="L")
    rotated = img.rotate(angle_deg, resample=Image.BILINEAR,
                         expand=False, fillcolor=0)
    return np.array(rotated).astype(np.float32) / 255.0


def _crop_margins(img: Image.Image, min_crop_pct: float = 0.05) -> Image.Image:
    """Crop empty white/light borders. Only crops if >5 % of area is margin."""
    try:
        gray = img.convert("L")
        inv = ImageOps.invert(gray)
        bbox = inv.getbbox()
        if not bbox:
            return img

        pad = 10
        w, h = img.size
        x0 = max(0, bbox[0] - pad)
        y0 = max(0, bbox[1] - pad)
        x1 = min(w, bbox[2] + pad)
        y1 = min(h, bbox[3] + pad)

        crop_area = (x1 - x0) * (y1 - y0)
        orig_area = w * h
        if crop_area < orig_area * (1.0 - min_crop_pct):
            return img.crop((x0, y0, x1, y1))
        return img
    except Exception:
        return img


# ---------------------------------------------------------------------------
# 2. Multi-Page Classification
# ---------------------------------------------------------------------------

PAGE_TYPES = {"header", "line_items", "totals", "terms"}


async def classify_pages(images_b64: list, llm_key: str) -> list:
    """
    Classify each page of a multi-page document using one LLM call.
    Returns e.g. ['header', 'line_items', 'totals'].
    Falls back to heuristic on failure.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    prompt = (
        f"You are analyzing a {len(images_b64)}-page invoice/receipt document.\n"
        "For EACH page (image), classify it as exactly ONE of:\n"
        '- "header"     — vendor name, address, invoice number, date\n'
        '- "line_items" — table/list of purchased items with quantities & prices\n'
        '- "totals"     — subtotal, tax, total, payment summary\n'
        '- "terms"      — terms & conditions, notes, legal, mostly blank\n\n'
        "If a page has BOTH header info AND line items → \"header\".\n"
        "If a page has BOTH line items AND totals   → \"totals\".\n"
        "Default to the dominant content type.\n\n"
        "Return ONLY a JSON array of strings, one per page. Example:\n"
        '["header", "line_items", "totals"]\n'
    )

    try:
        chat = (
            LlmChat(
                api_key=llm_key,
                session_id=f"classify-{uuid.uuid4()}",
                system_message="Classify invoice pages. Return JSON arrays only.",
            )
            .with_model("openai", "gpt-5.2")
        )
        file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=file_contents)
        )

        match = re.search(r"\[[\s\S]*?\]", response)
        if match:
            raw = json.loads(match.group())
            result = [
                (c.lower().strip() if c.lower().strip() in PAGE_TYPES else "line_items")
                for c in raw
            ]
            # Pad / trim
            while len(result) < len(images_b64):
                result.append("line_items")
            result = result[: len(images_b64)]
            logger.info(f"Page classification: {result}")
            return result

        logger.warning("Could not parse classification response, using heuristic")
        return _default_classifications(len(images_b64))
    except Exception as e:
        logger.warning(f"Page classification LLM failed: {e}")
        return _default_classifications(len(images_b64))


def _default_classifications(n: int) -> list:
    """Heuristic fallback: first=header, middle=line_items, last=totals."""
    if n == 1:
        return ["header"]
    if n == 2:
        return ["header", "totals"]
    return ["header"] + ["line_items"] * (n - 2) + ["totals"]


# ---------------------------------------------------------------------------
# 3. Page-Type-Aware Extraction Prompt
# ---------------------------------------------------------------------------

def build_page_aware_prompt(
    page_types: list,
    vendor_hint: str = "",
) -> str:
    """
    Build a purchase-invoice extraction prompt that tells the LLM
    what each page contains, with explicit priority rules.
    Returns the full prompt string.
    """
    page_desc = "\n".join(
        f"  Page {i + 1}: {ptype.upper().replace('_', ' ')}"
        for i, ptype in enumerate(page_types)
    )

    return f"""You are reading a restaurant purchase invoice/receipt spanning {len(page_types)} page(s).

PAGE MAP (already classified for you):
{page_desc}

EXTRACTION INSTRUCTIONS BY PAGE TYPE:
- HEADER page(s)     → extract supplier_name, invoice_date, invoice_number
- LINE ITEMS page(s) → extract every line item (raw_name, quantity, pack_size, unit_price, total)
- TOTALS page(s)     → extract subtotal, tax, total — these VALUES OVERRIDE any totals on other pages
- TERMS page(s)      → SKIP entirely, do not extract anything

PRIORITY RULES (when same field appears on multiple pages):
- subtotal / tax / total   : TOTALS page wins  >  header page  >  line_items page
- supplier_name / date / # : HEADER page wins   >  totals page  >  line_items page

Output this exact JSON (one object, not per-page):
{{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0}}],"subtotal":0,"tax":0,"total":0}}

CRITICAL item-level rules:
- total = quantity × unit_price per item
- If unit_price missing: unit_price = total / quantity
- If quantity missing: quantity = total / unit_price
- Dates → YYYY-MM-DD. Use 0 for missing numbers.
- pack_size: The pack/case size EXACTLY as shown on the invoice (e.g., "10/4 LB", "6/5 LB", "BAG 50 LB", "150 EA", "1 GAL", "2/17.5 LB", "1/25 LB"). Copy this field verbatim from the invoice. Leave empty string if not visible.
- Do NOT duplicate items across overlapping pages. Each item ONCE.
- Return ONLY the JSON object.{vendor_hint}"""


# ---------------------------------------------------------------------------
# 4. Document-Level Merge (fallback utility)
# ---------------------------------------------------------------------------

def merge_extractions(page_results: list, page_types: list) -> dict:
    """
    Merge per-page extraction dicts into one invoice.
    Priority for totals fields:  totals > header > line_items
    Priority for vendor fields:  header > totals > line_items
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

    # --- Vendor / header fields: header page wins ---
    vendor_priority = {"header": 0, "totals": 1, "line_items": 2, "terms": 3}
    for ptype, result in sorted(
        zip(page_types, page_results), key=lambda x: vendor_priority.get(x[0], 3)
    ):
        if not result or ptype == "terms":
            continue
        for fld in ("supplier_name", "invoice_date", "invoice_number"):
            if result.get(fld) and not merged[fld]:
                merged[fld] = result[fld]

    # --- Totals fields: totals page wins ---
    totals_priority = {"totals": 0, "header": 1, "line_items": 2, "terms": 3}
    for ptype, result in sorted(
        zip(page_types, page_results), key=lambda x: totals_priority.get(x[0], 3)
    ):
        if not result or ptype == "terms":
            continue
        if ptype == "totals":
            for fld in ("subtotal", "tax", "total"):
                val = float(result.get(fld, 0) or 0)
                if val:
                    merged[fld] = val
        elif not merged["total"]:
            for fld in ("subtotal", "tax", "total"):
                val = float(result.get(fld, 0) or 0)
                if val:
                    merged[fld] = val

    # --- Items: accumulate + dedup by (name, qty, price) ---
    seen_items = set()
    for ptype, result in zip(page_types, page_results):
        if not result or ptype == "terms":
            continue
        for item in result.get("items", []):
            key = (
                (item.get("raw_name", "") or "").lower().strip(),
                float(item.get("quantity", 0) or 0),
                float(item.get("unit_price", 0) or 0),
            )
            if key[0] and key not in seen_items:
                seen_items.add(key)
                merged["items"].append(item)

    return merged


# ---------------------------------------------------------------------------
# 5. Pack Size Parsing & Normalization (with strict validation)
# ---------------------------------------------------------------------------

# ONLY these units are trusted for $/LB normalization
NORMALIZABLE_UNITS = {"LB", "OZ"}

# Conversion to LB — ONLY LB and OZ
TO_LB = {
    "LB": 1.0,
    "OZ": 0.0625,
}

# All known units (for parsing, not normalization)
KNOWN_UNITS = {
    "LB", "LBS", "KG", "OZ", "G", "GM", "GR", "GRAM", "GRAMS",
    "GAL", "GALLON", "QT", "QUART", "L", "LITER", "ML", "PT", "PINT",
    "EA", "EACH", "CT", "COUNT", "PK", "PACK", "BX", "BOX",
    "CS", "CASE", "BG", "BAG", "DZ", "DOZEN",
}

# Canonical unit mapping
UNIT_CANONICAL = {
    "LBS": "LB", "POUND": "LB", "POUNDS": "LB", "#": "LB",
    "KGS": "KG", "KILO": "KG", "KILOS": "KG", "KILOGRAM": "KG",
    "OZS": "OZ", "OUNCE": "OZ", "OUNCES": "OZ",
    "GALLON": "GAL", "GALLONS": "GAL",
    "QUART": "QT", "QUARTS": "QT",
    "LITER": "L", "LITERS": "L", "LITRE": "L",
    "EACH": "EA", "COUNT": "CT",
    "PACK": "PK", "PACKS": "PK",
    "BOX": "BX", "BOXES": "BX",
    "CASE": "CS", "CASES": "CS",
    "BAG": "BG", "BAGS": "BG",
    "DOZEN": "DZ",
    "GRAM": "G", "GRAMS": "G", "GM": "G",
    "PINT": "PT", "PINTS": "PT",
}


def _canonicalize_unit(raw: str) -> str:
    """Normalize unit string to canonical form."""
    u = raw.strip().upper().rstrip(".")
    return UNIT_CANONICAL.get(u, u)


# Safe prefixes to strip (packaging descriptors that precede the actual size)
_STRIP_PREFIXES = {"CS", "BX", "BG", "PK", "CT", "BAG", "BOX", "CASE", "PACK"}


def _normalize_raw_text(text: str) -> str:
    """
    Clean OCR artifacts from pack size text BEFORE pattern matching.
    Only applies safe, deterministic transformations.
    """
    s = text.strip().upper()
    if not s:
        return s

    # 1. Collapse multiple spaces/tabs
    s = re.sub(r"\s+", " ", s)

    # 2. Remove duplicated separators: "//" → "/"
    s = re.sub(r"/{2,}", "/", s)

    # 3. Strip known prefix glued to digits FIRST (before space insertion)
    #    e.g., "CS1000/7 GM" → "1000/7 GM", "BX24/12 OZ" → "24/12 OZ"
    m = re.match(r"^([A-Z]{2,3})(\d+[/\d].*)", s)
    if m and m.group(1) in _STRIP_PREFIXES:
        s = m.group(2)

    # 4. "WORD+NUMBER" with no space → insert space (AFTER prefix strip)
    #    e.g., "BAG50 LB" → "BAG 50 LB"
    s = re.sub(r"^([A-Z]+)(\d)", r"\1 \2", s)

    # 5. "N/N# WORD" → extract just the "N/N#" part
    #    e.g., "6/7# JAR" → "6/7#" (JAR is packaging descriptor, not unit)
    m = re.match(r"^(\d+/\d+\.?\d*#)\s+[A-Z]+$", s)
    if m:
        s = m.group(1)

    # 6. Normalize spaces around slash: "10 / 4 LB" → "10/4 LB"
    s = re.sub(r"\s*/\s*", "/", s)

    return s.strip()


def parse_pack_size(raw: str) -> dict:
    """
    Parse a pack size string into structured components.
    Returns pack_parse_status: "parsed", "failed", or "not_applicable".

    Only returns structured data when parsing is confident.
    """
    text = (raw or "").strip()

    # --- NOT APPLICABLE: empty input ---
    if not text:
        return {
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable",
            "packs_per_case": None,
            "weight_per_pack": None,
            "unit": None,
            "total_case_weight": None,
        }

    # Normalize OCR artifacts before matching
    upper = _normalize_raw_text(text)

    # --- Try patterns ---
    ppc, wpp, unit = None, None, None

    # Pattern 1: "N/N UNIT" or "N/NUNIT" (e.g., "10/4 LB", "4/5LB", "2/17.5 LB")
    m = re.match(r"^(\d+)\s*/\s*(\d+\.?\d*)\s*([A-Z#]+\.?)$", upper)
    if m:
        ppc, wpp, unit = int(m.group(1)), float(m.group(2)), _canonicalize_unit(m.group(3))

    # Pattern 2: "WORD N UNIT" (e.g., "BAG 50 LB", "CS 10 LB")
    if ppc is None:
        m = re.match(r"^([A-Z]+)\s+(\d+\.?\d*)\s*([A-Z#]+\.?)$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(2)), _canonicalize_unit(m.group(3))

    # Pattern 3: "N UNIT" (e.g., "50 LB", "150 EA", "1 GAL")
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)\s+([A-Z#]+\.?)$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), _canonicalize_unit(m.group(2))

    # Pattern 3b: "NUNIT" no space (e.g., "50LB", "5LB")
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)([A-Z]{2,})$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), _canonicalize_unit(m.group(2))

    # Pattern 4: "N#" (e.g., "10#" = 10 LB)
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)#$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), "LB"

    # Pattern 5: "N/N#" (e.g., "6/7#" = 6 packs of 7 LB)
    if ppc is None:
        m = re.match(r"^(\d+)\s*/\s*(\d+\.?\d*)#$", upper)
        if m:
            ppc, wpp, unit = int(m.group(1)), float(m.group(2)), "LB"

    # Pattern 6: "N N UNIT" — spaced count+weight (e.g., "2 5 LB" = 2×5 LB)
    #   STRICT: only when all three tokens are clearly [int] [number] [known_unit]
    #   and the first number is small (≤50, typical case count)
    if ppc is None:
        m = re.match(r"^(\d+)\s+(\d+\.?\d*)\s+([A-Z]+)$", upper)
        if m:
            candidate_ppc = int(m.group(1))
            candidate_wpp = float(m.group(2))
            candidate_unit = _canonicalize_unit(m.group(3))
            # Safety: ppc must be ≤ 50 (reasonable case count)
            #         wpp must be > 0
            #         unit must be a known unit
            if (candidate_ppc <= 50 and candidate_wpp > 0
                    and candidate_unit in KNOWN_UNITS):
                ppc, wpp, unit = candidate_ppc, candidate_wpp, candidate_unit

    # --- Validate parsed result ---
    if ppc is not None and wpp is not None and unit is not None:
        # Reject if unit is not a known unit
        if unit not in KNOWN_UNITS:
            logger.warning(
                f"PACK_PARSE_FAILED: '{text}' — unknown unit '{unit}'"
            )
            return {
                "pack_size_raw": text,
                "pack_parse_status": "failed",
                "packs_per_case": None,
                "weight_per_pack": None,
                "unit": None,
                "total_case_weight": None,
            }

        # Reject nonsensical values
        if ppc <= 0 or wpp <= 0:
            logger.warning(
                f"PACK_PARSE_FAILED: '{text}' — invalid values ppc={ppc} wpp={wpp}"
            )
            return {
                "pack_size_raw": text,
                "pack_parse_status": "failed",
                "packs_per_case": None,
                "weight_per_pack": None,
                "unit": None,
                "total_case_weight": None,
            }

        tcw = round(ppc * wpp, 4)
        return {
            "pack_size_raw": text,
            "pack_parse_status": "parsed",
            "packs_per_case": ppc,
            "weight_per_pack": wpp,
            "unit": unit,
            "total_case_weight": tcw,
        }

    # --- FAILED: could not match any pattern ---
    logger.warning(f"PACK_PARSE_FAILED: '{text}' — no pattern matched")
    return {
        "pack_size_raw": text,
        "pack_parse_status": "failed",
        "packs_per_case": None,
        "weight_per_pack": None,
        "unit": None,
        "total_case_weight": None,
    }


def enrich_item_with_pack_size(item: dict) -> dict:
    """
    Parse pack_size, validate, compute normalized $/LB ONLY when 100% reliable.
    Mutates and returns the item.
    """
    pack_size_raw = (
        item.get("pack_size") or item.get("pack_size_raw") or ""
    ).strip()
    parsed = parse_pack_size(pack_size_raw)

    # Always store raw + status
    item["pack_size_raw"] = parsed["pack_size_raw"]
    item["pack_parse_status"] = parsed["pack_parse_status"]

    if parsed["pack_parse_status"] == "parsed":
        item["packs_per_case"] = parsed["packs_per_case"]
        item["weight_per_pack"] = parsed["weight_per_pack"]
        item["pack_unit"] = parsed["unit"]
        item["total_case_weight"] = parsed["total_case_weight"]
    else:
        # Failed or not_applicable — null out all computed fields
        item["packs_per_case"] = None
        item["weight_per_pack"] = None
        item["pack_unit"] = None
        item["total_case_weight"] = None

    # --- Normalized $/LB: STRICT RULES ---
    # ONLY compute if ALL conditions are met:
    #   1. pack_parse_status == "parsed"
    #   2. packs_per_case > 0
    #   3. weight_per_pack > 0
    #   4. unit is LB or OZ (NORMALIZABLE_UNITS)
    #   5. unit_price > 0
    #   6. total_case_weight > 0

    unit_price = float(item.get("unit_price", 0) or 0)
    ppc = parsed.get("packs_per_case") or 0
    wpp = parsed.get("weight_per_pack") or 0
    unit = parsed.get("unit") or ""
    tcw = parsed.get("total_case_weight") or 0

    can_normalize = (
        parsed["pack_parse_status"] == "parsed"
        and ppc > 0
        and wpp > 0
        and unit in NORMALIZABLE_UNITS
        and unit_price > 0
        and tcw > 0
    )

    if can_normalize:
        lb_factor = TO_LB.get(unit, 0)
        if lb_factor > 0:
            total_lb = tcw * lb_factor
            item["normalized_price_per_lb"] = round(unit_price / total_lb, 4)
        else:
            # Should not happen given NORMALIZABLE_UNITS check, but safety
            item["normalized_price_per_lb"] = None
    else:
        item["normalized_price_per_lb"] = None

    return item



# ---------------------------------------------------------------------------
# 6b. Hard Invoice Robustness Layer
# ---------------------------------------------------------------------------

def sanitize_extracted_item(item: dict) -> dict:
    """
    Defensive cleanup of a raw extracted item before validation.
    Handles: type coercion, garbled values, negative numbers, nulls.
    Mutates and returns the item.
    """
    parse_issues = []

    # Coerce numeric fields safely
    for field in ("quantity", "unit_price", "total"):
        val = item.get(field)
        if val is None:
            item[field] = 0
            continue
        if isinstance(val, str):
            cleaned = re.sub(r'[^0-9.\-]', '', val)
            try:
                item[field] = float(cleaned) if cleaned else 0
            except ValueError:
                parse_issues.append(f"non-numeric {field}: {repr(val)}")
                item[field] = 0
        else:
            try:
                item[field] = float(val)
            except (ValueError, TypeError):
                parse_issues.append(f"unparseable {field}: {repr(val)}")
                item[field] = 0

    # Negative values → likely OCR errors, not credits
    for field in ("quantity", "unit_price", "total"):
        if item[field] < 0:
            parse_issues.append(f"negative {field}: {item[field]}, using absolute value")
            item[field] = abs(item[field])

    # Sanitize name
    name = item.get("raw_name", "")
    if isinstance(name, (int, float)):
        name = str(name)
    item["raw_name"] = (name or "").strip()

    # Sanitize pack_size
    ps = item.get("pack_size")
    if ps is None or (isinstance(ps, (int, float)) and ps == 0):
        item["pack_size"] = ""
    else:
        item["pack_size"] = str(ps).strip()

    if parse_issues:
        item["_parse_issues"] = parse_issues

    return item


def detect_column_misread(items: list) -> list:
    """
    Detect likely column misalignment from OCR/extraction.
    E.g., quantity column has values like 42.50 (looks like prices),
    or unit_price column has values like 2 (looks like quantities).
    Returns list of issue strings.
    """
    issues = []
    if len(items) < 3:
        return issues

    qty_vals = [float(it.get("quantity", 0) or 0) for it in items if float(it.get("quantity", 0) or 0) > 0]
    price_vals = [float(it.get("unit_price", 0) or 0) for it in items if float(it.get("unit_price", 0) or 0) > 0]

    if not qty_vals or not price_vals:
        return issues

    avg_qty = sum(qty_vals) / len(qty_vals)
    avg_price = sum(price_vals) / len(price_vals)

    # Typical restaurant: qty 1-50, price 5-500
    # If avg "quantity" is much higher than avg "price", they may be swapped
    if avg_qty > avg_price * 3 and avg_price < 20 and avg_qty > 10:
        issues.append(f"possible column swap: avg quantity={avg_qty:.1f} looks like prices, avg price={avg_price:.1f} looks like quantities")

    # Check if most quantities have cents (e.g., 42.50, 18.99)
    decimal_qtys = sum(1 for q in qty_vals if q != int(q) and q > 5)
    if decimal_qtys > len(qty_vals) * 0.5 and len(qty_vals) >= 3:
        issues.append("most quantities have decimal values — likely prices in quantity column")

    return issues


def compute_extraction_meta(items: list, extracted_data: dict) -> dict:
    """
    Compute invoice-level extraction quality metadata.
    Runs AFTER item-level validation. Returns a meta dict.
    """
    total_items = len(items)
    meta = {
        "extraction_confidence": "high",
        "extraction_issues": [],
        "items_extracted": total_items,
        "items_with_issues": 0,
        "partial_extraction": False,
    }

    if total_items == 0:
        meta["extraction_confidence"] = "low"
        meta["extraction_issues"].append("no items extracted")
        meta["partial_extraction"] = True
    else:
        issues_count = 0
        empty_names = 0
        garbled_names = 0
        zero_totals = 0

        for item in items:
            has_issue = False
            name = (item.get("raw_name") or "").strip()
            total = float(item.get("total", 0) or 0)

            if not name:
                empty_names += 1
                has_issue = True
            elif not _item_name_looks_clear(name):
                garbled_names += 1
                has_issue = True

            if total == 0:
                zero_totals += 1
                has_issue = True

            if item.get("needs_review"):
                has_issue = True

            if has_issue:
                issues_count += 1

        meta["items_with_issues"] = issues_count
        issue_ratio = issues_count / total_items

        if issue_ratio > 0.7:
            meta["extraction_confidence"] = "low"
        elif issue_ratio > 0.3:
            meta["extraction_confidence"] = "medium"

        if empty_names > total_items * 0.5:
            meta["extraction_issues"].append(f"{empty_names}/{total_items} items missing names")
            meta["extraction_confidence"] = "low"

        if garbled_names > total_items * 0.3:
            meta["extraction_issues"].append(f"{garbled_names}/{total_items} items have garbled names")

        if zero_totals > total_items * 0.5:
            meta["extraction_issues"].append(f"{zero_totals}/{total_items} items have zero totals")
            meta["partial_extraction"] = True

        # Column misread detection
        col_issues = detect_column_misread(items)
        if col_issues:
            meta["extraction_issues"].extend(col_issues)
            if meta["extraction_confidence"] == "high":
                meta["extraction_confidence"] = "medium"

        # Subtotal consistency
        items_sum = round(sum(float(it.get("total", 0) or 0) for it in items), 2)
        subtotal = float(extracted_data.get("subtotal", 0) or 0)
        if items_sum > 0 and subtotal > 0:
            diff_pct = abs(items_sum - subtotal) / subtotal
            if diff_pct > 0.20:
                meta["extraction_issues"].append(f"items sum (${items_sum:.2f}) differs from subtotal (${subtotal:.2f}) by {diff_pct*100:.0f}%")
                if meta["extraction_confidence"] == "high":
                    meta["extraction_confidence"] = "medium"

    # Missing header data
    if not (extracted_data.get("supplier_name") or "").strip():
        meta["extraction_issues"].append("supplier name not detected")
    if not (extracted_data.get("invoice_date") or "").strip():
        meta["extraction_issues"].append("invoice date not detected")
    if not (extracted_data.get("invoice_number") or "").strip():
        meta["extraction_issues"].append("invoice number not detected")

    return meta


def salvage_partial_extraction(raw_response: str) -> dict:
    """
    When JSON parsing fails entirely, try to salvage partial data
    from the raw GPT response using regex.
    Returns a best-effort dict (may be mostly empty).
    """
    result = {"items": [], "_salvaged": True}

    # Try individual JSON fields
    for field, pattern in [
        ("supplier_name", r'"supplier_name"\s*:\s*"([^"]*)"'),
        ("invoice_number", r'"invoice_number"\s*:\s*"([^"]*)"'),
        ("invoice_date", r'"invoice_date"\s*:\s*"([^"]*)"'),
    ]:
        m = re.search(pattern, raw_response)
        if m:
            result[field] = m.group(1).strip()

    # Try to find a date anywhere
    if not result.get("invoice_date"):
        m = re.search(r'(\d{4}-\d{2}-\d{2})', raw_response)
        if m:
            result["invoice_date"] = m.group(1)

    # Try to extract items array even if outer JSON is broken
    items_match = re.search(r'"items"\s*:\s*\[([\s\S]*?)\]', raw_response)
    if items_match:
        try:
            items_json = "[" + items_match.group(1) + "]"
            items = json.loads(items_json)
            if isinstance(items, list):
                result["items"] = items
        except (json.JSONDecodeError, ValueError):
            pass

    # Try to find total
    for field, patterns in [
        ("total", [r'"total"\s*:\s*([0-9.]+)', r'total[:\s]+\$?([0-9,.]+)']),
        ("subtotal", [r'"subtotal"\s*:\s*([0-9.]+)']),
        ("tax", [r'"tax"\s*:\s*([0-9.]+)']),
    ]:
        for p in patterns:
            m = re.search(p, raw_response, re.IGNORECASE)
            if m:
                try:
                    result[field] = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
                break

    return result


# ---------------------------------------------------------------------------
# 7. Confidence & Validation Layer (Strict — Trust > Coverage)
# ---------------------------------------------------------------------------

def _item_name_looks_clear(name: str) -> bool:
    """Heuristic: does the item name look like a real product name, not garbled OCR?"""
    if not name or len(name.strip()) < 2:
        return False
    s = name.strip()
    alpha = sum(1 for c in s if c.isalpha())
    if alpha < len(s) * 0.3:
        return False
    tokens = s.split()
    if len(tokens) == 1 and len(s) > 40:
        return False
    return True


def _detect_suspicious_patterns(item: dict) -> list:
    """Detect suspicious patterns that should prevent trusted status."""
    flags = []
    qty = float(item.get("quantity", 0) or 0)
    up = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)
    tcw = item.get("total_case_weight")

    # Unrealistic pack sizes (case weight > 5000 LB or packs > 200)
    ppc = item.get("packs_per_case")
    if ppc is not None and ppc > 200:
        flags.append(f"unrealistic packs_per_case: {ppc}")
    if tcw is not None and tcw > 5000:
        flags.append(f"unrealistic case weight: {tcw}")

    # Defaulted/placeholder values
    if qty == 1 and up == 0 and total == 0:
        flags.append("likely defaulted values (qty=1, price=0, total=0)")
    if qty > 0 and up > 0 and qty == up:
        flags.append(f"qty equals unit_price ({qty}) — possible OCR misread")

    # Extremely high or low prices
    if up > 50000:
        flags.append(f"unit_price suspiciously high: ${up}")
    if total > 0 and up > 0 and up > total:
        flags.append("unit_price > total")

    return flags


def validate_and_score_item(item: dict) -> dict:
    """
    Strict validation and confidence scoring.
    Uses HARD GATES: any critical failure forces 'unverified' status.
    Trust > Coverage — conservative classification.

    Mutates and returns the item with:
      - valid_calc: bool
      - validation_errors: list[str]
      - confidence_score: int (0-100)
      - confidence_level: "trusted" | "unverified"
    """
    errors = []
    score = 0
    hard_fail = False  # Any hard fail → forced unverified

    raw_name = (item.get("raw_name") or "").strip()
    qty = float(item.get("quantity", 0) or 0)
    up = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)
    pack_status = item.get("pack_parse_status") or "not_applicable"
    pack_size_raw = item.get("pack_size_raw") or item.get("pack_size") or ""

    # ===== HARD GATE 1: Math validation (qty × price ≈ total) =====
    valid_calc = False
    if qty > 0 and up > 0 and total > 0:
        expected = round(qty * up, 2)
        tolerance = max(0.02, 0.01 * total)
        if abs(expected - total) <= tolerance:
            valid_calc = True
            score += 40
        else:
            hard_fail = True
            errors.append(f"MATH MISMATCH: qty({qty})×price(${up:.2f})=${expected:.2f} ≠ total(${total:.2f})")
    elif total > 0 and (qty == 0 or up == 0):
        hard_fail = True
        errors.append("total exists but qty or unit_price is missing/zero")
    elif qty > 0 and up > 0 and total == 0:
        hard_fail = True
        errors.append("qty and price exist but total is missing/zero")
    else:
        hard_fail = True
        errors.append("missing core numeric fields (qty, unit_price, total)")

    # ===== HARD GATE 2: Required fields =====
    missing = []
    if not raw_name:
        missing.append("item_name")
        hard_fail = True
    if qty <= 0:
        missing.append("qty")
    if up <= 0:
        missing.append("unit_price")
    if total <= 0:
        missing.append("line_total")
    if not missing:
        score += 20
    else:
        errors.append(f"missing: {', '.join(missing)}")

    # ===== HARD GATE 3: Pack size — if present, must parse or block trusted =====
    has_pack = bool(pack_size_raw.strip())
    if has_pack:
        if pack_status == "parsed":
            score += 20
        elif pack_status == "failed":
            # Pack size present but unparseable → cannot be trusted for price normalization
            hard_fail = True
            errors.append(f"pack_size parse failed: \"{pack_size_raw}\"")
    else:
        # No pack_size → fine, many items don't have one
        score += 15

    # ===== CHECK 4: Item name quality =====
    if _item_name_looks_clear(raw_name):
        score += 20
    else:
        errors.append("item name may be garbled or missing")

    # ===== CHECK 5: Suspicious patterns =====
    sus_flags = _detect_suspicious_patterns(item)
    if sus_flags:
        hard_fail = True
        for f in sus_flags:
            errors.append(f"SUSPICIOUS: {f}")

    # ===== Normalized price safety =====
    nplb = item.get("normalized_price_per_lb")
    if nplb is not None and nplb > 0:
        if pack_status != "parsed":
            errors.append("normalized price exists but pack_parse_status != parsed — cleared")
            item["normalized_price_per_lb"] = None
        else:
            pack_unit = (item.get("pack_unit") or "").upper()
            if pack_unit not in NORMALIZABLE_UNITS:
                errors.append(f"normalized price exists but unit '{pack_unit}' is not weight-based — cleared")
                item["normalized_price_per_lb"] = None

    # ===== Final classification: Trust > Coverage =====
    score = max(0, min(100, score))

    if hard_fail:
        level = "unverified"
    elif score >= 85:
        level = "trusted"
    else:
        level = "unverified"

    item["valid_calc"] = valid_calc
    item["validation_errors"] = errors
    item["confidence_score"] = score
    item["confidence_level"] = level

    # Human-readable primary reason
    if level == "trusted":
        item["confidence_reason"] = "All checks passed"
    elif not valid_calc and qty > 0 and up > 0 and total > 0:
        item["confidence_reason"] = "Math mismatch (qty × price ≠ total)"
    elif not raw_name:
        item["confidence_reason"] = "Missing item name"
    elif has_pack and pack_status == "failed":
        item["confidence_reason"] = "Pack size could not be parsed"
    elif sus_flags:
        item["confidence_reason"] = "Suspicious values detected"
    elif missing:
        item["confidence_reason"] = f"Missing fields: {', '.join(missing)}"
    else:
        item["confidence_reason"] = "Needs review"

    # Explicit review markers for "save now, review later"
    item["needs_review"] = level != "trusted"
    item["review_reason"] = item["confidence_reason"] if level != "trusted" else None

    return item


def validate_purchase_items(items: list) -> list:
    """
    Cross-item validation: detect suspicious patterns across all items in a purchase.
    Call AFTER individual validate_and_score_item on each item.
    """
    if len(items) < 2:
        return items

    # Detect repeated identical values across rows
    prices = [float(it.get("unit_price", 0) or 0) for it in items]
    totals = [float(it.get("total", 0) or 0) for it in items]
    names = [(it.get("raw_name") or "").strip().upper() for it in items]

    # Check for duplicate rows (same name + same price + same total)
    seen = set()
    for idx, it in enumerate(items):
        key = (names[idx], prices[idx], totals[idx])
        if key in seen and names[idx]:
            if "SUSPICIOUS: duplicate row" not in (it.get("validation_errors") or []):
                it.setdefault("validation_errors", []).append("SUSPICIOUS: duplicate row (same name, price, total)")
                it["confidence_level"] = "unverified"
        seen.add(key)

    # Check if ALL prices are identical (unlikely in real invoices with >3 items)
    nonzero_prices = [p for p in prices if p > 0]
    if len(nonzero_prices) >= 4 and len(set(nonzero_prices)) == 1:
        for it in items:
            if float(it.get("unit_price", 0) or 0) > 0:
                if "SUSPICIOUS: all items have identical price" not in (it.get("validation_errors") or []):
                    it.setdefault("validation_errors", []).append("SUSPICIOUS: all items have identical price")
                    it["confidence_level"] = "unverified"

    return items



def compute_review_status(items: list) -> str:
    """
    Compute invoice-level review status from item validation signals.
    Returns: "clean" | "warning" | "error"
    - clean:   no items need review
    - warning: some items need review (minor issues)
    - error:   items have hard errors (math mismatch, missing name, suspicious)
    """
    has_warning = False
    has_error = False
    for item in items:
        if not item.get("needs_review"):
            continue
        errors = item.get("validation_errors", [])
        reason = (item.get("review_reason") or "").lower()
        is_hard = any(
            "math mismatch" in e.lower() or "suspicious" in e.lower() or "item_name" in e.lower()
            for e in errors
        ) or "math mismatch" in reason or "missing item name" in reason or "suspicious" in reason
        if is_hard:
            has_error = True
        else:
            has_warning = True
    if has_error:
        return "error"
    if has_warning:
        return "warning"
    return "clean"
