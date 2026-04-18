"""
US Foods Dark Image Enhancement — Before vs After Test
=======================================================
Tests the retry-with-enhancement path on the failed/partial US Foods subset.

Uses DEDUPLICATED files (identical md5 → test once) to avoid wasting LLM calls.
Maps results back to all copies for the full report.
"""
import os, sys, json, time, hashlib, requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

# All 12 files from the original retest
ALL_FILES = [
    # 9 FAILED (0 items in previous test)
    "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",
    "receipt_057d0deb-ab3e-4633-adf0-439fa28cd475.jpg",
    "receipt_e1063baa-d0d1-4b9b-9059-8cdc84054b96.png",
    "receipt_a7e60907-96aa-44d1-a84c-bdbf1cf04edb.png",
    "receipt_b8b602e2-fa29-47b2-9d77-91e65a5dfbe9.jpg",
    "receipt_14fed72d-49dd-41f8-ab32-63acd989626a.jpg",
    "receipt_0b29c12f-592f-47ee-8957-2ec04194e532.png",
    "receipt_53392acc-40a4-45d6-a1d2-30f8aad0baa8.jpg",
    "receipt_642e4384-1a7b-43f8-b9d9-d270b9ef3be6.png",
    # 3 PARTIAL (1-2 items in previous test)
    "receipt_4ebbc3d0-4176-4ae6-a28a-64a0d608255b.jpg",
    "receipt_4c526a58-ad59-4f85-a164-819539515db6.png",
    "receipt_c51f7eca-e8a2-499a-a3a2-fe341494f9b9.jpg",
]

# Previous results (from vendor detection retest)
PREVIOUS_RESULTS = {
    "receipt_13a52320": {"status": "SUCCESS", "items": 16, "trusted": 16},
    "receipt_057d0deb": {"status": "SUCCESS", "items": 17, "trusted": 17},
    "receipt_e1063baa": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_a7e60907": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_b8b602e2": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_14fed72d": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_0b29c12f": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_53392acc": {"status": "PARTIAL", "items": 15, "trusted": 4},
    "receipt_642e4384": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_4ebbc3d0": {"status": "FAILED", "items": 0, "trusted": 0},
    "receipt_4c526a58": {"status": "SKIPPED", "items": 0, "trusted": 0},
    "receipt_c51f7eca": {"status": "FAILED", "items": 0, "trusted": 0},
}


def login():
    resp = requests.post(f"{API_URL}/api/auth/login",
                         json={"email": "demo@test.com", "password": "testpassword"})
    resp.raise_for_status()
    return resp.json()["token"]


def md5(fpath):
    return hashlib.md5(open(fpath, "rb").read()).hexdigest()


