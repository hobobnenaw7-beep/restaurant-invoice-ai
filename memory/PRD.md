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
- [x] Full-stack scaffolding (FastAPI + React + MongoDB)
- [x] JWT authentication (register/login/me)
- [x] All pages created (Dashboard, Expenses, Sales, Vendors, Items, Reports, Chat, Settings)
- [x] Database seeding with realistic demo data
- [x] Premium SaaS UI/UX (dark sidebar, light content, Manrope + IBM Plex Sans fonts)
- [x] CRUD endpoints for purchases, sales, vendors, items, aliases
- [x] Dashboard summary with period comparisons and top lists
- [x] Reports endpoint (weekly/monthly/yearly)
- [x] Real OCR document extraction via GPT-5.2 Vision (upload endpoint)
- [x] Chat Assistant with GPT-5.2 integration
- [x] Reports Page with KPI cards, trend charts, vendor spending, price intelligence
- [x] Inline Upload (removed standalone Upload Center)
- [x] Smart Alerts System on Dashboard
- [x] Vendor Price Comparison on Reports page
- [x] Excel/CSV Upload Support
- [x] Expenses page refactor (Raw Materials, Salaries, Other Expenses tabs)
- [x] **Suppliers → Vendors Rename (March 12, 2026)**:
  - Renamed "Suppliers" to "Vendors" across all user-facing UI
  - Sidebar nav, page title, description, buttons, table headers, form labels, search placeholders
  - Updated Dashboard "Top Vendors" card, Reports "Vendor Spending" table, Chat quick questions
  - Backend API endpoints unchanged (`/api/suppliers`) — only UI labels changed

- [x] **Items Page List View (March 12, 2026)**:
  - Converted card/grid layout to structured table/list layout
  - Columns: Item Name, Category, Aliases (badges, max 4 shown), Actions (Aliases, Edit, Delete)
  - Compact, scannable rows ideal for accounting/admin use

- [x] **Item Name Autocomplete in Expenses Form (March 12, 2026)**:
  - Replaced plain text input with searchable autocomplete dropdown in Add Raw Material Purchase form
  - Fetches canonical items + aliases from Items database when dialog opens
  - Type-to-filter with dropdown suggestions; select existing or type new item freely

- [x] **Price Tracking System (March 12, 2026)**:
  - Backend `GET /api/items/{item_id}/price-history` — computes price history from purchases by matching canonical name + aliases
  - Returns records (vendor, date, unit_price, qty, unit), trend (avg price per date), and summary stats (avg/min/max/vendors)
  - Frontend: "Prices" button on each item row → opens Price History dialog with 4 KPI cards, Recharts line chart, and scrollable purchase records table
  - Tested: 100% pass rate (8/8 backend, all frontend features verified)

- [x] **Vendor Price Comparison (March 14, 2026)**:
  - Backend `GET /api/prices/vendor-comparison` — per-item, per-vendor latest price comparison with canonical name + alias resolution
  - Returns items sorted by vendor count and savings potential, each with vendors sorted cheapest first, best_vendor, savings_pct
  - Frontend: "Vendor Price Comparison" card grid on Items page below items table — each card shows item name, savings badge, vendor rows with price/date/unit/purchases, green highlight + BEST PRICE badge on cheapest vendor
  - Tested: 100% pass rate (9/9 backend, 11/11 frontend features verified)

- [x] **Price Alert System (March 14, 2026)**:
  - Backend: POST /api/purchases now auto-generates price_increase alerts when item prices exceed previous prices (uses canonical + alias matching)
  - Each alert stores: item_name, previous_price, new_price, change_pct, vendor, date, severity
  - New endpoints: GET /api/alerts/prices, DELETE /api/alerts/prices/{aid}
  - Dashboard summary returns price_alerts array
  - Frontend: "Price Alerts" section on dashboard with red icon, alert count badge, dismissable alert cards showing item name, price change, percentage, vendor, date, HIGH badge for >15%
  - Tested: 100% pass rate (12/12 backend, all frontend verified)

- [x] **Automatic Profit Calculation (March 14, 2026)**:
  - Backend: Dashboard summary now returns daily_profit, weekly_profit, monthly_profit, yearly_profit + previous period comparisons
  - Formula: Net Profit = Total Sales - (Raw Materials + Salaries + Other Expenses)
  - Frontend: "Net Profit" section on dashboard with 4 color-coded cards (green=profit, red=loss), period % change badges, progress bars
  - Tested: 100% pass rate (16/16 backend, all frontend verified)

## Credentials
- Test: demo@test.com / testpassword

## Prioritized Backlog

### P0
- Verify and complete Expenses page refactor (3-tab CRUD, dashboard totals)
- Implement Real OCR/Document Extraction (OpenAI GPT-5.2 Vision)

### P1
- Implement Real Chat Assistant Backend (GPT-5.2 with financial data context)
- Build Item Normalization UI

### P2
- Implement Settings page functionality
- Enhance CRUD UI on Vendors/Items pages
- Refactoring: extract backend routes into separate files
