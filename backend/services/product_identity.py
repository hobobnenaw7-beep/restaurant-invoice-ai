"""
Universal Product Identity Layer
=================================

Three distinct entity layers:

A. Canonical Product  — the universal identity
   Collection: canonical_products
   {canonical_product_id, canonical_name, category, attributes, status}

B. Vendor Product Mapping  — vendor+code → canonical_product_id
   Collection: vendor_product_mappings
   {vendor_key, product_code, canonical_product_id, vendor_description, pack_size, source}

C. Alias / Description Mapping  — normalized text → canonical_product_id
   Collection: product_aliases
   {normalized_text, canonical_product_id, confidence, source}

Matching priority:
  1. Direct code mapping (vendor + product_code)  — highest confidence
  2. User-confirmed alias (source=user_corrected)  — highest confidence
  3. Fuzzy keyword match  — scored, low confidence → needs_review
"""

import re
import uuid
import logging
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger("restaurant_ai")


# ─────────────────────────────────────────────────────────────────────
# Text Normalization & Keyword Extraction
# ─────────────────────────────────────────────────────────────────────

# Noise prefixes from OCR / section headers
_NOISE_PREFIXES = re.compile(
    r'^(?:\d+\s+LB\s+|LE?\s+|D\s+|\*+\w+\*+\s*|POULTRY\s*-?\s*|FROZEN\s*-?\s*)',
    re.IGNORECASE,
)
# Brand/system prefixes (Sysco specific)
_SYS_PREFIX = re.compile(r'^(?:SYS|SVS|SXS)\s+(?:CLS|REL|IMP)\s+', re.IGNORECASE)

# Pack/size suffixes that aren't product identity
_PACK_SUFFIX = re.compile(
    r'\s+(?:\d+\s*(?:LB|OZ|CT|CS|GAL|#)\.?\s*$|\d+X\d+.*$|YTD\w+$|SYR?\w+$)',
    re.IGNORECASE,
)

# Product attribute patterns
_CUT_PATTERNS = {
    "breast": r'\bBR(?:EA)?ST\b',
    "wing": r'\bWING\b',
    "thigh": r'\bTHIGH\b',
    "tender": r'\bTENDER\b',
    "gizzard": r'\bGIZZARD\b',
    "liver": r'\bLIVER\b',
    "whole": r'\bWH(?:O)?LE?\b',
    "ground": r'\bGROUND\b',
    "fillet": r'\bFILLET\b',
    "steak": r'\bSTEAK\b',
}
_SIZE_PATTERNS = {
    "small": r'\bS(?:M|MALL)\b',
    "medium": r'\bM(?:ED|EDIUM)\b',
    "large": r'\bL(?:G|RG|ARGE)\b',
    "jumbo": r'\bJUMBO\b',
}
_FORM_PATTERNS = {
    "breaded": r'\bBR(?:EA)?D(?:ED)?\b',
    "iqf": r'\bIQF\b',
    "frozen": r'\bFR(?:O)?Z(?:EN|N)?\b',
    "fresh": r'\bFRESH\b',
    "raw": r'\bRAW\b',
    "cooked": r'\bCOOK(?:ED)?\b',
}


