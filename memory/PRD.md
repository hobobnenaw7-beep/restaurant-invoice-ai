# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus multi-user permissions, accountability, and self-improving product memory.

## Unit Normalization — Layered Decision Engine — MILESTONE 2 COMPLETE

### Full Decision Flow
```
Input: item with pack_size, item_code, qty, unit_price, total, storage_category
                    ↓
Signal 1: Parser (always runs pack_size text)
Signal 2: Memory (always runs vendor+code lookup)
                    ↓
┌─ USER_CORRECTED memory? → Apply (conf=1.0) unless parser contradicts unit type
↓
Drift Detection (category-aware thresholds):
  frozen/chilled: 10% | dry: 25% | default: 15%
                    ↓
  IF drift detected:
    Signal 3: MATH ARBITRATION
      - Check PPU from each multiplier against reasonable ranges
      - Parser gets document evidence bonus (strong parse methods)
      - If math clearly favors one signal → auto-resolve (no review)
      - If inconclusive → needs_review
                    ↓
Recency Bias → stale memory loses confidence
Validation → bounds, category-unit sense
Conflict Resolution → agree/disagree/review
```

### Math Arbitration Details
- PPU reasonableness: $0.10-$50/lb, $0.005-$20/piece
- Parser document bonus: +0.25 for strong parse methods (direct invoice evidence)
- Win margin: 0.15 (must clearly beat the other signal)
- Result: reduces unnecessary needs_review by resolving drift via math

### Verified Scenarios
1. Parser wins via math (shrimp $4.50/lb > $0.90/lb) ✓
2. Memory wins via math (chicken $2.95/lb > $0.059/lb on OCR garble) ✓
3. Math inconclusive (both PPUs reasonable) → parser wins via document bonus ✓
4. Category-aware drift thresholds ✓
5. User-corrected truth with parser contradiction check ✓
6. Learning loop: review → user corrects → memory → auto-reuse ✓

## Completed Work (Milestone 2 — FULLY CLOSED)
- Unit Normalization + Canonical Unit + Pack Size Parsing
- Product Memory (DB-backed, cross-invoice)
- Layered Decision Engine (3-signal: parser + memory + math)
- Manual-to-Memory Learning Loop
- Trust Calibration + Drift Detection (category-aware)
- **Math Arbitration Layer (auto-resolve drift without review)**

## Other Completed Work
- Permissions + Accountability (4 roles, 21 permissions)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- 294-image stress test
- Multi-signal vendor detection
- Correction Memory v2
- Dark image preprocessing
- Manual Review Workflow (inline edit + verify)
- Hybrid Item Classification System

## Upcoming Tasks
### P0 - Milestone 3 (user to define)
### P2 - Smart Market Insights, AI Chat, Trash/Restore, Salaries OCR

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
