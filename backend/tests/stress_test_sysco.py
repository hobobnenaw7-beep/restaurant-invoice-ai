"""
Sysco Pipeline Stress Test.
Runs all uploaded images through the pipeline and logs results.
Identifies Sysco invoices via OCR content (looks for "SYSCO" in text).
"""
import base64
import io
import json
import os
import sys
import time
import traceback

sys.path.insert(0, "/app/backend")

from PIL import Image
from preprocessing import preprocess_image
from services.sysco_pipeline import run_sysco_pipeline, _extract_words

UPLOADS_DIR = "/app/backend/uploads"
REPORT_PATH = "/app/backend/tests/stress_test_report.json"

def is_sysco_invoice(img: Image.Image) -> bool:
    """Quick check: does the OCR text contain 'SYSCO'?"""
    try:
        words = _extract_words(img)
        text = " ".join(w["text"].upper() for w in words[:100])
        return "SYSCO" in text
    except:
        return False

def run_stress_test():
    # Get all image files (skip scan artifacts)
    files = []
    for f in sorted(os.listdir(UPLOADS_DIR)):
        if f.startswith("scan_"):
            continue
        if f.endswith((".jpg", ".png")):
            files.append(f)

    print(f"Total image files: {len(files)}")

    results = []
    sysco_count = 0

    for idx, fname in enumerate(files):
        fpath = os.path.join(UPLOADS_DIR, fname)
        print(f"[{idx+1}/{len(files)}] Processing {fname}...", end=" ", flush=True)

        try:
            with open(fpath, "rb") as f:
                raw = f.read()

            # Preprocess
            processed = preprocess_image(raw)
            img = Image.open(io.BytesIO(processed))

            # Check if Sysco
            if not is_sysco_invoice(img):
                print("SKIP (not Sysco)")
                continue

            sysco_count += 1
            b64 = base64.b64encode(processed).decode()

            # Run pipeline
            t0 = time.time()
            result = run_sysco_pipeline(b64)
            elapsed = time.time() - t0

            meta = result["pipeline_meta"]
            items = result["items"]
            excluded = result["excluded_rows"]

            trusted = [it for it in items if it["confidence_level"] == "trusted"]
            review = [it for it in items if "review" in it.get("confidence_level", "")]

            entry = {
                "file": fname,
                "image_size": f"{img.size[0]}x{img.size[1]}",
                "time_sec": round(elapsed, 2),
                "ocr_words": meta.get("ocr_words", 0),
                "rows_segmented": meta.get("rows_segmented", 0),
                "columns_detected": meta.get("columns_detected", []),
                "total_items": len(items),
                "trusted_count": len(trusted),
                "review_count": len(review),
                "excluded_count": len(excluded),
                "subtotal_match": meta.get("subtotal_match", False),
                "trusted_items": [],
                "review_items": [],
                "failure_patterns": [],
            }

            # Log trusted items (for false-positive checking)
            for it in trusted:
                entry["trusted_items"].append({
                    "name": it["raw_name"][:50],
                    "qty": it["quantity"],
                    "price": it["unit_price"],
                    "total": it["total"],
                    "math": f"{it['quantity']}*{it['unit_price']}={round(it['quantity']*it['unit_price'],2)}",
                    "actual_total": it["total"],
                    "math_match": it.get("valid_calc", False),
                })

            # Log review items with failure categories
            for it in review:
                entry["review_items"].append({
                    "name": it["raw_name"][:50],
                    "qty": it["quantity"],
                    "price": it["unit_price"],
                    "total": it["total"],
                    "category": it.get("numeric_failure_category", "unknown"),
                    "reason": it.get("review_reason", "")[:100],
                    "qty_source": it.get("qty_source", "?"),
                    "price_source": it.get("price_source", "?"),
                    "total_source": it.get("total_source", "?"),
                })

            # Identify failure patterns
            categories = {}
            for it in review:
                cat = it.get("numeric_failure_category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1
            entry["failure_patterns"] = categories

            results.append(entry)
            print(f"Sysco #{sysco_count}: {len(items)} items, {len(trusted)} trusted, {len(review)} review ({elapsed:.1f}s)")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "file": fname,
                "error": str(e),
                "traceback": traceback.format_exc()[:500],
            })

    # Summary
    print("\n" + "="*70)
    print(f"STRESS TEST SUMMARY")
    print(f"="*70)
    print(f"Total files scanned: {len(files)}")
    print(f"Sysco invoices found: {sysco_count}")
    print(f"Successfully processed: {len([r for r in results if 'error' not in r])}")
    print(f"Errors: {len([r for r in results if 'error' in r])}")

    if results:
        successful = [r for r in results if "error" not in r]
        total_items = sum(r["total_items"] for r in successful)
        total_trusted = sum(r["trusted_count"] for r in successful)
        total_review = sum(r["review_count"] for r in successful)

        print(f"\nTotal line items extracted: {total_items}")
        print(f"Total trusted: {total_trusted}")
        print(f"Total review: {total_review}")
        if total_items > 0:
            print(f"Trust rate: {total_trusted/total_items:.0%}")

        # Aggregate failure patterns
        all_patterns = {}
        for r in successful:
            for cat, count in r.get("failure_patterns", {}).items():
                all_patterns[cat] = all_patterns.get(cat, 0) + count

        print(f"\nFailure pattern breakdown:")
        for cat, count in sorted(all_patterns.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

        # Column stability
        col_sets = {}
        for r in successful:
            key = ",".join(sorted(r.get("columns_detected", [])))
            col_sets[key] = col_sets.get(key, 0) + 1
        print(f"\nColumn detection stability:")
        for cols, count in sorted(col_sets.items(), key=lambda x: -x[1]):
            print(f"  [{cols}]: {count} invoices")

    # Save report
    report = {
        "summary": {
            "total_files": len(files),
            "sysco_invoices": sysco_count,
            "total_items": sum(r.get("total_items", 0) for r in results if "error" not in r),
            "total_trusted": sum(r.get("trusted_count", 0) for r in results if "error" not in r),
            "total_review": sum(r.get("review_count", 0) for r in results if "error" not in r),
        },
        "invoices": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {REPORT_PATH}")


if __name__ == "__main__":
    run_stress_test()
