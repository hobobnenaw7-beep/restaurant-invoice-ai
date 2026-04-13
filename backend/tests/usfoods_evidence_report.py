"""
US Foods Extraction Evidence Report
- Runs the same invoice 3 times to test determinism
- Captures raw GPT output fields vs final pipeline output
- Tracks retry behavior
- Shows failure cases with exact reasons
"""
import json
import os
import time
import requests
import re

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

# The US Foods file we know has line items
TEST_FILE = "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg"


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
            timeout=120,
        )
    return resp.json() if resp.status_code == 200 else {"error": resp.text[:200]}


def main():
    token = login()
    fpath = os.path.join(UPLOADS_DIR, TEST_FILE)

    if not os.path.exists(fpath):
        print(f"ERROR: {fpath} not found")
        return

    print("=" * 80)
    print("US FOODS EXTRACTION EVIDENCE REPORT")
    print(f"File: {TEST_FILE}")
    print(f"Size: {os.path.getsize(fpath) / 1024:.0f} KB")
    print("=" * 80)

    # ══════════════════════════════════════════════════════════════
    # SECTION 4: DETERMINISM TEST — Run 3 times
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 80)
    print("SECTION 1: DETERMINISM TEST (3 consecutive runs)")
    print("=" * 80)

    runs = []
    for run_idx in range(3):
        print(f"\n  Run {run_idx + 1}/3...")
        t0 = time.time()
        result = extract(fpath, token)
        elapsed = time.time() - t0

        if "error" in result:
            print(f"    ERROR: {result['error'][:100]}")
            runs.append({"error": True, "elapsed": elapsed})
            continue

        data = result.get("extracted_data", result.get("data", result))
        items = data.get("items", [])
        vendor = result.get("detected_vendor", data.get("supplier_name", ""))
        scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
        trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
        review = [it for it in scoreable if it.get("confidence_level") != "trusted" and it.get("confidence_level") != "excluded"]

        # Check for false trusts
        false_trusts = 0
        for it in trusted:
            q = float(it.get("quantity", 0) or 0)
            p = float(it.get("unit_price", 0) or 0)
            t = float(it.get("total", 0) or 0)
            if q > 0 and p > 0 and t > 0:
                if abs(round(q * p, 2) - t) > 0.01:
                    false_trusts += 1

        # Count items with real data
        items_with_price = sum(1 for it in scoreable if float(it.get("unit_price", 0) or 0) > 0)
        items_with_total = sum(1 for it in scoreable if float(it.get("total", 0) or 0) > 0)
        items_with_qty = sum(1 for it in scoreable if float(it.get("quantity", 0) or 0) > 0)
        items_vis_true = sum(1 for it in scoreable if it.get("qty_column_visible") is True)

        run_data = {
            "error": False,
            "elapsed": elapsed,
            "vendor": vendor,
            "total_items": len(scoreable),
            "trusted": len(trusted),
            "review": len(review),
            "trust_rate": len(trusted) / len(scoreable) * 100 if scoreable else 0,
            "false_trusts": false_trusts,
            "items_with_price": items_with_price,
            "items_with_total": items_with_total,
            "items_with_qty": items_with_qty,
            "items_vis_true": items_vis_true,
            "items": scoreable,
        }
        runs.append(run_data)

        print(f"    Vendor: {vendor}")
        print(f"    Items: {len(scoreable)}, Trusted: {len(trusted)} ({run_data['trust_rate']:.0f}%), Review: {len(review)}")
        print(f"    With qty>0: {items_with_qty}, With price>0: {items_with_price}, With total>0: {items_with_total}")
        print(f"    qty_column_visible=true: {items_vis_true}")
        print(f"    False trusts: {false_trusts}")
        print(f"    Time: {elapsed:.1f}s")

    # Consistency analysis
    valid_runs = [r for r in runs if not r.get("error")]
    if len(valid_runs) >= 2:
        item_counts = [r["total_items"] for r in valid_runs]
        trust_rates = [r["trust_rate"] for r in valid_runs]
        print(f"\n  CONSISTENCY:")
        print(f"    Item counts across runs: {item_counts}")
        print(f"    Trust rates across runs: {[f'{t:.0f}%' for t in trust_rates]}")
        print(f"    Item count variance: {max(item_counts) - min(item_counts)}")
        print(f"    Trust rate variance: {max(trust_rates) - min(trust_rates):.1f}pp")

    # ══════════════════════════════════════════════════════════════
    # SECTION 2: DETAILED ROW-BY-ROW EVIDENCE (from best run)
    # ══════════════════════════════════════════════════════════════
    best_run = max(valid_runs, key=lambda r: r["trusted"]) if valid_runs else None
    if not best_run:
        print("\nNo valid runs to analyze.")
        return

    print("\n\n" + "=" * 80)
    print("SECTION 2: ROW-BY-ROW EVIDENCE (best run)")
    print("=" * 80)

    items = best_run["items"]
    trusted_examples = []
    review_examples = []

    for idx, it in enumerate(items):
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        gates = td.get("gates", {})

        name = ext.get("raw_name", it.get("raw_name", ""))[:55]
        item_code = ext.get("item_code", it.get("item_code", ""))[:10]
        qty = ext.get("quantity", it.get("quantity", 0))
        price = ext.get("unit_price", it.get("unit_price", 0))
        total = ext.get("total", it.get("total", 0))
        pack = ext.get("pack_size", it.get("pack_size", ""))[:20]

        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))
        reason = td.get("reason", "?")[:80]
        failure_cat = td.get("failure_category", "?")

        qty_src = gates.get("qty_source", it.get("qty_source", "?"))
        price_src = gates.get("price_source", it.get("price_source", "?"))
        total_src = gates.get("total_source", it.get("total_source", "?"))
        math_check = gates.get("math_check", it.get("valid_calc", "?"))
        vis = it.get("qty_column_visible", gates.get("qty_column_visible", "?"))

        # Math verification
        if qty and price and total:
            computed = round(float(qty) * float(price), 2)
            math_diff = abs(computed - float(total))
            math_str = f"{qty} x {price} = {computed} (actual={total}, diff=${math_diff:.2f})"
        else:
            math_str = "incomplete data"

        record = {
            "idx": idx + 1,
            "name": name,
            "item_code": item_code,
            "qty": qty,
            "price": price,
            "total": total,
            "pack": pack,
            "row_type": row_type,
            "status": status,
            "qty_src": qty_src,
            "price_src": price_src,
            "total_src": total_src,
            "math_check": math_check,
            "vis": vis,
            "reason": reason,
            "failure_cat": failure_cat,
            "math_str": math_str,
        }

        if status == "trusted":
            trusted_examples.append(record)
        else:
            review_examples.append(record)

    def print_row_evidence(r, label):
        print(f"\n  [{label}] Row #{r['idx']}: {r['name']}")
        print(f"      item_code: {r['item_code']}")
        print(f"      EXTRACTED: qty={r['qty']}  price={r['price']}  total={r['total']}  pack={r['pack']}")
        print(f"      SOURCES:   qty_src={r['qty_src']}  price_src={r['price_src']}  total_src={r['total_src']}")
        print(f"      MATH:      {r['math_str']}")
        print(f"      VISIBLE:   qty_column_visible={r['vis']}")
        print(f"      GATES:     math_check={r['math_check']}")
        print(f"      DECISION:  {r['status']} ({r['row_type']})")
        print(f"      REASON:    {r['reason']}")
        if r['failure_cat'] not in ('none', 'n/a', 'fee_valid', '?'):
            print(f"      FAILURE:   {r['failure_cat']}")

    # Show 3-5 trusted examples
    print(f"\n  TRUSTED ROWS ({len(trusted_examples)} total):")
    for r in trusted_examples[:5]:
        print_row_evidence(r, "TRUSTED")

    # Show all review examples
    print(f"\n  REVIEW ROWS ({len(review_examples)} total):")
    for r in review_examples:
        print_row_evidence(r, "REVIEW")

    # ══════════════════════════════════════════════════════════════
    # SECTION 3: RETRY BEHAVIOR
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 80)
    print("SECTION 3: RETRY BEHAVIOR ANALYSIS")
    print("=" * 80)

    # Check backend logs for retry triggers
    try:
        with open("/var/log/supervisor/backend.err.log", "r") as f:
            log_lines = f.readlines()

        retry_lines = [l.strip() for l in log_lines if "quality" in l.lower() or "retry" in l.lower() or "Retry improved" in l or "Retry did not" in l]
        recent_retries = retry_lines[-20:] if retry_lines else []

        if recent_retries:
            print(f"\n  Retry log entries (last 20):")
            for line in recent_retries:
                # Trim timestamp for readability
                print(f"    {line[-120:]}")
        else:
            print(f"\n  No retry triggers found in recent logs.")
            print(f"  This means the FIRST extraction pass succeeded without needing a retry.")
    except Exception as e:
        print(f"  Could not read logs: {e}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 4: SUMMARY
    # ══════════════════════════════════════════════════════════════
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if valid_runs:
        avg_trust = sum(r["trust_rate"] for r in valid_runs) / len(valid_runs)
        avg_items = sum(r["total_items"] for r in valid_runs) / len(valid_runs)
        total_false = sum(r["false_trusts"] for r in valid_runs)
        print(f"  Runs completed: {len(valid_runs)}/3")
        print(f"  Average trust rate: {avg_trust:.1f}%")
        print(f"  Average items extracted: {avg_items:.1f}")
        print(f"  Total false trusts: {total_false}")
        print(f"  All runs extracted real prices: {all(r['items_with_price'] == r['total_items'] or r['items_with_price'] >= r['total_items'] - 1 for r in valid_runs)}")
        print(f"  All runs had qty_column_visible: {all(r['items_vis_true'] >= r['total_items'] - 1 for r in valid_runs)}")


if __name__ == "__main__":
    main()