def normalize_product_text(raw_name: str) -> str:
    """Strip OCR noise, prefixes, suffixes → core product identity text."""
    text = raw_name.strip().upper()
    text = _NOISE_PREFIXES.sub('', text).strip()
    text = _SYS_PREFIX.sub('', text).strip()
    text = _PACK_SUFFIX.sub('', text).strip()
    text = re.sub(r'[^A-Z0-9\s/]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_keywords(text: str) -> list[str]:
    """Extract significant keywords for fuzzy matching (sorted, deduplicated)."""
    norm = normalize_product_text(text)
    words = [w for w in norm.split() if len(w) > 1]
    # Remove pure numbers
    words = [w for w in words if not w.isdigit()]
    return sorted(set(words))


def extract_attributes(raw_name: str) -> dict:
    """Extract structured product attributes from raw name."""
    upper = raw_name.upper()
    attrs = {}
    for attr_name, pattern in _CUT_PATTERNS.items():
        if re.search(pattern, upper):
            attrs["cut"] = attr_name
            break
    for attr_name, pattern in _SIZE_PATTERNS.items():
        if re.search(pattern, upper):
            attrs["size"] = attr_name
            break
    for attr_name, pattern in _FORM_PATTERNS.items():
        if re.search(pattern, upper):
            attrs["form"] = attr_name
            break
    # Extract brand (first word if it looks like a brand)
    words = raw_name.strip().upper().split()
    if words:
        first = words[0]
        if first not in ("SYS", "SVS", "SXS", "CLS", "REL", "THE", "A", "AN"):
            known_brands = ("NABISCO", "HANOVER", "MONACO", "CAJ", "MONARCH", "HSE", "MRS", "IMPFRESH")
            if first in known_brands or (len(words) > 1 and first not in ("CHICKEN", "BEEF", "PORK", "SHRIMP")):
                attrs["brand"] = first
    return attrs


def build_keyword_signature(keywords: list[str]) -> str:
    """Build a stable signature from sorted keywords for indexing."""
    return "|".join(keywords)


# ─────────────────────────────────────────────────────────────────────
# Fuzzy Matching
# ─────────────────────────────────────────────────────────────────────

def compute_keyword_similarity(keywords_a: list[str], keywords_b: list[str]) -> float:
    """Jaccard similarity on keyword sets."""
    if not keywords_a or not keywords_b:
        return 0.0
    set_a = set(keywords_a)
    set_b = set(keywords_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


# ─────────────────────────────────────────────────────────────────────
# DB Operations
# ─────────────────────────────────────────────────────────────────────

async def create_canonical_product(
    db,
    restaurant_id: str,
    canonical_name: str,
    category: str = "",
    attributes: dict = None,
    source: str = "auto",
) -> dict:
    """Create a new canonical product."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "canonical_name": canonical_name,
        "category": category,
        "attributes": attributes or {},
        "keywords": extract_keywords(canonical_name),
        "keyword_signature": build_keyword_signature(extract_keywords(canonical_name)),
        "status": "active",
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    await db.canonical_products.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def create_vendor_mapping(
    db,
    restaurant_id: str,
    vendor_key: str,
    product_code: str,
    canonical_product_id: str,
    vendor_description: str = "",
    pack_size: str = "",
    source: str = "auto",
    user_id: str = "",
    user_name: str = "",
) -> dict:
    """Create or update a vendor → canonical product mapping."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "vendor_key": vendor_key,
        "product_code": product_code,
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
        "vendor_description": vendor_description,
        "pack_size": pack_size,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    if source == "user_corrected":
        doc["corrected_by_user_id"] = user_id
        doc["corrected_by_name"] = user_name
    await db.vendor_product_mappings.update_one(
        {"vendor_key": vendor_key, "product_code": product_code, "restaurant_id": restaurant_id},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4())}},
        upsert=True,
    )
    return doc


