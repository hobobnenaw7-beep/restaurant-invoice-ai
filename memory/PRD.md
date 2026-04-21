# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/ (auth, permissions, models, database)
│   ├── routes/
│   │   ├── upload.py (Extraction pipeline, routing, correction, classification, normalization)
│   │   ├── purchases.py (CRUD + inline edit + verify + correction memory)
│   │   ├── items.py (CRUD + storage-category + filter)
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── correction_memory.py (v2: strong key hierarchy + provenance)
│   │   ├── storage_classifier.py (Auto-classify + manual override protection)
│   │   ├── unit_normalizer.py (Pack parsing + price_per_unit calculation)
│   │   ├── usfoods_structural.py (2-phase extraction + dark image retry)
│   ├── preprocessing.py (Image processing + dark image enhancement)
├── frontend/src/
│   ├── components/ (InlineReviewPanel, InvoiceReviewDialog)
│   ├── pages/ (ItemsPage, ExpensesPage, etc.)
```

## Unit Normalization (Milestone 2) — COMPLETE
### Formula
`price_per_unit = line_total / (quantity × normalized_multiplier)`

### Pattern Coverage
- Sysco: fraction lb (4/10 LB), simple lb (40 LB), OZ, GAL, EA, CS+count
- Sysco OCR fix: "410LB" → 4/10 = 40 lb (prefix≥2 only, preserves 120LB/150LB as-is)
- CS prefix stripping: "CS 410 LB" → stripped → "410LB" → fraction fix
- US Foods / PFG: LB+container (40 LB CS), CT count (6 CT), fraction CT, fraction OZ portions
- Ambiguous/empty → unit_status='review', price_per_unit=None (flagged, no guess)
- Fee items → excluded

### Test Results
- 24 pack_size parse patterns: 24/24 pass
- 4 price formula tests: 4/4 pass
- 2 before/after JSON examples: verified
- 2 review flag tests: verified
- Live Sysco extraction: all items correctly normalized

## Completed Work
- Permissions + Accountability model
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test
- Multi-signal vendor detection
- Correction Memory v2
- Dark image preprocessing
- Manual Review Workflow
- Hybrid Item Classification System
- **Unit Normalization & Price Calculation (Milestone 2)**

## Upcoming Tasks
### P0
- Production testing of normalization on US Foods + PFG invoices
### P1
- Re-enable Product Memory layer integration
### P2
- Smart Market Insights 3-panel expansion
- AI Chat Assistant polish
- Trash/Restore UI
- OCR/Image Upload for Salaries tab

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123
- Cashier: cashier@test.com / testpass123
- Staff: staff@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
