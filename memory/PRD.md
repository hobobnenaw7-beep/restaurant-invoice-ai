# Restaurant Accounting AI — PRD

## Problem Statement
Full-stack restaurant accounting platform with OCR receipt ingestion, vendor price comparison, confidence scoring, and AI chat assistant. Built with React + FastAPI + MongoDB.

## Architecture (Post V2 Migration)
```
/app/backend/
├── server.py              # 75 lines — FastAPI app, CORS, mount routers
├── core/
│   ├── database.py        # MongoDB client, db, UPLOADS_DIR, LLM_KEY, logger
│   ├── auth.py            # JWT utils, get_user, hash_pw, verify_pw, require_manager
│   └── models.py          # All Pydantic models (15+ classes)
├── services/
│   ├── audit.py           # audit_log() helper
│   ├── alerts.py          # generate_smart_alerts() engine
│   ├── approval.py        # compute_approval_status()
│   └── normalization.py   # Item name normalization layer (NEW)
├── routes/                # 20 domain-specific routers
├── preprocessing.py       # Trust logic (UNTOUCHED — pack parsing + confidence)
├── tests/
│   └── test_normalization.py  # 14 regression tests
└── requirements.txt
```

## Pipeline (updated)
```
OCR → Extraction (GPT) → NORMALIZATION → Validation/Trust → Save
                          ^^^^^^^^^^^^^
                          services/normalization.py
```

## Normalization Layer Design
- **clean_name**: conservative (uppercase + whitespace + grade separator only)
- **base_name**: aggressive (specs + embedded weight stripped for broad matching)
- **strict_match_key**: token-normalized sorted words of clean_name (distinguishes products)
- **loose_match_key**: token-normalized sorted words of base_name (groups broadly)
- **specs**: structured extraction (grade, size_code, product_code, embedded_weight/count)
- **unit_std**: standardized unit field
- Token normalization: abbreviation expansion (BNLS→BONELESS, HDLS→HEADLESS, etc.)
- Singular/plural normalization (TOMATOES→TOMATO, ONIONS→ONION)
- Pure functions, no DB calls, no side effects

## Completed Features
- OCR Receipt Extraction (GPT-5.2 via Emergent LLM Key)
- Pack-size regex parsing with confidence scoring
- Vendor Price Comparison Dashboard (normalized $/LB)
- Manual/Assisted Item Matching
- Decision-Making UI (best/worst deal, spread %, savings)
- Confidence + Review Layer (Trusted vs Unverified hard gates)
- Explainability + Quick Fix UI
- Full CRUD: Purchases, Sales, Salaries, Other Expenses, Suppliers, Items
- Audit Logs, Approval Workflow, User Management
- Reports with PDF/Excel export
- AI Chat Assistant, Records Library
- Backend V2 Migration (Feb 2026) — 4007→75 lines
- Performance Audit (Feb 2026) — All endpoints <160ms
- **Normalization Layer (Feb 2026)** — Item name/unit standardization module

## Known Bottlenecks (from audit)
1. Dashboard double `generate_smart_alerts` call (HIGH)
2. Purchase save loads ALL purchases for price comparison (MEDIUM)
3. Full-collection scans in analytics endpoints (MEDIUM, scaling concern)
4. N+1 query in items endpoint (LOW)

## Backlog
- P1: AI Chat Assistant Page Polish
- P1: OCR/Image Upload for Salaries tab
- P2: Client-side pack size preview
- P2: bcrypt warning cleanup
