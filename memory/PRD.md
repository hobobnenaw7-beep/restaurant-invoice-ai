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
- [x] Raw Materials: pack_weight, unit dropdown (LB/KG/OZ/EA/CS/BX/GAL/L/BAG/PK), normalized_unit_price (March 29, 2026)
- [x] Raw Materials: ALL computed values (line total, $/unit, subtotal, invoice total) are strictly read-only (March 29, 2026)
- [x] Salaries: CRUD
- [x] Other Expenses: CRUD with OCR, fixed subcategories

### Sales
- [x] Full CRUD with OCR upload

### OCR & Document Extraction (March 17, 2026)
- [x] Real OCR via OpenAI GPT-5.2 Vision (NOT MOCKED)
- [x] Multi-page PDF support (up to 5 pages)
- [x] Excel/CSV parsing with intelligent column mapping
- [x] Image upload support (JPEG, PNG, WebP)
- [x] Post-processing validation: auto-fills missing qty, unit_price, total
- [x] Better prompts for accurate extraction
- [x] Support in both Expenses (Raw Materials) and Sales forms
- [x] Image preprocessing: auto-rotate, deskew, crop margins, contrast, noise reduction (March 29, 2026)
- [x] Multi-page classification: header/line_items/totals/terms per page (March 29, 2026)
- [x] Page-type-aware extraction prompts with priority rules (March 29, 2026)

### Multi-Image Document Upload (March 23, 2026)
- [x] Frontend sends files[] as multipart/form-data array
- [x] Backend LLM handles deduplication of overlapping receipts

### Vendor Pattern Learning
- [x] /api/receipts/learn endpoint for building vendor_patterns

### UI/UX
- [x] Event bus for instant cross-component sync
- [x] ConfirmDeleteDialog (styled) globally
- [x] ConfirmSaveDialog showing vendor, date, total before save
- [x] Read-only auto-calculated totals

### Real Invoice Analysis (March 29, 2026)
- [x] Analyzed real invoices from US Foods, Performance Foodservice, Sysco
- [x] Identified key data fields: item_code, raw_name, qty, pack_size (composite), unit, unit_price, extended_price, category
- [x] Documented pack size complexity: "10/4 LB" = 10 packs × 4 lb = 40 lb/case
- [x] Identified standardization challenges across suppliers

## Backlog

### P0
- Phase 1 manual input improvements: pack size text field, vendor item autocomplete, keyboard tab flow
- Backend refactoring: break down server.py (~3600+ lines) into modular route files

### P1
- AI Chat Assistant Page Polish: improve UX of floating assistant
- Core Workflow Polish: review and harden all main flows
- Add OCR/Image Upload support to Salaries tab

### P2
- Phase 2: pack size parsing engine, normalized $/LB computation, vendor price comparison dashboard
- Build Item Normalization UI (mapping raw item names to canonical items)
- Enhance Vendor/Item CRUD (edit purchases, more filters)

## Key DB Collections
- `purchases`, `sales`, `salaries`, `other_expenses`
- `vendor_patterns`: prompt hints, typical items per vendor
- `uploaded_receipts`: file metadata, raw OCR text
- `receipt_extractions`: parsing results with method tracking

## Key API Endpoints
- `POST /api/upload/extract` — Multi-file OCR with preprocessing + page classification
- `POST /api/upload/parse-excel` — Excel/CSV parsing
- `POST /api/receipts/learn` — Vendor pattern learning
- `GET /api/dashboard/summary` — With year/month filters
- CRUD: `/api/purchases`, `/api/sales`, `/api/salaries`, `/api/other-expenses`
