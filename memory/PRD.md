# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Image preprocessing: orientation fix, deskew, enhancement, standardization
- Document type classification: simple_receipt, structured_invoice, vendor_specific, multi_page_pdf
- Dual pricing mode detection: CASE_PRICE vs WEIGHT_BASED
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory with full audit UI
- Correction hints (user-controlled, no auto-apply)
- Review lifecycle with guided correction suggestions + Fix All Issues
- Issue type classification: math, pack, name, suspicious, missing, review

## Architecture
- Backend: FastAPI modular (core/, routes/, services/)
- Frontend: React + TailwindCSS + Shadcn UI
- Database: MongoDB
- LLM: OpenAI GPT-5.2 via emergentintegrations
- Image: Tesseract 5.3.0 (OSD), OpenCV, Pillow, NumPy

## Completed Features
- [x] Clean Backend V2 Migration
- [x] Normalization Layer + Correction Memory V1
- [x] "Save Now, Review Later" + Quick Review UI
- [x] Invoice Sorting, Invoice-level review_status
- [x] Hard Invoice Robustness Layer
- [x] Guided Correction Suggestions V1 + Fix All Issues
- [x] Pricing Mode Detection & $/LB Fix
- [x] Correction Layer Phase 1: Capture + Visibility
- [x] Correction Layer Phase 2: Correction Hints
- [x] Correction Memory UI — Full audit/management page
- [x] Image Preprocessing Phase 1: Orientation + Deskew + Enhancement (2026-04-01)
- [x] Document Type Classification Phase 2 (2026-04-02)
  - Rule-based classifier: layout analysis (line count, text density, horizontal lines, content fill, width)
  - Types: simple_receipt, structured_invoice, vendor_specific, multi_page_pdf
  - Priority: multi_page_pdf > vendor_specific > layout-based
  - Scoring: lines>=15 (+3), density>0.02 (+1), h_lines>0.003 (+2), width>800 (+1). Score>=4 = structured
  - Routing scaffold: PARSER_ROUTES maps to parser.* module paths
  - Stored in receipt doc + API response (document_classification, parser_route)
  - No extraction logic changes

## Known Issues (Parked)
- Old pytest suite failures — deferred by user
- bcrypt.__about__ warning in backend startup logs

## Upcoming Tasks
- Phase 3: Parser-specific handling per document type (when ready)
- Integrate loose match keys into vendor comparison

## Future/Backlog
- AI Chat Assistant Page Polish
- OCR/Image Upload support for Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