def extract_one(filepath, token, timeout=300):
    fname = os.path.basename(filepath)
    ext = fname.rsplit('.', 1)[-1].lower()
    ct_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}
    ct = ct_map.get(ext, 'application/octet-stream')
    try:
        with open(filepath, 'rb') as f:
            resp = requests.post(
                f"{API_URL}/api/upload/extract",
                files={"file": (fname, f, ct)},
                data={"document_type": "purchase_invoice"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=(30, timeout),
            )
        if resp.status_code != 200:
            return {"status": "failed", "error": f"HTTP {resp.status_code}"}
        return {"status": "ok", "data": resp.json()}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def analyze(result, fname):
    if result["status"] != "ok":
        return {"file": fname, "status": "FAILED", "items": 0, "trusted": 0,
                "false_trusts": 0, "error": result.get("error", "?")}
    data = result["data"]
    extracted = data.get("extracted_data") or {}
    items = extracted.get("items") or []
    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee", "credit", "discount")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    trust_rate = len(trusted) / len(scoreable) * 100 if scoreable else 0

    false_trusts = 0
    for it in trusted:
        if it.get("row_type") in ("fee", "credit", "discount"):
            continue
        q = float(it.get("quantity", 0) or 0)
        p = float(it.get("unit_price", 0) or 0)
        t = float(it.get("total", 0) or 0)
        if q > 0 and p > 0 and abs(t) > 0:
            if abs(round(q * p, 2) - abs(t)) > 0.02:
                false_trusts += 1

    if len(scoreable) == 0:
        cls = "FAILED"
    elif trust_rate < 50:
        cls = "PARTIAL"
    else:
        cls = "SUCCESS"

    return {
        "file": fname, "status": cls,
        "items": len(scoreable), "trusted": len(trusted),
        "trust_rate": round(trust_rate, 1), "false_trusts": false_trusts,
        "receipt_id": data.get("receipt_id", ""),
    }


def main():
    print("=" * 80)
    print("  US FOODS DARK IMAGE ENHANCEMENT — BEFORE vs AFTER")
    print("=" * 80)

    token = login()

    # Deduplicate by md5
    file_hashes = {}
    hash_to_files = {}
    for fname in ALL_FILES:
        fpath = os.path.join(UPLOADS_DIR, fname)
        if not os.path.exists(fpath):
            continue
        h = md5(fpath)
        file_hashes[fname] = h
        hash_to_files.setdefault(h, []).append(fname)

    # Pick one representative per unique hash
    unique_tests = {}
    for h, fnames in hash_to_files.items():
        unique_tests[h] = fnames[0]  # Test with first copy

    print(f"\n  Total files: {len(ALL_FILES)}")
    print(f"  Unique images: {len(unique_tests)}")
    for h, fname in unique_tests.items():
        copies = hash_to_files[h]
        fpath = os.path.join(UPLOADS_DIR, fname)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"    {fname[:50]} ({size_kb:.0f}KB) — {len(copies)} copies")

    # Run extraction on each unique image
    print(f"\n{'='*80}")
    print(f"  EXTRACTION (with retry-on-zero + dark enhancement)")
    print(f"{'='*80}")

    results_by_hash = {}
    for i, (h, fname) in enumerate(unique_tests.items(), 1):
        fpath = os.path.join(UPLOADS_DIR, fname)
        size_kb = os.path.getsize(fpath) / 1024
        copies = len(hash_to_files[h])

        print(f"\n  [{i}/{len(unique_tests)}] {fname[:50]} ({size_kb:.0f}KB, {copies} copies)")

        t0 = time.time()
        result = extract_one(fpath, token)
        elapsed = time.time() - t0

        analysis = analyze(result, fname)
        analysis["elapsed"] = round(elapsed, 1)
        results_by_hash[h] = analysis

        icon = {"SUCCESS": "+", "PARTIAL": "~", "FAILED": "X"}[analysis["status"]]
        print(f"    [{icon}] {analysis['status']} | items={analysis['items']} "
              f"trusted={analysis['trusted']} ({analysis.get('trust_rate', 0)}%) "
              f"| false_trusts={analysis['false_trusts']} | {elapsed:.1f}s")

        time.sleep(3)  # Rate limit

    # Build full results (map unique results back to all copies)
    print(f"\n{'='*80}")
    print(f"  BEFORE vs AFTER COMPARISON")
    print(f"{'='*80}")

    full_results = []
    for fname in ALL_FILES:
        fpath = os.path.join(UPLOADS_DIR, fname)
        prefix = fname.split(".")[0][:17]  # e.g., "receipt_13a52320"
        prev = PREVIOUS_RESULTS.get(prefix, {"status": "?", "items": 0, "trusted": 0})

        if not os.path.exists(fpath):
            full_results.append({
                "file": fname, "prev": prev,
                "now": {"status": "SKIPPED", "items": 0, "trusted": 0},
            })
            continue

        h = file_hashes.get(fname)
        now = results_by_hash.get(h, {"status": "?", "items": 0, "trusted": 0})
        full_results.append({"file": fname, "prev": prev, "now": now})

    # Print comparison table
    print(f"\n  {'File':<50} {'BEFORE':>12} {'AFTER':>12} {'CHANGE':>10}")
    print(f"  {'─'*86}")

    total_before_items = 0
    total_after_items = 0
    total_before_trusted = 0
    total_after_trusted = 0

    for r in full_results:
        prev = r["prev"]
        now = r["now"]
        before = f"{prev['status']}({prev['items']}i)"
        after = f"{now['status']}({now['items']}i)"

        if now["items"] > prev["items"]:
            change = f"+{now['items'] - prev['items']} items"
        elif now["items"] < prev["items"]:
            change = f"-{prev['items'] - now['items']} items"
        elif now["status"] != prev["status"]:
            change = f"{prev['status']}→{now['status']}"
        else:
            change = "same"

        total_before_items += prev["items"]
        total_after_items += now["items"]
        total_before_trusted += prev.get("trusted", 0)
        total_after_trusted += now.get("trusted", 0)

        print(f"  {r['file'][:49]:<50} {before:>12} {after:>12} {change:>10}")

    # Summary
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")

    before_success = sum(1 for r in full_results if r["prev"]["status"] == "SUCCESS")
    before_partial = sum(1 for r in full_results if r["prev"]["status"] == "PARTIAL")
    before_failed = sum(1 for r in full_results if r["prev"]["status"] == "FAILED")

    after_success = sum(1 for r in full_results if r["now"]["status"] == "SUCCESS")
    after_partial = sum(1 for r in full_results if r["now"]["status"] == "PARTIAL")
    after_failed = sum(1 for r in full_results if r["now"]["status"] == "FAILED")
    after_skipped = sum(1 for r in full_results if r["now"]["status"] == "SKIPPED")

    total_false = sum(r["now"].get("false_trusts", 0) for r in full_results)

    print(f"\n  {'Metric':<35} {'Before':>10} {'After':>10} {'Change':>10}")
    print(f"  {'─'*68}")
    print(f"  {'Success':.<35} {before_success:>10} {after_success:>10} {after_success - before_success:>+10}")
    print(f"  {'Partial':.<35} {before_partial:>10} {after_partial:>10} {after_partial - before_partial:>+10}")
    print(f"  {'Failed':.<35} {before_failed:>10} {after_failed:>10} {after_failed - before_failed:>+10}")
    print(f"  {'Skipped':.<35} {'1':>10} {after_skipped:>10} {'':>10}")
    print(f"  {'Total items extracted':.<35} {total_before_items:>10} {total_after_items:>10} {total_after_items - total_before_items:>+10}")
    print(f"  {'Total trusted items':.<35} {total_before_trusted:>10} {total_after_trusted:>10} {total_after_trusted - total_before_trusted:>+10}")
    print(f"  {'False trusts':.<35} {'0':>10} {total_false:>10} {'':>10}")

    # Check routing
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    db = client["test_database"]

    print(f"\n  ROUTING CHECK:")
    for r in full_results:
        rid = r["now"].get("receipt_id")
        if not rid:
            continue
        receipt = db.uploaded_receipts.find_one({"id": rid}, {"_id": 0, "vendor_routing": 1})
        if receipt and receipt.get("vendor_routing"):
            vr = receipt["vendor_routing"]
            print(f"    {r['file'][:45]} → parser={vr['selected_parser']}, conf={vr['confidence']:.3f}")

    client.close()

    # Save results
    with open("/tmp/usfoods_enhancement_results.json", "w") as f:
        json.dump({
            "before": {"success": before_success, "partial": before_partial, "failed": before_failed, "items": total_before_items, "trusted": total_before_trusted},
            "after": {"success": after_success, "partial": after_partial, "failed": after_failed, "items": total_after_items, "trusted": total_after_trusted, "false_trusts": total_false},
            "details": [{"file": r["file"], "prev": r["prev"], "now": {k: v for k, v in r["now"].items() if k != "data"}} for r in full_results],
        }, f, indent=2)
    print(f"\n  Results saved: /tmp/usfoods_enhancement_results.json")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
