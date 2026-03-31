"""
Normalization Layer — services/normalization.py

Pure functions. No DB calls. No side effects.
Pipeline position: Extraction → NORMALIZATION → Validation → Save

Two tiers:
  clean_name  — conservative: uppercase, whitespace, separator standardization (preserves all meaning)
  base_name   — aggressive: specs + embedded weight stripped (for broad matching only)

Match keys use token normalization (abbreviations, singular/plural) for stability.
"""

import re
from preprocessing import UNIT_CANONICAL

# ─── Token normalization: common food-industry abbreviations ───
ABBREVIATION_MAP = {
    "BNLS": "BONELESS",
    "BNLESS": "BONELESS",
    "BNL": "BONELESS",
    "HDLS": "HEADLESS",
    "HDLESS": "HEADLESS",
    "HDL": "HEADLESS",
    "SKLS": "SKINLESS",
    "SKLSS": "SKINLESS",
    "SKN": "SKIN",
    "SKNLS": "SKINLESS",
    "CTN": "CARTON",
    "CTNS": "CARTON",
    "FRZ": "FROZEN",
    "FRZN": "FROZEN",
    "FRH": "FRESH",
    "FRSH": "FRESH",
    "GRN": "GREEN",
    "GRD": "GROUND",
    "GRND": "GROUND",
    "BRST": "BREAST",
    "BRSTS": "BREAST",
    "THGH": "THIGH",
    "THGHS": "THIGH",
    "WHL": "WHOLE",
    "SML": "SMALL",
    "MED": "MEDIUM",
    "LRG": "LARGE",
    "XLG": "EXTRA LARGE",
    "XLRG": "EXTRA LARGE",
    "ORG": "ORGANIC",
    "ORGN": "ORGANIC",
    "ORGNC": "ORGANIC",
    "NAT": "NATURAL",
    "NTRL": "NATURAL",
    "PREM": "PREMIUM",
    "IMP": "IMPORTED",
    "DOM": "DOMESTIC",
    "UNSLTD": "UNSALTED",
    "SLTD": "SALTED",
    "XVRGN": "EXTRA VIRGIN",
    "XVIRGIN": "EXTRA VIRGIN",
    "VEG": "VEGETABLE",
    "VEGS": "VEGETABLE",
    "YLW": "YELLOW",
    "WHT": "WHITE",
    "BLK": "BLACK",
    "RD": "RED",
    "FLLT": "FILLET",
    "FLTS": "FILLET",
    "FLT": "FILLET",
    "PRTNS": "PORTIONS",
    "PRTN": "PORTION",
    "PKG": "PACKAGE",
    "PKGS": "PACKAGE",
    "APPROX": "APPROXIMATE",
    "AVG": "AVERAGE",
    "MIN": "MINIMUM",
    "MAX": "MAXIMUM",
    "ASST": "ASSORTED",
    "ASSTD": "ASSORTED",
    "SLT": "SALT",
    "SGR": "SUGAR",
    "FLR": "FLOUR",
    "PK": "PACK",
    "PKS": "PACK",
    "CS": "CASE",
    "BX": "BOX",
    "BXS": "BOX",
    "BG": "BAG",
    "BGS": "BAG",
    "BTL": "BOTTLE",
    "BTLS": "BOTTLE",
    "JR": "JAR",
    "JRS": "JAR",
    "CN": "CAN",
    "CNS": "CAN",
}

# ─── Plural → singular rules (simple suffix stripping) ───
# Applied AFTER abbreviation expansion, so we're working with full words.
# Order matters: check longest suffixes first.
_PLURAL_RULES = [
    # Irregular / special cases checked first
    ("TOMATOES", "TOMATO"),
    ("POTATOES", "POTATO"),
    ("LEAVES", "LEAF"),
    ("HALVES", "HALF"),
    ("LOAVES", "LOAF"),
    ("KNIVES", "KNIFE"),
]

