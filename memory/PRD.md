# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic. Key goals: UI clarity, correction visibility, image preprocessing, document classification, layout-based OCR parsing.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **OCR**: Tesseract + OpenCV (proven unreliable — kept only for synthetic tests)
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (primary extraction — vision-based)
- **Validation**: Deterministic rule-based pipeline (system-enforced, no LLM math)

## Vendor-Separated Pipeline Strategy

**Three separate failure classes. Do NOT treat as one pipeline problem.**

| Vendor | Failure Class | Status | Input | Next Phase |
|--------|--------------|--------|-------|------------|
| **Sysco** | Refinement/Validation | **Controlled Operational** (guarded, scanned only) | Scanned PDF | Operational testing with usability metrics |
| **PFG** | Column Separation | **Limited Mode** (all items → needs_review) | Any | Dedicated PFG Column Separation Phase |
| **US Foods** | Extraction/Reading | **Parked** | — | Dedicated extraction phase later |

## Usability Metrics (Silent Collection)

4 dimensions tracked per invoice — no user-facing UI:
1. **Time saved** — upload-to-save vs 5-min manual baseline (configurable)
2. **Review burden** — trusted vs needs_review vs manually corrected
3. **Error detection value** — system-flagged items: confirmed vs overridden
4. **User friction** — edits count, fields corrected, review time

Endpoints:
- `POST /api/metrics/invoice-lifecycle` — Log per-invoice lifecycle data
- `GET /api/metrics/invoice-summary` — Aggregated stats for internal analysis

## Guardrails

### Sysco (Controlled Operational — Guarded Mode)
Usable for real-world testing. NOT fully trusted. Validation gates all output.
1. Group total / subtotal text in item name → needs_review
2. Missing or unreadable qty (qty=0 with total>0) → needs_review
3. Math validation: qty × price ≠ total by >10% → needs_review
4. Service row classification (fuel surcharge, delivery)
5. Subtotal mismatch >5% → ALL items downgraded to review

### PFG (Limited Mode)
1. ALL items → needs_review: "$/LB and EXT PRICE cannot be reliably separated"
2. All-qty-1 detection, pack-in-name, weight-as-qty, service rows

## Critical Findings (Spike Testing V1-V3)

- Tesseract OCR: unusable on both camera photos AND scanned PDFs
- GPT-5.2 Vision: primary reading layer, stable on scanned Sysco, unstable on PFG column separation
- Hybrid architecture (GPT reads → system enforces): structurally sound

## Code Structure
```
/app/backend/
├── routes/
│   ├── upload.py               (Pipeline, vendor prompts, PFG/Sysco post-validation)
│   ├── purchases.py            (PATCH for inline edits)
│   ├── metrics.py              (Legacy review session tracking)
│   ├── usability_metrics.py    (4-dimension silent lifecycle tracking)
├── services/
│   ├── layout_parser.py        (OCR extraction — kept for synthetic tests)
│   ├── semantic_validator.py   (Row classification, trust levels, vendor patterns)
├── preprocessing.py            (Pack parsing, item validation, score computation)
├── tests/
│   ├── test_pfg_parser.py           (18 tests)
│   ├── test_sysco_validation.py     (32 tests)
│   ├── test_sysco_preprocessing.py  (12 tests)
│   ├── test_pfg_post_extraction.py  (7 tests)
│   ├── test_vendor_guardrails.py    (9 tests)
│   ├── spike_hybrid*.py            (Spike V1-V3 evidence)
```

## Testing: 78/78 backend tests pass

## Prioritized Backlog

### P0 — Immediate
- Sysco operational testing with scanned invoices + usability metrics collection

### P0 — Next Dedicated Phase
- PFG Column Separation Phase ($/LB vs EXT PRICE separation)

### P1
- US Foods dedicated extraction phase
- Document Capture / Scan Mode
- Vendor comparison with loose match keys

### P2
- AI Chat Assistant Polish
- Salaries OCR, pack size preview
- bcrypt / pytest fixes (parked)

## Credentials
- Demo: demo@test.com / testpassword
