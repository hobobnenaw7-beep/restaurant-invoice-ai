# Changelog

## 2026-03-24 — Shared first-insert crash fix (insertBefore / insertOrAppendPlacementNode)

### Root causes (2)
1. **Save flow batching**: React 18 automatic batching combined `setItems` (empty→data DOM swap) + `setShowAdd(false)` (Dialog Portal removal) + `setSaving(false)` into ONE render commit. React tried to place new DOM nodes using `insertBefore` with sibling references from the Portal that was simultaneously being torn down.
2. **Tab switching unmount/remount**: Conditional rendering (`{activeTab === 'x' && <Tab />}`) destroyed entire tab components on switch, causing state loss, fresh API calls, and DOM reconstruction conflicts during the empty→skeleton→data transition.

### Fixes
1. **Save flow**: All 4 `doSave` functions now call `setShowAdd(false)` FIRST (closes dialog), then `load(true)` (fire-and-forget). Dialog close + loading=true batch into ONE safe render (Portal removed + skeleton shown). Items arrive later in a SEPARATE render (skeleton→table). No batching conflict.
2. **Tab keep-alive**: All 3 expense tabs are always mounted; inactive tabs hidden with `display:none`. No unmount/remount cycles.
- Files: `ExpensesPage.js`, `SalesPage.js`

## 2026-03-24 — iOS Safari "Maximum call stack size exceeded" Fix

### Root cause (3 issues combined)
1. **`FileReader.readAsDataURL()`** stored 4-16MB base64 strings in React state for iPhone photos (12MP+). On every re-render triggered by form updates, React diffed this massive string in the VDOM. Safari's smaller call stack (~10K frames vs Chrome's ~15K) overflowed during recursive reconciliation.
2. **`ItemAutocomplete` had internal `query` state synced from `value` via `useEffect`**. After extraction populated 10+ items, each autocomplete fired `useEffect → setQuery → re-render`, causing cascading renders.
3. **No double-execution guard** on `handleExtract` — on mobile, tapping Extract could trigger it twice.

### Fixes
- Replaced `FileReader.readAsDataURL()` with `URL.createObjectURL()` — preview uses ~50-byte blob URL, not multi-MB base64
- Added `URL.revokeObjectURL()` cleanup in `clearFile`, `openAdd`, and `openAddForm`
- Made `ItemAutocomplete` fully controlled — removed internal `query` state and `useEffect` sync entirely. Uses `value` prop directly.
- Added `extractingRef` guard to prevent double execution of `handleExtract`
- Added `touchstart` event listener for mobile dropdown close
- Files: `ExpensesPage.js`, `SalesPage.js`

## 2026-03-24 — Deterministic Save Flow (removed setTimeout hacks)

### Architecture change
- **Old**: save → close dialog → useEffect detects close → setTimeout(300ms) → refresh list
- **New**: save → await load(false) while dialog still open → close dialog after list is settled

### What changed
- `ExpensesPage.js` (RawMaterialsTab, SalariesTab, OtherExpensesTab): Removed `savedRef`, removed `useEffect` watching `showAdd`, doSave now does `await load(false)` before `setShowAdd(false)`
- `SalesPage.js`: Same pattern
- `DuplicateCheck.js`: `confirmSave` removed setTimeout, calls saveFn directly

### Why this is correct
- List refresh happens while dialog DOM is stable (no animation conflict)
- Dialog closes only after data is settled (deterministic)
- No race conditions, no timing assumptions, no cleanup required

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
