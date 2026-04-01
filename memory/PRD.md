# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Dual pricing mode detection: CASE_PRICE vs WEIGHT_BASED
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: store user edits per supplier (name, pack_size, unit_price, total)
- Review lifecycle with guided correction suggestions + Fix All Issues
- Invoice-level review_status: clean | warning | error
- Issue type classification: math, pack, name, suspicious, missing, review
- Correction hints: surface stored corrections as user-controlled hints (no auto-apply)

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
- [x] Pricing Mode Detection & $/LB Fix **FOUNDATIONAL**
- [x] Correction Layer Phase 1: Capture + Visibility (2026-04-01)
  - Issue type classification (classifyIssue): math, pack, name, suspicious, missing, review
  - List view: categorized issue tags ("1 math · 1 pack") per invoice
  - Edit dialog: specific issue type badges (Math Mismatch, Pack Parse Failed, etc.)
  - Backend: correction_memory stores edits for pack_size, unit_price, total
- [x] Correction Layer Phase 2: Correction Hints (2026-04-01)
  - GET /api/correction-hints?supplier_name=X — returns unambiguous stored corrections
  - Ambiguity filtering: multiple corrections for same normalized_key → show nothing
  - "Previously corrected" hints in edit dialog with per-field Use/Dismiss buttons
  - No auto-apply, no ranking, no AI, no confidence scoring
  - User explicitly clicks "Use" to apply a specific field correction

## Known Issues (Parked)
- Old pytest suite failures — deferred by user (Message 5)
- bcrypt.__about__ warning in backend startup logs (P2)

## Upcoming Tasks (P1)
- Integrate loose match keys into vendor comparison for auto-grouping

## Future/Backlog (P2)
- AI Chat Assistant Page Polish
- Add OCR/Image Upload support to Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
