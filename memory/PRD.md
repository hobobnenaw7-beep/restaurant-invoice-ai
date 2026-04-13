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
│   │   ├── product_memory.py (Cross-row historic validation — disabled per user direction)
│   │   ├── llm_rate_limiter.py (Rate limiting for GPT-5.2 calls)
│   ├── tests/
│   │   ├── test_qty_visible_logic.py (9 unit tests)
│   │   ├── test_pipeline_correctness.py (12 unit tests)
│   │   ├── trust_gate_results.py (Multi-vendor trust gate validation)
│   │   ├── usfoods_raw_diagnostic.py (Raw GPT extraction diagnostic)
│   │   ├── phase2_stress_test.py (Large-scale batch test)
├── frontend/src/
│   ├── pages/DashboardPage.js
│   ├── components/profit/SmartMarketInsights.js
```

## Pipeline Flow (per invoice)
```
Image → GPT-5.2 Vision (vendor-specific prompt) → Quality Check + Retry
    → Per-Item Sanitize → Row Classification → Source Validation
    → Vendor-Specific Trust Gate → trust_decision Audit → DB Save
```

### Vendor-Specific Prompts (3 dedicated + 1 generic)
- **Sysco**: Strict read-only with horizontal column anchoring, qty_column_visible
- **US Foods**: Multi-format detection (Format A/B/C), strict read-only, qty_column_visible
- **PFG**: SHIP column focus, WEIGHT/PACK confusion guards, strict read-only, qty_column_visible
- **Generic**: For unrecognized vendors, read-only mode, qty_column_visible

### Extraction Quality Check + Retry
GPT-5.2 vision is non-deterministic. If >50% of items have critical fields at 0 (price=0 AND total=0, or qty=0 with total present), or if only 1-2 items extracted with all zeros, the system retries once and keeps the better result.

### Row Classification
- `line_item`: product rows (full math gate: qty × price = total ±$0.01)
- `fee`: fuel surcharge, delivery, service charges (total > 0 only, no qty×price)
- `group_total`, `subtotal`, `tax`, `header`: excluded from scoring

### Vendor-Specific Trust Gates
All three vendor gates follow the same structure:
1. Fee rows: trust if total > 0 (no product math)
2. Product rows: trust if ALL of:
   - qty × price = total (±$0.01)
   - qty_source == "column_read"
   - price_source == "column_read"
   - total_source == "column_read"
   - No column confusion errors
   - Readable item name

### Column Sanity Checks
- **PFG**: WEIGHT-as-qty (qty > 50), decimal qty (SHIP is integer), pack-as-qty
- **US Foods**: WEIGHT-as-qty (qty > 50), decimal qty (SHIPPED is integer), ORDERED-vs-SHIPPED

### trust_decision Audit Trail
Every row carries:
```json
{
  "row_type": "line_item|fee",
  "extracted": {"raw_name": "...", "quantity": N, "unit_price": N, "total": N},
  "gates": {"qty_source": "column_read", "math_check": true, ...},
  "final_status": "trusted|needs_review_numeric",
  "failure_category": "none|fee_valid|math_fail|source|...",
  "reason": "human-readable explanation"
}
```

## Current Trust Rates (Feb 2026)
| Vendor | Trust Rate | False Trusts | Notes |
|--------|-----------|--------------|-------|
| Sysco | 100% | 0 | Fully operational |
| US Foods | 87.5% | 0 | Operational with dedicated prompt + retry |
| PFG | 100% | 0 | Fully operational |

## Known Issues
- Vendor detection sometimes fails (returns None for US Foods images) — needs fallback
- GPT-5.2 vision non-determinism requires retry mechanism (implemented)
- upload.py ~2600+ lines (refactoring parked per user direction)
- bcrypt attribute error in backend logs (P2)

## Upcoming Tasks
### P0
- Improve vendor detection reliability (fallback to DB-stored vendor when GPT fails)

### P1
- Scale stress test to full 294 images (correctness confirmed, ready for scale)
- Re-enable Product Memory as secondary validation layer

### P2
- Expand Smart Market Insights (3-panel command center)
- AI Chat Assistant polish
- OCR/Image Upload for Salaries tab
- upload.py refactoring

## Test Credentials
- Username: demo@test.com / Password: testpassword

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
