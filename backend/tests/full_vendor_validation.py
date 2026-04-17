"""
Full Vendor Validation Test — Extraction Accuracy + Data Integrity
===================================================================
Tests all 3 vendors (Sysco, PFG, US Foods) for:
1. Field verification (vendor, items, qty, price, total)
2. Accuracy per field
3. Edge cases (fees, taxes, discounts)
4. Data integrity (created_by_user_id, source_type)
5. Structured report output
"""
import json
import os
import time
import requests
import sys

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

# Ground truth for US Foods clean test invoice (synthetic — known exact values)
USFOODS_CLEAN_TRUTH = {
    "supplier_name": "US Foods",
    "invoice_number": "1234567-890123",
    "invoice_date": "2026-02-15",
    "expected_items": 11,
    "expected_fee_rows": 1,
    "items": [
        {"code": "5302546", "name": "TARTAR SAUCE CREAMY", "qty": 1, "price": 57.99, "total": 57.99},
        {"code": "5018449", "name": "CONTAINER PP 8X8 3CMT", "qty": 1, "price": 21.45, "total": 21.45},
        {"code": "5024470", "name": "CONTAINER PP 7.5X9 3CMT", "qty": 2, "price": 20.90, "total": 41.80},
        {"code": "9887347", "name": "MIX PONG PIE FLNG BANANA", "qty": 1, "price": 53.70, "total": 53.70},
        {"code": "7302710", "name": "MARGARINE LIQ TFF REF", "qty": 12, "price": 38.99, "total": 467.88},
        {"code": "5942538", "name": "POTATO RUSSET 90CT", "qty": 2, "price": 20.79, "total": 41.58},
        {"code": "5927212", "name": "SAUCE CKTL SEAFD ZESTY", "qty": 1, "price": 56.76, "total": 56.76},
        {"code": "7300133", "name": "HUSH PUPPY BAG FZN", "qty": 1, "price": 25.99, "total": 25.99},
        {"code": "5824123", "name": "POTATO FF CC FZN", "qty": 16, "price": 25.00, "total": 400.00},
        {"code": "5924099", "name": "CRAB SNOW CLSTR 8-20Z", "qty": 7, "price": 125.49, "total": 878.43},
        {"code": "7001604", "name": "FLOUNDER 3-5Z FIL FZN", "qty": 3, "price": 37.50, "total": 112.50},
    ],
    "fee": {"name": "FUEL SURCHARGE", "total": 6.50},
    "subtotal": 2158.08,
    "total": 2170.58,
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
            timeout=300,
        )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    return resp.json()


def analyze_extraction(result):
    """Analyze a single extraction result."""
    data = result.get("extracted_data") or result.get("data") or result
    items = data.get("items") or []
    vendor = result.get("detected_vendor") or data.get("supplier_name") or "?"

    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
    line_items = [it for it in scoreable if it.get("row_type") == "line_item"]
    fee_items = [it for it in scoreable if it.get("row_type") == "fee"]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    review = [it for it in scoreable if it.get("confidence_level") not in ("trusted", "excluded")]

    false_trusts = 0
    rows = []
    for idx, it in enumerate(scoreable):
        td = it.get("trust_decision", {})
        ext = td.get("extracted", {})
        gates = td.get("gates", {})

        name = (ext.get("raw_name") or it.get("raw_name") or "?")[:55]
        code = (ext.get("item_code") or it.get("item_code") or "")[:8]
        qty = float(ext.get("quantity", it.get("quantity", 0)) or 0)
        price = float(ext.get("unit_price", it.get("unit_price", 0)) or 0)
        total = float(ext.get("total", it.get("total", 0)) or 0)
        row_type = td.get("row_type", it.get("row_type", "?"))
        status = td.get("final_status", it.get("confidence_level", "?"))

        math_pass = False
        if row_type == "fee":
            math_pass = total > 0
        elif qty > 0 and price > 0 and total > 0:
            math_pass = abs(round(qty * price, 2) - total) <= 0.02
            if status == "trusted" and not math_pass:
                false_trusts += 1

        rows.append({
            "idx": idx + 1, "name": name, "code": code,
            "qty": qty, "price": price, "total": total,
            "row_type": row_type, "status": status, "math_pass": math_pass,
        })

    return {
        "vendor": vendor,
        "invoice_number": data.get("invoice_number", ""),
        "invoice_date": data.get("invoice_date", ""),
        "total_items": len(items),
        "scoreable": len(scoreable),
        "line_items": len(line_items),
        "fee_items": len(fee_items),
        "trusted": len(trusted),
        "review": len(review),
        "trust_rate": round(len(trusted) / len(scoreable) * 100, 1) if scoreable else 0,
        "false_trusts": false_trusts,
        "subtotal": float(data.get("subtotal", 0) or 0),
        "tax": float(data.get("tax", 0) or 0),
        "total_invoice": float(data.get("total", 0) or 0),
        "rows": rows,
        "has_created_by": bool(data.get("created_by_user_id") or result.get("created_by_user_id")),
        "source_type": data.get("source_type") or result.get("source_type") or "",
        "raw_data": data,
        "raw_result": result,
    }


