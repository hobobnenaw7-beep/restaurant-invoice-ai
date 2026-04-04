"""
Phase 4: Semantic and Consistency Intelligence

Deterministic rule-based semantic validation for parsed invoice line items.
Detects row-level logical errors that pass numeric validation:
- Cross-row value leakage
- Truncated / generic / suspicious item names
- Service/surcharge rows misidentified as products
- Structurally inconsistent rows vs neighbors
- Vendor-specific pattern violations
- Row classification (product vs service)
- Trust level computation (math + fields + classification)

Output: flags only, never auto-corrects.
Trust level: trusted / info / warning / needs_review
"""

import re
import logging
from statistics import median

logger = logging.getLogger(__name__)


# ── 1. Constants ──

SERVICE_KEYWORDS = {
    "delivery", "fuel", "surcharge", "credit", "discount", "freight",
    "handling", "service", "charge", "fee", "adjustment", "return",
    "deposit", "rebate", "refund", "coupon", "promo", "minimum",
}

GENERIC_NAMES = {
    "packer", "misc", "other", "item", "product", "sundry",
    "various", "assorted", "general", "n/a", "na", "tbd",
}

# Pack-size patterns that shouldn't appear inside item_name
PACK_PATTERN = re.compile(r'\b\d+/\d+\s*(LB|OZ|CT|EA|GAL|ML|QT|CS|PK|DZ|BX)\b', re.IGNORECASE)

# Expanded valid pack formats:
# Weight: 6/4 LB, 2/5 OZ, 10 LB
# Volume: 4 GAL, 2 QT
# Count: 24 CT, 12 EA, 1 DZ
# Dimensions: 1508X8X3, 12X10X5
# Ratio: 6/4, 2/5, 48/6
# Combined: 4/10 LB, 48/6 OZ
VALID_PACK_PATTERNS = [
    re.compile(r'^\d+/\d+\s*(LB|LBS|OZ|GAL|CT|EA|DZ|ML|QT|PT|CS|PK|BX)\b', re.IGNORECASE),  # 6/4 LB
    re.compile(r'^\d+\s*(LB|LBS|OZ|GAL|CT|EA|DZ|ML|QT|PT|CS|PK|BX)\b', re.IGNORECASE),       # 10 LB
    re.compile(r'^\d+[xX]\d+([xX]\d+)?\s*$'),                                                    # 1508X8X3
    re.compile(r'^\d+/\d+\s*$'),                                                                  # 6/4
    re.compile(r'^\d+\s*(GM|G|KG|MG|L|CL)\b', re.IGNORECASE),                                   # 10007 GM
    re.compile(r'^\d+\s*#\s*$'),                                                                   # 25#
]

# Price-like patterns inside item names (column bleed)
PRICE_IN_NAME = re.compile(r'\$\d+\.\d{2}\b')
BARE_DECIMAL_IN_NAME = re.compile(r'\b\d{1,4}\.\d{2}\b')


# ── 1b. Row Classification ──

def classify_row_type(item: dict) -> str:
    """
    Classify a row as 'product' or 'service'.
    Service rows: fuel surcharges, delivery fees, credits, adjustments, etc.
    These bypass pack validation entirely.
    """
    name = (item.get("item_name") or "").strip().lower()
    if not name:
        return "product"

    name_words = set(name.split())
    service_hits = name_words & SERVICE_KEYWORDS

    if service_hits:
        pack = (item.get("pack_size") or "").strip()
        qty = float(item.get("quantity", 0) or 0)
        # Strong signal: service keyword + no pack + qty <= 1
        if not pack and qty <= 1:
            return "service"
        # Service keyword dominates the name (e.g., "fuel surcharge", "delivery fee")
        if len(service_hits) >= 1 and len(name_words) <= 4:
            return "service"

    return "product"


def is_valid_pack_format(pack_str: str) -> bool:
    """
    Check if a pack string matches any known valid format.
    Expanded to handle: weight, volume, count, dimensions, metric units.
    Returns True if the pack is a recognized format (even if unusual).
    """
    if not pack_str or not pack_str.strip():
        return False
    p = pack_str.strip()
    for pattern in VALID_PACK_PATTERNS:
        if pattern.match(p):
            return True
    return False


