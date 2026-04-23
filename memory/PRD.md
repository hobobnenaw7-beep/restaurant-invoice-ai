# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, multi-user permissions, self-improving product memory, and universal product identity.

## Milestone 21: Dashboard Visual Refinement (Minimal Color) — COMPLETE (2026-02-14)

### Goal
Reduce visual clutter on the dashboard. Color is now reserved for
meaning (up/down, alerts) — never for decoration.

### Layout (matches spec exactly)
- **Row 1** — 2 neutral stat cards: **Sales** (green delta when up),
  **Expenses** (red delta when up). Both clickable → sales / expenses
  pages.
- **Row 2** — 3 nav cards with soft-tinted icons: **Orders**,
  **Procurement**, **Items**. Pure navigation, no data preview.
- **Insights** (below) — 3 neutral cards:
  - **Price Movement** — only the delta pill is colored; rows neutral.
  - **Best Vendor** — completely neutral list (no hierarchy noise).
  - **Alerts** — red background when severity high / |Δ|≥20%,
    amber when ≥10%. Only place a colored background appears on the
    page.

### Color rules enforced
- Default surface: white + slate-200 border
- Numbers: slate-900 (black neutral)
- Icons: pastel tints (`text-emerald-300`, `text-rose-300`,
  `text-sky-300`, `text-indigo-300`, `text-teal-300`, `text-amber-400`)
- Meaning only: green up = good (sales), red up = bad (expenses),
  amber/red for alerts

### Files
- `/app/frontend/src/pages/DashboardPage.js` — rewritten
  (~420 lines; stat cards, nav cards, PriceMovement, BestVendor,
  AlertsCard, DeltaPill). Data sources: `/api/dashboard/summary`,
  `/api/prices/intelligence`, `/api/prices/vendor-comparison`.

### Verified
- Smoke test: row_sales/row_expenses rendered; row2 Orders/Procurement/Items
  rendered; Insights trio rendered; 6 colored delta indicators; prior
  heavy donut charts removed. ESLint clean.


## Milestone 20: Analytics Migration to Canonical-ID Joins — COMPLETE (2026-02-14)

### Goal
Migrate core analytics reads away from fragile raw-name grouping toward
canonical-identity grouping, so aliases / spacing / OCR noise roll up
into a single timeline whenever canonical linkage exists.

### Services / endpoints migrated
- `GET /api/prices/vendor-comparison`  (`VendorComparisonService`)
- `GET /api/prices/intelligence`       (price trends + alerts)
- `GET /api/items/{id}/price-history`  (`PriceHistoryService`)

`ProcurementDecisionEngine` already grouped by `canonical_product_id`
at ingest time — no migration needed; smoke-verified no regression.

### Identity Key Rule (enforced everywhere)
```
identity_group_key =
    "canon::<canonical_item_id>[::<variant_key>]"   if canonical linkage exists
                                                    (after one merge hop)
    otherwise
    "norm::<normalize_name(raw_name)>"              — never raw item_name
```

### Implementation
- **New: `services/identity_resolver.py`** — `CanonicalIndex` dataclass
  + `build_canonical_index(rid)` + `idx.resolve(item)` returning
  `(group_key, canonical_name, variant_key)`. Pure + tenant-scoped.
- **`routes/prices.py`** — both endpoints now call
  `build_canonical_index()` once per request, then iterate purchases
  bucketing by `idx.resolve()`. New `group_key` field exposed on
  vendor-comparison rows for transparent traceability.
- **`routes/items.py`** — `item_price_history` now matches on
  `group_key == "canon::<item_id>"` (prefix tolerates variant suffix)
  with name/alias fallback for legacy rows missing `canonical_item_id`.
- **`routes/purchases.py`** — fixed a pre-existing `KeyError` on alias
  docs that use the `alias` field (post-M19) instead of `alias_name`.

### Before / After (Vendor Comparison)
**Before** (raw-name keyed):
```python
alias_to_canonical[raw.lower()] = canonical_name
group = alias_to_canonical.get(raw.lower(), raw)  # ← falls back to RAW
item_vendor_prices[group][vendor].append(...)
```
Problem: "Shrimp 16-20 IQF", "shrimp 16-20 iqf", "SHRIMP16/20IQF" all
produced three separate rows because raw text leaked through the
fallback.

**After** (canonical-id keyed):
```python
idx = await build_canonical_index(rid)           # O(n) once
for p in purchases:
    for it in p["items"]:
        gkey, canon_name, _ = idx.resolve(it)     # O(1) per line
        item_vendor_prices[gkey][vendor].append(...)
```
All three raw variants collapse into `canon::<id>`, a single row with
the canonical display name.

### Validation delivered
1. **Before/after query logic** — shown above, plus `group_key`
   exposed on vendor-comparison response for user-visible proof.
2. **Historical trends aggregated at canonical level** — confirmed by
   the consolidation integration test (`test_analytics_consolidation_iter98.py`).
