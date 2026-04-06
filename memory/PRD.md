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

## Strict Decision Gate (Deterministic)

No row becomes "trusted" unless ALL conditions pass:
1. qty from defined column (qty > 0)
2. unit_price from defined column (price > 0)
3. total from defined column (total > 0)
4. item name present
5. math validated (qty × price ≈ total within 2% or $0.50)
6. no hard failures
7. subtotal validates (items sum within 5% of declared total)

## Review Status Taxonomy

| Status | Meaning | Action |
|--------|---------|--------|
| `trusted` | All gates passed, no ambiguity | Auto-accepted |
| `needs_review_light` | Minor issues (pack format, name quality) but math OK | User review recommended |
| `needs_review_numeric` | Math mismatch or missing qty/price/total | User review required |
| `extraction_failed` | Critical fields missing or garbled | Manual entry needed |
| `vendor_unsupported` | Vendor not yet fully supported (PFG, US Foods) | Manual entry needed |

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
├── preprocessing.py            (Pack parsing, item validation, score computation, SCAN MODE)
├── tests/
│   ├── test_pfg_parser.py           (18 tests)
│   ├── test_sysco_validation.py     (32 tests)
│   ├── test_sysco_preprocessing.py  (12 tests)
│   ├── test_pfg_post_extraction.py  (7 tests)
│   ├── test_vendor_guardrails.py    (9 tests)
│   ├── test_scan_mode.py            (25 tests — edge detection, perspective, pipeline)
│   ├── spike_hybrid*.py            (Spike V1-V3 evidence)
```

## Scan Mode (Always ON — Feb 2026)
Automatic image preprocessing for camera photos:
1. **Edge detection**: OpenCV Canny + contour detection to find document boundaries
2. **Perspective correction**: 4-point transform to flatten angled photos
3. **Camera photo detection**: Border brightness analysis (dark borders = camera photo)
4. **4-way orientation fix**: Compares OCR readability at 0°/90°/180°/270° — picks best (fixes upside-down and sideways documents)
5. **Fallback**: CLAHE adaptive contrast for photos where edges can't be found
6. **Clean scan passthrough**: No-op for scanned PDFs (already full-frame)
7. **Preprocessing evidence**: Every upload returns step-by-step metadata + before/after artifacts
Pipeline: Scan Mode → EXIF rotate → 4-way Orientation fix → Deskew → Crop margins → Enhancement

**Requires**: `tesseract-ocr` + `tesseract-ocr-eng` system packages (for OSD + readability scoring)

## Testing: 85/85 backend tests pass (60 existing + 25 scan mode)

## Prioritized Backlog

### P0 — Immediate
- Real-world Sysco testing (20-30 invoices)
- Success criteria: ≥70% fully trusted invoices, ≥85% trusted rows, <2 min correction time
- Identify top 3 failure patterns from real usage → fix those

### P0 — Next Dedicated Phase
- PFG Column Separation Phase ($/LB vs EXT PRICE separation)

### P1
- US Foods dedicated extraction phase
- Vendor comparison with loose match keys

### P2 (Paused)
- AI Chat Assistant Polish
- Salaries OCR, pack size preview
- bcrypt / pytest fixes (parked)

## Credentials
- Demo: demo@test.com / testpassword
