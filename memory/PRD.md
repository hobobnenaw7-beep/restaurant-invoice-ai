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
7. Item normalization (raw names -> canonical items)
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
- [x] Backend: GET /api/purchase-decisions computes per-item per-vendor price analysis
- [x] Best vendor identification per item with saving_per_unit calculation
- [x] Weekly price comparison (this week vs last week avg, % change)
- [x] Actionable insights and Summary cards
- [x] Item Price Comparison table with search filter
- [x] Sidebar navigation added as "Smart Purchases"

### Settings Page (March 22, 2026)
- [x] Restaurant Profile, Your Profile, Financial Settings, Notifications, Language & Display, Data Management
- [x] Logo upload with 2MB limit, base64 storage
- [x] All settings persist to MongoDB

### Dashboard — Final Enhancement (March 23, 2026)
- [x] Monthly Spending donut chart with 3 categories: Raw Materials, Salaries, Other
- [x] Monthly Sales donut chart with revenue total and month-over-month % change
- [x] 3-column layout: Spending donut | Sales donut | Market Insights
- [x] Quick Actions: Add Expense, Sales, Compare Vendors, View Reports (Upload Invoice removed)
- [x] Home button centered in top header (home icon + "Dashboard" label), visible on all pages
- [x] Drill-down sheets for all 4 categories (Raw Materials, Salaries, Other, Sales)
- [x] Date range filters (from/to) in all drill-down views with Apply button
- [x] "Where Should I Buy?" item search bar with vendor price comparison
- [x] Market Insights: max 5 actionable alerts sorted by severity
- [x] Data Freshness indicator
- [x] Today's Best Opportunities cards (1 saving + 1 risk)
- [x] Category insights showing month-over-month % changes

### Audit Log System (March 23, 2026)
- [x] Immutable audit log collection in MongoDB
- [x] Tracks 7 action types, 5 entity types
- [x] Manager-only access with paginated, filterable UI
- [x] All CRUD endpoints instrumented

### Floating AI Assistant (March 23, 2026)
- [x] Site-wide chat widget powered by GPT-5.2
- [x] Contextual financial advice based on user data

### Vendor Detail Page (March 19, 2026)
- [x] Clickable vendor rows, purchase records, detail modals, filters

### Expenses (3 tabs)
- [x] Raw Materials, Salaries, Other Expenses: full CRUD, upload/extract, duplicate detection

### Sales
- [x] CRUD with date range support, upload/extract, duplicate detection

### Records Library
- [x] View-only archive with search, date, file type, category filters

### Reports
- [x] 6-tab layout with date range filtering, PDF/Excel export

### Vendors & Items
- [x] Full CRUD with spending totals, price history charts, vendor comparison

### Stability & Performance
- [x] Fixed infinite re-renders, memoized components, stress-tested navigation

## Credentials
- Test: demo@test.com / testpassword

## Prioritized Backlog

### P0
- Implement Real OCR/Document Extraction: Replace mock /api/upload/extract with real AI service

### P1
- AI Chat Assistant Page Polish: improve UX of floating assistant
- Core Workflow Polish: review and harden all main flows

### P2
- Build Item Normalization UI
- Backend Refactoring: extract monolithic server.py (3200+ lines) into modular route files
- Enhance Vendor/Item CRUD (edit purchases, more filters)