# ── 1c. Trust Level Computation ──

def compute_trust_level(item: dict) -> str:
    """
    Compute unified trust level for an item based on:
    - Math validation (financial correctness) — primary signal
    - Critical field presence
    - Row classification coherence
    - Structural ambiguity

    Levels:
      trusted       — math passes + critical fields present + coherent classification
      info          — semantic annotations present but don't affect financial correctness
      warning       — ambiguous structure or unclear field source
      needs_review  — math fails or critical fields missing
    """
    math_status = item.get("validation", {}).get("status", "pass")
    semantic_flags = item.get("semantic_flags", [])
    row_type = item.get("row_type", "product")
    qty = float(item.get("quantity", 0) or 0)
    price = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total_price", 0) or 0)
    name = (item.get("item_name") or "").strip()

    # Critical field check
    has_name = bool(name)
    has_financials = total > 0 or (qty > 0 and price > 0)
    has_critical_fields = has_name and has_financials

    # Service rows: trusted if they have a name and a total/amount
    if row_type == "service":
        if has_name and total > 0:
            return "trusted"
        elif has_name:
            return "info"
        else:
            return "warning"

    # Product rows: math is the primary trust signal
    if math_status == "needs_review":
        return "needs_review"

    if not has_critical_fields:
        return "warning"

    # Structural ambiguity flags that indicate unclear field source
    structural_ambiguity = [f for f in semantic_flags if any(
        kw in f for kw in [
            "values_duplicate_neighbor", "total_matches_neighbor",
            "price_in_name", "missing_name", "truncated_name",
        ]
    )]

    if structural_ambiguity:
        return "warning"

    # Math passes or is close — check for non-financial semantic annotations
    if math_status == "pass":
        if semantic_flags:
            # Semantic flags exist but math is correct → informational only
            return "trusted"
        return "trusted"

    if math_status == "warning":
        # Close math (< 2% off) + no structural issues → still trusted
        if not structural_ambiguity:
            return "trusted"
        return "warning"

    return "warning"


# ── 2. Row-level semantic checks ──

def check_item_name_quality(item: dict) -> list[str]:
    """Detect truncated, generic, or suspicious item names."""
    flags = []
    name = (item.get("item_name") or "").strip()

    if not name:
        return ["missing_name"]

    # Truncated: 3 or fewer alphanumeric characters (likely abbreviated)
    alpha_chars = sum(1 for c in name if c.isalnum())
    if alpha_chars <= 3:
        flags.append(f"truncated_name: '{name}' ({alpha_chars} chars)")

    # Single word without context (unless it's a known short product like "RICE")
    words = name.split()
    if len(words) == 1 and len(name) < 8:
        flags.append(f"single_word_name: '{name}'")

    # Generic/placeholder names
    name_lower = name.lower().strip()
    for gn in GENERIC_NAMES:
        if name_lower == gn or name_lower.startswith(gn + " "):
            flags.append(f"generic_name: '{name}' matches '{gn}'")
            break

    # Service/surcharge row misidentified as product
    name_words_lower = set(name_lower.split())
    service_hits = name_words_lower & SERVICE_KEYWORDS
    if service_hits:
        flags.append(f"possible_service_row: '{name}' contains {service_hits}")

    return flags


def check_column_bleed(item: dict) -> list[str]:
    """Detect prices, pack sizes, or quantities bleeding into item name."""
    flags = []
    name = (item.get("item_name") or "").strip()
    if not name:
        return flags

    # Price embedded in name ($12.50)
    if PRICE_IN_NAME.search(name):
        flags.append(f"price_in_name: '{name}'")

    # Pack size in name instead of pack_size field
    pack_match = PACK_PATTERN.search(name)
    pack_field = (item.get("pack_size") or "").strip()
    if pack_match and not pack_field:
        flags.append(f"pack_size_in_name: '{pack_match.group()}' in '{name}' (pack_size field empty)")

    # Bare decimal in name that looks like a price (e.g., "CHICKEN 42.50")
    # Only flag if it's at the end of the name (likely a misplaced price)
    words = name.split()
    if len(words) >= 2:
        last_word = words[-1]
        if BARE_DECIMAL_IN_NAME.match(last_word) and float(last_word) > 1.0:
            flags.append(f"trailing_number_in_name: '{last_word}' in '{name}'")

    return flags


