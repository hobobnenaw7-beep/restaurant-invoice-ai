"""
Unit Normalization Layer for Invoice Items.

Converts all items into a consistent unit (lb or piece) and calculates price_per_unit.
Runs after extraction, before saving data.

Canonical units: lb, piece, oz, gal
All weight-based items normalize to lb. All count-based to piece.
Gallon items convert to lb via approximate density.

Product Memory Integration:
  Before parsing, check unit_memory (DB) by vendor + product_code.
  If a saved mapping exists, reuse it for cross-invoice consistency.
  After successful normalization, save the mapping for future reuse.

Pack size patterns (Sysco):
- "40 LB" → 40 lb per case
- "4/5 LB" → 4 bags × 5 lb = 20 lb per case
- "150LB" → 150 lb per case
- "1/22 LB" → 1 × 22 lb = 22 lb per case
- "4/1GAL" → 4 gallons per case (convert gal → lb using product-specific density)
- "CS1000 EA" → 1000 pieces per case
- "25 EA" → 25 pieces per case

US Foods / PFG patterns:
- "40 LB CS", "20 LB BAG" → weight + container suffix
- "6 CT", "2/24 CT" → piece count
- "6/4 OZ" → fraction ounce portions

Rules:
1. All weight-based items normalize to LB
2. All count-based items normalize to PIECE
3. Ambiguous items get unit_status = "review"
4. Fees/surcharges are excluded from normalization
"""
import re
import logging

logger = logging.getLogger("restaurant_ai")


# ─────────────────────────────────────────────────────────────────────
# Canonical Unit Constants
# ─────────────────────────────────────────────────────────────────────

CANONICAL_UNITS = ("lb", "piece", "oz", "gal")

# Maps internal unit_type → canonical_unit
_UNIT_TYPE_TO_CANONICAL = {
    "lb": "lb",
    "piece": "piece",
    "gallon": "gal",
}


# ─────────────────────────────────────────────────────────────────────
# Unit Memory — DB-backed cross-invoice persistence
# ─────────────────────────────────────────────────────────────────────

def _normalize_vendor_key(vendor: str) -> str:
    """Normalize vendor name for memory key."""
    if not vendor:
        return ""
    v = vendor.strip().upper()
    if "SYSCO" in v:
        return "SYSCO"
    if "US FOOD" in v or "USFOODS" in v:
        return "USFOODS"
    if "PERFORMANCE" in v or "PFG" in v:
        return "PFG"
    return re.sub(r'[^A-Z0-9]', '', v)[:20]


def _clean_code(code: str) -> str:
    """Extract digits from product code, min 4."""
    if not code:
        return ""
    digits = re.sub(r'[^0-9]', '', code)
    return digits if len(digits) >= 4 else ""


async def lookup_unit_memory(vendor: str, product_code: str, restaurant_id: str) -> dict:
    """
    Check unit_memory for a saved mapping by vendor + product_code.
    Returns the mapping dict or empty dict.
    """
    from core.database import db

    vk = _normalize_vendor_key(vendor)
    code = _clean_code(product_code)
    if not vk or not code:
        return {}

    doc = await db.unit_memory.find_one(
        {"vendor_key": vk, "product_code": code, "restaurant_id": restaurant_id},
        {"_id": 0},
    )
    if doc:
        logger.info(
            f"Unit memory HIT: {vk}:{code} → canonical_unit={doc.get('canonical_unit')}, "
            f"multiplier={doc.get('multiplier')}, pack={doc.get('pack_size')}"
        )
    return doc or {}


