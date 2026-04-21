"""
Milestone 4 — Price Intelligence & Market Benchmarking
=======================================================

Tracks unit-safe price observations per (canonical_product_id, canonical_unit)
and computes Vendor Analytics (min / max / avg / latest / trend) and
confidence-based Price Increase Alerts.

Hard rules
----------
- An observation is ingested ONLY when ALL of these are true:
    * canonical_product_id is resolved
    * canonical_unit is present
    * price_per_unit > 0
    * identity_confidence >= AUTO_LINK_THRESHOLD (0.80)
    * unit_status != "review" (we never learn pricing from review items)
- Strictly user-scoped — every read filters by restaurant_id.
- Trend = direction of latest 3-observation moving average vs the prior
  3-observation moving average (requires >= 4 points; otherwise "insufficient_data").
- Alert rule: latest price > moving_average * 1.10 AND observations >= 3
  AND identity_confidence + unit confidence are both high.

Collections
-----------
`price_history`:
  {id, restaurant_id, canonical_product_id, canonical_name, canonical_unit,
   price_per_unit, unit_price, quantity, normalization_multiplier,
   vendor_key, vendor_name, supplier_id,
   purchase_id, item_index, raw_name, item_code, invoice_date,
   identity_confidence, identity_match_type,
   unit_confidence, unit_source,
   observed_at, created_at}
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import db
from services.product_identity import resolve_product_identity, AUTO_LINK_THRESHOLD

logger = logging.getLogger("restaurant_ai")

# ── Thresholds ─────────────────────────────────────────────────────────
MIN_OBSERVATIONS_FOR_TREND = 4           # need 3+3 for MA vs prior MA (min 4 points)
MIN_OBSERVATIONS_FOR_ALERT = 3
PRICE_ALERT_PCT_THRESHOLD = 10.0         # percent above moving average
HIGH_IDENTITY_CONFIDENCE = 0.80
HIGH_UNIT_CONFIDENCE = {"parser", "memory:user_corrected", "user_corrected", "auto"}


# ── Vendor key normalization (matches unit_normalizer convention) ────
def _normalize_vendor_key(vendor: str) -> str:
    if not vendor:
        return "UNKNOWN"
    v = vendor.strip().upper()
    if "SYSCO" in v:
        return "SYSCO"
    if "US FOOD" in v or "USFOODS" in v:
        return "USFOODS"
    if "PERFORMANCE" in v or "PFG" in v:
        return "PFG"
    import re
    key = re.sub(r"[^A-Z0-9]", "", v)[:24]
    return key or "UNKNOWN"


def _unit_confidence_label(item: dict) -> str:
    """Return a confidence label for the unit normalization on an item."""
    src = (item.get("_unit_source") or "").strip()
    if src:
        return src
    status = (item.get("unit_status") or "").strip()
    if status == "user_corrected":
        return "user_corrected"
    if status == "resolved":
        return "parser"
    return status or "unknown"


def _is_high_unit_confidence(item: dict) -> bool:
    status = (item.get("unit_status") or "").lower()
    if status == "review":
        return False
    src = _unit_confidence_label(item)
    # Anything except "review" / "conflict" / "unknown" counts as high
    return src not in ("conflict", "unknown", "")


# ── Observation Ingestion ─────────────────────────────────────────────

async def ingest_purchase_items(
    *,
    restaurant_id: str,
    purchase_id: str,
    supplier_name: str,
    supplier_id: str = "",
    invoice_date: str = "",
    items: list[dict],
) -> dict:
    """
    Ingest all eligible items from a purchase into `price_history`.
    Re-ingestion is safe: we delete prior observations for this
    (purchase_id, restaurant_id) before inserting fresh ones.

    Returns: {inserted: int, skipped: int, reasons: {...}}
    """
    # Remove any prior observations for this purchase (idempotent re-ingest)
    await db.price_history.delete_many(
        {"restaurant_id": restaurant_id, "purchase_id": purchase_id}
    )

    vendor_key = _normalize_vendor_key(supplier_name)
    now = datetime.now(timezone.utc).isoformat()

    to_insert: list[dict] = []
    skipped = 0
    reasons: dict[str, int] = {}

    for idx, item in enumerate(items):
        raw_name = (item.get("raw_name") or "").strip()
        item_code = (item.get("item_code") or "").strip()

        price_per_unit = item.get("price_per_unit")
        canonical_unit = (item.get("canonical_unit") or "").strip()
        multiplier = item.get("normalization_multiplier")
        unit_conf_label = _unit_confidence_label(item)

        # Fallback: derive canonical_unit + price_per_unit from legacy
        # preprocessing fields (`pack_unit`, `normalized_price_per_lb`,
        # `total_case_weight`) when Milestone 2 fields are missing.
        if not canonical_unit or price_per_unit is None:
            pack_unit = (item.get("pack_unit") or "").strip().upper()
            npl = item.get("normalized_price_per_lb")
            try:
                npl_f = float(npl) if npl is not None else 0.0
            except (TypeError, ValueError):
                npl_f = 0.0

            if pack_unit in ("LB", "OZ") and npl_f > 0:
                canonical_unit = "lb"
                price_per_unit = npl_f
                tcw = item.get("total_case_weight")
                try:
                    tcw_f = float(tcw) if tcw is not None else 0.0
                except (TypeError, ValueError):
                    tcw_f = 0.0
                if tcw_f > 0:
                    multiplier = tcw_f if pack_unit == "LB" else (tcw_f / 16.0)
                unit_conf_label = unit_conf_label or "legacy_parser"

        # Hard gate: must have all canonical pricing fields
        if not raw_name or not canonical_unit or price_per_unit is None:
            skipped += 1
            reasons["missing_canonical_pricing"] = reasons.get("missing_canonical_pricing", 0) + 1
            continue
        try:
            ppu = float(price_per_unit)
        except (TypeError, ValueError):
            ppu = 0.0
        if ppu <= 0:
            skipped += 1
            reasons["non_positive_ppu"] = reasons.get("non_positive_ppu", 0) + 1
            continue

        # Skip unit_status=review — we don't learn pricing from unresolved items
        if (item.get("unit_status") or "").lower() == "review":
            skipped += 1
            reasons["low_unit_confidence"] = reasons.get("low_unit_confidence", 0) + 1
            continue

        # Resolve canonical product — prefer cached value if already on item
        cpid = (item.get("canonical_product_id") or "").strip()
        canonical_name = (item.get("canonical_name") or "").strip()
        identity_conf = float(item.get("identity_confidence") or 0)
        identity_match_type = (item.get("identity_match_type") or "").strip()

        if not cpid or identity_conf == 0:
            res = await resolve_product_identity(
                db, restaurant_id,
                raw_name=raw_name,
                vendor_key=vendor_key,
                product_code=item_code,
            )
            cpid = res.get("canonical_product_id") or ""
            canonical_name = res.get("canonical_name") or ""
            identity_conf = float(res.get("confidence") or 0)
            identity_match_type = res.get("match_type") or ""
            # Persist resolution back onto the item so the UI can render it
            item["canonical_product_id"] = cpid
            item["canonical_name"] = canonical_name
            item["identity_confidence"] = round(identity_conf, 3)
            item["identity_match_type"] = identity_match_type

        if not cpid:
            skipped += 1
            reasons["no_canonical_product"] = reasons.get("no_canonical_product", 0) + 1
            continue
        if identity_conf < HIGH_IDENTITY_CONFIDENCE:
            skipped += 1
            reasons["low_identity_confidence"] = reasons.get("low_identity_confidence", 0) + 1
            continue

        doc = {
            "id": str(uuid.uuid4()),
            "restaurant_id": restaurant_id,
            "canonical_product_id": cpid,
            "canonical_name": canonical_name,
            "canonical_unit": canonical_unit,
            "price_per_unit": round(ppu, 4),
            "unit_price": float(item.get("unit_price") or 0),
            "quantity": float(item.get("quantity") or 0),
            "normalization_multiplier": float(multiplier) if multiplier else None,
            "vendor_key": vendor_key,
            "vendor_name": supplier_name or "",
            "supplier_id": supplier_id or "",
            "purchase_id": purchase_id,
            "item_index": idx,
            "raw_name": raw_name,
            "item_code": item_code,
            "invoice_date": invoice_date or "",
            "identity_confidence": round(identity_conf, 3),
            "identity_match_type": identity_match_type,
            "unit_confidence": unit_conf_label or _unit_confidence_label(item),
            "unit_source": item.get("_unit_source") or "",
            "observed_at": invoice_date or now,
            "created_at": now,
        }
        to_insert.append(doc)

    if to_insert:
        await db.price_history.insert_many(to_insert)

    logger.info(
        f"price_intelligence.ingest: rid={restaurant_id} purchase={purchase_id} "
        f"inserted={len(to_insert)} skipped={skipped} reasons={reasons}"
    )

    # After ingestion, evaluate alerts for affected canonical products
    touched = {d["canonical_product_id"] for d in to_insert}
    new_alerts: list[dict] = []
    for cpid in touched:
        alert = await _evaluate_alert_for_product(
            restaurant_id=restaurant_id,
            canonical_product_id=cpid,
        )
        if alert:
            new_alerts.append(alert)

    return {
        "inserted": len(to_insert),
        "skipped": skipped,
        "reasons": reasons,
        "new_alerts": new_alerts,
    }


# ── Analytics ─────────────────────────────────────────────────────────

def _sort_observations(obs: list[dict]) -> list[dict]:
    """Sort observations by observed_at ascending (oldest first)."""
    return sorted(obs, key=lambda x: (x.get("observed_at") or "", x.get("created_at") or ""))


def _compute_ma(prices: list[float], window: int = 3) -> Optional[float]:
    """Arithmetic mean of the last `window` items, or None if insufficient."""
    if len(prices) < window:
        return None
    return round(sum(prices[-window:]) / window, 4)


def compute_trend(observations: list[dict]) -> dict:
    """
    Returns: {
      trend: 'up' | 'down' | 'stable' | 'insufficient_data',
      moving_average_latest: float or None,
      moving_average_prior: float or None,
      change_pct: float or None,
      observations_used: int,
    }
    """
    obs = _sort_observations(observations)
    prices = [float(o.get("price_per_unit") or 0) for o in obs]
    prices = [p for p in prices if p > 0]

    if len(prices) < MIN_OBSERVATIONS_FOR_TREND:
        return {
            "trend": "insufficient_data",
            "moving_average_latest": None,
            "moving_average_prior": None,
            "change_pct": None,
            "observations_used": len(prices),
        }

    ma_latest = _compute_ma(prices, 3)
    ma_prior = _compute_ma(prices[:-1], 3)
    if ma_prior is None or ma_latest is None or ma_prior <= 0:
        return {
            "trend": "insufficient_data",
            "moving_average_latest": ma_latest,
            "moving_average_prior": ma_prior,
            "change_pct": None,
            "observations_used": len(prices),
        }

    change_pct = round(((ma_latest - ma_prior) / ma_prior) * 100, 2)
    if abs(change_pct) < 1.0:
        trend = "stable"
    elif change_pct > 0:
        trend = "up"
    else:
        trend = "down"

    return {
        "trend": trend,
        "moving_average_latest": ma_latest,
        "moving_average_prior": ma_prior,
        "change_pct": change_pct,
        "observations_used": len(prices),
    }


def compute_stats(observations: list[dict]) -> dict:
    """
    Per-product min / max / avg / latest across observations.
    Assumes all observations share the same canonical_unit.
    """
    obs = _sort_observations(observations)
    prices = [float(o.get("price_per_unit") or 0) for o in obs]
    prices = [p for p in prices if p > 0]
    if not prices:
        return {
            "observations": 0, "min": None, "max": None, "avg": None,
            "latest": None, "first": None, "latest_vendor": None,
            "latest_date": None, "latest_observed_at": None,
        }
    latest_obs = obs[-1]
    return {
        "observations": len(prices),
        "min": round(min(prices), 4),
        "max": round(max(prices), 4),
        "avg": round(sum(prices) / len(prices), 4),
        "latest": round(prices[-1], 4),
        "first": round(prices[0], 4),
        "latest_vendor": latest_obs.get("vendor_name") or "",
        "latest_date": latest_obs.get("invoice_date") or "",
        "latest_observed_at": latest_obs.get("observed_at") or "",
    }


def evaluate_alert(observations: list[dict]) -> Optional[dict]:
    """
    Return an alert dict when the latest price is > MA by PRICE_ALERT_PCT_THRESHOLD
    with enough observations and high confidence. Otherwise None.
    """
    obs = _sort_observations(observations)
    if len(obs) < MIN_OBSERVATIONS_FOR_ALERT:
        return None

    # Only count high-confidence observations
    high_conf = [
        o for o in obs
        if float(o.get("identity_confidence") or 0) >= HIGH_IDENTITY_CONFIDENCE
        and (o.get("unit_confidence") or "") not in ("review", "conflict", "unknown", "")
    ]
    if len(high_conf) < MIN_OBSERVATIONS_FOR_ALERT:
        return None

    latest = high_conf[-1]
    latest_price = float(latest.get("price_per_unit") or 0)
    if latest_price <= 0:
        return None

    # Moving average over all prior high-confidence observations (exclude latest)
    prior = [float(o.get("price_per_unit") or 0) for o in high_conf[:-1]]
    prior = [p for p in prior if p > 0]
    if len(prior) < 2:
        return None
    ma = sum(prior) / len(prior)
    if ma <= 0:
        return None

    change_pct = round(((latest_price - ma) / ma) * 100, 2)
    if change_pct < PRICE_ALERT_PCT_THRESHOLD:
        return None

    return {
        "canonical_product_id": latest.get("canonical_product_id"),
        "canonical_name": latest.get("canonical_name"),
        "canonical_unit": latest.get("canonical_unit"),
        "latest_price": round(latest_price, 4),
        "moving_average": round(ma, 4),
        "change_pct": change_pct,
        "observations": len(high_conf),
        "latest_vendor": latest.get("vendor_name") or "",
        "latest_invoice_date": latest.get("invoice_date") or "",
        "latest_purchase_id": latest.get("purchase_id") or "",
        "severity": "high" if change_pct >= 20 else "medium",
    }


async def _evaluate_alert_for_product(*, restaurant_id: str, canonical_product_id: str) -> Optional[dict]:
    """Re-evaluate the alert for a canonical product. Upserts to db.alerts."""
    obs = await db.price_history.find(
        {"restaurant_id": restaurant_id, "canonical_product_id": canonical_product_id},
        {"_id": 0},
    ).to_list(5000)
    if not obs:
        return None
    alert = evaluate_alert(obs)
    # Canonical alert record key
    alert_key = {
        "restaurant_id": restaurant_id,
        "type": "price_intelligence",
        "canonical_product_id": canonical_product_id,
    }
    if not alert:
        # Clear any stale alerts for this product
        await db.alerts.delete_many(alert_key)
        return None

    now = datetime.now(timezone.utc).isoformat()
    alert_doc = {
        **alert_key,
        "severity": alert["severity"],
        "item_name": alert["canonical_name"],
        "canonical_unit": alert["canonical_unit"],
        "previous_price": alert["moving_average"],
        "new_price": alert["latest_price"],
        "change_pct": alert["change_pct"],
        "vendor": alert["latest_vendor"],
        "invoice_date": alert["latest_invoice_date"],
        "observations": alert["observations"],
        "message": (
            f"{alert['canonical_name']} — latest ${alert['latest_price']:.2f}/"
            f"{alert['canonical_unit']} is {alert['change_pct']:.1f}% above moving "
            f"average ${alert['moving_average']:.2f}/{alert['canonical_unit']} "
            f"({alert['observations']} observations)"
        ),
        "is_read": False,
        "updated_at": now,
    }
    existing = await db.alerts.find_one(alert_key, {"_id": 0, "id": 1, "created_at": 1})
    if existing:
        await db.alerts.update_one(alert_key, {"$set": alert_doc})
    else:
        alert_doc["id"] = str(uuid.uuid4())
        alert_doc["created_at"] = now
        await db.alerts.insert_one(alert_doc)
    return alert


# ── Query helpers ─────────────────────────────────────────────────────

async def list_products_summary(restaurant_id: str) -> list[dict]:
    """Product-level summary across all canonical units (grouped per product+unit)."""
    cursor = db.price_history.find({"restaurant_id": restaurant_id}, {"_id": 0})
    buckets: dict[tuple, list[dict]] = {}
    async for obs in cursor:
        key = (obs["canonical_product_id"], obs.get("canonical_unit") or "")
        buckets.setdefault(key, []).append(obs)

    # Load canonical products in one go
    pids = list({k[0] for k in buckets.keys()})
    cp_map: dict[str, dict] = {}
    if pids:
        async for cp in db.canonical_products.find(
            {"id": {"$in": pids}, "restaurant_id": restaurant_id},
            {"_id": 0, "id": 1, "canonical_name": 1, "category": 1},
        ):
            cp_map[cp["id"]] = cp

    out: list[dict] = []
    for (cpid, unit), obs_list in buckets.items():
        stats = compute_stats(obs_list)
        trend = compute_trend(obs_list)
        alert = evaluate_alert(obs_list)
        cp = cp_map.get(cpid, {})
        vendors = sorted({o.get("vendor_name") or "" for o in obs_list if o.get("vendor_name")})
        out.append({
            "canonical_product_id": cpid,
            "canonical_name": cp.get("canonical_name") or obs_list[-1].get("canonical_name") or "",
            "category": cp.get("category", ""),
            "canonical_unit": unit,
            "stats": stats,
            "trend": trend,
            "vendors": vendors,
            "vendor_count": len(vendors),
            "alert": alert,
        })
    out.sort(key=lambda x: (x["alert"] is None, -x["stats"].get("observations", 0), x["canonical_name"]))
    return out


async def product_history(restaurant_id: str, canonical_product_id: str, canonical_unit: str = "") -> dict:
    """Return sorted history + stats + trend + alert for a single product+unit."""
    query: dict[str, Any] = {
        "restaurant_id": restaurant_id,
        "canonical_product_id": canonical_product_id,
    }
    if canonical_unit:
        query["canonical_unit"] = canonical_unit

    obs = await db.price_history.find(query, {"_id": 0}).to_list(5000)
    obs = _sort_observations(obs)

    # If no unit specified, default to the most-observed unit
    if not canonical_unit and obs:
        counts: dict[str, int] = {}
        for o in obs:
            counts[o.get("canonical_unit") or ""] = counts.get(o.get("canonical_unit") or "", 0) + 1
        canonical_unit = max(counts, key=counts.get)
        obs = [o for o in obs if (o.get("canonical_unit") or "") == canonical_unit]

    cp = await db.canonical_products.find_one(
        {"id": canonical_product_id, "restaurant_id": restaurant_id},
        {"_id": 0, "id": 1, "canonical_name": 1, "category": 1},
    )

    return {
        "canonical_product_id": canonical_product_id,
        "canonical_name": (cp or {}).get("canonical_name") or (obs[-1].get("canonical_name") if obs else ""),
        "category": (cp or {}).get("category", ""),
        "canonical_unit": canonical_unit,
        "observations": obs,
        "stats": compute_stats(obs),
        "trend": compute_trend(obs),
        "alert": evaluate_alert(obs),
    }


async def product_vendor_comparison(restaurant_id: str, canonical_product_id: str, canonical_unit: str = "") -> dict:
    """Per-vendor latest / avg / count, with best/worst highlighted."""
    detail = await product_history(restaurant_id, canonical_product_id, canonical_unit)
    unit = detail["canonical_unit"]
    obs = detail["observations"]

    buckets: dict[str, list[dict]] = {}
    for o in obs:
        vendor = o.get("vendor_name") or "Unknown"
        buckets.setdefault(vendor, []).append(o)

    vendors = []
    for vendor, rows in buckets.items():
        rows = _sort_observations(rows)
        prices = [float(r.get("price_per_unit") or 0) for r in rows if float(r.get("price_per_unit") or 0) > 0]
        if not prices:
            continue
        vendors.append({
            "vendor": vendor,
            "observations": len(prices),
            "latest_price": round(prices[-1], 4),
            "latest_date": rows[-1].get("invoice_date") or rows[-1].get("observed_at") or "",
            "avg_price": round(sum(prices) / len(prices), 4),
            "min_price": round(min(prices), 4),
            "max_price": round(max(prices), 4),
        })
    vendors.sort(key=lambda v: v["latest_price"])
    best = vendors[0]["vendor"] if vendors else None
    worst = vendors[-1]["vendor"] if len(vendors) > 1 else best
    best_price = vendors[0]["latest_price"] if vendors else None
    worst_price = vendors[-1]["latest_price"] if vendors else None
    savings_pct = None
    if best_price and worst_price and worst_price > 0 and len(vendors) > 1:
        savings_pct = round((1 - best_price / worst_price) * 100, 2)
    return {
        "canonical_product_id": canonical_product_id,
        "canonical_name": detail["canonical_name"],
        "canonical_unit": unit,
        "vendors": vendors,
        "best_vendor": best,
        "worst_vendor": worst,
        "savings_pct": savings_pct,
    }


async def list_alerts(restaurant_id: str) -> list[dict]:
    """Currently active price intelligence alerts."""
    alerts = await db.alerts.find(
        {"restaurant_id": restaurant_id, "type": "price_intelligence"},
        {"_id": 0},
    ).sort("change_pct", -1).to_list(500)
    return alerts


# ── Historical backfill ────────────────────────────────────────────────

async def backfill_from_purchases(restaurant_id: str) -> dict:
    """
    One-time backfill: scan all existing purchases and ingest any eligible
    items into price_history. Safe to re-run — ingestion is idempotent per
    purchase_id.
    """
    purchases = await db.purchases.find({"restaurant_id": restaurant_id}, {"_id": 0}).to_list(20000)
    total_ins = 0
    total_skip = 0
    aggregated_reasons: dict[str, int] = {}
    purchases_with_items = 0

    for p in purchases:
        items = p.get("items") or []
        if not items:
            continue
        purchases_with_items += 1
        stats = await ingest_purchase_items(
            restaurant_id=restaurant_id,
            purchase_id=p.get("id"),
            supplier_name=p.get("supplier_name") or "",
            supplier_id=p.get("supplier_id") or "",
            invoice_date=p.get("invoice_date") or "",
            items=items,
        )
        total_ins += stats["inserted"]
        total_skip += stats["skipped"]
        for k, v in stats["reasons"].items():
            aggregated_reasons[k] = aggregated_reasons.get(k, 0) + v

    return {
        "purchases_scanned": len(purchases),
        "purchases_with_items": purchases_with_items,
        "observations_inserted": total_ins,
        "observations_skipped": total_skip,
        "skip_reasons": aggregated_reasons,
    }