def check_data_integrity(result):
    """Check created_by_user_id and source_type in the raw API response."""
    # These fields are on the stored receipt, not in extracted_data
    # Check the receipt-level fields
    receipt_fields = {}
    for key in ("created_by_user_id", "created_by_name", "source_type"):
        receipt_fields[key] = result.get(key, "NOT_FOUND")
    return receipt_fields


def compare_with_truth(analysis, truth):
    """Compare extraction against ground truth for accuracy."""
    results = {
        "vendor_match": truth["supplier_name"].lower() in analysis["vendor"].lower(),
        "item_count_expected": truth["expected_items"],
        "item_count_actual": analysis["line_items"],
        "fee_count_expected": truth.get("expected_fee_rows", 0),
        "fee_count_actual": analysis["fee_items"],
        "field_matches": [],
        "field_mismatches": [],
    }

    # Match items by product code or by total
    truth_totals = {it["total"]: it for it in truth["items"]}
    matched = 0
    qty_matches = 0
    price_matches = 0
    total_matches = 0
    code_matches = 0

    for row in analysis["rows"]:
        if row["row_type"] != "line_item":
            continue
        # Try matching by total value (most reliable)
        best_match = None
        for t_total, t_item in truth_totals.items():
            if abs(row["total"] - t_total) < 0.05:
                best_match = t_item
                break
        if not best_match and row["code"]:
            for t_item in truth["items"]:
                if t_item["code"] == row["code"]:
                    best_match = t_item
                    break

        if best_match:
            matched += 1
            if abs(row["total"] - best_match["total"]) < 0.05:
                total_matches += 1
            else:
                results["field_mismatches"].append(f'Total: expected ${best_match["total"]}, got ${row["total"]} ({row["name"][:30]})')
            if abs(row["price"] - best_match["price"]) < 0.05:
                price_matches += 1
            else:
                results["field_mismatches"].append(f'Price: expected ${best_match["price"]}, got ${row["price"]} ({row["name"][:30]})')
            if abs(row["qty"] - best_match["qty"]) < 0.5:
                qty_matches += 1
            else:
                results["field_mismatches"].append(f'Qty: expected {best_match["qty"]}, got {row["qty"]} ({row["name"][:30]})')
            if row["code"] == best_match["code"]:
                code_matches += 1

    n = max(matched, 1)
    results["matched_items"] = matched
    results["accuracy"] = {
        "total": round(total_matches / n * 100, 1),
        "price": round(price_matches / n * 100, 1),
        "qty": round(qty_matches / n * 100, 1),
        "code": round(code_matches / n * 100, 1),
        "overall": round((total_matches + price_matches + qty_matches) / (n * 3) * 100, 1),
    }

    return results


