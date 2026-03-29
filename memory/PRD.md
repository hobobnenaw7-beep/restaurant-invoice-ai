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
- [x] Raw Materials: Server-side pack size parsing with strict validation
- [x] Raw Materials: `pack_parse_status` field: "parsed", "failed", "not_applicable"
- [x] Raw Materials: $/LB ONLY computed when status=parsed AND unit is LB or OZ (strict rule)
- [x] Raw Materials: Failed parses → null computed fields, raw preserved, warning logged
- [x] Raw Materials: ALL computed values (line total, case weight, $/LB, subtotal, invoice total) strictly read-only
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
- [x] Pack size extracted as verbatim text and parsed server-side with validation
- [x] Excel/CSV parsing with intelligent column mapping

### Data Standardization (Phase 2 — March 29, 2026)
- [x] Pack size parser: 18+ formats with strict validation
- [x] Case weight: packs_per_case × weight_per_pack (only when parsed)
- [x] Normalized $/LB: ONLY for LB and OZ units (strict — no KG, GAL, EA, CT, PK)
- [x] pack_parse_status tracking per item
- [x] All failed parses logged with PACK_PARSE_FAILED warnings
- [x] Both raw and computed values stored; null when uncertain
- [x] Real invoice validation: US Foods (5/14 $/LB), Sysco (9/12), PFG (0/6) — zero false positives

### UI/UX
- [x] Event bus for instant cross-component sync
- [x] ConfirmDeleteDialog and ConfirmSaveDialog
- [x] Read-only computed fields with visual distinction (gray bg for computed, teal for $/LB, red tint for failed parse)

## Backlog

### P0
- Backend refactoring: break down server.py (~3600+ lines) into modular route files
- Improve parser coverage for OCR artifacts (BAG50→BAG 50, 1 25 LB→1/25 LB)

### P1
- Vendor price comparison dashboard (uses normalized $/LB)
- AI Chat Assistant Page Polish
- Core Workflow Hardening
- Add OCR/Image Upload support to Salaries tab

### P2
- Client-side pack size preview during entry
- Build Item Normalization UI
- Vendor-specific OCR preprocessing

## Key DB Schema (purchases.items)
```
{
  raw_name: "CHICKEN BREAST BNLS",
  quantity: 3,
  pack_size: "4/10 LB",           // editable input
  unit_price: 89.45,               // editable input
  total: 268.35,                   // computed: qty × price (read-only)
  
  // Server-computed on save:
  pack_size_raw: "4/10 LB",        // preserved verbatim
  pack_parse_status: "parsed",     // "parsed" | "failed" | "not_applicable"
  packs_per_case: 4,               // null if failed
  weight_per_pack: 10.0,           // null if failed
  pack_unit: "LB",                 // null if failed
  total_case_weight: 40.0,         // null if failed
  normalized_price_per_lb: 2.2363  // null unless LB/OZ and all checks pass
}
```
