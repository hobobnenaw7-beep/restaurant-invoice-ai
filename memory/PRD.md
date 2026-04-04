# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic (no AI/LLM for suggestions or layout fixing). Key goals: UI clarity, correction visibility, image preprocessing, document classification, layout-based OCR parsing.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **OCR**: Tesseract + OpenCV
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (for initial extraction)
- **Validation**: Deterministic rule-based pipeline

## Code Structure
```
/app/backend/
├── routes/upload.py (Pipeline flow)
├── routes/purchases.py (PATCH for inline edits)
├── routes/metrics.py (Usability metrics)
├── services/layout_parser.py (OCR extraction, PFG rules, fallback handlers)
├── services/semantic_validator.py (Row classification, trust levels, vendor patterns)
├── preprocessing.py (Pack parsing, item validation, score computation)
├── tests/
│   ├── test_pfg_parser.py (18 safeguards)
│   ├── test_sysco_validation.py (32 tests)
│   ├── test_sysco_preprocessing.py (12 tests)
/app/frontend/src/
├── pages/ExpensesPage.js
├── components/InvoiceReviewDialog.js
```

## What's Been Implemented

### Completed Phases (1-7.5)
- Phase 1-3: Preprocess → Classify → Layout Parse
- Phase 4: Semantic Validation (row-level logical checks)
- Phase 5: Layout Parser Hardening (PFG rules, fallback handling)
- Phase 6-7: Review + Correction Layer (InvoiceReviewDialog, PATCH API, audit trail)
- Phase 7.5: Usability Testing Instrumentation

### Bug Fixes (Latest Session - Feb 2026)
- **PFG Parsing Bug**: Fixed pack-token leakage. Pack zone now covers full gap between description text and ORD/SHIP columns. ORD captured as explicit "unknown" column. 5 new safeguard tests added.
- **Sysco Validation Improvements**:
  - Row classification: product vs service (SERVICE_KEYWORDS-based)
  - Expanded pack format handling: dimensions (1508X8X3), metric (10007 GM), volume (4 GAL)
  - Softened HARD GATE 3: pack parse failure = informational when math passes
  - Case weight check now uses LB-equivalent conversion
  - Trust level computation: trusted/info/warning/needs_review based on math + fields + classification
- Upload hint text added: "For best results, use scanned invoices..."

## Key API Endpoints
- `POST /api/upload/extract` - Extract invoice data
- `PATCH /api/purchases/{id}/items/{index}` - Inline edits with revalidation
- `POST /api/metrics/session` - Usability tracking

## Testing Status
- **62 backend tests**: 18 PFG + 32 Sysco validation + 12 Sysco preprocessing — ALL PASS
- **Frontend**: Login, dashboard, expenses, upload dialog — ALL VERIFIED
- **Testing agent iteration**: 74 (100% pass rate)

## Prioritized Backlog

### P0 (Pending real-world test results)
- Document Capture / Scan Mode (auto-edge detection, crop, perspective correction, deskew)

### P1
- Integrate loose match keys into vendor comparison for improved auto-grouping

### P2
- AI Chat Assistant Page Polish
- Add OCR/Image Upload to Salaries tab
- Client-side pack size preview
- bcrypt attribute error in backend logs (parked)
- Old pytest suite failures (parked)

## Known Limitations
- OCR precision on very small (10pt) monospace fonts on noisy backgrounds (documented as acceptable)
- Parser safeguards: "If a quantity column exists, unknown columns must NEVER fill qty" — DO NOT alter

## Credentials
- Demo: demo@test.com / testpassword
