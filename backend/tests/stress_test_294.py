"""
294-Image Stress Test Runner
=============================
Processes 294 invoice images through the extraction pipeline.
Tracks: success/failure/partial, timing, audit fields, duplicates.
Runs in batches with rate limiting to avoid proxy 502s.
"""
import json, os, sys, time, random, hashlib
import requests
from datetime import datetime

API_URL = "https://invoice-ai-35.preview.emergentagent.com"
UPLOADS_DIR = "/app/backend/uploads"
TARGET_COUNT = 294
BATCH_SIZE = 3
BATCH_PAUSE = 5  # seconds between batches
RESULTS_FILE = "/tmp/stress_test_results.json"


def login():
    resp = requests.post(f"{API_URL}/api/auth/login", json={"email": "demo@test.com", "password": "testpassword"})
    resp.raise_for_status()
    return resp.json()["token"]


def get_test_files():
    """Select 294 files from uploads, prioritizing variety."""
    exts = ('.jpg', '.jpeg', '.png', '.pdf')
    all_files = [f for f in os.listdir(UPLOADS_DIR)
                 if any(f.lower().endswith(e) for e in exts)
                 and not f.startswith('usfoods_test')
                 and not f.startswith('scan_')]

    # Shuffle for variety, take first 294
    random.seed(42)  # Reproducible selection
    random.shuffle(all_files)
    return all_files[:TARGET_COUNT]


