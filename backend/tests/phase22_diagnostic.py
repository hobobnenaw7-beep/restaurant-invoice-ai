"""
Phase 2.2 Diagnostic: Why is Product Memory not producing upgrades?
Checks each ambiguous product from Phase 2 against the DB memory.
"""
import asyncio
import json
import re
import sys
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
from services.product_memory import ProductMemory, _normalize_product_key

REPORT_PATH = "/app/backend/tests/phase2_stress_report.json"


async def diagnose():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_database"]

    # Build memory from DB
    memory = ProductMemory()
    added = await memory.build_from_db(db)
    print(f"Memory built: {memory.size} entries, {memory.unique_products} unique products")
    print(f"  From DB: {added} entries\n")

    # Dump all memory products for inspection
    print("=" * 70)
    print("ALL PRODUCTS IN MEMORY")
    print("=" * 70)
    for key, entries in sorted(memory._products.items()):
        qtys = [e["qty"] for e in entries]
        prices = [e["price"] for e in entries]
        print(f"  {key:<45} entries={len(entries)} qtys={qtys} prices={prices}")

    # Load Phase 2 ambiguity log
    with open(REPORT_PATH) as f:
        report = json.load(f)

    ambig_items = report.get("ambiguity_pattern_log", [])
    print(f"\n{'=' * 70}")
    print(f"AMBIGUOUS ITEMS FROM PHASE 2 ({len(ambig_items)} total)")
    print(f"{'=' * 70}")

    # Group by normalized key
    grouped = defaultdict(list)
    for item in ambig_items:
        raw = item["name"]
        key = _normalize_product_key(raw)
        grouped[key].append(item)

    print(f"Unique normalized keys: {len(grouped)}")

    for key, items in sorted(grouped.items(), key=lambda x: -len(x[1])):
        count = len(items)
        price = items[0]["price"]
        raw_variants = list(set(it["name"][:50] for it in items))

        # Check memory lookup
        match = memory.lookup(items[0]["name"], price)
        calc_qty = round(items[0]["total"] / price, 2) if price > 0 else 0

        status = "NO MATCH"
        detail = ""
        if match.get("matched"):
            status = f"MATCHED (consistency={match['consistency']})"
            if match["consistency"] == "stable":
                sq = match["stable_qty"]
                if calc_qty == sq:
                    status = f"UPGRADE ELIGIBLE (stable_qty={sq}, calc_qty={calc_qty})"
                else:
                    status = f"INCONSISTENCY (stable_qty={sq}, calc_qty={calc_qty})"
            elif match["consistency"] == "insufficient":
                status = f"INSUFFICIENT DATA (occurrences={match['occurrences']}, price_matches={match['price_matches']})"
            detail = f"  qty_pattern={match.get('qty_pattern', {})}"

        print(f"\n  KEY: {key}")
        print(f"  Occurrences in Phase 2: {count}x | Price: ${price}")
        print(f"  OCR Variants: {raw_variants[:3]}")
        print(f"  Memory Status: {status}")
        if detail:
            print(f"  {detail}")

    # Summary
    match_count = 0
    upgrade_count = 0
    inconsistency_count = 0
    no_match_count = 0

    for key, items in grouped.items():
        price = items[0]["price"]
        match = memory.lookup(items[0]["name"], price)
        if not match.get("matched"):
            no_match_count += len(items)
        elif match["consistency"] == "stable":
            calc_qty = round(items[0]["total"] / price, 2) if price > 0 else 0
            if calc_qty == match["stable_qty"]:
                upgrade_count += len(items)
            else:
                inconsistency_count += len(items)
            match_count += len(items)
        else:
            match_count += len(items)

    print(f"\n{'=' * 70}")
    print(f"DIAGNOSTIC SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total ambiguous items: {len(ambig_items)}")
    print(f"  No match in memory: {no_match_count}")
    print(f"  Matched but insufficient: {match_count - upgrade_count - inconsistency_count}")
    print(f"  Matched with inconsistency: {inconsistency_count}")
    print(f"  Upgrade eligible: {upgrade_count}")

    client.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
