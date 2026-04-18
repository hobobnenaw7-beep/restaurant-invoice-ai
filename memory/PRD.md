# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/
│   │   ├── auth.py, permissions.py, models.py, database.py
│   ├── routes/
│   │   ├── upload.py (Extraction pipeline, multi-signal routing, correction apply, hallucination filter)
│   │   ├── purchases.py (Correction save on explicit user edit)
│   │   ├── correction_memory.py (CRUD for correction management)
│   │   ├── auth.py, sales.py, other_expenses.py, records.py, settings.py, profit_dashboard.py
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── correction_memory.py (v2: strong key hierarchy + provenance)
│   │   ├── usfoods_structural.py (2-phase extraction + dark image retry)
│   │   ├── product_memory.py (In-memory cross-row validation)
│   │   ├── normalization.py, unit_normalizer.py, llm_rate_limiter.py
│   ├── preprocessing.py (Image processing + dark image detection/enhancement)
├── frontend/src/
│   ├── App.js, components/, contexts/, pages/
```

## Completed Work
- Permissions + Accountability model (21 perms, 4 roles)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test — COMPLETE
- Multi-signal vendor detection + confidence routing — COMPLETE
- Correction Memory v2 (strong key hierarchy + provenance) — COMPLETE
- **Dark image preprocessing layer — COMPLETE**
  - Quality assessment on original images (before standard preprocessing)
  - Aggressive enhancement: gamma + CLAHE + brightness normalization
  - Retry-with-enhancement in structural parser
  - Hallucination filter exemption for structural items with product codes
  - Result: 0→138 items recovered (+90 net), zero false trusts

## Upcoming Tasks
### P0
- Production correction workflow testing with real user edits

### P1
- Re-enable Product Memory layer integration
- Test multi-user workflows with production data

### P2
- Smart Market Insights 3-panel expansion
- AI Chat Assistant polish
- Trash/Restore UI for soft-deleted records
- OCR/Image Upload for Salaries tab

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123
- Cashier: cashier@test.com / testpass123
- Staff: staff@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
