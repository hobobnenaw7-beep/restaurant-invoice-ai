from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List
import uuid, re, json, base64, io
from datetime import datetime, timezone

from core.database import db, UPLOADS_DIR, LLM_KEY, logger
from core.auth import get_user

router = APIRouter()


def _normalize_date(raw: str) -> str:
    """Try to parse various date formats and return YYYY-MM-DD."""
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()
    from dateutil import parser as dateparser
    try:
        dt = dateparser.parse(raw, dayfirst=False)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        dt = dateparser.parse(raw, dayfirst=True)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return raw


@router.post("/upload/parse-excel")
async def parse_excel(file: UploadFile = File(...), document_type: str = Form("purchase_invoice"), user=Depends(get_user)):
    """Parse Excel/CSV files and extract purchase or sales data."""
    import openpyxl, csv as csv_mod
    try:
        content = await file.read()
        fname = (file.filename or "").lower()
        rows = []

        if fname.endswith('.csv'):
            text = content.decode('utf-8', errors='replace')
            reader = csv_mod.reader(text.strip().splitlines())
            for r in reader:
                rows.append(r)
        elif fname.endswith('.xlsx') or fname.endswith('.xls'):
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else '' for c in r])
            wb.close()
        else:
            raise HTTPException(400, "Unsupported file type. Use .xlsx, .xls, or .csv")

        if len(rows) < 2:
            raise HTTPException(400, "File has no data rows")

        headers_raw = [str(h).strip().lower().replace(' ', '_') for h in rows[0]]
        col_map = {}
        for i, h in enumerate(headers_raw):
            for key, aliases in {
                'supplier': ['supplier', 'supplier_name', 'vendor', 'vendor_name', 'from'],
                'date': ['date', 'invoice_date', 'inv_date', 'purchase_date', 'order_date', 'report_date'],
                'invoice_number': ['invoice', 'invoice_number', 'inv_no', 'invoice_no', 'inv_number', 'invoice#', 'inv#', 'ref', 'reference'],
                'item_name': ['item', 'item_name', 'product', 'product_name', 'description', 'raw_name', 'name', 'menu_item', 'ingredient'],
                'quantity': ['quantity', 'qty', 'count'],
                'unit': ['unit', 'uom', 'measure', 'unit_of_measure'],
                'pack_size': ['pack_weight', 'weight', 'pack_size', 'size', 'pack_wt', 'net_weight', 'pack'],
                'unit_price': ['price', 'unit_price', 'unit_cost', 'cost', 'rate'],
                'total': ['total', 'line_total', 'subtotal', 'ext_price', 'extended_price', 'revenue', 'amount'],
            }.items():
                if h in aliases and key not in col_map:
                    col_map[key] = i

        data_rows = rows[1:]

        def safe_float(val):
            try:
                s = str(val).replace('$', '').replace(',', '').strip()
                return float(s) if s else 0
            except (ValueError, TypeError):
                return 0

        def safe_date(val):
            s = str(val).strip()
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(s[:10], fmt).strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    continue
            return datetime.now(timezone.utc).strftime('%Y-%m-%d')

        if document_type == "purchase_invoice":
            items_parsed = []
            for row in data_rows:
                if len(row) <= max(col_map.values(), default=0):
                    row.extend([''] * (max(col_map.values(), default=0) + 1 - len(row)))
                item_name = row[col_map['item_name']].strip() if 'item_name' in col_map else ''
                if not item_name:
                    continue
                qty = safe_float(row[col_map['quantity']]) if 'quantity' in col_map else 1
                up = safe_float(row[col_map['unit_price']]) if 'unit_price' in col_map else 0
                tot = safe_float(row[col_map['total']]) if 'total' in col_map else (qty * up)
                if tot == 0 and qty > 0 and up > 0:
                    tot = qty * up
                if up == 0 and tot > 0 and qty > 0:
                    up = tot / qty

                pack_size_raw = str(row[col_map['pack_size']]).strip() if 'pack_size' in col_map else ''
                unit_raw = row[col_map['unit']].strip().upper() if 'unit' in col_map else ''
                if unit_raw and not pack_size_raw:
                    pack_size_raw = unit_raw

                items_parsed.append({
                    "supplier": row[col_map['supplier']].strip() if 'supplier' in col_map else '',
                    "date": safe_date(row[col_map['date']]) if 'date' in col_map else datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    "invoice_number": row[col_map['invoice_number']].strip() if 'invoice_number' in col_map else '',
                    "raw_name": item_name,
                    "quantity": qty,
                    "pack_size": pack_size_raw,
                    "unit_price": round(up, 2),
                    "total": round(tot, 2),
                })

            groups = {}
            for it in items_parsed:
                key = (it['supplier'] or 'Unknown', it['date'], it['invoice_number'])
                groups.setdefault(key, []).append(it)

            if not groups and items_parsed:
                groups[('Unknown', items_parsed[0]['date'], '')] = items_parsed

            if len(groups) <= 1:
                all_items = [it for items in groups.values() for it in items]
                first = all_items[0] if all_items else {}
                subtotal = round(sum(it['total'] for it in all_items), 2)
                return {"extracted_data": {
                    "supplier_name": first.get('supplier', ''),
                    "invoice_date": first.get('date', datetime.now(timezone.utc).strftime('%Y-%m-%d')),
                    "invoice_number": first.get('invoice_number', ''),
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "pack_size": it.get('pack_size', ''), "unit_price": it['unit_price'], "total": it['total']} for it in all_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(all_items)}
            else:
                first_key = list(groups.keys())[0]
                first_items = groups[first_key]
                subtotal = round(sum(it['total'] for it in first_items), 2)
                return {"extracted_data": {
                    "supplier_name": first_key[0],
                    "invoice_date": first_key[1],
                    "invoice_number": first_key[2],
                    "items": [{"raw_name": it['raw_name'], "quantity": it['quantity'], "pack_size": it.get('pack_size', ''), "unit_price": it['unit_price'], "total": it['total']} for it in first_items],
                    "subtotal": subtotal, "tax": 0, "total": subtotal,
                }, "document_type": document_type, "row_count": len(items_parsed), "purchase_groups": len(groups),
                   "message": f"Found {len(groups)} purchases with {len(items_parsed)} total items. Showing the first purchase."}
        else:
            items_parsed = []
            for row in data_rows:
                if len(row) <= max(col_map.values(), default=0):
                    row.extend([''] * (max(col_map.values(), default=0) + 1 - len(row)))
                item_name = row[col_map['item_name']].strip() if 'item_name' in col_map else ''
                if not item_name:
                    continue
                qty = safe_float(row[col_map['quantity']]) if 'quantity' in col_map else 1
                revenue = safe_float(row[col_map['total']]) if 'total' in col_map else 0
                items_parsed.append({"menu_item": item_name, "quantity": qty, "revenue": round(revenue, 2)})

            total_sales = round(sum(it['revenue'] for it in items_parsed), 2)
            report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if 'date' in col_map and data_rows:
                report_date = safe_date(data_rows[0][col_map['date']])

            return {"extracted_data": {
                "report_date": report_date,
                "total_sales": total_sales,
                "items": items_parsed,
            }, "document_type": document_type, "row_count": len(items_parsed)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excel parse error: {e}")
        raise HTTPException(500, f"Failed to parse file: {str(e)}")


@router.post("/upload/extract")
async def extract_document(files: List[UploadFile] = File(None), file: UploadFile = File(None), document_type: str = Form(...), user=Depends(get_user)):
    try:
        all_files = []
        if files:
            all_files.extend(files)
        if file and file not in all_files:
            all_files.append(file)
        if not all_files:
            raise HTTPException(400, "No files uploaded")

        logger.info(f"Extract: received {len(all_files)} file(s), document_type={document_type}")
        rid = user["restaurant_id"]

        from preprocessing import preprocess_image

        images_b64 = []
        first_content = None
        first_fname = ""
        first_mime = ""

        for idx, f in enumerate(all_files):
            content = await f.read()
            mime = f.content_type or "image/jpeg"
            fname = (f.filename or "").lower()

            if idx == 0:
                first_content = content
                first_fname = fname
                first_mime = mime

            if "pdf" in mime.lower() or fname.endswith(".pdf"):
                import fitz
                pdf_doc = fitz.open(stream=content, filetype="pdf")
                for page_num in range(min(len(pdf_doc), 5)):
                    page = pdf_doc[page_num]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("png")
                    img_bytes = preprocess_image(img_bytes)
                    images_b64.append(base64.b64encode(img_bytes).decode())
                pdf_doc.close()
            else:
                processed = preprocess_image(content)
                images_b64.append(base64.b64encode(processed).decode())

        logger.info(f"Extract: {len(images_b64)} total image(s) to process")

        # ── Document Classification (Phase 2) ──
        from services.document_classifier import classify_document, get_parser_route

        file_format = "pdf" if any(
            ("pdf" in (f.content_type or "").lower() or (f.filename or "").lower().endswith(".pdf"))
            for f in (all_files if hasattr(all_files[0], 'content_type') else [])
        ) else "image"
        # Determine file format from stored metadata
        if first_fname.endswith(".pdf") or "pdf" in first_mime.lower():
            file_format = "pdf"

        # Classification happens before vendor detection (vendor info added later)
        doc_classification = classify_document(
            images_b64=images_b64,
            file_format=file_format,
            page_count=len(images_b64),
        )
        parser_route = get_parser_route(doc_classification)
        logger.info(
            f"Classification: {doc_classification['document_type']} "
            f"({doc_classification['confidence_reason']}), route={parser_route}"
        )

        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        vendor_hint = ""
        vendor_pattern = None
        detect_chat = LlmChat(api_key=LLM_KEY, session_id=f"detect-{uuid.uuid4()}", system_message="You read receipts. Return ONLY the vendor/supplier company name, nothing else. If unclear, return UNKNOWN.").with_model("openai", "gpt-5.2")
        detect_msg = UserMessage(text="What is the vendor/supplier name on this receipt?", file_contents=[ImageContent(image_base64=images_b64[0])])
        detected_vendor = (await detect_chat.send_message(detect_msg)).strip().strip('"').strip("'")
        logger.info(f"Detected vendor: {detected_vendor}")

        if detected_vendor and detected_vendor.upper() != "UNKNOWN":
            norm_vendor = detected_vendor.lower().strip()
            vp = await db.vendor_patterns.find_one(
                {"restaurant_id": rid, "vendor_name_lower": {"$regex": f".*{re.escape(norm_vendor[:20])}.*", "$options": "i"}},
                {"_id": 0}
            )
            if not vp:
                sup = await db.suppliers.find_one(
                    {"restaurant_id": rid, "name": {"$regex": f".*{re.escape(norm_vendor[:20])}.*", "$options": "i"}},
                    {"_id": 0, "id": 1}
                )
                if sup:
                    vp = await db.vendor_patterns.find_one({"restaurant_id": rid, "vendor_id": sup["id"]}, {"_id": 0})
            if vp:
                vendor_pattern = vp
                hints = vp.get("hints", {})
                hint_parts = []
                if hints.get("date_position"):
                    hint_parts.append(f"Date is usually found {hints['date_position']}")
                if hints.get("line_format"):
                    hint_parts.append(f"Line items are typically formatted as: {hints['line_format']}")
                if hints.get("has_tax"):
                    hint_parts.append("This vendor usually includes tax")
                if hints.get("typical_items"):
                    hint_parts.append(f"Common items from this vendor: {', '.join(hints['typical_items'][:10])}")
                if hints.get("notes"):
                    hint_parts.append(f"Additional notes: {hints['notes']}")
                if hint_parts:
                    vendor_hint = "\n\nVENDOR-SPECIFIC HINTS (from previous receipts):\n" + "\n".join(f"- {h}" for h in hint_parts)

        parsing_method = "vendor" if vendor_pattern else "general"

        # Update classification with vendor info now that we know it
        if vendor_pattern and detected_vendor.upper() != "UNKNOWN":
            doc_classification = classify_document(
                images_b64=images_b64,
                file_format=file_format,
                page_count=len(images_b64),
                vendor_name=detected_vendor,
                has_vendor_pattern=True,
            )
            parser_route = get_parser_route(doc_classification)
            logger.info(f"Classification updated with vendor: {doc_classification['document_type']}")

        page_types = None
        if len(images_b64) > 1 and document_type == "purchase_invoice":
            from preprocessing import classify_pages, build_page_aware_prompt
            page_types = await classify_pages(images_b64, LLM_KEY)
            prompt = build_page_aware_prompt(page_types, vendor_hint)
            logger.info(f"Multi-page purchase: {len(images_b64)} pages, types={page_types}")
        else:
            multi_hint = ""
            if len(images_b64) > 1:
                multi_hint = f"""

MULTI-IMAGE DOCUMENT ({len(images_b64)} images):
These images are parts of ONE document. They may be:
- Separate pages of a multi-page invoice, OR
- Overlapping photos of a long receipt
CRITICAL: Produce ONE unified result. If the same line item appears in multiple images, include it ONLY ONCE. Use the LAST occurrence of subtotal/tax/total. Do NOT duplicate items."""

            if document_type == "purchase_invoice":
                prompt = f"""You are reading a restaurant purchase invoice or receipt. Extract ALL data into this exact JSON format:
{{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0}}],"subtotal":0,"tax":0,"total":0}}

CRITICAL rules for line items:
- Look for patterns like: "2 x 5.00", "5.00 x 2", "2 @ 5.00", "Qty 2 Price 5.00"
- In columnar layouts, match quantity + unit price + total from the same row
- total = quantity * unit_price for each line item
- If unit_price is missing but total and quantity are known: unit_price = total / quantity
- If quantity is missing but total and unit_price are known: quantity = total / unit_price
- subtotal = sum of all item totals
- total = subtotal + tax
- Dates must be in YYYY-MM-DD format. Convert any date format you see.
- Use 0 for any truly missing numeric values
- pack_size: The pack/case size EXACTLY as shown on the invoice. Common formats: "10/4 LB" (10 packs of 4 LB), "6/5 LB", "BAG 50 LB", "150 EA", "1 GAL", "2/17.5 LB", "1/25 LB", "12/1 QT", "50 LB", "10#". Copy this field verbatim. Leave empty string "" if not visible.
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""
            elif document_type == "salary_document":
                prompt = f"""You are reading a payroll document, salary slip, or payment record for restaurant staff. Extract data into this exact JSON format:
{{"employee_name":"","position":"","amount":0,"payment_date":"YYYY-MM-DD","notes":"","pay_period":"","deductions":0,"gross_amount":0}}

Rules:
- employee_name: the person being paid
- position: their role/title if mentioned (e.g., Chef, Server, Manager)
- amount: the NET pay amount (after deductions). This is the most important field.
- payment_date: date of payment in YYYY-MM-DD format
- notes: any relevant details (payment method, reference number, etc.)
- pay_period: the period covered (e.g., "March 2026", "March 1-15")
- deductions: total deductions if shown, else 0
- gross_amount: gross pay before deductions if shown, else 0
- If this is a summary with multiple employees, extract the FIRST/PRIMARY employee
- Dates must be in YYYY-MM-DD format
- Use 0 for missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""
            elif document_type == "other_expense":
                prompt = f"""You are reading a utility bill, tax document, service invoice, maintenance bill, or general expense document for a restaurant. Extract data into this exact JSON format:
{{"title":"","category":"","amount":0,"expense_date":"YYYY-MM-DD","notes":"","vendor_name":"","reference_number":""}}

Rules:
- title: a short description of the expense (e.g., "March Electricity Bill", "Kitchen Equipment Repair")
- category: classify as EXACTLY one of: Utilities, Taxes, Maintenance & Repairs, Software & Subscriptions, Services, Rent / Facility, Miscellaneous
  - Utilities: electricity, water, gas, internet, phone bills
  - Taxes: tax payments, filings, government fees
  - Maintenance & Repairs: equipment repair, plumbing, HVAC, cleaning services
  - Software & Subscriptions: POS systems, accounting software, delivery apps
  - Services: legal, accounting, consulting, pest control, security
  - Rent / Facility: rent, lease, property insurance, facility costs
  - Miscellaneous: anything that doesn't fit above
- amount: the total amount due/paid
- expense_date: the bill date or due date in YYYY-MM-DD format
- notes: any useful details (account number, meter readings, service description)
- vendor_name: the company/provider name
- reference_number: invoice/bill/reference number if shown
- This may be a simple summary document, not an itemized receipt
- Dates must be in YYYY-MM-DD format
- Use 0 for missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""
            else:
                prompt = f"""You are reading a restaurant sales report or receipt. Extract ALL data into this exact JSON format:
{{"report_date":"YYYY-MM-DD","total_sales":0,"items":[{{"menu_item":"","quantity":0,"revenue":0}}]}}

Rules:
- total_sales should be the grand total
- For each item, revenue is the total amount for that item
- Dates must be in YYYY-MM-DD format
- Use 0 for any truly missing numeric values
- Return ONLY the JSON object, no other text.{vendor_hint}{multi_hint}"""

        chat = LlmChat(api_key=LLM_KEY, session_id=f"extract-{uuid.uuid4()}", system_message="You are an expert at reading restaurant invoices and receipts. Extract data accurately. Return valid JSON only, no markdown fences.").with_model("openai", "gpt-5.2")
        file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]
        user_msg = UserMessage(text=prompt, file_contents=file_contents)
        response = await chat.send_message(user_msg)

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                extracted = json.loads(json_match.group())
            except json.JSONDecodeError:
                from preprocessing import salvage_partial_extraction
                extracted = salvage_partial_extraction(response)
                logger.warning(f"JSON decode failed, salvaged partial extraction: {list(extracted.keys())}")
        else:
            from preprocessing import salvage_partial_extraction
            extracted = salvage_partial_extraction(response)
            logger.warning(f"No JSON found in response, salvaged: {list(extracted.keys())}")

        receipt_id = str(uuid.uuid4())

        # ── Layout parsing (Phase 3) — runs in parallel with LLM ──
        layout_parse_result = None
        try:
            from services.layout_parser import parse_invoice_layout
            if document_type == "purchase_invoice" and images_b64:
                layout_parse_result = parse_invoice_layout(
                    b64_image=images_b64[0],
                    document_type=doc_classification.get("document_type", "structured_invoice"),
                    vendor_name=detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
                )
                logger.info(
                    f"Layout parser: {layout_parse_result['parser_used']}, "
                    f"{len(layout_parse_result['items'])} items, "
                    f"{layout_parse_result['row_count']} rows, "
                    f"header={'yes' if layout_parse_result['header_detected'] else 'no'}"
                )
        except Exception as e:
            logger.warning(f"Layout parsing failed (non-fatal): {e}")

        receipt_doc = {
            "id": receipt_id,
            "restaurant_id": rid,
            "file_name": first_fname or "untitled",
            "file_type": first_mime,
            "file_count": len(all_files),
            "page_types": page_types,
            "document_classification": doc_classification,
            "parser_route": parser_route,
            "layout_parse": {
                "parser_used": layout_parse_result["parser_used"],
                "item_count": len(layout_parse_result["items"]),
                "row_count": layout_parse_result["row_count"],
                "column_count": layout_parse_result["column_count"],
                "header_detected": layout_parse_result["header_detected"],
            } if layout_parse_result else None,
            "raw_ocr_text": response[:5000],
            "detected_vendor": detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
            "vendor_id": vendor_pattern.get("vendor_id") if vendor_pattern else None,
            "parsing_method": parsing_method,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        ext = first_fname.rsplit(".", 1)[-1] if "." in first_fname else "jpg"
        stored_name = f"receipt_{receipt_id}.{ext}"
        file_path = UPLOADS_DIR / stored_name
        with open(file_path, "wb") as f:
            f.write(first_content)
        receipt_doc["file_url"] = f"/uploads/{stored_name}"
        await db.uploaded_receipts.insert_one(receipt_doc)

        extraction_meta = None

        if "error" not in extracted:
            if document_type == "purchase_invoice":
                from preprocessing import (
                    enrich_item_with_pack_size, validate_and_score_item,
                    validate_purchase_items, sanitize_extracted_item,
                    compute_extraction_meta,
                )
                from services.normalization import normalize_item

                warnings = []
                processed_items = []
                for idx, item in enumerate(extracted.get("items", [])):
                    try:
                        sanitize_extracted_item(item)

                        qty = float(item.get("quantity", 0) or 0)
                        up = float(item.get("unit_price", 0) or 0)
                        tot = float(item.get("total", 0) or 0)
                        item_warnings = []

                        if tot == 0 and qty > 0 and up > 0:
                            item["total"] = round(qty * up, 2)
                            tot = item["total"]
                        elif up == 0 and tot > 0 and qty > 0:
                            item["unit_price"] = round(tot / qty, 2)
                            up = item["unit_price"]
                        elif qty == 0 and tot > 0 and up > 0:
                            item["quantity"] = round(tot / up, 2)
                            qty = item["quantity"]

                        if qty > 0 and up > 0 and tot > 0:
                            expected = round(qty * up, 2)
                            if abs(expected - tot) > 0.02:
                                item_warnings.append(f"qty*price={expected} but total={tot}")
                                item["_warning"] = True

                        if qty == 0:
                            item_warnings.append("missing quantity")
                            item["_warning"] = True
                        if up == 0 and tot == 0:
                            item_warnings.append("missing price and total")
                            item["_warning"] = True
                        if not item.get("raw_name", "").strip():
                            item_warnings.append("missing item name")
                            item["_warning"] = True

                        pack_raw = item.get("pack_size", "") or ""
                        if pack_raw:
                            item["pack_size"] = pack_raw
                            enrich_item_with_pack_size(item)

                        normalize_item(item)
                        validate_and_score_item(item)

                        if item.get("_parse_issues"):
                            item_warnings.extend(item["_parse_issues"])

                        if item_warnings:
                            item["_warning_detail"] = "; ".join(item_warnings)
                            warnings.extend(item_warnings)

                        processed_items.append(item)
                    except Exception as item_err:
                        logger.error(f"Item {idx} processing failed: {item_err}")
                        item["_warning"] = True
                        item["_warning_detail"] = f"Processing error: {str(item_err)}"
                        item["confidence_level"] = "unverified"
                        item["confidence_score"] = 0
                        item["needs_review"] = True
                        item["review_reason"] = f"Processing error: {str(item_err)}"
                        warnings.append(f"Item {idx}: processing error")
                        processed_items.append(item)

                extracted["items"] = processed_items

                items_sum = round(sum(float(it.get("total", 0) or 0) for it in extracted.get("items", [])), 2)
                if not extracted.get("subtotal") and items_sum > 0:
                    extracted["subtotal"] = items_sum
                if not extracted.get("total") and items_sum > 0:
                    extracted["total"] = round(items_sum + float(extracted.get("tax", 0) or 0), 2)

                subtotal = float(extracted.get("subtotal", 0) or 0)
                if items_sum > 0 and subtotal > 0 and abs(items_sum - subtotal) > 0.10:
                    warnings.append(f"Items sum ({items_sum}) differs from subtotal ({subtotal})")
                    extracted["_subtotal_warning"] = True

                total = float(extracted.get("total", 0) or 0)
                tax = float(extracted.get("tax", 0) or 0)
                if subtotal > 0 and total > 0:
                    expected_total = round(subtotal + tax, 2)
                    if abs(expected_total - total) > 0.10:
                        warnings.append(f"subtotal+tax={expected_total} but total={total}")
                        extracted["_total_warning"] = True

                raw_date = extracted.get("invoice_date", "")
                if raw_date:
                    normalized = _normalize_date(raw_date)
                    if normalized != raw_date:
                        extracted["invoice_date"] = normalized
                        if not normalized:
                            warnings.append(f"Could not parse date: {raw_date}")
                            extracted["_date_warning"] = True

                extracted["_warnings"] = warnings
                extracted["_has_warnings"] = len(warnings) > 0

                # Cross-item validation
                validate_purchase_items(extracted["items"])

                # Compute invoice-level extraction quality
                extraction_meta = compute_extraction_meta(extracted["items"], extracted)

        extraction_id = str(uuid.uuid4())
        ext_doc = {
            "id": extraction_id,
            "receipt_id": receipt_id,
            "restaurant_id": rid,
            "date": extracted.get("invoice_date", "") if document_type == "purchase_invoice" else extracted.get("report_date", ""),
            "total": float(extracted.get("total", 0) or extracted.get("total_sales", 0) or 0),
            "parsing_method": parsing_method,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.receipt_extractions.insert_one(ext_doc)

        items_to_store = extracted.get("items", [])
        if items_to_store:
            item_docs = []
            for it in items_to_store:
                item_docs.append({
                    "id": str(uuid.uuid4()),
                    "extraction_id": extraction_id,
                    "item_name": it.get("raw_name", "") or it.get("menu_item", ""),
                    "quantity": float(it.get("quantity", 0) or 0),
                    "unit_price": float(it.get("unit_price", 0) or 0),
                    "total": float(it.get("total", 0) or it.get("revenue", 0) or 0),
                })
            await db.extracted_items.insert_many(item_docs)

        if isinstance(extracted.get("items"), list) and document_type != "purchase_invoice":
            from preprocessing import validate_purchase_items
            validate_purchase_items(extracted["items"])

        # Apply correction memory (supplier-scoped, strict_match_key only)
        if document_type == "purchase_invoice" and isinstance(extracted.get("items"), list):
            from services.correction_memory import apply_corrections
            supplier_id_for_correction = ""
            detected_name = (detected_vendor or "").strip()
            if detected_name and detected_name.upper() != "UNKNOWN":
                sup = await db.suppliers.find_one(
                    {"restaurant_id": rid, "name": {"$regex": f".*{re.escape(detected_name[:20])}.*", "$options": "i"}},
                    {"_id": 0, "id": 1},
                )
                if sup:
                    supplier_id_for_correction = sup["id"]
            if supplier_id_for_correction:
                await apply_corrections(extracted["items"], rid, supplier_id_for_correction)

        result = {
            "extracted_data": extracted,
            "document_type": document_type,
            "receipt_id": receipt_id,
            "parsing_method": parsing_method,
            "page_types": page_types,
            "document_classification": doc_classification,
            "parser_route": parser_route,
            "layout_parse": {
                "parser_used": layout_parse_result["parser_used"],
                "items": layout_parse_result["items"],
                "row_count": layout_parse_result["row_count"],
                "column_count": layout_parse_result["column_count"],
                "header_detected": layout_parse_result["header_detected"],
            } if layout_parse_result else None,
            "detected_vendor": detected_vendor if detected_vendor.upper() != "UNKNOWN" else None,
            "message": f"Data extracted using {parsing_method} parsing" + (" (vendor pattern matched)" if parsing_method == "vendor" else "") + (f" -- pages classified as {page_types}" if page_types else ""),
        }

        # Attach extraction quality metadata for purchase invoices
        if document_type == "purchase_invoice":
            if extraction_meta is None:
                from preprocessing import compute_extraction_meta
                extraction_meta = compute_extraction_meta(extracted.get("items", []) if isinstance(extracted.get("items"), list) else [], extracted)
            result["extraction_meta"] = extraction_meta

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(500, f"Extraction failed: {str(e)}")
