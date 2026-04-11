# Invoice AI — Product Requirements Document

## Original Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline using GPT-5.2 Vision as a reader (not inferencer) with strict math-first validation (`qty × price = total`). Zero false trusted rows is a hard requirement. Vendor-separated strategy with Sysco as primary MVP.

## Architecture
- **Stack**: React (frontend) + FastAPI (backend) + MongoDB (Motor async)
- **LLM**: GPT-5.2 Vision via Emergent LLM Key — used ONLY as a reader, never for inference
- **Math-First Trust Gate**: `qty × price = extended_price` with $0.01 tolerance
- **Product Memory**: Item code-first matching, fuzzy description fallback, controlled qty=1 support
- **Unit Normalizer**: Converts pack_size → lb or piece, calculates price_per_unit (99% parse rate)

## Data Flow Integrity
- Only `trusted` + `user_confirmed` data feeds analytics
- Review data isolated in `sysco_review_items` until confirmed
- `sysco_trusted_extractions` stores verified trusted items with full metadata + unit normalization fields

## What's Been Implemented

### Extraction Pipeline (FROZEN — 0 false trusts achieved)
- [x] GPT-5.2 Vision reader for Sysco camera photos
- [x] Math-First Validation gate (qty × price = total)
- [x] Category header filtering (POULTRY, SEAFOOD, etc.)
- [x] Partial-page subtotal logic
- [x] LLM rate limiter with exponential backoff
- [x] Product Memory V2: item_code-first, fuzzy fallback, controlled qty=1
- [x] DB storage: trusted items saved to `sysco_trusted_extractions`
- [x] Review items saved to `sysco_review_items`
- [x] Row-level priority: valid rows stay valid regardless of invoice-level mismatches
- [x] Trust rate: 53.5%, 0 false trusts confirmed

### Unit Normalization Layer (Phase 6)
- [x] Parses 76 unique Sysco pack_size patterns (99% success rate)
- [x] Supports: LB, #, GAL, OZ, EA, CT, container dimensions (8X8X3)
- [x] OCR resilience: handles "41OLB" (O→0), "4/0#" (0→10), "1508X8X3" (squashed spaces)
- [x] Adds: normalized_quantity, normalized_unit (lb/piece), price_per_unit, unit_status
- [x] Fee items (FUEL SURCHARGE) excluded from normalization
- [x] Persisted to `sysco_trusted_extractions` items

### Profit Dashboard APIs
- [x] `GET /api/profit/intelligence` — price trends, vendor stability, cost drivers
- [x] `GET /api/profit/review-queue` — review items with reason labels
- [x] `POST /api/profit/confirm-item` — confirms item, updates status
- [x] `GET /api/profit/search?q=` — decision engine search
- [x] `POST /api/profit/ai-insights` — deterministic auto-insights + GPT-5.2 explanation

### Smart Market Insights (Dashboard Section)
- [x] Added below existing dashboard (no layout changes)
- [x] Price Alerts, Savings Opportunities, Risk Alerts
- [x] Max 5 insights, 2-3 lines each, actionable, deduplicated

## Prioritized Backlog

### P0 (Next)
- US Foods Dedicated Extraction Phase
- PFG Dedicated Extraction Phase
- Scale Sysco stress test to full 294 images

### P1
- Historical price trend charts (visual graphs)
- Multi-vendor comparison with real data

### P2
- bcrypt attribute error cleanup (parked)
- upload.py refactoring (~1,900 lines, on user approval)
- AI Chat Assistant Page Polish
- OCR/Image Upload for Salaries tab

## Key Collections
- `sysco_trusted_extractions` — Verified items with item_code, confidence_level, unit normalization
- `sysco_review_items` — Items needing review (status: review/confirmed)
- `user_confirmed` — User-confirmed items from review queue

## Credentials
- Username: demo@test.com / Password: testpassword
