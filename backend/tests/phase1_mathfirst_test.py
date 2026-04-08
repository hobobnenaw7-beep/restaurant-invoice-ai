"""
Phase 1 Stress Test: Sysco Math-First Pipeline via API
Sends 15 diverse Sysco invoices through the full /api/upload/extract endpoint.
Reports per-invoice breakdown: trusted, review, false-trust, failure categories.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"

# Same 15 files from Phase 1 (includes 4 duplicate pairs)
PHASE1_FILES = [
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
]

UPLOADS_DIR = "/app/backend/uploads"
REPORT_PATH = "/app/backend/tests/phase1_mathfirst_report.json"


def login():
    """Login and get auth token."""
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com",
        "password": "testpassword",
    })
    resp.raise_for_status()
    return resp.json()["token"]


def extract_invoice(filepath, token):
    """Upload a file to /api/upload/extract and return the result."""
    fname = os.path.basename(filepath)
    content_type = "image/png" if fname.endswith(".png") else "image/jpeg"

    with open(filepath, "rb") as f:
        files = {"file": (fname, f, content_type)}
        data = {"document_type": "purchase_invoice"}
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(
            f"{API_URL}/api/upload/extract",
            files=files,
            data=data,
            headers=headers,
            timeout=120,
        )

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

    return resp.json()


def analyze_result(fname, result):
    """Analyze a single extraction result and return structured findings."""
    if "error" in result and isinstance(result["error"], str):
        return {
            "file": fname,
            "error": result["error"],
            "extracted_items": 0,
            "trusted_count": 0,
            "review_count": 0,
            "excluded_count": 0,
            "failure_categories": {},
        }

    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])

    line_items = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    excluded = [it for it in items if it.get("confidence_level") == "excluded"]
    trusted = [it for it in line_items if it.get("confidence_level") == "trusted"]
    review = [it for it in line_items if it.get("needs_review", False)]

    # Failure category breakdown
    failure_cats = {}
    for it in review:
        cat = it.get("numeric_failure_category", "unknown")
        failure_cats[cat] = failure_cats.get(cat, 0) + 1

    # False trust check: verify each trusted item's math ourselves
    false_trusts = []
    for it in trusted:
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        total = float(it.get("total", 0) or 0)
        if qty <= 0 or price <= 0 or total <= 0:
            false_trusts.append({
                "name": it.get("raw_name", "")[:50],
                "reason": f"zero value: qty={qty}, price={price}, total={total}",
            })
        else:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            if diff > 0.01:
                false_trusts.append({
                    "name": it.get("raw_name", "")[:50],
                    "reason": f"math fail: {qty}×{price}={computed} ≠ {total} (diff={diff})",
                })

    # Check sources for trusted items
    for it in trusted:
        for field, src_key in [("qty", "qty_source"), ("price", "price_source"), ("total", "total_source")]:
            src = (it.get(src_key) or "").lower()
            if src not in ("column_read",):
                false_trusts.append({
                    "name": it.get("raw_name", "")[:50],
                    "reason": f"{field}_source='{src}' (not column_read)",
                })
                break  # one flag per item is enough

    return {
        "file": fname,
        "vendor_detected": result.get("detected_vendor", data.get("supplier_name", "")),
        "invoice_number": data.get("invoice_number", ""),
        "invoice_date": data.get("invoice_date", ""),
        "total_items_returned": len(items),
        "extracted_line_items": len(line_items),
        "trusted_count": len(trusted),
        "review_count": len(review),
        "excluded_count": len(excluded),
        "false_trusts": false_trusts,
        "false_trust_count": len(false_trusts),
        "failure_categories": failure_cats,
        "merchandise_subtotal": data.get("_sysco_merchandise_subtotal", 0),
        "subtotal_match": data.get("_sysco_subtotal_match", False),
        "declared_subtotal": float(data.get("subtotal", 0) or 0),
        "declared_total": float(data.get("total", 0) or 0),
        "declared_tax": float(data.get("tax", 0) or 0),
        "trusted_items_detail": [
            {
                "name": it.get("raw_name", "")[:50],
                "qty": it.get("quantity"),
                "price": it.get("unit_price"),
                "total": it.get("total"),
                "qty_source": it.get("qty_source"),
                "price_source": it.get("price_source"),
                "total_source": it.get("total_source"),
                "math_ok": it.get("valid_calc"),
            }
            for it in trusted
        ],
        "review_items_detail": [
            {
                "name": it.get("raw_name", "")[:50],
                "qty": it.get("quantity"),
                "price": it.get("unit_price"),
                "total": it.get("total"),
                "category": it.get("numeric_failure_category", "unknown"),
                "reason": (it.get("review_reason") or "")[:80],
            }
            for it in review
        ],
    }


def run_phase1():
    print("=" * 70)
    print("PHASE 1: SYSCO MATH-FIRST STRESS TEST (GPT Vision + Hard Gate)")
    print("=" * 70)

    print("\nStep 1: Logging in...")
    token = login()
    print(f"  Auth token acquired.\n")

    results = []

    for idx, fname in enumerate(PHASE1_FILES):
        fpath = os.path.join(UPLOADS_DIR, fname)
        print(f"{'─'*70}")
        print(f"[{idx+1}/{len(PHASE1_FILES)}] {fname}")

        if not os.path.exists(fpath):
            print(f"  FILE NOT FOUND — skipping")
            results.append({"file": fname, "error": "FILE_NOT_FOUND"})
            continue

        fsize_kb = os.path.getsize(fpath) // 1024
        print(f"  Size: {fsize_kb}KB")

        t0 = time.time()
        try:
            raw_result = extract_invoice(fpath, token)
            elapsed = time.time() - t0
            print(f"  API response: {elapsed:.1f}s")

            analysis = analyze_result(fname, raw_result)
            analysis["api_time_sec"] = round(elapsed, 1)
            results.append(analysis)

            print(f"  Vendor: {analysis.get('vendor_detected', '?')}")
            print(f"  Items: {analysis['extracted_line_items']} line | {analysis['trusted_count']} trusted | {analysis['review_count']} review | {analysis['excluded_count']} excluded")
            print(f"  False trusts: {analysis['false_trust_count']}")
            print(f"  Subtotal: merch=${analysis.get('merchandise_subtotal',0):.2f} vs declared=${analysis.get('declared_subtotal',0):.2f} | match={analysis.get('subtotal_match', False)}")

            if analysis.get("failure_categories"):
                cats = analysis["failure_categories"]
                print(f"  Failure cats: {cats}")

            if analysis.get("trusted_items_detail"):
                print(f"  TRUSTED:")
                for t in analysis["trusted_items_detail"]:
                    print(f"    [{t['qty_source'][:3]}|{t['price_source'][:3]}|{t['total_source'][:3]}] {t['name']:<40} qty={t['qty']:<5} price=${t['price']:<8} total=${t['total']}")

            if analysis.get("false_trusts"):
                print(f"  *** FALSE TRUSTS:")
                for ft in analysis["false_trusts"]:
                    print(f"    {ft['name']}: {ft['reason']}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ERROR after {elapsed:.1f}s: {e}")
            results.append({"file": fname, "error": str(e), "api_time_sec": round(elapsed, 1)})

    # ═══════════════════════════════════════════════════════════════════
    # AGGREGATE SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n\n{'═'*70}")
    print(f"PHASE 1 MATH-FIRST SUMMARY")
    print(f"{'═'*70}")

    successful = [r for r in results if "error" not in r or r.get("extracted_line_items", 0) > 0]
    errors = [r for r in results if "error" in r and r.get("extracted_line_items", 0) == 0]

    print(f"Invoices processed: {len(successful)}/{len(PHASE1_FILES)}")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  {e['file']}: {e.get('error','?')[:60]}")

    total_line = sum(r.get("extracted_line_items", 0) for r in successful)
    total_trusted = sum(r.get("trusted_count", 0) for r in successful)
    total_review = sum(r.get("review_count", 0) for r in successful)
    total_excluded = sum(r.get("excluded_count", 0) for r in successful)
    total_false = sum(r.get("false_trust_count", 0) for r in successful)

    print(f"\n{'─'*40}")
    print(f"Total line items: {total_line}")
    print(f"TRUSTED:          {total_trusted}")
    print(f"REVIEW:           {total_review}")
    print(f"EXCLUDED:         {total_excluded}")
    print(f"FALSE TRUSTS:     {total_false}")
    if total_line > 0:
        print(f"Trust rate: {total_trusted}/{total_line} = {total_trusted/total_line:.0%}")
    print(f"{'─'*40}")

    # All failure categories
    all_cats = {}
    for r in successful:
        for cat, count in r.get("failure_categories", {}).items():
            all_cats[cat] = all_cats.get(cat, 0) + count
    print(f"\nFailure categories:")
    for cat, count in sorted(all_cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Subtotal match stats
    sub_match = sum(1 for r in successful if r.get("subtotal_match"))
    print(f"\nMerchandise subtotal match: {sub_match}/{len(successful)}")

    # Per-invoice table
    print(f"\n{'─'*110}")
    hdr = f"{'File':<28} {'Vendor':<10} {'Line':>5} {'Trust':>6} {'Revw':>5} {'Excl':>5} {'False':>6} {'SubM':>5} {'Time':>6}"
    print(hdr)
    print(f"{'─'*110}")
    for r in successful:
        f = r["file"][:27]
        v = (r.get("vendor_detected") or "")[:9]
        print(f"{f:<28} {v:<10} {r.get('extracted_line_items',0):>5} {r.get('trusted_count',0):>6} {r.get('review_count',0):>5} {r.get('excluded_count',0):>5} {r.get('false_trust_count',0):>6} {'Y' if r.get('subtotal_match') else 'N':>5} {r.get('api_time_sec',0):>5.1f}s")

    # Timing
    times = [r.get("api_time_sec", 0) for r in successful if r.get("api_time_sec", 0) > 0]
    if times:
        print(f"\nTiming: avg={sum(times)/len(times):.1f}s | min={min(times):.1f}s | max={max(times):.1f}s | total={sum(times):.0f}s")

    # Camera photo analysis
    camera_trusted = 0
    png_trusted = 0
    for r in successful:
        if r["file"].endswith(".png"):
            png_trusted += r.get("trusted_count", 0)
        else:
            camera_trusted += r.get("trusted_count", 0)
    print(f"\nCamera photo (JPG) trusted items: {camera_trusted}")
    print(f"Clean image (PNG) trusted items:  {png_trusted}")

    # Save report
    report = {
        "phase": "phase1_mathfirst",
        "approach": "GPT Vision read-only + deterministic math gate ($0.01 tolerance)",
        "total_files": len(PHASE1_FILES),
        "successful": len(successful),
        "errors": len(errors),
        "summary": {
            "total_line_items": total_line,
            "trusted": total_trusted,
            "review": total_review,
            "excluded": total_excluded,
            "false_trusts": total_false,
            "trust_rate": round(total_trusted / total_line, 4) if total_line > 0 else 0,
            "subtotal_match_count": sub_match,
            "failure_categories": all_cats,
            "camera_trusted": camera_trusted,
            "png_trusted": png_trusted,
        },
        "invoices": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    run_phase1()
