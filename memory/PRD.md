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
│   │   ├── auth.py, sales.py, other_expenses.py, records.py
│   │   ├── upload.py (Extraction pipeline with multi-signal routing + correction apply)
│   │   ├── purchases.py (Correction save on explicit user edit)
│   │   ├── correction_memory.py (CRUD for correction management)
│   │   ├── settings.py, profit_dashboard.py, password_reset.py
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── correction_memory.py (v2: strong key hierarchy + provenance)
│   │   ├── usfoods_structural.py (2-phase structural extraction)
│   │   ├── product_memory.py (In-memory cross-row validation)
│   │   ├── normalization.py, unit_normalizer.py, llm_rate_limiter.py
├── frontend/src/
│   ├── App.js, components/, contexts/, pages/
│   ├── pages/CorrectionMemoryPage.js (Manage corrections UI)
```

## Correction Memory v2 — Key Structure

### Primary Key: `{CANONICAL_VENDOR}:{PRODUCT_CODE}`
- Confidence: **1.0** (strong match)
- Example: `SYSCO:5551234`
- Requires: vendor identified + 4+ digit product code

### Secondary Key: `{CANONICAL_VENDOR}:{SORTED_NORMALIZED_NAME}:{NORMALIZED_PACK}`
- Confidence: **0.75** (lower, flagged as secondary)
- Example: `SYSCO:1620 IQF SHRIMP:2/5LB`
- Requires: vendor identified + raw name

### Match Priority
1. Primary (product code) wins always
2. Secondary (name + pack) only if no primary match
3. First match per tier wins (no loose/fuzzy matching)

### Safeguards
- raw_name NEVER overwritten
- Corrections applied as additive display layer only
- Secondary matches flagged with lower confidence
- Full provenance on every applied correction
- Only explicit user saves create memory entries
- No destructive updates to historical records

## Completed Work
- Permissions + Accountability model (21 perms, 4 roles)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test — COMPLETE
- Multi-signal vendor detection + confidence routing — COMPLETE
- **Correction Memory v2 (strong key hierarchy + provenance) — COMPLETE**

## Upcoming Tasks
### P0
- Image preprocessing for dark US Foods photos
- Image quality gate for low-entropy images

### P1
- Test multi-user correction workflows with production data
- Re-enable Product Memory layer integration

### P2
- Smart Market Insights 3-panel expansion
- AI Chat Assistant polish
- Trash/Restore UI for soft-deleted records

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123
- Cashier: cashier@test.com / testpass123
- Staff: staff@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
