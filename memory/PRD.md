# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Unit Normalization — Layered Decision Engine with Learning Loop — COMPLETE

### Architecture
```
Signal 1: Parser (always runs) → parses pack_size text
Signal 2: Memory (always runs) → looks up vendor+product_code
                    ↓
         ┌─ USER_CORRECTED? ──→ Apply directly (confidence=1.0)
         │                       unless multiplier out-of-bounds
         ↓
         Validation Layer → math check, bounds, category sense
                    ↓
         Confidence Scoring
                    ↓
         Conflict Resolution → agree/disagree/review
                    ↓
         Save to memory if new (source=auto)
```

### Learning Loop
1. Item arrives with ambiguous pack → flagged needs_review
2. User edits price/total via PATCH → unit_memory saves as `source=user_corrected`
3. Next extraction (same product_code) → memory HIT with confidence=1.0
4. Item auto-normalized, NOT sent back to review

### Protection Rules
- `user_corrected` NEVER overwritten by `auto` saves
- `user_corrected` applied directly at confidence=1.0 (no conflict checking)
- Only rejected if multiplier falls outside bounds (0.5–5000)
- Auto parsers can still override other auto mappings (latest wins)

### DB Schema: `unit_memory`
```json
{
  "vendor_key": "SYSCO",
  "product_code": "8880001",
  "restaurant_id": "...",
  "canonical_unit": "lb",
  "multiplier": 10.0,
  "pack_size": "2/5 LB",
  "parse_method": "user_corrected",
  "source": "user_corrected",
  "version": 1,
  "corrected_by_user_id": "8245ae5d-...",
  "corrected_by_name": "Demo User",
  "last_corrected_at": "2026-04-21T04:35:15+00:00",
  "times_used": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

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
- Unit Normalization + Canonical Unit
- Product Memory with cross-format consistency
- Layered Decision Engine (validation + confidence + conflict)
- **Manual-to-Memory Learning Loop (user_corrected truth)**

## Upcoming Tasks
### P0
- Milestone 3 (user to define)
### P2
- Smart Market Insights, AI Chat Assistant, Trash/Restore, Salaries OCR

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
