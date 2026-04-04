# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic (no AI/LLM for suggestions or layout fixing). Key goals: UI clarity, correction visibility, image preprocessing, document classification, layout-based OCR parsing.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **OCR**: Tesseract + OpenCV (with image preprocessing)
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (primary extraction)
- **Validation**: Deterministic rule-based pipeline

## Code Structure
```
/app/backend/
├── routes/
│   ├── upload.py       (Pipeline flow, vendor-specific prompts, PFG post-validation, subtotal checks)
│   ├── purchases.py    (PATCH for inline edits)
│   ├── metrics.py      (Usability metrics)
├── services/
│   ├── layout_parser.py  (OCR extraction, image preprocessing, PFG rules, fallback handlers)
│   ├── semantic_validator.py  (Row classification, trust levels, vendor patterns, pack format validation)
├── preprocessing.py    (Pack parsing, item validation, score computation)
├── tests/
│   ├── test_pfg_parser.py          (18 safeguards - layout parser)
│   ├── test_sysco_validation.py    (32 tests - semantic validator)
│   ├── test_sysco_preprocessing.py (12 tests - preprocessing)
│   ├── test_pfg_post_extraction.py (7 tests - LLM output validation)
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

### Vendor Stabilization (Current Session - Feb 2026)

#### PFG (Performance Foodservice) Stabilization:
1. **Pack-token exclusion** — Pack zone covers full gap between description text and ORD/SHIP columns. ORD captured as explicit "unknown" column. No numeric token between description and SHIP leaks into qty.
2. **PFG-specific LLM prompt** — Built-in vendor hint injected into GPT-5.2 extraction: describes all 8 PFG columns (ITEM#, DESCRIPTION, PACK/SIZE, ORD, SHIP, WEIGHT, $/LB, EXT PRICE), emphasizes SHIP = qty, warns against common errors.
3. **PFG post-extraction validation** — Catches:
   - All-qty=1 pattern (SHIP column missed)
   - Pack info leaked into item names
   - Weight-as-qty (qty > 100, suspiciously large)
   - Service row classification (fuel surcharge, delivery)
4. **Subtotal-level validation** — When items sum ≠ declared subtotal by >5%, ALL items downgraded from "trusted" to "review" with mismatch explanation.
5. **Image preprocessing for OCR** — Auto-rotate portrait→landscape, adaptive threshold for camera photos, scaling to ~2500px.

#### Sysco Stabilization:
1. **Row classification** — product vs service (SERVICE_KEYWORDS-based). Service rows bypass pack validation.
2. **Expanded pack format handling** — Dimensions (1508X8X3), metric units (10007 GM), volume (4 GAL), count (24 CT).
3. **Trust level computation** — trusted/info/warning/needs_review based on math + fields + classification.
4. **HARD GATE 3 softening** — Pack parse failure is informational (not hard fail) when math passes.
5. **Case weight check** — Uses LB-equivalent conversion (10007 GM = ~22 LB, not flagged).
6. **Sysco-specific LLM prompt** — Built-in vendor hint for GPT-5.2 with Sysco column layout.

## Key API Endpoints
- `POST /api/upload/extract` - Extract invoice data (with vendor-specific prompts)
- `PATCH /api/purchases/{id}/items/{index}` - Inline edits with revalidation
- `POST /api/metrics/session` - Usability tracking

## Testing Status
- **69 backend tests**: 18 PFG parser + 32 Sysco validation + 12 Sysco preprocessing + 7 PFG post-extraction — ALL PASS
- **Frontend**: Login, dashboard, expenses, upload dialog — ALL VERIFIED
- **Testing agent iterations**: 73-75 (100% pass rate)

## Vendor Stabilization Status
| Vendor | Extraction | Validation | Status |
|--------|-----------|------------|--------|
| PFG | LLM prompt + post-validation | Column mapping + pack exclusion | Step 1 Complete |
| Sysco | LLM prompt | Row classification + trust levels | Step 2 Complete |
| US Foods | Not started | Not started | Step 3 (Parked) |

## Known Limitations
- Camera photos still produce low-quality OCR with Tesseract (image preprocessing helps but can't fully overcome)
- LLM extraction is the primary path; layout parser serves as validation layer
- OCR precision on very small (10pt) monospace fonts on noisy backgrounds remains limited

## Prioritized Backlog

### P0 (Next after vendor stabilization)
- US Foods dedicated extraction/OCR recovery phase
- Document Capture / Scan Mode (auto-edge detection, crop, perspective correction, deskew)

### P1
- Integrate loose match keys into vendor comparison for improved auto-grouping

### P2
- AI Chat Assistant Page Polish
- Add OCR/Image Upload to Salaries tab
- Client-side pack size preview
- bcrypt attribute error in backend logs (parked)
- Old pytest suite failures (parked)

## Credentials
- Demo: demo@test.com / testpassword
