# Restaurant Accountant AI — PRD

## Original Problem Statement
Full-stack restaurant accounting application with AI-powered OCR for invoice extraction, expense tracking, sales reporting, and vendor management.

## Core Architecture
- **Frontend:** React + TailwindCSS + Shadcn UI
- **Backend:** FastAPI + MongoDB
- **OCR:** OpenAI GPT-5.2 via Emergent LLM Key
- **Event Bus:** `dataEvents.js` for cross-component sync

## What's Been Implemented

### Authentication
- [x] JWT-based login/register with demo account (demo@test.com / testpassword)

### Dashboard
- [x] Summary cards, donut charts with year/month filters
- [x] Drill-down navigation to full expense/sales pages

### Expenses (3 tabs)
- [x] Raw Materials: full CRUD, upload/extract, duplicate detection
- [x] Raw Materials: pack_size text field, server-side parsing with strict validation
- [x] Raw Materials: $/LB ONLY computed when parsed AND unit is LB or OZ
- [x] Raw Materials: ALL computed values strictly read-only
- [x] Salaries: CRUD
- [x] Other Expenses: CRUD with OCR, fixed subcategories

### Sales
- [x] Full CRUD with OCR upload

### OCR & Document Extraction
- [x] Real OCR via OpenAI GPT-5.2 Vision, multi-page PDF (up to 5 pages)
- [x] Image preprocessing: auto-rotate, deskew, crop margins, contrast, noise reduction
- [x] Multi-page classification & page-type-aware extraction
- [x] Pack size extracted as verbatim text and parsed server-side

### Data Standardization (Phase 2)
- [x] Pack size parser: 18+ formats with strict validation, 22/22 unit tests
- [x] Parser coverage expansion: OCR artifacts (BAG50, BX24/12, spaced slashes)
- [x] Normalization audit: all 6 rules verified safe, zero false positives

### Vendor Price Comparison Dashboard (March 29, 2026)
- [x] `GET /api/vendor-comparison/normalized` — strict $/LB comparison
- [x] Only `normalized_price_per_lb > 0` AND `pack_unit ∈ {LB, OZ}` items
- [x] Conservative exact-match grouping by default
- [x] `match_source` flag: "exact" | "user_confirmed" on every group
- [x] `raw_names_in_group` shows all linked names for confirmed groups
- [x] Frontend: stat cards, search, filters (All/Multi-Vendor/Single/Confirmed Links)
- [x] BEST badge, spread %, Confirmed badge on merged groups

### Manual/Assisted Item Matching (March 29, 2026)
- [x] `item_mappings` MongoDB collection for confirmed links
- [x] CRUD: `GET/POST/PUT/DELETE /api/item-mappings`
- [x] `GET /api/item-mappings/suggestions` — word-overlap (Jaccard) similarity
- [x] Suggestions exclude already-mapped items, require user confirmation
- [x] Confirmed mappings merge comparison groups, never auto-merge
- [x] Frontend: "Manage Item Matches" toggle panel
- [x] Suggestion cards with editable canonical name + "Confirm Link" button
- [x] Confirmed Mappings list with delete capability
- [x] Fully tested: 24 backend + 10 frontend tests (100% pass rate)

### Decision-Making Layer (March 29, 2026)
- [x] Quick Decisions summary card at page top — multi-vendor items sorted by savings opportunity
- [x] Each decision: "Buy from X to save Y% vs Z" with exact $/LB and per-pound savings
- [x] Decision banner inside each expanded multi-vendor group
- [x] "Best Deal" badge (green) on cheapest vendor row
- [x] "High Price" warning badge (red) on most expensive vendor row
- [x] Spread color-coded: red >=15%, amber 8-15%, green <8%
- [x] $/LB column: green for best, red for worst
- [x] Signal column in table for visual badges
- [x] No badges/banners for single-vendor groups (nothing to compare)
- [x] Deterministic logic only — no trends, no charts
- [x] Fully tested: 12/12 frontend tests (100% pass rate)

### UI/UX
- [x] Event bus for instant cross-component sync
- [x] ConfirmDeleteDialog and ConfirmSaveDialog
- [x] Read-only computed fields with visual distinction

## Backlog

### P0
- Backend refactoring: break down server.py (~3800+ lines) into modular route files

### P1
- AI Chat Assistant Page Polish
- Core Workflow Hardening
- Add OCR/Image Upload support to Salaries tab

### P2
- Client-side pack size preview during entry
- Vendor-specific OCR preprocessing
- Fix bcrypt `__about__` warning in backend startup logs

## Key DB Schema

### purchases.items
```
{
  raw_name, quantity, pack_size, unit_price, total,
  pack_size_raw, pack_parse_status, packs_per_case,
  weight_per_pack, pack_unit, total_case_weight,
  normalized_price_per_lb
}
```

### item_mappings
```
{
  id, restaurant_id, canonical_name,
  mapped_names: [str],  // uppercase normalized
  created_at, updated_at
}
```

## Key API Endpoints
- `POST /api/upload/extract` — OCR with preprocessing
- `POST /api/purchases` — Create purchase with pack size enrichment
- `GET /api/vendor-comparison/normalized` — Strict $/LB comparison with mappings
- `GET/POST/PUT/DELETE /api/item-mappings` — CRUD for confirmed item links
- `GET /api/item-mappings/suggestions` — Similarity suggestions
