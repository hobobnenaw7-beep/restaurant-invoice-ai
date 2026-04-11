"""
Extended 10-file Sysco accuracy test — broader validation of qty_column_visible fix.
"""
import json
import os
import sys
import time
import requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"

SAMPLE_FILES = [
    "e76577bc-bc4c-45ce-a99a-db566eef0393.jpg",
    "receipt_46ad2974-1de8-4a48-97cd-5622e4599da0.jpg",
    "receipt_801ef80d-14d3-40ff-a582-a8bdf696258a.jpg",
    "receipt_833003c8-7172-4ec6-9201-3dbb683561e5.jpg",
    "receipt_a33f716a-bf00-4204-ac2f-faa646d75042.jpg",
    "receipt_dabe0e27-5924-4ad2-8d53-d20b89001517.jpg",
    "receipt_e50c2bf6-5bd2-4fe4-a740-6bcef6917b14.jpg",
    "receipt_e5a037b0-8aa1-4537-9687-7a0525491faf.jpg",
    "95ebb38a-6d7e-4606-83f1-ec2a0f2a6d15.jpg",
    "receipt_458ec34d-8deb-44e5-9948-ed068ca80761.png",
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

        trust_rate = len(trusted)/len(line_items)*100 if line_items else 0
        print(f"  Vendor: {vendor}, Items: {len(line_items)}, Trust: {trust_rate:.0f}%")
        print(f"  Trusted: {len(trusted)}, Review: {len(review)}, False: {false_trusts}")
        print(f"  visible: T={vis_true} F={vis_false}, Time: {elapsed:.1f}s")

        # Show review items for debugging
        for it in review:
            name = (it.get("raw_name") or "")[:35]
            cat = it.get("numeric_failure_category", "?")
            vis = it.get("qty_column_visible", "?")
            print(f"    REVIEW: {name} cat={cat} vis={vis}")

    print("\n" + "=" * 60)
    overall = total_trusted/total_line_items*100 if total_line_items else 0
    print(f"TOTAL: {total_line_items} items, {total_trusted} trusted ({overall:.1f}%), {total_review} review, {total_false_trusts} false trusts")


if __name__ == "__main__":
    main()
