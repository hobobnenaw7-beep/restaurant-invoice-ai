# Changelog

## 2026-03-25 — Receipt Extraction Accuracy + Manual Correction Screen

### Backend improvements
- Enhanced GPT prompt with explicit receipt patterns (2×5, 5×2, 2@5, columnar layouts)
- Post-processing now validates qty×price=total for each line item, flags mismatches
- Cross-checks: items_sum vs subtotal, subtotal+tax vs total
- Date normalization via python-dateutil (handles MM/DD/YYYY, DD-MM-YYYY, "March 25, 2026", etc.)
- Returns `_has_warnings`, `_warnings[]`, per-item `_warning`/`_warning_detail`, `_subtotal_warning`, `_total_warning`, `_date_warning`

### Frontend review screen
- Line totals are now EDITABLE (was read-only)
- Auto-recalculation: editing qty or price recalculates line total → subtotal → total
- Editing tax recalculates total
- OCR warning banner (amber) appears when extraction has issues
- Per-item warning highlighting (amber background + detail message)
- Warning flags on date/subtotal/total fields when mismatched
- Button changed to "Confirm & Save" (clear intent)
- Warning metadata stripped before sending to backend

## 2026-03-24 — WebView/In-App Browser insertBefore Crash Fix (FINAL)

### Root cause
WebView/in-app browsers (Instagram, Facebook, LINE, etc.) inject DOM nodes into `document.body`. When React 18 batches Dialog Portal removal with list DOM updates in the same render commit, it encounters unexpected sibling nodes from the browser injection. React's `insertBefore` tries to reference these stale/injected nodes → "The object can not be found here" crash.

Additionally, conditional rendering that swapped between completely different DOM subtrees (empty-state div vs Table div) forced React to unmount/mount entire trees during reconciliation — a fragile operation that fails in non-standard DOM environments.

### Fixes (3 structural changes)
1. **Unified table structure**: All 4 list views (Raw Materials, Salaries, Other Expenses, Sales) ALWAYS render `Table > TableHeader > TableBody`. Empty state = single TableRow. Loading = skeleton TableRows. Data = item TableRows. React only adds/removes rows within a stable parent — never swaps subtrees.
2. **Dialog-first close**: Save flows: `setShowAdd(false)` first (removes Portal), then `load(true)` fire-and-forget. Separates Portal removal from list update into different render commits.
3. **Keep-alive tabs**: Expense category tabs always mounted with CSS `display:none`. No unmount/remount cycles.
4. **Error Boundary**: `StableErrorBoundary` wraps all page content. Catches errors → shows Retry button instead of red crash screen.

### Files changed
- `ExpensesPage.js`: Unified table for all 3 tabs, keep-alive tab rendering, dialog-first save
- `SalesPage.js`: Unified table, dialog-first save
- `App.js`: StableErrorBoundary wrapper
- `StableErrorBoundary.js`: New error boundary component

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