3. **Before/after consolidation example** — 3 OCR-noisy raw_names
   (`"Widget -xxx"`, `"W1dg3t-xxx"`, `"widget   xxx"`) linked to one
   canonical now yield exactly ONE vendor-comparison row and ≥3
   price-history records.
4. **Endpoints migrated**: vendor-comparison, price-intelligence,
   item-price-history.

### Guardrails honored (verified)
- **Identity confidence not weakened** — matcher thresholds from M19
  unchanged; analytics only READ the existing `canonical_item_id`.
- **Variants stay separate** — `variant_key` suffixed into group_key.
- **Tenant isolated** — `build_canonical_index(rid)` scopes every
  collection load by `restaurant_id`.
- **Backwards compat preserved** — historical rows without
  `canonical_item_id` still appear, grouped by normalized raw_name
  (not raw), plus the legacy name/alias fallback in
  `item_price_history`.
- **No procurement regression** — pytests + endpoint probe green.

### Tests — iteration_98.json (18/18 PASS + 26/26 M19 regression)
- `tests/test_identity_resolver.py` — 10 unit tests
- `tests/test_analytics_consolidation_iter98.py` — 1 end-to-end consolidation proof
- 8 additional live-HTTP verifications authored by testing agent

### Files
- Backend: `services/identity_resolver.py` (new),
  `routes/prices.py`, `routes/items.py`, `routes/purchases.py`.
- Tests: `tests/test_identity_resolver.py`, `tests/test_analytics_consolidation_iter98.py`.


## Milestone 19: Robust Identity, Canonical Linking & Smart Input — COMPLETE (2026-02-14)

### Goal
Unify item identity across the system: eliminate duplicates from OCR/spacing
noise, enforce a single source of truth (approved canonical items),
guide user input via system-approved suggestions, and prevent unsafe
automation — all while keeping handwritten OCR variability tolerable.

### Backend
- **`services/item_identity.py`** (new): `normalize_name`, `tokenize`,
  `jaccard`, `fuzzy_ratio`, `split_base_and_variant`. Pure functions.
- **`services/item_matcher.py`** (new): 6-tier matcher
  `exact → alias → normalized → token/fuzzy → memory`. Returns
  `MatchResult{canonical_item_id, variant_key, confidence, tier,
  token_score, fuzzy_score, candidates, needs_review, auto_linked}`.
  Stricter thresholds: `TOKEN_AUTO=0.85`, `FUZZY_AUTO=0.90`,
  `MARGIN=0.10`, `MEDIUM_FLOOR=0.70`. Suggested / archived canonicals
  are NEVER candidates.
- **`routes/item_autocomplete.py`** (new): `GET /api/items/autocomplete`
  returns approved canonicals + declared variants + saved aliases only.
- **`routes/invoice_items.py`** (new): explicit, user-controlled actions
  per invoice line — `POST /link`, `POST /promote`, `POST /match`,
  `GET /match-preview`. Auto-link only when matcher returns
  `auto_linked=True`.
- **`routes/purchases.py`**: new `_enrich_purchases_with_canonical`
  resolves `canonical_item_id` + `variant_key` at READ time, surfacing
  `canonical_name / variant_label / display_name`. Follows one merge
  hop. This delivers **automatic Canonical→Invoice propagation** with
  zero writes to purchase rows on canonical rename.
- **`core/models.py`**: `CanonicalItemVariant` + `variants` list on
  `CanonicalItemCreate`.

### Frontend
- **`components/SmartItemAutocomplete.js`** (new): reusable combobox.
  Queries `/api/items/autocomplete` on debounced input; arrow keys +
  enter + click. Source labelled (canonical / variant / alias).
  Advisory only — picks only fill the input + memoize identity; nothing
  mutates server-side until Save.
- **`components/InvoiceReviewDialog.js`**: `raw_name` input replaced by
  SmartItemAutocomplete. On save, PATCH first then — only if the user
  picked a suggestion — POST `/link` with canonical_item_id + variant_key.
  Row now shows `display_name` + `linked` + variant badges.
- **`pages/ItemsPage.js`**: Add/Edit dialog gains a Variants editor
  (`variants-editor`, `variant-add`, `variant-key-{i}`,
  `variant-label-{i}`, `variant-remove-{i}`). Variant chips render on
  item rows (`variants-chips-{id}`, `variant-chip-{id}-{key}`).

### Tests (all PASS — iteration_97.json)
- `tests/test_item_matcher.py` — 21 unit tests: normalization,
  jaccard/fuzzy, variant extraction, 6-tier matcher, auto-link
  guardrails (suggested/archived exclusion, variant-required-medium,
  competing candidates, OCR noise).
- `tests/test_identity_integration_iter97.py` — 5 live HTTP tests:
  autocomplete scope, explicit link, Canonical→Invoice propagation,
  match-preview non-mutating, variant-declared-without-raw-variant
  guardrail.

