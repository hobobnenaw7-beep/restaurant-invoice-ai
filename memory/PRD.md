# Restaurant Accounting AI — PRD

## Problem Statement
Full-stack restaurant accounting platform with OCR receipt ingestion, vendor price comparison, confidence scoring, and AI chat assistant. Built with React + FastAPI + MongoDB.

## Architecture
```
/app/backend/
├── server.py              # ~78 lines — FastAPI app, CORS, mount 21 routers
├── core/
│   ├── database.py        # MongoDB client, db, UPLOADS_DIR, LLM_KEY, logger
│   ├── auth.py            # JWT utils, get_user, hash_pw, verify_pw, require_manager
│   └── models.py          # All Pydantic models (15+ classes)
├── services/
│   ├── audit.py           # audit_log() helper
│   ├── alerts.py          # generate_smart_alerts() engine
│   ├── approval.py        # compute_approval_status()
│   ├── normalization.py   # Item name normalization layer
│   └── correction_memory.py # Correction memory: save + apply
├── routes/                # 21 domain-specific routers (incl. correction_memory)
├── preprocessing.py       # Trust logic (UNTOUCHED — pack parsing + confidence)
└── tests/
    └── test_normalization.py
```

## Pipeline (current)
```
OCR → Extraction (GPT) → Pack Enrichment → Normalization → Correction Memory → Validation/Trust → Save
                                                            ^^^^^^^^^^^^^^^^^
                                                            NEW: auto-applies learned corrections
```

## Correction Memory System (V1)
- **Collection**: `correction_memory` — stores supplier-scoped corrections
- **Fields**: id, user_id, restaurant_id, supplier_id, normalized_key (strict), original_raw_name, corrected_name, corrected_specs, confidence, created_at, updated_at
- **Save trigger**: PUT /api/purchases (user edits item name → correction saved)
- **Apply trigger**: POST /api/purchases + POST /api/upload/extract (after normalization, before validation)
- **Matching**: strict_match_key ONLY, supplier-specific ONLY
- **Safety**: raw_name NEVER overwritten, correction stored in `correction_applied` metadata
- **Confidence**: items with corrections get `confidence_level: "learned"`
- **API**: GET /api/correction-memory (read-only listing)

## Integration Rules
1. strict_match_key trusted for exact grouping only
2. loose_match_key suggestion-only — never auto-merge
3. raw_name preserved exactly
4. norm output stored alongside originals
5. Correction memory: supplier-scoped, strict key only, no fuzzy matching
6. UI NOT modified

## Completed Features
- OCR Receipt Extraction (GPT-5.2 via Emergent LLM Key)
- Pack-size regex parsing with confidence scoring
- Vendor Price Comparison Dashboard (normalized $/LB)
- Manual/Assisted Item Matching
- Decision-Making UI (best/worst deal, spread %, savings)
- Confidence + Review Layer (Trusted vs Unverified hard gates)
- Explainability + Quick Fix UI
- Full CRUD for all entity types
- Audit Logs, Approval Workflow, User Management
- Reports with PDF/Excel export
- AI Chat Assistant, Records Library
- Backend V2 Migration (Feb 2026)
- Performance Audit (Feb 2026)
- Normalization Layer (Feb 2026)
- **Correction Memory V1 (Feb 2026)** — auto-learns from edits, auto-applies per supplier

## Known Bottlenecks
1. Dashboard double `generate_smart_alerts` call (HIGH)
2. Purchase save loads ALL purchases for price comparison (MEDIUM)
3. Full-collection scans in analytics endpoints (MEDIUM)
4. N+1 query in items endpoint (LOW)
