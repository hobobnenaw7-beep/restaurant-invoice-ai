"""
US Foods 2-Phase Structural Extraction — 3-Run Consistency Test
"""
import json
import os
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
NUM_RUNS = 3

TEST_FILES = [
    "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",
    "receipt_9ef2c3ac-1f53-4e47-bb68-fa9d45caa9de.jpg",
]


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com", "password": "testpassword",
    })
    resp.raise_for_status()
    return resp.json()["token"]


def extract(filepath, token):
    fname = os.path.basename(filepath)
    ct = "image/jpeg"
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


def analyze(result):
    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])
    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    review = [it for it in scoreable if it.get("confidence_level") not in ("trusted", "excluded")]

    false_trusts = 0
    rows = []
    for idx, it in enumerate(scoreable):
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        gates = td.get("gates", {})

        name = (ext.get("raw_name") or it.get("raw_name") or "?")[:50]
        code = (ext.get("item_code") or it.get("item_code") or "")[:8]
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)
        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))
        qty_src = gates.get("qty_source", it.get("qty_source", "?"))

        math_pass = False
        if row_type == "fee":
            math_pass = total > 0
        elif qty > 0 and price > 0 and total > 0:
            math_pass = abs(round(qty * price, 2) - total) <= 0.01
            if status == "trusted" and not math_pass:
                false_trusts += 1

        rows.append({
            "idx": idx + 1, "name": name, "code": code,
            "qty": qty, "price": price, "total": total,
            "row_type": row_type, "status": status,
            "qty_src": qty_src, "math_pass": math_pass,
        })

    return {
        "total_scoreable": len(scoreable),
        "trusted": len(trusted),
        "review": len(review),
        "trust_rate": round(len(trusted) / len(scoreable) * 100, 1) if scoreable else 0,
        "false_trusts": false_trusts,
        "rows": rows,
        "subtotal": float(data.get("subtotal", 0) or 0),
        "tax": float(data.get("tax", 0) or 0),
        "invoice_total": float(data.get("total", 0) or 0),
    }


def main():
    print("=" * 95)
    print("  US FOODS 2-PHASE STRUCTURAL — 3-RUN CONSISTENCY")
    print("=" * 95)

    token = login()

    for test_file in TEST_FILES:
        fpath = os.path.join(UPLOADS_DIR, test_file)
        if not os.path.exists(fpath):
            print(f"\n  SKIP: {test_file}")
            continue

        fsize = os.path.getsize(fpath) / 1024
        print(f"\n{'─'*95}")
        print(f"  FILE: {test_file} ({fsize:.0f} KB)")
        print(f"{'─'*95}")

        runs = []
        for run_idx in range(NUM_RUNS):
            print(f"  Run {run_idx+1}/{NUM_RUNS}...", end=" ", flush=True)
            t0 = time.time()
            try:
                result = extract(fpath, token)
                elapsed = time.time() - t0
                if "error" in result:
                    print(f"ERROR ({elapsed:.1f}s)")
                    runs.append(None)
                    continue
                a = analyze(result)
                a["elapsed"] = elapsed
                runs.append(a)
                print(f"OK ({elapsed:.1f}s) — {a['total_scoreable']} items, {a['trusted']} trusted, {a['review']} review, {a['false_trusts']} false")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"EXCEPTION ({elapsed:.1f}s): {e}")
                runs.append(None)
            if run_idx < NUM_RUNS - 1:
                time.sleep(3)

        valid = [r for r in runs if r is not None]
        if not valid:
            continue

        # Summary table
        print(f"\n  {'Run':<5} {'Items':<7} {'Trust':<7} {'Revw':<6} {'Rate':<7} {'False':<6} {'Time'}")
        print(f"  {'─'*55}")
        for i, r in enumerate(runs):
            if r is None:
                print(f"  {i+1:<5} FAILED")
            else:
                print(f"  {i+1:<5} {r['total_scoreable']:<7} {r['trusted']:<7} {r['review']:<6} {r['trust_rate']:<7.1f} {r['false_trusts']:<6} {r['elapsed']:.1f}s")

        # Consistency
        item_counts = [r["total_scoreable"] for r in valid]
        trust_rates = [r["trust_rate"] for r in valid]
        false_counts = [r["false_trusts"] for r in valid]
        item_consistent = max(item_counts) - min(item_counts) <= 2
        zero_false = all(f == 0 for f in false_counts)

        print(f"\n  CONSISTENCY:")
        print(f"    Items:  {item_counts}  {'CONSISTENT' if item_consistent else 'VARIES'}")
        print(f"    Trust:  {[f'{t:.1f}%' for t in trust_rates]}")
        print(f"    False:  {false_counts}  {'ZERO' if zero_false else 'FAIL'}")

        # Row detail per run
        for ri, r in enumerate(valid):
            print(f"\n  RUN {ri+1} ({r['total_scoreable']} items, {r['trusted']} trusted):")
            print(f"  {'#':<3} {'S':<3} {'Code':<9} {'Qty':<5} {'Price':<9} {'Total':<9} {'M':<3} {'Name'}")
            print(f"  {'─'*85}")
            for row in r["rows"]:
                s = "T" if row["status"] == "trusted" else "R"
                m = "OK" if row["math_pass"] else "X"
                print(f"  {row['idx']:<3} {s:<3} {row['code']:<9} {row['qty']:<5g} ${row['price']:<8.2f} ${row['total']:<8.2f} {m:<3} {row['name'][:38]}")

        # Cross-run: compare product codes (deterministic anchor)
        print(f"\n  PRODUCT CODE COMPARISON (deterministic anchor):")
        for ri, r in enumerate(valid):
            codes = [row["code"] for row in r["rows"] if row["code"]]
            print(f"    Run {ri+1}: {codes}")
        if len(valid) >= 2:
            codes_sets = [set(row["code"] for row in r["rows"] if row["code"]) for r in valid]
            common = codes_sets[0]
            for cs in codes_sets[1:]:
                common = common & cs
            all_codes = codes_sets[0]
            for cs in codes_sets[1:]:
                all_codes = all_codes | cs
            print(f"    Common across all runs: {len(common)}/{len(all_codes)} codes")
            print(f"    Common codes: {sorted(common)}")

        # Cross-run: compare totals (most reliable field)
        print(f"\n  TOTAL VALUES COMPARISON:")
        for ri, r in enumerate(valid):
            totals = sorted([row["total"] for row in r["rows"] if row["total"] > 0])
            print(f"    Run {ri+1}: {totals}")

    # Backend logs
    print(f"\n{'='*95}")
    print("  BACKEND LOGS")
    print(f"{'='*95}")
    try:
        with open("/var/log/supervisor/backend.err.log") as f:
            lines = f.readlines()
        for line in lines[-40:]:
            l = line.strip()
            if any(kw in l for kw in ("Phase 1", "Phase 2", "structural", "Hallucination")):
                print(f"  {l[-120:]}")
    except:
        pass

    print(f"\n{'='*95}")
    print("  COMPLETE")
    print(f"{'='*95}")


if __name__ == "__main__":
    main()
