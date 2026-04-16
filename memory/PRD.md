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
│   ├── migrations/
│   │   ├── backfill_ownership.py (Field renaming + backfill)
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
| view_dashboard | ✅ | ✅ | ✅ | ✅ |
| view_sales | ✅ | ✅ | ✅ | ❌ |
| view_expenses | ✅ | ✅ | ❌ | ❌ |
| view_reports | ✅ | ✅ | ❌ | ❌ |
| view_records | ✅ | ✅ | ✅ | ✅ |
| view_vendors | ✅ | ✅ | ✅ | ❌ |
| view_items | ✅ | ✅ | ✅ | ❌ |
| view_users | ✅ | ❌ | ❌ | ❌ |
| data_scope | all | all | own | own |
| can_delete_sales | ✅ | ❌ | ❌ | ❌ |
| can_delete_expenses | ✅ | ❌ | ❌ | ❌ |

### Enforcement
- Backend: `require_permission()` + `apply_scope_filter()` + `apply_soft_delete_filter()`
- Frontend: `PermRoute` + sidebar filtering + `SmartLanding`
- Soft-delete preserves audit trail (deleted_at, deleted_by_user_id)
- Ownership fields: created_by_user_id, created_by_name, source_type, created_at

## Extraction Pipeline Trust Rates
| Vendor | Clean Input | Phone Photo | False Trusts |
|--------|------------|-------------|--------------|
| Sysco | 100% | 100% | 0 |
| PFG | 100% | 100% | 0 |
| US Foods | 100% | Variable | 0 |

## Completed Work
- Permissions + Accountability model (21 permissions, 4 roles, data scope) — APPROVED
- Soft-delete for sales and expenses — APPROVED
- Route-level permission enforcement (backend + frontend) — APPROVED
- Permission-aware landing page (no blank screens) — APPROVED
- Secured Reset All Data (manager-only, password+RESET confirmation) — APPROVED
- Consistent table layouts (Expenses/Sales/Records with Created By, Source, Status)
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- Image preprocessing + consensus mechanism

## Upcoming Tasks
### P0
- Obtain real US Foods PDF for extraction validation
- Test multi-user workflows with production data

### P1
- Scale stress test to 294 images
- Re-enable Product Memory layer

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