### Guardrails honored (verified end-to-end)
- **No auto-merge**, **no auto-create**: autocomplete never writes.
- **Invoice-text edits NEVER mutate canonical items** — PATCH item
  only writes purchase doc; `/link` is explicit and user-invoked.
- **Canonical edits DO propagate** automatically via read-time join
  (raw_name preserved untouched).
- **Stricter auto-link**: token≥0.85 AND fuzzy≥0.90 AND margin≥0.10 AND
  variant consistency. OCR-noisy inputs (e.g. "liv blue carb") resolve
  to MEDIUM (needs_review), not HIGH.
- **Approved-only suggestions**: autocomplete excludes suggested /
  archived / raw invoice text.

### Files
- Backend: `services/item_identity.py` (new), `services/item_matcher.py` (new),
  `routes/item_autocomplete.py` (new), `routes/invoice_items.py` (new),
  `routes/purchases.py` (enrich helper), `core/models.py` (variants),
  `server.py` (registration).
- Frontend: `components/SmartItemAutocomplete.js` (new),
  `components/InvoiceReviewDialog.js` (autocomplete + identity save flow),
  `pages/ItemsPage.js` (variants editor + chips).
- Tests: `tests/test_item_matcher.py`, `tests/test_identity_integration_iter97.py`.


## Milestone 18: Dashboard Minimalization — COMPLETE (2026-02-14)

### Goal
Turn the dashboard into a quick control center — no heavy data sections,
just primary actions + navigation + headline charts.

### Kept
- Top actions: **Add Expense**, **Sales**
- New secondary nav (nav-only, no preview): **Items**, **Orders**, **Procurement**
- Period filter (Year / Month) + Data Freshness indicator
- **Spending** donut chart (with category drill-through)
- **Sales** donut chart (with drill-down sheet)
- Drill-down Sheet (raw materials / salaries / other / sales)
- Empty-state banner with Seed Demo Data button

### Removed (clutter)
- "Compare Vendors" quick action
- "View Reports" quick action
- `ItemSearch` card ("Where Should I Buy?")
- `MarketInsights` card
- `BestOpportunityCard`
- `SmartMarketInsights` section

### Files
- `/app/frontend/src/pages/DashboardPage.js` — trimmed from 1043 → 624 lines.
  New `TopActions` (2 CTAs) and `SecondaryNav` (3 outline nav buttons)
  components with `data-testid` coverage (`quick-action-{i}`,
  `secondary-nav-{i}`, `data-nav-label`).

### Verified
- Smoke test: top_action_count=2, secondary_nav_count=3 (Items/Orders/Procurement),
  Spending + Sales cards render, removed sections confirmed absent.
- ESLint clean.


## Milestone 17: Traceability Loop Closure (Correction → Canonical) — COMPLETE (2026-02-14)

### Goal
Let users see exactly where each invoice-edit correction ended up in the
item catalog today, and give a subtle advisory hint when a newly-suggested
item is likely a duplicate of an existing approved one.

### Backend — `correction_memory.py`
- New helpers `_status_from_canonical()` and `_enrich_corrections_with_destination()`.
- Every correction row now carries `canonical_destination`:
  `{status, canonical_item_id, canonical_name, merged_from_name, merged_from_item_id}`.
- Status is derived from the current `canonical_items` doc the alias points to:
  - `approved` → live catalog entry
  - `suggested` → pending review
  - `merged` → sibling canonical with same `corrected_name` was merged into this id
  - `dismissed` → suggested + archived
  - `archived` → archived approved
  - `unlinked` → no alias found for `original_raw_name`
- Enrichment added to:
  - `GET /api/correction-memory`
  - `GET /api/corrections/by-vendor/{supplier_id}` (used by the UI)
  - `PATCH /api/corrections/{id}` return value
- Tenant-scoped throughout, `_id` excluded.

### Frontend — `CorrectionMemoryPage.js`
- New `DestinationCell` component (colored badge + clickable canonical link).
- New `Destination` column in the corrections table.
- Clicking a merged/approved/suggested destination navigates to
  `/items?highlight=<canonical_item_id>`.

### Frontend — `ItemsPage.js`
- `?highlight=<id>` support: scroll row into view, apply `ring-2
  ring-teal-500` ring, set `data-highlighted="true"`; ring fades after ~3.5s.
- Smart Duplicate Hint (advisory only, threshold 0.70 token Jaccard):
  - Runs on rendered `is_suggested` rows against a separately-fetched
    pool of approved items (`approvedItems`).
  - Renders `"Possible duplicate of "<Name>" (X% match)"` under the
    row name with `data-testid="duplicate-hint-<item.id>"`.
  - Click triggers **no** backend action — purely informational.

### Guardrails honored (verified)
- **Advisory only** — hint never calls /merge, /promote, or /dismiss
- **Approved-only matching pool** (no suggested↔suggested suggestions)
- **No OCR / procurement / correction-pipeline changes**
- **Tenant-scoped** throughout, `_id` never leaked