# Words that end in S but are NOT plural — do not strip
_PLURAL_EXCEPTIONS = frozenset({
    "LETTUCE", "RICE", "CHEESE", "JUICE", "SAUCE", "GREASE",
    "ASPARAGUS", "HUMMUS", "COUSCOUS", "MOLASSES", "BASS",
    "GRASS", "CLASS", "GLASS", "DRESS", "PRESS", "ROSS",
    "BONUS", "CITRUS", "PLUS", "MINUS", "ITIOUS",
    "HDLS", "BNLS", "SKLS",  # Abbreviations (handled elsewhere)
})


def _singularize(word: str) -> str:
    """Simple rule-based singular form. Input must be uppercase."""
    if len(word) <= 3:
        return word
    if word in _PLURAL_EXCEPTIONS:
        return word

    # Check irregular forms first
    for plural, singular in _PLURAL_RULES:
        if word == plural:
            return singular

    # Standard suffix rules
    if word.endswith("IES") and len(word) > 4:
        # BERRIES → BERRY, but not SERIES
        return word[:-3] + "Y"
    if word.endswith("SES") and len(word) > 4:
        # CASES → CASE, SAUCES stays (in exceptions)
        return word[:-1]
    if word.endswith("S") and not word.endswith("SS"):
        # ONIONS → ONION, BREASTS → BREAST
        # But not BASS, GRASS etc (in exceptions)
        candidate = word[:-1]
        if len(candidate) >= 3:
            return candidate

    return word


# ─── Spec patterns ───
# Grade: NN-NN or NN/NN where both sides are numbers (e.g., 80-20, 80/20)
_RE_GRADE = re.compile(r'\b(\d{1,3})\s*[-/]\s*(\d{1,3})\b')

# Product code: #NNN
_RE_PRODUCT_CODE = re.compile(r'#(\d+)')

# Embedded weight/count at end of name: 25LB, 150CT, 50OZ, 10KG
_RE_EMBEDDED_WEIGHT = re.compile(r'\b(\d+(?:\.\d+)?)\s*(LB|LBS|OZ|KG|CT|EA|GAL|QT)\b', re.IGNORECASE)


def _is_grade(left: int, right: int) -> bool:
    """Heuristic: grade ratios have lopsided numbers (80/20, 70/30, 93/7)."""
    return left >= 2 * right


def _extract_specs(name_upper: str) -> dict:
    """Extract structured specs from an uppercase item name. Returns specs dict."""
    specs = {}

    # Grade / size codes (e.g., 80-20, 31-35)
    for m in _RE_GRADE.finditer(name_upper):
        left, right = int(m.group(1)), int(m.group(2))
        if _is_grade(left, right):
            specs["grade"] = f"{left}/{right}"
        else:
            specs["size_code"] = f"{left}-{right}"

    # Product codes (#11, #4052)
    m = _RE_PRODUCT_CODE.search(name_upper)
    if m:
        specs["product_code"] = f"#{m.group(1)}"

    # Embedded weight/count (25LB, 150CT)
    for m in _RE_EMBEDDED_WEIGHT.finditer(name_upper):
        num, unit = m.group(1), m.group(2).upper()
        unit = {"LBS": "LB"}.get(unit, unit)
        if unit in ("CT", "EA"):
            specs["embedded_count"] = f"{num}{unit}"
        else:
            specs["embedded_weight"] = f"{num}{unit}"

    return specs


def _build_clean_name(raw: str) -> str:
    """
    Step 1: Conservative cleanup. Preserves ALL meaningful content.
    - Uppercase
    - Collapse whitespace
    - Standardize grade separators (- → / for grade patterns only)
    - Strip trailing punctuation
    """
    s = raw.strip().upper()
    s = re.sub(r'\s+', ' ', s)
    s = s.rstrip('.;,')

    # Standardize grade separators: 80-20 → 80/20 (only for grade ratios, not size codes)
    def _norm_grade_sep(m):
        left, right = int(m.group(1)), int(m.group(2))
        if _is_grade(left, right):
            return f"{left}/{right}"
        return m.group(0)  # Leave size codes as-is (31-35 stays 31-35)

    s = _RE_GRADE.sub(_norm_grade_sep, s)
    return s.strip()


