"""
Before/After Results — Tests fee handling, column checks, and trust_decision audit
across Sysco, US Foods, and PFG invoices.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@test.com", "password": "testpassword",
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


def analyze_result(result, fname):
    """Analyze extraction result and return structured report."""
    data = result.get("extracted_data", result.get("data", result))
    items = data.get("items", [])
    vendor = result.get("detected_vendor", data.get("supplier_name", ""))

    report = {
        "file": fname,
        "vendor": vendor,
        "total_items": len(items),
        "rows": [],
    }

    by_type = {}
    by_status = {}
    fees = []
    column_issues = []
    false_trusts = 0

    for it in items:
        rt = it.get("row_type", "unknown")
        conf = it.get("confidence_level", "unknown")
        td = it.get("trust_decision", {})

        by_type[rt] = by_type.get(rt, 0) + 1
        by_status[conf] = by_status.get(conf, 0) + 1

        if rt == "fee":
            fees.append({
                "name": (it.get("raw_name") or "")[:40],
                "total": it.get("total", 0),
                "status": conf,
                "reason": td.get("reason", "?")[:60],
            })

        errors = it.get("validation_errors", [])
        col_errors = [e for e in errors if "column_check" in e]
        if col_errors:
            column_issues.append({
                "name": (it.get("raw_name") or "")[:40],
                "errors": col_errors,
            })

        # False trust check
        if conf == "trusted" and rt == "line_item":
            qty = float(it.get("quantity", 0) or 0)
            price = float(it.get("unit_price", 0) or 0)
            total = float(it.get("total", 0) or 0)
            if qty > 0 and price > 0 and total > 0:
                computed = round(qty * price, 2)
                if abs(computed - total) > 0.01:
                    false_trusts += 1

        # Compact row record
        report["rows"].append({
            "name": (it.get("raw_name") or "")[:45],
            "type": rt,
            "qty": it.get("quantity", 0),
            "price": it.get("unit_price", 0),
            "total": it.get("total", 0),
            "status": conf,
            "reason": (td.get("reason") or "")[:60],
        })

    report["by_type"] = by_type
    report["by_status"] = by_status
    report["fees"] = fees
    report["column_issues"] = column_issues
    report["false_trusts"] = false_trusts

    return report


def print_report(report):
    vendor = report["vendor"]
    print(f"\n{'='*70}")
    print(f"VENDOR: {vendor}")
    print(f"FILE:   {report['file']}")
    print(f"{'='*70}")

    # Row types
    print(f"\nRow Types: {report['by_type']}")
    print(f"Status:    {report['by_status']}")
    print(f"False Trusts: {report['false_trusts']}")

    # Fee handling
    if report["fees"]:
        print(f"\n  FEE ROWS ({len(report['fees'])}):")
        for fee in report["fees"]:
            print(f"    {fee['name']:40s} total=${fee['total']:>8.2f} → {fee['status']} ({fee['reason']})")

    # Column issues
    if report["column_issues"]:
        print(f"\n  COLUMN ISSUES ({len(report['column_issues'])}):")
        for ci in report["column_issues"]:
            print(f"    {ci['name']:40s}")
            for e in ci["errors"]:
                print(f"      - {e}")

    # Per-row breakdown
    print(f"\n  ROWS ({len(report['rows'])}):")
    print(f"  {'Name':45s} {'Type':12s} {'Qty':>5s} {'Price':>8s} {'Total':>8s} {'Status':20s}")
    print(f"  {'-'*45} {'-'*12} {'-'*5} {'-'*8} {'-'*8} {'-'*20}")
    for row in report["rows"]:
        qty_s = f"{row['qty']}" if row['qty'] else "-"
        price_s = f"{row['price']:.2f}" if row['price'] else "-"
        total_s = f"{row['total']:.2f}" if row['total'] else "-"
        print(f"  {row['name']:45s} {row['type']:12s} {qty_s:>5s} {price_s:>8s} {total_s:>8s} {row['status']:20s}")


def main():
    token = login()

    # Find sample files for each vendor
    all_files = os.listdir(UPLOADS_DIR)

    # Test with known Sysco files
    sysco_files = [
        "296c4a30-127b-4252-ae72-84f5dfb75212.jpg",
        "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    ]

    # Find US Foods and PFG files (scan for the first few)
    test_queue = []
    for fname in sysco_files:
        fpath = os.path.join(UPLOADS_DIR, fname)
        if os.path.exists(fpath):
            test_queue.append(fpath)

    # Add a few more files that might be other vendors
    other_candidates = [
        "receipt_46ad2974-1de8-4a48-97cd-5622e4599da0.jpg",
        "receipt_801ef80d-14d3-40ff-a582-a8bdf696258a.jpg",
        "cc7dc90b-f682-4d5d-91fc-36de6439c60b.jpg",
        "receipt_e50c2bf6-5bd2-4fe4-a740-6bcef6917b14.jpg",
        "receipt_a33f716a-bf00-4204-ac2f-faa646d75042.jpg",
        "receipt_dabe0e27-5924-4ad2-8d53-d20b89001517.jpg",
    ]
    for fname in other_candidates:
        fpath = os.path.join(UPLOADS_DIR, fname)
        if os.path.exists(fpath):
            test_queue.append(fpath)

    vendor_stats = {}

    for fpath in test_queue:
        fname = os.path.basename(fpath)
        print(f"\nProcessing: {fname}...")
        t0 = time.time()
        try:
            result = extract_invoice(fpath, token)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        elapsed = time.time() - t0

        if "error" in result and isinstance(result["error"], str):
            print(f"  ERROR ({elapsed:.0f}s): {result['error'][:100]}")
            continue

        report = analyze_result(result, fname)
        print_report(report)

        # Aggregate by vendor
        v = report["vendor"] or "UNKNOWN"
        if v not in vendor_stats:
            vendor_stats[v] = {"total": 0, "trusted": 0, "review": 0, "excluded": 0,
                               "fees_total": 0, "fees_trusted": 0, "false_trusts": 0}
        stats = vendor_stats[v]
        for status, count in report["by_status"].items():
            if status == "trusted":
                stats["trusted"] += count
            elif status == "excluded":
                stats["excluded"] += count
            else:
                stats["review"] += count
        stats["total"] += report["total_items"]
        stats["fees_total"] += len(report["fees"])
        stats["fees_trusted"] += sum(1 for f in report["fees"] if f["status"] == "trusted")
        stats["false_trusts"] += report["false_trusts"]

        print(f"\n  Time: {elapsed:.1f}s")

    # Final summary
    print(f"\n\n{'='*70}")
    print("VENDOR SUMMARY")
    print(f"{'='*70}")
    for vendor, stats in vendor_stats.items():
        scoreable = stats["total"] - stats["excluded"]
        trust_rate = stats["trusted"] / scoreable * 100 if scoreable > 0 else 0
        print(f"\n{vendor}:")
        print(f"  Total items: {stats['total']}")
        print(f"  Scoreable: {scoreable}")
        print(f"  Trusted: {stats['trusted']} ({trust_rate:.1f}%)")
        print(f"  Review: {stats['review']}")
        print(f"  Excluded: {stats['excluded']}")
        print(f"  Fees: {stats['fees_trusted']}/{stats['fees_total']} trusted")
        print(f"  False Trusts: {stats['false_trusts']}")


if __name__ == "__main__":
    main()
