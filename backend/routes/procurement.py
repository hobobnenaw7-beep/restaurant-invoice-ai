"""
Milestone 5 — Procurement Decision API
=======================================
All endpoints are scoped to the authenticated user's restaurant_id.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from core.auth import get_user
from services.procurement_decisions import (
    recommendations_for_restaurant,
    recommendation_for_product,
    set_target_price,
)

router = APIRouter()


class SetTargetPriceBody(BaseModel):
    target_price_per_unit: Optional[float] = Field(
        default=None,
        description="Target price per canonical_unit. Send null to clear.",
    )
    canonical_unit: Optional[str] = Field(
        default=None,
        description="The canonical_unit this target applies to (e.g. 'lb', 'piece').",
    )


@router.get("/procurement/recommendations")
async def list_recommendations(
    only_actionable: bool = Query(
        default=False,
        description="If true, returns only high-confidence actionable items "
                    "(switch_vendor / renegotiate) — suitable for inline summary panels.",
    ),
    user=Depends(get_user),
):
    items = await recommendations_for_restaurant(
        user["restaurant_id"], only_actionable=only_actionable
    )
    return {
        "items": items,
        "total": len(items),
        "breakdown": {
            "switch_vendor": sum(1 for i in items if i["recommendation_type"] == "switch_vendor"),
            "renegotiate":   sum(1 for i in items if i["recommendation_type"] == "renegotiate"),
            "no_action":     sum(1 for i in items if i["recommendation_type"] == "no_action"),
            "monitor_only":  sum(1 for i in items if i["recommendation_type"] == "monitor_only"),
        },
    }


@router.get("/procurement/recommendations/{canonical_product_id}")
async def get_recommendation(
    canonical_product_id: str,
    canonical_unit: str = Query(default=""),
    user=Depends(get_user),
):
    rec = await recommendation_for_product(
        user["restaurant_id"], canonical_product_id, canonical_unit
    )
    if not rec:
        raise HTTPException(404, "No price observations for this canonical product")
    return rec


@router.patch("/procurement/targets/{canonical_product_id}")
async def patch_target_price(
    canonical_product_id: str,
    body: SetTargetPriceBody,
    user=Depends(get_user),
):
    try:
        result = await set_target_price(
            user["restaurant_id"],
            canonical_product_id,
            target_price_per_unit=body.target_price_per_unit,
            canonical_unit=body.canonical_unit,
        )
    except KeyError:
        raise HTTPException(404, "Canonical product not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