# ── 3. Context-aware cross-row checks ──

def check_cross_row_leakage(items: list[dict]) -> dict[int, list[str]]:
    """
    Detect when a row's values suspiciously match a neighbor's values.
    This catches OCR cross-row contamination where one row reads
    another row's price/total.
    """
    flags_by_idx = {}
    if len(items) < 2:
        return flags_by_idx

    for i in range(len(items)):
        current = items[i]
        c_total = float(current.get("total_price", 0) or 0)
        c_price = float(current.get("unit_price", 0) or 0)
        c_qty = float(current.get("quantity", 0) or 0)

        for offset in [-1, 1]:
            j = i + offset
            if j < 0 or j >= len(items):
                continue
            neighbor = items[j]
            n_total = float(neighbor.get("total_price", 0) or 0)
            n_price = float(neighbor.get("unit_price", 0) or 0)
            n_qty = float(neighbor.get("quantity", 0) or 0)

            issues = []

            # Total matches neighbor's total exactly (suspicious if names differ)
            if c_total > 0 and c_total == n_total:
                c_name = (current.get("item_name") or "").upper()
                n_name = (neighbor.get("item_name") or "").upper()
                c_words = set(c_name.split())
                n_words = set(n_name.split())
                if len(c_words & n_words) == 0:  # Different items
                    issues.append(
                        f"total_matches_neighbor: row[{i}] total=${c_total:.2f} == row[{j}] total=${n_total:.2f}"
                    )

            # Price matches neighbor's price AND total matches neighbor's total
            if c_price > 0 and c_total > 0 and c_price == n_price and c_total == n_total:
                issues.append(
                    f"values_duplicate_neighbor: row[{i}] (${c_price}, ${c_total}) == row[{j}]"
                )

            # Qty matches neighbor but different items (less suspicious alone)
            # Only flag if combined with a price match
            if c_qty > 0 and c_qty == n_qty and c_price == n_price and c_qty > 1:
                issues.append(
                    f"qty_and_price_match_neighbor: row[{i}] (qty={c_qty}, price=${c_price}) == row[{j}]"
                )

            if issues:
                if i not in flags_by_idx:
                    flags_by_idx[i] = []
                flags_by_idx[i].extend(issues)

    return flags_by_idx


def check_structural_consistency(items: list[dict]) -> dict[int, list[str]]:
    """
    Detect rows that are structurally inconsistent with their neighbors.
    Checks: word count in name, field completeness, value ranges.
    """
    flags_by_idx = {}
    if len(items) < 3:
        return flags_by_idx

    # Compute per-item metrics
    name_lengths = []
    has_qty = []
    has_price = []
    totals = []
    for item in items:
        name = (item.get("item_name") or "").strip()
        name_lengths.append(len(name.split()))
        has_qty.append(float(item.get("quantity", 0) or 0) > 0)
        has_price.append(float(item.get("unit_price", 0) or 0) > 0)
        totals.append(float(item.get("total_price", 0) or 0))

    median_name_len = median(name_lengths) if name_lengths else 2
    valid_totals = [t for t in totals if t > 0]
    median_total = median(valid_totals) if valid_totals else 0

    for i, item in enumerate(items):
        issues = []

        # Name significantly shorter than neighbors
        if name_lengths[i] < max(1, median_name_len * 0.4) and median_name_len >= 2:
            issues.append(
                f"short_name_vs_peers: {name_lengths[i]} words (median={median_name_len:.0f})"
            )

        # Row missing qty when most rows have it
        qty_fill_rate = sum(has_qty) / len(has_qty) if has_qty else 0
        if not has_qty[i] and qty_fill_rate >= 0.5:
            issues.append(f"missing_qty_when_peers_have_it: fill_rate={qty_fill_rate:.0%}")

        # Row missing price when most rows have it
        price_fill_rate = sum(has_price) / len(has_price) if has_price else 0
        if not has_price[i] and price_fill_rate > 0.7:
            issues.append(f"missing_price_when_peers_have_it: fill_rate={price_fill_rate:.0%}")

        # Total is a statistical outlier (>3× or <0.25× the median)
        if median_total > 0 and totals[i] > 0:
            ratio = totals[i] / median_total
            if ratio > 4.0:
                issues.append(f"total_outlier_high: ${totals[i]:.2f} is {ratio:.1f}× median ${median_total:.2f}")
            elif ratio < 0.15:
                issues.append(f"total_outlier_low: ${totals[i]:.2f} is {ratio:.2f}× median ${median_total:.2f}")

        if issues:
            flags_by_idx[i] = issues

    return flags_by_idx


