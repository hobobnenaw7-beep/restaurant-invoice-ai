# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction. Features modular backend architecture, normalization layer, correction memory system, and review lifecycle management.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Strict trust/validation logic for extracted items
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: auto-apply learned user edits per supplier
- Review lifecycle: needs_review, review_reason, confidence_level persist across saves

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
  - needs_review, review_reason, confidence_level displayed per item
  - Amber highlighting for flagged rows in list, detail, and edit views
  - Review count indicator in invoice list (Items column)
  - Review banner in View Detail dialog
  - Status column with green checks / amber warnings in detail view
  - Fix/Accept buttons in edit mode
  - Save works without resolving flagged items
  - Review flags persist through save/update/reopen cycle

## Known Issues
- P0: Old pytest suite failures (test_profit_calculation.py, test_sales_date_range.py, test_strict_confidence_scoring.py) due to missing REACT_APP_BACKEND_URL env var — deferred by user
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
