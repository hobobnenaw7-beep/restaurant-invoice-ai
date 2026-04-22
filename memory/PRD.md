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

## Milestone 9: Navigation Restructure + Orders Foundation — COMPLETE (2026-02-13)

### Goal
Staged refactor across 5 phases: cleaner grouped sidebar, safe redirects for legacy
routes, UI consolidation under **Procurement**, and a minimal **Item-driven Orders**
page with strict guardrails (NO free-text, NO auto-ordering from DSS).

### Navigation Tree (final)
```
Dashboard
Orders                          (NEW — lightweight)
Expenses  ▾
  Raw Materials        → /expenses?tab=raw_materials
  Salaries             → /expenses?tab=salaries
  Other Expenses       → /expenses?tab=other
Sales
Items  ▾
  Item Catalog         → /items
  Product Matching Rules → /correction-memory
Vendors  ▾
  Vendor Directory     → /vendors
  Vendor Pricing ($/LB)→ /vendor-comparison
Reports
Procurement  ▾
  Smart Purchases      → /procurement/smart-purchases
  Price Intelligence   → /procurement/price-insights
  Decisions            → /procurement/decisions
  Suggestions Inbox    → /procurement/suggestions
Records Library
—— Management ——
User Management · Approvals · Audit Log
Settings (pinned)
```

### Legacy Route Redirects (all <Navigate replace/>)
| Old | New |
|---|---|
| /purchase-decisions      | /procurement/smart-purchases |
| /price-intelligence      | /procurement/price-insights |
| /procurement-decisions   | /procurement/decisions |
| /procurement/inbox       | /procurement/suggestions |

Bookmarks keep working — no 404s, no blank screens. Verified live.

### Orders (Phase 4 — lightweight, Item-driven)
- Backend: `routes/orders.py` — `GET/POST/DELETE /api/orders`.
  `_enrich_items()` resolves each `item_id` against `canonical_items` (tenant-scoped).
  Unknown id → 400 `unknown_item_ids:[...]`. Status must be `draft|submitted`
  (anything else → 400). Tenant isolation enforced. No _id leakage.
- Frontend: `pages/OrdersPage.js` + `CreateOrderModal` with `ItemPicker` reading
  `/api/items` and auto-enriching the last known price/vendor/unit from
  `/api/items/{id}/price-history` (non-fatal — "if available").
- Strict constraints enforced in UI and API:
  * NO free-text product creation (only ItemPicker)
  * NO duplicate product definitions (every line must reference canonical_items.id)
  * NO auto-ordering from Procurement recommendations (zero references in code)

### Regression Discipline
- Phase 3 explicitly UI-only. **No changes** to price_intelligence /
  procurement / procurement_suggestions / procurement_audit services.
- 34/34 procurement regression tests remain green (inbox_outcome + audit_api +
  audit unit).

### Testing — 46/46 PASS (iter 93, 100%)
- 12 new Orders API tests: auth, create/enrich/list/delete, bogus item_id → 400,
  invalid status → 400, cross-tenant 404, no _id leakage.
- 34 procurement regression tests green.
- Frontend verified live: sidebar order exact, 4 groups expand/collapse with
  correct children+hrefs, 4 legacy redirects, group-active-state on
  /procurement/decisions, Orders page empty state + modal + item-pick + save-draft,
  mobile sheet opens, 5 regression pages still render.

### Files
- /app/frontend/src/components/Layout.js (rewritten — navTree + NavGroup)
- /app/frontend/src/App.js (new routes + <Navigate replace/>)
- /app/frontend/src/pages/OrdersPage.js (new — 289 lines)
- /app/backend/routes/orders.py (new — 135 lines)
- /app/backend/server.py (registered orders_router)
- /app/backend/tests/test_orders_api.py (new — 12 tests)


## Milestone 8: Decision Audit Log (Learning Foundation) — COMPLETE (2026-02-13)

### Goal
Structured, queryable dataset linking **recommendation → user interaction →
final outcome** — the data-collection layer for future decision-quality
evaluation. Strict scope: NO ML, NO auto-tuning, NO threshold adjustment.

### Data Model (one record per active recommendation)
```
procurement_decision_events
  event_id, restaurant_id, user_id
  canonical_product_id, canonical_name, canonical_unit
  recommendation_type      (switch_vendor|renegotiate|no_action|monitor_only)
  confidence_score, confidence_level, risk_level
  generated_at, first_generated_at, generation_count
  suggestion_id, suggestion_opened_at, draft_viewed_at, acknowledged_at
  outcome_type (acted_on|not_pursued), outcome_at, outcome_note, outcome_by_user_id
  status (open|interacted|finalized), updated_at
```

