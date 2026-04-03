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
- 15-invoice stress test baseline: 17.6% accuracy (16/91 items)

### Phase 4 - Layout Parser Stabilization (DONE)
- **Accuracy: 17.6% → 86.8% (4.9x improvement)**
- 13 fixes applied

### Phase 4.5 - Numeric Validation Layer (DONE)
- Per-item: qty × unit_price ≈ total_price cross-check
- Invoice-level: sum of totals, zero-value detection, duplicate detection
- Flags: pass / warning / needs_review (never auto-corrects)

### Phase 5 - Semantic and Consistency Intelligence (DONE)
- 5 deterministic checks: Name Quality, Column Bleed, Cross-Row Leakage, Structural Consistency, Vendor Patterns
- Severity levels: pass / suspicious / needs_review
- Real-world validation: 5/7 problem invoices ALL caught, 3/3 controls clean

### Phase 6 - Layout Parser Hardening (DONE)
- Pack-size column extraction in fallback parsers
- Header-less column inference with spatial clustering
- Low-yield fallback detection (< 40% threshold)
- INV04: 1/4 → 4/4 items parsed, INV08: 3 false positives → 0

### Phase 7 - Review + Correction Layer (DONE) — April 2026
- **Display Layer**: Per-item status indicators, issue badges, validation summary banner, field-level highlighting of problematic fields
- **Correction Layer**: Inline editing (raw_name, qty, price, total, pack_size), Fix button on flagged rows, immediate revalidation with validation delta (improved/degraded/unchanged)
- **Data Integrity**: Full audit trail (previous value, new value, timestamp, user), post-edit validation integrity showing if edit made row better or worse
- **List Filtering**: Purchases list filterable by validation status (All / Needs Review / All Verified)
- **Backend**: `PATCH /api/purchases/{id}/items/{index}` with revalidation + audit, `GET /api/purchases/{id}/edit-history`
- **Testing**: 17/17 backend + 17/17 frontend tests passed

## Known Limitations (correctly classified)

### OCR Quality — Known, Correctly Handled
- OCR corrupts numeric values on 13pt generated images — math validation correctly flags as needs_review
- 10pt font precision: OCR reads ".09" instead of ".00" — correctly flagged

### Vendor Model — Intentional
- PFG missing pack_size: PFG uses weight-based pricing, semantic validator intentionally skips

## Other Known Issues
- **bcrypt** attribute error in backend logs (P2, parked)
- **pytest** suite failures (P2, blocked by user instruction)

## Key API Endpoints
- `POST /api/upload/extract`: Full pipeline (Preprocess → Classify → Layout Parse → Validation → LLM)
- `PATCH /api/purchases/{id}/items/{index}`: Inline edit with revalidation + audit trail
- `GET /api/purchases/{id}/edit-history`: Edit audit trail
- `GET /api/correction-hints`: Fetch learned corrections
- `GET/PUT/DELETE /api/correction-memory`: CRUD for audit page

## Database Schema
- `purchases`: document_type, page_count, items (with validation_errors, needs_review, confidence_level), edit_history[], review_status, layout_parse_results
- `correction_memory`: usage_count, last_used_at, enabled

## Credentials
- Email: demo@test.com
- Password: testpassword

## Upcoming Tasks
- Phase 8 proposal pending user approval — scope TBD
- Integrate loose match keys into vendor comparison (P1, blocked until phase defined)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
