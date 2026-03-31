# Backend V2 — Performance & Architecture Audit Report
**Date**: Feb 2026 | **Context**: Post-migration from 4,007-line monolith to modular architecture

---

## 1. Endpoint Performance (avg of 3 runs each)

### Browsing (GET) — Target: <200ms
| Endpoint | Avg (ms) | Classification |
|---|---|---|
| `/api/auth/me` | 139 | Pure DB read |
| `/api/purchases` | 126 | Pure DB read |
| `/api/sales` | 135 | Pure DB read |
| `/api/salaries` | 124 | Pure DB read |
| `/api/other-expenses` | 117 | Pure DB read |
| `/api/alerts` | 126 | Pure DB read |
| `/api/records` | 114 | Pure DB read |
| `/api/chat/messages` | 110 | Pure DB read |
| `/api/approvals/counts` | 113 | Pure DB read (4x count_documents) |
| `/api/settings` | 132 | Pure DB read (2x find_one) |
| `/api/item-mappings` | 128 | Pure DB read |
| `/api/alerts/prices` | 118 | Pure DB read |
| `/api/dashboard/summary` | 159 | DB read + compute (see findings) |
| `/api/items` | 148 | DB read + N+1 alias queries |
| `/api/suppliers` | 122 | DB read + in-memory dedup |
| `/api/reports` | 131 | DB read + in-memory aggregation |
| `/api/prices/intelligence` | 127 | Full-collection scan + compute |
| `/api/prices/vendor-comparison` | 118 | Full-collection scan + compute |
| `/api/vendor-comparison/normalized` | 111 | Full-collection scan + compute |
| `/api/purchase-decisions` | 120 | Full-collection scan + compute |
| `/api/item-mappings/suggestions` | 122 | Full-collection scan + compute |

**All under 160ms** — acceptable at current data volume (35 purchases, 60 sales, 43 suppliers).

### Save (POST) — Target: <500ms
| Endpoint | Avg (ms) |
|---|---|
| `POST /api/purchases` (full pipeline) | 117 |
| `POST /api/sales` | 118 |
| `POST /api/salaries` | 112 |
| `POST /api/duplicates/check` | 114 |

**All under 120ms** — well within target.

---

## 2. Architecture Correctness Verification

### Claim: "Browsing endpoints are pure DB reads"
**MOSTLY CORRECT.** 12 of 24 GET endpoints are strict `db.find()` → return patterns with no computation. The remaining 12 load data and do in-memory computation (aggregation, dedup, price comparison), which is appropriate for analytics endpoints.

**EXCEPTION FOUND:**
`/api/dashboard/summary` calls `generate_smart_alerts(rid)` **TWICE** (lines 52 and 89 in `dashboard.py`). Each call loads ALL purchases and runs 3 analysis passes (not-ordered, price-increases, cheaper-vendors). This is **redundant** — the second call on line 89 only exists to re-check for cheaper vendors if the first 5 alerts didn't include one. The same result can be obtained from the first call's full result set.

### Claim: "Extraction does NOT run validation/trust"
**INCORRECT — validation DOES run during extraction.** In `routes/upload.py`:
- Line 431: `enrich_item_with_pack_size(item)` — runs pack-size regex parsing
- Line 433: `validate_and_score_item(item)` — runs full hard-gate validation (math check, field check, confidence scoring)
- Line 498: `validate_purchase_items(extracted["items"])` — runs cross-item suspicious pattern detection

**However, this is LIGHTWEIGHT** — all validation functions are pure CPU (regex + arithmetic), no DB or network calls. With typical receipts (5-20 items), this adds <1ms. The extraction bottleneck is the LLM calls (2-3 GPT-5.2 calls at ~3-15s each), not validation. **Running validation here is actually beneficial** because it gives the user immediate feedback on extraction quality before they save.

### Claim: "Save is not doing heavy chained operations"
**PARTIALLY INCORRECT.** `POST /api/purchases` does:

| Step | Operation | Weight |
|---|---|---|
| 1 | Enrich + validate items | Lightweight (CPU only) |
| 2 | Insert purchase | Fast DB write |
| 3 | Check/create vendor | 1 DB query |
| 4 | Check/create each item | N DB queries (1 per item) |
| 5 | **Load ALL purchases** | `find().to_list(10000)` |
| 6 | **Load ALL canonical items + aliases** | 2 more full-collection reads |
| 7 | **Scan all purchases for price changes** | O(items × purchases) |
| 8 | Create price alerts | Conditional DB writes |
| 9 | Audit log | 1 DB write |

Steps 5-7 are **unnecessary in the hot path**. Currently fast at 35 purchases, but at 500+ purchases this will degrade. The price-change detection could be deferred to a background task.

---

## 3. Identified Bottlenecks (by severity)

### HIGH — Dashboard double `generate_smart_alerts` call
- **File**: `routes/dashboard.py`, lines 52 and 89
- **Impact**: Loads ALL purchases TWICE plus runs 3 analysis passes each time
- **Current cost**: ~20ms (small dataset) — will grow linearly with data volume
- **Fix**: Use the first call's result for both smart_alerts AND best_opportunities

### MEDIUM — Purchase save loads all purchases for price comparison
- **File**: `routes/purchases.py`, lines 91-148
- **Impact**: O(items × all_purchases) scan on every save
- **Current cost**: <5ms (35 purchases) — at 1000 purchases, expect 50-100ms added
- **Fix**: Could query only recent purchases for the same items (indexed query) instead of full-collection scan

### MEDIUM — Full-collection scans in analytics endpoints
- **Files**: `prices.py`, `vendor_comparison.py`, `alerts.py`, `purchase-decisions`
- **Impact**: Load ALL purchases into memory for every request
- **Current cost**: ~10ms — at 10K purchases, expect 200-500ms
- **Fix**: Add MongoDB aggregation pipelines instead of Python-side computation (future optimization, not urgent)

### LOW — N+1 query in items endpoint
- **File**: `routes/items.py`, line 20
- **Impact**: 1 query per item to fetch aliases
- **Current cost**: ~10ms for 73 items
- **Fix**: Single query with `$in` on all item IDs, then group in Python

---

## 4. Summary

| Metric | Status |
|---|---|
| Browsing endpoints < 200ms | PASS (all 110-159ms) |
| Save endpoints < 500ms | PASS (all 112-118ms) |
| Pure DB reads for browsing | 12/24 pure, 12/24 with in-memory compute (acceptable) |
| Extraction path bottleneck | LLM calls (expected), not validation |
| Trust logic preserved | YES — `preprocessing.py` unchanged |
| Frontend compatibility | YES — verified by testing agent (100% pass) |
| No behavioral changes | YES — all response shapes identical |

### Architecture Health: GOOD
The migration achieved its primary goal: **separation of concerns**. The 4,007-line monolith is now 75 lines of orchestration + 20 focused route modules + 3 core modules + 3 service modules. Each file has a single responsibility and can be modified independently.

### Scaling concerns (not urgent, but worth noting):
At current data volume (35 purchases, 60 sales), everything is fast. At 1000+ purchases, the full-collection-scan analytics endpoints and the purchase-save price-detection will need optimization (MongoDB aggregation pipelines, indexed queries, or background processing).
