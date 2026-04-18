# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/ (auth, permissions, models, database)
│   ├── routes/
│   │   ├── upload.py (Extraction pipeline, multi-signal routing, correction apply)
│   │   ├── purchases.py (CRUD + inline PATCH edit + verify + correction memory hook)
│   │   ├── correction_memory.py (CRUD for correction management)
│   │   ├── auth.py, sales.py, other_expenses.py, records.py, settings.py
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── correction_memory.py (v2: strong key hierarchy + provenance)
│   │   ├── usfoods_structural.py (2-phase extraction + dark image retry)
│   ├── preprocessing.py (Image processing + dark image detection/enhancement)
├── frontend/src/
│   ├── components/
│   │   ├── InlineReviewPanel.js (Inline edit cells + Mark Verified)
│   │   ├── InvoiceReviewDialog.js (Full review dialog with audit trail)
│   ├── pages/ExpensesPage.js (Needs Review filter + InlineReviewPanel integration)
```

## Manual Review Workflow — COMPLETE
### Flow
1. User selects "Needs Review" filter on Expenses → InlineReviewPanel appears
2. Click any Price/Qty/Total cell → inline input opens
3. Enter/blur saves via PATCH → item, totals, review_status recalculated
4. Navigate between invoices with < > arrows
5. When all items resolved → "Mark Verified" button appears
6. Click Mark Verified → sets review_status='verified', approval_status='approved'

### Memory Hook Rules
- **Name corrections** → saved to Correction Memory (primary/secondary key)
- **Price/quantity edits** → audit trail ONLY (not saved to correction memory)

### Audit Trail
Every PATCH edit records: edited_by, edited_at, field, previous_value, new_value, validation_delta

## Completed Work
- Permissions + Accountability model (21 perms, 4 roles)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test — COMPLETE
- Multi-signal vendor detection + confidence routing — COMPLETE
- Correction Memory v2 (strong key hierarchy + provenance) — COMPLETE
- Dark image preprocessing layer — COMPLETE
- **Manual Review Workflow (inline edit + verify + audit) — COMPLETE**

## Upcoming Tasks
### P0
- Production testing of correction workflows with real invoice data
- End-to-end test: upload dark image → review → inline edit → verify cycle

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
