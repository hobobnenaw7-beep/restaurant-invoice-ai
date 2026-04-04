# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic. Key goals: UI clarity, correction visibility, image preprocessing, document classification, layout-based OCR parsing.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **OCR**: Tesseract + OpenCV (proven unreliable on camera photos AND scanned PDFs)
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (primary extraction — vision-based)
- **Validation**: Deterministic rule-based pipeline (system-enforced, no LLM math)

## Vendor Operational Status

| Vendor | Status | Input Format | Key Limitation |
|--------|--------|-------------|----------------|
| **Sysco** | **CONTROLLED OPERATIONAL** (guarded mode) | Scanned PDF preferred | Subtotal mismatches, occasional unreadable qty, row misclassification — all gated by validation guardrails |
| **PFG** | **LIMITED** (all items → needs_review) | Scanned PDF | $/LB and EXT PRICE columns cannot be separated — dedicated phase needed |
| **US Foods** | **NOT STARTED** | — | Separate extraction/OCR problem, parked for future phase |

## Critical Findings (Spike Testing)

### Tesseract OCR — Proven Unusable
- Camera photos: complete garbage output for ALL vendors
- Scanned PDFs: also garbage output (PFG colored backgrounds, Sysco dense layout)
- **Decision: Tesseract is NOT a viable reading layer for these invoice formats**

### GPT-5.2 Vision — Primary Reading Layer
- Can read invoice text reliably from both camera photos and scans
- **Limitation 1**: Non-deterministic — same image gives different numeric values across runs (camera photos only; stable on scans)
- **Limitation 2**: Cannot separate PFG's $/LB and EXT PRICE columns (too close together)
- **Scanned input stabilizes Sysco** — ketchup price stable at $18.95, math validates

### Architecture Validation
The hybrid approach (GPT reads → system enforces) is structurally sound:
- Group header filtering: works
- Row classification (product/service): works
- qty from SHIP column (PFG): works
- Math validation (qty × price ≈ total): works
- Subtotal-level validation: works

## Guardrails Implemented

### Sysco (Controlled Operational — Guarded Mode)
Usable in real-world testing but NOT fully trusted. Validation gates all output.
1. Group total / subtotal text in item name → needs_review (never becomes product)
2. Missing or unreadable qty (qty=0 with total>0) → needs_review
3. Math validation: qty × price ≠ total by >10% → needs_review
4. Service row classification (fuel surcharge, delivery)
5. Subtotal mismatch >5% → ALL items downgraded to review
6. Any invoice with subtotal mismatch, unreadable fields, or misclassification → partial or full needs_review

### PFG (Limited Mode)
1. ALL items → needs_review with explanation: "$/LB and EXT PRICE cannot be reliably separated"
2. All-qty-1 detection (SHIP column missed)
3. Pack-in-name leakage detection
4. Weight-as-qty detection (qty > 100)
5. Service row classification

## Code Structure
```
/app/backend/
├── routes/
│   ├── upload.py           (Pipeline, vendor prompts, PFG/Sysco post-validation)
│   ├── purchases.py        (PATCH for inline edits)
│   ├── metrics.py          (Usability metrics)
├── services/
│   ├── layout_parser.py    (OCR extraction — proven unreliable, kept as validation layer)
│   ├── semantic_validator.py (Row classification, trust levels, vendor patterns)
├── preprocessing.py        (Pack parsing, item validation, score computation)
├── tests/
│   ├── test_pfg_parser.py           (18 tests — layout parser safeguards)
│   ├── test_sysco_validation.py     (32 tests — semantic validator)
│   ├── test_sysco_preprocessing.py  (12 tests — preprocessing)
│   ├── test_pfg_post_extraction.py  (7 tests — LLM output validation)
│   ├── test_vendor_guardrails.py    (9 tests — operational guardrails)
│   ├── spike_hybrid.py             (Spike V1 — camera photos)
│   ├── spike_hybrid_v2.py          (Spike V2 — camera photos with read-only prompt)
│   ├── spike_hybrid_v3.py          (Spike V3 — scanned PDFs)
```

## Testing Status
- **78 backend tests**: ALL PASS, zero regressions
- **Spike tests**: V1-V3 completed, evidence documented
- **Testing agent iterations**: 73-75 (100% pass rate)

## Key API Endpoints
- `POST /api/upload/extract` — Extract invoice data (vendor-specific prompts + guardrails)
- `PATCH /api/purchases/{id}/items/{index}` — Inline edits with revalidation
- `POST /api/metrics/session` — Usability tracking

## Prioritized Backlog

### P0 — Next Phase
- **PFG Column Separation Phase**: Dedicated approach to separate $/LB and EXT PRICE columns. Options: column-region cropping, multi-pass extraction, or structured table prompt.
- **Scanned input workflow**: UI guidance to prefer scanned PDFs over camera photos.

### P1
- US Foods dedicated extraction/OCR recovery phase
- Document Capture / Scan Mode (auto-edge detection, crop, perspective correction)
- Vendor comparison with loose match keys

### P2
- AI Chat Assistant Page Polish
- OCR/Image Upload for Salaries tab
- Client-side pack size preview
- bcrypt attribute error (parked)
- pytest suite failures (parked)

## Credentials
- Demo: demo@test.com / testpassword
