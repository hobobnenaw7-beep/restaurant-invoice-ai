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
- 13 fixes applied (OSD threshold, median filter, bg cleanup, column mapping, Unicode quotes, OCR digit fix, header keywords, DPI, separator logic)

### Phase 4.5 - Numeric Validation Layer (DONE - Current)
- Per-item: qty × unit_price ≈ total_price cross-check
- Invoice-level: sum of totals, zero-value detection, duplicate detection
- **Detection rate: 92%** of bad rows correctly flagged
- **Precision: 71%** (100% if PFG weight-based items counted as correct warnings)
- Only MISSED type: cross-row value leakage with self-consistent wrong values
- Flags: pass / warning / needs_review (never auto-corrects)
- Integrated into `parse_invoice_layout()` output and upload API response

## Remaining Known Issues
- **inv08 (10pt font)**: OCR reads ".09" instead of ".00" — Tesseract limitation on very small text (all 10 items correctly FLAGGED by validation)
- **inv04 MAYO (1 item)**: Cross-row value leakage — internally consistent wrong values can't be detected by math validation alone
- **bcrypt** attribute error in backend logs (P2, parked)
- **pytest** suite failures (P2, blocked by user instruction)

## Key API Endpoints
- `POST /api/upload/extract`: Full pipeline (Preprocess → Classify → Layout Parse → LLM)
- `GET /api/correction-hints`: Fetch learned corrections
- `GET/PUT/DELETE /api/correction-memory`: CRUD for audit page

## Database Schema
- `purchases`: document_type, page_count, layout_parse_results
- `correction_memory`: usage_count, last_used_at, enabled

## Credentials
- Email: demo@test.com
- Password: testpassword

## Upcoming Tasks
- Integrate loose match keys into vendor comparison (P1)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
