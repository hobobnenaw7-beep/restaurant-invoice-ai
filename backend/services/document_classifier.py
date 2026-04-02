"""
Document Type Classifier — Phase 2
Classifies invoice images into document types BEFORE extraction.

Types:
  - simple_receipt       : handwritten or informal receipt (few lines, informal layout)
  - structured_invoice   : formal columnar invoice (Sysco, PFG style) 
  - vendor_specific      : known vendor with stored patterns
  - multi_page_pdf       : multi-page PDF document

Classification uses:
  - file metadata (format, page count)
  - image analysis (density, layout, aspect ratio)
  - vendor pattern lookup (from DB)
  - NO AI, NO LLM calls

Returns a ClassificationResult dict for downstream routing.
"""
import io
import logging
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# ── Classification result ──

def make_result(
    document_type: str,
    page_count: int,
    file_format: str,
    vendor_pattern: str = None,
    confidence_reason: str = "",
    layout_features: dict = None,
) -> dict:
    return {
        "document_type": document_type,
        "page_count": page_count,
        "file_format": file_format,         # "image" or "pdf"
        "vendor_pattern": vendor_pattern,    # vendor name if detected, else None
        "confidence_reason": confidence_reason,
        "layout_features": layout_features or {},
    }


# ── Main classifier ──

def classify_document(
    images_b64: list,
    file_format: str,
    page_count: int,
    vendor_name: str = None,
    has_vendor_pattern: bool = False,
) -> dict:
    """
    Classify a document based on its properties. No AI.

    Args:
        images_b64: list of base64-encoded preprocessed page images
        file_format: "image" or "pdf"
        page_count: number of pages/images
        vendor_name: detected vendor name (from LLM or lookup), or None
        has_vendor_pattern: whether a vendor_pattern record exists in DB

    Returns:
        ClassificationResult dict
    """
    try:
        # Rule 1: Multi-page PDF
        if file_format == "pdf" and page_count > 1:
            return make_result(
                document_type="multi_page_pdf",
                page_count=page_count,
                file_format=file_format,
                vendor_pattern=vendor_name if has_vendor_pattern else None,
                confidence_reason=f"PDF with {page_count} pages",
                layout_features=_analyze_first_page(images_b64[0]) if images_b64 else {},
            )

        # Rule 2: Known vendor with stored pattern
        if has_vendor_pattern and vendor_name:
            layout = _analyze_first_page(images_b64[0]) if images_b64 else {}
            return make_result(
                document_type="vendor_specific",
                page_count=page_count,
                file_format=file_format,
                vendor_pattern=vendor_name,
                confidence_reason=f"Matched vendor pattern: {vendor_name}",
                layout_features=layout,
            )

        # Rule 3: Analyze image layout to distinguish receipt vs structured invoice
        if images_b64:
            layout = _analyze_first_page(images_b64[0])
            doc_type = _classify_by_layout(layout)
            return make_result(
                document_type=doc_type,
                page_count=page_count,
                file_format=file_format,
                vendor_pattern=vendor_name if has_vendor_pattern else None,
                confidence_reason=layout.get("classification_reason", "Layout analysis"),
                layout_features=layout,
            )

        # Fallback
        return make_result(
            document_type="structured_invoice",
            page_count=page_count,
            file_format=file_format,
            confidence_reason="Fallback — no images to analyze",
        )

    except Exception as e:
        logger.warning(f"Document classification failed, defaulting: {e}")
        return make_result(
            document_type="structured_invoice",
            page_count=page_count,
            file_format=file_format,
            confidence_reason=f"Classification error: {e}",
        )


# ── Layout analysis ──

