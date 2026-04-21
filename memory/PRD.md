# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Unit Normalization — Layered Decision Engine (Milestone 2) — COMPLETE

### Architecture
```
Signal 1: Parser (always runs) → parses pack_size text
Signal 2: Memory (always runs) → looks up vendor+product_code
                    ↓
         Validation Layer:
           - Math cross-check (qty × price ≈ total)
           - Multiplier bounds check (0.5 – 5000)
           - Category-unit sense check (meat→lb, eggs→piece)
                    ↓
         Confidence Scoring:
           - Base: 0.7
           - Parser boost: +0.1 for strong methods
           - Memory boost: +0.1 per historical usage
                    ↓
         Conflict Resolution:
           - Agree → high confidence normalized
           - Disagree on unit → needs_review (NEVER blind trust)
           - Multiplier out of bounds → parser wins
           - Only memory available → use if valid
```

### Decision Outcomes
| Scenario | Outcome | Source |
|----------|---------|--------|
| Parser + Memory agree | normalized (0.9 conf) | validated_agreement |
| Only parser (no memory) | normalized (save to memory) | parsed_and_saved |
| Only memory (parser fails) | normalized if valid | memory |
| Unit disagreement | **needs_review** | conflict |
| Multiplier out of bounds | parser wins | parser |
| Both invalid | **needs_review** | conflict |

### Verified Test Cases
1. Unit disagreement (Memory=piece, Parser=lb) → **needs_review** ✓
2. Agreement (Memory=lb/40, Parser=lb/40) → normalized ✓
3. Out-of-bounds multiplier (Memory=9999) → parser wins ✓
4. Memory-only (parser fails) → memory accepted if valid ✓

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
- Product Memory Integration
- **Layered Decision Engine (validation + confidence + conflict resolution)**

## Upcoming Tasks
### P0
- Milestone 3 (user to define)
### P1
- Multi-user workflow testing
### P2
- Smart Market Insights, AI Chat Assistant, Trash/Restore, Salaries OCR

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
