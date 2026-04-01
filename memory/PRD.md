# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction. Features modular backend architecture, normalization layer, correction memory system, review lifecycle, hard invoice robustness, guided correction suggestions, weight-based invoice math, and bulk fix actions.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Weight-based invoice math: Line Total = Qty × Pack Weight (LB) × $/LB
- Simple math fallback for non-weight items: Line Total = Qty × Unit Price
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle with guided correction suggestions
- Invoice-level review_status: clean | warning | error
- Fix All Issues bulk action for batch corrections

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
- [x] Invoice Sorting Fix (date-based, created_at fallback)
- [x] Invoice-level review_status (clean/warning/error)
- [x] Hard Invoice Robustness Layer
- [x] Guided Correction Suggestions V1
- [x] Weight-Based Invoice Math Fix
- [x] Fix All Issues Bulk Action (2026-04-01)
  - "Fix All Issues" button in confidence review banner with count
  - Only safe fixes: math recalculation, pack normalization, correction memory
  - Excludes unsafe: fuzzy guesses, missing name, unknown units
  - Confirmation modal with summary + per-item detail
  - Apply All: batch-applies fixes, revalidates each item
  - Fixed items become Trusted, unfixable items stay flagged
  - Button disappears when no safe fixes remain
  - Subtotals/totals auto-update after apply
  - Per-row Apply/Edit/Ignore preserved alongside bulk action

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
