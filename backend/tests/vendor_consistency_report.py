"""
3-Vendor Consistency Report
============================
Runs each vendor's sample invoice(s) 3 times each.
For every run, captures:
  - Item count, trusted count, review count, false trusts
  - Per-row math verification (qty * price = total)
  - Field sources (column_read vs ambiguous)
  - Trust rate consistency across runs

Produces a full evidence report showing BEFORE (raw extraction) vs AFTER (trust gate) for each vendor.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
NUM_RUNS = 3

VENDOR_SAMPLES = {
    "SYSCO": [
        "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    ],
    "US_FOODS": [
        "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",
    ],
    "PFG": [
        "receipt_20b24d09-5761-4c09-aca6-6925cb235a55.png",
    ],
}


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com", "password": "testpassword",
    })
    resp.raise_for_status()
    return resp.json()["token"]


def extract_invoice(filepath, token):
    fname = os.path.basename(filepath)
    ct = "image/png" if fname.endswith(".png") else "image/jpeg"
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{API_URL}/api/upload/extract",
            files={"file": (fname, f, ct)},
            data={"document_type": "purchase_invoice"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=180,
        )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    return resp.json()


def analyze_run(result):
    """Analyze a single extraction run and return structured metrics."""
    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])
    vendor = result.get("detected_vendor", data.get("supplier_name", ""))

    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    review = [it for it in scoreable if it.get("confidence_level") not in ("trusted", "excluded")]

    false_trusts = 0
    row_details = []

    for idx, it in enumerate(scoreable):
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        gates = td.get("gates", {})

        name = (ext.get("raw_name") or it.get("raw_name") or "?")[:60]
        item_code = ext.get("item_code", it.get("item_code", ""))
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)
        pack = (ext.get("pack_size") or it.get("pack_size") or "")[:25]

        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))
        reason = td.get("reason", "")[:100]
        failure_cat = td.get("failure_category", "")

        qty_src = gates.get("qty_source", it.get("qty_source", "?"))
        price_src = gates.get("price_source", it.get("price_source", "?"))
        total_src = gates.get("total_source", it.get("total_source", "?"))
        math_check = gates.get("math_check", "?")
        vis = it.get("qty_column_visible", gates.get("qty_column_visible", "?"))

        # Math verification
        math_pass = False
        math_detail = "incomplete"
        if row_type == "fee":
            math_pass = total > 0
            math_detail = f"fee: total={total} > 0 = {math_pass}"
        elif qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            math_pass = diff <= 0.01
            math_detail = f"{qty} x {price} = {computed} vs {total} (diff=${diff:.2f})"
            if status == "trusted" and not math_pass:
                false_trusts += 1

        row_details.append({
            "idx": idx + 1,
            "name": name,
            "item_code": item_code,
            "qty": qty,
            "price": price,
            "total": total,
            "pack": pack,
            "row_type": row_type,
            "status": status,
            "reason": reason,
            "failure_cat": failure_cat,
            "qty_src": qty_src,
            "price_src": price_src,
            "total_src": total_src,
            "math_check": math_check,
            "math_pass": math_pass,
            "math_detail": math_detail,
            "vis": vis,
        })

    return {
        "vendor": vendor,
        "total_scoreable": len(scoreable),
        "trusted": len(trusted),
        "review": len(review),
        "trust_rate": round(len(trusted) / len(scoreable) * 100, 1) if scoreable else 0,
        "false_trusts": false_trusts,
        "items_with_price": sum(1 for it in scoreable if float(it.get("unit_price", 0) or 0) > 0),
        "items_with_total": sum(1 for it in scoreable if float(it.get("total", 0) or 0) > 0),
        "items_with_qty": sum(1 for it in scoreable if float(it.get("quantity", 0) or 0) > 0),
        "rows": row_details,
        "subtotal": float(data.get("subtotal", 0) or 0),
        "tax": float(data.get("tax", 0) or 0),
        "total_invoice": float(data.get("total", 0) or 0),
    }


def print_vendor_report(vendor_label, file_results):
    """Print detailed report for one vendor."""
    print(f"\n{'='*85}")
    print(f"  {vendor_label} — FULL CONSISTENCY REPORT")
    print(f"{'='*85}")

    for file_entry in file_results:
        fname = file_entry["file"]
        runs = file_entry["runs"]
        valid = [r for r in runs if r is not None]

        print(f"\n  File: {fname}")
        print(f"  Runs completed: {len(valid)}/{NUM_RUNS}")

        if not valid:
            print("  ALL RUNS FAILED")
            continue

        # ── Per-run summary table ──
        print(f"\n  {'Run':<6} {'Items':<7} {'Trusted':<9} {'Review':<8} {'Trust%':<8} {'False':<7} {'Time'}")
        print(f"  {'─'*60}")
        for i, r in enumerate(runs):
            if r is None:
                print(f"  {i+1:<6} FAILED")
                continue
            print(f"  {i+1:<6} {r['total_scoreable']:<7} {r['trusted']:<9} {r['review']:<8} {r['trust_rate']:<8.1f} {r['false_trusts']:<7} {r.get('elapsed', 0):.1f}s")

        # ── Consistency metrics ──
        item_counts = [r["total_scoreable"] for r in valid]
        trust_rates = [r["trust_rate"] for r in valid]
        false_totals = [r["false_trusts"] for r in valid]

        item_consistent = max(item_counts) - min(item_counts) <= 1
        trust_consistent = max(trust_rates) - min(trust_rates) <= 5.0
        zero_false = all(f == 0 for f in false_totals)

        print(f"\n  CONSISTENCY ANALYSIS:")
        print(f"    Item counts:  {item_counts}  {'CONSISTENT' if item_consistent else 'VARIES'}")
        print(f"    Trust rates:  {[f'{t:.1f}%' for t in trust_rates]}  {'CONSISTENT' if trust_consistent else 'VARIES'}")
        print(f"    False trusts: {false_totals}  {'ZERO (PASS)' if zero_false else 'NON-ZERO (FAIL)'}")
        print(f"    Avg trust:    {sum(trust_rates)/len(trust_rates):.1f}%")

        # ── Row-by-row detail from the best run ──
        best = max(valid, key=lambda r: (r["trusted"], r["total_scoreable"]))
        print(f"\n  ROW-BY-ROW DETAIL (best run: {best['trusted']}/{best['total_scoreable']} trusted):")
        print(f"  Invoice totals: subtotal=${best['subtotal']:.2f}, tax=${best['tax']:.2f}, total=${best['total_invoice']:.2f}")

        # TRUSTED rows
        trusted_rows = [r for r in best["rows"] if r["status"] == "trusted"]
        review_rows = [r for r in best["rows"] if r["status"] != "trusted"]

        print(f"\n  TRUSTED ROWS ({len(trusted_rows)}):")
        print(f"  {'#':<4} {'Status':<12} {'Type':<10} {'Qty':<6} {'Price':<10} {'Total':<10} {'Math':<8} {'QSrc':<12} {'PSrc':<12} {'Name'}")
        print(f"  {'─'*120}")
        for r in trusted_rows:
            m = "PASS" if r["math_pass"] else "FAIL"
            print(f"  {r['idx']:<4} {'TRUSTED':<12} {r['row_type']:<10} {r['qty']:<6g} ${r['price']:<9.2f} ${r['total']:<9.2f} {m:<8} {r['qty_src']:<12} {r['price_src']:<12} {r['name'][:45]}")

        # REVIEW rows
        if review_rows:
            print(f"\n  REVIEW ROWS ({len(review_rows)}):")
            print(f"  {'#':<4} {'Status':<12} {'Type':<10} {'Qty':<6} {'Price':<10} {'Total':<10} {'Math':<8} {'QSrc':<12} {'Reason'}")
            print(f"  {'─'*120}")
            for r in review_rows:
                m = "PASS" if r["math_pass"] else "FAIL"
                print(f"  {r['idx']:<4} {'REVIEW':<12} {r['row_type']:<10} {r['qty']:<6g} ${r['price']:<9.2f} ${r['total']:<9.2f} {m:<8} {r['qty_src']:<12} {r['reason'][:50]}")

        # ── Cross-run item name comparison ──
        if len(valid) >= 2:
            print(f"\n  CROSS-RUN ITEM COMPARISON:")
            for run_idx, r in enumerate(valid):
                names = [row["name"][:40] for row in r["rows"]]
                print(f"    Run {run_idx+1} ({len(names)} items): {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")


def main():
    print("=" * 85)
    print("  3-VENDOR CONSISTENCY REPORT")
    print(f"  {NUM_RUNS} runs per sample | Zero-false-trust gate")
    print("=" * 85)

    token = login()
    print(f"  Authenticated OK\n")

    all_vendor_results = {}

    for vendor_label, files in VENDOR_SAMPLES.items():
        file_results = []

        for fname in files:
            fpath = os.path.join(UPLOADS_DIR, fname)
            if not os.path.exists(fpath):
                print(f"  SKIP: {fname} not found")
                continue

            fsize = os.path.getsize(fpath) / 1024
            print(f"\n  Testing {vendor_label}: {fname} ({fsize:.0f} KB)")

            runs = []
            for run_idx in range(NUM_RUNS):
                print(f"    Run {run_idx + 1}/{NUM_RUNS}...", end=" ", flush=True)
                t0 = time.time()
                try:
                    result = extract_invoice(fpath, token)
                    elapsed = time.time() - t0

                    if "error" in result:
                        print(f"ERROR ({elapsed:.1f}s): {result['error'][:80]}")
                        runs.append(None)
                        continue

                    analysis = analyze_run(result)
                    analysis["elapsed"] = elapsed
                    runs.append(analysis)
                    print(f"OK ({elapsed:.1f}s) — {analysis['trusted']}/{analysis['total_scoreable']} trusted, {analysis['false_trusts']} false")

                except Exception as e:
                    elapsed = time.time() - t0
                    print(f"EXCEPTION ({elapsed:.1f}s): {str(e)[:80]}")
                    runs.append(None)

                # Rate limit pause between runs
                if run_idx < NUM_RUNS - 1:
                    time.sleep(3)

            file_results.append({"file": fname, "runs": runs})

        all_vendor_results[vendor_label] = file_results
        print_vendor_report(vendor_label, file_results)

    # ── GLOBAL SUMMARY ──
    print(f"\n\n{'='*85}")
    print("  GLOBAL SUMMARY")
    print(f"{'='*85}")

    for vendor_label, file_results in all_vendor_results.items():
        all_runs = []
        for fr in file_results:
            all_runs.extend([r for r in fr["runs"] if r is not None])

        if not all_runs:
            print(f"\n  {vendor_label}: NO VALID RUNS")
            continue

        avg_trust = sum(r["trust_rate"] for r in all_runs) / len(all_runs)
        total_false = sum(r["false_trusts"] for r in all_runs)
        avg_items = sum(r["total_scoreable"] for r in all_runs) / len(all_runs)
        item_range = f"{min(r['total_scoreable'] for r in all_runs)}-{max(r['total_scoreable'] for r in all_runs)}"
        trust_range = f"{min(r['trust_rate'] for r in all_runs):.0f}-{max(r['trust_rate'] for r in all_runs):.0f}%"

        status = "PASS" if total_false == 0 else "FAIL"
        print(f"\n  {vendor_label}:")
        print(f"    Runs: {len(all_runs)}/{len(all_runs)}")
        print(f"    Avg trust rate: {avg_trust:.1f}%")
        print(f"    Trust range:    {trust_range}")
        print(f"    Avg items:      {avg_items:.1f} (range: {item_range})")
        print(f"    False trusts:   {total_false} [{status}]")

    print(f"\n{'='*85}")
    print("  REPORT COMPLETE")
    print(f"{'='*85}")


if __name__ == "__main__":
    main()
