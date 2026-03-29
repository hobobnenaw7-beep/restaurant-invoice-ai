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
- [x] Raw Materials: pack_size text field (type what you see: "10/4 LB", "BAG 50 LB", "150 EA")
- [x] Raw Materials: Server-side pack size parsing → packs_per_case, weight_per_pack, pack_unit, total_case_weight
- [x] Raw Materials: Normalized $/LB auto-computed (unit_price / total_case_weight) for weight-based items
- [x] Raw Materials: ALL computed values (line total, case weight, $/LB, subtotal, invoice total) are strictly read-only
- [x] Salaries: CRUD
- [x] Other Expenses: CRUD with OCR, fixed subcategories

### Sales
- [x] Full CRUD with OCR upload

### OCR & Document Extraction
- [x] Real OCR via OpenAI GPT-5.2 Vision
- [x] Multi-page PDF support (up to 5 pages)
- [x] Image preprocessing: auto-rotate, deskew, crop margins, contrast, noise reduction
- [x] Multi-page classification: header/line_items/totals/terms per page
- [x] Page-type-aware extraction prompts with priority rules
- [x] Pack size extracted as text (verbatim from invoice) and parsed server-side
- [x] Excel/CSV parsing with intelligent column mapping
- [x] Tested on real invoices: US Foods, PFG, Sysco PDFs

### Data Standardization (Phase 2 — March 29, 2026)
- [x] Pack size parser: supports 18+ formats (N/N UNIT, WORD N UNIT, N UNIT, N#, etc.)
- [x] Case weight computation: packs_per_case × weight_per_pack
- [x] Normalized $/LB: unit_price / total_case_weight (weight-based only)
- [x] Both raw and computed values stored in DB
- [x] Canonical unit mapping (LBS→LB, KGS→KG, OUNCE→OZ, etc.)
- [x] Weight-to-LB conversion factors for cross-unit normalization

### Multi-Image Document Upload
- [x] Frontend sends files[] as multipart/form-data array
- [x] Backend LLM handles deduplication of overlapping receipts

### Vendor Pattern Learning
- [x] /api/receipts/learn endpoint for building vendor_patterns

### UI/UX
- [x] Event bus for instant cross-component sync
- [x] ConfirmDeleteDialog (styled) globally
- [x] ConfirmSaveDialog showing vendor, date, total before save
- [x] Read-only auto-calculated totals (line totals, subtotal, invoice total, case weight, $/LB)

## Backlog

### P0
- Backend refactoring: break down server.py (~3600+ lines) into modular route files

### P1
- Vendor price comparison dashboard (uses normalized $/LB data)
- AI Chat Assistant Page Polish
- Core Workflow Hardening
- Add OCR/Image Upload support to Salaries tab

### P2
- Client-side pack size preview (show Case Wt and $/LB during entry before save)
- Build Item Normalization UI (mapping raw item names to canonical items)
- Vendor-specific OCR preprocessing
- Enhance Vendor/Item CRUD (edit purchases, more filters)

## Key DB Collections
- `purchases`: items now include pack_size_raw, packs_per_case, weight_per_pack, pack_unit, total_case_weight, is_weight_based, normalized_price_per_lb
- `sales`, `salaries`, `other_expenses`
- `vendor_patterns`: prompt hints, typical items per vendor
- `uploaded_receipts`: file metadata, raw OCR text

## Key API Endpoints
- `POST /api/upload/extract` — Multi-file OCR with preprocessing + page classification + pack size enrichment
- `POST /api/purchases` — Creates purchase with server-side pack size parsing
- `PUT /api/purchases/{pid}` — Updates purchase with server-side pack size parsing
- `GET /api/dashboard/summary` — With year/month filters