def _build_base_name(clean_name: str, specs: dict, pack_size_raw: str) -> str:
    """
    Step 2: Aggressive reduction for broad matching.
    Strips specs + embedded weight (if redundant with pack_size) from clean_name.
    """
    s = clean_name

    # Remove grade pattern
    if "grade" in specs:
        s = _RE_GRADE.sub('', s)

    # Remove size_code pattern
    if "size_code" in specs:
        s = _RE_GRADE.sub('', s)

    # Remove product code
    if "product_code" in specs:
        s = _RE_PRODUCT_CODE.sub('', s)

    # Remove embedded weight ONLY if pack_size already carries the weight info
    if "embedded_weight" in specs and pack_size_raw:
        s = _RE_EMBEDDED_WEIGHT.sub('', s)
    if "embedded_count" in specs and pack_size_raw:
        s = _RE_EMBEDDED_WEIGHT.sub('', s)

    # Collapse whitespace after removals
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _normalize_token(token: str) -> str:
    """Expand abbreviation, then singularize. Input must be uppercase."""
    expanded = ABBREVIATION_MAP.get(token, token)
    # If abbreviation expanded to multi-word, process each sub-word
    if ' ' in expanded:
        return expanded  # e.g., "EXTRA LARGE" — leave as-is (will be split later)
    return _singularize(expanded)


def _build_match_key(name: str) -> str:
    """
    Tokenize, normalize each token (abbreviations + singular), sort, rejoin.
    Produces a stable, order-independent key.
    """
    tokens = name.split()
    normalized = []
    for t in tokens:
        expanded = _normalize_token(t)
        # Handle multi-word expansions (e.g., EXTRA LARGE)
        for sub in expanded.split():
            normalized.append(sub)
    normalized.sort()
    return ' '.join(normalized)


def _standardize_unit(raw_unit: str) -> str:
    """Standardize unit using existing UNIT_CANONICAL from preprocessing."""
    if not raw_unit:
        return ""
    u = raw_unit.strip().upper().rstrip(".")
    return UNIT_CANONICAL.get(u, u)


# ─── Public API ───

def normalize_item(item: dict) -> dict:
    """
    Main entry point. Adds 'norm' dict to item. Does NOT modify existing fields.

    Args:
        item: dict with at minimum 'raw_name'. Optionally 'pack_size'/'pack_size_raw', 'unit'.

    Returns:
        The same item dict with 'norm' key added.
    """
    raw_name = (item.get("raw_name") or "").strip()
    if not raw_name:
        item["norm"] = {
            "clean_name": "",
            "base_name": "",
            "strict_match_key": "",
            "loose_match_key": "",
            "specs": {},
            "unit_std": _standardize_unit(item.get("unit", "")),
        }
        return item

    pack_size_raw = (item.get("pack_size_raw") or item.get("pack_size") or "").strip()

    # Step 1-2: Build clean_name (conservative)
    clean_name = _build_clean_name(raw_name)

    # Step 3: Extract specs
    specs = _extract_specs(clean_name)

    # Step 4: Build base_name (aggressive)
    base_name = _build_base_name(clean_name, specs, pack_size_raw)

    # Step 5: Build match keys (token-normalized + sorted)
    strict_match_key = _build_match_key(clean_name)
    loose_match_key = _build_match_key(base_name)

    # Step 6: Standardize unit
    unit_std = _standardize_unit(item.get("unit", ""))

    item["norm"] = {
        "clean_name": clean_name,
        "base_name": base_name,
        "strict_match_key": strict_match_key,
        "loose_match_key": loose_match_key,
        "specs": specs,
        "unit_std": unit_std,
    }
    return item


def normalize_items(items: list) -> list:
    """Normalize a list of items. Convenience wrapper."""
    for item in items:
        normalize_item(item)
    return items
