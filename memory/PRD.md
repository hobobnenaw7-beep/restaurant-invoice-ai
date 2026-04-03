# Restaurant Accounting & Invoice Management System

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline with phased approach:
- Save Now, Review Later workflow
- Normalization Layer, Correction Memory System V1
- Image preprocessing (deskew, rotation), Document classification
- Layout-based OCR parsing with deterministic validation

**User Mandate**: Strict phased rollout with deterministic rule-based logic only. No AI/LLM for suggestions or layout fixing.

## Tech Stack
- Frontend: React, TailwindCSS, Shadcn UI
- Backend: FastAPI, Python, MongoDB
- OCR: Tesseract (pytesseract), OpenCV (cv2)
- LLM: OpenAI GPT-5.2 via Emergent LLM Key (receipt extraction only)

## Completed Phases

### Phase 1: Correction Layer Capture + Visibility (DONE)
### Phase 2: Correction Hints UI (DONE)
### Correction Memory Audit UI (DONE)
### Phase 1 - Image Preprocessing (DONE)
### Phase 2 - Document Type Classification (DONE)
### Phase 3 - Parser-Specific Layout Handling (DONE)
### Phase 3.5 - Real-World Stress Testing (DONE)
### Phase 4 - Layout Parser Stabilization (DONE)
### Phase 4.5 - Numeric Validation Layer (DONE)
### Phase 5 - Semantic and Consistency Intelligence (DONE)
### Phase 6 - Layout Parser Hardening (DONE)

### Phase 7 - Review + Correction Layer (DONE) — April 2026
- Display: Per-item status indicators, issue badges, validation summary banner, field-level highlighting
- Correction: Inline editing, Fix button, immediate revalidation with validation delta
- Data Integrity: Full audit trail (previous value, new value, timestamp, user)
- List Filtering: Purchases list filterable by validation status
- Testing: 17/17 backend + 17/17 frontend tests passed

### Phase 7.5 - Usability Testing Instrumentation (DONE) — April 2026
- Lightweight metrics: time per invoice, edits per invoice, flagged rows count
- Backend: `POST /api/metrics/review-session` + `GET /api/metrics/review-sessions`
- Frontend: Auto-logs on dialog close (skips <2s accidental opens)
- No in-app feedback forms (feedback collected externally)
- Verified end-to-end: real session captured (6.1s, 0 edits, 1/4 flagged)

## Current Status: AWAITING REAL-WORLD TESTING
- 1-2 restaurants, 5-10 invoices each
- Users upload their own real invoices
- Metrics auto-collected via instrumentation
- Feedback collected externally
- Results will determine: Phase 8 vs UX refinement Phase 7.5b

## Known Limitations
- OCR quality on 13pt generated images — correctly flagged by math validation
- PFG missing pack_size — intentional (weight-based pricing model)

## Other Known Issues
- bcrypt attribute error in backend logs (P2, parked)
- pytest suite failures (P2, blocked by user instruction)

## Key API Endpoints
- `POST /api/upload/extract`: Full pipeline
- `PATCH /api/purchases/{id}/items/{index}`: Inline edit with revalidation + audit
- `GET /api/purchases/{id}/edit-history`: Edit audit trail
- `POST /api/metrics/review-session`: Log review session metrics
- `GET /api/metrics/review-sessions`: Retrieve all metrics

## Credentials
- Email: demo@test.com
- Password: testpassword

## Upcoming (blocked on testing results)
- Phase 8 scope TBD after real-world testing
- Vendor comparison with loose match keys (P1)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