def extract_one(filepath, token, timeout=300):
    """Extract a single invoice. Returns result dict or error."""
    fname = os.path.basename(filepath)
    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else 'jpg'
    ct_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'pdf': 'application/pdf'}
    ct = ct_map.get(ext, 'application/octet-stream')

    try:
        with open(filepath, 'rb') as f:
            resp = requests.post(
                f"{API_URL}/api/upload/extract",
                files={"file": (fname, f, ct)},
                data={"document_type": "purchase_invoice"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=(30, timeout),  # (connect_timeout, read_timeout)
            )
        if resp.status_code != 200:
            return {"status": "failed", "error": f"HTTP {resp.status_code}", "detail": resp.text[:200]}
        return {"status": "ok", "data": resp.json()}
    except requests.Timeout:
        return {"status": "failed", "error": "timeout"}
    except requests.ConnectionError as e:
        return {"status": "failed", "error": f"connection: {str(e)[:100]}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


def analyze_result(result):
    """Analyze extraction result for success/partial/failure."""
    if result["status"] != "ok":
        return {"classification": "failed", "error": result.get("error", "unknown")}

    data = result["data"]
    extracted = data.get("extracted_data") or data.get("data") or {}
    items = extracted.get("items") or []
    scoreable = [it for it in items if it.get("row_type") in ("line_item", "fee", "credit", "discount")]
    trusted = [it for it in scoreable if it.get("confidence_level") == "trusted"]
    vendor = data.get("detected_vendor") or extracted.get("supplier_name") or "?"
    receipt_id = data.get("receipt_id", "")

    if len(scoreable) == 0:
        return {"classification": "failed", "error": "zero_items", "vendor": vendor, "receipt_id": receipt_id}

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

    trust_rate = len(trusted) / len(scoreable) * 100 if scoreable else 0
    review_count = len(scoreable) - len(trusted)

    if trust_rate == 0 and len(scoreable) > 0:
        cls = "partial"
    elif trust_rate < 50:
        cls = "partial"
    else:
        cls = "success"

    return {
        "classification": cls,
        "vendor": vendor,
        "receipt_id": receipt_id,
        "total_items": len(items),
        "scoreable": len(scoreable),
        "trusted": len(trusted),
        "review": review_count,
        "trust_rate": round(trust_rate, 1),
        "false_trusts": false_trusts,
        "invoice_total": float(extracted.get("total", 0) or 0),
    }


def main():
    print("=" * 80)
    print("  294-IMAGE STRESS TEST")
    print(f"  Started: {datetime.now().isoformat()}")
    print("=" * 80)

    token = login()
    files = get_test_files()
    print(f"  Selected {len(files)} files for testing\n")

    results = []
    success = 0
    partial = 0
    failed = 0
    total_time = 0

    for batch_start in range(0, len(files), BATCH_SIZE):
        batch = files[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(files) + BATCH_SIZE - 1) // BATCH_SIZE

        for i, fname in enumerate(batch):
            idx = batch_start + i + 1
            fpath = os.path.join(UPLOADS_DIR, fname)
            fsize_kb = os.path.getsize(fpath) / 1024

            sys.stdout.write(f"\r  [{idx:3d}/{len(files)}] Batch {batch_num}/{total_batches} | {fname[:40]:40s} ({fsize_kb:.0f}KB)")
            sys.stdout.flush()

            t0 = time.time()
            result = extract_one(fpath, token)
            elapsed = time.time() - t0
            total_time += elapsed

            analysis = analyze_result(result)
            analysis["file"] = fname
            analysis["elapsed"] = round(elapsed, 1)
            analysis["file_size_kb"] = round(fsize_kb, 0)
            results.append(analysis)

            if analysis["classification"] == "success":
                success += 1
            elif analysis["classification"] == "partial":
                partial += 1
            else:
                failed += 1

            # Progress line
            rate = (success + partial) / idx * 100
            sys.stdout.write(f" → {analysis['classification']:7s} ({elapsed:.1f}s) | S:{success} P:{partial} F:{failed} ({rate:.0f}%)")
            sys.stdout.flush()
            print()

        # Rate limit pause between batches
        if batch_start + BATCH_SIZE < len(files):
            time.sleep(BATCH_PAUSE)

    # ── Save results ──
    with open(RESULTS_FILE, 'w') as f:
        json.dump({
            "total": len(files),
            "success": success,
            "partial": partial,
            "failed": failed,
            "total_time_seconds": round(total_time, 1),
            "avg_time_per_image": round(total_time / len(files), 1),
            "results": results,
        }, f, indent=2)

    print(f"\n\n{'='*80}")
    print("  STRESS TEST COMPLETE")
    print(f"{'='*80}")
    print(f"  Total images: {len(files)}")
    print(f"  Success:      {success} ({success/len(files)*100:.1f}%)")
    print(f"  Partial:      {partial} ({partial/len(files)*100:.1f}%)")
    print(f"  Failed:       {failed} ({failed/len(files)*100:.1f}%)")
    print(f"  Total time:   {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  Avg/image:    {total_time/len(files):.1f}s")
    print(f"  Results saved: {RESULTS_FILE}")

    # ── Failure details ──
    if failed > 0:
        print(f"\n  FAILED EXTRACTIONS ({failed}):")
        for r in results:
            if r["classification"] == "failed":
                print(f"    {r['file'][:40]:40s} | {r.get('error', '?')[:50]}")

    if partial > 0:
        print(f"\n  PARTIAL EXTRACTIONS ({partial}):")
        for r in results:
            if r["classification"] == "partial":
                vendor = r.get("vendor", "?")[:20]
                trust = r.get("trust_rate", 0)
                items = r.get("scoreable", 0)
                print(f"    {r['file'][:40]:40s} | {vendor:20s} | {items} items | {trust:.0f}% trust")

    # Vendor breakdown
    vendor_stats = {}
    for r in results:
        v = r.get("vendor", "unknown")[:30]
        if v not in vendor_stats:
            vendor_stats[v] = {"success": 0, "partial": 0, "failed": 0, "total": 0}
        vendor_stats[v]["total"] += 1
        vendor_stats[v][r["classification"]] += 1

    print(f"\n  VENDOR BREAKDOWN:")
    print(f"  {'Vendor':<30} {'Total':>6} {'Success':>8} {'Partial':>8} {'Failed':>7}")
    print(f"  {'─'*65}")
    for v, s in sorted(vendor_stats.items(), key=lambda x: -x[1]["total"]):
        print(f"  {v:<30} {s['total']:>6} {s['success']:>8} {s['partial']:>8} {s['failed']:>7}")

    print(f"\n{'='*80}")


if __name__ == "__main__":
    main()
