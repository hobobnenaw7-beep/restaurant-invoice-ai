# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, multi-user permissions, self-improving product memory, and universal product identity.

## Milestone 3: Universal Product Identity Layer — COMPLETE

### Three-Layer Architecture
```
A. Canonical Product (canonical_products)
   {id, canonical_name, category, attributes, keywords, status}

B. Vendor Product Mapping (vendor_product_mappings)
   {vendor_key, product_code, canonical_product_id, vendor_description, pack_size, source}

C. Alias / Description (product_aliases)
   {normalized_text, canonical_product_id, confidence, source}
```

### Resolution Priority
1. Direct code mapping (vendor+code) → confidence 1.0
2. User-confirmed alias (source=user_corrected) → confidence 1.0
3. Exact normalized text → confidence 0.95
4. Fuzzy keyword match → confidence 0.50-0.80 (low → needs_review)

### Cross-Vendor Example (Verified)
```
Canonical Product: "Chicken Breast Tender Boneless Jumbo" (Poultry)
  SYSCO:7667363   → "SYS CLS CHICKN CVP BRST TENDER JUMBO" (4/10 LB)
  USFOODS:4523871 → "CHICKEN BREAST TNDR BNLS JUMBO" (2/5 LB)
  PFG:PFG12345    → "CHKN BREAST TENDER JUMBO BNLS" (user confirmed)
```

### Initial Product Candidates
Top 20 from 3,205 unique signatures across 9,090 extracted items. Includes:
Container Foam, Chicken Gizzard, Chicken Wing, Ketchup Packet, Lemonade, Okra, etc.

### API Endpoints
- POST /api/products/generate-initial — Analyze data, generate candidates
- GET/POST /api/products/canonical — List/create products
- POST /api/products/canonical/{id}/vendor-mapping — Add vendor mapping
- POST /api/products/canonical/{id}/alias — Add text alias
- POST /api/products/resolve — Resolve item to canonical product
- POST /api/products/confirm-link — User confirms vendor=canonical link

### Files
- /app/backend/services/product_identity.py — Core identity engine
- /app/backend/routes/product_identity.py — API routes

## Milestone 4.5: DSS Upgrade (Decision-Support System) — COMPLETE (2026-04-21)

### Insight Confidence Engine (exact scoring)
```
score = recency*0.30 + observations*0.25 + identity*0.25 + unit*0.20

recency:     ≤14d→1.0, ≤30d→0.70, ≤90d→0.40, ≤180d→0.20, else 0.05
observations: ≥6→1.0, ≥4→0.70, ≥3→0.50, ≥2→0.25, ≥1→0.10
identity:    mean of per-obs identity_confidence (0..1)
unit:        weighted mean; parser/user_corrected→~1.0, legacy→0.5, review/unknown→~0.1

level = High   if score ≥ 0.80
      = Medium if 0.60 ≤ score < 0.80
      = Low    if score < 0.60
```

### Decision Guardrails
- **High** → actionable recommendation (`switch_vendor` / `renegotiate` / `investigate` / `hold`)
- **Medium** → insight labelled "Review suggested", no action button
- **Low** → raw data only (stats/trend/vendor-comparison hidden in UI)
- **Alert suppression**: evaluate_alert returns None unless level == "high". Dashboard bell double-guards on `confidence_level == "high"`.

### Data Integrity
- Every `price_history` record carries `data_quality_flag ∈ {good, fair, poor}`.
- **poor** records excluded from: trend, stats, evaluate_alert, vendor comparison.
- **fair** records show in raw history only (not analytics).
- Ingestion writes the flag; one-time migration back-classified 9 existing records.

### Probabilistic Language
- Alerts: "High likelihood you are paying above the recent typical price…"
- Recommendations never contain "overpaying" or imperative verbs for Medium/Low.

### UI — Color-coded confidence
- **Green** (`ShieldCheck`) = High · **Yellow** (`ShieldAlert`) = Medium · **Red** (`Shield`) = Low
- Hoverable tooltip breaks down score: "Based on N observations · recency/obs/identity/unit × weights"
- Recommendation panel uses the same tone (green/amber/slate).
- Stats/vendor-comparison/chart auto-hide when level = Low.
- Per-record `GOOD / FAIR / POOR` badge in the raw-history table.

### Testing — 47/47 PASS
- `test_dss_confidence.py` — 16 pure-function tests
- `test_price_intelligence_milestone4.py` — 11 trend/alert/stats tests (dates now relative)
- `test_dss_price_intelligence.py` — 20 HTTP contract tests (iteration_87)