async def create_alias(
    db,
    restaurant_id: str,
    normalized_text: str,
    canonical_product_id: str,
    confidence: float = 1.0,
    source: str = "auto",
    user_id: str = "",
) -> dict:
    """Create a text alias → canonical product mapping."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "normalized_text": normalized_text,
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
        "confidence": confidence,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    if source == "user_corrected":
        doc["corrected_by_user_id"] = user_id
    await db.product_aliases.update_one(
        {"normalized_text": normalized_text, "restaurant_id": restaurant_id},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4())}},
        upsert=True,
    )
    return doc


# ─────────────────────────────────────────────────────────────────────
# Resolve Product Identity
# ─────────────────────────────────────────────────────────────────────

CONFIDENCE_DIRECT_CODE = 1.0
CONFIDENCE_USER_ALIAS = 1.0
CONFIDENCE_EXACT_TEXT = 0.95
CONFIDENCE_FUZZY_HIGH = 0.80
CONFIDENCE_FUZZY_LOW = 0.50
AUTO_LINK_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.50


async def resolve_product_identity(
    db,
    restaurant_id: str,
    raw_name: str,
    vendor_key: str = "",
    product_code: str = "",
) -> dict:
    """
    Resolve an extracted item to a canonical product.

    Returns:
      {
        "canonical_product_id": str or None,
        "canonical_name": str or None,
        "confidence": float,
        "match_type": "direct_code" | "user_alias" | "exact_text" | "fuzzy" | "none",
        "decision_path": str,
        "product_status": "matched" | "needs_review" | "new",
      }
    """
    result = {
        "canonical_product_id": None,
        "canonical_name": None,
        "confidence": 0.0,
        "match_type": "none",
        "decision_path": "",
        "product_status": "new",
    }

    # ─── Priority 1: Direct vendor+code mapping ───
    if vendor_key and product_code:
        mapping = await db.vendor_product_mappings.find_one(
            {"vendor_key": vendor_key, "product_code": product_code, "restaurant_id": restaurant_id},
            {"_id": 0},
        )
        if mapping:
            cp = await db.canonical_products.find_one(
                {"id": mapping["canonical_product_id"], "restaurant_id": restaurant_id},
                {"_id": 0},
            )
            if cp:
                result["canonical_product_id"] = cp["id"]
                result["canonical_name"] = cp["canonical_name"]
                result["confidence"] = CONFIDENCE_DIRECT_CODE
                result["match_type"] = "direct_code"
                result["decision_path"] = f"vendor_mapping:{vendor_key}:{product_code}"
                result["product_status"] = "matched"
                logger.debug(f"Product identity: direct code match {vendor_key}:{product_code} → {cp['canonical_name']}")
                return result

    # ─── Priority 2: Exact normalized text alias ───
    norm_text = normalize_product_text(raw_name)
    if norm_text:
        alias = await db.product_aliases.find_one(
            {"normalized_text": norm_text, "restaurant_id": restaurant_id},
            {"_id": 0},
        )
        if alias:
            cp = await db.canonical_products.find_one(
                {"id": alias["canonical_product_id"], "restaurant_id": restaurant_id},
                {"_id": 0},
            )
            if cp:
                conf = CONFIDENCE_USER_ALIAS if alias.get("source") == "user_corrected" else CONFIDENCE_EXACT_TEXT
                result["canonical_product_id"] = cp["id"]
                result["canonical_name"] = cp["canonical_name"]
                result["confidence"] = conf
                result["match_type"] = "user_alias" if alias.get("source") == "user_corrected" else "exact_text"
                result["decision_path"] = f"alias:'{norm_text}' (source={alias.get('source')})"
                result["product_status"] = "matched"
                return result

    # ─── Priority 3: Fuzzy keyword match ───
    keywords = extract_keywords(raw_name)
    if keywords:
        all_products = await db.canonical_products.find(
            {"restaurant_id": restaurant_id, "status": "active"},
            {"_id": 0, "id": 1, "canonical_name": 1, "keywords": 1},
        ).to_list(500)

        best_match = None
        best_score = 0.0
        for cp in all_products:
            cp_keywords = cp.get("keywords", [])
            score = compute_keyword_similarity(keywords, cp_keywords)
            if score > best_score:
                best_score = score
                best_match = cp

        if best_match and best_score >= REVIEW_THRESHOLD:
            result["canonical_product_id"] = best_match["id"]
            result["canonical_name"] = best_match["canonical_name"]
            result["confidence"] = round(best_score, 3)
            result["match_type"] = "fuzzy"
            result["decision_path"] = f"fuzzy:score={best_score:.3f},keywords={keywords[:5]}"

            if best_score >= AUTO_LINK_THRESHOLD:
                result["product_status"] = "matched"
            else:
                result["product_status"] = "needs_review"
                logger.info(
                    f"Product identity: low-confidence fuzzy match "
                    f"'{raw_name[:40]}' → '{best_match['canonical_name']}' "
                    f"(score={best_score:.3f}) → needs_review"
                )
            return result

    # No match found
    result["decision_path"] = f"no_match:keywords={keywords[:5]}"
    return result


# ─────────────────────────────────────────────────────────────────────
# Generate Initial Canonical Products from Existing Data
# ─────────────────────────────────────────────────────────────────────

async def generate_initial_products(db, restaurant_id: str, min_frequency: int = 5) -> dict:
    """
    Analyze existing extracted items and generate canonical products
    from the most frequent items.

    Rules:
      - Only group items that are CLEARLY the same product
      - Do not over-merge nearby but different items
      - If uncertain, keep separate and mark as review candidates
    """
    # Get all extracted items
    items = await db.extracted_items.find(
        {},
        {"_id": 0, "raw_name": 1, "item_name": 1, "item_code": 1, "receipt_id": 1}
    ).to_list(20000)

    # Build receipt → vendor map
    receipt_ids = list(set(it.get("receipt_id", "") for it in items if it.get("receipt_id")))
    receipts_cursor = db.uploaded_receipts.find(
        {"id": {"$in": receipt_ids}},
        {"_id": 0, "id": 1, "detected_vendor": 1}
    )
    receipts = {}
    async for r in receipts_cursor:
        receipts[r["id"]] = r.get("detected_vendor", "")

    # Normalize and group
    groups = defaultdict(lambda: {"names": [], "codes": set(), "vendors": set(), "count": 0})
    for it in items:
        raw = (it.get("raw_name") or it.get("item_name") or "").strip()
        if not raw or raw.upper() in ("?", "UNKNOWN"):
            continue
        norm = normalize_product_text(raw)
        if not norm or len(norm) < 3:
            continue
        # Skip fees/surcharges
        if any(kw in norm for kw in ("SURCHARGE", "FUEL", "DELIVERY", "CREDIT")):
            continue

        keywords = extract_keywords(raw)
        sig = build_keyword_signature(keywords)
        groups[sig]["names"].append(raw)
        groups[sig]["count"] += 1
        code = (it.get("item_code") or "").strip()
        if code:
            groups[sig]["codes"].add(code)
        vendor = receipts.get(it.get("receipt_id", ""), "")
        if vendor:
            v_norm = vendor.strip().upper()
            if "SYSCO" in v_norm:
                v_norm = "SYSCO"
            elif "US FOOD" in v_norm:
                v_norm = "USFOODS"
            elif "PERFORMANCE" in v_norm or "PFG" in v_norm:
                v_norm = "PFG"
            else:
                v_norm = v_norm[:20]
            groups[sig]["vendors"].add(v_norm)

    # Filter by frequency and generate products
    candidates = sorted(groups.items(), key=lambda x: -x[1]["count"])
    products = []
    for sig, data in candidates[:30]:
        if data["count"] < min_frequency:
            continue
        # Pick the most common raw name as canonical
        from collections import Counter
        name_counts = Counter(data["names"])
        best_name = name_counts.most_common(1)[0][0]
        canonical_name = normalize_product_text(best_name)
        attrs = extract_attributes(best_name)

        products.append({
            "canonical_name": canonical_name,
            "frequency": data["count"],
            "variant_count": len(name_counts),
            "codes": sorted(data["codes"])[:5],
            "vendors": sorted(data["vendors"])[:3],
            "attributes": attrs,
            "top_variants": [n for n, _ in name_counts.most_common(3)],
        })

    return {
        "total_unique_signatures": len(groups),
        "products_generated": len(products),
        "products": products,
    }
