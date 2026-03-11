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
4. Purchase Invoice extraction flow (supplier, date, items, totals)
5. Sales Report extraction flow (date, total, items)
6. Pages: Dashboard, Purchases, Sales, Suppliers, Items, Reports, Chat, Settings
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
- [x] All pages created (Dashboard, Upload, Purchases, Sales, Suppliers, Items, Reports, Chat, Settings)
- [x] Database seeding with realistic demo data
- [x] Premium SaaS UI/UX (dark sidebar, light content, Manrope + IBM Plex Sans fonts)
- [x] CRUD endpoints for purchases, sales, suppliers, items, aliases
- [x] Dashboard summary with period comparisons and top lists
- [x] Reports endpoint (weekly/monthly/yearly)
- [x] Real OCR document extraction via GPT-5.2 Vision (upload endpoint)
- [x] **Chat Assistant — Enhanced (March 11, 2026)**:
  - Categorized quick questions (This Week, Monthly, Yearly, Insights)
  - Real GPT-5.2 integration with rich financial context
  - Financial analyst-style responses (bold metrics, bullets, period comparisons)
  - Formatted message rendering (markdown bold, bullets, numbered lists)
  - Follow-up quick question chips
  - Clear conversation functionality
  - Message persistence via MongoDB

- [x] **Reports Page — Enhanced (March 11, 2026)**:
  - Weekly/Monthly/Yearly tabs with date picker
  - 4 KPI cards (Revenue, Purchases, Profit, Gross Margin) with % change vs previous period
  - Revenue vs Purchases trend chart (area chart)
  - Supplier Spending table (name, total, invoices, avg/invoice)
  - Price Changes table (item, previous, current, % change with directional arrows)
  - PDF download (reportlab) and Excel download (openpyxl) with multi-sheet reports

- [x] **Upload Center Removed — Inline Upload (March 11, 2026)**:
  - Removed Upload Center page, route, and sidebar link
  - Added "Add Purchase" button on Purchases page with dialog: upload zone + manual form + line items CRUD
  - Added "Add Sale" button on Sales page with dialog: upload zone + manual form + menu items CRUD
  - AI extraction (GPT-5.2 Vision) available inline via Browse → Extract flow

## Credentials
- Test: test@demo.com / password123

## Prioritized Backlog

### P1
- Build Item Normalization UI
- Enhance CRUD UI on Purchases/Sales/Suppliers pages

### P2
- Implement Settings page functionality
- Refactoring: extract backend routes into separate files