### Sample scored insight (from demo@test.com)
- Product: Chicken Breast Tender Boneless Jumbo, 9 good observations, latest today
- Components: recency=1.00, observations=1.00, identity=0.95, unit=0.95
- Weighted score = 0.30 + 0.25 + 0.2375 + 0.19 = **0.978 → HIGH**
- Alert surfaced: +28.2% vs MA $3.20, severity high, action=renegotiate

### Low-confidence suppression (same user)
- Product: Ground Beef 80/20, 0 good + 3 poor observations (identity 0.55, unit "unknown")
- All poor records filtered out of analytics → 0 good obs
- score = 0.00 → **LOW**, recommendation = "Not enough reliable data yet · RAW DATA ONLY", action=None
- Alert = null (correctly suppressed)

## Milestone 4: Price Intelligence & Market Benchmarking — COMPLETE (2026-04-21)

### Goal
Unit-safe price benchmarks, trend direction, and confidence-based alerts across every
canonical product — strictly scoped per-restaurant.

### Data Model
```
price_history:
  {id, restaurant_id, canonical_product_id, canonical_name, canonical_unit,
   price_per_unit, unit_price, quantity, normalization_multiplier,
   vendor_key, vendor_name, supplier_id,
   purchase_id, item_index, raw_name, item_code, invoice_date,
   identity_confidence, identity_match_type,
   unit_confidence, unit_source,
   observed_at, created_at}

alerts (type='price_intelligence'): persisted when threshold hit.
```

### Ingestion Gates (hard rules)
- canonical_product_id resolved (identity_confidence >= 0.80)
- canonical_unit present
- price_per_unit > 0
- unit_status != "review"
- Legacy fallback: if pack_unit ∈ (LB, OZ) and normalized_price_per_lb > 0
  → derive canonical_unit=lb + multiplier from total_case_weight

### Analytics Engine
- stats: min / max / avg / latest / first (+ latest_vendor / latest_date)
- trend: Up / Down / Stable / insufficient_data
  (latest-3 moving average vs prior-3 MA; needs >= 4 observations;
  |change| < 1% → stable)
- alert: latest_price > moving_average * 1.10 AND >= 3 high-confidence
  observations → severity high (>=20%) / medium (10-20%).
  Stale alerts are auto-cleared on re-evaluation.

### API Endpoints
- GET  /api/price-intelligence/products — list (stats, trend, vendors, alert)
- GET  /api/price-intelligence/products/{cpid}/history?canonical_unit=lb
- GET  /api/price-intelligence/products/{cpid}/vendors?canonical_unit=lb
- GET  /api/price-intelligence/alerts
- POST /api/price-intelligence/backfill — one-shot historical ingest (idempotent)

### Pipeline Hooks
- POST   /api/purchases                 → ingest_purchase_items
- PUT    /api/purchases/{pid}           → re-ingest on update
- PATCH  /api/purchases/{pid}/items/{i} → re-ingest on inline edit

### Dashboard Integration
- /api/dashboard/summary → PI alerts prepended to smart_alerts
  (surfaces in the existing notification bell).

### Frontend
- New page `/price-intelligence` (added to sidebar as "Price Intelligence")
  with KPIs, filters (all/alerts/up/down), product table, and detail modal
  (price chart with avg reference line, vendor comparison, full history).
- Inline alert badge on product rows.

### Files
- /app/backend/services/price_intelligence.py
- /app/backend/routes/price_intelligence.py
- /app/backend/routes/purchases.py (hooks)
- /app/backend/routes/dashboard.py (alert merge)
- /app/frontend/src/pages/PriceIntelligencePage.js
- /app/backend/tests/test_price_intelligence_milestone4.py (11 analytics unit tests)
- /app/backend/tests/test_price_intelligence_endpoints.py (14 endpoint tests)

### Testing
- 11/11 pure-function tests (trend/alert rules) pass
- 14/14 endpoint/integration tests pass (iteration_86 — multi-tenant isolation
  verified, backfill idempotency verified, hooks verified).

## Completed Work
All Milestone 1-3 deliverables complete. See CHANGELOG.md for details.

## Upcoming Tasks
### P1
- Expand "Smart Market Insights" into 3-panel command center
- Integrate product identity into extraction pipeline (auto-resolve during upload)
- Build Product Identity management UI
### P2
- AI Chat Assistant page polish, Trash/Restore UI, Salaries OCR upload
- Inline price-intelligence alert badge next to items in ExpensesPage rows

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
