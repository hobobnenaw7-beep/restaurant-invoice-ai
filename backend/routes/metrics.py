from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from core.database import db
from routes.auth import get_user

router = APIRouter()


@router.post("/metrics/review-session")
async def log_review_session(data: dict, user=Depends(get_user)):
    """Log a single invoice review session. Lightweight — 3 metrics only."""
    await db.review_metrics.insert_one({
        "purchase_id": data.get("purchase_id"),
        "supplier_name": data.get("supplier_name", ""),
        "time_spent_seconds": round(float(data.get("time_spent_seconds", 0)), 1),
        "edits_count": int(data.get("edits_count", 0)),
        "flagged_rows_count": int(data.get("flagged_rows_count", 0)),
        "total_rows": int(data.get("total_rows", 0)),
        "user_id": user["id"],
        "restaurant_id": user["restaurant_id"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "recorded"}


@router.get("/metrics/review-sessions")
async def get_review_sessions(user=Depends(get_user)):
    """Retrieve all review session metrics for analysis."""
    sessions = await db.review_metrics.find(
        {"restaurant_id": user["restaurant_id"]}, {"_id": 0}
    ).sort("recorded_at", -1).to_list(500)
    return sessions
