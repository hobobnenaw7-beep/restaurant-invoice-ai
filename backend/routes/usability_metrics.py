"""
Usability Metrics — Silent Collection

Tracks 4 dimensions per invoice for real-world testing analysis:
1. Time saved — upload-to-save duration vs configurable manual baseline
2. Review burden — trusted vs needs_review vs manually corrected counts
3. Error detection value — system-flagged items: confirmed vs overridden
4. User friction — edits count, fields corrected, review time

All collection is silent — no user-facing UI.
Baseline is configurable (default 5 min per invoice).
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from core.database import db
from routes.auth import get_user

router = APIRouter()

# Configurable manual baseline (seconds per invoice)
MANUAL_BASELINE_SECONDS = 300  # 5 minutes


@router.post("/metrics/invoice-lifecycle")
async def log_invoice_lifecycle(data: dict, user=Depends(get_user)):
    """
    Log full invoice lifecycle metrics at save time.
    Called silently by frontend after successful save.

    Expected payload:
    {
      "purchase_id": "uuid",
      "supplier_name": "Sysco",
      "vendor_status": "operational" | "limited" | "unknown",

      # Timing (milliseconds from frontend)
      "upload_start_ms": 1234567890,
      "extraction_complete_ms": 1234567890,
      "review_open_ms": 1234567890 | null,
      "review_close_ms": 1234567890 | null,
      "save_ms": 1234567890,

      # Item counts
      "total_items": 10,
      "trusted_items": 7,
      "needs_review_items": 3,
      "manually_edited_items": 1,

      # Error detection
      "system_flagged_count": 3,
      "user_confirmed_flags": 2,     # user edited flagged items (true positive)
      "user_overrode_flags": 1,      # user saved without editing flagged items (false positive or accepted)

      # Fields corrected
      "fields_corrected": ["quantity", "unit_price"],
      "edits_count": 2,

      # Input metadata
      "input_format": "pdf" | "jpg" | "png" | "xlsx",
      "page_count": 1,
      "document_type": "purchase_invoice"
    }
    """
    now = datetime.now(timezone.utc).isoformat()

    # Compute derived metrics
    upload_start = data.get("upload_start_ms", 0)
    save_ms = data.get("save_ms", 0)
    extraction_ms = data.get("extraction_complete_ms", 0)
    review_open = data.get("review_open_ms")
    review_close = data.get("review_close_ms")

    # Total wall-clock time (upload start → save)
    total_seconds = round((save_ms - upload_start) / 1000, 1) if save_ms and upload_start else 0

    # Extraction time (upload start → extraction complete)
    extraction_seconds = round((extraction_ms - upload_start) / 1000, 1) if extraction_ms and upload_start else 0

    # Review time (review dialog open → close)
    review_seconds = round((review_close - review_open) / 1000, 1) if review_open and review_close else 0

    # Time saved vs manual baseline
    time_saved_seconds = round(MANUAL_BASELINE_SECONDS - total_seconds, 1) if total_seconds > 0 else 0
    time_saved_pct = round((time_saved_seconds / MANUAL_BASELINE_SECONDS) * 100, 1) if MANUAL_BASELINE_SECONDS > 0 else 0

    # Review burden
    total_items = int(data.get("total_items", 0))
    trusted = int(data.get("trusted_items", 0))
    needs_review = int(data.get("needs_review_items", 0))
    edited = int(data.get("manually_edited_items", 0))
    auto_accept_rate = round((trusted / total_items) * 100, 1) if total_items > 0 else 0

    # Error detection
    flagged = int(data.get("system_flagged_count", 0))
    confirmed = int(data.get("user_confirmed_flags", 0))
    overrode = int(data.get("user_overrode_flags", 0))
    detection_precision = round((confirmed / flagged) * 100, 1) if flagged > 0 else 0

    metric = {
        "purchase_id": data.get("purchase_id"),
        "supplier_name": data.get("supplier_name", ""),
        "vendor_status": data.get("vendor_status", "unknown"),
        "user_id": user["id"],
        "restaurant_id": user["restaurant_id"],
        "recorded_at": now,

        # Dimension 1: Time saved
        "total_seconds": total_seconds,
        "extraction_seconds": extraction_seconds,
        "review_seconds": review_seconds,
        "manual_baseline_seconds": MANUAL_BASELINE_SECONDS,
        "time_saved_seconds": time_saved_seconds,
        "time_saved_pct": time_saved_pct,

        # Dimension 2: Review burden
        "total_items": total_items,
        "trusted_items": trusted,
        "needs_review_items": needs_review,
        "manually_edited_items": edited,
        "auto_accept_rate": auto_accept_rate,

        # Dimension 3: Error detection value
        "system_flagged_count": flagged,
        "user_confirmed_flags": confirmed,
        "user_overrode_flags": overrode,
        "detection_precision": detection_precision,

        # Dimension 4: User friction
        "edits_count": int(data.get("edits_count", 0)),
        "fields_corrected": data.get("fields_corrected", []),

        # Input metadata
        "input_format": data.get("input_format", "unknown"),
        "page_count": int(data.get("page_count", 1)),
        "document_type": data.get("document_type", "purchase_invoice"),
    }

    await db.invoice_metrics.insert_one(metric)
    return {"status": "recorded"}


@router.get("/metrics/invoice-summary")
async def get_invoice_metrics_summary(user=Depends(get_user)):
    """
    Aggregated metrics summary for internal analysis.
    Returns per-vendor and overall statistics.
    """
    metrics = await db.invoice_metrics.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).sort("recorded_at", -1).to_list(1000)

    if not metrics:
        return {"total_invoices": 0, "vendors": {}, "overall": {}}

    # Aggregate by vendor
    vendors = {}
    for m in metrics:
        v = m.get("supplier_name", "Unknown")
        vendors.setdefault(v, []).append(m)

    vendor_stats = {}
    for v, ms in vendors.items():
        count = len(ms)
        avg_time = round(sum(m.get("total_seconds", 0) for m in ms) / count, 1)
        avg_saved = round(sum(m.get("time_saved_seconds", 0) for m in ms) / count, 1)
        avg_accept = round(sum(m.get("auto_accept_rate", 0) for m in ms) / count, 1)
        avg_edits = round(sum(m.get("edits_count", 0) for m in ms) / count, 1)
        total_flagged = sum(m.get("system_flagged_count", 0) for m in ms)
        total_confirmed = sum(m.get("user_confirmed_flags", 0) for m in ms)
        precision = round((total_confirmed / total_flagged) * 100, 1) if total_flagged > 0 else 0

        vendor_stats[v] = {
            "invoice_count": count,
            "avg_total_seconds": avg_time,
            "avg_time_saved_seconds": avg_saved,
            "avg_auto_accept_rate": avg_accept,
            "avg_edits_per_invoice": avg_edits,
            "detection_precision": precision,
            "vendor_status": ms[-1].get("vendor_status", "unknown"),
        }

    # Overall
    total = len(metrics)
    overall = {
        "avg_total_seconds": round(sum(m.get("total_seconds", 0) for m in metrics) / total, 1),
        "avg_time_saved_seconds": round(sum(m.get("time_saved_seconds", 0) for m in metrics) / total, 1),
        "avg_auto_accept_rate": round(sum(m.get("auto_accept_rate", 0) for m in metrics) / total, 1),
        "avg_edits_per_invoice": round(sum(m.get("edits_count", 0) for m in metrics) / total, 1),
    }

    return {
        "total_invoices": total,
        "vendors": vendor_stats,
        "overall": overall,
        "manual_baseline_seconds": MANUAL_BASELINE_SECONDS,
    }
