"""
Phase 1 Sysco Pipeline Stress Test.
Runs 15 diverse Sysco invoices through the full deterministic pipeline.
Outputs detailed per-invoice breakdown + failure pattern summary.
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
from services.sysco_pipeline import run_sysco_pipeline, _extract_words, _segment_rows

# 15 confirmed Sysco invoice files (diverse set)
PHASE1_FILES = [
    "296c4a30-127b-4252-ae72-84f5dfb75212.jpg",
    "bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg",
    "cc7dc90b-f682-4d5d-91fc-36de6439c60b.jpg",
    "e76577bc-bc4c-45ce-a99a-db566eef0393.jpg",
    "receipt_20ea1a7e-762c-4e82-8c1d-bbdae92594d1.jpg",
    "receipt_333073da-edec-481e-9f49-f5b8199a15c3.jpg",
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
REPORT_PATH = "/app/backend/tests/phase1_stress_report.json"


def run_phase1():
    print("=" * 70)
    print("PHASE 1: SYSCO PIPELINE STRESS TEST (15 invoices)")
    print("=" * 70)

    results = []

    for idx, fname in enumerate(PHASE1_FILES):
        fpath = os.path.join(UPLOADS_DIR, fname)
        short = fname[:20] + "..."
        print(f"\n{'─'*70}")
        print(f"[{idx+1}/{len(PHASE1_FILES)}] {fname}")

        if not os.path.exists(fpath):
            print(f"  FILE NOT FOUND — skipping")
            results.append({"file": fname, "error": "FILE_NOT_FOUND"})
            continue

        try:
            fsize_kb = os.path.getsize(fpath) // 1024

            # Step 1: Preprocess (scan mode + orientation fix)
            with open(fpath, "rb") as f:
                raw = f.read()

            t0 = time.time()
            processed = preprocess_image(raw)
            preprocess_time = time.time() - t0

            img = Image.open(io.BytesIO(processed))
            if img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size

            print(f"  Image: {w}x{h} | {fsize_kb}KB | preprocess: {preprocess_time:.1f}s")

            # Step 2: Run pipeline
            b64 = base64.b64encode(processed).decode()
            t1 = time.time()
            result = run_sysco_pipeline(b64)
            pipeline_time = time.time() - t1

            meta = result["pipeline_meta"]
            items = result["items"]
            excluded = result["excluded_rows"]
            subtotal = result["subtotal_validation"]

            # Classify results
            trusted = [it for it in items if it["confidence_level"] == "trusted"]
            review = [it for it in items if "review" in it.get("confidence_level", "")]

            # Row classification breakdown from excluded + items
            row_types = {}
            for ex in excluded:
                rt = ex.get("row_type", "unknown")
                row_types[rt] = row_types.get(rt, 0) + 1
            for it in items:
                rt = it.get("row_type", "line_item")
                row_types[rt] = row_types.get(rt, 0) + 1

            entry = {
                "file": fname,
                "image_size": f"{w}x{h}",
                "file_size_kb": fsize_kb,
                "preprocess_time_sec": round(preprocess_time, 2),
                "pipeline_time_sec": round(pipeline_time, 2),
                "total_time_sec": round(preprocess_time + pipeline_time, 2),
                "ocr_words": meta.get("ocr_words", 0),
                "rows_segmented": meta.get("rows_segmented", 0),
                "columns_detected": meta.get("columns_detected", []),
                "header_row_idx": meta.get("header_row_idx", -1),
                "row_type_breakdown": row_types,
                "extracted_line_items": len(items),
                "trusted_count": len(trusted),
                "review_count": len(review),
                "excluded_count": len(excluded),
                "subtotal_match": subtotal.get("subtotal_match", False),
                "subtotal_items_sum": subtotal.get("items_sum", 0),
                "subtotal_declared": subtotal.get("declared_subtotal", 0),
                "subtotal_diff_pct": subtotal.get("subtotal_diff_pct", 0),
                "trusted_items_detail": [],
                "review_items_detail": [],
                "failure_categories": {},
                "column_alignment_issues": [],
                "row_classification_issues": [],
            }

            # ─── Trusted items detail (for false-positive checking) ───
            print(f"  Pipeline: {pipeline_time:.1f}s | OCR: {meta.get('ocr_words',0)} words | {meta.get('rows_segmented',0)} rows")
            print(f"  Columns: {meta.get('columns_detected', [])}")
            print(f"  Items: {len(items)} total | {len(trusted)} trusted | {len(review)} review")
            print(f"  Subtotal: items_sum=${subtotal.get('items_sum',0):.2f} vs declared=${subtotal.get('declared_subtotal',0):.2f} | match={subtotal.get('subtotal_match',False)}")

            if trusted:
                print(f"\n  TRUSTED ITEMS ({len(trusted)}):")
            for it in trusted:
                qty = it["quantity"]
                price = it["unit_price"]
                total = it["total"]
                calc = round(qty * price, 2)
                math_ok = it.get("valid_calc", False)
                name = (it.get("raw_name", "") or "")[:45]

                # Check for potential false trust
                false_flags = []
                if abs(calc - total) > 0.50:
                    false_flags.append(f"MATH_FAIL: {qty}*{price}={calc} != {total}")
                if qty == 0 or price == 0 or total == 0:
                    false_flags.append(f"ZERO_VALUE: qty={qty} price={price} total={total}")
                if qty > 100:
                    false_flags.append(f"HIGH_QTY: {qty}")
                if price > 2000:
                    false_flags.append(f"HIGH_PRICE: {price}")

                detail = {
                    "name": name,
                    "qty": qty,
                    "price": price,
                    "total": total,
                    "calculated": calc,
                    "math_ok": math_ok,
                    "false_trust_flags": false_flags,
                }
                entry["trusted_items_detail"].append(detail)

                flag_str = f" *** {', '.join(false_flags)} ***" if false_flags else ""
                print(f"    [T] {name:<45} qty={qty:<6} price=${price:<8} total=${total:<10} calc=${calc}{flag_str}")

            # ─── Review items detail ───
            if review:
                print(f"\n  REVIEW ITEMS ({len(review)}):")
            for it in review:
                cat = it.get("numeric_failure_category", "unknown")
                entry["failure_categories"][cat] = entry["failure_categories"].get(cat, 0) + 1

                name = (it.get("raw_name", "") or "")[:45]
                qty = it["quantity"]
                price = it["unit_price"]
                total = it["total"]
                reason = (it.get("review_reason", "") or "")[:80]

                detail = {
                    "name": name,
                    "qty": qty,
                    "price": price,
                    "total": total,
                    "category": cat,
                    "reason": reason,
                    "qty_source": it.get("qty_source", "?"),
                    "price_source": it.get("price_source", "?"),
                    "total_source": it.get("total_source", "?"),
                }
                entry["review_items_detail"].append(detail)

                print(f"    [R] {name:<45} qty={qty:<6} price=${price:<8} total=${total:<10} cat={cat} | {reason[:60]}")

            # ─── Column alignment issues ───
            cols = meta.get("columns_detected", [])
            if "qty" not in cols:
                entry["column_alignment_issues"].append("MISSING_QTY_COLUMN")
            if "unit_price" not in cols:
                entry["column_alignment_issues"].append("MISSING_PRICE_COLUMN")
            if "total" not in cols:
                entry["column_alignment_issues"].append("MISSING_TOTAL_COLUMN")
            if "description" not in cols:
                entry["column_alignment_issues"].append("MISSING_DESCRIPTION_COLUMN")
            if entry["column_alignment_issues"]:
                print(f"\n  COLUMN ISSUES: {entry['column_alignment_issues']}")

            # ─── Row classification issues ───
            if entry["extracted_line_items"] == 0 and entry["ocr_words"] > 50:
                entry["row_classification_issues"].append("ZERO_LINE_ITEMS_DESPITE_OCR")
            if entry["extracted_line_items"] > 50:
                entry["row_classification_issues"].append(f"SUSPICIOUSLY_HIGH_ITEMS: {entry['extracted_line_items']}")
            if entry["row_classification_issues"]:
                print(f"  ROW ISSUES: {entry['row_classification_issues']}")

            results.append(entry)

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "file": fname,
                "error": str(e),
                "traceback": traceback.format_exc()[:500],
            })

    # ═══════════════════════════════════════════════════════════════════
    # AGGREGATE SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n\n{'═'*70}")
    print(f"PHASE 1 SUMMARY")
    print(f"{'═'*70}")

    successful = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    print(f"Invoices processed: {len(successful)}/{len(PHASE1_FILES)}")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  {e['file']}: {e.get('error','?')}")

    if not successful:
        print("No successful results to analyze.")
        return

    total_items = sum(r["extracted_line_items"] for r in successful)
    total_trusted = sum(r["trusted_count"] for r in successful)
    total_review = sum(r["review_count"] for r in successful)

    print(f"\nTotal line items extracted: {total_items}")
    print(f"Total trusted: {total_trusted}")
    print(f"Total review: {total_review}")
    if total_items > 0:
        print(f"Trust rate: {total_trusted}/{total_items} = {total_trusted/total_items:.0%}")

    # False trust check
    total_false_trusts = 0
    for r in successful:
        for t in r.get("trusted_items_detail", []):
            if t.get("false_trust_flags"):
                total_false_trusts += 1
                print(f"\n  *** FALSE TRUST: {r['file']}")
                print(f"      Item: {t['name']}")
                print(f"      Flags: {t['false_trust_flags']}")

    print(f"\nFalse trusted items: {total_false_trusts}")
    if total_false_trusts == 0:
        print("  ZERO FALSE TRUSTS — trust gate is holding!")

    # Failure category breakdown
    all_cats = {}
    for r in successful:
        for cat, count in r.get("failure_categories", {}).items():
            all_cats[cat] = all_cats.get(cat, 0) + count

    print(f"\nFailure category breakdown:")
    for cat, count in sorted(all_cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Column detection stability
    col_sets = {}
    for r in successful:
        key = ", ".join(sorted(r.get("columns_detected", [])))
        col_sets[key] = col_sets.get(key, 0) + 1
    print(f"\nColumn detection stability:")
    for cols, count in sorted(col_sets.items(), key=lambda x: -x[1]):
        print(f"  [{cols}]: {count} invoices")

    # Column alignment issues
    all_col_issues = {}
    for r in successful:
        for issue in r.get("column_alignment_issues", []):
            all_col_issues[issue] = all_col_issues.get(issue, 0) + 1
    if all_col_issues:
        print(f"\nColumn alignment issues:")
        for issue, count in sorted(all_col_issues.items(), key=lambda x: -x[1]):
            print(f"  {issue}: {count} invoices")

    # Row classification issues
    all_row_issues = {}
    for r in successful:
        for issue in r.get("row_classification_issues", []):
            all_row_issues[issue] = all_row_issues.get(issue, 0) + 1
    if all_row_issues:
        print(f"\nRow classification issues:")
        for issue, count in sorted(all_row_issues.items(), key=lambda x: -x[1]):
            print(f"  {issue}: {count} invoices")

    # Subtotal match rate
    sub_match = sum(1 for r in successful if r.get("subtotal_match"))
    print(f"\nSubtotal match: {sub_match}/{len(successful)} invoices")

    # Per-invoice summary table
    print(f"\n{'─'*100}")
    print(f"{'File':<25} {'Size':>6} {'OCR':>5} {'Rows':>5} {'Items':>6} {'Trust':>6} {'Revw':>5} {'SubM':>5} {'Time':>6}")
    print(f"{'─'*100}")
    for r in successful:
        f = r["file"][:24]
        print(f"{f:<25} {r['file_size_kb']:>5}K {r['ocr_words']:>5} {r['rows_segmented']:>5} {r['extracted_line_items']:>6} {r['trusted_count']:>6} {r['review_count']:>5} {'Y' if r.get('subtotal_match') else 'N':>5} {r['total_time_sec']:>5.1f}s")

    # Timing stats
    times = [r["total_time_sec"] for r in successful]
    print(f"\nTiming: avg={sum(times)/len(times):.1f}s | min={min(times):.1f}s | max={max(times):.1f}s")

    # Save report
    report = {
        "phase": "phase1",
        "total_files": len(PHASE1_FILES),
        "successful": len(successful),
        "errors": len(errors),
        "summary": {
            "total_items": total_items,
            "total_trusted": total_trusted,
            "total_review": total_review,
            "trust_rate": round(total_trusted / total_items, 3) if total_items > 0 else 0,
            "false_trusted": total_false_trusts,
            "subtotal_match_count": sub_match,
            "failure_categories": all_cats,
            "column_issues": all_col_issues,
            "row_issues": all_row_issues,
        },
        "invoices": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    run_phase1()
