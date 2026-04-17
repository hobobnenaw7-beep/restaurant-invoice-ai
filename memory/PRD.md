# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/
│   │   ├── auth.py (JWT auth, password hashing)
│   │   ├── permissions.py (visibility/action perms, data scope, soft-delete helpers)
│   │   ├── models.py (Pydantic models with data_scope field)
│   │   ├── database.py (MongoDB connection)
│   ├── routes/
│   │   ├── auth.py (Auth + User CRUD with permissions/scope)
│   │   ├── sales.py (Scope-filtered, soft-delete, ownership fields)
│   │   ├── other_expenses.py (Scope-filtered, soft-delete, ownership fields)
│   │   ├── records.py (Scope-filtered, ownership fields)
│   │   ├── upload.py (Extraction pipeline with multi-signal routing)
│   │   ├── settings.py (Manager-only reset with password verification)
│   │   ├── profit_dashboard.py (AI insights)
│   ├── services/
│   │   ├── vendor_detection.py (Multi-signal detection + confidence routing)
│   │   ├── usfoods_structural.py (2-phase structural extraction)
│   │   ├── unit_normalizer.py, llm_rate_limiter.py, audit.py, approval.py
│   ├── tests/
│   │   ├── stress_test_294.py, stress_test_294_report.md
│   │   ├── usfoods_retest_subset.py, vendor_detection_report.md
├── frontend/src/
│   ├── App.js (PermRoute, SmartLanding, NoAccessPage)
│   ├── components/Layout.js (Sidebar filters by visibility permissions)
│   ├── contexts/AuthContext.js
│   ├── pages/ (Dashboard, Sales, Expenses, Records, Settings, UserManagement, etc.)
```

## Permission Model — APPROVED FOR PRODUCTION
| Permission | Manager | Accountant | Cashier | Staff |
|-----------|---------|------------|---------|-------|
| view_dashboard | Y | Y | Y | Y |
| view_sales | Y | Y | Y | N |
| view_expenses | Y | Y | N | N |
| view_reports | Y | Y | N | N |
| view_records | Y | Y | Y | Y |
| view_vendors | Y | Y | Y | N |
| view_items | Y | Y | Y | N |
| view_users | Y | N | N | N |
| data_scope | all | all | own | own |
| can_delete_sales | Y | N | N | N |
| can_delete_expenses | Y | N | N | N |

## Vendor Detection — Multi-Signal (April 17, 2026)
Three signals per invoice:
- **Name Match** (weight 0.55): 16+ variants per vendor
- **Content Clues** (weight 0.25): Domain/URL/account patterns
- **Layout Signature** (weight 0.20): Column header keywords
- Routing threshold: 0.40 confidence
- Full audit trail stored on every receipt

## Extraction Pipeline — Stress Tested
### 294-Image Stress Test (Phase 3)
| Metric | Value |
|--------|-------|
| Total images | 294 |
| Success | 152 (51.7%) |
| Partial | 109 (37.1%) |
| Failed | 33 (11.2%) |
| False trusts | **0** |

### Core Vendor Performance
| Vendor | Success Rate | False Trusts |
|--------|-------------|--------------|
| Sysco (148) | 99.3% | 0 |
| US Foods (78) | 84.6% | 0 |
| PFG (25) | 96.0% | 0 |

### Vendor Detection Upgrade Results (US Foods Re-test)
| Metric | Before | After |
|--------|--------|-------|
| Files routed to structural parser | 0/12 | **11/11** |
| Previously-failed files recovered | — | **3 (2 SUCCESS, 1 PARTIAL)** |
| False trusts | 0 | 0 |

## Completed Work
- Permissions + Accountability model (21 permissions, 4 roles, data scope)
- Soft-delete for sales and expenses
- Route-level permission enforcement (backend + frontend)
- Permission-aware landing page
- Secured Reset All Data (manager-only, password+RESET confirmation)
- Forgot Password flow (Manager-only, 15-min token, rate limited)
- Consistent table layouts (Created By, Source, Status columns)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- Credit/discount row handling (negative totals preserved)
- 294-image stress test — COMPLETE
- **Multi-signal vendor detection + confidence-based routing — COMPLETE**

## Upcoming Tasks
### P0
- Image preprocessing enhancement for dark US Foods photos (contrast/brightness)
- Image quality gate (warn on low-entropy <100KB images)

### P1
- Re-enable Product Memory Layer (extraction baseline proven)
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
- NoDash: nodash@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