### Verified — iteration_96.json
- 8/8 backend pytests PASS (`test_correction_destination_iter96.py`)
- All 5 destination statuses observed against seeded data
- Frontend Destination badges + merged link clickthrough to
  `/items?highlight=<id>` renders the teal ring and scrolls into view
- Duplicate hint `"Possible duplicate of "Beef" (100% match)"` verified
  with zero side-effect API calls

### Files touched
- `/app/backend/routes/correction_memory.py` (enrichment helpers + route wiring)
- `/app/frontend/src/pages/CorrectionMemoryPage.js` (Destination column,
  DestinationCell, navigation)
- `/app/frontend/src/pages/ItemsPage.js` (Jaccard helpers, approvedItems
  state, duplicateHints memo, highlight effect, ring styling)
- `/app/backend/tests/test_correction_destination_iter96.py` (new)


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

## Milestone 16: Suggested Item Merge (Deduplication) — COMPLETE (2026-02-13)

### Backend — 1 new endpoint
- `POST /api/items/{iid}/merge` with body `{target_item_id}`:
  * 404 if suggested or target missing; 400 if source not suggested,
    target not approved / archived, or self-merge.
  * **Transfers aliases** from suggested → target (update_many on
    `canonical_item_id`). If a (target, alias) duplicate exists, increments
    existing alias's `usage_count` and drops the duplicate alias row.
  * **Adds the suggestion's own `name`** as an alias on the target
    (source="merge", usage_count=1) — unless already present.
  * **Marks suggestion** `is_merged=True`, `is_archived=True`,
    `merged_into_item_id`, `merged_at`, `merged_by_user_id/name`.
  * `correction_memory` is **NEVER touched** — rows remain readable.
  * Response: `{status, suggested_id, target (with refreshed aliases),
    aliases_transferred, aliases_deduped}`.
  * Audit log: `MERGE` event with transfer/dedup counts.

### Frontend — Items page
- New **Merge** button (indigo, `GitMerge` icon) on every suggested row,
  between Promote and Dismiss. testid `merge-item-{id}`.
- Two-step `MergeDialog` (testid `merge-dialog`):
  1. **Target picker**: amber context banner (`merge-context`), search input
     (`merge-search`), scrollable list of approved items
     (`merge-target-{id}`), empty state (`merge-target-empty`). **Next**
     button disabled until a target is chosen.
  2. **Confirmation**: plain-English summary with 4 guarantees:
     "suggestion's name + aliases become aliases on existing item",
     "correction memory rows are preserved",
     "no duplicate canonical item will be created",
     "suggestion is archived (non-destructive)". **Back** and **Confirm merge**.
- Success toast reports aliases transferred / deduped.

### Guardrails honored (all verified live)
- **No auto-merge** — user must pick target + confirm
- **No OCR / parsing changes**
- **No procurement logic changes**
- **No destructive deletes** — aliases transferred (never dropped unless
  they already existed on target, in which case usage_count merges)
- **Tenant-scoped** throughout
- `correction_memory` snapshot count unchanged after merge

### End-to-End Verified (live curl + Playwright)
```
Suggested: "Shrimp IQF 16/20 Merge-1776922647"
→ POST /items/{sid}/merge  body: {target_item_id: <Shrimp 16-20 Count IQF id>}
✓ status: "merged"
✓ target.aliases: ["SHRIMP 16-20 IQF", "Shrimp IQF 16/20 Merge-1776922647"]
✓ approved count BEFORE/AFTER: 125/125 — NO duplicate canonical created
✓ suggestion marked is_merged=true, is_archived=true,
  merged_into_item_id=<target>, merged_by_name="Demo User"
✓ correction_memory count unchanged (4 → 4)
```

### Screenshots captured (5)
- `merge_before.png` — suggested row with Promote / Merge / Dismiss buttons
- `merge_picker.png` — searchable target list ("SHRIMP 16-20 IQF" selected)
- `merge_confirm.png` — confirmation step with 4 guarantees
- `merge_after.png` — Approved tab, 3 canonical Shrimp items (duplicate gone)
- `merge_aliases.png` — Alias dialog on target post-merge

### Files
- `/app/backend/routes/items.py` — `MergeSuggestedBody` model + `/merge` endpoint + Pydantic import
- `/app/frontend/src/pages/ItemsPage.js` — Merge button, MergeDialog (target picker + confirm step), `openMergeDialog` / `confirmMerge` handlers


## Milestone 15: Suggested Catalog Governance — COMPLETE (2026-02-13)

### Goal
Add a safe review layer for suggested canonical items so user edits keep
learning into the catalog without polluting it.

### Backend — 2 new endpoints + extended filter
- `POST /api/items/{iid}/promote` — sets `is_suggested: false`, stamps
  `promoted_at`, `promoted_by_user_id`, `promoted_by_name`. Aliases untouched.
  400 if item is not suggested, 404 if missing.
- `POST /api/items/{iid}/dismiss` — soft-archive via `is_archived: true`
  (+ aliases archived with same flag). 400 if not suggested.
