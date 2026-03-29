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
# 5. Pack Size Parsing & Normalization
# ---------------------------------------------------------------------------

# Weight-based units (can compute $/LB)
WEIGHT_UNITS = {"LB", "LBS", "KG", "OZ", "G", "GM", "GR", "GRAM", "GRAMS"}
# Volume-based (can compute $/GAL etc but not $/LB)
VOLUME_UNITS = {"GAL", "GALLON", "QT", "QUART", "L", "LITER", "ML", "FL OZ", "PT", "PINT"}
# Count-based (no weight normalization)
COUNT_UNITS = {"EA", "EACH", "CT", "COUNT", "PK", "PACK", "BX", "BOX", "CS", "CASE", "BG", "BAG", "DZ", "DOZEN"}

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

# Conversion to LB for normalization
TO_LB = {
    "LB": 1.0,
    "KG": 2.20462,
    "OZ": 0.0625,
    "G": 0.00220462,
}


def _canonicalize_unit(raw: str) -> str:
    """Normalize unit string to canonical form."""
    u = raw.strip().upper().rstrip(".")
    return UNIT_CANONICAL.get(u, u)


def parse_pack_size(raw: str) -> dict:
    """
    Parse a pack size string into structured components.

    Supported formats:
        "10/4 LB"       → 10 packs × 4 LB = 40 LB
        "6/5 LB"        → 6 × 5 = 30 LB
        "2/17.5 LB"     → 2 × 17.5 = 35 LB
        "BAG 50 LB"     → 1 × 50 = 50 LB
        "150 EA"         → 150 EA (count-based)
        "1 GAL"          → 1 GAL
        "4/10 LB"        → 4 × 10 = 40 LB
        "12/1 QT"        → 12 × 1 QT
        "1/25 LB"        → 1 × 25 = 25 LB
        "50 LB"          → 1 × 50 = 50 LB
        "10#"            → 1 × 10 = 10 LB
        "2.5 GA"         → 1 × 2.5 GAL
        "4/5LB"          → 4 × 5 = 20 LB (no space)
        "20/10 LB"       → 20 × 10 = 200 LB

    Returns dict with:
        pack_size_raw, packs_per_case, weight_per_pack, unit,
        total_case_weight, is_weight_based, normalized_to_lb
    """
    result = {
        "pack_size_raw": (raw or "").strip(),
        "packs_per_case": 0,
        "weight_per_pack": 0,
        "unit": "",
        "total_case_weight": 0,
        "is_weight_based": False,
        "normalized_to_lb": 0,
    }

    text = (raw or "").strip().upper()
    if not text:
        return result

    # --- Pattern 1: "N/N UNIT" or "N/NUNIT" (e.g., "10/4 LB", "4/5LB", "2/17.5 LB") ---
    m = re.match(
        r"^(\d+)\s*/\s*(\d+\.?\d*)\s*([A-Z#]+\.?)$",
        text
    )
    if m:
        result["packs_per_case"] = int(m.group(1))
        result["weight_per_pack"] = float(m.group(2))
        result["unit"] = _canonicalize_unit(m.group(3))
        result["total_case_weight"] = round(
            result["packs_per_case"] * result["weight_per_pack"], 4
        )
        result["is_weight_based"] = result["unit"] in WEIGHT_UNITS
        return result

    # --- Pattern 2: "WORD N UNIT" (e.g., "BAG 50 LB", "CS 10 LB") ---
    m = re.match(
        r"^([A-Z]+)\s+(\d+\.?\d*)\s*([A-Z#]+\.?)$",
        text
    )
    if m:
        result["packs_per_case"] = 1
        result["weight_per_pack"] = float(m.group(2))
        result["unit"] = _canonicalize_unit(m.group(3))
        result["total_case_weight"] = result["weight_per_pack"]
        result["is_weight_based"] = result["unit"] in WEIGHT_UNITS
        return result

    # --- Pattern 3: "N UNIT" (e.g., "50 LB", "150 EA", "1 GAL", "2.5 GA") ---
    m = re.match(
        r"^(\d+\.?\d*)\s*([A-Z#]+\.?)$",
        text
    )
    if m:
        result["packs_per_case"] = 1
        result["weight_per_pack"] = float(m.group(1))
        result["unit"] = _canonicalize_unit(m.group(2))
        result["total_case_weight"] = result["weight_per_pack"]
        result["is_weight_based"] = result["unit"] in WEIGHT_UNITS
        return result

    # --- Pattern 4: "N#" (e.g., "10#" = 10 LB) ---
    m = re.match(r"^(\d+\.?\d*)#$", text)
    if m:
        result["packs_per_case"] = 1
        result["weight_per_pack"] = float(m.group(1))
        result["unit"] = "LB"
        result["total_case_weight"] = result["weight_per_pack"]
        result["is_weight_based"] = True
        return result

    # --- Pattern 5: "N/N" without unit (assume CS/EA) ---
    m = re.match(r"^(\d+)\s*/\s*(\d+\.?\d*)$", text)
    if m:
        result["packs_per_case"] = int(m.group(1))
        result["weight_per_pack"] = float(m.group(2))
        result["unit"] = "EA"
        result["total_case_weight"] = round(
            result["packs_per_case"] * result["weight_per_pack"], 4
        )
        result["is_weight_based"] = False
        return result

    # Could not parse — return raw only
    logger.debug(f"Could not parse pack size: '{raw}'")
    return result


def enrich_item_with_pack_size(item: dict) -> dict:
    """
    Given a line item dict, parse its pack_size field and compute
    normalized pricing. Mutates and returns the item.
    """
    pack_size_raw = (item.get("pack_size") or item.get("pack_size_raw") or "").strip()
    parsed = parse_pack_size(pack_size_raw)

    item["pack_size_raw"] = parsed["pack_size_raw"]
    item["packs_per_case"] = parsed["packs_per_case"]
    item["weight_per_pack"] = parsed["weight_per_pack"]
    item["pack_unit"] = parsed["unit"]
    item["total_case_weight"] = parsed["total_case_weight"]
    item["is_weight_based"] = parsed["is_weight_based"]

    # Compute normalized $/LB
    unit_price = float(item.get("unit_price", 0) or 0)
    case_weight = parsed["total_case_weight"]

    if parsed["is_weight_based"] and case_weight > 0 and unit_price > 0:
        # Convert to LB if needed
        lb_factor = TO_LB.get(parsed["unit"], 0)
        if lb_factor > 0:
            total_lb = case_weight * lb_factor
            item["normalized_price_per_lb"] = round(unit_price / total_lb, 4)
        else:
            item["normalized_price_per_lb"] = 0
    else:
        item["normalized_price_per_lb"] = 0

    return item
