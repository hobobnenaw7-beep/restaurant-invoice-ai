# Restaurant Accountant AI — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI/MongoDB restaurant accounting application with AI-powered OCR invoice extraction.

## Core Requirements
- OCR extraction pipeline (GPT-5.2 via Emergent LLM Key)
- Image preprocessing pipeline: orientation fix, deskew, enhancement, standardization
- Dual pricing mode detection: CASE_PRICE vs WEIGHT_BASED
- Conservative normalization (preserve meaningful product distinctions)
- Correction Memory: store user edits per supplier (name, pack_size, unit_price, total)
- Correction Memory UI: full audit/management per vendor
- Review lifecycle with guided correction suggestions + Fix All Issues
- Invoice-level review_status: clean | warning | error
- Issue type classification: math, pack, name, suspicious, missing, review
- Correction hints: surface stored corrections as user-controlled hints

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
- [x] Correction Layer Phase 1: Capture + Visibility (2026-04-01)
- [x] Correction Layer Phase 2: Correction Hints (2026-04-01)
- [x] Correction Memory UI — Full audit/management page (2026-04-01)
- [x] Image Preprocessing Phase 1: Orientation + Deskew + Enhancement (2026-04-01)
  - Tesseract OSD orientation detection (90/180/270°) with heuristic fallback
  - Projection-profile deskew (±5°)
  - Auto-contrast, background noise cleanup, sharpening, contrast normalization
  - EXIF auto-rotate, margin cropping, median filter noise reduction
  - Graceful fallback on any error

## Known Issues (Parked)
- Old pytest suite failures — deferred by user
- bcrypt.__about__ warning in backend startup logs

## Upcoming Tasks
- Phase 2: Document Type Classification (after preprocessing is stable)
- Integrate loose match keys into vendor comparison

## Future/Backlog
- AI Chat Assistant Page Polish
- OCR/Image Upload support for Salaries tab
- Client-side pack size preview

## Test Credentials
- Email: demo@test.com
- Password: testpassword
