# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction. Features modular backend architecture, normalization layer, correction memory system, review lifecycle, hard invoice robustness, and guided correction suggestions.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Strict trust/validation logic for extracted items
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle: needs_review, review_reason, confidence_level persist across saves
- Invoice-level review_status: clean | warning | error
- Hard invoice handling: robust extraction for messy/low-quality inputs
- Guided Correction Suggestions: rule-based fix proposals per flagged item

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
- [x] Quick Review UI (item-level review indicators)
- [x] Invoice Sorting Fix (date-based, created_at fallback)
- [x] Invoice-level review_status (clean/warning/error)
- [x] Hard Invoice Robustness Layer
- [x] Bug Fix: compute_review_status resilient to old items
- [x] Guided Correction Suggestions V1 (2026-03-31)
  - Math mismatch → suggest corrected total (qty × price)
  - Missing total/price/qty → suggest computed value
  - Pack parse failure → suggest normalized format (1x30LB → 1/30 LB)
  - Correction memory → surface learned corrections
  - Missing name → suggest from normalization data
  - UI: blue "Suggested fix" box with Apply/Dismiss buttons
  - Apply writes suggested values and revalidates item
  - Dismiss hides suggestion without changing data
  - Edit Manually / Ignore buttons for manual workflow
  - Old items get client-side suggestions via revalidateItem on edit open

## Known Issues
- P0: Old pytest suite failures (test_profit_calculation.py etc.) — deferred by user
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
