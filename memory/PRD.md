# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction. Features modular backend architecture, normalization layer, correction memory system, and review lifecycle management.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Strict trust/validation logic for extracted items
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle: needs_review, review_reason, confidence_level persist across saves
- Invoice-level review_status: clean | warning | error

## Architecture
- Backend: FastAPI modular (core/, routes/, services/)
- Frontend: React + TailwindCSS + Shadcn UI
- Database: MongoDB
- LLM: OpenAI GPT-5.2 via emergentintegrations

## Completed Features
- [x] Clean Backend V2 Migration (monolith -> modular)
- [x] Performance & Architecture Validation Audit
- [x] Normalization Layer (services/normalization.py)
- [x] Correction Memory System V1 (services/correction_memory.py)
- [x] "Save Now, Review Later" Data Persistence
- [x] Quick Review UI (2026-03-31)
- [x] Invoice Sorting Fix (2026-03-31)
  - All lists sort by date field (invoice_date, report_date, expense_date, payment_date)
  - Default: newest first (descending)
  - Fallback to created_at when date is missing/empty
  - Uses MongoDB aggregation pipeline with $cond
- [x] Invoice-level review_status (2026-03-31)
  - Computed by compute_review_status() in preprocessing.py
  - clean: no issues, warning: items need review, error: hard errors (math mismatch, missing name, suspicious)
  - UI: no color for clean, orange border+bg for warning, red border+bg for error
  - Visual only — does NOT block saving
  - Stored on purchase documents, computed on create/update

## Known Issues
- P0: Old pytest suite failures (test_profit_calculation.py, etc.) — deferred by user
- P2: bcrypt.__about__ warning in backend startup logs

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