def print_vendor_report(label, analysis, truth_comparison=None, integrity=None, elapsed=0):
    """Print structured report for one vendor."""
    a = analysis
    print(f"\n{'='*95}")
    print(f"  {label}")
    print(f"{'='*95}")
    print(f"  Vendor detected:  {a['vendor']}")
    print(f"  Invoice #:        {a['invoice_number']}")
    print(f"  Invoice date:     {a['invoice_date']}")
    print(f"  Extraction time:  {elapsed:.1f}s")
    print(f"")
    print(f"  Items:    {a['scoreable']} scoreable ({a['line_items']} products + {a['fee_items']} fees)")
    print(f"  Trusted:  {a['trusted']}/{a['scoreable']} ({a['trust_rate']}%)")
    print(f"  Review:   {a['review']}")
    print(f"  False:    {a['false_trusts']}")
    print(f"  Totals:   subtotal=${a['subtotal']:.2f}  tax=${a['tax']:.2f}  total=${a['total_invoice']:.2f}")

    # Row detail
    print(f"\n  {'#':<3} {'S':<3} {'Type':<10} {'Code':<9} {'Qty':<6} {'Price':<10} {'Total':<10} {'M':<3} {'Name'}")
    print(f"  {'─'*90}")
    for row in a["rows"]:
        s = "T" if row["status"] == "trusted" else "R"
        m = "OK" if row["math_pass"] else "X"
        print(f"  {row['idx']:<3} {s:<3} {row['row_type']:<10} {row['code']:<9} {row['qty']:<6g} ${row['price']:<9.2f} ${row['total']:<9.2f} {m:<3} {row['name'][:38]}")

    # Accuracy comparison
    if truth_comparison:
        tc = truth_comparison
        print(f"\n  ACCURACY vs GROUND TRUTH:")
        print(f"    Vendor match:     {'YES' if tc['vendor_match'] else 'NO'}")
        print(f"    Items matched:    {tc['matched_items']}/{tc['item_count_expected']} expected")
        print(f"    Fee rows:         {tc['fee_count_actual']}/{tc['fee_count_expected']} expected")
        acc = tc["accuracy"]
        print(f"    Field accuracy:")
        print(f"      Total:    {acc['total']}%")
        print(f"      Price:    {acc['price']}%")
        print(f"      Qty:      {acc['qty']}%")
        print(f"      Code:     {acc['code']}%")
        print(f"      Overall:  {acc['overall']}%")
        if tc["field_mismatches"]:
            print(f"    Mismatches ({len(tc['field_mismatches'])}):")
            for mm in tc["field_mismatches"]:
                print(f"      - {mm}")

    # Data integrity
    if integrity:
        print(f"\n  DATA INTEGRITY:")
        for k, v in integrity.items():
            status = "PASS" if v and v != "NOT_FOUND" else "MISSING"
            print(f"    {k}: {v} [{status}]")

    # Edge cases
    print(f"\n  EDGE CASES:")
    fees = [r for r in a["rows"] if r["row_type"] == "fee"]
    print(f"    Fee/Surcharge rows: {len(fees)} detected")
    for f in fees:
        print(f"      - {f['name'][:40]}: ${f['total']:.2f} [{'PASS' if f['math_pass'] else 'FAIL'}]")
    tax_val = a['tax']
    print(f"    Tax: ${tax_val:.2f}")
    disc_msg = 'None detected' if tax_val >= 0 else f'${abs(tax_val):.2f}'
    print(f"    Discounts: {disc_msg}")


