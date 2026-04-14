"""
US Foods Section Splitting — 3-Run Consistency Test
Tests the section-split pipeline on US Foods samples.
"""
import json
import os
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
NUM_RUNS = 3

# Two US Foods test files
TEST_FILES = [
    "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",  # Dark 21-item invoice
    "receipt_9ef2c3ac-1f53-4e47-bb68-fa9d45caa9de.jpg",   # Second US Foods invoice
]


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
            timeout=300,
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
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)
        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))
        reason = td.get("reason", "")[:80]
        qty_src = gates.get("qty_source", it.get("qty_source", "?"))

        math_pass = False
        if row_type == "fee":
            math_pass = total > 0
        elif qty > 0 and price > 0 and total > 0:
            computed = round(qty * price, 2)
            math_pass = abs(computed - total) <= 0.01
            if status == "trusted" and not math_pass:
                false_trusts += 1

        rows.append({
            "idx": idx + 1,
            "name": name,
            "qty": qty,
            "price": price,
            "total": total,
            "row_type": row_type,
            "status": status,
            "reason": reason,
            "qty_src": qty_src,
            "math_pass": math_pass,
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
    print("  US FOODS SECTION SPLITTING — 3-RUN CONSISTENCY TEST")
    print("=" * 90)

    token = login()

    for test_file in TEST_FILES:
        fpath = os.path.join(UPLOADS_DIR, test_file)
        if not os.path.exists(fpath):
            print(f"\n  SKIP: {test_file} not found")
            continue

        fsize = os.path.getsize(fpath) / 1024
        print(f"\n{'─'*90}")
        print(f"  File: {test_file} ({fsize:.0f} KB)")
        print(f"{'─'*90}")

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
            print("  ALL RUNS FAILED")
            continue

        # Summary
        print(f"\n  {'Run':<6} {'Items':<8} {'Trusted':<9} {'Review':<8} {'Trust%':<8} {'False':<7} {'Time'}")
        print(f"  {'─'*65}")
        for i, r in enumerate(runs):
            if r is None:
                print(f"  {i+1:<6} FAILED")
            else:
                print(f"  {i+1:<6} {r['total_scoreable']:<8} {r['trusted']:<9} {r['review']:<8} {r['trust_rate']:<8.1f} {r['false_trusts']:<7} {r['elapsed']:.1f}s")

        # Consistency
        item_counts = [r["total_scoreable"] for r in valid]
        trust_rates = [r["trust_rate"] for r in valid]
        false_counts = [r["false_trusts"] for r in valid]

        item_consistent = max(item_counts) - min(item_counts) <= 2
        zero_false = all(f == 0 for f in false_counts)

        print(f"\n  CONSISTENCY:")
        print(f"    Items:  {item_counts}  {'CONSISTENT' if item_consistent else 'VARIES'}")
        print(f"    Trust:  {[f'{t:.1f}%' for t in trust_rates]}")
        print(f"    False:  {false_counts}  {'ZERO' if zero_false else 'NON-ZERO'}")

        # Row detail for each run
        for run_idx, r in enumerate(valid):
            print(f"\n  RUN {run_idx + 1} ({r['total_scoreable']} items, {r['trusted']} trusted):")
            print(f"  {'#':<4} {'St':<6} {'Type':<10} {'Qty':<6} {'Price':<10} {'Total':<10} {'M':<4} {'QSrc':<12} {'Name'}")
            print(f"  {'─'*95}")
            for row in r["rows"]:
                m = "OK" if row["math_pass"] else "X"
                s = "T" if row["status"] == "trusted" else "R"
                print(
                    f"  {row['idx']:<4} {s:<6} {row['row_type']:<10} "
                    f"{row['qty']:<6g} ${row['price']:<9.2f} ${row['total']:<9.2f} "
                    f"{m:<4} {row['qty_src']:<12} {row['name'][:38]}"
                )

        # Cross-run name comparison
        print(f"\n  CROSS-RUN NAMES:")
        for run_idx, r in enumerate(valid):
            names = [row["name"][:35] for row in r["rows"]]
            print(f"    Run {run_idx+1} ({len(names)}): {', '.join(names[:5])}{'...' if len(names)>5 else ''}")

        if len(valid) >= 2:
            names_0 = [(row["name"][:30], row["total"]) for row in valid[0]["rows"]]
            names_1 = [(row["name"][:30], row["total"]) for row in valid[1]["rows"]]
            # Check total-based matching
            totals_0 = sorted([row["total"] for row in valid[0]["rows"]])
            totals_1 = sorted([row["total"] for row in valid[1]["rows"]])
            totals_match = totals_0 == totals_1
            print(f"    Totals match (run1 vs run2): {totals_match}")

    # Check backend logs for section split evidence
    print(f"\n{'='*90}")
    print("  BACKEND LOG EVIDENCE")
    print(f"{'='*90}")
    try:
        with open("/var/log/supervisor/backend.err.log") as f:
            lines = f.readlines()
        split_lines = [l.strip() for l in lines if "section split" in l.lower() or "Section split" in l or "Dedup" in l.lower() or "strip" in l.lower()]
        for line in split_lines[-20:]:
            print(f"  {line[-120:]}")
    except Exception as e:
        print(f"  Could not read logs: {e}")

    print(f"\n{'='*90}")
    print("  TEST COMPLETE")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