async def save_unit_memory(
    vendor: str,
    product_code: str,
    restaurant_id: str,
    canonical_unit: str,
    multiplier: float,
    pack_size: str,
    parse_method: str,
):
    """
    Save or update a unit mapping in unit_memory.
    Only saves for items with a valid product_code.
    """
    from core.database import db
    from datetime import datetime, timezone

    vk = _normalize_vendor_key(vendor)
    code = _clean_code(product_code)
    if not vk or not code or not canonical_unit:
        return

    now = datetime.now(timezone.utc).isoformat()
    await db.unit_memory.update_one(
        {"vendor_key": vk, "product_code": code, "restaurant_id": restaurant_id},
        {"$set": {
            "vendor_key": vk,
            "product_code": code,
            "restaurant_id": restaurant_id,
            "canonical_unit": canonical_unit,
            "multiplier": multiplier,
            "pack_size": pack_size,
            "parse_method": parse_method,
            "updated_at": now,
        }, "$inc": {"times_used": 1}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logger.debug(
        f"Unit memory SAVE: {vk}:{code} → {canonical_unit}, multiplier={multiplier}"
    )

# ── Regex patterns for parsing pack_size ──

# "40 LB", "150LB", "85LBS", "150#", "25/#", "12.0LB"
_SIMPLE_LB = re.compile(
    r'^(\d+(?:\.\d+)?)\s*(?:LBS?|#|POUND)$', re.IGNORECASE
)

# "4/5 LB", "2/10 LB", "1/22 LB", "8/5#", "12/1#", "2X1#"
_FRACTION_LB = re.compile(
    r'^(\d+)\s*[/X]\s*(\d+(?:\.\d+)?)\s*(?:LBS?|#|POUND)$', re.IGNORECASE
)

# "CS 40.0 LB", "CS 150 LB", "CS 12.0 LB", "1 CS 120 LB", "2 CS 120 LB"
_CS_LB = re.compile(
    r'^(?:(\d+)\s*)?CS\s+(\d+(?:\.\d+)?)\s*(?:LBS?|#)$', re.IGNORECASE
)

# "1 CS 150/8X8X3" → 150 count containers
_CS_COUNT = re.compile(
    r'^(?:(\d+)\s*)?CS\s*(\d+)\s*/\s*\d+', re.IGNORECASE
)

# "4/1GAL", "4 GAL", "4/1 GAL", "1GAL", "41GAL"
_GAL = re.compile(
    r'^(\d+)\s*[/X]?\s*(\d*)\s*GAL', re.IGNORECASE
)

# "CS1000 EA", "25 EA", "1 EA", "CS1000"
_EA = re.compile(
    r'^(?:CS)?(\d+)\s*(?:EA|CT|COUNT|PCS?)?\s*$', re.IGNORECASE
)

# Container dimensions like "1508X8X3", "150X8X3NSYS", "1509X9X2"
# Sysco format: count + dimensions (e.g., "150 8X8X3" = 150 containers of 8×8×3 inches)
# OCR often squashes the space: "1508X8X3" → need to separate count from dimension
_CONTAINER_DIM = re.compile(
    r'^(?:CS\s*)?(\d{2,4})\s*[X×]\s*(\d+)\s*[X×]\s*(\d+)', re.IGNORECASE
)

# "120-4.5#" → count × weight
_COUNT_WEIGHT = re.compile(
    r'^(\d+)\s*[-]\s*(\d+(?:\.\d+)?)\s*#$', re.IGNORECASE
)

# "25/#" → 25 lb (# = pounds)
_SIMPLE_HASH = re.compile(
    r'^(\d+)\s*/?\s*#$', re.IGNORECASE
)

# "41GAL" → OCR misread of "410LB" or "41.0LB" (O→0 substitution)
_OCR_LB = re.compile(
    r'^(\d+)[O](\d*)(?:LBS?|#)$', re.IGNORECASE
)

# Ounce patterns: "1224 OZ", "1232OZ", "12/24 OZ", "12/24OZ"
_FRACTION_OZ = re.compile(
    r'^(\d+)\s*[/]?\s*(\d+)\s*OZ$', re.IGNORECASE
)
_SIMPLE_OZ = re.compile(
    r'^(\d+(?:\.\d+)?)\s*OZ$', re.IGNORECASE
)

# "150/CS" → 150 pieces per case
_COUNT_CS = re.compile(
    r'^(\d+)\s*/\s*CS$', re.IGNORECASE
)

# "1 CS1000 EA" → 1000 pieces
_N_CS_COUNT_EA = re.compile(
    r'^(\d+)\s*CS\s*(\d+)\s*(?:EA|CT)?$', re.IGNORECASE
)

# "2 CS 1509X9X3NSYS" or "2 CS 150X9X9X2 SYS" → container dim with CS prefix
_N_CS_DIM = re.compile(
    r'^(\d+)\s*CS\s+(\d{2,4})\s*[X×/]', re.IGNORECASE
)

# "CS 1508X8X3NSYS" or "CS 1509X9X3 SYS" or "CS 1509X9X3" → container dims
_CS_DIM = re.compile(
    r'^CS\s+(\d{2,4})\s*[X×]', re.IGNORECASE
)

# "3 CS 1500CT" → count-based
_N_CS_CT = re.compile(
    r'^(\d+)\s*CS\s+(\d+)\s*CT$', re.IGNORECASE
)

# "8/1.5" → 8 × 1.5 lb = 12 lb (fractional without unit = assume lb)
_FRACTION_BARE = re.compile(
    r'^(\d+)\s*/\s*(\d+(?:\.\d+))$', re.IGNORECASE
)

# "CS10007 GM" or "CS1007 GM" → count + grams
_CS_GM = re.compile(
    r'^CS\s*(\d+)\s*(?:/?\s*\d+\s*)?GM$', re.IGNORECASE
)

# "CS-150..." → OCR-damaged container packs, extract leading count
_CS_DASH = re.compile(
    r'^CS\s*[-]\s*(\d+)', re.IGNORECASE
)

# Common liquid → lb conversion (approximate, by product category)
_GAL_TO_LB = 8.34  # water baseline; sauces ~8.5-9, oils ~7.5

# ── US Foods / PFG additional patterns ──

# "40 LB CS", "20 LB BAG", "50 LB BX" — weight + container suffix
_LB_CONTAINER = re.compile(
    r'^(\d+(?:\.\d+)?)\s*(?:LBS?|#)\s*(?:CS|CASE|BX|BOX|BAG|PKG|PK|CTN)$', re.IGNORECASE
)

# "2/5 LB BAG", "4/10 LB CS", "6/2 LB PKG"
_FRAC_LB_CONTAINER = re.compile(
    r'^(\d+)\s*[/X]\s*(\d+(?:\.\d+)?)\s*(?:LBS?|#)\s*(?:CS|CASE|BX|BOX|BAG|PKG|PK|CTN)?$', re.IGNORECASE
)

# "6 CT", "12 CT", "24 CT", "48 CT" — count-based (pieces per case)
_CT = re.compile(
    r'^(\d+)\s*(?:CT|COUNT|PCS?|PC)$', re.IGNORECASE
)

# "1/50 CT", "2/24 CT" — fraction count
_FRAC_CT = re.compile(
    r'^(\d+)\s*[/X]\s*(\d+)\s*(?:CT|COUNT|PCS?)$', re.IGNORECASE
)

# "4 OZ", "8 OZ", "16 OZ" — single ounce (common for US Foods portioned items)
_PORTION_OZ = re.compile(
    r'^(\d+(?:\.\d+)?)\s*OZ$', re.IGNORECASE
)

# "6/4 OZ", "12/8 OZ" — fraction ounce portions
_FRAC_PORTION_OZ = re.compile(
    r'^(\d+)\s*[/X]\s*(\d+(?:\.\d+)?)\s*OZ$', re.IGNORECASE
)


def parse_pack_size(pack_str: str) -> dict:
    """
    Parse a pack_size string into normalized weight/count.

    Returns:
        {
            "parsed": True/False,
            "total_weight_lb": float or None,
            "total_pieces": int or None,
            "unit_type": "lb" | "piece" | "gallon" | None,
            "parse_method": str,
            "raw": str,
        }
    """
    raw = (pack_str or "").strip()
    if not raw:
        return {"parsed": False, "unit_type": None, "raw": raw, "parse_method": "empty"}

    cleaned = raw.upper().strip()

    # Remove trailing SYS/NSYS noise
    cleaned = re.sub(r'\s*(N?SYS)\s*$', '', cleaned)

    # OCR correction: "4/0#" → "4/10#", "12/0 LB" → "12/10 LB" (0 is OCR-damaged 10)
    cleaned = re.sub(r'^(\d+)\s*/\s*0\s*(#|LBS?)$', r'\g<1>/10\2', cleaned)

    # ── Strip "CS" prefix for Sysco packs: "CS 410 LB" → "410 LB" ──
    # Sysco wraps pack sizes in "CS ..." — remove it so patterns match the core value.
    _cs_prefix_stripped = False
    cs_prefix_match = re.match(r'^(?:CS\s+)(.+)$', cleaned)
    if cs_prefix_match:
        inner = cs_prefix_match.group(1).strip()
        # Only strip if inner looks like a weight/count pattern (not "CS1000" which is count-based)
        if re.match(r'^\d+.*(?:LB|#|OZ|GAL|EA|CT)', inner, re.IGNORECASE):
            cleaned = inner
            _cs_prefix_stripped = True

    # ── Sysco concatenated fraction: "410LB" → "4/10 LB" ──
    # When OCR drops the slash: "410LB" should be "4/10LB" (4 bags × 10 lb = 40 lb)
    _CONCAT_FRAC = re.compile(r'^(\d)(\d{2,3})\s*(LBS?|#|POUND)$', re.IGNORECASE)
    m_concat = _CONCAT_FRAC.match(cleaned)
    if m_concat:
        prefix = int(m_concat.group(1))
        suffix = int(m_concat.group(2))
        unit_str = m_concat.group(3)
        # Only split when prefix is clearly a bag count (2-9).
        # prefix=1 is ambiguous: "120LB" is 120 lb, not 1×20 lb.
        if 2 <= prefix <= 9 and 5 <= suffix <= 30:
            cleaned = f"{prefix}/{suffix}{unit_str}"
            logger.debug(f"Pack size OCR fix: '{raw}' → '{cleaned}' (concatenated fraction)")

    # ── Fraction LB: "4/5 LB", "2/10 LB", "8/5#" — check BEFORE simple LB ──
    m = _FRACTION_LB.match(cleaned)
    if m:
        count = int(m.group(1))
        weight = float(m.group(2))
        total_lb = count * weight
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "fraction_lb", "raw": raw}

    # ── Simple LB: "40 LB", "150LB", "85LBS", "150#" ──
    m = _SIMPLE_LB.match(cleaned)
    if m:
        lb = float(m.group(1))
        return {"parsed": True, "total_weight_lb": lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "simple_lb", "raw": raw}

    # ── CS + LB: "CS 40.0 LB", "2 CS 120 LB" ──
    m = _CS_LB.match(cleaned)
    if m:
        cs_count = int(m.group(1) or 1)
        lb = float(m.group(2))
        total_lb = cs_count * lb
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "cs_lb", "raw": raw}

    # ── Count-weight: "120-4.5#" ──
    m = _COUNT_WEIGHT.match(cleaned)
    if m:
        count = int(m.group(1))
        weight = float(m.group(2))
        total_lb = count * weight
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": count,
                "unit_type": "lb", "parse_method": "count_weight", "raw": raw}

    # ── OCR misread LB: "41OLB" → 410 lb ──
    m = _OCR_LB.match(cleaned)
    if m:
        part1 = m.group(1)
        part2 = m.group(2) or "0"
        lb = float(part1 + part2)
        return {"parsed": True, "total_weight_lb": lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "ocr_lb", "raw": raw}

    # ── Simple hash: "25/#" → 25 lb ──
    m = _SIMPLE_HASH.match(cleaned)
    if m:
        lb = float(m.group(1))
        return {"parsed": True, "total_weight_lb": lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "simple_hash", "raw": raw}

    # ── Ounce patterns: "12/24 OZ", "1224 OZ", "1232OZ" ──
    # Sysco: "12/24 OZ" = 12 × 24oz. OCR strips slash → "1224 OZ"
    # Try with explicit slash first
    oz_slash = re.match(r'^(\d+)\s*/\s*(\d+)\s*OZ$', cleaned, re.IGNORECASE)
    if oz_slash:
        count = int(oz_slash.group(1))
        oz_each = int(oz_slash.group(2))
        total_oz = count * oz_each
        total_lb = round(total_oz / 16, 2)
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "fraction_oz", "raw": raw}

    # No-slash: "1224 OZ" → split digits into count + oz
    oz_bare = re.match(r'^(\d{3,4})\s*OZ$', cleaned, re.IGNORECASE)
    if oz_bare:
        digits = oz_bare.group(1)
        mid = len(digits) // 2
        count = int(digits[:mid])
        oz_each = int(digits[mid:])
        if count > 0 and oz_each > 0:
            total_oz = count * oz_each
            total_lb = round(total_oz / 16, 2)
            return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                    "unit_type": "lb", "parse_method": "fraction_oz_split", "raw": raw}

    # Simple OZ: "24OZ", "16 OZ"
    oz_simple = re.match(r'^(\d{1,2})\s*OZ$', cleaned, re.IGNORECASE)
    if oz_simple:
        oz = float(oz_simple.group(1))
        total_lb = round(oz / 16, 2)
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "simple_oz", "raw": raw}

    # ── US Foods / PFG patterns ──

    # "40 LB CS", "20 LB BAG", "50 LB BX" — weight + container suffix
    m = _LB_CONTAINER.match(cleaned)
    if m:
        lb = float(m.group(1))
        return {"parsed": True, "total_weight_lb": lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "lb_container", "raw": raw}

    # "6 CT", "12 CT", "24 CT" — piece count
    m = _CT.match(cleaned)
    if m:
        count = int(m.group(1))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "ct_count", "raw": raw}

    # "1/50 CT", "2/24 CT" — fraction count
    m = _FRAC_CT.match(cleaned)
    if m:
        packs = int(m.group(1))
        per_pack = int(m.group(2))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": packs * per_pack,
                "unit_type": "piece", "parse_method": "frac_ct", "raw": raw}

    # "6/4 OZ", "12/8 OZ" — fraction ounce portions
    m = _FRAC_PORTION_OZ.match(cleaned)
    if m:
        packs = int(m.group(1))
        oz_each = float(m.group(2))
        total_lb = round(packs * oz_each / 16, 2)
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": packs,
                "unit_type": "lb", "parse_method": "frac_portion_oz", "raw": raw}

    # ── N CS + count EA: "1 CS1000 EA" → 1000 pcs ──
    m = _N_CS_COUNT_EA.match(cleaned)
    if m:
        cs_count = int(m.group(1))
        ea_count = int(m.group(2))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": cs_count * ea_count,
                "unit_type": "piece", "parse_method": "n_cs_count_ea", "raw": raw}

    # ── Count/CS: "150/CS" → 150 pieces ──
    m = _COUNT_CS.match(cleaned)
    if m:
        count = int(m.group(1))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "count_cs", "raw": raw}

    # ── N CS + container dims: "2 CS 1509X9X3NSYS" ──
    m = _N_CS_DIM.match(cleaned)
    if m:
        cs_count = int(m.group(1))
        leading = m.group(2)
        piece_count = int(leading)
        if len(leading) >= 4:
            last1 = int(leading[-1])
            if 0 <= last1 <= 12 and len(leading) > 1:
                candidate = int(leading[:-1])
                if 10 <= candidate <= 2000:
                    piece_count = candidate
        return {"parsed": True, "total_weight_lb": None, "total_pieces": cs_count * piece_count,
                "unit_type": "piece", "parse_method": "n_cs_dim", "raw": raw}

    # ── N CS + CT: "3 CS 1500CT" → 3 × 1500 ──
    m = _N_CS_CT.match(cleaned)
    if m:
        cs_count = int(m.group(1))
        ct = int(m.group(2))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": cs_count * ct,
                "unit_type": "piece", "parse_method": "n_cs_ct", "raw": raw}

    # ── CS + container dims: "CS 1508X8X3NSYS", "CS 1509X9X3" ──
    m = _CS_DIM.match(cleaned)
    if m:
        leading = m.group(1)
        count = int(leading)
        if len(leading) >= 4:
            last1 = int(leading[-1])
            if 0 <= last1 <= 12 and len(leading) > 1:
                candidate_count = int(leading[:-1])
                if 10 <= candidate_count <= 2000:
                    count = candidate_count
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "cs_dim", "raw": raw}

    # ── CS + GM: "CS10007 GM", "CS1007 GM" → count-based ──
    m = _CS_GM.match(cleaned)
    if m:
        count = int(m.group(1))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "cs_gm", "raw": raw}

    # ── CS-dash: "CS-150?23 X?5" → extract leading count ──
    m = _CS_DASH.match(cleaned)
    if m:
        count = int(m.group(1))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "cs_dash", "raw": raw}

    # ── Fraction bare: "8/1.5" → 8 × 1.5 lb ──
    m = _FRACTION_BARE.match(cleaned)
    if m:
        count = int(m.group(1))
        weight = float(m.group(2))
        total_lb = count * weight
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "lb", "parse_method": "fraction_bare", "raw": raw}

    # ── Gallon: "4/1GAL", "4 GAL", "1GAL" ──
    m = _GAL.match(cleaned)
    if m:
        outer = int(m.group(1) or 1)
        inner = int(m.group(2)) if m.group(2) else 1
        total_gal = outer * inner if inner > 0 else outer
        total_lb = round(total_gal * _GAL_TO_LB, 1)
        return {"parsed": True, "total_weight_lb": total_lb, "total_pieces": None,
                "unit_type": "gallon", "parse_method": "gallon",
                "total_gallons": total_gal, "raw": raw}

    # ── Container dimensions: "1508X8X3", "150X8X3NSYS" → piece count ──
    # Sysco: "150 8X8X3" = 150 containers, OCR squashes to "1508X8X3"
    # Strategy: the digits before the first X are "count + first_dim_digit" merged.
    # Container dims are small (2-12 inches), so we try splitting the leading number.
    m = _CONTAINER_DIM.match(cleaned)
    if m:
        leading = m.group(1)  # e.g., "1508" or "150" or "1500"
        dim2 = int(m.group(2))  # second dimension
        dim3 = int(m.group(3))  # third dimension

        # Try to infer where the count ends and the first dimension starts.
        # Container dimensions are single digits (2-12). Check if last 1-2 chars
        # of leading number form a valid dimension.
        count = int(leading)  # fallback: entire number is count (e.g., "150X8X3")
        if len(leading) >= 4:
            # Try last 1 char as dim: "1508" → count=150, dim1=8
            last1 = int(leading[-1])
            if 0 <= last1 <= 12 and len(leading) > 1:
                candidate_count = int(leading[:-1])
                # Sanity: container counts are typically 25-1000
                if 10 <= candidate_count <= 2000:
                    count = candidate_count

        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "container_dim", "raw": raw}

    # ── CS count: "CS1000 EA", "CS1000", "1 CS 150/8X8X3" ──
    m = _CS_COUNT.match(cleaned)
    if m:
        count = int(m.group(2))
        return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                "unit_type": "piece", "parse_method": "cs_count", "raw": raw}

    # ── Simple EA/count: "25 EA", "1 EA" ──
    m = _EA.match(cleaned)
    if m:
        count = int(m.group(1))
        if count > 0:
            return {"parsed": True, "total_weight_lb": None, "total_pieces": count,
                    "unit_type": "piece", "parse_method": "ea_count", "raw": raw}

    # ── Just a number: "1", "2", "4", "6" → ambiguous case count ──
    if re.match(r'^\d{1,2}$', cleaned):
        return {"parsed": False, "unit_type": None, "raw": raw,
                "parse_method": "bare_number_ambiguous"}

    # ── CS only: "CS" ──
    if cleaned == "CS":
        return {"parsed": False, "unit_type": None, "raw": raw,
                "parse_method": "cs_only_ambiguous"}

    return {"parsed": False, "unit_type": None, "raw": raw,
            "parse_method": "unrecognized"}


