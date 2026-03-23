# Restaurant Accountant AI — PRD

## Original Problem Statement
Build a modern full-stack web app called "Restaurant Accountant AI" — an AI-powered accounting and financial analysis tool for small/medium restaurants. Help owners upload purchase invoices and sales reports (images/PDFs), extract structured data via AI, review/edit/save it, and generate financial reports.

## Tech Stack
- **Backend**: FastAPI, Python, MongoDB, Pydantic, JWT Auth
- **Frontend**: React, React Router, TailwindCSS, shadcn/ui, Recharts
- **AI**: OpenAI GPT-5.2 via emergentintegrations (Emergent LLM Key)
- **Architecture**: Full-stack monorepo, Supervisor-managed

## Core Requirements
1. JWT email/password authentication
2. Dashboard with summary cards, top 5 lists, price alerts, weekly/monthly comparisons
3. Upload Center for image/PDF invoices and sales reports
4. Purchase Invoice extraction flow (vendor, date, items, totals)
5. Sales Report extraction flow (date, total, items)
6. Pages: Dashboard, Expenses, Sales, Vendors, Items, Reports, Chat, Settings
7. Item normalization (raw names → canonical items)
8. Weekly/Monthly/Yearly reports with financial metrics
9. Alerts for price/spending changes
10. AI Chat Assistant using GPT-5.2
11. Modern dark-sidebar/light-content SaaS design
12. Charts for trends and comparisons
13. Demo data seeding

## What's Been Implemented

### Authentication & Users
- [x] JWT authentication (register/login/me)
- [x] Multi-user support with roles (Manager, Accountant, Cashier, Staff)
- [x] 13 granular permissions per user
- [x] Approval workflow (pending/approved/rejected records)
- [x] User Management page (Manager-only)
- [x] Approvals page for reviewing pending records

### OCR & Document Extraction (March 17, 2026)
- [x] Real OCR via OpenAI GPT-5.2 Vision (NOT MOCKED)
- [x] Multi-page PDF support (up to 5 pages)
- [x] Excel/CSV parsing with intelligent column mapping
- [x] Image upload support (JPEG, PNG, WebP)
- [x] Post-processing validation: auto-fills missing qty, unit_price, total
- [x] Better prompts for accurate extraction
- [x] Support in both Expenses (Raw Materials) and Sales forms

### Smart Purchase Decisions (March 23, 2026)
- [x] Backend: GET /api/purchase-decisions computes per-item per-vendor price analysis from real purchase data
- [x] For each item: tracks all vendor prices, latest price, average price, purchase count
- [x] Best vendor identification per item with saving_per_unit calculation
- [x] Weekly price comparison (this week vs last week avg, % change)
- [x] Actionable insights: "Best vendor for X: Y (saving $Z/unit)" and "X price increased by N%"
- [x] Summary cards: Potential Weekly Savings, Vendor Switch Opportunities, Weekly Price Changes
- [x] Item Price Comparison table with search filter
- [x] Sidebar navigation added as "Smart Purchases"

### Settings Page (March 22, 2026)
- [x] Restaurant Profile: name, logo upload, phone, email, address
- [x] Your Profile: editable name, read-only email
- [x] Financial Settings: currency (9 options), default tax rate, default expense category
- [x] Notification Settings: master toggle + 3 sub-toggles (price increase, cheaper vendor, not ordered)
- [x] Language & Display: language (6 options), date format (3 options)
- [x] Data Management: Reset All Data with DELETE confirmation dialog
- [x] Logo upload with 2MB limit, base64 storage
- [x] All settings persist to MongoDB restaurant document

### Critical Frontend Runtime Bug Fixes (March 19, 2026)
- [x] Fixed "Maximum call stack size exceeded": replaced all setTimeout-based refresh with savedRef + useEffect pattern
- [x] Fixed "insertBefore / insertOrAppendPlacementNode": no DOM structure change during dialog exit (background refresh without skeleton)
- [x] Fixed line item reconciliation: stable _key per item instead of array index
- [x] Fixed DuplicateCheck: removed stacked setTimeout(150ms), uses useRef for pendingSave
- [x] Fixed dialog dismiss during save: onOpenChange blocked when saving/extracting
- [x] All 13 critical tests passed with ZERO console errors

### Vendor Detail Page (March 19, 2026)
- [x] Vendor list rows are clickable → navigates to /vendors/:id
- [x] Detail page shows: vendor name, total spent, invoice count, contact, phone, email, address
- [x] All purchase records listed with date, invoice #, item count, total, approval status
- [x] Purchase detail modal: full line items (name, qty, unit, price, total) + subtotal/tax/total
- [x] Delete from vendor detail removes record and updates totals immediately
- [x] Search by invoice number filter
- [x] Date range filter (from/to)
- [x] Back navigation to vendors list
- [x] Empty state when vendor has no purchases

