# Changelog

## 2026-03-24 — Critical Stability Bug Fixes (3 bugs)

### Bug 3: Dashboard disappears after reset → FIXED
- **Root cause**: `isEmpty` check returned early with `EmptyDashboard` component that only showed a "Load Demo Data" button, hiding all UI.
- **Fix**: Removed early return. Dashboard always renders full UI (search, quick actions, donut charts, market insights). Empty data banner shows inline with "Load Demo Data" button when no data exists.
- **File**: `DashboardPage.js` lines 901-960

### Bug 2: Save flow crash (DOM insertBefore error) → FIXED
- **Root cause**: `useEffect` triggered `load(false)` immediately when dialog closed (`showAdd=false`), causing DOM table re-render while dialog exit animation was still running.
- **Fix**: All save-refresh `useEffect` hooks now use `setTimeout(300ms)` to defer list refresh until after dialog animation completes. `DuplicateCheck.confirmSave` also defers 300ms.
- **Files**: `ExpensesPage.js` (3 tabs), `SalesPage.js`, `DuplicateCheck.js`

### Bug 1: Empty app first invoice crash → FIXED
- **Root cause**: MongoDB `insert_one` mutates the dict and adds `_id` (ObjectId), which could leak into JSON responses.
- **Fix**: Added `vendor_doc.pop("_id", None)` and `item_doc.pop("_id", None)` after insert.
- **File**: `server.py` lines 1563-1584

## 2026-03-23 — Navigation Update
- Removed "Home" and "Chat Assistant" from sidebar
- Added centered Home button in top header (home icon + "Dashboard" label)

## 2026-03-23 — Dashboard Final Enhancements
- Monthly Sales donut chart alongside spending
- Date filters in all drill-down views
- Quick actions: Add Expense, Sales, Compare Vendors, View Reports
- Empty data banner with "Load Demo Data" inline
