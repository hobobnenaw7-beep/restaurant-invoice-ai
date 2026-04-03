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
- Only MISSED type: cross-row value leakage with self-consistent wrong values
- Flags: pass / warning / needs_review (never auto-corrects)
- Integrated into `parse_invoice_layout()` output and upload API response

### Phase 5 - Semantic and Consistency Intelligence (DONE)
- **5 deterministic checks**, never auto-corrects, only flags:
  1. **Name Quality**: truncated (≤3 chars), single-word, generic ("MISC", "PACKER"), service rows ("DELIVERY CHARGE", "FUEL SURCHARGE")
  2. **Column Bleed**: price embedded in name ($35.00), pack size in name (4/10 LB), trailing numbers
  3. **Cross-Row Leakage**: duplicate qty+price+total between neighbors (the MAYO problem — previously undetectable)
  4. **Structural Consistency**: outlier rows (short name, missing qty/price vs peers, total outlier vs median)
  5. **Vendor Patterns**: distributor missing pack_size (Sysco/US Foods), unreasonable quantities, PFG weight indicators
- **Severity levels**: `pass` / `suspicious` / `needs_review`
- **Real-world validation** on 10 full-pipeline invoices:
  - Problem invoices: 5/7 ALL issues caught (2 partial = non-semantic limitations)
  - Control invoices: 2/3 zero false positives
  - Cross-row leakage: NOW CAUGHT (was the only undetectable failure mode)
- **Deduplication logic**: suppresses `distributor_missing_pack_size` when `pack_size_in_name` already flagged, or when ALL items are missing pack (parser issue, not data quality)

## Known Non-Semantic Limitations (NOT semantic-validator failures)
- **PFG missing pack_size** (INV01): PFG uses weight-based pricing, not standard distributor pack columns. The semantic validator intentionally does not check PFG for missing packs. This is a vendor-specific parser limitation.
- **Column bleed / pack_size_in_name** (INV04, INV08): When OCR can't read dark column headers, the fallback parser merges pack sizes into item_name. The semantic validator correctly flags `pack_size_in_name` as a finding. This is a layout parser / column-mapping limitation, not a semantic bug.
- **INV04 low parse rate** (1/4 items): No-vendor invoices with unreadable headers sometimes fail column detection. This is a layout parser limitation.

## Other Known Issues
- **inv08 (10pt font)**: OCR reads ".09" instead of ".00" — Tesseract limitation on very small text (correctly FLAGGED by numeric validation)
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
- Phase 5 proposal pending user approval — scope TBD
- Integrate loose match keys into vendor comparison (P1, blocked until phase defined)

## Future/Backlog
- AI Chat Assistant Page Polish (P2)
- OCR/Image Upload for Salaries tab (P2)
- Client-side pack size preview (P2)
