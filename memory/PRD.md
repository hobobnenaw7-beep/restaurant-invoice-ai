# Restaurant Accounting AI — PRD

## Problem Statement
Full-stack restaurant accounting platform with OCR receipt ingestion, vendor price comparison, confidence scoring, and AI chat assistant. Built with React + FastAPI + MongoDB.

## Architecture (Post V2 Migration)
```
/app/backend/
├── server.py              # 75 lines — FastAPI app, CORS, mount routers
├── core/
│   ├── __init__.py        # Re-exports
│   ├── database.py        # MongoDB client, db, UPLOADS_DIR, LLM_KEY, logger
│   ├── auth.py            # JWT utils, get_user, hash_pw, verify_pw, require_manager
│   └── models.py          # All Pydantic models (15+ classes)
├── services/
│   ├── audit.py           # audit_log() helper
│   ├── alerts.py          # generate_smart_alerts() engine
│   └── approval.py        # compute_approval_status()
├── routes/                # 20 domain-specific routers
│   ├── auth.py            # Auth + User management
│   ├── audit.py           # Audit log API
│   ├── approvals.py       # Approval workflow
│   ├── dashboard.py       # Dashboard summary, item-search, drill-down
│   ├── upload.py          # OCR extraction + Excel parse
│   ├── receipts.py        # Receipt learning + vendor patterns
│   ├── records.py         # Records library (file uploads)
│   ├── duplicates.py      # Duplicate detection
│   ├── purchases.py       # Purchases CRUD + auto-vendor/item creation
│   ├── salaries.py        # Salaries CRUD
│   ├── other_expenses.py  # Other Expenses CRUD
│   ├── sales.py           # Sales CRUD
│   ├── suppliers.py       # Suppliers CRUD + merge
│   ├── items.py           # Items + Aliases + Price History
│   ├── reports.py         # Reports + Category + PDF/Excel export
│   ├── prices.py          # Price Intelligence + Vendor Comparison
│   ├── vendor_comparison.py # Item Mappings + Normalized $/LB Comparison
│   ├── alerts.py          # Alerts + Smart Purchase Decisions
│   ├── chat.py            # AI Chat (GPT-5.2 via Emergent LLM Key)
│   └── settings.py        # Settings + Seed
├── preprocessing.py       # Trust logic (UNTOUCHED — Trusted/Unverified hard gates)
└── requirements.txt
```

## Completed Features
- OCR Receipt Extraction (GPT-5.2 via Emergent LLM Key)
- Pack-size regex parsing with confidence scoring
- Vendor Price Comparison Dashboard (normalized $/LB)
- Manual/Assisted Item Matching (Jaccard similarity suggestions)
- Decision-Making UI (best/worst deal, spread %, savings banners)
- Confidence + Review Layer (Trusted vs Unverified hard gates)
- Explainability + Quick Fix UI (inline editing, confidence_reason)
- Full CRUD: Purchases, Sales, Salaries, Other Expenses, Suppliers, Items
- Audit Logs, Approval Workflow, User Management
- Reports with PDF/Excel export (category + summary)
- AI Chat Assistant
- Records Library (file uploads)
- **Backend V2 Migration (COMPLETED Feb 2026)** — 4007-line monolith → 75-line orchestrator + 20 route modules

## Key DB Schema
- `purchases.items`: includes `confidence_level`, `confidence_reason`, `pack_parse_status`
- `item_mappings`: `raw_name` → `canonical_name` for vendor comparison
- `vendor_patterns`: learned OCR hints per vendor

## 3rd Party Integrations
- OpenAI GPT-5.2 via Emergent LLM Key (`emergentintegrations`)

## Backlog (P1/P2)
- P1: AI Chat Assistant Page Polish
- P1: OCR/Image Upload for Salaries tab
- P2: Client-side pack size preview
- P2: bcrypt warning cleanup
