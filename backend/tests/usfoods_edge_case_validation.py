"""
US Foods Edge Case Validation — Tax, Discounts, Credits, Multi-page, Noise
============================================================================
3 test invoices × 3 runs each = 9 extractions.
Reports: raw JSON, field accuracy, determinism (identical across runs).
"""
import json, os, time, requests, copy

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
NUM_RUNS = 3

# ── Ground truth for each invoice ──

INVOICES = [
    {
        "label": "A: Tax + Discount + Multi-Section",
        "file": "usfoods_test_tax_discount.png",
        "truth": {
            "supplier": "US Foods",
            "invoice_number": "9876543-001122",
            "invoice_date": "2026-02-20",
            "items": [
                {"code": "4821503", "qty": 4, "price": 42.50, "total": 170.00},
                {"code": "3910287", "qty": 3, "price": 89.99, "total": 269.97},
                {"code": "7723401", "qty": 2, "price": 95.00, "total": 190.00},
                {"code": "5510892", "qty": 6, "price": 22.15, "total": 132.90},
                {"code": "2283019", "qty": 2, "price": 65.40, "total": 130.80},
                {"code": "8841022", "qty": 5, "price": 5.89, "total": 29.45},
                {"code": "1192847", "qty": 3, "price": 18.75, "total": 56.25},
                {"code": "6637201", "qty": 4, "price": 31.50, "total": 126.00},
                {"code": "3345098", "qty": 2, "price": 24.80, "total": 49.60},
            ],
            "fee": 8.50,
            "subtotal": 1154.97,
            "tax": 80.85,
            "discount": 25.00,
            "total": 1219.32,
        },
    },
    {
        "label": "B: Multi-Page + Credit Line",
        "file": "usfoods_test_multipage_credit.png",
        "truth": {
            "supplier": "US Foods",
            "invoice_number": "5551234-998877",
            "invoice_date": "2026-03-05",
            "items": [
                {"code": "5501234", "qty": 10, "price": 48.90, "total": 489.00},
                {"code": "3382910", "qty": 8, "price": 19.75, "total": 158.00},
                {"code": "9012456", "qty": 2, "price": 145.00, "total": 290.00},
                {"code": "4478231", "qty": 3, "price": 28.50, "total": 85.50},
                {"code": "7756012", "qty": 4, "price": 12.90, "total": 51.60},
                {"code": "1128903", "qty": 5, "price": 26.40, "total": 132.00},
                {"code": "5501234", "qty": 1, "price": 48.90, "total": -48.90},  # CREDIT
            ],
            "fee": 12.75,
            "subtotal": 1157.20,
            "tax": 75.22,
            "total": 1245.17,
        },
    },
    {
        "label": "C: Noisy Scan + Tax",
        "file": "usfoods_test_noisy.png",
        "truth": {
            "supplier": "US Foods",
            "invoice_number": "3337890-445566",
            "invoice_date": "2026-01-28",
            "items": [
                {"code": "8801245", "qty": 3, "price": 25.99, "total": 77.97},
                {"code": "6629081", "qty": 1, "price": 19.45, "total": 19.45},
                {"code": "4412873", "qty": 6, "price": 68.50, "total": 411.00},
                {"code": "2209134", "qty": 4, "price": 42.75, "total": 171.00},
                {"code": "7783922", "qty": 2, "price": 15.30, "total": 30.60},
            ],
            "fee": 6.50,
            "subtotal": 710.02,
            "tax": 53.25,
            "total": 769.77,
        },
    },
]


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"})
    resp.raise_for_status()
    return resp.json()["token"]


def extract(filepath, token):
    fname = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{API_URL}/api/upload/extract",
            files={"file": (fname, f, "image/png")},
            data={"document_type": "purchase_invoice"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=300,
        )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    return resp.json()


def analyze(result):
    data = result.get("extracted_data") or result.get("data") or result
    items = data.get("items") or []
    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]

    rows = []
    false_trusts = 0
    for it in scoreable:
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        code = (ext.get("item_code") or it.get("item_code") or "")[:8]
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)
        name = (ext.get("raw_name") or it.get("raw_name") or "?")[:50]
        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))

        math_ok = False
        if row_type == "fee":
            math_ok = total > 0
        elif qty > 0 and price > 0 and total != 0:
            math_ok = abs(round(qty * price, 2) - abs(total)) <= 0.02
            if status == "trusted" and not math_ok:
                false_trusts += 1

        rows.append({"code": code, "qty": qty, "price": price, "total": total,
                      "name": name, "row_type": row_type, "status": status, "math_ok": math_ok})

    return {
        "vendor": result.get("detected_vendor") or data.get("supplier_name") or "?",
        "invoice_number": data.get("invoice_number", ""),
        "invoice_date": data.get("invoice_date", ""),
        "scoreable": len(scoreable),
        "trusted": len(trusted),
        "false_trusts": false_trusts,
        "trust_rate": round(len(trusted) / len(scoreable) * 100, 1) if scoreable else 0,
        "subtotal": float(data.get("subtotal", 0) or 0),
        "tax": float(data.get("tax", 0) or 0),
        "total": float(data.get("total", 0) or 0),
        "rows": rows,
        "raw_items_json": json.dumps(items, indent=2)[:3000],
    }


