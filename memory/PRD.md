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
│   └── approval.py        # compute_approval_status()
├── routes/                # 20 domain-specific routers
├── preprocessing.py       # Trust logic (UNTOUCHED)
└── requirements.txt
```

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
- **Backend V2 Migration (Feb 2026)** — 4007→75 lines
- **Performance Audit (Feb 2026)** — All endpoints <160ms, 3 bottlenecks identified

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
