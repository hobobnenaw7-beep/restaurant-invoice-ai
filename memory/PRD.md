# Restaurant Accounting — Invoice Review Pipeline

## Original Problem Statement
Build a robust, rule-based Invoice Review and Correction Pipeline for restaurant accounting. Strict phased approach with deterministic logic.

## Architecture
- **Frontend**: React + Shadcn/UI
- **Backend**: FastAPI + MongoDB (async motor)
- **LLM**: OpenAI GPT-5.2 via Emergent LLM Key (read-only extraction)
- **Rate Limiter**: Async request queue with retry logic (`services/llm_rate_limiter.py`)
- **Product Memory**: Cross-row validation from DB history (`services/product_memory.py`)
- **Validation**: Deterministic math-first pipeline (system-enforced, no LLM math)

## Vendor Pipeline Status

| Vendor | Status | Trust Rate | False Trusts |
|--------|--------|-----------|-------------|
| **Sysco** | Controlled Operational | **44%** | **0** |
| **US Foods** | Structural Mapping Done | N/A (pending) | 0 |
| **PFG** | Pending | N/A (pending) | 0 |
| **Other** | Pending | N/A (pending) | 0 |

## Product Memory (Phase 2.2)
- Built from DB history (83 trusted items from 27 past Sysco purchases)
- Plus current invoice trusted items
- Cross-validates ambiguous rows against known product patterns
- Safe upgrade: review → review_with_memory_support (NOT trusted)
- No numeric inference allowed

## Files of Reference
- `/app/backend/routes/upload.py` — Pipeline flow, vendor routing, trust gates
- `/app/backend/services/llm_rate_limiter.py` — Rate limiting + retry
- `/app/backend/services/product_memory.py` — Product memory cross-validation
- `/app/backend/services/sysco_pipeline.py` — Legacy OCR pipeline (bypassed)
- `/app/backend/preprocessing.py` — Image preprocessing
- `/app/backend/tests/phase2_stress_test.py` — 50-file stress test

## Credentials
- Demo: demo@test.com / testpassword