### Lifecycle Hooks (zero-regression, try/except wrapped)
- `GET /procurement/recommendations` → `record_recommendation_generated()`
  upserts ONE open record per `(tenant, cpid, rec_type)`; duplicate calls refresh
  confidence/risk/generated_at and bump `generation_count` (NO new rows).
- `POST /procurement/events` → `record_interaction()` stamps
  `suggestion_opened_at | draft_viewed_at | acknowledged_at` on first occurrence
  only (subsequent calls never overwrite).
- `POST /procurement/suggestions` → `link_suggestion()` attaches `suggestion_id`.
- `PATCH /procurement/suggestions/{id}/outcome` → `finalize_outcome()` flips
  status to `finalized`, writes `outcome_type / outcome_at / outcome_note /
  outcome_by_user_id`. Fallback: minimal finalized row created if audit record
  missing so the dataset stays complete.

### Read-Only API
- `GET /api/procurement/audit/events` — filter by status / recommendation_type /
  outcome_type / confidence_level; invalid values → 400.
- `GET /api/procurement/audit/stats` — returns:
  `{total, open, interacted, finalized,
    by_recommendation_type.{switch_vendor|renegotiate|no_action|monitor_only}.
        {generated, acted_on, not_pursued, acted_on_rate, not_pursued_rate},
    high_confidence_not_pursued[],
    sample_queries.{switch_vendor_acted_on_rate,
                    high_confidence_not_pursued_count}}`

### Sample Queries Supported
1. "% of switch_vendor recommendations that were acted_on"
   → `stats.sample_queries.switch_vendor_acted_on_rate`
2. "high-confidence recommendations that were not_pursued"
   → `stats.high_confidence_not_pursued[]` (full records with reason notes)

### Example Record Lifecycle
```
t0  recommendations_for_restaurant() runs
    → insert {status: open, confidence_score: 0.94, generation_count: 1, ...}
t1  user opens modal → suggestion_opened event
    → update {status: interacted, suggestion_opened_at: t1}
t2  draft_viewed event  → draft_viewed_at = t2
t3  acknowledgment_checked event → acknowledged_at = t3
t4  POST /suggestions  → suggestion_id linked
t5  PATCH /suggestions/{id}/outcome {acted_on}
    → status: finalized, outcome_type: acted_on, outcome_at: t5
```

### Testing — 24/24 PASS (iter 92 = 100%)
- 11 unit (fake-collection: upsert, idempotency, interaction first-stamp,
  link, finalize, missing-record fallback, stats shape + rates, tenant isolation)
- 13 live integration (auth, filter validation, hooks, full e2e lifecycle,
  idempotency, cross-tenant isolation, perf <1.5s on demo tenant)
- 40/40 regression pass across inbox/api/decisions

### Files
- /app/backend/services/procurement_audit.py
- /app/backend/routes/procurement_audit.py
- /app/backend/server.py (router registration)
- /app/backend/services/procurement_decisions.py (hook)
- /app/backend/services/procurement_suggestions.py (hooks)
- /app/backend/routes/procurement.py (user_id propagation)
- /app/backend/tests/test_procurement_audit.py
- /app/backend/tests/test_procurement_audit_api.py


## Milestone 6: Controlled Action Layer — COMPLETE (2026-04-22)

### Goal
Bridge decision → action **with friction, not automation**. Advisory only:
no purchase execution, no vendor comms, no imperative language.

### Backend
- `services/procurement_suggestions.py`
  * `log_event` — fixed enum (suggestion_opened, draft_viewed, acknowledgment_checked, action_confirmed, action_canceled); raises ValueError on unknown type → 400.
  * `save_suggestion` — HARD gate on `acknowledgment_confirmed`; status always `saved_for_review` (execution statuses cannot be set via API).
  * `list_suggestions` — tenant-scoped.
  * `suggested_quantity_hint` — returns `{lookback, quantities, helper_text, disclaimer}` filtered to `data_quality_flag='good'`; NEVER pre-fills input.
- `routes/procurement_suggestions.py`
  * `POST /api/procurement/events`
  * `POST /api/procurement/suggestions`
  * `GET  /api/procurement/suggestions`
  * `GET  /api/procurement/quantity-hint/{cpid}?canonical_unit=lb`

