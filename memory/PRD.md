# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Image preprocessing: orientation fix, deskew, enhancement, standardization
- Document type classification: simple_receipt, structured_invoice, vendor_specific, multi_page_pdf
- Layout parser: Tesseract OCR → row detection → column detection → structured line items
- Dual pricing mode detection: CASE_PRICE vs WEIGHT_BASED
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory with full audit UI + correction hints
- Review lifecycle with guided correction suggestions + Fix All Issues
- Issue type classification: math, pack, name, suspicious, missing, review

## Architecture
- Backend: FastAPI modular (core/, routes/, services/)
- Frontend: React + TailwindCSS + Shadcn UI
- Database: MongoDB
- LLM: OpenAI GPT-5.2 via emergentintegrations
- Image: Tesseract 5.3.0 (OSD + OCR), OpenCV, Pillow, NumPy

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
- [x] Image Preprocessing Phase 1: Orientation + Deskew + Enhancement
- [x] Document Type Classification Phase 2
- [x] Parser-Specific Layout Handling Phase 3 (2026-04-02)
  - Tesseract OCR with word-level bounding boxes (run_ocr)
  - Row detection: y-coordinate clustering (detect_rows)
  - Column detection: header keyword scoring + data alignment inference (detect_columns)
  - Vendor parsers: Sysco (fallback for dark headers), PFG (weight-based), US Foods
  - Fallback: _extract_items_simple (splits text/numbers by position)
  - Smart separator filter: preserves header rows with multiple column keywords
  - Integrated into upload pipeline (stores result, returns in API response)
  - Tested on 4 formats: seafood receipt, Sysco, PFG, messy layout (26/26 tests passed)

## Known Issues (Parked)
- Old pytest suite failures — deferred by user
- bcrypt.__about__ warning in backend startup logs

## Upcoming Tasks
- Integrate loose match keys into vendor comparison

## Future/Backlog
- AI Chat Assistant Page Polish
- OCR/Image Upload support for Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