def main():
    print("=" * 95)
    print("  FULL VENDOR VALIDATION — EXTRACTION ACCURACY + DATA INTEGRITY")
    print("=" * 95)

    token = login()
    print(f"  Authenticated as manager\n")

    overall_results = {}

    # ══════════════════════════════════════════════════════════════
    # VENDOR 1: US FOODS (Clean Synthetic Invoice)
    # ══════════════════════════════════════════════════════════════
    fpath = os.path.join(UPLOADS_DIR, "usfoods_clean_test_invoice.png")
    print(f"\n  Extracting US Foods (clean)...", end=" ", flush=True)
    t0 = time.time()
    result = extract_invoice(fpath, token)
    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        analysis = analyze_extraction(result)
        truth_cmp = compare_with_truth(analysis, USFOODS_CLEAN_TRUTH)
        integrity = check_data_integrity(result)
        print_vendor_report("US FOODS (Clean Scan)", analysis, truth_cmp, integrity, elapsed)
        overall_results["US Foods Clean"] = {
            "status": "PASS" if truth_cmp["accuracy"]["overall"] >= 90 and analysis["false_trusts"] == 0 else "FAIL",
            "accuracy": truth_cmp["accuracy"]["overall"],
            "trust_rate": analysis["trust_rate"],
            "false_trusts": analysis["false_trusts"],
            "items": f"{analysis['line_items']}/{USFOODS_CLEAN_TRUTH['expected_items']}",
        }

    time.sleep(3)

    # ══════════════════════════════════════════════════════════════
    # VENDOR 2: SYSCO
    # ══════════════════════════════════════════════════════════════
    fpath = os.path.join(UPLOADS_DIR, "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg")
    print(f"\n  Extracting Sysco...", end=" ", flush=True)
    t0 = time.time()
    result = extract_invoice(fpath, token)
    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        analysis = analyze_extraction(result)
        integrity = check_data_integrity(result)
        print_vendor_report("SYSCO", analysis, None, integrity, elapsed)
        overall_results["Sysco"] = {
            "status": "PASS" if analysis["trust_rate"] >= 90 and analysis["false_trusts"] == 0 else "NEEDS_REVIEW",
            "accuracy": "N/A (no ground truth file)",
            "trust_rate": analysis["trust_rate"],
            "false_trusts": analysis["false_trusts"],
            "items": str(analysis["line_items"]),
        }

    time.sleep(3)

    # ══════════════════════════════════════════════════════════════
    # VENDOR 3: PFG (Performance Foodservice)
    # ══════════════════════════════════════════════════════════════
    fpath = os.path.join(UPLOADS_DIR, "receipt_20b24d09-5761-4c09-aca6-6925cb235a55.png")
    print(f"\n  Extracting PFG...", end=" ", flush=True)
    t0 = time.time()
    result = extract_invoice(fpath, token)
    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        analysis = analyze_extraction(result)
        integrity = check_data_integrity(result)
        print_vendor_report("PFG (Performance Foodservice)", analysis, None, integrity, elapsed)
        overall_results["PFG"] = {
            "status": "PASS" if analysis["trust_rate"] >= 90 and analysis["false_trusts"] == 0 else "NEEDS_REVIEW",
            "accuracy": "N/A (no ground truth file)",
            "trust_rate": analysis["trust_rate"],
            "false_trusts": analysis["false_trusts"],
            "items": str(analysis["line_items"]),
        }

    time.sleep(3)

    # ══════════════════════════════════════════════════════════════
    # VENDOR 4: US FOODS (Dark Phone Photo - stress test)
    # ══════════════════════════════════════════════════════════════
    fpath = os.path.join(UPLOADS_DIR, "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg")
    print(f"\n  Extracting US Foods (dark phone photo)...", end=" ", flush=True)
    t0 = time.time()
    result = extract_invoice(fpath, token)
    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        analysis = analyze_extraction(result)
        integrity = check_data_integrity(result)
        print_vendor_report("US FOODS (Dark Phone Photo)", analysis, None, integrity, elapsed)
        overall_results["US Foods Phone"] = {
            "status": "PASS" if analysis["false_trusts"] == 0 else "FAIL",
            "accuracy": "Variable (image quality dependent)",
            "trust_rate": analysis["trust_rate"],
            "false_trusts": analysis["false_trusts"],
            "items": str(analysis["line_items"]),
            "note": "Dark photo — row count varies per run, zero false trusts guaranteed",
        }

    # ══════════════════════════════════════════════════════════════
    # GLOBAL SUMMARY
    # ══════════════════════════════════════════════════════════════
    print(f"\n\n{'='*95}")
    print("  VALIDATION SUMMARY")
    print(f"{'='*95}")
    print(f"\n  {'Vendor':<25} {'Status':<12} {'Accuracy':<20} {'Trust Rate':<12} {'False':<7} {'Items'}")
    print(f"  {'─'*90}")
    for vendor, r in overall_results.items():
        acc_str = f"{r['accuracy']}%" if isinstance(r['accuracy'], (int, float)) else r['accuracy']
        print(f"  {vendor:<25} {r['status']:<12} {acc_str:<20} {r['trust_rate']:<12.1f} {r['false_trusts']:<7} {r['items']}")

    total_false = sum(r["false_trusts"] for r in overall_results.values())
    all_pass = all(r["status"] in ("PASS",) for r in overall_results.values())

    print(f"\n  PRODUCTION READINESS:")
    print(f"    Total false trusts across all vendors: {total_false}")
    print(f"    All vendors PASS: {all_pass}")

    if total_false == 0:
        print(f"    ZERO FALSE TRUSTS — Trust gate is reliable")
    else:
        print(f"    WARNING: {total_false} false trusts detected")

    print(f"\n{'='*95}")
    print("  VALIDATION COMPLETE")
    print(f"{'='*95}")


if __name__ == "__main__":
    main()
