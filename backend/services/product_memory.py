"""
Sysco Product Memory — built ONLY from previously Trusted rows.
Used as a cross-row validation support layer, NOT for numeric inference.

V2: Item Code-first matching, fuzzy description fallback, controlled qty=1 support.

Stores: item_code, normalized description, unit price, pack, confirmed quantities.
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


def _tokenize(text: str) -> set:
    """Convert text to a set of normalized tokens for fuzzy matching."""
    if not text:
        return set()
    text = text.upper().strip()
    # Remove special chars
    text = re.sub(r'[^A-Z0-9\s]', '', text)
    tokens = set(text.split())
    # Remove very short noise tokens (1 char) and common OCR noise
    tokens = {t for t in tokens if len(t) >= 2}
    return tokens


def _jaccard_similarity(tokens_a: set, tokens_b: set) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# Minimum Jaccard similarity threshold for fuzzy matching
FUZZY_THRESHOLD = 0.45


class ProductMemory:
    """
    In-memory product lookup table built from trusted extractions.
    Used for cross-row validation (support layer only).

    Lookup priority:
    1. Item Code (exact match) — most stable
    2. Fuzzy description match + price match — fallback for OCR variance
    """

    def __init__(self):
        # Key: normalized product name
        # Value: list of {price, qty, pack, source_invoice, item_code, tokens}
        self._products = defaultdict(list)
        # Key: item_code (cleaned digits)
        # Value: list of {price, qty, pack, source_invoice, raw_name, key}
        self._by_item_code = defaultdict(list)
        self._build_count = 0

    def _clean_item_code(self, code: str) -> str:
        """Extract just the digits from an item code."""
        if not code:
            return ""
        digits = re.sub(r'[^0-9]', '', code)
        return digits if len(digits) >= 4 else ""

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
            item_code = self._clean_item_code(it.get("item_code") or "")

            if qty <= 0 or price <= 0 or total <= 0:
                continue

            tokens = _tokenize(raw_name)

            entry = {
                "price": price,
                "qty": qty,
                "total": total,
                "pack": pack,
                "source": source_label,
                "raw_name": raw_name,
                "item_code": item_code,
                "tokens": tokens,
            }

            self._products[key].append(entry)

            # Index by item_code if available
            if item_code:
                self._by_item_code[item_code].append({
                    **entry,
                    "key": key,
                })

            added += 1

        self._build_count += added
        return added

    async def build_from_db(self, db):
        """
        Build memory from all previously trusted Sysco items in MongoDB.
        Uses async motor client.
        Checks: sysco_trusted_extractions (new), purchases, receipt_extractions.
        """
        added = 0

        for coll_name in ["sysco_trusted_extractions", "purchases", "receipt_extractions"]:
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
            logger.info(f"Product memory: 0 items from DB (checked sysco_trusted_extractions, purchases, receipt_extractions)")
        return added

    def _fuzzy_find(self, raw_name: str) -> list:
        """
        Find memory products that fuzzy-match the given raw_name.
        Returns list of (key, similarity_score) sorted by score descending.
        """
        query_tokens = _tokenize(raw_name)
        if not query_tokens:
            return []

        matches = []
        for key, entries in self._products.items():
            # Use the tokens from the first entry (all entries for a key have similar names)
            if entries:
                candidate_tokens = entries[0].get("tokens", set())
                if not candidate_tokens:
                    candidate_tokens = _tokenize(key)
                sim = _jaccard_similarity(query_tokens, candidate_tokens)
                if sim >= FUZZY_THRESHOLD:
                    matches.append((key, sim))

        matches.sort(key=lambda x: -x[1])
        return matches

    def lookup(self, raw_name: str, unit_price: float, item_code: str = "") -> dict:
        """
        Look up a product by item_code (primary) or fuzzy name match (fallback).

        Priority:
        1. Item code match (exact digit match)
        2. Exact normalized key match
        3. Fuzzy token-based match

        Returns match info including quantity patterns.
        """
        cleaned_code = self._clean_item_code(item_code)
        price_tolerance = 0.01

        # ── Priority 1: Item Code Match ──
        if cleaned_code and cleaned_code in self._by_item_code:
            entries = self._by_item_code[cleaned_code]
            return self._build_match_result(
                entries, unit_price, price_tolerance,
                match_method="item_code",
                match_key=cleaned_code,
            )

        # ── Priority 2: Exact Normalized Key Match ──
        key = _normalize_product_key(raw_name)
        if key and key in self._products:
            entries = self._products[key]
            return self._build_match_result(
                entries, unit_price, price_tolerance,
                match_method="exact_key",
                match_key=key,
            )

        # ── Priority 3: Fuzzy Token Match ──
        fuzzy_matches = self._fuzzy_find(raw_name)
        if fuzzy_matches:
            best_key, best_sim = fuzzy_matches[0]
            entries = self._products[best_key]
            return self._build_match_result(
                entries, unit_price, price_tolerance,
                match_method="fuzzy",
                match_key=best_key,
                fuzzy_score=round(best_sim, 3),
            )

        return {"matched": False, "match_key": key, "match_method": "none"}

    def _build_match_result(self, entries: list, unit_price: float,
                            price_tolerance: float, match_method: str,
                            match_key: str, fuzzy_score: float = None) -> dict:
        """Build a standardized match result from a list of memory entries."""
        # Filter to entries matching this price
        price_matches = [
            e for e in entries
            if abs(e["price"] - unit_price) <= price_tolerance
        ]

        # Also track ALL qty patterns (not just price-matched)
        all_qty_pattern = defaultdict(int)
        for e in entries:
            all_qty_pattern[e["qty"]] += 1

        # Build qty frequency for price-matched entries
        qty_pattern = defaultdict(int)
        for e in price_matches:
            qty_pattern[e["qty"]] += 1

        # Determine stability
        if len(price_matches) < 2:
            consistency = "insufficient"
            stable_qty = None
        else:
            sorted_qtys = sorted(qty_pattern.items(), key=lambda x: -x[1])
            top_qty, top_count = sorted_qtys[0]
            if top_count >= 2:
                consistency = "stable"
                stable_qty = top_qty
            else:
                consistency = "variable"
                stable_qty = None

        # Has this product+price been seen before at all?
        seen_at_this_price = len(price_matches) > 0
        # Has this product been seen at ANY price?
        seen_at_any_price = len(entries) > 0

        result = {
            "matched": True,
            "match_key": match_key,
            "match_method": match_method,
            "occurrences": len(entries),
            "price_matches": len(price_matches),
            "qty_pattern": dict(qty_pattern),
            "all_qty_pattern": dict(all_qty_pattern),
            "stable_qty": stable_qty,
            "consistency": consistency,
            "seen_at_this_price": seen_at_this_price,
            "seen_at_any_price": seen_at_any_price,
        }

        if fuzzy_score is not None:
            result["fuzzy_score"] = fuzzy_score

        return result

    @property
    def size(self):
        return self._build_count

    @property
    def unique_products(self):
        return len(self._products)

    @property
    def unique_item_codes(self):
        return len(self._by_item_code)

    def get_stats(self):
        return {
            "total_entries": self._build_count,
            "unique_products": len(self._products),
            "unique_item_codes": len(self._by_item_code),
        }
