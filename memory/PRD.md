# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction. Features modular backend architecture, normalization layer, correction memory system, review lifecycle management, and hard invoice robustness.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Strict trust/validation logic for extracted items
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle: needs_review, review_reason, confidence_level persist across saves
- Invoice-level review_status: clean | warning | error
- Hard invoice handling: robust extraction for messy/low-quality inputs

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
- [x] Quick Review UI
- [x] Invoice Sorting Fix (all lists sort by date, fallback to created_at)
- [x] Invoice-level review_status (clean/warning/error)
- [x] Hard Invoice Robustness Layer (2026-03-31)
  - sanitize_extracted_item: type coercion, negative values, null handling
  - detect_column_misread: flags qty/price column swap patterns
  - compute_extraction_meta: invoice-level extraction confidence (high/medium/low)
  - salvage_partial_extraction: recovers data from broken JSON responses
  - Per-item try/except in extraction pipeline (one bad item doesn't crash)
  - extraction_meta returned in /upload/extract response
  - sanitize_extracted_item called in create/update purchase endpoints

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
