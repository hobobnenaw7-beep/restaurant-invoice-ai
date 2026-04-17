"""
Re-test US Foods failed/partial subset with new multi-signal vendor detection.
Tests that the structural parser is now triggered consistently.
"""
import os, sys, json, time, requests

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"

def login():
    resp = requests.post(f"{API_URL}/api/auth/login",
                         json={"email": "demo@test.com", "password": "testpassword"})
    resp.raise_for_status()
    return resp.json()["token"]


# The 12 US Foods files that failed or were partial in the stress test
# 9 failed (0 items) + 3 partial (1-2 items)
USFOODS_RETEST_FILES = [
    # FAILED (0 items)
    "receipt_13a52320-c3f6-4cfd-a6c8-9677ba9dfa86.jpg",
    "receipt_057d0deb-ab3e-4633-adf0-439fa28cd475.jpg",
    "receipt_e1063baa-d0d1-4b9b-9059-8cdc84054b96.png",
    "receipt_a7e60907-96aa-44d1-a84c-bdbf1cf04edb.png",
    "receipt_b8b602e2-fa29-47b2-9d77-91e65a5dfbe9.jpg",
    "receipt_14fed72d-49dd-41f8-ab32-63acd989626a.jpg",
    "receipt_0b29c12f-592f-47ee-8957-2ec04194e532.png",
    "receipt_53392acc-40a4-45d6-a1d2-30f8aad0baa8.jpg",
    "receipt_642e4384-1a7b-43f8-b9d9-d270b9ef3be6.png",
    # PARTIAL (1-2 items)
    "receipt_4ebbc3d0-4176-4ae6-a28a-64a0d608255b.jpg",
    "receipt_4c526a58-ad59-4f85-a164-819539515db6.png",
    "receipt_c51f7eca-e8a2-499a-a3a2-fe341494f9b9.jpg",
]

def extract_one(filepath, token, timeout=300):
    fname = os.path.basename(filepath)
    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else 'jpg'
    ct_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
              'png': 'image/png', 'pdf': 'application/pdf'}
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
            return {"status": "failed", "error": f"HTTP {resp.status_code}",
                    "detail": resp.text[:300]}
        return {"status": "ok", "data": resp.json()}
    except requests.Timeout:
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def main():
    print("=" * 80)
    print("  US FOODS RE-TEST: Failed/Partial Subset")
    print("  Testing multi-signal vendor detection + structural parser routing")
    print("=" * 80)

    token = login()
    results = []

    for i, fname in enumerate(USFOODS_RETEST_FILES, 1):
        fpath = os.path.join(UPLOADS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  [{i:2d}/{len(USFOODS_RETEST_FILES)}] SKIP {fname} — file not found")
            results.append({"file": fname, "status": "skipped", "reason": "file not found"})
            continue

        size_kb = os.path.getsize(fpath) / 1024
        print(f"\n  [{i:2d}/{len(USFOODS_RETEST_FILES)}] {fname} ({size_kb:.0f}KB)")

        t0 = time.time()
        result = extract_one(fpath, token)
        elapsed = time.time() - t0

        if result["status"] != "ok":
            print(f"    ERROR: {result.get('error', '?')} ({elapsed:.1f}s)")
            results.append({
                "file": fname, "status": "failed",
                "error": result.get("error", "?"), "elapsed": round(elapsed, 1)
            })
            time.sleep(3)  # Rate limit
            continue

        data = result["data"]
        extracted = data.get("extracted_data") or data.get("data") or {}
        items = extracted.get("items") or []
        vendor = data.get("detected_vendor") or "?"
        receipt_id = data.get("receipt_id", "")

        scoreable = [it for it in items
                     if it.get("row_type") in ("line_item", "fee", "credit", "discount")]
        trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
        trust_rate = len(trusted) / len(scoreable) * 100 if scoreable else 0

        # Check for false trusts
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

        # Classification
        if len(scoreable) == 0:
            cls = "FAILED"
        elif trust_rate < 50:
            cls = "PARTIAL"
        else:
            cls = "SUCCESS"

        rec = {
            "file": fname, "status": cls, "vendor": vendor,
            "receipt_id": receipt_id,
            "total_items": len(items), "scoreable": len(scoreable),
            "trusted": len(trusted), "trust_rate": round(trust_rate, 1),
            "false_trusts": false_trusts, "elapsed": round(elapsed, 1),
            "size_kb": round(size_kb, 0),
        }
        results.append(rec)

        status_icon = {"SUCCESS": "+", "PARTIAL": "~", "FAILED": "X"}[cls]
        print(f"    [{status_icon}] {cls} | vendor={vendor} | "
              f"items={len(scoreable)} trusted={len(trusted)} "
              f"({trust_rate:.0f}%) | false_trusts={false_trusts} | {elapsed:.1f}s")

        time.sleep(3)  # Rate limit between extractions

    # ── Summary ──
    print(f"\n{'='*80}")
    print(f"  RE-TEST SUMMARY")
    print(f"{'='*80}")

    success = sum(1 for r in results if r.get("status") == "SUCCESS")
    partial = sum(1 for r in results if r.get("status") == "PARTIAL")
    failed = sum(1 for r in results if r.get("status") == "FAILED")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    total_false = sum(r.get("false_trusts", 0) for r in results)

    print(f"  Total files: {len(USFOODS_RETEST_FILES)}")
    print(f"  Success: {success}")
    print(f"  Partial: {partial}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    print(f"  False trusts: {total_false}")

    # Check routing — query DB for routing metadata
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    db = client["test_database"]

    print(f"\n  ROUTING VERIFICATION:")
    structural_count = 0
    generic_count = 0
    for r in results:
        rid = r.get("receipt_id")
        if not rid:
            continue
        receipt = db.uploaded_receipts.find_one(
            {"id": rid},
            {"_id": 0, "vendor_routing": 1}
        )
        if receipt and receipt.get("vendor_routing"):
            vr = receipt["vendor_routing"]
            parser = vr.get("selected_parser", "?")
            conf = vr.get("confidence", 0)
            reason = vr.get("routing_reason", "?")[:80]
            if parser == "usfoods_structural":
                structural_count += 1
            else:
                generic_count += 1
            print(f"    {r['file'][:45]:45s} | parser={parser:20s} | conf={conf:.3f}")
        else:
            print(f"    {r['file'][:45]:45s} | NO ROUTING DATA")

    print(f"\n  Routed to structural parser: {structural_count}/{structural_count + generic_count}")
    print(f"  Routed to generic parser:    {generic_count}/{structural_count + generic_count}")

    client.close()

    # Save results
    with open("/tmp/usfoods_retest_results.json", "w") as f:
        json.dump({"results": results, "summary": {
            "success": success, "partial": partial, "failed": failed,
            "skipped": skipped, "false_trusts": total_false,
            "structural_routed": structural_count,
            "generic_routed": generic_count,
        }}, f, indent=2)
    print(f"\n  Results saved: /tmp/usfoods_retest_results.json")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