- `GET /api/items?status={suggested|approved|archived}` — filter by state.
  Default listing now EXCLUDES archived items (keeps history intact but hides noise).
- All tenant-scoped. All audit-logged (`PROMOTE` / `DISMISS` actions).

### Frontend — Items page refinements
- New **Status filter tab strip**: All · Approved · **Suggested** (with count pill
  when not selected). data-testids: `filter-status-{all|approved|suggested}`,
  `filter-status-suggested-count`.
- Suggested rows visually distinct:
  * amber row background tint (`bg-amber-50/60`)
  * Sparkles icon badge (instead of letter initial)
  * **SUGGESTED** uppercase pill badge (testid `badge-suggested-{id}`)
  * Origin hint line: *"Suggested from a user edit"* (testid `origin-hint-{id}`)
- Per-row actions on suggested items:
  * **Promote** (teal, CheckCircle2) → testid `promote-item-{id}`
  * **Dismiss** (outline, XCircle) → testid `dismiss-item-{id}`
  * Dismiss asks for confirm (window.confirm mentions aliases archived / correction history intact).

### Rules honored
- **Promote preserves aliases** — verified live: after promoting
  "Shrimp 16-20 Count IQF", the alias `SHRIMP 16-20 IQF` remained attached.
- **Dismiss preserves correction_memory** — verified: after dismissing
  "E2E Regression Item ...", the correction row still returns from
  `/api/correction-memory`.
- Aliases are **archived, not deleted**, on dismiss — past records stay readable.
- Tenant-scoped throughout.
- No OCR/parsing changes · No auto-merge · No auto-promotion · No procurement changes.

### End-to-End Verified (live)
```
Initial: 3 suggested items in Suggested tab
→ POST /items/{id}/promote  "Shrimp 16-20 Count IQF"   HTTP 200
  → moves out of Suggested, visible in Approved, is_suggested:false,
    aliases intact (SHRIMP 16-20 IQF preserved)
→ POST /items/{id}/dismiss  "E2E Regression Item ..."  HTTP 200
  → hidden from default /items, visible at /items?status=archived,
    correction_memory row for same corrected_name STILL present
```

### Files
- `/app/backend/routes/items.py` — added `/promote`, `/dismiss`, `status=` filter, archived exclusion
- `/app/frontend/src/pages/ItemsPage.js` — status-filter tabs, Suggested badge + origin hint, Promote/Dismiss buttons


## Milestone 14: Correction Pipeline v3 (Edit → Memory → Catalog) — COMPLETE (2026-02-13)

### Gap identified
- Inline PATCH `/purchases/{pid}/items/{idx}` already called `save_correction`
  on `raw_name` changes — so Correction Memory *was* being written, but:
  1. **Records lacked structured metadata** (`source`, `variant`, `unit`, `category`).
  2. **NO catalog linkage** — `canonical_items` / `item_aliases` were never touched
     when a user corrected a name. The system did not learn into the Items/Materials
     catalog.

### What was implemented (non-destructive, lightweight)
1. **Correction record enrichment** — `save_correction()` now stores first-class
   `source` (default `"user_edit"`), `variant`, `unit`, `category` fields.
2. **New `services/catalog_linkage.py`** — given a corrected_name:
   * **exact case-insensitive** match on `canonical_items.name` → returns `"linked"`
   * **contains-match** (when name ≥ 4 chars) → returns `"linked"`
   * **no match** → creates a new `canonical_items` row with
     `is_suggested: true` + `suggested_source: "user_edit"` → returns `"suggested"`.
   * On both paths: upserts `item_aliases` row (alias → canonical_item_id),
     incrementing `usage_count` on repeats (never duplicates).
3. **Wired into both** `PATCH /purchases/{pid}/items/{idx}` and
   `PUT /purchases/{pid}`. Wrapped in try/except so linkage failure never
   breaks item save.
4. **PATCH response** now includes `catalog_linkage: {action, canonical_item_id, canonical_name}`.
5. **Frontend toast** in `InvoiceReviewDialog` surfaces the outcome:
   * `linked` → `Linked to catalog: {name}` (success)
   * `suggested` → `Added "{name}" as a suggested item — review in Items` (info)
6. **Non-destructive**: we never overwrite existing canonical items. Suggested
   entries carry `is_suggested: true` so UI can badge/filter if desired.

### Rules honored
- Correction Memory stores only user-driven edits (`source: "user_edit"`).
- Not all item edits become corrections — only `raw_name` changes.
  Price/qty inline edits do NOT create a correction row (unchanged).
- Parsing layer (`normalize_item`, OCR extraction) is unchanged.

### End-to-End Verified (live)
1. PATCH item[0].raw_name = "E2E Regression Item ..." (novel) →
   response `catalog_linkage: {action: "suggested", canonical_item_id: <new uuid>}`.
   * `correction_memory` has a new row with `source="user_edit"`, `unit="LB"`,
     `original_raw_name="CHKN BRST BNLS 6OZ"`, `corrected_name="E2E Regression Item ..."`.
   * `canonical_items` has a new row with `is_suggested: true`,
     `suggested_source: "user_edit"`, plus an `item_aliases` row mapping the
     original raw_name to the new canonical id.
