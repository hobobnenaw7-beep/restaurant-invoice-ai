"""
Multi-vendor before/after test: Sysco, US Foods, PFG
Shows row classification, column mapping, trust decision per row.
"""
import json
import os
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

VENDOR_SAMPLES = {
    "SYSCO": [
        "296c4a30-127b-4252-ae72-84f5dfb75212.jpg",
        "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    ],
    "US_FOODS": [
        "receipt_a7e60907-96aa-44d1-a84c-bdbf1cf04edb.png",
        "receipt_06ce771b-bd02-48c8-b309-f6ed1e2b796c.png",
    ],
    "PFG": [
        "receipt_c227970f-be14-4d52-9186-c6d63b0062b9.jpg",
        "receipt_bb764da3-eac7-431c-9266-6e378c765c47.jpg",
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


def print_row_detail(it):
    """Print one row with full trust_decision audit."""
    td = it.get("trust_decision", {})
    ext = td.get("extracted", {})
    gates = td.get("gates", {})

    name = ext.get("raw_name", "?")[:45]
    rt = td.get("row_type", "?")
    status = td.get("final_status", "?")
    reason = td.get("reason", "?")[:65]
    cat = td.get("failure_category", "?")

    qty = ext.get("quantity", 0)
    price = ext.get("unit_price", 0)
    total = ext.get("total", 0)

    # Format gates
    gate_parts = []
    for k, v in gates.items():
        if k == "validation_errors":
            gate_parts.append(f"ERRORS:{len(v)}")
        else:
            gate_parts.append(f"{k}={v}")
    gates_str = ", ".join(gate_parts)[:60]

    print(f"  {rt:12s} {status:22s} {name}")
    print(f"             qty={qty} price={price} total={total}")
    if gates_str:
        print(f"             gates: {gates_str}")
    if cat not in ("none", "n/a", "fee_valid"):
        print(f"             failure: {cat}")
    if "n/a" not in reason and reason:
        print(f"             reason: {reason}")

    # Show validation errors
    errors = it.get("validation_errors", [])
    for e in errors:
        print(f"             ! {e}")
    print()


def main():
    token = login()

    for vendor_label, files in VENDOR_SAMPLES.items():
        print(f"\n{'#'*70}")
        print(f"# VENDOR: {vendor_label}")
        print(f"{'#'*70}")

        vendor_totals = {"line_items": 0, "fees": 0, "excluded": 0,
                         "trusted": 0, "review": 0, "column_issues": 0, "false_trusts": 0}

        for fname in files:
            fpath = os.path.join(UPLOADS_DIR, fname)
            if not os.path.exists(fpath):
                print(f"\n  SKIP: {fname} not found")
                continue

            print(f"\n  FILE: {fname}")
            print(f"  {'─'*60}")

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

            data = result.get("extracted_data", result.get("data", result))
            items = data.get("items", [])
            vendor = result.get("detected_vendor", data.get("supplier_name", ""))

            print(f"  Detected vendor: {vendor}")
            print(f"  Time: {elapsed:.1f}s")
            print(f"  Total rows: {len(items)}")
            print()

            for it in items:
                rt = it.get("row_type", "unknown")
                conf = it.get("confidence_level", "unknown")

                if rt in ("line_item", "fee"):
                    print_row_detail(it)

                if rt == "line_item":
                    vendor_totals["line_items"] += 1
                elif rt == "fee":
                    vendor_totals["fees"] += 1
                else:
                    vendor_totals["excluded"] += 1

                if conf == "trusted":
                    vendor_totals["trusted"] += 1
                elif conf not in ("excluded",):
                    vendor_totals["review"] += 1

                errors = it.get("validation_errors", [])
                col_errors = [e for e in errors if "column_check" in e]
                if col_errors:
                    vendor_totals["column_issues"] += 1

                # False trust check
                if conf == "trusted" and rt == "line_item":
                    qty = float(it.get("quantity", 0) or 0)
                    price = float(it.get("unit_price", 0) or 0)
                    total = float(it.get("total", 0) or 0)
                    if qty > 0 and price > 0 and total > 0:
                        computed = round(qty * price, 2)
                        if abs(computed - total) > 0.01:
                            vendor_totals["false_trusts"] += 1

        scoreable = vendor_totals["line_items"] + vendor_totals["fees"]
        trust_rate = vendor_totals["trusted"] / scoreable * 100 if scoreable > 0 else 0
        print(f"\n  {'='*60}")
        print(f"  {vendor_label} SUMMARY:")
        print(f"    Line items: {vendor_totals['line_items']}")
        print(f"    Fee rows: {vendor_totals['fees']}")
        print(f"    Excluded (headers/totals): {vendor_totals['excluded']}")
        print(f"    Trusted: {vendor_totals['trusted']} ({trust_rate:.1f}%)")
        print(f"    Review: {vendor_totals['review']}")
        print(f"    Column issues detected: {vendor_totals['column_issues']}")
        print(f"    False trusts: {vendor_totals['false_trusts']}")


if __name__ == "__main__":
    main()
