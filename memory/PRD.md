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

### Phase 4.5 - Numeric Validation Layer (DONE)
- Per-item: qty × unit_price ≈ total_price cross-check
- Invoice-level: sum of totals, zero-value detection, duplicate detection
- **Detection rate: 92%** of bad rows correctly flagged
- **Precision: 71%** (100% if PFG weight-based items counted as correct warnings)
- Flags: pass / warning / needs_review (never auto-corrects)

### Phase 5 - Semantic and Consistency Intelligence (DONE)
- **5 deterministic checks**, never auto-corrects, only flags:
  1. **Name Quality**: truncated (≤3 chars), single-word, generic ("MISC", "PACKER"), service rows ("DELIVERY CHARGE", "FUEL SURCHARGE")
  2. **Column Bleed**: price embedded in name ($35.00), pack size in name (4/10 LB), trailing numbers
  3. **Cross-Row Leakage**: duplicate qty+price+total between neighbors (the MAYO problem — previously undetectable)
  4. **Structural Consistency**: outlier rows (short name, missing qty/price vs peers, total outlier vs median)
  5. **Vendor Patterns**: distributor missing pack_size (Sysco/US Foods), unreasonable quantities, PFG weight indicators
- **Severity levels**: `pass` / `suspicious` / `needs_review`
- **Real-world validation**: 5/7 problem invoices ALL caught, 3/3 controls clean
- **Deduplication logic**: suppresses `distributor_missing_pack_size` when `pack_size_in_name` already flagged, or when ALL items are missing pack (parser issue)

### Phase 6 - Layout Parser Hardening (DONE)
- **3 parser-level fixes** (semantic validator untouched):
  1. **`_extract_items_simple` (fallback parser)**: Pack-size words now separated into `pack_size` field instead of merging into `item_name`
  2. **`_infer_columns_from_data` (header-less inference)**: Added spatial clustering of pack-size words to detect dedicated `pack_size` columns and narrow `item_name` boundary
  3. **Low-yield fallback detection**: When column-based extraction returns < 40% of available data rows, tries `_extract_items_simple` and uses whichever produces more items. Applied to default structured parser, Sysco, and US Foods vendor parsers
- **Additional improvements**: Post-processing in `_map_words_to_columns` extracts pack patterns from `item_name` into `pack_size`; unknown columns with pack-size words routed to `pack_size`; vendor parsers use 3-tier fallback (header → inferred → simple)
- **Results**:
  - INV08 (US Foods control): 3 false positives → **0 flags** (pack_size correctly separated)
  - INV04 (no-header): **1/4 → 4/4 items parsed** (low-yield fallback triggered)
  - All controls: **3/3 CONTROL_PASS**
  - All tests: **13/13 unit + 8/8 integration + 10/10 real-world**, zero regressions

## Known Limitations (correctly classified)

### Parser/Layout — FIXED
- **INV04 low-yield fallback**: Column-based parser stuck on garbled OCR values, didn't fall back to simple extraction. **Fixed** by low-yield detection (< 40% threshold).

### OCR Quality — Known, Correctly Handled
- **INV04 garbled values**: OCR corrupts numeric values on 13pt generated images ($35.00→"$35 99", $105.00→"Sigs ag"). Math validation correctly flags these as `needs_review`. Real uploaded invoices with better print quality would produce better OCR.
- **10pt font precision**: OCR reads ".09" instead of ".00" on very small text. Correctly flagged by numeric validation.

### Vendor Model — Intentional
- **PFG missing pack_size (INV01)**: PFG uses weight-based pricing, not standard distributor pack columns. Semantic validator intentionally does not check PFG for missing packs.

## Other Known Issues
- **bcrypt** attribute error in backend logs (P2, parked)
- **pytest** suite failures (P2, blocked by user instruction)

## Key API Endpoints
- `POST /api/upload/extract`: Full pipeline (Preprocess → Classify → Layout Parse [Numeric + Semantic Validation] → LLM)
- `GET /api/correction-hints`: Fetch learned corrections
- `GET/PUT/DELETE /api/correction-memory`: CRUD for audit page

## Database Schema
- `purchases`: document_type, page_count, layout_parse_results (includes validation_summary + semantic_summary)
- `correction_memory`: usage_count, last_used_at, enabled

## Credentials
- Email: demo@test.com
- Password: testpassword

## Upcoming Tasks
- Phase 7 proposal pending user approval — scope TBD
- Integrate loose match keys into vendor comparison (P1, blocked until phase defined)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
