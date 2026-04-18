# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/ (auth, permissions, models, database)
│   ├── routes/
│   │   ├── upload.py (Extraction pipeline, multi-signal routing, correction apply, storage classify)
│   │   ├── purchases.py (CRUD + inline PATCH edit + verify + correction memory hook)
│   │   ├── items.py (CRUD + PATCH storage-category with manual override + filter)
│   │   ├── correction_memory.py (CRUD for correction management)
│   │   ├── auth.py, sales.py, other_expenses.py, records.py, settings.py
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── correction_memory.py (v2: strong key hierarchy + provenance)
│   │   ├── storage_classifier.py (Auto-classify by section headers + keywords, manual protection)
│   │   ├── usfoods_structural.py (2-phase extraction + dark image retry)
│   ├── preprocessing.py (Image processing + dark image detection/enhancement)
├── frontend/src/
│   ├── components/
│   │   ├── InlineReviewPanel.js (Inline edit cells + Mark Verified)
│   │   ├── InvoiceReviewDialog.js (Full review dialog with audit trail)
│   ├── pages/
│   │   ├── ItemsPage.js (Storage category column, filter tabs, dropdown edit)
│   │   ├── ExpensesPage.js (Needs Review filter + InlineReviewPanel)
```

## Hybrid Item Classification System — COMPLETE
### Schema
- `storage_category`: enum (dry, chilled, frozen)
- `category_source`: enum (auto, manual, default: auto)

### Auto-Classification
- Section headers: FROZEN, DRY, REFRIGERATED → classify items under each section
- Product name keywords: IQF→frozen, FRESH→chilled, RICE→dry
- Applied during extraction pipeline (upload.py)

### Manual Override Protection
- UI dropdown sets `category_source=manual`
- Parser NEVER overwrites manual assignments, even if section header disagrees
- Manual categories reused for future invoices via product_code lookup

### UI
- Filter tabs: All Items | Frozen | Chilled | Dry
- Storage column with inline dropdown per item
- "manual" badge shown when category_source=manual

## Completed Work
- Permissions + Accountability model (21 perms, 4 roles)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test — COMPLETE
- Multi-signal vendor detection + confidence routing — COMPLETE
- Correction Memory v2 (strong key hierarchy + provenance) — COMPLETE
- Dark image preprocessing layer — COMPLETE
- Manual Review Workflow (inline edit + verify + audit) — COMPLETE
- **Hybrid Item Classification System — COMPLETE**

## Upcoming Tasks
### P0
- Production testing: end-to-end upload → classify → review → verify cycle
- Test manual override on real extraction data

### P1
- Re-enable Product Memory layer integration
- Multi-user workflow testing

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