def _is_fee_item(raw_name: str) -> bool:
    """Check if item is a fee/surcharge (not a product)."""
    name = (raw_name or "").upper()
    fee_keywords = ("FUEL", "SURCHARGE", "FEE", "DELIVERY", "CHARGE", "MISC CHARGE")
    return any(kw in name for kw in fee_keywords)


def normalize_item(item: dict) -> dict:
    """
    Add normalized unit fields to an extracted item.

    Adds:
        - normalized_quantity: total weight in lb or total pieces
        - normalized_unit: "lb" | "piece" | "gallon" | None
        - price_per_unit: price per lb or per piece
        - unit_status: "normalized" | "review" | "excluded"
        - unit_parse_method: how pack_size was parsed
    """
    raw_name = (item.get("raw_name") or "").strip()
    pack_size = (item.get("pack_size") or "").strip()
    qty = float(item.get("quantity", 0) or 0)
    unit_price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)

    # Fees/surcharges: exclude from normalization
    if _is_fee_item(raw_name):
        item["normalized_quantity"] = None
        item["normalized_unit"] = None
        item["price_per_unit"] = None
        item["unit_status"] = "excluded"
        item["unit_parse_method"] = "fee_item"
        return item

    # Parse pack_size
    parsed = parse_pack_size(pack_size)

    if not parsed["parsed"]:
        # Could not parse → flag for review
        item["normalized_quantity"] = None
        item["normalized_unit"] = None
        item["price_per_unit"] = None
        item["unit_status"] = "review"
        item["unit_parse_method"] = parsed["parse_method"]
        return item

    # Calculate normalized quantity (qty × pack_weight or qty × pack_count)
    unit_type = parsed["unit_type"]

    if unit_type == "lb" and parsed.get("total_weight_lb"):
        weight_per_case = parsed["total_weight_lb"]
        norm_qty = round(qty * weight_per_case, 2) if qty > 0 else weight_per_case
        denominator = qty * weight_per_case if qty > 0 else weight_per_case
        ppu = round(total / denominator, 4) if denominator > 0 and total != 0 else None
        item["normalized_quantity"] = norm_qty
        item["normalized_unit"] = "lb"
        item["canonical_unit"] = "lb"
        item["normalization_multiplier"] = weight_per_case
        item["price_per_unit"] = ppu
        item["unit_status"] = "normalized"
        item["unit_parse_method"] = parsed["parse_method"]
        item["_pack_weight_lb"] = weight_per_case

    elif unit_type == "gallon" and parsed.get("total_weight_lb"):
        weight_per_case = parsed["total_weight_lb"]
        norm_qty = round(qty * weight_per_case, 2) if qty > 0 else weight_per_case
        denominator = qty * weight_per_case if qty > 0 else weight_per_case
        ppu = round(total / denominator, 4) if denominator > 0 and total != 0 else None
        item["normalized_quantity"] = norm_qty
        item["normalized_unit"] = "lb"
        item["canonical_unit"] = "gal"
        item["normalization_multiplier"] = weight_per_case
        item["price_per_unit"] = ppu
        item["unit_status"] = "normalized"
        item["unit_parse_method"] = parsed["parse_method"]
        item["_pack_weight_lb"] = weight_per_case
        item["_pack_gallons"] = parsed.get("total_gallons")

    elif unit_type == "piece" and parsed.get("total_pieces"):
        pieces_per_case = parsed["total_pieces"]
        norm_qty = round(qty * pieces_per_case, 2) if qty > 0 else float(pieces_per_case)
        denominator = qty * pieces_per_case if qty > 0 else float(pieces_per_case)
        ppu = round(total / denominator, 4) if denominator > 0 and total != 0 else None
        item["normalized_quantity"] = norm_qty
        item["normalized_unit"] = "piece"
        item["canonical_unit"] = "piece"
        item["normalization_multiplier"] = float(pieces_per_case)
        item["price_per_unit"] = ppu
        item["unit_status"] = "normalized"
        item["unit_parse_method"] = parsed["parse_method"]
        item["_pack_pieces"] = pieces_per_case

    else:
        item["normalized_quantity"] = None
        item["normalized_unit"] = None
        item["price_per_unit"] = None
        item["unit_status"] = "review"
        item["unit_parse_method"] = parsed["parse_method"]

    return item


