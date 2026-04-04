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

### Phase 1-3: Foundation (DONE)
- Correction Layer, Hints UI, Memory Audit, Image Preprocessing, Document Classification, Parser-Specific Layout

### Phase 3.5: Real-World Stress Testing (DONE)
- 15-invoice baseline: 17.6% accuracy

### Phase 4: Layout Parser Stabilization (DONE)
- **17.6% → 86.8% accuracy (4.9x improvement)**

### Phase 4.5: Numeric Validation Layer (DONE)
- qty × unit_price ≈ total_price cross-check, 92% detection rate

### Phase 5: Semantic and Consistency Intelligence (DONE)
- 5 deterministic checks, never auto-corrects, only flags

### Phase 6: Layout Parser Hardening (DONE)
- Pack-size column extraction, header-less inference, low-yield fallback

### Phase 7: Review + Correction Layer (DONE)
- Inline editing, validation display, field-level highlighting, audit trail
- Testing: 17/17 backend + 17/17 frontend

### Phase 7.5: Usability Testing Instrumentation (DONE)
- Lightweight metrics: time per invoice, edits per invoice, flagged rows count

### Performance Parser Fix (DONE, VALIDATED, LOCKED) — April 2026

**Root cause**: Parser confused ORD qty / SHIP qty / WEIGHT / pack-size numerics on PFG invoices.

**3 bugs fixed**:
1. WEIGHT mapped as quantity → Built `_parse_pfg_inferred()` with ORD/SHIP pair detection
2. OCR misreads leaking WEIGHT into empty qty → Unknown column handler respects dedicated columns
3. ORD spilling into SHIP column → Nearest-center fallback skips numeric fields for non-numeric words

**Result**: 0/8 → 8/8 correct quantities on problematic invoice

**Safeguards locked**:
1. **Permanent regression tests** — 13 pytest fixtures at `/app/backend/tests/test_pfg_parser.py`:
   - SHIP vs ORD selection (3 tests)
   - WEIGHT never used as qty (2 tests)
   - Pack-size token handling (2 tests)
   - Math consistency (2 tests)
   - Unknown column guard (1 test)
   - Full end-to-end (3 tests)
2. **Unknown column guard** — When a dedicated qty column exists, unknown columns NEVER fill qty
3. **Qty validation safety net** — When multiple qty candidates exist, validates via qty×price≈total. If no candidate is close (<30%), falls back to rightmost (SHIP)
4. **Vendor rule documented** — PFG = SHIP is authoritative quantity (not ORD, not WEIGHT). Documented in layout_parser.py vendor rules section.
5. **T05 seafood** — Tagged as OCR_QUALITY_LIMITATION, not parser regression

**Regression results**: 9/10 tests PASS, 47/50 rows correct
- T05 (Seafood) is known OCR quality limitation on generated images, not a parser bug
- Zero regressions in Sysco, US Foods, semantic detection

## Known Limitations

### OCR Quality (tagged: OCR_QUALITY_LIMITATION)
- Tesseract garbles small generated test images (13pt monospace font)
- Real scanned invoices at 300 DPI perform dramatically better
- This validates the need for Document Capture / Scan Mode

### Vendor Model — Intentional
- PFG weight-based pricing: total = weight × $/LB, NOT qty × $/LB
  - Math validation correctly flags as needs_review (expected behavior)

## Other Known Issues
- **bcrypt** attribute error in backend logs (P2, parked)
- **pytest** suite failures (P2, blocked by user instruction)

## Key API Endpoints
- `POST /api/upload/extract`: Full pipeline
- `PATCH /api/purchases/{id}/items/{index}`: Inline edit with revalidation + audit
- `GET /api/purchases/{id}/edit-history`: Edit audit trail
- `POST /api/metrics/review-session`: Log review session metrics
- `GET /api/metrics/review-sessions`: Retrieve all metrics

## Database Schema
- `purchases`: items[], edit_history[], review_status, layout_parse_results
- `correction_memory`: usage_count, last_used_at, enabled
- `review_metrics`: purchase_id, time_spent_seconds, edits_count, flagged_rows_count

## Credentials
- Email: demo@test.com
- Password: testpassword

## Upcoming (user to decide next step)
- **Option A**: Controlled real-world testing (1-2 restaurants, 5-10 invoices)
- **Option B**: Document Capture / Scan Mode (auto-detect edges, crop, perspective correction, deskew, contrast → scan-like quality before OCR)
- Vendor comparison with loose match keys (P1, blocked until phase defined)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