2. PATCH item[1].raw_name = "Beef" (exists in catalog) →
   response `catalog_linkage: {action: "linked", canonical_item_id: <existing>}`.
   * No new canonical_item created; a single `item_aliases` row is added
     linking the raw_name to the existing "Beef" canonical id.

### Testing — all green
- 6 new unit tests in `test_catalog_linkage.py` (exact-CI match, contains match,
  suggested path creates new canonical, alias usage_count increments on repeat,
  empty corrected_name skipped, tenant isolation).
- Full regression: 53 passed, 1 skipped across `test_catalog_linkage`,
  `test_correction_memory_v2`, `test_correction_memory_ui`,
  `test_procurement_audit`, `test_procurement_inbox_outcome`, `test_orders_api`.

### Files
- /app/backend/services/catalog_linkage.py (new)
- /app/backend/services/correction_memory.py (save_correction now accepts source/variant/unit/category)
- /app/backend/routes/purchases.py (PATCH + PUT endpoints call catalog linkage; PATCH response carries catalog_linkage)
- /app/frontend/src/components/InvoiceReviewDialog.js (toast surfaces linkage outcome)
- /app/backend/tests/test_catalog_linkage.py (new — 6 tests)


## Milestone 13: Decision Flow Alignment (Insight → Order) — COMPLETE (2026-02-13)

### Goal
Turn the daily flow into: **invoice → insight → decision → suggestion → order**
with the user always in control. No automation introduced.

### 1) Updated Procurement Command Center
- **Center panel action label**: `Save Suggestion` → **"Save Insight"** (non-executional,
  advisory); "Review Later" unchanged. data-testids updated:
  `decision-save-insight-{cpid}` / `decision-review-later-{cpid}`.
- **Right panel → Triage**: replaces Saved + To Review tabs with 3 mutually
  exclusive triage categories:
  * **Needs Review** (medium-confidence recs not eligible for center)
  * **Low Confidence** (`confidence_level === 'low'`)
  * **Missing Data** (`monitor_only` OR `obs < 3` OR `!confidence_level`)
  data-testids: `right-tab-needs-review`, `right-tab-low-confidence`, `right-tab-missing-data`.
  Panel title renamed to **"Triage"**.
- **Saved / Acted On moved out** of Command Center into `/procurement/history`
  (ProcurementInboxPage). Header link `cc-history-link` exposes a live saved-count badge.

### 2) Updated wording
Center panel buttons: **Save Insight** · **Review Later** (no Accept/Approve/Execute).
Info bar: "Save Insight opens the acknowledgment modal. Review Later is session-only —
advisory only, no purchase is executed."

### 3) Orders smart hints (item-line, advisory-only)
Each order line now shows up to 3 inline hint pills computed from the
`/items/{id}/price-history` records (no new backend call):
- **preferred vendor** — slate pill · Store icon — last-known vendor (`hint-preferred-{id}`)
- **suggested qty** — teal pill · Lightbulb icon — median of last 5 recorded quantities;
  clicking the pill fills the quantity input (user-triggered, never auto) (`hint-suggested-qty-{id}`)
- **better price** — amber pill · Sparkles icon — appears only when another vendor
  in history has an avg price >2% cheaper than the latest vendor. Opens
  `/procurement?panel=decisions` in a new tab. (`hint-better-price-{id}`)

### 4) Smart Influence Rule (enforced)
- Hints are **displays + one-click fills**; never auto-apply.
- NO auto-select vendor · NO auto-fill final qty · NO auto-generate PO.
- All writes still go through the user pressing Save Draft / Submit.

### Orders page flow (proposed)
```
Open Orders → (optional) "Re-order last week (Smart)" preloads item rows
           → user picks/adds items from Item Catalog
           → each line displays: preferred vendor · suggested qty · better-price hint
           → user types/accepts quantities, optional vendor
           → "Save as Draft" OR "Mark as Submitted" (no external execution)
```

### How Procurement links into Orders (without automation)
- **Pull-based**: the "better price" hint shows only if historical data supports
  it; it carries a link to `/procurement?panel=decisions` so the user can see
  the full evidence, then manually choose what to do. Decision is never
  written into the order.
- **Orders banner** carries a persistent link back to Procurement
  (`orders-procurement-link`).
- **Procurement footer** carries a forward link to Orders (`cc-orders-link`).

### Testing
- Lint clean across all touched/new files.
- Live Playwright verified: Save Insight buttons, Triage 3 tabs, no legacy
  Saved/Acted-On controls on Command Center, forbidden-words scan clean,
  `/procurement/history` breadcrumb + page renders, Orders line shows
  `preferred` + `suggested qty` hints correctly. Backend `git status` clean
  (only an untracked unrelated pytest log file). All 76/76 backend regression
  tests from iter 94 still valid — no backend file modified.

