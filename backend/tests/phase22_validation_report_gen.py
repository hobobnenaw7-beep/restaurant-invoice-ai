"""
Phase 2.2 Validation Report Generator
Simulates what Product Memory WOULD achieve if DB storage was working:
- Builds memory from ALL trusted items across the 50-file dataset
- Tests each ambiguous item against this enriched memory
- Compares baseline (no memory) vs potential (with cross-invoice memory)
"""
import json
import sys
import re
from collections import defaultdict

sys.path.insert(0, "/app/backend")
from services.product_memory import ProductMemory, _normalize_product_key

REPORT_PATH = "/app/backend/tests/phase2_stress_report.json"
OUTPUT_PATH = "/app/backend/tests/phase22_validation_report.json"


def run_validation():
    with open(REPORT_PATH) as f:
        report = json.load(f)

    invoices = [inv for inv in report["invoices"] if inv.get("is_sysco") and "error" not in inv]

    print("=" * 70)
    print("PHASE 2.2 VALIDATION REPORT — Product Memory Analysis")
    print("=" * 70)

    # ── Section 1: Current Baseline ──
    total_items = sum(inv["extracted_line_items"] for inv in invoices)
    total_trusted = sum(inv["trusted_count"] for inv in invoices)
    total_memory = sum(inv.get("memory_support_count", 0) for inv in invoices)
    total_review = sum(inv["review_count"] for inv in invoices)
    total_false = sum(inv["false_trust_count"] for inv in invoices)

    baseline_rate = total_trusted / total_items if total_items > 0 else 0

    print(f"\n  BASELINE (Current Phase 2.2 Results)")
    print(f"  {'─' * 50}")
    print(f"  Sysco Invoices:        {len(invoices)}")
    print(f"  Total Line Items:      {total_items}")
    print(f"  Trusted:               {total_trusted}")
    print(f"  Memory Support:        {total_memory}")
    print(f"  Review:                {total_review}")
    print(f"  False Trusts:          {total_false}")
    print(f"  Trust Rate:            {total_trusted}/{total_items} = {baseline_rate:.1%}")
    print(f"  Trust+Memory Rate:     {(total_trusted + total_memory)}/{total_items} = {(total_trusted + total_memory) / total_items:.1%}")

    # ── Section 2: Why Memory Produced 0 Upgrades ──
    print(f"\n  ROOT CAUSE ANALYSIS")
    print(f"  {'─' * 50}")
    print(f"  Product Memory DB Load:")
    print(f"    - purchases collection: 27 Sysco docs, but contains TEST/SEED data")
    print(f"      (generic names: 'Roma Tomatoes', 'Flour', 'Cheese Mozzarella')")
    print(f"    - receipt_extractions: 0 Sysco docs found")
    print(f"      (extraction results stored without detected_vendor or confidence_level)")
    print(f"    - Result: Memory has 83 entries from 14 products, NONE match Sysco format")
    print(f"    - All 62 ambiguous items return 'NO MATCH' against memory")

    # ── Section 3: Simulate Cross-Invoice Memory ──
    print(f"\n  SIMULATION: Cross-Invoice Memory (What If DB Was Fixed)")
    print(f"  {'─' * 50}")

    # Build memory from ALL trusted items across ALL invoices
    memory = ProductMemory()
    for inv in invoices:
        trusted_items = inv.get("trusted_items_detail", [])
        for item in trusted_items:
            # Reconstruct the format build_from_trusted_items expects
            memory_item = {
                "raw_name": item["name"],
                "quantity": item["qty"],
                "unit_price": item["price"],
                "total": item["total"],
                "confidence_level": "trusted",
                "pack_size": "",
            }
            memory.build_from_trusted_items([memory_item], source_label=f"cross_invoice")

    print(f"  Cross-Invoice Memory: {memory.size} entries, {memory.unique_products} unique products")

    # List memory products
    print(f"\n  Memory Products:")
    for key, entries in sorted(memory._products.items()):
        qtys = sorted(set(e["qty"] for e in entries))
        prices = sorted(set(round(e["price"], 2) for e in entries))
        print(f"    {key:<48} entries={len(entries):>2} qtys={qtys} prices={prices}")

    # Check each ambiguous item against cross-invoice memory
    ambig_items = report.get("ambiguity_pattern_log", [])
    upgrades = []
    inconsistencies = []
    no_matches = []
    insufficient = []

    for item in ambig_items:
        raw_name = item["name"]
        price = item["price"]
        total = item["total"]

        match = memory.lookup(raw_name, price)
        calc_qty = round(total / price, 2) if price > 0 else 0

        if not match.get("matched"):
            no_matches.append({
                "name": raw_name[:50],
                "price": price,
                "total": total,
                "key": _normalize_product_key(raw_name),
            })
        elif match["consistency"] == "stable":
            sq = match["stable_qty"]
            if calc_qty == sq:
                upgrades.append({
                    "name": raw_name[:50],
                    "price": price,
                    "total": total,
                    "stable_qty": sq,
                    "calc_qty": calc_qty,
                    "occurrences": match["occurrences"],
                    "price_matches": match["price_matches"],
                })
            else:
                inconsistencies.append({
                    "name": raw_name[:50],
                    "price": price,
                    "total": total,
                    "stable_qty": sq,
                    "calc_qty": calc_qty,
                })
        elif match["consistency"] == "insufficient":
            insufficient.append({
                "name": raw_name[:50],
                "price": price,
                "total": total,
                "occurrences": match["occurrences"],
                "price_matches": match["price_matches"],
                "qty_pattern": match.get("qty_pattern", {}),
            })
        else:
            no_matches.append({
                "name": raw_name[:50],
                "price": price,
                "total": total,
                "consistency": match["consistency"],
            })

    # ── Section 4: Simulation Results ──
    print(f"\n  SIMULATION RESULTS:")
    print(f"  {'─' * 50}")
    print(f"  Ambiguous items tested: {len(ambig_items)}")
    print(f"  UPGRADE ELIGIBLE:      {len(upgrades)}")
    print(f"  INCONSISTENCY:         {len(inconsistencies)}")
    print(f"  INSUFFICIENT DATA:     {len(insufficient)}")
    print(f"  NO MATCH:              {len(no_matches)}")

    if upgrades:
        new_memory_count = len(upgrades)
        new_trust_rate = total_trusted / total_items
        new_trust_plus_memory = (total_trusted + new_memory_count) / total_items

        print(f"\n  POTENTIAL PHASE 2.2 METRICS (if DB storage fixed):")
        print(f"  {'─' * 50}")
        print(f"  Trusted:                {total_trusted} (unchanged)")
        print(f"  Memory Support:         {new_memory_count} (NEW)")
        print(f"  Review:                 {total_review - new_memory_count} (reduced)")
        print(f"  Trust Rate:             {new_trust_rate:.1%} (unchanged)")
        print(f"  Trust+Memory Rate:      {new_trust_plus_memory:.1%} (was {baseline_rate:.1%})")
        print(f"  False Trusts:           0 (no changes to trust classification)")

        print(f"\n  UPGRADED ITEMS BREAKDOWN:")
        for u in upgrades:
            print(f"    {u['name']:<48} price=${u['price']:<8} total=${u['total']:<8} stable_qty={u['stable_qty']} (seen {u['price_matches']}x)")
    else:
        print(f"\n  Even with cross-invoice memory, NO items are upgrade-eligible.")
        print(f"  Reason: Trusted items have different prices than ambiguous items,")
        print(f"  and/or the qty patterns don't align.")

    if inconsistencies:
        print(f"\n  INCONSISTENCIES FOUND:")
        for inc in inconsistencies:
            print(f"    {inc['name']:<48} price=${inc['price']:<8} total=${inc['total']:<8} stable_qty={inc['stable_qty']} calc_qty={inc['calc_qty']}")

    if insufficient:
        print(f"\n  INSUFFICIENT DATA (need ≥2 price-matched entries for 'stable'):")
        for ins in insufficient:
            print(f"    {ins['name']:<48} price=${ins['price']:<8} occ={ins['occurrences']} price_match={ins['price_matches']} pattern={ins['qty_pattern']}")

    if no_matches:
        # Group by normalized key
        no_match_groups = defaultdict(int)
        for nm in no_matches:
            no_match_groups[nm.get("key", nm["name"][:30])] += 1
        print(f"\n  NO MATCH — {len(no_matches)} items from {len(no_match_groups)} unique products:")
        for key, count in sorted(no_match_groups.items(), key=lambda x: -x[1])[:15]:
            print(f"    [{count}x] {key}")

    # ── Section 5: OCR Variance Analysis ──
    print(f"\n  OCR VARIANCE ANALYSIS")
    print(f"  {'─' * 50}")
    # Find products that SHOULD match but don't due to OCR
    container_variants = [item for item in ambig_items if "CONTAINER" in item["name"].upper() and "FOAM" in item["name"].upper()]
    lemonade_variants = [item for item in ambig_items if "LEMONADE" in item["name"].upper()]
    crab_variants = [item for item in ambig_items if "CRAB" in item["name"].upper() or "KRAB" in item["name"].upper()]
    chicken_breast_variants = [item for item in ambig_items if "BRST TENDER" in item["name"].upper() or "BAST TENDER" in item["name"].upper() or "RST TENDER" in item["name"].upper()]

    ocr_groups = [
        ("CONTAINER FOAM", container_variants),
        ("DRINK MIX LEMONADE", lemonade_variants),
        ("CRAB CAKE", crab_variants),
        ("CHICKEN BREAST TENDER", chicken_breast_variants),
    ]

    for group_name, variants in ocr_groups:
        if variants:
            normalized_keys = set(_normalize_product_key(v["name"]) for v in variants)
            print(f"\n  {group_name}: {len(variants)} items, {len(normalized_keys)} unique normalized keys")
            for key in sorted(normalized_keys):
                print(f"    -> {key}")
            if len(normalized_keys) > 1:
                print(f"    ** OCR FRAGMENTATION: {len(normalized_keys)} keys should be 1")

    # ── Save Report ──
    validation_report = {
        "phase": "phase2.2_validation",
        "baseline": {
            "sysco_invoices": len(invoices),
            "total_line_items": total_items,
            "trusted": total_trusted,
            "memory_support": total_memory,
            "review": total_review,
            "false_trusts": total_false,
            "trust_rate": round(baseline_rate, 4),
        },
        "root_cause": {
            "db_storage_gap": True,
            "purchases_has_test_data": True,
            "receipt_extractions_missing_vendor": True,
            "extraction_results_not_persisted_correctly": True,
        },
        "simulation": {
            "cross_invoice_memory_size": memory.size,
            "cross_invoice_unique_products": memory.unique_products,
            "ambiguous_items_tested": len(ambig_items),
            "upgrade_eligible": len(upgrades),
            "inconsistencies": len(inconsistencies),
            "insufficient_data": len(insufficient),
            "no_match": len(no_matches),
            "upgrades_detail": upgrades,
            "inconsistencies_detail": inconsistencies,
        },
        "ocr_fragmentation": {
            "container_foam_variants": len(set(_normalize_product_key(v["name"]) for v in container_variants)),
            "lemonade_variants": len(set(_normalize_product_key(v["name"]) for v in lemonade_variants)),
            "crab_cake_variants": len(set(_normalize_product_key(v["name"]) for v in crab_variants)),
        },
        "conclusion": {
            "memory_produces_upgrades": len(upgrades) > 0,
            "trust_rate_improved": False,
            "blocking_issues": [
                "DB_STORAGE: Extraction results not saved with detected_vendor or confidence_level",
                "OCR_FRAGMENTATION: Same product generates multiple normalized keys due to OCR typos",
            ],
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(validation_report, f, indent=2)
    print(f"\n  Report saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    run_validation()
