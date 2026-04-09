"""
Phase 2 Sysco Pipeline Stress Test: 50 files (15 Phase 1 + 35 new unique).
Reports: trusted/review split, false trusts, partial/complete, vendor distribution,
ambiguity pattern log for qty=1 items.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"

PHASE2_FILES = [
    "296c4a30-127b-4252-ae72-84f5dfb75212.jpg",
    "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    "cc7dc90b-f682-4d5d-91fc-36de6439c60b.jpg",
    "e76577bc-bc4c-45ce-a99a-db566eef0393.jpg",
    "receipt_20ea1a7e-762c-4e82-8c1d-bbdae92594d1.jpg",
    "receipt_333073da-edec-481e-9f49-f5b8199a15c3.jpg",
    "receipt_46ad2974-1de8-4a48-97cd-5622e4599da0.jpg",
    "receipt_801ef80d-14d3-40ff-a582-a8bdf696258a.jpg",
    "receipt_833003c8-7172-4ec6-9201-3dbb683561e5.jpg",
    "receipt_a33f716a-bf00-4204-ac2f-faa646d75042.jpg",
    "receipt_dabe0e27-5924-4ad2-8d53-d20b89001517.jpg",
    "receipt_e50c2bf6-5bd2-4fe4-a740-6bcef6917b14.jpg",
    "receipt_e5a037b0-8aa1-4537-9687-7a0525491faf.jpg",
    "95ebb38a-6d7e-4606-83f1-ec2a0f2a6d15.jpg",
    "receipt_458ec34d-8deb-44e5-9948-ed068ca80761.png",
    "receipt_aa140bda-813d-455e-ab65-a34422d7fc1e.jpg",
    "receipt_c912c288-927c-4aa7-99ad-ac54964c9aa5.jpg",
    "receipt_79a254d0-15eb-4417-9432-f12470fecfd7.png",
    "receipt_0ad1fb34-bbcf-4a9c-a6df-39ecf8ebba35.jpg",
    "receipt_236cda56-6a67-4243-8b3d-32d391306a62.png",
    "receipt_000a71bb-a857-4b2d-bd9e-3ca72161fceb.jpg",
    "receipt_e679742e-b319-4d96-8d83-e5fa6468106b.jpg",
    "receipt_450d9d1e-1fa4-4d7d-9b9b-49655e959ed4.jpg",
    "receipt_201c7a1b-3f32-4994-9611-208d79b204d4.jpg",
    "receipt_04211076-2479-4c08-a17a-7baa6f00109a.png",
    "4881f8bb-2b5a-4dd1-ba9f-16033c50d936.jpg",
    "receipt_3219b800-5e1f-48cb-9850-b3a590d04c14.jpg",
    "receipt_bf5af1a1-7267-425b-9660-c05405fefd99.jpg",
    "receipt_213ca1ff-4de8-4c8a-9f3a-0a4e8021ba68.jpg",
    "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",
    "receipt_c88bce30-7a97-4dca-9abb-01e3f6707f77.jpg",
    "receipt_cf40bd1e-2659-4d37-9c95-b46e317f8155.jpg",
    "receipt_c0ac94f6-8d20-4530-83f1-684324555115.jpg",
    "receipt_70f3ed3f-f7e1-4973-b3c9-fd9c64fd86c0.jpg",
    "receipt_ac9e8d86-8c4e-481b-ad5c-2ad65a8f1d7f.jpg",
    "receipt_a2852a6f-66e8-46a9-bb11-b00438cff039.jpg",
    "304be2e0-8cf2-4862-abf8-396c63796e81.jpg",
    "receipt_93d39617-1550-4055-bfac-793519c49ce2.jpg",
    "receipt_06ce771b-bd02-48c8-b309-f6ed1e2b796c.png",
    "receipt_27cdefe4-fbba-45c4-88ad-db1968f5674a.jpg",
    "5796acad-0e73-497e-a5d1-8e6c314f2d32.jpg",
    "061bdd86-d324-4138-b940-5b5f19f233f3.jpg",
    "receipt_2c862a65-0d98-4c3b-a745-a117c8f1f315.png",
    "1600af34-b3e5-4f05-96aa-cf553c777bc4.jpg",
    "receipt_c227970f-be14-4d52-9186-c6d63b0062b9.jpg",
    "receipt_5ff63026-250a-43bb-bd7e-7b8f331df374.jpg",
    "15f89c02-de1d-470c-9d1a-a4f22918db32.jpg",
    "receipt_5287cf4a-5328-408a-af27-2749e0bba90d.jpg",
    "receipt_cfd74e65-2ac6-44fe-b982-49e57c25e26a.jpg",
    "9e70d872-9c3a-46f2-825f-2c506e757d09.jpg",
]

UPLOADS_DIR = "/app/backend/uploads"
REPORT_PATH = "/app/backend/tests/phase2_stress_report.json"


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword",
    })
    resp.raise_for_status()
    return resp.json()["token"]


def extract_invoice(filepath, token):
    fname = os.path.basename(filepath)
    content_type = "image/png" if fname.endswith(".png") else "image/jpeg"
    with open(filepath, "rb") as f:
        files = {"file": (fname, f, content_type)}
        data = {"document_type": "purchase_invoice"}
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(
            f"{API_URL}/api/upload/extract",
            files=files, data=data, headers=headers, timeout=120,
        )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    return resp.json()


def analyze_result(fname, result):
    if "error" in result and isinstance(result["error"], str):
        return {"file": fname, "error": result["error"]}

    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])
    vendor = result.get("detected_vendor", data.get("supplier_name", ""))
    vendor_lower = (vendor or "").lower()

    is_sysco = "sysco" in vendor_lower
    is_pfg = "performance" in vendor_lower or "pfg" in vendor_lower
    is_usfoods = "us foods" in vendor_lower or "usfoods" in vendor_lower

    if is_sysco:
        vendor_class = "Sysco"
    elif is_pfg:
        vendor_class = "PFG"
    elif is_usfoods:
        vendor_class = "US Foods"
    elif vendor and vendor.upper() != "UNKNOWN":
        vendor_class = f"Other ({vendor[:30]})"
    else:
        vendor_class = "Unknown"

    line_items = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    excluded = [it for it in items if it.get("confidence_level") == "excluded"]
    trusted = [it for it in line_items if it.get("confidence_level") == "trusted"]
    memory_support = [it for it in line_items if it.get("confidence_level") == "review_with_memory_support"]
    review = [it for it in line_items if it.get("needs_review", False)]
    vendor_pending = [it for it in line_items if it.get("confidence_level") == "vendor_logic_pending"]

    # Failure categories
    failure_cats = {}
    for it in review:
        cat = it.get("numeric_failure_category", "unknown")
        if it.get("confidence_level") == "vendor_logic_pending":
            cat = "vendor_logic_pending"
        failure_cats[cat] = failure_cats.get(cat, 0) + 1

    # False trust check
    false_trusts = []
    for it in trusted:
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        if qty <= 0 or price <= 0 or total <= 0:
            false_trusts.append({"name": it.get("raw_name", "")[:50], "reason": f"zero: q={qty} p={price} t={total}"})
        else:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            if diff > 0.01:
                false_trusts.append({"name": it.get("raw_name", "")[:50], "reason": f"math: {qty}*{price}={computed}!={total}"})
        for field, src_key in [("qty", "qty_source"), ("price", "price_source"), ("total", "total_source")]:
            src = (it.get(src_key) or "").lower()
            if src not in ("column_read",):
                false_trusts.append({"name": it.get("raw_name", "")[:50], "reason": f"{field}_source='{src}'"})
                break

    # Ambiguity pattern log (qty=1 items with source_not_column_read)
    ambiguity_log = []
    # Full qty distribution for audit
    qty_distribution = {}
    for it in line_items:
        qty = float(it.get("quantity", 0) or 0)
        qty_key = str(int(qty)) if qty == int(qty) else str(qty)
        qty_distribution[qty_key] = qty_distribution.get(qty_key, 0) + 1

        if qty == 1.0 and it.get("numeric_failure_category") == "source_not_column_read":
            ambiguity_log.append({
                "name": (it.get("raw_name") or "")[:50],
                "price": it.get("unit_price"),
                "total": it.get("total"),
                "qty_source": it.get("qty_source", "?"),
                "price_source": it.get("price_source", "?"),
                "total_source": it.get("total_source", "?"),
                "review_reason": (it.get("review_reason") or "")[:80],
            })

    return {
        "file": fname,
        "vendor_detected": vendor,
        "vendor_class": vendor_class,
        "is_sysco": is_sysco,
        "total_items_returned": len(items),
        "extracted_line_items": len(line_items),
        "trusted_count": len(trusted),
        "memory_support_count": len(memory_support),
        "review_count": len(review),
        "vendor_pending_count": len(vendor_pending),
        "excluded_count": len(excluded),
        "false_trusts": false_trusts,
        "false_trust_count": len(false_trusts),
        "failure_categories": failure_cats,
        "merchandise_subtotal": data.get("_sysco_merchandise_subtotal", 0),
        "subtotal_match": data.get("_sysco_subtotal_match", False),
        "is_partial_page": data.get("_sysco_is_partial_page", False),
        "invoice_completeness": data.get("_invoice_completeness", "unknown"),
        "declared_subtotal": float(data.get("subtotal", 0) or 0),
        "ambiguity_log": ambiguity_log,
        "qty_distribution": qty_distribution,
        "usfoods_detail": {
            "item_codes_found": sum(1 for it in line_items if (it.get("item_code") or "").strip()),
            "math_pass": sum(1 for it in line_items if it.get("valid_calc")),
            "math_fail": sum(1 for it in line_items if not it.get("valid_calc") and it.get("row_type") in ("line_item", "fee")),
        } if is_usfoods else None,
        "product_memory_stats": data.get("_product_memory_stats", {}) if is_sysco else None,
        "memory_support_detail": [
            {
                "name": (it.get("raw_name") or "")[:50],
                "qty": it.get("quantity"),
                "price": it.get("unit_price"),
                "total": it.get("total"),
                "item_code": (it.get("item_code") or "")[:15],
                "stable_qty": it.get("_memory_stable_qty"),
                "calc_qty": it.get("_memory_calc_qty"),
                "qty1_support": it.get("_memory_qty1_support", False),
                "match_method": (it.get("_memory_match") or {}).get("match_method", "?"),
                "review_reason": (it.get("review_reason") or "")[:120],
            }
            for it in memory_support
        ] if is_sysco else None,
        "trusted_items_detail": [
            {"name": it.get("raw_name", "")[:50], "qty": it.get("quantity"), "price": it.get("unit_price"), "total": it.get("total")}
            for it in trusted
        ],
    }


def run_phase2():
    print("=" * 70)
    print(f"PHASE 2: STRESS TEST ({len(PHASE2_FILES)} files)")
    print("=" * 70)

    token = login()
    print(f"Auth token acquired.\n")

    results = []
    for idx, fname in enumerate(PHASE2_FILES):
        fpath = os.path.join(UPLOADS_DIR, fname)
        print(f"{'─'*70}")
        print(f"[{idx+1}/{len(PHASE2_FILES)}] {fname}")

        if not os.path.exists(fpath):
            print(f"  FILE NOT FOUND — skipping")
            results.append({"file": fname, "error": "FILE_NOT_FOUND"})
            continue

        fsize_kb = os.path.getsize(fpath) // 1024
        t0 = time.time()
        try:
            raw = extract_invoice(fpath, token)
            elapsed = time.time() - t0
            a = analyze_result(fname, raw)

            if "error" in a:
                print(f"  ERROR ({elapsed:.0f}s): {a['error']}")
                a["api_time_sec"] = round(elapsed, 1)
                results.append(a)
                continue

            a["api_time_sec"] = round(elapsed, 1)
            a["file_size_kb"] = fsize_kb
            results.append(a)

            v = a.get("vendor_class", "?")
            trust_label = f"{a['trusted_count']}T/{a.get('memory_support_count',0)}M" if a.get("is_sysco") else f"{a.get('vendor_pending_count',0)}VP"
            print(f"  {elapsed:.0f}s | {v:<12} | {a['extracted_line_items']} items | {trust_label} | {a['review_count']}R | {a['excluded_count']}X | compl={a.get('invoice_completeness','?')}")

            if a.get("false_trusts"):
                for ft in a["false_trusts"]:
                    print(f"  *** FALSE TRUST: {ft['name']}: {ft['reason']}")

            # Show memory upgrades
            if a.get("memory_support_count", 0) > 0:
                for m in (a.get("memory_support_detail") or []):
                    print(f"  >> MEMORY SUPPORT: {m['name'][:40]} qty1={m.get('qty1_support')} method={m.get('match_method')}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  EXCEPTION ({elapsed:.0f}s): {e}")
            results.append({"file": fname, "error": str(e), "api_time_sec": round(elapsed, 1)})

    # ═════════════════════════════════════════════════════════════════
    # AGGREGATE SUMMARY
    # ═════════════════════════════════════════════════════════════════
    print(f"\n\n{'═'*70}")
    print(f"PHASE 2 SUMMARY ({len(PHASE2_FILES)} files)")
    print(f"{'═'*70}")

    successful = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    sysco = [r for r in successful if r.get("is_sysco")]
    non_sysco = [r for r in successful if not r.get("is_sysco")]

    print(f"\nProcessed: {len(successful)}/{len(PHASE2_FILES)} | Errors: {len(errors)}")

    # ── Vendor Distribution ──
    from collections import Counter
    vendors = Counter(r.get("vendor_class", "?") for r in successful)
    print(f"\nVendor Distribution:")
    for v, c in vendors.most_common():
        print(f"  {v}: {c} invoices")

    # ── SYSCO Results ──
    print(f"\n{'─'*40}")
    print(f"SYSCO INVOICES ({len(sysco)})")
    print(f"{'─'*40}")
    s_items = sum(r.get("extracted_line_items", 0) for r in sysco)
    s_trusted = sum(r.get("trusted_count", 0) for r in sysco)
    s_memory = sum(r.get("memory_support_count", 0) for r in sysco)
    s_review = sum(r.get("review_count", 0) for r in sysco)
    s_excluded = sum(r.get("excluded_count", 0) for r in sysco)
    s_false = sum(r.get("false_trust_count", 0) for r in sysco)
    print(f"  Line items: {s_items}")
    print(f"  TRUSTED:    {s_trusted}")
    print(f"  MEMORY_SUPPORT: {s_memory}")
    print(f"  REVIEW:     {s_review}")
    print(f"  EXCLUDED:   {s_excluded}")
    print(f"  FALSE TRUST:{s_false}")
    if s_items > 0:
        print(f"  Trust rate: {s_trusted}/{s_items} = {s_trusted/s_items:.0%}")
        print(f"  Trust+Memory rate: {s_trusted+s_memory}/{s_items} = {(s_trusted+s_memory)/s_items:.0%}")

    # Completeness
    compl = Counter(r.get("invoice_completeness", "?") for r in sysco)
    print(f"  Completeness: {dict(compl)}")

    # Failure categories (Sysco only)
    s_cats = {}
    for r in sysco:
        for cat, count in r.get("failure_categories", {}).items():
            s_cats[cat] = s_cats.get(cat, 0) + count
    print(f"  Failure categories:")
    for cat, count in sorted(s_cats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    # ── NON-SYSCO Results ──
    if non_sysco:
        print(f"\n{'─'*40}")
        print(f"NON-SYSCO INVOICES ({len(non_sysco)})")
        print(f"{'─'*40}")
        ns_items = sum(r.get("extracted_line_items", 0) for r in non_sysco)
        ns_vp = sum(r.get("vendor_pending_count", 0) for r in non_sysco)
        ns_trusted = sum(r.get("trusted_count", 0) for r in non_sysco)
        print(f"  Line items: {ns_items}")
        print(f"  Vendor Logic Pending: {ns_vp}")
        print(f"  Trusted (should be 0): {ns_trusted}")
        for r in non_sysco:
            v = r.get("vendor_class", "?")
            usf = ""
            if r.get("usfoods_detail"):
                d = r["usfoods_detail"]
                usf = f" | codes={d['item_codes_found']} math_pass={d['math_pass']} math_fail={d['math_fail']}"
            print(f"    {r['file'][:30]:<32} {v:<15} {r.get('extracted_line_items',0)} items, {r.get('vendor_pending_count',0)} pending{usf}")

    # ── PRODUCT MEMORY ANALYSIS ──
    print(f"\n{'─'*40}")
    print(f"PRODUCT MEMORY CROSS-VALIDATION")
    print(f"{'─'*40}")
    total_mem_matches = 0
    total_mem_upgrades = 0
    all_inconsistencies = []
    for r in sysco:
        ms = r.get("product_memory_stats") or {}
        total_mem_matches += ms.get("matches_found", 0)
        total_mem_upgrades += ms.get("upgraded_to_memory_support", 0)
        for inc in ms.get("inconsistencies", []):
            inc["file"] = r["file"][:25]
            all_inconsistencies.append(inc)
    print(f"  Memory matches found: {total_mem_matches}")
    print(f"  Upgraded to review_with_memory_support: {total_mem_upgrades}")
    print(f"  Inconsistencies detected: {len(all_inconsistencies)}")

    if total_mem_upgrades > 0:
        print(f"\n  MEMORY-SUPPORTED ITEMS:")
        for r in sysco:
            for m in (r.get("memory_support_detail") or []):
                print(f"    {m['name']:<45} qty={m['qty']} price=${m['price']} total=${m['total']} stable_qty={m.get('stable_qty')}")

    if all_inconsistencies:
        print(f"\n  INCONSISTENCIES:")
        for inc in all_inconsistencies:
            print(f"    {inc['file']} | {inc['product']:<35} price=${inc['price']} total=${inc['total']} memory_qty={inc['memory_stable_qty']} calc_qty={inc['calculated_qty']}")

    # ── SYSCO QTY VALUE DISTRIBUTION AUDIT ──
    print(f"\n{'─'*40}")
    print(f"SYSCO QTY VALUE DISTRIBUTION")
    print(f"{'─'*40}")
    all_qty_dist = {}
    for r in sysco:
        for k, v in r.get("qty_distribution", {}).items():
            all_qty_dist[k] = all_qty_dist.get(k, 0) + v
    for k in sorted(all_qty_dist.keys(), key=lambda x: float(x)):
        pct = all_qty_dist[k] / sum(all_qty_dist.values()) * 100
        bar = "#" * int(pct / 2)
        print(f"  qty={k:>4}: {all_qty_dist[k]:>4} items ({pct:>5.1f}%) {bar}")

    # ── AMBIGUITY PATTERN LOG ──
    print(f"\n{'─'*40}")
    print(f"AMBIGUITY PATTERN LOG (qty=1 trap)")
    print(f"{'─'*40}")
    all_ambig = []
    for r in sysco:
        for a in r.get("ambiguity_log", []):
            a["file"] = r["file"][:25]
            all_ambig.append(a)

    print(f"  Total qty=1 ambiguous items: {len(all_ambig)}")

    # Analyze recurring patterns
    if all_ambig:
        # Group by source combination
        src_patterns = Counter(
            f"qty={a['qty_source']}, price={a['price_source']}, total={a['total_source']}"
            for a in all_ambig
        )
        print(f"\n  Source patterns:")
        for pat, count in src_patterns.most_common():
            print(f"    [{count}x] {pat}")

        # Group by product name (fuzzy — first 25 chars)
        name_patterns = Counter(a["name"][:25] for a in all_ambig)
        print(f"\n  Top recurring products (qty=1 ambiguous):")
        for name, count in name_patterns.most_common(10):
            print(f"    [{count}x] {name}")

        # Price patterns (same price repeated = likely total being read as price)
        prices = Counter(a["price"] for a in all_ambig)
        print(f"\n  Price clustering (same price across invoices):")
        for price, count in prices.most_common(10):
            if count >= 2:
                print(f"    ${price}: appears {count}x")

    # ── ERRORS ──
    if errors:
        print(f"\n{'─'*40}")
        print(f"ERRORS ({len(errors)})")
        print(f"{'─'*40}")
        for e in errors:
            print(f"  {e['file'][:40]}: {str(e.get('error',''))[:60]}")

    # ── PER-INVOICE TABLE ──
    print(f"\n{'─'*120}")
    print(f"{'File':<28} {'Vendor':<13} {'Line':>5} {'Trust':>6} {'MemS':>5} {'Revw':>5} {'VP':>4} {'Excl':>5} {'FT':>4} {'Compl':<10} {'Time':>6}")
    print(f"{'─'*120}")
    for r in successful:
        f = r["file"][:27]
        v = r.get("vendor_class", "?")[:12]
        c = (r.get("invoice_completeness") or "?")[:9]
        print(f"{f:<28} {v:<13} {r.get('extracted_line_items',0):>5} {r.get('trusted_count',0):>6} {r.get('memory_support_count',0):>5} {r.get('review_count',0):>5} {r.get('vendor_pending_count',0):>4} {r.get('excluded_count',0):>5} {r.get('false_trust_count',0):>4} {c:<10} {r.get('api_time_sec',0):>5.1f}s")

    # Timing
    times = [r.get("api_time_sec", 0) for r in successful if r.get("api_time_sec", 0) > 0]
    if times:
        print(f"\nTiming: avg={sum(times)/len(times):.1f}s | min={min(times):.1f}s | max={max(times):.1f}s | total={sum(times)/60:.1f}min")

    # ── SAVE REPORT ──
    report = {
        "phase": "phase2",
        "total_files": len(PHASE2_FILES),
        "successful": len(successful),
        "errors": len(errors),
        "vendor_distribution": dict(vendors),
        "sysco_summary": {
            "invoices": len(sysco),
            "line_items": s_items,
            "trusted": s_trusted,
            "memory_support": s_memory,
            "review": s_review,
            "excluded": s_excluded,
            "false_trusts": s_false,
            "trust_rate": round(s_trusted / s_items, 4) if s_items > 0 else 0,
            "trust_plus_memory_rate": round((s_trusted + s_memory) / s_items, 4) if s_items > 0 else 0,
            "completeness": dict(compl),
            "failure_categories": s_cats,
            "product_memory": {
                "matches_found": total_mem_matches,
                "upgraded_to_memory_support": total_mem_upgrades,
                "inconsistencies": len(all_inconsistencies),
            },
        },
        "non_sysco_summary": {
            "invoices": len(non_sysco),
            "line_items": sum(r.get("extracted_line_items", 0) for r in non_sysco),
            "vendor_pending": sum(r.get("vendor_pending_count", 0) for r in non_sysco),
            "trusted": sum(r.get("trusted_count", 0) for r in non_sysco),
        },
        "ambiguity_pattern_log": all_ambig,
        "invoices": results,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report: {REPORT_PATH}")


if __name__ == "__main__":
    run_phase2()
