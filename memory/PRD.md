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
- [x] Correction Layer Phase 1: Capture + Visibility (2026-04-01)
  - Issue type classification (classifyIssue): math, pack, name, suspicious, missing, review
  - List view: categorized issue tags ("1 math · 1 pack") per invoice
  - Edit dialog: specific issue type badges (Math Mismatch, Pack Parse Failed, Missing Name, etc.)
  - Backend: correction_memory stores edits for pack_size, unit_price, total (not just name)
  - Apply only for deterministic fixes (math recalculation)
  - Edit Manually + Ignore always available

## Known Issues
- P0: Old pytest suite failures — deferred by user
- P2: bcrypt.__about__ warning in backend startup logs
- Minor: OCR sometimes corrupts pack text (e.g., "2/5 LB" -> "2.5 LB") — extraction-level issue

## Upcoming Tasks (P1)
- Correction Layer Phase 2: Surface stored corrections as simple hints (not AI suggestions)
- Integrate loose match keys into vendor comparison for auto-grouping

## Future/Backlog (P2)
- AI Chat Assistant Page Polish
- Add OCR/Image Upload support to Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
