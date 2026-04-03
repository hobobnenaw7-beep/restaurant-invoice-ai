"""
Phase 4: Semantic and Consistency Intelligence

Deterministic rule-based semantic validation for parsed invoice line items.
Detects row-level logical errors that pass numeric validation:
- Cross-row value leakage
- Truncated / generic / suspicious item names
- Service/surcharge rows misidentified as products
- Structurally inconsistent rows vs neighbors
- Vendor-specific pattern violations

Output: flags only, never auto-corrects.
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

# Price-like patterns inside item names (column bleed)
PRICE_IN_NAME = re.compile(r'\$\d+\.\d{2}\b')
BARE_DECIMAL_IN_NAME = re.compile(r'\b\d{1,4}\.\d{2}\b')


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
    """
    flags_by_idx = {}
    if not vendor:
        return flags_by_idx

    vendor_lower = (vendor or "").lower()

    # Pre-compute pack_size fill rate for distributor check
    # If most items are missing pack, it's likely a parser/column issue, not real missing data
    is_distributor = ("sysco" in vendor_lower or "us foods" in vendor_lower or "usfoods" in vendor_lower)
    if is_distributor and items:
        pack_filled = sum(1 for it in items if (it.get("pack_size") or "").strip())
        pack_fill_rate = pack_filled / len(items)
    else:
        pack_fill_rate = 1.0  # Irrelevant for non-distributors

    for i, item in enumerate(items):
        issues = []
        name = (item.get("item_name") or "").strip().upper()
        pack = (item.get("pack_size") or "").strip()
        qty = float(item.get("quantity", 0) or 0)
        price = float(item.get("unit_price", 0) or 0)
        total = float(item.get("total_price", 0) or 0)

        if is_distributor:
            # Only flag missing pack_size when SOME items DO have pack_size
            # (pack_fill_rate > 0 means the column was successfully mapped for at least some rows).
            # If ALL items are missing pack, it's a parser/OCR column-mapping issue.
            if not pack and qty > 0 and total > 0 and pack_fill_rate > 0:
                # Check if pack info is embedded in item name
                has_pack_in_name = bool(re.search(r'\d+/\d+\s*(LB|OZ|CT|EA|GAL|ML|QT|CS|PK|DZ|BX)\b', name, re.IGNORECASE))
                if not has_pack_in_name:
                    issues.append("distributor_missing_pack_size")

            # Quantities should be reasonable (1-500 for cases)
            if qty > 500:
                issues.append(f"unreasonable_qty_for_distributor: {qty}")

        if "pfg" in vendor_lower or "performance" in vendor_lower:
            # PFG: weight-based pricing, expect weight indicators
            if total > 0 and price == 0 and "LB" not in name and "OZ" not in name:
                if not any(w in name for w in ["LB", "OZ", "KG", "POUND"]):
                    issues.append("pfg_missing_weight_indicator")

        if "seafood" in vendor_lower or "fish" in vendor_lower:
            # Seafood suppliers: items should be food products
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
    Adds a `semantic_flags` field to each item and returns an aggregate summary.
    Never auto-corrects — only flags.
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

    # 1. Row-level name quality
    for i, item in enumerate(items):
        name_flags = check_item_name_quality(item)
        bleed_flags = check_column_bleed(item)
        all_flags = name_flags + bleed_flags
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
    # is already flagged (pack info exists, just in wrong column — not truly missing)
    for item in items:
        sf = item.get("semantic_flags", [])
        has_pack_in_name = any("pack_size_in_name" in f for f in sf)
        if has_pack_in_name:
            item["semantic_flags"] = [f for f in sf if "distributor_missing_pack_size" not in f]

    # 5. Compute per-item semantic status
    flagged_indices = []
    suspicious_count = 0
    needs_review_count = 0
    total_issues = 0

    for i, item in enumerate(items):
        sem_flags = item.get("semantic_flags", [])
        total_issues += len(sem_flags)

        if not sem_flags:
            item["semantic_status"] = "pass"
            continue

        # Determine severity
        has_critical = any(
            kw in f for f in sem_flags
            for kw in ["values_duplicate_neighbor", "total_matches_neighbor",
                       "price_in_name", "missing_name", "math_mismatch"]
        )
        has_moderate = any(
            kw in f for f in sem_flags
            for kw in ["total_outlier", "truncated_name", "possible_service_row",
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

    return {
        "semantic_issues_total": total_issues,
        "suspicious_count": suspicious_count,
        "needs_review_count": needs_review_count,
        "flagged_indices": sorted(flagged_indices),
        "checks_run": checks_run,
    }
