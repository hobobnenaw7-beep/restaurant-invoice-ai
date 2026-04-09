# Invoice AI — Product Requirements Document

## Original Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline using GPT-5.2 Vision as a reader (not inferencer) with strict math-first validation (`qty × price = total`). Zero false trusted rows is a hard requirement. The system has pivoted to a vendor-separated strategy with Sysco as the primary MVP.

## Architecture
- **Stack**: React (frontend) + FastAPI (backend) + MongoDB (Motor async)
- **LLM**: GPT-5.2 Vision via Emergent LLM Key — used ONLY as a reader, never for inference
- **Math-First Trust Gate**: `qty × price = extended_price` with $0.01 tolerance
- **Product Memory**: Cross-validates ambiguous rows against historical DB data using item_code (primary) or fuzzy description matching (fallback)

## Data Flow Integrity
- Only `trusted` + `user_confirmed` data feeds analytics
- Review data is isolated in `sysco_review_items` until confirmed
- `sysco_trusted_extractions` stores verified trusted items with full metadata

## What's Been Implemented

### Extraction Pipeline (FROZEN — 0 false trusts achieved)
- [x] GPT-5.2 Vision reader for Sysco camera photos
- [x] Math-First Validation gate (qty × price = total)
- [x] Category header filtering (POULTRY, SEAFOOD, etc.)
- [x] Partial-page subtotal logic
- [x] LLM rate limiter with exponential backoff
- [x] Product Memory V2: item_code-first matching, fuzzy description fallback, controlled qty=1 support
- [x] DB storage gap fixed: trusted items saved to `sysco_trusted_extractions`
- [x] Review items saved to `sysco_review_items`
- [x] Row-level priority: valid rows stay valid regardless of invoice-level mismatches
- [x] Trust rate: 53.5% (broke 52% ceiling), 0 false trusts confirmed

### Profit Dashboard & AI Command Center (Phase B — COMPLETE)
- [x] **5 Backend APIs**: `/api/profit/intelligence`, `/api/profit/review-queue`, `/api/profit/confirm-item`, `/api/profit/search`, `/api/profit/ai-insights`
- [x] **Three-Panel Layout**: Main panel (left/center), AI sidebar (right, permanent), Review queue (bottom)
- [x] **KPI Strip**: Total Spend, Top Cost Driver, Biggest Price Move, Review Queue count
- [x] **Smart Insights Banner**: Auto-generated actionable alerts (price increases, spend concentration)
- [x] **Decision Engine Search**: "Where Should I Buy?" — vendor comparison, price trends, suggested actions
- [x] **Profit Intelligence**: Top cost drivers with progress bars, price trends (30d), vendor stability scores
- [x] **Review Queue**: Interactive table with reason labels (Qty Ambiguous, Price Mismatch, Memory Supported) + Confirm action
- [x] **AI Sidebar**: Permanent, context-aware, deterministic auto-insights + GPT-5.2 explanation layer
- [x] **Confirm Flow**: Review → Confirm → user_confirmed → dashboard updates instantly

### Testing
- 31 backend tests passed (100%)
- 6 frontend features verified (100%)
- Phase 2.2 stress test: 50 files, 53.5% trust rate, 0 false trusts

## Prioritized Backlog

### P0 (Next)
- US Foods Dedicated Extraction Phase — vendor-specific math gates & trust logic
- PFG Dedicated Extraction Phase — same as above
- Scale Sysco stress test to full 294 images

### P1
- Enhance dashboard with real multi-vendor comparison data (once US Foods/PFG are live)
- Historical price trend charts (7d/30d/90d visual graphs)

### P2
- bcrypt attribute error cleanup (parked)
- Old pytest suite URL config fixes (parked)
- AI Chat Assistant Page Polish
- OCR/Image Upload for Salaries tab
- Client-side pack size preview
- upload.py refactoring (~1,900 lines) — on user approval only

## Key API Endpoints
- `POST /api/upload/extract` — Core extraction pipeline
- `GET /api/profit/intelligence` — Price trends, vendor stability, cost drivers
- `GET /api/profit/review-queue` — Review items with reason labels
- `POST /api/profit/confirm-item` — Confirm review item
- `GET /api/profit/search?q=` — Decision engine search
- `POST /api/profit/ai-insights` — AI explanation layer

## Key Collections
- `sysco_trusted_extractions` — Verified trusted items with item_code, confidence_level
- `sysco_review_items` — Items needing review (status: review/confirmed)
- `user_confirmed` — User-confirmed items from review queue
- `purchases` — Legacy seed data (NOT used for profit analytics)

## Credentials
- Username: demo@test.com
- Password: testpassword
