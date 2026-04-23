"""
Invoice Item Identity Actions (Milestone 19)
=============================================

Explicit, user-controlled actions on a single line item inside a purchase.

Endpoints (all tenant-scoped, audit-logged):
  POST /api/purchases/{pid}/items/{idx}/link      { canonical_item_id, variant_key? }
  POST /api/purchases/{pid}/items/{idx}/promote   { name, category?, unit?, variants? }
  POST /api/purchases/{pid}/items/{idx}/match     — re-run matcher, return MatchResult
  GET  /api/purchases/{pid}/items/{idx}/match-preview - same as above, no mutation

Guardrails:
  • Editing invoice text NEVER mutates canonical items.
  • Explicit actions only attach / promote / relink — user stays in control.
  • Creates an alias row on link so future parses learn from this decision.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.auth import get_user
from services.audit import audit_log
from services.item_matcher import match_item

router = APIRouter()


class LinkBody(BaseModel):
    canonical_item_id: str
    variant_key: Optional[str] = None


class VariantIn(BaseModel):
    key: str
    label: Optional[str] = ""


class PromoteBody(BaseModel):
    name: str
    category: Optional[str] = ""
    unit: Optional[str] = ""
    storage_category: Optional[str] = ""
    variants: Optional[List[VariantIn]] = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_purchase_item(pid: str, idx: int, rid: str) -> tuple[dict, dict]:
    purchase = await db.purchases.find_one({"id": pid, "restaurant_id": rid}, {"_id": 0})
    if not purchase:
        raise HTTPException(404, "purchase_not_found")
    items = purchase.get("items") or []
    if idx < 0 or idx >= len(items):
        raise HTTPException(404, "item_index_out_of_range")
    return purchase, items[idx]


async def _upsert_alias(*, rid: str, canonical_item_id: str, alias_text: str,
                        user_id: Optional[str]) -> None:
    alias_text = (alias_text or "").strip()
    if not alias_text:
        return
    existing = await db.item_aliases.find_one(
        {"restaurant_id": rid, "canonical_item_id": canonical_item_id,
         "alias": alias_text}, {"_id": 0},
    )
    now = _utcnow()
    if existing:
        await db.item_aliases.update_one(
            {"id": existing["id"]},
            {"$set": {"last_used_at": now}, "$inc": {"usage_count": 1}},
        )
        return
    await db.item_aliases.insert_one({
        "id": str(uuid.uuid4()),
        "restaurant_id": rid,
        "canonical_item_id": canonical_item_id,
        "alias": alias_text,
        "source": "invoice_item_link",
        "created_by_user_id": user_id,
        "created_at": now,
        "last_used_at": now,
        "usage_count": 1,
    })


@router.post("/purchases/{pid}/items/{idx}/link")
async def link_invoice_item(pid: str, idx: int, body: LinkBody, user=Depends(get_user)):
    rid = user["restaurant_id"]
    purchase, item = await _get_purchase_item(pid, idx, rid)

    target = await db.canonical_items.find_one(
        {"id": body.canonical_item_id, "restaurant_id": rid}, {"_id": 0},
    )
    if not target:
        raise HTTPException(404, "canonical_item_not_found")
    if target.get("is_archived"):
        raise HTTPException(400, "canonical_item_archived")

    variant_key = (body.variant_key or "").strip() or None
    if variant_key:
        declared = {(v.get("key") or "").strip() for v in (target.get("variants") or [])}
        if variant_key not in declared:
            raise HTTPException(400, "variant_not_declared_on_canonical")

    items = purchase.get("items") or []
    raw_name = (item.get("raw_name") or item.get("name") or "").strip()
    items[idx] = {
        **item,
        "canonical_item_id": target["id"],
        "variant_key": variant_key,
        "link_confidence": "high",
        "link_source": "manual",
        "linked_at": _utcnow(),
        "linked_by_user_id": user.get("id"),
    }
    await db.purchases.update_one({"id": pid, "restaurant_id": rid}, {"$set": {"items": items}})

    # Learn the alias so future identical raw names auto-link.
    await _upsert_alias(rid=rid, canonical_item_id=target["id"], alias_text=raw_name,
                        user_id=user.get("id"))

    await audit_log(
        user, "LINK_INVOICE_ITEM", "Purchase", pid,
        f'{user["name"]} linked "{raw_name}" → {target.get("name")}'
        + (f' ({variant_key})' if variant_key else ""),
        new_value={"canonical_item_id": target["id"], "variant_key": variant_key,
                   "raw_name": raw_name},
    )

    return {
        "status": "linked",
        "canonical_item_id": target["id"],
        "canonical_name": target.get("name"),
        "variant_key": variant_key,
    }


@router.post("/purchases/{pid}/items/{idx}/promote")
async def promote_invoice_item(pid: str, idx: int, body: PromoteBody, user=Depends(get_user)):
    rid = user["restaurant_id"]
    purchase, item = await _get_purchase_item(pid, idx, rid)

    name = (body.name or "").strip() or (item.get("raw_name") or "").strip()
    if not name:
        raise HTTPException(400, "missing_name")

    now = _utcnow()
    new_id = str(uuid.uuid4())
    variants = []
    for v in (body.variants or []):
        key = (v.key or "").strip().lower()
        label = (v.label or key).strip()
        if key and all(v2["key"] != key for v2 in variants):
            variants.append({"key": key, "label": label})
    doc = {
        "id": new_id,
        "restaurant_id": rid,
        "name": name,
        "category": (body.category or "").strip(),
        "unit": (body.unit or "").strip(),
        "storage_category": (body.storage_category or "").strip(),
        "variants": variants,
        "is_suggested": False,  # explicit promote = approved immediately
        "promoted_from": "invoice_item",
        "promoted_from_purchase_id": pid,
        "created_at": now,
        "promoted_at": now,
        "promoted_by_user_id": user.get("id"),
        "promoted_by_name": user.get("name", ""),
    }
    await db.canonical_items.insert_one(doc)

    items = purchase.get("items") or []
    raw_name = (item.get("raw_name") or item.get("name") or "").strip()
    items[idx] = {
        **item,
        "canonical_item_id": new_id,
        "variant_key": None,
        "link_confidence": "high",
        "link_source": "promoted",
        "linked_at": now,
    }
    await db.purchases.update_one({"id": pid, "restaurant_id": rid}, {"$set": {"items": items}})
    await _upsert_alias(rid=rid, canonical_item_id=new_id, alias_text=raw_name,
                        user_id=user.get("id"))

    await audit_log(
        user, "PROMOTE_INVOICE_ITEM", "Item", new_id,
        f'{user["name"]} promoted "{raw_name}" as new item "{name}"',
        new_value={"name": name, "variants": variants, "canonical_item_id": new_id},
    )

    doc.pop("_id", None)
    return {"status": "promoted", "canonical_item": doc}


async def _run_match_for_item(rid: str, item: dict) -> dict:
    raw = (item.get("raw_name") or item.get("name") or "").strip()
    if not raw:
        return {"canonical_item_id": None, "variant_key": None,
                "confidence": "low", "tier": "empty",
                "token_score": 0.0, "fuzzy_score": 0.0,
                "candidates": [], "needs_review": False, "auto_linked": False}

    canonicals = await db.canonical_items.find(
        {"restaurant_id": rid}, {"_id": 0},
    ).to_list(5000)
    aliases = await db.item_aliases.find(
        {"restaurant_id": rid, "is_archived": {"$ne": True}},
        {"_id": 0, "alias": 1, "alias_name": 1, "canonical_item_id": 1},
    ).to_list(5000)
    memory = await db.correction_memory.find(
        {"restaurant_id": rid, "enabled": {"$ne": False}},
        {"_id": 0, "original_raw_name": 1, "corrected_name": 1},
    ).to_list(5000)

    res = match_item(raw, canonical_items=canonicals, aliases=aliases,
                     correction_memory=memory)
    return res.to_dict()


@router.get("/purchases/{pid}/items/{idx}/match-preview")
async def match_preview_invoice_item(pid: str, idx: int, user=Depends(get_user)):
    rid = user["restaurant_id"]
    _, item = await _get_purchase_item(pid, idx, rid)
    return await _run_match_for_item(rid, item)


@router.post("/purchases/{pid}/items/{idx}/match")
async def match_invoice_item(pid: str, idx: int, user=Depends(get_user)):
    """
    Re-run the matcher. Auto-links ONLY when confidence=='high' and the
    matcher returned auto_linked=True (all guardrails satisfied).
    Otherwise returns the preview without mutating the item.
    """
    rid = user["restaurant_id"]
    purchase, item = await _get_purchase_item(pid, idx, rid)
    result = await _run_match_for_item(rid, item)

    if result.get("auto_linked") and result.get("canonical_item_id"):
        items = purchase.get("items") or []
        items[idx] = {
            **item,
            "canonical_item_id": result["canonical_item_id"],
            "variant_key": result.get("variant_key"),
            "link_confidence": "high",
            "link_source": "matcher_auto",
            "linked_at": _utcnow(),
        }
        await db.purchases.update_one(
            {"id": pid, "restaurant_id": rid}, {"$set": {"items": items}},
        )
        await audit_log(
            user, "AUTOLINK_INVOICE_ITEM", "Purchase", pid,
            f'{user["name"]} auto-linked "{item.get("raw_name")}" → '
            f'{result.get("canonical_name")}',
            new_value={"canonical_item_id": result["canonical_item_id"],
                       "variant_key": result.get("variant_key"),
                       "tier": result.get("tier"),
                       "token_score": result.get("token_score"),
                       "fuzzy_score": result.get("fuzzy_score")},
        )
    return result