### Files
- /app/frontend/src/pages/ProcurementCommandCenterPage.js (wording + Triage panel)
- /app/frontend/src/pages/ProcurementInboxPage.js (new title + breadcrumb)
- /app/frontend/src/pages/OrdersPage.js (smart-hints helper + inline UI)
- /app/frontend/src/App.js (new `/procurement/history` route)


## Milestone 12: Command Center Advisory-Only Polish (2026-02-13)

### Refinements on top of Milestone 10
- **Advisory-only button wording** on Decision Engine cards:
  * `Accept` → **"Save Suggestion"** (teal · Sparkles icon)
  * `Dismiss` → **"Review Later"** (outline · Clock icon)
  * data-testids updated: `decision-save-suggestion-{cpid}` / `decision-review-later-{cpid}`
  * Info bar copy: "Save Suggestion opens the acknowledgment modal. Review Later
    is session-only — advisory only, no purchase is executed."
- **Forbidden execution verbs banned** on the Decision Engine surface:
  no "Accept", "Approve", "Execute" in user-visible text.
- **Intent-preserving redirects** from legacy routes now carry `?panel=`:
  | Legacy | → |
  |---|---|
  | `/purchase-decisions`, `/procurement/smart-purchases` | `/procurement?panel=decisions` |
  | `/price-intelligence`, `/procurement/price-insights`  | `/procurement?panel=market` |
  | `/procurement-decisions`, `/procurement/decisions`    | `/procurement?panel=decisions` |
  | `/procurement/inbox`, `/procurement/suggestions`      | `/procurement?panel=suggestions` |
- **Panel focus via URL**: `/procurement?panel=market|decisions|suggestions`
  adds subtle teal focus ring on the chosen panel + scrolls it into view on
  mobile. Exposed as `data-panel-focus="true|false"` on each
  `panel-{name}-wrap` element for deep-link robustness.
- **Zero backend changes** — `git status backend/` clean except an untracked
  pytest log file. All APIs reused verbatim.

### Reused APIs (unchanged list)
- `GET /api/price-intelligence/products`
- `GET /api/procurement/recommendations`
- `GET /api/procurement/suggestions?status=saved_for_review`
- `PATCH /api/procurement/suggestions/{id}/outcome`
- `POST /api/procurement/events` + `POST /api/procurement/suggestions`

### Files
- /app/frontend/src/pages/ProcurementCommandCenterPage.js (wording + panel focus)
- /app/frontend/src/App.js (8 legacy redirects now carry `?panel=`)


## Milestone 11: Expenses — Dedicated Sub-Pages (2026-02-13)

### Goal
Make each expense type feel like its own workspace — separate route,
themed header, category-specific CTA — not just a tab inside a shared screen.

### Routes
| URL | Page |
|---|---|
| `/expenses`                  | `<Navigate to="/expenses/raw-materials" replace/>` |
| `/expenses/raw-materials`    | `RawMaterialsPage` (teal accent) |
| `/expenses/salaries`         | `SalariesPage` (blue accent) |
| `/expenses/other`            | `OtherExpensesPage` (amber accent) |

### Visual Identity (subtle — NOT full-page theming)
Applied only to: breadcrumb current segment · title · icon badge · accent
strip · primary "+ Add" button.

| Page | Theme | Icon | CTA label |
|---|---|---|---|
| Raw Materials  | teal  | Beef   | `+ Add Raw Material` |
| Salaries       | blue  | Users2 | `+ Add Salary` |
| Other Expenses | amber | Wrench | `+ Add Expense` |

### Implementation
- `pages/expenses/ExpenseHeader.js` — shared header strip (breadcrumb +
  themed title + icon badge + accent bar).
- `pages/expenses/{RawMaterials|Salaries|OtherExpenses}Page.js` — thin
  wrappers that import the existing `{RawMaterials|Salaries|OtherExpenses}Tab`
  exports from `pages/ExpensesPage.js`. Zero duplication of business logic.
- `ExpensesPage.js` now just `<Navigate to="/expenses/raw-materials"/>` so any
  stale import still works.
- Shared table structure / search / date filters / status filter all
  preserved inside the tab components (unchanged).
- Cross-category tabs REMOVED from the inner view — each page is category-only.
- Sidebar children updated to point at new canonical paths.
- `DashboardPage` drill-down updated to navigate to the new dedicated routes
  instead of `/expenses` with `state.tab`.

### Testing
- Lint clean across all 5 touched/new files.
- Live Playwright verified: `/expenses` redirect, all 3 themed headers +
  breadcrumbs, all 3 contextual Add button labels, absence of sibling-tab
  row inside each page, sidebar children all resolve.
- ZERO backend changes — no regression risk on any service.