async def normalize_item_with_memory(item: dict, vendor: str = "", restaurant_id: str = "") -> dict:
    """
    Normalize item with Product Memory integration.

    Priority:
      1. Check unit_memory by vendor + product_code → reuse if found
      2. Parse pack_size and calculate normally
      3. Save successful mapping to unit_memory for future reuse

    This ensures the same product is ALWAYS normalized identically
    across different invoices.
    """
    raw_name = (item.get("raw_name") or "").strip()
    pack_size = (item.get("pack_size") or "").strip()
    item_code = (item.get("item_code") or "").strip()
    qty = float(item.get("quantity", 0) or 0)
    total = float(item.get("total", 0) or 0)

    # Skip fees
    if _is_fee_item(raw_name):
        normalize_item(item)
        return item

    # ── Step 1: Check unit_memory ──
    memory = await lookup_unit_memory(vendor, item_code, restaurant_id)
    if memory:
        multiplier = memory.get("multiplier", 0)
        canonical_unit = memory.get("canonical_unit", "")
        if multiplier > 0 and canonical_unit:
            norm_qty = round(qty * multiplier, 2) if qty > 0 else multiplier
            denominator = qty * multiplier if qty > 0 else multiplier
            ppu = round(total / denominator, 4) if denominator > 0 and total != 0 else None
            item["normalized_quantity"] = norm_qty
            item["normalized_unit"] = canonical_unit if canonical_unit != "gal" else "lb"
            item["canonical_unit"] = canonical_unit
            item["normalization_multiplier"] = multiplier
            item["price_per_unit"] = ppu
            item["unit_status"] = "normalized"
            item["unit_parse_method"] = f"memory:{memory.get('parse_method', '?')}"
            item["_unit_source"] = "memory"
            return item

    # ── Step 2: Normal parse ──
    normalize_item(item)

    # ── Step 3: Save to memory if successful ──
    if item.get("unit_status") == "normalized" and item_code:
        canonical_unit = item.get("canonical_unit", "")
        multiplier = item.get("normalization_multiplier", 0)
        if canonical_unit and multiplier > 0:
            await save_unit_memory(
                vendor=vendor,
                product_code=item_code,
                restaurant_id=restaurant_id,
                canonical_unit=canonical_unit,
                multiplier=multiplier,
                pack_size=pack_size,
                parse_method=item.get("unit_parse_method", ""),
            )
            item["_unit_source"] = "parsed_and_saved"

    return item


