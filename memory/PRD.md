# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Unit Normalization — Layered Decision Engine — COMPLETE

### Full Decision Flow
```
Input: item with pack_size, item_code, quantity, total, storage_category
                    ↓
Signal 1: Parser (always runs pack_size text)
Signal 2: Memory (always runs vendor+code lookup)
                    ↓
┌─ USER_CORRECTED memory? ──→ Apply directly (conf=1.0)
│                              UNLESS parser contradicts unit type
↓
Drift Detection (category-aware thresholds):
  frozen/chilled: 10% threshold (strict)
  dry/chemicals:  25% threshold (tolerant)
  default:        15%
  meat keywords:  10% (auto-detected)
                    ↓
  IF drift > threshold → needs_review (memory_drift_detected)
                    ↓
Recency Bias:
  >180 days old: memory_conf -= 0.15
  >90 days old:  memory_conf -= 0.08
                    ↓
Validation Layer (math, bounds, category sense)
                    ↓
Confidence Scoring + Conflict Resolution
                    ↓
Apply or Flag for Review
```

### Drift Thresholds by Category
| Category | Threshold | Reasoning |
|----------|-----------|-----------|
| frozen, chilled | 10% | Perishables — pack sizes are standardized |
| dry | 25% | Stable goods — vendor may change pack sizes |
| uncategorized/default | 15% | Balanced |
| Meat/seafood keywords | 10% | Auto-detected strict even without storage_category |

### Verified Drift Scenarios
1. **75% drift on frozen meat** → needs_review ✓
2. **0% drift on dry goods** → normalized ✓
3. **20% drift on dry (within 25% tolerance)** → normalized ✓
4. **20% drift on frozen (exceeds 10% threshold)** → needs_review ✓

## Completed Work (Milestone 2 — FULLY CLOSED)
- Unit Normalization + Canonical Unit Layer
- Product Memory with cross-format consistency
- Layered Decision Engine (validation + confidence + conflict)
- Manual-to-Memory Learning Loop (user_corrected truth)
- **Trust Calibration & Drift Detection (anti-blind-trust)**
  - Category-aware thresholds
  - Recency bias (stale memory loses confidence)
  - User-corrected drift check (parser unit contradiction)

## Upcoming Tasks
### P0
- Milestone 3 (user to define)
### P2
- Smart Market Insights, AI Chat Assistant, Trash/Restore

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
