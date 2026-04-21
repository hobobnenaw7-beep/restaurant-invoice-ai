# Invoice AI — Product Requirements Document

## Problem Statement
Build a deterministic, rule-based Invoice Review and Correction Pipeline with a strict "zero false trusted rows" math-first trust gate, multi-user permissions, self-improving product memory, and universal product identity.

## Milestone 3: Universal Product Identity Layer — COMPLETE

### Three-Layer Architecture
```
A. Canonical Product (canonical_products)
   {id, canonical_name, category, attributes, keywords, status}

B. Vendor Product Mapping (vendor_product_mappings)
   {vendor_key, product_code, canonical_product_id, vendor_description, pack_size, source}

C. Alias / Description (product_aliases)
   {normalized_text, canonical_product_id, confidence, source}
```

### Resolution Priority
1. Direct code mapping (vendor+code) → confidence 1.0
2. User-confirmed alias (source=user_corrected) → confidence 1.0
3. Exact normalized text → confidence 0.95
4. Fuzzy keyword match → confidence 0.50-0.80 (low → needs_review)

### Cross-Vendor Example (Verified)
```
Canonical Product: "Chicken Breast Tender Boneless Jumbo" (Poultry)
  SYSCO:7667363   → "SYS CLS CHICKN CVP BRST TENDER JUMBO" (4/10 LB)
  USFOODS:4523871 → "CHICKEN BREAST TNDR BNLS JUMBO" (2/5 LB)
  PFG:PFG12345    → "CHKN BREAST TENDER JUMBO BNLS" (user confirmed)
```

### Initial Product Candidates
Top 20 from 3,205 unique signatures across 9,090 extracted items. Includes:
Container Foam, Chicken Gizzard, Chicken Wing, Ketchup Packet, Lemonade, Okra, etc.

### API Endpoints
- POST /api/products/generate-initial — Analyze data, generate candidates
- GET/POST /api/products/canonical — List/create products
- POST /api/products/canonical/{id}/vendor-mapping — Add vendor mapping
- POST /api/products/canonical/{id}/alias — Add text alias
- POST /api/products/resolve — Resolve item to canonical product
- POST /api/products/confirm-link — User confirms vendor=canonical link

### Files
- /app/backend/services/product_identity.py — Core identity engine
- /app/backend/routes/product_identity.py — API routes

## Completed Work
All Milestone 1-3 deliverables complete. See CHANGELOG.md for details.

## Upcoming Tasks
### P0
- Integrate product identity into extraction pipeline (auto-resolve during upload)
- Build Product Identity management UI
### P2
- Smart Market Insights, AI Chat Assistant, Trash/Restore

## Test Credentials
- Manager: demo@test.com / testpassword
- Accountant: accountant@test.com / testpass123

## 3rd Party Integrations
- OpenAI GPT-5.2 (Vision) — uses Emergent LLM Key