async def normalize_items_with_memory(items: list, vendor: str = "", restaurant_id: str = "") -> dict:
    """
    Normalize all items with Product Memory integration.
    Returns stats about normalization.
    """
    stats = {
        "total": 0,
        "normalized_lb": 0,
        "normalized_piece": 0,
        "review": 0,
        "excluded": 0,
        "memory_hits": 0,
        "memory_saves": 0,
        "parse_methods": {},
    }

    for it in items:
        if it.get("confidence_level") == "excluded":
            continue
        if it.get("row_type") not in ("line_item", "fee", None):
            continue

        stats["total"] += 1
        await normalize_item_with_memory(it, vendor=vendor, restaurant_id=restaurant_id)

        status = it.get("unit_status", "review")
        unit = it.get("normalized_unit")
        source = it.get("_unit_source", "")

        if status == "normalized" and unit == "lb":
            stats["normalized_lb"] += 1
        elif status == "normalized" and unit == "piece":
            stats["normalized_piece"] += 1
        elif status == "excluded":
            stats["excluded"] += 1
        else:
            stats["review"] += 1

        if source == "memory":
            stats["memory_hits"] += 1
        elif source == "parsed_and_saved":
            stats["memory_saves"] += 1

        method = it.get("unit_parse_method", "unknown")
        stats["parse_methods"][method] = stats["parse_methods"].get(method, 0) + 1

    total_normalizable = stats["total"] - stats["excluded"]
    stats["normalization_rate"] = (
        round((stats["normalized_lb"] + stats["normalized_piece"]) / total_normalizable, 4)
        if total_normalizable > 0 else 0
    )

    return stats
    """
    Normalize all items in an extraction result.
    Returns stats about normalization.
    """
    stats = {
        "total": 0,
        "normalized_lb": 0,
        "normalized_piece": 0,
        "review": 0,
        "excluded": 0,
        "parse_methods": {},
    }

    for it in items:
        if it.get("confidence_level") == "excluded":
            continue
        if it.get("row_type") not in ("line_item", "fee", None):
            continue

        stats["total"] += 1
        normalize_item(it)

        status = it.get("unit_status", "review")
        unit = it.get("normalized_unit")

        if status == "normalized" and unit == "lb":
            stats["normalized_lb"] += 1
        elif status == "normalized" and unit == "piece":
            stats["normalized_piece"] += 1
        elif status == "excluded":
            stats["excluded"] += 1
        else:
            stats["review"] += 1

        method = it.get("unit_parse_method", "unknown")
        stats["parse_methods"][method] = stats["parse_methods"].get(method, 0) + 1

    total_normalizable = stats["total"] - stats["excluded"]
    stats["normalization_rate"] = (
        round((stats["normalized_lb"] + stats["normalized_piece"]) / total_normalizable, 4)
        if total_normalizable > 0 else 0
    )

    return stats
