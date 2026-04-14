"""
US Foods Prompt Fix — 3-Run Consistency Test
Tests the adjusted prompt (removed "FULLY VISIBLE" gate) on the same sample.
Reports: row count, trusted vs review, field values, cross-run consistency.
"""
import json
import os
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
TEST_FILE = "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg"
NUM_RUNS = 3


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com", "password": "testpassword",
    })
    resp.raise_for_status()
    return resp.json()["token"]


def extract(filepath, token):
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
    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])
    vendor = result.get("detected_vendor", data.get("supplier_name", ""))

    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    review = [it for it in scoreable if it.get("confidence_level") not in ("trusted", "excluded")]

    false_trusts = 0
    rows = []

    for idx, it in enumerate(scoreable):
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        gates = td.get("gates", {})

        name = (ext.get("raw_name") or it.get("raw_name") or "?")[:55]
        item_code = ext.get("item_code", it.get("item_code", ""))
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)

        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))
        reason = td.get("reason", "")[:80]
        failure_cat = td.get("failure_category", "")

        qty_src = gates.get("qty_source", it.get("qty_source", "?"))
        price_src = gates.get("price_source", it.get("price_source", "?"))
        total_src = gates.get("total_source", it.get("total_source", "?"))
        vis = it.get("qty_column_visible", gates.get("qty_column_visible", "?"))

        # Math verification
        math_pass = False
        if row_type == "fee":
            math_pass = total > 0
        elif qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            diff = abs(computed - total)
            math_pass = diff <= 0.01
            if status == "trusted" and not math_pass:
                false_trusts += 1

        rows.append({
            "idx": idx + 1,
            "name": name,
            "item_code": item_code,
            "qty": qty,
            "price": price,
            "total": total,
            "row_type": row_type,
            "status": status,
            "reason": reason,
            "failure_cat": failure_cat,
            "qty_src": qty_src,
            "price_src": price_src,
            "total_src": total_src,
            "math_pass": math_pass,
            "vis": vis,
        })

    return {
        "vendor": vendor,
        "total_scoreable": len(scoreable),
        "trusted": len(trusted),
        "review": len(review),
        "trust_rate": round(len(trusted) / len(scoreable) * 100, 1) if scoreable else 0,
        "false_trusts": false_trusts,
        "rows": rows,
        "subtotal": float(data.get("subtotal", 0) or 0),
        "tax": float(data.get("tax", 0) or 0),
        "total_invoice": float(data.get("total", 0) or 0),
    }


