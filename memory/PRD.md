# Restaurant Accounting & Invoice Management System

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline with phased approach:
- Save Now, Review Later workflow
- Normalization Layer
- Correction Memory System V1
- Image preprocessing (deskew, rotation)
- Document classification
- Layout-based OCR parsing

**User Mandate**: Strict phased rollout with deterministic rule-based logic only. No AI/LLM for suggestions or layout fixing.

## Tech Stack
- Frontend: React, TailwindCSS, Shadcn UI
- Backend: FastAPI, Python, MongoDB
- OCR: Tesseract (pytesseract), OpenCV (cv2)
- LLM: OpenAI GPT-5.2 via Emergent LLM Key (receipt extraction only)

## Completed Phases

### Phase 1: Correction Layer Capture + Visibility (DONE)
- Issue tags in UI, correction data capture

### Phase 2: Correction Hints UI (DONE)
- Learned memory surfaced as safe manual suggestions

### Correction Memory Audit UI (DONE)
- New page for users to view/edit/delete learned corrections

### Phase 1 - Image Preprocessing (DONE)
- OpenCV/Tesseract auto-rotation, deskew, contrast enhancement

### Phase 2 - Document Type Classification (DONE)
- Rule-based density/line counting to route invoices

### Phase 3 - Parser-Specific Layout Handling (DONE)
- Tesseract-based bounding box extraction and column inference

### Phase 3.5 - Real-World Stress Testing (DONE)
- 15-invoice stress test baseline: 17.6% accuracy (16/91 items)

### Phase 4 - Layout Parser Stabilization (DONE - Current)
- **Accuracy: 17.6% → 86% (4.9× improvement)**
- Fixes applied:
  1. Preprocessing: Raised OSD confidence threshold (3.0), fixed false rotations
  2. Preprocessing: Raised median filter noise threshold (40), prevent clean image degradation
  3. Preprocessing: Adaptive bg cleanup for gray backgrounds
  4. Preprocessing: Skip autocontrast/contrast-norm on clean white-bg images
  5. Layout parser: Fixed `_map_words_to_columns` boundary matching (strict bounds → fallback)
  6. Layout parser: Rewritten `_infer_columns_from_data` with right-edge alignment
  7. Layout parser: Pack-size word filtering (`_is_pack_size_word`)
  8. Layout parser: Unicode smart-quote handling in `_parse_number` and `_is_price_like`
  9. Layout parser: OCR digit confusion fix (`_ocr_digit_fix`)
  10. Layout parser: OCR misread header keywords (aty→quantity, ttem→item_name)
  11. Layout parser: Fallback item_name column when header detection misses description
  12. Layout parser: Added `--dpi 300` to Tesseract config
  13. Layout parser: Less aggressive `_is_separator_or_summary` filtering

## Remaining Known Issues
- **inv08 (10pt font)**: OCR reads ".09" instead of ".00" — Tesseract limitation on very small text
- **inv04 (1 item)**: Cross-row value leakage near dark header band — OCR artifact
- **inv15 (noisy)**: Random noise causes occasional value errors — inherent quality limitation
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
- Phase 5: Optimize parser for remaining edge cases (if user approves)
- Integrate loose match keys into vendor comparison (P1)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
