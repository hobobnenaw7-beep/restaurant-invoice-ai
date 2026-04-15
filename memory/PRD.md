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
│   │   ├── usfoods_structural.py (NEW — 2-phase structural extraction for US Foods)
│   │   ├── image_preprocessor.py (Resize/enhance for GPT Vision)
│   │   ├── section_splitter.py (Section splitting — tested, NOT active)
│   ├── tests/
│   │   ├── vendor_consistency_report.py (3-vendor 3-run consistency)
│   │   ├── usfoods_structural_test.py (2-phase structural validation)
│   │   ├── usfoods_prompt_fix_test.py
│   │   ├── trust_gate_results.py (Multi-vendor trust gate validation)
│   │   ├── usfoods_evidence_report.py
├── frontend/src/
│   ├── pages/ExpensesPage.js (photo capture guidelines added)
```

## Pipeline Flow (per invoice)

### Sysco / PFG (Standard Path)
```
Image → Preprocess → GPT-5.2 Vision (vendor-specific prompt) → Consensus if poor
    → Per-Item Sanitize → Row Classification → Source Validation
    → Vendor-Specific Trust Gate → trust_decision Audit → DB Save
```

### US Foods (2-Phase Structural Path)
```
Image → Preprocess → Phase 1: GPT reads NUMERIC GRID (product codes + qty/price/total)
                   → Phase 2: GPT reads DESCRIPTIONS (product names + pack sizes)
                   → Deterministic Assembly (merge by product_code)
    → Per-Item Sanitize → Row Classification → Source Validation
    → US Foods Trust Gate → trust_decision Audit → DB Save
```

### Vendor-Specific Prompts
- **Sysco**: Strict read-only with horizontal column anchoring, qty_column_visible
- **US Foods**: 2-phase structural — Phase 1 (numbers-only), Phase 2 (descriptions-only)
- **PFG**: SHIP column focus, WEIGHT/PACK confusion guards, strict read-only
- **Generic**: Read-only mode, qty_column_visible

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

## Current Trust Rates (Feb 2026)

### Proven Deterministic (clean inputs)
| Vendor | Trust Rate | False Trusts | Determinism | Notes |
|--------|-----------|--------------|-------------|-------|
| Sysco | 100% | 0 | 3/3 identical | Fully operational, proven |
| PFG | 100% | 0 | 3/3 identical | Fully operational, proven |
| US Foods (clean scan) | 100% | 0 | 3/3 identical (12/12 items, all codes match) | 2-phase structural, proven on clean input |

### Production-Safe (dark phone photos)
| Vendor | Trust Rate | False Trusts | Determinism | Notes |
|--------|-----------|--------------|-------------|-------|
| US Foods (phone photo) | 0-100% | 0 | Non-deterministic item counts | Safe (zero false trusts), variability tied to image quality |

## Completed Work (Feb 2026)
- qty_column_visible confidence signal for all vendor prompts
- Fee row handling (total > 0, skip product math)
- Vendor-specific column sanity checks (US Foods, PFG)
- trust_decision audit field on every row
- Dedicated US Foods GPT prompt path
- Anti-hallucination backend filter (price=0 + total=0 rows)
- Image preprocessing (resize 4K phone photos before LLM)
- Multi-attempt consensus mechanism (Sysco/PFG/generic)
- Post-extraction vendor detection fallback via supplier_name
- US Foods relaxed prompt (removed "FULLY VISIBLE" gate that caused 0-item collapse)
- US Foods 2-phase structural extraction engine (Phase 1: numbers, Phase 2: descriptions)
- Section splitting tested and reverted (proven worse than single-pass)
- Photo capture guidelines added to upload UI
- Clean-input validation: US Foods 2-phase achieves 100% determinism on clean scans

## Approaches Tested and Results
| Approach | Outcome |
|----------|---------|
| Single-call strict prompt | 0 items on dark photos (too restrictive) |
| Single-call relaxed prompt | 11-19 items, 0 false trusts, non-deterministic names |
| Section splitting (2 strips) | WORSE — 0-9 items (strips lose column context) |
| Multi-attempt consensus | Helps Sysco/PFG; marginal for US Foods |
| Tesseract OCR on phone photos | Total failure (gibberish output) |
| Tesseract OCR on clean scans | Perfect (all text readable) |
| 2-phase structural (numbers + descriptions) | 100% deterministic on clean input; non-deterministic on dark photos |

## Known Issues
- US Foods dark phone photos: non-deterministic extraction (safe but variable)
- Emergent Proxy rate limiting on heavy bursts (50+ concurrent)
- upload.py ~2700+ lines (refactoring parked per user direction)

## Upcoming Tasks
### P0 — Immediate
- Obtain real US Foods PDF/clean scan for production validation
- Confirm 2-phase structural determinism on real clean US Foods invoice

### P1 — After Clean-Input Confirmation
- Scale stress test to full 294 images (Sysco, US Foods, PFG)
- Re-enable Product Memory as secondary validation layer

### P2 — Future
- Expand Smart Market Insights (3-panel command center)
- AI Chat Assistant polish
- OCR/Image Upload for Salaries tab
- upload.py refactoring

## Test Credentials
- Username: demo@test.com / Password: testpassword

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