### Frontend
- `components/procurement/PurchaseSuggestionModal.js` — advisory-only:
  * Header badge "ADVISORY ONLY" + disclaimer.
  * Section A: Recommendation Summary (product, recommended vendor, reference price rows, delta row, reason).
  * Section B: Suggested Quantities — **helper text only, zero input fields**. Yellow disclaimer row.
  * Section C: Evidence + Uncertainty bullets.
  * Mandatory acknowledgment block: red-dashed, disclaimer + checkbox gates Save Suggestion button.
  * Footer: Copy details · Cancel · Save Suggestion (disabled until ack).
  * Post-save state: "Suggestion saved for your review" + Copy / Done buttons.
  * Event log wired: suggestion_opened on open · draft_viewed after hint load · acknowledgment_checked on tick · action_confirmed on save · action_canceled on cancel/X.
- CTA label **"Prepare Purchase Suggestion"** on full-card and inline-card; shown ONLY for high-confidence switch_vendor/renegotiate. No "order"/"buy"/"submit" anywhere.

### Collections
- `procurement_suggestion_events` — audit log per event.
- `procurement_suggestions` — saved advisory drafts (status=`saved_for_review`).

### Testing — 18/18 PASS (iteration_90, 100% on all spec criteria)
- 8 unit tests (events enum, save ack-gate, quantity-hint filtering & disclaimer, tenant isolation).
- 10 API tests (POST /events valid+invalid, POST /suggestions ack enforcement, GET /suggestions, /quantity-hint payload shape, 401 unauth, isolation).
- Frontend verified: CTA label exact, 3 sections present, zero inputs in quantities, acknowledgment gate works at UI AND API layers, events fire correctly, saved-state copy aligned with spec.

### Files
- /app/backend/services/procurement_suggestions.py
- /app/backend/routes/procurement_suggestions.py
- /app/backend/tests/test_procurement_suggestions.py
- /app/backend/tests/test_procurement_suggestions_api.py
- /app/frontend/src/components/procurement/PurchaseSuggestionModal.js
- /app/frontend/src/components/procurement/ProcurementUI.js (CTA + callback wiring)
- /app/frontend/src/pages/ProcurementDecisionsPage.js (wires the modal)
- /app/frontend/src/pages/PriceIntelligencePage.js (inline pill + modal)

## Milestone 5: Procurement Decision Engine — FRONTEND COMPLETE (2026-04-21)

### Hybrid UI
- **Inline summary panel** on Price Intelligence page — "Top procurement actions"
  grid rendering up to 5 high-confidence actionable cards from
  `GET /api/procurement/recommendations?only_actionable=true`. View-all button
  navigates to the dedicated tab.
- **Dedicated page** at `/procurement-decisions` — full list of decisions from
  `GET /api/procurement/recommendations`, KPI-strip filters (Total / Switch
  Vendor / Renegotiate / No Action / Monitor Only), search, Confidence filter
  (All/High/Medium/Low), Risk filter (All/Low/Medium/High), Full decision cards
  with action pill, color-coded risk + confidence badges, 3-delta price-context
  row (vs Avg / vs Target / vs Alt), best-alternative highlight, expandable
  evidence + uncertainty bullets, observation count + trend indicator.
- **Target Price Modal** (shared, used from both pages) wraps
  `PATCH /api/procurement/targets/{cpid}`. Supports set/clear/validate; cards
  auto-refresh on save.

### Reusable Components
- `components/procurement/ProcurementUI.js` — `ActionPill`, `ConfidenceBadge`,
  `RiskBadge`, `DeltaRow`, `InlineDecisionCard`, `FullDecisionCard`,
  `TargetPriceModal`, plus `REC_CFG`/`CONF_CFG`/`RISK_CFG` color dictionaries.

### Routing & Nav
- New route `/procurement-decisions` (PermRoute `view_reports`).
- Sidebar link labelled **Procurement** with `Sparkles` icon.

### Testing — 100% PASS (iteration_89)
- All 12 flows verified: login, inline summary safety (no low/medium/monitor
  leaks), probabilistic language ("High likelihood…"), view-all navigation,
  dedicated tab KPI/search/confidence/risk filters, full-card elements
  (action pill, risk, confidence, 3 deltas, evidence toggle, best-alt row),
  Target modal open/validate/save/auto-refresh/clear/sidebar link.

## Milestone 5: Procurement Decision Engine — BACKEND COMPLETE (2026-04-21)

### Goal
Convert high-confidence pricing insights into decision-ready procurement
recommendations with explicit evidence, uncertainty and risk.