### Bug Fixes (March 19, 2026)
- [x] Bug 1: App works correctly from completely empty database — all endpoints return valid data, dashboard shows proper empty state, all CRUD operations work from zero records
- [x] Bug 2: Auto-create vendors and items from expenses — when saving a purchase with a new vendor/item name, they are automatically added to the master Vendors and Items lists with case-insensitive dedup

### Stability & Performance (March 17, 2026)
- [x] Fixed infinite re-render risk: moved NavLink and SidebarContent outside Layout as memo'd components
- [x] Fixed NotificationPanel useEffect loop: used ref for onClose callback instead of dependency
- [x] Memoized Dashboard: load (useCallback), smartAlerts (useMemo), SmartAlertsSection (memo), CustomTooltip (memo)
- [x] Memoized Layout callbacks: handleCloseAlerts, handleCloseMobile, handleToggleAlerts (useCallback)
- [x] Fixed Expenses page runtime error: deferred list refresh after dialog close (all 3 tabs + Sales page)
- [x] Fixed DuplicateCheck confirmSave timing: deferred save after warning dialog exit animation
- [x] Stress-tested: rapid navigation through 7 pages + rapid bell toggling — zero crashes

### Financial Calculation Accuracy (March 17, 2026)
- [x] Dashboard and Reports show consistent numbers (bounded date ranges)
- [x] All report endpoints filter by approval_status (approved only)
- [x] Expenses form auto-calculates subtotal and total from line items
- [x] Tax field auto-updates total
- [x] Subtotal = sum of line item totals, Total = subtotal + tax

### Dashboard Enhancement — Expense Visualization (March 23, 2026)
- [x] Monthly Spending donut chart with 3 categories: Raw Materials, Salaries, Other
- [x] Total expense in center with month-over-month % change
- [x] Per-category dollar amounts and percentages in legend
- [x] Category insights: auto-generated messages like "Raw Materials decreased by 33.5% this month"

### Dashboard Radical Cleanup (March 23, 2026)
- [x] Removed all accounting clutter: Sales cards, Net Profit, Weekly Sales vs Purchases chart, Top Items, Top Vendors, Expense Trends chart
- [x] Removed Utilities category completely from all charts and backend logic
- [x] Added "Where Should I Buy?" item search bar with debounced search
- [x] Item search shows all vendors for an item, prices, cheapest option with BEST badge
- [x] Backend: new GET /api/dashboard/item-search?q= endpoint with per-vendor price analysis
- [x] Market Insights section: max 5 actionable alerts (price increases, cheaper vendors, not ordered)
- [x] Dashboard answers ONLY: "Where am I spending?" and "Where should I buy today?"
- [x] Smart Alerts limited to 5 items sorted by severity (high first)
- [x] Notification bell with alert dropdown

### Expenses (3 tabs)
- [x] Raw Materials: CRUD, upload/extract, auto-calculation, vendor autocomplete
- [x] Salaries: CRUD, payment tracking
- [x] Other Expenses: CRUD with categories (Rent, Electricity, etc.)
- [x] Duplicate entry detection for all 3 types

### Sales
- [x] CRUD with date range support (from/to dates)
- [x] Upload/extract from images, PDFs, Excel
- [x] Extraction properly sets date_from/date_to
- [x] Duplicate entry detection

### Records Library
- [x] View-only archive (uploads happen through Sales/Expense forms)
- [x] Sales Files and Expense Files tabs
- [x] Search, date filter, file type filter
- [x] Expense Category filter on Expense Files tab
- [x] File preview, download, delete
- [x] Auto-linked to transactions

### Reports
- [x] 6-tab layout: Sales, Raw Materials, Salaries, Other Expenses, Vendors, Profit
- [x] Date range filtering
- [x] PDF and Excel export
- [x] All reports filter approved records only

### Vendors & Items
- [x] Vendors: CRUD with spending totals and invoice counts
- [x] Items: CRUD with aliases, price history charts, vendor comparison
- [x] Price alert generation on new purchases

### Other Features
- [x] Premium SaaS UI/UX (dark sidebar, light content)
- [x] Demo data seeding
- [x] Duplicate file detection in Records Library
- [x] Sortable columns throughout

## Credentials
- Test: demo@test.com / testpassword

## Prioritized Backlog

### P1
- Core Workflow Polish: review and harden Expenses, Sales, Records, Reports, Vendors/Items flows
- Implement Real Chat Assistant Backend (GPT-5.2 with financial data context)

### P2
- Implement Audit Log (track user/record actions)
- Build Item Normalization UI
- Enhance Vendor/Item CRUD (edit purchases, more filters)
- Backend Refactoring: extract monolithic server.py into modular route files

### Deferred (by user)
- AI Chat Assistant backend (deferred)
- Audit log (deferred)
