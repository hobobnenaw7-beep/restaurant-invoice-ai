"""
Multi-vendor trust gate test: Sysco, US Foods, PFG
Shows before/after with 2-3 example rows per vendor.
"""
import json
import os
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

VENDOR_SAMPLES = {
    "SYSCO": [
        "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",  # Has fuel surcharge
    ],
    "US_FOODS": [
        "receipt_b6c5bf31-c5e0-4224-822e-0d2e6e02ca95.jpg",  # Real US Foods with line items
        "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",  # Another US Foods JPG
        "receipt_70f3ed3f-f7e1-4973-b3c9-fd9c64fd86c0.jpg",  # Third US Foods JPG
    ],
    "PFG": [
        "receipt_20b24d09-5761-4c09-aca6-6925cb235a55.png",  # PFG with clear line items
        "receipt_c227970f-be14-4d52-9186-c6d63b0062b9.jpg",  # PFG with fuel surcharge
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


def print_row(it, idx):
    td = it.get("trust_decision", {})
    ext = td.get("extracted", {})
    gates = td.get("gates", {})

    name = ext.get("raw_name", "?")[:50]
    rt = td.get("row_type", "?")
    status = td.get("final_status", "?")
    reason = td.get("reason", "?")[:80]
    cat = td.get("failure_category", "?")

    qty = ext.get("quantity", 0)
    price = ext.get("unit_price", 0)
    total = ext.get("total", 0)

    status_icon = "✓" if status == "trusted" else "✗"
    print(f"    [{idx}] {status_icon} {status:22s} | {rt:10s} | {name}")
    print(f"         qty={qty}  price={price}  total={total}")

    # Gate details
    gate_parts = []
    for k, v in gates.items():
        if k == "validation_errors":
            for e in v:
                gate_parts.append(f"! {e[:70]}")
        elif k == "fee_math_rule":
            gate_parts.append(f"{k}: {v}")
        else:
            gate_parts.append(f"{k}={v}")

    for gp in gate_parts[:4]:
        print(f"         {gp}")

    if cat not in ("none", "n/a", "fee_valid", "?"):
        print(f"         failure_category: {cat}")
    if reason and reason != "n/a":
        print(f"         reason: {reason}")
    print()


def main():
    token = login()

    for vendor_label, files in VENDOR_SAMPLES.items():
        print(f"\n{'='*75}")
        print(f" {vendor_label}")
        print(f"{'='*75}")

        vendor_total = 0
        vendor_trusted = 0
        vendor_review = 0
        vendor_fees = 0
        vendor_fees_trusted = 0
        vendor_false = 0
        example_trusted = []
        example_review = []

        for fname in files:
            fpath = os.path.join(UPLOADS_DIR, fname)
            if not os.path.exists(fpath):
                print(f"\n  SKIP: {fname} not found")
                continue

            print(f"\n  File: {fname}")
            t0 = time.time()
            result = extract_invoice(fpath, token)
            elapsed = time.time() - t0

            if "error" in result:
                print(f"  ERROR ({elapsed:.0f}s): {result.get('error', '')[:100]}")
                continue

            data = result.get("extracted_data", result.get("data", result))
            items = data.get("items", [])
            vendor = result.get("detected_vendor", data.get("supplier_name", ""))

            scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee")]
            trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
            review = [it for it in scoreable if it.get("confidence_level") != "trusted" and it.get("confidence_level") != "excluded"]

            print(f"  Vendor: {vendor} | Items: {len(scoreable)} | Trusted: {len(trusted)} | Review: {len(review)} | Time: {elapsed:.1f}s")

            vendor_total += len(scoreable)
            vendor_trusted += len(trusted)
            vendor_review += len(review)

            for it in scoreable:
                rt = it.get("row_type", "?")
                conf = it.get("confidence_level", "?")
                if rt == "fee":
                    vendor_fees += 1
                    if conf == "trusted":
                        vendor_fees_trusted += 1

                # False trust check
                if conf == "trusted" and rt == "line_item":
                    qty = float(it.get("quantity", 0) or 0)
                    price = float(it.get("unit_price", 0) or 0)
                    total = float(it.get("total", 0) or 0)
                    if qty > 0 and price > 0 and total > 0:
                        computed = round(qty * price, 2)
                        if abs(computed - total) > 0.01:
                            vendor_false += 1

                # Collect examples
                if conf == "trusted" and len(example_trusted) < 3:
                    example_trusted.append(it)
                elif conf != "trusted" and conf != "excluded" and len(example_review) < 3:
                    example_review.append(it)

            # Print all rows for this file
            print(f"\n  All rows:")
            for idx, it in enumerate(scoreable):
                print_row(it, idx + 1)

        # Vendor summary
        trust_rate = vendor_trusted / vendor_total * 100 if vendor_total > 0 else 0
        print(f"\n  {'─'*70}")
        print(f"  {vendor_label} SUMMARY:")
        print(f"    Total scoreable: {vendor_total}")
        print(f"    Trusted: {vendor_trusted} ({trust_rate:.1f}%)")
        print(f"    Review: {vendor_review}")
        print(f"    Fees: {vendor_fees_trusted}/{vendor_fees} trusted")
        print(f"    False trusts: {vendor_false}")

        # Example rows
        if example_trusted:
            print(f"\n  EXAMPLE TRUSTED ROWS:")
            for it in example_trusted[:2]:
                print_row(it, "T")
        if example_review:
            print(f"\n  EXAMPLE REVIEW ROWS:")
            for it in example_review[:2]:
                print_row(it, "R")


if __name__ == "__main__":
    main()
