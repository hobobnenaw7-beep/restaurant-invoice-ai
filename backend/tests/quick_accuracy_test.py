"""
Quick 5-file Sysco accuracy test — measures the impact of qty_column_visible fix.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"

SAMPLE_FILES = [
    "296c4a30-127b-4252-ae72-84f5dfb75212.jpg",
    "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    "cc7dc90b-f682-4d5d-91fc-36de6439c60b.jpg",
    "receipt_20ea1a7e-762c-4e82-8c1d-bbdae92594d1.jpg",
    "receipt_333073da-edec-481e-9f49-f5b8199a15c3.jpg",
]

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


def main():
    token = login()
    total_line_items = 0
    total_trusted = 0
    total_review = 0
    total_false_trusts = 0
    total_vis_true = 0
    total_vis_false = 0
    total_vis_missing = 0
    total_qty1_trusted = 0
    total_qty1_review = 0

    for idx, fname in enumerate(SAMPLE_FILES):
        fpath = os.path.join(UPLOADS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"[{idx+1}] SKIP - {fname} not found")
            continue

        print(f"\n[{idx+1}/{len(SAMPLE_FILES)}] {fname}")
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

        line_items = [it for it in items if it.get("row_type") in ("line_item", "fee")]
        trusted = [it for it in line_items if it.get("confidence_level") == "trusted"]
        review = [it for it in line_items if it.get("needs_review", False)]

        vis_true = sum(1 for it in line_items if it.get("qty_column_visible") is True)
        vis_false = sum(1 for it in line_items if it.get("qty_column_visible") is False)
        vis_missing = sum(1 for it in line_items if "qty_column_visible" not in it)

        qty1_items = [it for it in line_items if float(it.get("quantity", 0) or 0) == 1.0]
        qty1_trusted = [it for it in qty1_items if it.get("confidence_level") == "trusted"]
        qty1_review = [it for it in qty1_items if it.get("needs_review", False)]

        trust_rate = len(trusted)/len(line_items)*100 if line_items else 0

        # False trust check
        false_trusts = 0
        for it in trusted:
            qty = float(it.get("quantity", 0) or 0)
            price = float(it.get("unit_price", 0) or 0)
            total = float(it.get("total", 0) or 0)
            if qty <= 0 or price <= 0 or total <= 0:
                false_trusts += 1
            else:
                computed = round(qty * price, 2)
                if abs(computed - total) > 0.01:
                    false_trusts += 1

        total_line_items += len(line_items)
        total_trusted += len(trusted)
        total_review += len(review)
        total_false_trusts += false_trusts
        total_vis_true += vis_true
        total_vis_false += vis_false
        total_vis_missing += vis_missing
        total_qty1_trusted += len(qty1_trusted)
        total_qty1_review += len(qty1_review)

        print(f"  Vendor: {vendor}")
        print(f"  Items: {len(line_items)}, Trusted: {len(trusted)}, Review: {len(review)}")
        print(f"  Trust rate: {trust_rate:.1f}%, False trusts: {false_trusts}")
        print(f"  qty_column_visible: T={vis_true} F={vis_false} M={vis_missing}")
        print(f"  qty=1 items: {len(qty1_items)} (trusted={len(qty1_trusted)}, review={len(qty1_review)})")
        print(f"  Time: {elapsed:.1f}s")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    overall_trust = total_trusted/total_line_items*100 if total_line_items else 0
    print(f"Total line items: {total_line_items}")
    print(f"Trusted: {total_trusted} ({overall_trust:.1f}%)")
    print(f"Review: {total_review}")
    print(f"False trusts: {total_false_trusts}")
    print(f"qty_column_visible: T={total_vis_true} F={total_vis_false} M={total_vis_missing}")
    print(f"qty=1 items: trusted={total_qty1_trusted}, review={total_qty1_review}")


if __name__ == "__main__":
    main()
