# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, plus a multi-user permissions and accountability model for team operation.

## Architecture
```
/app/
├── backend/
│   ├── core/
│   │   ├── auth.py (JWT auth, password hashing)
│   │   ├── permissions.py (NEW — visibility/action perms, data scope, soft-delete helpers)
│   │   ├── models.py (Pydantic models with data_scope field)
│   │   ├── database.py (MongoDB connection)
│   ├── routes/
│   │   ├── auth.py (Auth + User CRUD with permissions/scope)
│   │   ├── sales.py (Scope-filtered, soft-delete, ownership fields)
│   │   ├── other_expenses.py (Scope-filtered, soft-delete, ownership fields)
│   │   ├── records.py (Scope-filtered, ownership fields)
│   │   ├── upload.py (Extraction pipeline with ownership fields)
│   │   ├── profit_dashboard.py (AI insights)
│   ├── services/
│   │   ├── usfoods_structural.py (2-phase structural extraction)
│   │   ├── unit_normalizer.py, llm_rate_limiter.py, etc.
│   ├── migrations/
│   │   ├── backfill_ownership.py (Field renaming + backfill)
├── frontend/src/
│   ├── App.js (PermRoute for route-level permission enforcement)
│   ├── components/Layout.js (Sidebar filters by visibility permissions)
│   ├── contexts/AuthContext.js (Login fetches permissions via /auth/me)
│   ├── pages/
│   │   ├── DashboardPage.js (Default month = All Months)
│   │   ├── UserManagementPage.js (Visibility perms, Data Scope, Action perms)
│   │   ├── SalesPage.js (Created By + Source columns)
```

## Permission Model

### Visibility Permissions (8)
| Page | Manager | Accountant | Cashier | Staff |
|------|---------|------------|---------|-------|
| Dashboard | Y | Y | Y | Y |
| Sales | Y | Y | Y | N |
| Expenses | Y | Y | N | N |
| Reports | Y | Y | N | N |
| Records Library | Y | Y | Y (own) | Y (own) |
| Vendors | Y | Y | Y (view) | N |
| Items | Y | Y | Y (view) | N |
| Users/Mgmt | Y | N | N | N |

### Data Scope
- Manager/Accountant: `all` (sees all records)
- Cashier/Staff: `own` (sees only own records)

### Action Permissions (13)
- Sales: add/edit/delete (Cashier can add+edit own, Manager can delete)
- Expenses: add/edit/delete (Accountant can add+edit, Manager can delete)
- Files: upload, view/export reports, view records
- Management: vendors, items, users

### Enforcement
- Backend: `require_permission()` dependency on each route
- Backend: `apply_scope_filter()` on every query
- Backend: `apply_soft_delete_filter()` excludes deleted records
- Frontend: `PermRoute` redirects unauthorized URL access
- Frontend: Sidebar filters nav items by visibility permissions

### Soft-Delete
- Sales and Expenses use soft-delete (status="deleted")
- Preserves: deleted_at, deleted_by_user_id, deleted_by_name
- Only Manager can delete

### Ownership Fields (all transactional collections)
- `created_by_user_id` — user ID who created the record
- `created_by_name` — display name
- `source_type` — "manual" | "upload" | "system" | "pos" | "import"
- `created_at` — ISO timestamp

## Extraction Pipeline Trust Rates (Feb 2026)
| Vendor | Clean Input | Phone Photo | False Trusts |
|--------|------------|-------------|--------------|
| Sysco | 100% | 100% | 0 |
| PFG | 100% | 100% | 0 |
| US Foods | 100% | Variable | 0 |

## Completed Work
- Permissions + Accountability model (21 permissions, 4 roles, data scope)
- Soft-delete for sales and expenses
- Ownership + audit trail fields on all collections
- Route-level permission enforcement (backend + frontend)
- Sidebar visibility filtering
- Dashboard default month = All Months
- Created By / Source columns in Sales table
- US Foods 2-phase structural extraction
- Multi-vendor trust gates (zero false trusts)
- Image preprocessing + consensus mechanism
- Migration script for field backfill

## Known Issues
- US Foods dark phone photos: non-deterministic row counts (safe — zero false trusts)
- Emergent Proxy rate limiting on heavy bursts (50+ concurrent)
- upload.py ~2600+ lines (refactoring parked per user direction)

## Upcoming Tasks
### P0
- Obtain real US Foods PDF/clean scan for production validation
- Test permission enforcement with multi-user workflows

### P1
- Scale stress test to 294 images
- Re-enable Product Memory layer

### P2
- Smart Market Insights 3-panel expansion
- AI Chat Assistant polish
- OCR/Image Upload for Salaries tab

## Test Credentials
- Username: demo@test.com / Password: testpassword (manager)

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