# ── 4. Vendor-aware semantic checks ──

def check_vendor_patterns(items: list[dict], vendor: str | None) -> dict[int, list[str]]:
    """
    Lightweight vendor-specific consistency checks.
    Uses known patterns for major distributors.
    Skips pack validation for service rows.
    Accepts expanded pack formats (dimensions, volume, metric).
    """
    flags_by_idx = {}
    if not vendor:
        return flags_by_idx

    vendor_lower = (vendor or "").lower()

    # Pre-compute pack_size fill rate for distributor check
    is_distributor = ("sysco" in vendor_lower or "us foods" in vendor_lower or "usfoods" in vendor_lower)
    if is_distributor and items:
        pack_filled = sum(1 for it in items if (it.get("pack_size") or "").strip())
        pack_fill_rate = pack_filled / len(items)
    else:
        pack_fill_rate = 1.0

    for i, item in enumerate(items):
        issues = []
        name = (item.get("item_name") or "").strip().upper()
        pack = (item.get("pack_size") or "").strip()
        qty = float(item.get("quantity", 0) or 0)
        price = float(item.get("unit_price", 0) or 0)
        total = float(item.get("total_price", 0) or 0)
        row_type = item.get("row_type", "product")

        if is_distributor:
            # Skip pack validation entirely for service rows
            if row_type == "service":
                pass  # No pack checks for service rows
            else:
                # Only flag missing pack when SOME items DO have pack
                if not pack and qty > 0 and total > 0 and pack_fill_rate > 0:
                    has_pack_in_name = bool(re.search(
                        r'\d+/\d+\s*(LB|OZ|CT|EA|GAL|ML|QT|CS|PK|DZ|BX)\b',
                        name, re.IGNORECASE
                    ))
                    if not has_pack_in_name:
                        issues.append("distributor_missing_pack_size")

                # Check if pack format is valid (expanded patterns)
                if pack and not is_valid_pack_format(pack):
                    # Only flag as informational (info level), not trust-degrading
                    # when math validation passes
                    math_ok = item.get("validation", {}).get("status", "") in ("pass", "warning")
                    if math_ok:
                        issues.append(f"pack_format_unusual: '{pack}' (math OK, informational)")
                    else:
                        issues.append(f"pack_parse_failed: '{pack}'")

            # Quantities should be reasonable (1-500 for cases)
            if qty > 500:
                issues.append(f"unreasonable_qty_for_distributor: {qty}")

        if "pfg" in vendor_lower or "performance" in vendor_lower:
            if total > 0 and price == 0 and "LB" not in name and "OZ" not in name:
                if not any(w in name for w in ["LB", "OZ", "KG", "POUND"]):
                    issues.append("pfg_missing_weight_indicator")

        if "seafood" in vendor_lower or "fish" in vendor_lower:
            non_food = ["DELIVERY", "FUEL", "SERVICE", "BOX", "ICE"]
            for nf in non_food:
                if nf in name and total > 0 and qty > 0:
                    issues.append(f"seafood_non_product_row: '{nf}' in '{name}'")

        if issues:
            flags_by_idx[i] = issues

    return flags_by_idx