def main():
    print("=" * 90)
    print("  US FOODS PROMPT FIX — 3-RUN CONSISTENCY TEST")
    print(f"  File: {TEST_FILE}")
    print(f"  Change: Removed 'FULLY VISIBLE' gate, kept math safety net")
    print("=" * 90)

    token = login()
    fpath = os.path.join(UPLOADS_DIR, TEST_FILE)
    fsize = os.path.getsize(fpath) / 1024
    print(f"  File size: {fsize:.0f} KB")
    print(f"  Running {NUM_RUNS} extraction passes...\n")

    runs = []
    for run_idx in range(NUM_RUNS):
        print(f"  Run {run_idx + 1}/{NUM_RUNS}...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = extract(fpath, token)
            elapsed = time.time() - t0

            if "error" in result:
                print(f"ERROR ({elapsed:.1f}s): {result['error'][:80]}")
                runs.append(None)
                continue

            analysis = analyze_run(result)
            analysis["elapsed"] = elapsed
            runs.append(analysis)
            print(
                f"OK ({elapsed:.1f}s) — "
                f"{analysis['total_scoreable']} items, "
                f"{analysis['trusted']} trusted, "
                f"{analysis['review']} review, "
                f"{analysis['false_trusts']} false"
            )
        except Exception as e:
            elapsed = time.time() - t0
            print(f"EXCEPTION ({elapsed:.1f}s): {str(e)[:80]}")
            runs.append(None)

        if run_idx < NUM_RUNS - 1:
            time.sleep(3)

    valid = [r for r in runs if r is not None]
    if not valid:
        print("\n  ALL RUNS FAILED — cannot produce report")
        return

    # ── Summary Table ──
    print(f"\n{'='*90}")
    print("  RUN SUMMARY")
    print(f"{'='*90}")
    print(f"  {'Run':<6} {'Items':<8} {'Trusted':<9} {'Review':<8} {'Trust%':<8} {'False':<7} {'Time'}")
    print(f"  {'─'*65}")
    for i, r in enumerate(runs):
        if r is None:
            print(f"  {i+1:<6} FAILED")
        else:
            print(f"  {i+1:<6} {r['total_scoreable']:<8} {r['trusted']:<9} {r['review']:<8} {r['trust_rate']:<8.1f} {r['false_trusts']:<7} {r['elapsed']:.1f}s")

    # ── Consistency ──
    item_counts = [r["total_scoreable"] for r in valid]
    trust_rates = [r["trust_rate"] for r in valid]
    trusted_counts = [r["trusted"] for r in valid]
    review_counts = [r["review"] for r in valid]
    false_counts = [r["false_trusts"] for r in valid]

    item_consistent = max(item_counts) - min(item_counts) <= 2
    trust_consistent = max(trust_rates) - min(trust_rates) <= 10.0
    zero_false = all(f == 0 for f in false_counts)

    print(f"\n  CONSISTENCY ANALYSIS:")
    print(f"    Item counts:    {item_counts}  {'CONSISTENT' if item_consistent else 'VARIES'}")
    print(f"    Trusted counts: {trusted_counts}")
    print(f"    Review counts:  {review_counts}")
    print(f"    Trust rates:    {[f'{t:.1f}%' for t in trust_rates]}  {'CONSISTENT' if trust_consistent else 'VARIES'}")
    print(f"    False trusts:   {false_counts}  {'ZERO (PASS)' if zero_false else 'NON-ZERO (FAIL)'}")
    print(f"    Avg trust rate: {sum(trust_rates)/len(trust_rates):.1f}%")
    print(f"    Avg items:      {sum(item_counts)/len(item_counts):.1f}")

    # ── Detailed row-by-row for each run ──
    for run_idx, r in enumerate(valid):
        print(f"\n{'─'*90}")
        print(f"  RUN {run_idx + 1} DETAIL ({r['total_scoreable']} items, {r['trusted']} trusted)")
        print(f"  Invoice: subtotal=${r['subtotal']:.2f}, tax=${r['tax']:.2f}, total=${r['total_invoice']:.2f}")
        print(f"{'─'*90}")

        print(f"  {'#':<4} {'Status':<12} {'Type':<10} {'Qty':<6} {'Price':<10} {'Total':<10} {'Math':<6} {'QSrc':<12} {'Vis':<6} {'Name'}")
        print(f"  {'─'*115}")

        for row in r["rows"]:
            m = "OK" if row["math_pass"] else "FAIL"
            vis_str = "Y" if row["vis"] is True else ("N" if row["vis"] is False else "?")
            status_short = "TRUST" if row["status"] == "trusted" else "REVW"
            print(
                f"  {row['idx']:<4} {status_short:<12} {row['row_type']:<10} "
                f"{row['qty']:<6g} ${row['price']:<9.2f} ${row['total']:<9.2f} "
                f"{m:<6} {row['qty_src']:<12} {vis_str:<6} {row['name'][:40]}"
            )

        # Show review reasons
        review_rows = [row for row in r["rows"] if row["status"] != "trusted"]
        if review_rows:
            print(f"\n  REVIEW REASONS:")
            for row in review_rows:
                print(f"    #{row['idx']} {row['name'][:35]}: {row['reason'][:70]}")

    # ── Cross-run name comparison ──
    print(f"\n{'='*90}")
    print("  CROSS-RUN ITEM NAME COMPARISON")
    print(f"{'='*90}")
    for run_idx, r in enumerate(valid):
        names = [row["name"][:35] for row in r["rows"]]
        print(f"  Run {run_idx+1} ({len(names)} items):")
        for i, n in enumerate(names):
            print(f"    [{i+1}] {n}")

    # ── VERDICT ──
    print(f"\n{'='*90}")
    print("  VERDICT")
    print(f"{'='*90}")
    avg_items = sum(item_counts) / len(item_counts)
    avg_trust = sum(trust_rates) / len(trust_rates)
    total_false = sum(false_counts)

    if avg_items >= 11 and zero_false and item_consistent:
        print(f"  PASS: Avg {avg_items:.0f} items, {avg_trust:.1f}% trust, 0 false trusts, consistent")
    elif avg_items > 0 and zero_false:
        print(f"  PARTIAL: Avg {avg_items:.0f} items (target: 11+), {avg_trust:.1f}% trust, 0 false trusts")
    else:
        print(f"  NEEDS WORK: Avg {avg_items:.0f} items, {avg_trust:.1f}% trust, {total_false} false trusts")

    print(f"{'='*90}")


if __name__ == "__main__":
    main()