### Decision Flow
```
1. GUARDRAILS (fail-closed → monitor_only)
   - insight confidence level == 'high' AND score >= 0.80
   - good-quality observation count >= 3
   - identity_confidence and unit_confidence both high
   (data_quality_flag filtering upstream already enforces per-record checks)

2. SIGNALS (unit-safe)
   - delta_vs_avg       = (current - hist_avg) / hist_avg
   - delta_vs_target    = (current - target) / target  (if target set)
   - delta_vs_alt       = (current - best_alt) / current
   - alt_evidence_depth = # good observations for alt vendor
   - alt_recent         = alt appears in last 6 observations

3. RULES (first match wins)
   a) cheaper alt >=5% AND alt_evidence_depth >=2 AND alt_recent
      → switch_vendor
   b) delta_vs_avg >= 10%  OR  delta_vs_target >= 5%
      → renegotiate
   c) |delta_vs_avg| <= 3%
      → no_action
   d) fallback
      → monitor_only

4. RISK + DECISION_CONFIDENCE
   risk_level ∈ {low, medium, high} — scales with evidence depth
   decision_confidence = insight_score * evidence_scale (derated if thin alt)
   monitor_only is capped at 0.50 decision_confidence
```

### API Endpoints
- GET   /api/procurement/recommendations[?only_actionable=true]
  Returns {items, total, breakdown{switch_vendor,renegotiate,no_action,monitor_only}}
  `only_actionable=true` safety filter — only high-confidence switch_vendor/renegotiate.
- GET   /api/procurement/recommendations/{canonical_product_id}[?canonical_unit=lb]
- PATCH /api/procurement/targets/{canonical_product_id}
  Body: `{target_price_per_unit, canonical_unit}` — null clears.

### Output Model (per decision)
canonical_product_id, canonical_name, canonical_unit, category,
recommendation_type, decision_confidence, confidence_level, insight_confidence,
risk_level, reason_summary, evidence[], uncertainty[],
current_vendor, current_price_per_unit,
target_price_per_unit, historical_average_price_per_unit,
best_alternative_vendor, best_alternative_price_per_unit, best_alternative_observations,
price_delta_vs_avg_pct, price_delta_vs_target_pct, price_delta_vs_alternative_pct,
observation_count, alert, trend, status,
guardrails_passed, guardrail_failures[], generated_at

### Sample Decisions (from tests + live data)

**switch_vendor:**
```
recommendation_type=switch_vendor, decision_confidence=0.98, risk=medium
reason: "High likelihood of savings by switching Chicken Breast from
         Sysco Restaurant Supply to US Foods (~16.7% lower across 4 observations)."
evidence:
  - Sysco Restaurant Supply currently at $4.20/lb.
  - 8.0% above your own recent average of $3.89/lb across 9 observations.
  - 12.0% above the target price of $3.75/lb.
  - Alternative vendor US Foods has been $3.50/lb (16.7% cheaper) across 4 obs.
uncertainty:
  - Alternative-vendor comparison is based on only 4 observation(s); prices may vary.
```

**renegotiate (live):**
```
recommendation_type=renegotiate, decision_confidence=0.98, risk=low
reason: "High likelihood you are paying more than recent typical for
         Chicken Breast ... (24.3% above target) with no strong alternative
         vendor available — renegotiation suggested."
```

**monitor_only:**
```
recommendation_type=monitor_only, decision_confidence ≤ 0.50, risk=high
reason: "Not enough reliable evidence to recommend a specific action ...
         continue to monitor."
```

### Files
- /app/backend/services/procurement_decisions.py
- /app/backend/routes/procurement.py
- /app/backend/server.py (router registration)
- /app/backend/tests/test_procurement_decisions.py (17 unit tests)
- /app/backend/tests/test_procurement_api.py (14 API contract tests, from iteration_88)
- /app/backend/tests/conftest.py (sys.path fix)

### Testing — 31/31 PASS
- Unit: guardrails, switch_vendor rule, renegotiate rule, no_action, monitor_only,
  risk scaling, decision_confidence bounds, probabilistic language, output-model shape.
- API: list+breakdown, single-product, 404, only_actionable safety filter,
  target-price set/clear/validate, multi-tenant isolation, auth.

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
### P1 — next candidates
- Expand "Smart Market Insights" into 3-panel command center.
- Integrate product identity into extraction pipeline (auto-resolve during upload).
### P2
- AI Chat Assistant page polish, Trash/Restore UI, Salaries OCR upload.
- Inline price-intelligence alert badge next to items in ExpensesPage rows.
- Nightly digest emailer for top-3 actionable procurement decisions.
- UI surface for audit stats (learning-loop dashboard — top "not_pursued" reasons,
  acted-on rate by rec_type).
- Paged aggregation for aggregate_audit_stats beyond 2000 rows per tenant.
- Backfill: 4 pre-existing failures in test_procurement_suggestions.py
  (missing canonical_name / current_vendor kwargs — unrelated to audit log).

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
