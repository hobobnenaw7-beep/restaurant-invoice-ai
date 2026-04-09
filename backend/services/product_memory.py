"""
Sysco Product Memory — built ONLY from previously Trusted rows.
Used as a cross-row validation support layer, NOT for numeric inference.

Stores: normalized description, unit price, pack, confirmed quantities.
Provides consistency checks for ambiguous rows.
"""
import logging
import re
from collections import defaultdict

logger = logging.getLogger("restaurant_ai")


def _normalize_product_key(raw_name: str) -> str:
    """
    Normalize a product description for matching.
    Strips whitespace, uppercases, removes special chars.
    """
    if not raw_name:
        return ""
    name = raw_name.upper().strip()
    # Remove leading item codes (digits at start)
    name = re.sub(r'^\d{4,}\s*', '', name)
    # Remove special chars except alphanumeric, spaces, slashes
    name = re.sub(r'[^A-Z0-9\s/]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


class ProductMemory:
    """
    In-memory product lookup table built from trusted extractions.
    Used for cross-row validation (support layer only).
    """

    def __init__(self):
        # Key: normalized product name
        # Value: list of {price, qty, pack, source_invoice}
        self._products = defaultdict(list)
        self._build_count = 0

    def build_from_trusted_items(self, items: list, source_label: str = "current_invoice"):
        """
        Add trusted items to the memory.
        Only items with confidence_level == "trusted" are accepted.
        Items without row_type are accepted (older DB entries may lack this field).
        """
        added = 0
        for it in items:
            if it.get("confidence_level") != "trusted":
                continue
            # Accept line_item, fee, or missing row_type (older DB entries)
            rt = it.get("row_type")
            if rt and rt not in ("line_item", "fee"):
                continue

            raw_name = (it.get("raw_name") or "").strip()
            key = _normalize_product_key(raw_name)
            if not key:
                continue

            qty = float(it.get("quantity", 0) or 0)
            price = float(it.get("unit_price", 0) or 0)
            total = float(it.get("total", 0) or 0)
            pack = (it.get("pack_size") or "").strip()

            if qty <= 0 or price <= 0 or total <= 0:
                continue

            self._products[key].append({
                "price": price,
                "qty": qty,
                "total": total,
                "pack": pack,
                "source": source_label,
                "raw_name": raw_name,
            })
            added += 1

        self._build_count += added
        return added

    async def build_from_db(self, db):
        """
        Build memory from all previously trusted Sysco items in MongoDB.
        Uses async motor client.
        """
        added = 0

        for coll_name in ["purchases", "receipt_extractions"]:
            try:
                coll = db[coll_name]
                query = {
                    "$or": [
                        {"detected_vendor": {"$regex": "sysco", "$options": "i"}},
                        {"extracted_data.supplier_name": {"$regex": "sysco", "$options": "i"}},
                        {"supplier_name": {"$regex": "sysco", "$options": "i"}},
                    ],
                }
                count = await coll.count_documents(query)
                logger.info(f"Product memory: {coll_name} has {count} matching docs")

                if count > 0:
                    docs = await coll.find(
                        query,
                        {"_id": 0, "extracted_data": 1, "items": 1},
                    ).to_list(length=500)

                    logger.info(f"Product memory: {coll_name} to_list returned {len(docs)} docs")
                    for doc_idx, doc in enumerate(docs):
                        items = doc.get("extracted_data", {}).get("items", [])
                        if not items:
                            items = doc.get("items", [])
                        if doc_idx == 0:
                            trusted_in_first = sum(1 for it in items if it.get("confidence_level") == "trusted")
                            logger.info(f"Product memory: first doc has {len(items)} items, {trusted_in_first} trusted")
                        added += self.build_from_trusted_items(items, source_label=f"db_{coll_name}")

            except Exception as e:
                logger.warning(f"Product memory: {coll_name} load error: {type(e).__name__}: {e}")

        if added > 0:
            logger.info(f"Product memory: loaded {added} trusted items from DB")
        else:
            logger.info(f"Product memory: 0 items from DB (checked purchases, receipt_extractions)")
        return added

    def lookup(self, raw_name: str, unit_price: float) -> dict:
        """
        Look up a product by name and price.
        Returns match info including quantity patterns.

        Args:
            raw_name: the product description
            unit_price: the unit price to match

        Returns:
            dict with:
                matched: bool
                match_key: str
                occurrences: int (total times this product was trusted)
                price_matches: int (times this exact price was seen)
                qty_pattern: dict (qty value → count)
                stable_qty: int or None (qty if one value dominates ≥2x)
                consistency: "stable" | "variable" | "insufficient"
        """
        key = _normalize_product_key(raw_name)
        if not key or key not in self._products:
            return {"matched": False, "match_key": key}

        entries = self._products[key]
        price_tolerance = 0.01

        # Filter to entries matching this price
        price_matches = [
            e for e in entries
            if abs(e["price"] - unit_price) <= price_tolerance
        ]

        # Build qty frequency for price-matched entries
        qty_pattern = defaultdict(int)
        for e in price_matches:
            qty_pattern[e["qty"]] += 1

        # Determine stability
        if len(price_matches) < 2:
            consistency = "insufficient"
            stable_qty = None
        else:
            # Check if one qty value dominates (≥2 occurrences)
            sorted_qtys = sorted(qty_pattern.items(), key=lambda x: -x[1])
            top_qty, top_count = sorted_qtys[0]
            if top_count >= 2:
                consistency = "stable"
                stable_qty = top_qty
            else:
                consistency = "variable"
                stable_qty = None

        return {
            "matched": True,
            "match_key": key,
            "occurrences": len(entries),
            "price_matches": len(price_matches),
            "qty_pattern": dict(qty_pattern),
            "stable_qty": stable_qty,
            "consistency": consistency,
        }

    @property
    def size(self):
        return self._build_count

    @property
    def unique_products(self):
        return len(self._products)

    def get_stats(self):
        return {
            "total_entries": self._build_count,
            "unique_products": len(self._products),
        }