# ── 5. Orchestrator ──

def run_semantic_validation(items: list[dict], vendor: str | None = None) -> dict:
    """
    Run all semantic validation checks on parsed items.
    Adds `semantic_flags`, `row_type`, `semantic_status`, and `trust_level` to each item.
    Never auto-corrects — only flags.

    Trust model:
      - Math validation = primary financial trust signal
      - Semantic flags = informational annotations (don't degrade trust when math passes)
      - Row classification (product/service) determines which checks apply
      - Trust level = trusted / info / warning / needs_review
    """
    if not items:
        return {
            "semantic_issues_total": 0,
            "suspicious_count": 0,
            "needs_review_count": 0,
            "flagged_indices": [],
            "checks_run": [],
        }

    checks_run = []

    # 0. Row classification (product vs service)
    for item in items:
        item["row_type"] = classify_row_type(item)
    checks_run.append("row_classification")

    # 1. Row-level name quality
    for i, item in enumerate(items):
        name_flags = check_item_name_quality(item)
        bleed_flags = check_column_bleed(item)
        all_flags = name_flags + bleed_flags

        # For service rows, suppress service_row flag from name quality
        # (it's expected, not a problem — already classified)
        if item["row_type"] == "service":
            all_flags = [f for f in all_flags if "possible_service_row" not in f]

        item.setdefault("semantic_flags", []).extend(all_flags)
    checks_run.append("name_quality")
    checks_run.append("column_bleed")

    # 2. Cross-row leakage
    leakage = check_cross_row_leakage(items)
    for idx, flags in leakage.items():
        items[idx].setdefault("semantic_flags", []).extend(flags)
    checks_run.append("cross_row_leakage")

    # 3. Structural consistency
    structural = check_structural_consistency(items)
    for idx, flags in structural.items():
        items[idx].setdefault("semantic_flags", []).extend(flags)
    checks_run.append("structural_consistency")

    # 4. Vendor patterns
    vendor_flags = check_vendor_patterns(items, vendor)
    for idx, flags in vendor_flags.items():
        items[idx].setdefault("semantic_flags", []).extend(flags)
    if vendor:
        checks_run.append(f"vendor_patterns:{vendor}")

    # 4.5 Deduplicate: suppress distributor_missing_pack_size when pack_size_in_name
    for item in items:
        sf = item.get("semantic_flags", [])
        has_pack_in_name = any("pack_size_in_name" in f for f in sf)
        if has_pack_in_name:
            item["semantic_flags"] = [f for f in sf if "distributor_missing_pack_size" not in f]

    # 5. Compute per-item semantic status and trust level
    flagged_indices = []
    suspicious_count = 0
    needs_review_count = 0
    total_issues = 0

    for i, item in enumerate(items):
        sem_flags = item.get("semantic_flags", [])
        total_issues += len(sem_flags)

        if not sem_flags:
            item["semantic_status"] = "pass"
        else:
            # Determine semantic severity
            has_critical = any(
                kw in f for f in sem_flags
                for kw in ["values_duplicate_neighbor", "total_matches_neighbor",
                           "price_in_name", "missing_name", "math_mismatch"]
            )
            has_moderate = any(
                kw in f for f in sem_flags
                for kw in ["total_outlier", "truncated_name",
                           "pack_size_in_name", "generic_name", "qty_and_price_match"]
            )

            if has_critical:
                item["semantic_status"] = "needs_review"
                needs_review_count += 1
            elif has_moderate:
                item["semantic_status"] = "suspicious"
                suspicious_count += 1
            else:
                item["semantic_status"] = "suspicious"
                suspicious_count += 1

            flagged_indices.append(i)

        # Compute unified trust level
        item["trust_level"] = compute_trust_level(item)

    return {
        "semantic_issues_total": total_issues,
        "suspicious_count": suspicious_count,
        "needs_review_count": needs_review_count,
        "flagged_indices": sorted(flagged_indices),
        "checks_run": checks_run,
    }
