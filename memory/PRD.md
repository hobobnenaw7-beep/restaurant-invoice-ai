# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic. Key goals: UI clarity, correction visibility, image preprocessing, document classification, layout-based OCR parsing.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (primary extraction — vision-based)
- **Rate Limiter**: Custom async request queue with retry logic (`services/llm_rate_limiter.py`)
- **Validation**: Deterministic math-first pipeline (system-enforced, no LLM math)

## Vendor-Separated Pipeline Strategy

| Vendor | Status | Trust Gate | Input Support | Trust Rate |
|--------|--------|-----------|---------------|------------|
| **Sysco** | **Controlled Operational** | Math-first ($0.01 tolerance) + source validation | Camera photos + scans | **52% (0 false trusts)** |
| **US Foods** | **Structural Mapping Done** | Math gate runs, all items → vendor_logic_pending | Camera photos | N/A (no trust yet) |
| **PFG** | **Pending** | All items → vendor_logic_pending | Camera photos | N/A |
| **Other** | **Pending** | All items → vendor_logic_pending | Any | N/A |

## Sysco Math-First Trust Gate

A row is Trusted ONLY if ALL conditions pass:
1. vendor = Sysco
2. row_type = line_item or fee
3. Text is structurally readable (≥3 alpha chars)
4. qty > 0, unit_price > 0, total > 0
5. qty × unit_price = total (tolerance: $0.01)
6. All field sources are "column_read" (not "inferred" or "ambiguous")
7. No inferred/hallucinated values

### Known Pattern: qty=1 Trap
- GPT marks qty_source as "ambiguous" when QTY column is narrow/unreadable
- These items get qty=1 by default → `1 × price = total` trivially passes
- Trust gate CORRECTLY rejects these (source not column_read)
- This accounts for ~65% of review items

## Horizontal Anchoring (Sysco)
GPT Vision uses Price and Total columns (wider, more legible) as horizontal anchors to trace left and locate the QTY column. Improved trust rate from 47% → 52%.

## Partial Page Handling
- If items_sum < declared_subtotal → partial page (common with camera photos of multi-page invoices)
- Row-level trusted items preserved; invoice flagged as "partial"
- If items_sum > declared_subtotal → over-extraction; trusted items downgraded

## LLM Rate Limiter
- Min 3s interval between requests (prevents proxy burst limits)
- Max 2 retries with exponential backoff (8s, 16s)
- Handles webhook.site rate limits from Emergent proxy
- Stats endpoint: GET /api/llm-stats

## Stress Test Results (Phase 2.1 — 50 files)

### Sysco (20 invoices)
- 184 line items extracted
- 96 trusted (52%), 88 review, 1 excluded
- **0 false trusts**
- 17 complete, 2 partial, 1 over-extracted

### Non-Sysco (30 invoices)
- 110 line items extracted
- 0 trusted (correct — vendor logic pending)
- US Foods: 97% item code extraction, 94% math pass

## Key API Endpoints
- `POST /api/upload/extract` — Main extraction pipeline
- `GET /api/llm-stats` — Rate limiter statistics
- `POST /api/auth/login` — Authentication

## Files of Reference
- `/app/backend/routes/upload.py` — Pipeline flow, vendor routing, trust gates
- `/app/backend/services/llm_rate_limiter.py` — Rate limiting + retry logic
- `/app/backend/services/sysco_pipeline.py` — Legacy OCR pipeline (bypassed)
- `/app/backend/preprocessing.py` — Image preprocessing
- `/app/backend/tests/phase2_stress_test.py` — 50-file stress test
- `/app/backend/tests/phase2_stress_report.json` — Latest results

## Credentials
- Demo: demo@test.com / testpassword
