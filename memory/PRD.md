# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Dual pricing mode detection: CASE_PRICE vs WEIGHT_BASED
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle with guided correction suggestions + Fix All Issues
- Invoice-level review_status: clean | warning | error

## Architecture
- Backend: FastAPI modular (core/, routes/, services/)
- Frontend: React + TailwindCSS + Shadcn UI
- Database: MongoDB
- LLM: OpenAI GPT-5.2 via emergentintegrations

## Completed Features
- [x] Clean Backend V2 Migration
- [x] Performance & Architecture Validation Audit
- [x] Normalization Layer
- [x] Correction Memory System V1
- [x] "Save Now, Review Later" Data Persistence
- [x] Quick Review UI
- [x] Invoice Sorting Fix
- [x] Invoice-level review_status
- [x] Hard Invoice Robustness Layer
- [x] Guided Correction Suggestions V1
- [x] Fix All Issues Bulk Action
- [x] Pricing Mode Detection & $/LB Fix (2026-04-01) **FOUNDATIONAL**
  - Simple math tried FIRST: Qty×Price=Total → CASE_PRICE mode
  - Weight math as fallback: Qty×CaseWT×Price=Total → WEIGHT_BASED mode
  - CASE_PRICE: $/LB = CasePrice / CaseWT (derived, not direct)
  - WEIGHT_BASED: $/LB = unit_price (IS the price per pound)
  - pricing_mode field set on every item
  - enrich_item_with_pack_size no longer computes $/LB (deferred to validation)
  - NxN pack format parsing: 1x30, 1x30LB, 12x1LB
  - 39 $/LB values corrected across 108 invoices
  - Performance Foodservice: false $/LB values fixed (e.g., $60.84 → $24.34/LB)
  - Frontend revalidateItem mirrors backend pricing mode logic

## Known Issues
- P0: Old pytest suite failures — deferred by user
- P2: bcrypt.__about__ warning in backend startup logs
- Minor: OCR sometimes corrupts pack text (e.g., "2/5 LB" → "2.5 LB") — extraction-level issue

## Upcoming Tasks (P1)
- Correction Review UI / Correction Memory Management UI
- Integrate loose match keys into vendor comparison for auto-grouping

## Future/Backlog (P2)
- AI Chat Assistant Page Polish
- Add OCR/Image Upload support to Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