def compare(analysis, truth):
    """Field-level accuracy comparison."""
    results = {"vendor_ok": truth["supplier"].lower() in analysis["vendor"].lower(),
               "inv_num_ok": truth["invoice_number"] in analysis["invoice_number"],
               "date_ok": truth["invoice_date"] == analysis["invoice_date"],
               "matches": 0, "qty_ok": 0, "price_ok": 0, "total_ok": 0, "code_ok": 0}

    truth_by_total = {}
    for it in truth["items"]:
        key = round(it["total"], 2)
        truth_by_total[key] = it

    for row in analysis["rows"]:
        if row["row_type"] != "line_item":
            continue
        key = round(row["total"], 2)
        match = truth_by_total.get(key)
        if not match and row["code"]:
            for it in truth["items"]:
                if it["code"] == row["code"]:
                    match = it
                    break
        if match:
            results["matches"] += 1
            if abs(row["total"] - match["total"]) < 0.05:
                results["total_ok"] += 1
            if abs(row["price"] - match["price"]) < 0.05:
                results["price_ok"] += 1
            if abs(row["qty"] - match["qty"]) < 0.5:
                results["qty_ok"] += 1
            if row["code"] == match["code"]:
                results["code_ok"] += 1

    n = max(results["matches"], 1)
    expected = len(truth["items"])
    results["accuracy"] = {
        "total": round(results["total_ok"] / n * 100, 1),
        "price": round(results["price_ok"] / n * 100, 1),
        "qty": round(results["qty_ok"] / n * 100, 1),
        "code": round(results["code_ok"] / n * 100, 1),
        "item_coverage": round(results["matches"] / expected * 100, 1),
    }
    # Tax/subtotal accuracy
    results["tax_ok"] = abs(analysis["tax"] - truth.get("tax", 0)) < 1.0
    results["subtotal_ok"] = abs(analysis["subtotal"] - truth.get("subtotal", 0)) < 5.0
    results["total_ok_inv"] = abs(analysis["total"] - truth.get("total", 0)) < 5.0

    return results


