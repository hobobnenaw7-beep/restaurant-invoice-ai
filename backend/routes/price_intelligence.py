"""
Milestone 4 — Price Intelligence API
=====================================
Unit-safe price history, vendor analytics, alerts, and backfill.
All endpoints are scoped to the authenticated user's restaurant_id.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import get_user
from services.price_intelligence import (
    list_products_summary,
    product_history,
    product_vendor_comparison,
    list_alerts,
    backfill_from_purchases,
)

router = APIRouter()


@router.get("/price-intelligence/products")
async def products_summary(user=Depends(get_user)):
    """
    List every (canonical_product, canonical_unit) bucket the user has data
    for, with stats, trend, alert, and vendor list.
    """
    data = await list_products_summary(user["restaurant_id"])
    return {"items": data, "total": len(data)}


@router.get("/price-intelligence/products/{canonical_product_id}/history")
async def get_product_history(
    canonical_product_id: str,
    canonical_unit: str = Query(default=""),
    user=Depends(get_user),
):
    data = await product_history(user["restaurant_id"], canonical_product_id, canonical_unit)
    if not data["observations"]:
        raise HTTPException(404, "No price observations for this product")
    return data


@router.get("/price-intelligence/products/{canonical_product_id}/vendors")
async def get_product_vendor_comparison(
    canonical_product_id: str,
    canonical_unit: str = Query(default=""),
    user=Depends(get_user),
):
    data = await product_vendor_comparison(user["restaurant_id"], canonical_product_id, canonical_unit)
    if not data["vendors"]:
        raise HTTPException(404, "No vendor data for this product")
    return data


@router.get("/price-intelligence/alerts")
async def get_price_alerts(user=Depends(get_user)):
    alerts = await list_alerts(user["restaurant_id"])
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/price-intelligence/backfill")
async def backfill(user=Depends(get_user)):
    """
    One-time scan of existing purchases → ingest eligible observations into
    price_history. Idempotent (existing observations for the same purchase
    are replaced).
    """
    result = await backfill_from_purchases(user["restaurant_id"])
    return result