def _analyze_first_page(b64_image: str) -> dict:
    """
    Analyze image layout features: text density, line structure,
    aspect ratio, columnar structure.
    Returns a dict of features.
    """
    import base64
    try:
        img_bytes = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode != "L":
            gray = img.convert("L")
        else:
            gray = img

        arr = np.array(gray)
        h, w = arr.shape

        # 1. Text density: fraction of dark pixels
        threshold = arr.mean() - 30
        dark_pixels = np.sum(arr < max(threshold, 80))
        text_density = float(dark_pixels) / (h * w)

        # 2. Aspect ratio
        aspect_ratio = w / max(h, 1)

        # 3. Horizontal line detection (table structure indicator)
        #    Look for rows that are mostly dark (horizontal rules)
        row_means = arr.mean(axis=1)
        dark_rows = np.sum(row_means < (arr.mean() - 40))
        horizontal_line_ratio = dark_rows / max(h, 1)

        # 4. Projection profile analysis — columnar structure
        h_profile = arr.mean(axis=0)  # column-wise mean
        col_variance = float(np.var(h_profile))

        # 5. Content vertical spread — how much of the page has content
        binary = (arr < max(threshold, 80)).astype(np.float32)
        row_sums = binary.sum(axis=1)
        content_rows = np.sum(row_sums > (w * 0.02))
        content_fill = content_rows / max(h, 1)

        # 6. Estimate line count (peaks in horizontal projection)
        row_density = binary.sum(axis=1)
        if len(row_density) > 10:
            # Smooth the profile
            kernel_size = max(3, h // 100)
            smoothed = np.convolve(row_density, np.ones(kernel_size)/kernel_size, mode='same')
            # Count peaks (transitions from low to high)
            threshold_val = smoothed.mean() * 0.5
            above = smoothed > threshold_val
            transitions = np.diff(above.astype(int))
            line_count = int(np.sum(transitions == 1))
        else:
            line_count = 0

        return {
            "width": w,
            "height": h,
            "aspect_ratio": round(aspect_ratio, 3),
            "text_density": round(text_density, 4),
            "horizontal_line_ratio": round(horizontal_line_ratio, 4),
            "column_variance": round(col_variance, 1),
            "content_fill": round(content_fill, 3),
            "estimated_line_count": line_count,
        }

    except Exception as e:
        logger.warning(f"Layout analysis failed: {e}")
        return {}


def _classify_by_layout(layout: dict) -> str:
    """
    Classify based on layout features.

    simple_receipt: informal, fewer lines, no table structure
    structured_invoice: formal, many lines, table structure, columnar

    Returns document_type string.
    """
    if not layout:
        return "structured_invoice"

    lines = layout.get("estimated_line_count", 0)
    density = layout.get("text_density", 0)
    content_fill = layout.get("content_fill", 0)
    h_lines = layout.get("horizontal_line_ratio", 0)
    col_var = layout.get("column_variance", 0)
    aspect = layout.get("aspect_ratio", 0.7)
    height = layout.get("height", 0)
    width = layout.get("width", 0)

    reasons = []
    score = 0

    # Line count is the strongest signal
    if lines >= 15:
        score += 3
        reasons.append(f"{lines} lines (many)")
    elif lines >= 10:
        score += 2
        reasons.append(f"{lines} lines (moderate)")
    elif lines >= 6:
        score += 1
        reasons.append(f"{lines} lines (some)")
    else:
        reasons.append(f"{lines} lines (few)")

    # Text density — lower thresholds for PIL-rendered text
    if density > 0.05:
        score += 2
        reasons.append(f"high density ({density:.4f})")
    elif density > 0.02:
        score += 1
        reasons.append(f"medium density ({density:.4f})")
    else:
        reasons.append(f"low density ({density:.4f})")

    # Horizontal lines (table rules / dividers)
    if h_lines > 0.003:
        score += 2
        reasons.append(f"table lines ({h_lines:.4f})")
    elif h_lines > 0.001:
        score += 1
        reasons.append(f"some lines ({h_lines:.4f})")

    # Content fill
    if content_fill > 0.4:
        score += 1
        reasons.append(f"dense fill ({content_fill:.3f})")

    # Wide images tend to be structured
    if width > 800:
        score += 1
        reasons.append(f"wide ({width}px)")

    doc_type = "structured_invoice" if score >= 4 else "simple_receipt"
    layout["classification_reason"] = f"{doc_type}: {', '.join(reasons)} (score={score})"

    return doc_type


# ── Routing scaffold ──

PARSER_ROUTES = {
    "simple_receipt":     "parser.simple_receipt",
    "structured_invoice": "parser.structured_invoice",
    "vendor_specific":    "parser.vendor_specific",
    "multi_page_pdf":     "parser.multi_page_pdf",
}


def get_parser_route(classification: dict) -> str:
    """
    Return the parser module path for a given classification.
    This is a scaffold — parsers don't exist yet.
    Returns the route string for logging/future use.
    """
    doc_type = classification.get("document_type", "structured_invoice")
    route = PARSER_ROUTES.get(doc_type, PARSER_ROUTES["structured_invoice"])
    logger.info(
        f"Document routed: type={doc_type}, "
        f"route={route}, "
        f"pages={classification.get('page_count', 1)}, "
        f"vendor={classification.get('vendor_pattern', 'none')}"
    )
    return route
