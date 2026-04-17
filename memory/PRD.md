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
│   │   ├── upload.py (Extraction pipeline with ownership fields)
│   │   ├── settings.py (Manager-only reset with password verification)
│   │   ├── profit_dashboard.py (AI insights)
│   ├── services/
│   │   ├── usfoods_structural.py (2-phase structural extraction)
│   │   ├── unit_normalizer.py, llm_rate_limiter.py, audit.py, approval.py
│   ├── tests/
│   │   ├── stress_test_294.py (Batch execution script)
│   │   ├── stress_test_294_report.md (Final report)
├── frontend/src/
│   ├── App.js (PermRoute, SmartLanding, NoAccessPage — permission-aware routing)
│   ├── components/Layout.js (Sidebar filters by visibility permissions)
│   ├── contexts/AuthContext.js (Login fetches permissions via /auth/me)
│   ├── pages/
│   │   ├── DashboardPage.js (Default month = All Months)
│   │   ├── UserManagementPage.js (Visibility perms, Data Scope, Action perms)
│   │   ├── SalesPage.js (Created By + Source + Status columns)
│   │   ├── ExpensesPage.js (Created By + Status columns)
│   │   ├── RecordsLibraryPage.js (Created By + Source + Status columns)
│   │   ├── SettingsPage.js (Manager-only Data Management with password+RESET confirmation)
```

## Permission Model — APPROVED FOR PRODUCTION

### Role Matrix (66/66 tests passed)
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

### Enforcement
- Backend: `require_permission()` + `apply_scope_filter()` + `apply_soft_delete_filter()`
- Frontend: `PermRoute` + sidebar filtering + `SmartLanding`
- Soft-delete preserves audit trail (deleted_at, deleted_by_user_id)
- Ownership fields: created_by_user_id, created_by_name, source_type, created_at

## Extraction Pipeline — STRESS TESTED

### 294-Image Stress Test Results (April 17, 2026)
| Metric | Value |
|--------|-------|
| Total images | 294 |
| Success | 152 (51.7%) |
| Partial | 109 (37.1%) |
| Failed | 33 (11.2%) |
| False trusts | **0** |
| Runtime | 91.9 min (18.8s avg) |

### Core Vendor Performance
| Vendor | Images | Success Rate | False Trusts |
|--------|--------|-------------|--------------|
| Sysco | 148 | 99.3% | 0 |
| US Foods | 78 | 84.6% | 0 |
| PFG | 25 | 96.0% | 0 |
| **Core Total** | **251** | **94.4%** | **0** |

### Dashboard Performance at Scale
- All Months: 149.6ms avg (1,270+ records)
- Baseline: ~114ms
- Verdict: +31%, acceptable

### Audit Coverage
- 100% of all records tagged with user_id, source_type, created_at
- 0 missing audit fields across 1,270 receipts and 8,617 items

## Completed Work
- Permissions + Accountability model (21 permissions, 4 roles, data scope) — APPROVED
- Soft-delete for sales and expenses — APPROVED
- Route-level permission enforcement (backend + frontend) — APPROVED
- Permission-aware landing page (no blank screens) — APPROVED
- Secured Reset All Data (manager-only, password+RESET confirmation) — APPROVED
- Forgot Password flow (Manager-only, 15-min token, rate limited) — APPROVED
- Consistent table layouts (Expenses/Sales/Records with Created By, Source, Status)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- Image preprocessing + consensus mechanism
- Credit/discount row handling (negative totals preserved)
- **294-image stress test — COMPLETE** (Phase 3 finalized)

## Upcoming Tasks
### P0
- Widen US Foods structural parser trigger to capture all vendor name variants
- Add minimum image quality gate (reject <100KB with warning)

### P1
- Re-enable Product Memory Layer (extraction baseline now proven)
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
