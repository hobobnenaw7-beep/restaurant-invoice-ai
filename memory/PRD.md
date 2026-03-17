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

### Stability & Performance (March 17, 2026)
- [x] Fixed infinite re-render risk: moved NavLink and SidebarContent outside Layout as memo'd components
- [x] Fixed NotificationPanel useEffect loop: used ref for onClose callback instead of dependency
- [x] Memoized Dashboard: load (useCallback), smartAlerts (useMemo), SmartAlertsSection (memo), CustomTooltip (memo)
- [x] Memoized Layout callbacks: handleCloseAlerts, handleCloseMobile, handleToggleAlerts (useCallback)
- [x] Stress-tested: rapid navigation through 7 pages + rapid bell toggling — zero crashes

### Financial Calculation Accuracy (March 17, 2026)
- [x] Dashboard and Reports show consistent numbers (bounded date ranges)
- [x] All report endpoints filter by approval_status (approved only)
- [x] Expenses form auto-calculates subtotal and total from line items
- [x] Tax field auto-updates total
- [x] Subtotal = sum of line item totals, Total = subtotal + tax

### Dashboard
- [x] Smart Alerts at top (Price Increases, Cheaper Vendors, Not Ordered)
- [x] Summary cards: Today/Week/Month sales, purchases, expenses
- [x] Profit calculation cards
- [x] Top 5 items and vendors
- [x] Weekly trend charts
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
- Implement Real Chat Assistant Backend (GPT-5.2 with financial data context)
- Implement Audit Log (track user/record actions)
- Build Item Normalization UI

### P2
- Implement Settings page functionality
- Enhance Vendor/Item CRUD (edit purchases, more filters)
- Refactoring: extract backend routes into separate files

### Deferred
- AI Chat Assistant backend
- Audit log
- Settings page