### Files
- /app/frontend/src/pages/expenses/ExpenseHeader.js (new)
- /app/frontend/src/pages/expenses/RawMaterialsPage.js (new)
- /app/frontend/src/pages/expenses/SalariesPage.js (new)
- /app/frontend/src/pages/expenses/OtherExpensesPage.js (new)
- /app/frontend/src/pages/ExpensesPage.js (exports Tab components; default is Navigate)
- /app/frontend/src/App.js (3 new routes + /expenses redirect)
- /app/frontend/src/components/Layout.js (sidebar children point to new paths)
- /app/frontend/src/pages/DashboardPage.js (drill-down → new routes)


## Milestone 10: Procurement Command Center (3-Panel UI Consolidation) — COMPLETE (2026-02-13)

### Goal
Unify fragmented Procurement UI into ONE operational screen. STRICT UI-only
consolidation — zero backend changes.

### Navigation (final)
- `Procurement` is now a **single sidebar link** (not a group) → `/procurement`
- 8 legacy routes all `<Navigate to="/procurement" replace/>`:
  `/purchase-decisions`, `/procurement/smart-purchases`,
  `/price-intelligence`, `/procurement/price-insights`,
  `/procurement-decisions`, `/procurement/decisions`,
  `/procurement/inbox`, `/procurement/suggestions`
- Deep-link escape hatches kept for old bookmarks:
  `/procurement/legacy/decisions|inbox|price-intelligence|smart-purchases`
  (NOT linked from nav; render the original full pages directly.)

### Command Center Layout
```
┌──────────────┬─────────────────────────┬──────────────┐
│ Market View  │   Decision Engine       │ Suggestions  │
│ (~25%)       │   (~50%, critical)      │ (~25%)       │
├──────────────┼─────────────────────────┼──────────────┤
│ Anomalies /  │ High-confidence cards   │ Saved tab    │
│ Alerts       │ ONLY:                   │  - Ignore    │
│              │   • confidence ≥ 0.80   │  - Acted on  │
│ Top Movers   │   • observations ≥ 3    │              │
│ w/ mini SVG  │   • switch_vendor       │ To review    │
│ sparklines   │     OR renegotiate      │  - low conf  │
│              │   • MAX 7 cards         │  - monitor   │
│              │                         │  - Promote   │
│              │ Per card:               │    (opens    │
│              │  • product + unit       │    ack modal)│
│              │  • current → recommended│              │
│              │  • Δ$ and Δ%           │              │
│              │  • 1-line reason        │              │
│              │  • action pill          │              │
│              │  • risk + confidence    │              │
│              │  • View details / Dismiss / Accept     │
└──────────────┴─────────────────────────┴──────────────┘
```

### Reused APIs (zero new endpoints)
- `GET  /api/price-intelligence/products`
- `GET  /api/procurement/recommendations`
- `GET  /api/procurement/suggestions?status=saved_for_review`
- `PATCH /api/procurement/suggestions/{id}/outcome`  (acted_on / not_pursued)
- `POST /api/procurement/events` · `POST /api/procurement/suggestions`
  (via reused `PurchaseSuggestionModal`)

### Button Semantics (strict)
- **Accept** → opens existing `PurchaseSuggestionModal` (requires acknowledgment
  checkbox). NO auto-execute.
- **Dismiss** → session-local `Set` state. NO server mutation. Reload restores.
- **View details** → modal with Current / Best-alt / 3-way deltas / Evidence /
  Uncertainty / action pill + risk + confidence badges.
- **Promote (right panel)** → same as Accept (opens acknowledgment modal).
- **Ignore (right panel)** → PATCH `outcome_type=not_pursued` with optional note.
- **Acted on (right panel)** → PATCH `outcome_type=acted_on`.

### Smart Re-order on Orders page
- `smart-reorder-btn` visible only when orders already exist.
- Preseeds `CreateOrderModal` lines from most recent order's `item_ids`.
- Quantities **start at 0** (user must fill). Vendor field stays empty.
- `orders-procurement-link` in info banner: "Better price available? View Procurement →".
- NO auto-application of Procurement recommendations. NO "apply/auto-order/Create PO" wording.

### Testing — 100% PASS (iter 94)
- Backend: 76 passed + 1 pre-existing skip. **`git diff /app/backend/` clean.**
- Frontend: Playwright verified all 8 redirects, 3 panels visible, 2 cards
  within cap + threshold gate, View details modal, session-only dismiss
  (restored on reload), saved/review tabs, ignore flow with PATCH +
  toast, smart-reorder qty=0 + no vendor, 4/4 legacy escape hatches render.

### Files
- /app/frontend/src/pages/ProcurementCommandCenterPage.js (new)
- /app/frontend/src/App.js (routes: /procurement → CC; 8 legacy → Navigate)
- /app/frontend/src/components/Layout.js (Procurement group → single link)
- /app/frontend/src/pages/OrdersPage.js (smart-reorder-btn + preseedItemIds)
- UNCHANGED reused: `components/procurement/ProcurementUI.js`,
  `components/procurement/PurchaseSuggestionModal.js`.


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