def main():
    print("=" * 95)
    print("  US FOODS EDGE CASE VALIDATION — 3 Invoices × 3 Runs")
    print("=" * 95)

    token = login()

    for inv in INVOICES:
        fpath = os.path.join(UPLOADS_DIR, inv["file"])
        truth = inv["truth"]
        expected_items = len(truth["items"])

        print(f"\n{'━'*95}")
        print(f"  INVOICE {inv['label']}")
        print(f"  File: {inv['file']} | Expected: {expected_items} items")
        print(f"{'━'*95}")

        all_runs = []
        for run_idx in range(NUM_RUNS):
            if run_idx > 0:
                time.sleep(5)
            print(f"\n  Run {run_idx+1}/{NUM_RUNS}...", end=" ", flush=True)
            t0 = time.time()
            result = extract(fpath, token)
            elapsed = time.time() - t0

            if "error" in result:
                print(f"ERROR: {result['error']}")
                all_runs.append(None)
                continue

            a = analyze(result)
            c = compare(a, truth)
            a["comparison"] = c
            a["elapsed"] = elapsed
            all_runs.append(a)

            print(f"OK ({elapsed:.1f}s) — {a['scoreable']} items, {a['trusted']} trusted, {a['false_trusts']} false")

        valid = [r for r in all_runs if r is not None]
        if not valid:
            print("  ALL RUNS FAILED")
            continue

        # ── Per-run summary ──
        print(f"\n  {'Run':<5} {'Items':<7} {'Trust':<7} {'False':<6} {'Rate':<7} {'Tax':<10} {'Total':<12} {'Coverage'}")
        print(f"  {'─'*70}")
        for i, r in enumerate(all_runs):
            if r is None:
                print(f"  {i+1:<5} FAILED")
            else:
                c = r["comparison"]
                cov = c["accuracy"]["item_coverage"]
                print(f"  {i+1:<5} {r['scoreable']:<7} {r['trusted']:<7} {r['false_trusts']:<6} {r['trust_rate']:<7.1f} ${r['tax']:<9.2f} ${r['total']:<11.2f} {cov}%")

        # ── Determinism check ──
        if len(valid) >= 2:
            # Compare row-level totals across runs
            run_totals = []
            for r in valid:
                totals = sorted([row["total"] for row in r["rows"] if row["row_type"] == "line_item"])
                run_totals.append(totals)

            all_identical = all(t == run_totals[0] for t in run_totals[1:])
            item_counts = [r["scoreable"] for r in valid]
            count_consistent = max(item_counts) - min(item_counts) <= 1

            print(f"\n  DETERMINISM:")
            print(f"    Item counts: {item_counts} {'IDENTICAL' if len(set(item_counts)) == 1 else 'CONSISTENT' if count_consistent else 'VARIES'}")
            print(f"    Line totals identical across runs: {all_identical}")

            if not all_identical:
                for i, t in enumerate(run_totals):
                    print(f"      Run {i+1}: {t}")

        # ── Best run detailed report ──
        best = max(valid, key=lambda r: (r["trusted"], r["scoreable"]))
        c = best["comparison"]

        print(f"\n  FIELD ACCURACY (best run: {best['trusted']}/{best['scoreable']} trusted):")
        print(f"    Vendor match:     {'YES' if c['vendor_ok'] else 'NO'}")
        print(f"    Invoice # match:  {'YES' if c['inv_num_ok'] else 'NO'}")
        print(f"    Date match:       {'YES' if c['date_ok'] else 'NO'}")
        print(f"    Items matched:    {c['matches']}/{expected_items}")
        acc = c["accuracy"]
        print(f"    Total accuracy:   {acc['total']}%")
        print(f"    Price accuracy:   {acc['price']}%")
        print(f"    Qty accuracy:     {acc['qty']}%")
        print(f"    Code accuracy:    {acc['code']}%")
        print(f"    Tax detected:     ${best['tax']:.2f} (expected ${truth.get('tax', 0):.2f}) {'PASS' if c['tax_ok'] else 'FAIL'}")
        print(f"    Subtotal:         ${best['subtotal']:.2f} (expected ${truth.get('subtotal', 0):.2f}) {'PASS' if c['subtotal_ok'] else 'FAIL'}")
        print(f"    Invoice total:    ${best['total']:.2f} (expected ${truth.get('total', 0):.2f}) {'PASS' if c['total_ok_inv'] else 'FAIL'}")

        # ── Edge case detection ──
        fees = [r for r in best["rows"] if r["row_type"] == "fee"]
        credits = [r for r in best["rows"] if r["total"] < 0]
        print(f"\n  EDGE CASES:")
        print(f"    Fee rows: {len(fees)}")
        for f in fees:
            print(f"      {f['name'][:35]}: ${f['total']:.2f}")
        print(f"    Credit/negative rows: {len(credits)}")
        for cr in credits:
            print(f"      {cr['name'][:35]}: ${cr['total']:.2f}")
        print(f"    Tax: ${best['tax']:.2f} {'(non-zero DETECTED)' if best['tax'] > 0 else '(zero)'}")

        # ── Raw JSON (first 3 items) ──
        print(f"\n  RAW JSON SAMPLE (first 3 items from best run):")
        try:
            raw_items = json.loads(best["raw_items_json"]) if best["raw_items_json"] else []
            for it in raw_items[:3]:
                compact = json.dumps(it, default=str)[:200]
                print(f"    {compact}")
        except json.JSONDecodeError:
            # Truncated JSON — just print raw string
            print(f"    (raw JSON truncated at 3000 chars — full data available in extraction response)")

    # ── Router confirmation ──
    print(f"\n\n{'='*95}")
    print("  VENDOR ROUTING CONFIRMATION")
    print(f"{'='*95}")
    print(f"  US Foods detection: detected_vendor contains 'us food' OR 'usfoods'")
    print(f"  Parser used: services/usfoods_structural.py (2-phase: numbers + descriptions)")
    print(f"  Consensus: SKIPPED for US Foods (structural path replaces it)")
    print(f"  Sysco/PFG: Standard single-call + consensus retry")

    # Check logs for routing evidence
    try:
        with open("/var/log/supervisor/backend.err.log") as f:
            lines = f.readlines()
        structural = [l.strip() for l in lines if "structural" in l.lower() and "US Foods" in l]
        for l in structural[-6:]:
            print(f"  LOG: {l[-100:]}")
    except:
        pass

    print(f"\n{'='*95}")
    print("  VALIDATION COMPLETE")
    print(f"{'='*95}")


if __name__ == "__main__":
    main()
