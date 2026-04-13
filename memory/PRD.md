# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate. The system must achieve 80-90% trust rate on extracted invoice data across multiple vendors (Sysco, US Foods, PFG) without violating the zero-false-trust rule.

## Architecture
```
/app/
├── backend/
│   ├── routes/
│   │   ├── upload.py (Core pipeline: extraction, row classification, vendor gates, trust assignment)
│   │   ├── profit_dashboard.py (AI insights & decision engine APIs)
│   ├── services/
│   │   ├── unit_normalizer.py (pack_size → lb/piece, computes price_per_unit)
│   │   ├── product_memory.py (Cross-row historic validation — currently disabled per user direction)
│   ├── tests/
│   │   ├── test_qty_visible_logic.py (9 tests — qty_column_visible logic)
│   │   ├── test_pipeline_correctness.py (12 tests — fee handling, column checks)
│   │   ├── trust_gate_results.py (Multi-vendor trust gate validation)
│   │   ├── multi_vendor_results.py (Before/after comparison script)
│   │   ├── phase2_stress_test.py (Large-scale batch test)
├── frontend/src/
│   ├── pages/DashboardPage.js (Dashboard with SmartMarketInsights)
│   ├── components/profit/SmartMarketInsights.js (AI actionable cards)
```

## Pipeline Flow (per row)
```
GPT-5.2 Vision Extract → Row Classification → Source Validation → Vendor-Specific Gate → Trust Decision Audit → DB Save
```

### Stage 1: Row Classification
- `line_item`: product rows
- `fee`: fuel surcharge, delivery, service charges
- `group_total`, `subtotal`, `tax`: excluded from scoring
- `header`: category headers (excluded)

### Stage 2: Source Validation
- Per-item: checks qty_source, price_source, total_source
- qty=1 + price==total: only downgrades if qty_column_visible is NOT true
- Fee rows: skip product math, normalize qty=1, price=total
- All-qty-1 pattern: only bulk-downgrades if no qty_column_visible=true

### Stage 3: Vendor-Specific Trust Gates
**Sysco** — Math-first: qty × price = total (±$0.01) + all sources column_read
**PFG** — Same math rule + column confusion checks (WEIGHT-as-qty, decimal qty, pack-as-qty)
**US Foods** — Same math rule + column confusion checks (WEIGHT-as-qty, ORDERED-vs-SHIPPED)
**Fee rows (all vendors)** — total > 0 only, no qty×price math

### Stage 4: Trust Decision Audit
Every row gets a `trust_decision` object:
```json
{
  "row_type": "line_item|fee|...",
  "extracted": {"raw_name": "...", "quantity": N, "unit_price": N, "total": N, ...},
  "gates": {"qty_source": "column_read", "math_check": true, ...},
  "final_status": "trusted|needs_review_numeric",
  "failure_category": "none|fee_valid|source|math_fail|...",
  "reason": "human-readable explanation"
}
```

## Completed Work
- [x] Math-First Trust Gate (Sysco) — 100% on clean images, ~89% aggregate
- [x] qty_column_visible signal — GPT reports visual presence of QTY column digit
- [x] Fee row handling — fee rows use total > 0 only, no qty×price math
- [x] PFG Trust Gate — 83.3% on test samples, 0 false trusts
- [x] US Foods Trust Gate — 15% on test samples (extraction quality issue, not gate logic)
- [x] Vendor-specific column sanity checks (PFG: WEIGHT/decimal/pack; US Foods: WEIGHT/ORDERED)
- [x] trust_decision audit trail on every row
- [x] Unit Normalization Layer (pack_size → price_per_unit)
- [x] Product Memory (disabled per user direction until base extraction is reliable)
- [x] Smart Market Insights UI
- [x] Profit Intelligence APIs
- [x] 21 unit tests passing, 0 false trusts across all vendors

## Current Trust Rates (Feb 2026)
| Vendor | Trust Rate | False Trusts | Notes |
|--------|-----------|--------------|-------|
| Sysco | 100% | 0 | Fully operational |
| PFG | 83.3% | 0 | Operational, needs more samples |
| US Foods | 15% | 0 | Extraction quality issue, not gate logic |

## Known Issues
- US Foods: GPT returns price=0/total=0 for many items (category section formatting)
- US Foods: qty=1 downgrade still aggressive (prompt now has qty_column_visible, needs re-test)
- File `receipt_b6c5bf31` vendor detection fails (returns None instead of US Foods)
- bcrypt attribute error in backend logs (P2)
- upload.py ~2400 lines (refactoring parked per user direction)

## Upcoming Tasks
### P0
- Investigate US Foods extraction quality (why price=0 for many items)
- Improve US Foods vendor detection reliability

### P1
- Scale stress test to full 294 images (after correctness confirmed)
- Product Memory re-enablement (after base extraction reliable)

### P2
- Expand Smart Market Insights (3-panel command center)
- AI Chat Assistant polish
- OCR/Image Upload for Salaries tab
- upload.py refactoring

## Test Credentials
- Username: demo@test.com / Password: testpassword

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
