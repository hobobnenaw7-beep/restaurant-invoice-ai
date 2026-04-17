"""
Image preprocessing and multi-page classification for invoice extraction.
Phase 1: Orientation fix, deskew, enhancement, standardization.
Phase 2: Scan Mode — always-on document edge detection + perspective correction.
"""
import base64
import io
import json
import re
import logging
import uuid
import numpy as np
import cv2
from PIL import Image, ImageOps, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Image Preprocessing
# ---------------------------------------------------------------------------

def preprocess_image(image_bytes: bytes, save_artifacts: bool = False, artifact_id: str = "") -> bytes:
    """
    Full preprocessing pipeline for invoice images.
    Scan Mode is ALWAYS ON.

    Args:
        image_bytes: raw image bytes
        save_artifacts: if True, saves before/after images to uploads dir
        artifact_id: unique ID for naming artifact files

    Returns processed PNG bytes. Falls back to original on ANY error.
    Populates _last_preprocess_meta (module-level) with step-by-step evidence.
    """
    global _last_preprocess_meta
    meta = {
        "original_size_bytes": len(image_bytes),
        "original_dimensions": None,
        "steps_applied": [],
        "scan_mode_triggered": False,
        "scan_mode_result": "skipped",
        "final_dimensions": None,
        "final_size_bytes": 0,
        "artifact_before_url": None,
        "artifact_after_url": None,
    }
    _last_preprocess_meta = meta

    try:
        img = Image.open(io.BytesIO(image_bytes))
        meta["original_dimensions"] = f"{img.size[0]}x{img.size[1]}"

        # Save BEFORE artifact
        if save_artifacts and artifact_id:
            _save_artifact(image_bytes, artifact_id, "before", img.size)
            meta["artifact_before_url"] = f"/uploads/scan_before_{artifact_id}.jpg"

        # 0. EXIF auto-rotate first (so scan mode works on correct orientation)
        img = ImageOps.exif_transpose(img)
        meta["steps_applied"].append("exif_transpose")

        # 1. Convert to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 2. Scan Mode — always ON
        size_before_scan = img.size
        img = _scan_mode_detect_and_correct(img)
        size_after_scan = img.size
        if size_after_scan != size_before_scan:
            meta["scan_mode_triggered"] = True
            meta["scan_mode_result"] = f"corrected: {size_before_scan[0]}x{size_before_scan[1]} → {size_after_scan[0]}x{size_after_scan[1]}"
            meta["steps_applied"].append("scan_mode_perspective_correct")
        else:
            # Check if camera enhance fallback was used (dimensions unchanged but pixels changed)
            meta["scan_mode_result"] = "clean_scan_passthrough"
            meta["steps_applied"].append("scan_mode_passthrough")

        # 3. Detect and fix 90/180/270° rotation
        size_before_orient = img.size
        img, rotation_applied = _fix_orientation(img)
        if rotation_applied != 0:
            meta["steps_applied"].append(f"orientation_fix_{rotation_applied}deg: {size_before_orient[0]}x{size_before_orient[1]} → {img.size[0]}x{img.size[1]}")
        else:
            meta["steps_applied"].append("orientation_check_ok")

        # 4. Deskew — straighten slight tilt
        size_before_deskew = img.size
        img = _deskew(img)
        if img.size != size_before_deskew:
            meta["steps_applied"].append(f"deskew_applied")
        else:
            meta["steps_applied"].append("deskew_not_needed")

        # 5. Crop empty margins
        size_before_crop = img.size
        img = _crop_margins(img)
        if img.size != size_before_crop:
            meta["steps_applied"].append(f"crop: {size_before_crop[0]}x{size_before_crop[1]} → {img.size[0]}x{img.size[1]}")
        else:
            meta["steps_applied"].append("crop_not_needed")

        # 6. Enhancement pipeline (auto-contrast, noise, sharpness)
        img = _enhance_image(img)
        meta["steps_applied"].append("enhancement_applied")

        # 7. Resize for GPT vision — cap at 2048px on long side
        # GPT vision downscales larger images anyway, so sending 4032x3024
        # wastes bandwidth and can cause inconsistent extraction.
        max_dim = 2048
        w, h = img.size
        if max(w, h) > max_dim:
            if w > h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            meta["steps_applied"].append(f"resize: {w}x{h} → {new_w}x{new_h}")
        else:
            meta["steps_applied"].append("resize_not_needed")

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        processed = buf.getvalue()

        meta["final_dimensions"] = f"{img.size[0]}x{img.size[1]}"
        meta["final_size_bytes"] = len(processed)

        # Save AFTER artifact
        if save_artifacts and artifact_id:
            _save_artifact(processed, artifact_id, "after", img.size)
            meta["artifact_after_url"] = f"/uploads/scan_after_{artifact_id}.png"

        logger.info(
            f"Preprocessed image: {len(image_bytes)}→{len(processed)} bytes "
            f"({img.size[0]}x{img.size[1]}), "
            f"scan_mode={meta['scan_mode_result']}"
        )
        return processed
    except Exception as e:
        logger.warning(f"Image preprocessing failed, using original: {e}")
        meta["steps_applied"].append(f"FAILED: {str(e)}")
        return image_bytes


# Module-level storage for last preprocessing metadata
_last_preprocess_meta: dict = {}


def get_last_preprocess_meta() -> dict:
    """Return metadata from the last preprocess_image call."""
    return _last_preprocess_meta.copy()


def _save_artifact(image_bytes: bytes, artifact_id: str, stage: str, size: tuple) -> None:
    """Save a before/after artifact image to uploads dir."""
    try:
        from pathlib import Path
        uploads = Path(__file__).parent / "uploads"
        uploads.mkdir(exist_ok=True)
        ext = "jpg" if stage == "before" else "png"
        path = uploads / f"scan_{stage}_{artifact_id}.{ext}"

        if stage == "before":
            # Save as JPEG for smaller size
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((1200, 1600))  # Reasonable preview size
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            path.write_bytes(buf.getvalue())
        else:
            # After is already PNG
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((1200, 1600))
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            path.write_bytes(buf.getvalue())

        logger.info(f"Saved scan artifact: {path.name} ({size[0]}x{size[1]})")
    except Exception as e:
        logger.warning(f"Failed to save artifact {stage}/{artifact_id}: {e}")


# ---------------------------------------------------------------------------
# 0. Scan Mode — Document Edge Detection & Perspective Correction
# ---------------------------------------------------------------------------

def _scan_mode_detect_and_correct(img: Image.Image) -> Image.Image:
    """
    Always-on scan mode. Detects if image is a camera photo of a document
    and applies edge detection + perspective correction.

    Strategy:
      1. Check if image needs scan mode (has non-white borders = camera photo)
      2. Find document contour using Canny edges + contour detection
      3. If a valid quadrilateral found, apply 4-point perspective transform
      4. If not found, return original (no-op for clean scans)
    """
    try:
        arr = np.array(img)
        h, w = arr.shape[:2]

        # Skip very small images — not worth processing
        if h < 200 or w < 200:
            return img

        # Step 1: Check if this looks like a camera photo
        #   Camera photos have non-white borders (desk, table, background)
        #   Clean scans are nearly all white at the edges
        if not _image_needs_scan_mode(arr):
            logger.info("Scan mode: clean scan detected, skipping edge detection")
            return img

        logger.info("Scan mode: camera photo detected, attempting edge detection")

        # Step 2: Find document contour
        doc_contour = _find_document_contour(arr)

        if doc_contour is None:
            logger.info("Scan mode: no document contour found, using adaptive crop")
            # Fallback: adaptive contrast + tighter crop for camera photos
            return _camera_photo_enhance(img)

        # Step 3: Apply perspective correction
        corrected = _apply_perspective_transform(arr, doc_contour)
        if corrected is not None:
            result = Image.fromarray(corrected)
            logger.info(
                f"Scan mode: perspective corrected "
                f"({w}x{h} → {result.size[0]}x{result.size[1]})"
            )
            return result

        logger.info("Scan mode: perspective transform failed, using adaptive crop")
        return _camera_photo_enhance(img)

    except Exception as e:
        logger.warning(f"Scan mode failed (non-fatal): {e}")
        return img


def _image_needs_scan_mode(arr: np.ndarray) -> bool:
    """
    Detect if an image is a camera photo (needs scan mode) vs a clean scan.

    Camera photos: non-white borders, visible desk/table/background.
    Clean scans: white/near-white at edges, document fills the frame.

    Checks border strips (top/bottom/left/right 5% of image).
    If average border brightness < 200 (not white), it's likely a camera photo.
    """
    h, w = arr.shape[:2]
    strip = max(int(min(h, w) * 0.05), 10)

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if len(arr.shape) == 3 else arr

    # Sample border strips
    borders = [
        gray[:strip, :],          # top
        gray[h - strip:, :],      # bottom
        gray[:, :strip],          # left
        gray[:, w - strip:],      # right
    ]

    border_means = [float(np.mean(b)) for b in borders]
    avg_border = sum(border_means) / len(border_means)

    # Count how many borders are dark (non-white)
    dark_borders = sum(1 for m in border_means if m < 200)

    # If average border is dark OR 2+ borders are dark → camera photo
    if avg_border < 190 or dark_borders >= 2:
        logger.info(
            f"Scan mode check: border brightness={avg_border:.0f}, "
            f"dark_borders={dark_borders}/4 → camera photo"
        )
        return True

    return False


def _find_document_contour(arr: np.ndarray) -> np.ndarray | None:
    """
    Find the largest quadrilateral contour that represents the document.
    Uses Canny edge detection + contour approximation.

    Returns a 4-point contour (numpy array shape (4,2)) or None.
    """
    h, w = arr.shape[:2]
    img_area = h * w

    # Convert to grayscale
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    # Reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Try multiple Canny thresholds (adaptive)
    for low_t, high_t in [(30, 100), (50, 150), (20, 80)]:
        edges = cv2.Canny(blurred, low_t, high_t)

        # Dilate to close gaps in edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            continue

        # Sort by area, largest first
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:5]:  # Check top 5 largest
            area = cv2.contourArea(contour)

            # Document must be at least 15% of image area
            if area < img_area * 0.15:
                continue

            # Approximate contour to polygon
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            # We want a quadrilateral (4 points)
            if len(approx) == 4:
                # Verify it's roughly rectangular (angles close to 90°)
                if _is_valid_quad(approx.reshape(4, 2), w, h):
                    logger.info(
                        f"Scan mode: found document contour "
                        f"(area={area/img_area:.0%} of image, "
                        f"canny={low_t}/{high_t})"
                    )
                    return approx.reshape(4, 2)

    return None


def _is_valid_quad(pts: np.ndarray, img_w: int, img_h: int) -> bool:
    """
    Validate that a 4-point contour is a reasonable document rectangle.

    Checks:
    - Not too small (> 15% of image area)
    - Not too large (< 98% of image — that's just the full image)
    - Aspect ratio is reasonable for a document (not a thin strip)
    """
    # Bounding rect area
    x, y, bw, bh = cv2.boundingRect(pts.astype(np.int32))
    bound_area = bw * bh
    img_area = img_w * img_h

    if bound_area < img_area * 0.15:
        return False
    if bound_area > img_area * 0.98:
        return False

    # Aspect ratio check — documents are typically 1:1.2 to 1:2
    aspect = max(bw, bh) / max(min(bw, bh), 1)
    if aspect > 4.0:  # Too elongated — probably not a document
        return False

    return True


def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 points as: top-left, top-right, bottom-right, bottom-left.
    Required for consistent perspective transform.
    """
    rect = np.zeros((4, 2), dtype=np.float32)

    # Sum: top-left has smallest sum, bottom-right has largest
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # Diff: top-right has smallest diff, bottom-left has largest
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]

    return rect


def _apply_perspective_transform(
    arr: np.ndarray, contour: np.ndarray
) -> np.ndarray | None:
    """
    Apply 4-point perspective transform to extract the document region
    as a flat, front-facing rectangle.
    """
    try:
        rect = _order_points(contour.astype(np.float32))
        tl, tr, br, bl = rect

        # Compute output dimensions
        width_top = np.linalg.norm(tr - tl)
        width_bot = np.linalg.norm(br - bl)
        max_width = int(max(width_top, width_bot))

        height_left = np.linalg.norm(bl - tl)
        height_right = np.linalg.norm(br - tr)
        max_height = int(max(height_left, height_right))

        if max_width < 100 or max_height < 100:
            return None

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(
            arr, M, (max_width, max_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return warped

    except Exception as e:
        logger.warning(f"Perspective transform error: {e}")
        return None


def _camera_photo_enhance(img: Image.Image) -> Image.Image:
    """
    Fallback enhancement for camera photos when edge detection fails.
    Applies stronger contrast + brightness normalization than standard pipeline.
    """
    try:
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        mean_brightness = float(np.mean(gray))

        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # on the luminance channel for better local contrast
        lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        l_channel = lab[:, :, 0]
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(l_channel)
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

        # If very dark, boost brightness
        if mean_brightness < 150:
            enhanced = cv2.convertScaleAbs(enhanced, alpha=1.2, beta=30)

        logger.info(
            f"Scan mode fallback: CLAHE enhancement applied "
            f"(brightness was {mean_brightness:.0f})"
        )
        return Image.fromarray(enhanced)

    except Exception as e:
        logger.warning(f"Camera photo enhance failed: {e}")
        return img


# ---------------------------------------------------------------------------
# 1a. Orientation Detection (90 / 180 / 270)
# ---------------------------------------------------------------------------

def _fix_orientation(img: Image.Image) -> tuple[Image.Image, int]:
    """
    Detect if image is rotated 90°, 180°, or 270°.
    Uses multiple strategies:
      1. Tesseract OSD (if available and confident)
      2. 4-way OCR confidence comparison (0°, 90°, 180°, 270°)
      3. Projection-profile heuristic for 90° detection (final fallback)

    Returns (corrected_image, rotation_applied).
    """
    # Try Tesseract OSD first (handles all angles if confident)
    rotation = _detect_orientation_tesseract(img)
    if rotation is not None and rotation != 0:
        logger.info(f"Orientation fix: rotating {rotation}° (tesseract OSD)")
        return img.rotate(rotation, resample=Image.BICUBIC, expand=True,
                          fillcolor=(255, 255, 255)), rotation
    if rotation is not None:
        # OSD said 0° with confidence — still verify with OCR comparison
        pass

    # Compare all 4 orientations using OCR confidence
    best_angle = _detect_best_orientation(img)
    if best_angle != 0:
        logger.info(f"Orientation fix: rotating {best_angle}° (4-way OCR comparison)")
        return img.rotate(best_angle, resample=Image.BICUBIC, expand=True,
                          fillcolor=(255, 255, 255)), best_angle

    return img, 0


def _detect_best_orientation(img: Image.Image) -> int:
    """
    Compare OCR readability at 0°, 90°, 180°, 270° and return the
    rotation angle that produces the most readable text.

    Returns 0 if current orientation is best (or if detection fails).
    Requires the winning angle to score at least 1.5x better than current.
    """
    try:
        thumb = img.copy()
        thumb.thumbnail((800, 1200))
        gray = thumb.convert("L")

        scores = {}
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                rotated = gray
            else:
                rotated = gray.rotate(angle, expand=True)
            scores[angle] = _measure_text_readability(rotated)

        best_angle = max(scores, key=scores.get)
        best_score = scores[best_angle]
        current_score = scores[0]

        logger.info(
            f"4-way orientation: 0°={scores[0]:.0f}, 90°={scores[90]:.0f}, "
            f"180°={scores[180]:.0f}, 270°={scores[270]:.0f} → best={best_angle}°"
        )

        # Require significant improvement over current orientation
        if best_angle == 0:
            return 0
        if current_score == 0 and best_score > 0:
            return best_angle
        if best_score > current_score * 1.5:
            return best_angle

        return 0

    except Exception as e:
        logger.debug(f"4-way orientation detection failed: {e}")
        return 0


def _detect_180_rotation(img: Image.Image) -> bool:
    """
    Detect if an image is upside-down (needs 180° rotation).

    Strategy: Compare Tesseract OCR readability at 0° vs 180°.
    The correct orientation produces significantly more readable text
    (higher confidence scores, more recognized words).

    Uses a downscaled thumbnail for speed (~1-2 seconds).
    Returns True if image should be rotated 180°.
    """
    try:
        import pytesseract

        # Downscale for speed
        thumb = img.copy()
        thumb.thumbnail((800, 1200))
        gray = thumb.convert("L")

        # Measure readability at current orientation (0°)
        score_0 = _measure_text_readability(gray)

        # Measure readability at 180°
        gray_180 = gray.rotate(180, expand=False)
        score_180 = _measure_text_readability(gray_180)

        logger.info(
            f"180° check: score_0={score_0:.0f}, score_180={score_180:.0f}, "
            f"ratio={score_180/max(score_0, 1):.1f}x"
        )

        # 180° is correct if it scores significantly better
        # Require at least 1.5x improvement to avoid false positives
        if score_0 == 0 and score_180 == 0:
            return False
        if score_0 == 0 and score_180 > 0:
            return True
        if score_180 > score_0 * 1.5:
            return True

        return False

    except Exception as e:
        logger.debug(f"180° detection failed (non-fatal): {e}")
        return False


def _measure_text_readability(gray_img: Image.Image) -> float:
    """
    Measure how readable the text is using Tesseract.
    Returns a composite score based on:
      - Number of high-confidence word detections
      - Average confidence of detected words
    Higher score = more readable text = correct orientation.
    """
    try:
        import pytesseract

        data = pytesseract.image_to_data(
            gray_img,
            output_type=pytesseract.Output.DICT,
            config="--psm 3 --dpi 300",
        )

        confs = [int(c) for c in data["conf"] if int(c) > 0]
        if not confs:
            return 0.0

        # Count words with high confidence (>60) that have alpha characters
        high_conf_words = 0
        for text, conf in zip(data["text"], data["conf"]):
            c = int(conf)
            t = (text or "").strip()
            if c > 60 and len(t) >= 2 and sum(1 for ch in t if ch.isalpha()) > len(t) * 0.5:
                high_conf_words += 1

        avg_conf = sum(confs) / len(confs)

        # Composite score: word count weighted by average confidence
        return high_conf_words * (avg_conf / 100.0)

    except Exception:
        return 0.0


def _detect_orientation_tesseract(img: Image.Image):
    """
    Use Tesseract OSD to detect rotation angle.
    Returns rotation needed to fix (0, 90, 180, 270), or None on failure.
    """
    try:
        import pytesseract

        # OSD needs a reasonably sized image
        w, h = img.size
        if max(w, h) < 200:
            return None

        # Work on grayscale for OSD; upscale small images
        gray = img.convert("L")
        if max(w, h) < 600:
            scale = 600 / max(w, h)
            gray = gray.resize(
                (int(w * scale), int(h * scale)), Image.BILINEAR
            )

        osd = pytesseract.image_to_osd(
            gray,
            output_type=pytesseract.Output.DICT,
            config="--dpi 300",
        )
        detected_rotation = int(osd.get("rotate", 0))
        confidence = float(osd.get("orientation_conf", 0))

        logger.info(f"Tesseract OSD: rotation={detected_rotation}°, conf={confidence:.1f}")

        # Only apply if confidence is reasonable (OSD confidence < 3 is unreliable)
        if confidence < 3.0:
            return None

        # Tesseract returns the rotation needed to correct
        return detected_rotation
    except Exception as e:
        logger.debug(f"Tesseract OSD failed (non-fatal): {e}")
        return None


def _detect_orientation_heuristic(img: Image.Image) -> int:
    """
    Heuristic orientation detection using projection profiles.
    Tests 0° and 90° — picks the one where horizontal text lines
    produce sharper projection peaks. Uses aspect ratio as tiebreaker.
    Returns 0 or 90.
    """
    try:
        # Work on small grayscale thumbnail
        thumb = img.convert("L")
        scale = 400 / max(thumb.size)
        if scale < 1:
            thumb = thumb.resize(
                (int(thumb.size[0] * scale), int(thumb.size[1] * scale)),
                Image.BILINEAR,
            )
        arr = np.array(thumb)
        binary = (arr < (arr.mean() - 20)).astype(np.float32)

        # Horizontal projection profile (text lines → sharp peaks)
        h_profile = binary.sum(axis=1)
        h_score = float(np.var(h_profile)) if len(h_profile) > 1 else 0

        # Vertical projection profile (text lines if rotated 90°)
        v_profile = binary.sum(axis=0)
        v_score = float(np.var(v_profile)) if len(v_profile) > 1 else 0

        # Normalize by dimension count to compare fairly
        h_norm = h_score / max(len(h_profile), 1)
        v_norm = v_score / max(len(v_profile), 1)

        # Aspect ratio hint: invoices are typically portrait (taller than wide)
        w, h = img.size
        is_landscape = w > h * 1.2

        # If text variance strongly suggests rotation, rotate
        if v_norm > h_norm * 1.5:
            return 90
        # If ambiguous but landscape, try rotation
        if is_landscape and v_norm > h_norm * 0.8:
            return 90
        return 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 1b. Deskew (small angle straightening)
# ---------------------------------------------------------------------------

def _deskew(img: Image.Image, max_angle: float = 5.0) -> Image.Image:
    """
    Estimate and correct small skew angles (±5°) using horizontal
    projection-profile variance. Tests 21 angles.
    """
    try:
        # Work on a small grayscale thumbnail for speed
        thumb = img.convert("L").resize((400, int(400 * img.height / img.width)))
        arr = np.array(thumb)
        threshold = int(arr.mean()) - 20
        binary = (arr < max(threshold, 80)).astype(np.float32)

        best_angle = 0.0
        best_score = -1.0
        for angle_10x in range(int(-max_angle * 10), int(max_angle * 10) + 1, 5):
            angle = angle_10x / 10.0
            rotated = _rotate_array(binary, angle)
            profile = rotated.sum(axis=1)
            score = float(np.var(profile))
            if score > best_score:
                best_score = score
                best_angle = angle

        if abs(best_angle) < 0.3:
            return img  # negligible skew

        logger.info(f"Deskew: correcting {best_angle:.1f}° skew")
        return img.rotate(best_angle, resample=Image.BICUBIC,
                          expand=True, fillcolor=(255, 255, 255))
    except Exception as e:
        logger.warning(f"Deskew failed, skipping: {e}")
        return img


def _rotate_array(arr: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate a 2-D array by a small angle using Pillow (avoids scipy)."""
    img = Image.fromarray((arr * 255).astype(np.uint8), mode="L")
    rotated = img.rotate(angle_deg, resample=Image.BILINEAR,
                         expand=False, fillcolor=0)
    return np.array(rotated).astype(np.float32) / 255.0


def _crop_margins(img: Image.Image, min_crop_pct: float = 0.05) -> Image.Image:
    """Crop empty white/light borders. Only crops if >5 % of area is margin."""
    try:
        gray = img.convert("L")
        inv = ImageOps.invert(gray)
        bbox = inv.getbbox()
        if not bbox:
            return img

        pad = 10
        w, h = img.size
        x0 = max(0, bbox[0] - pad)
        y0 = max(0, bbox[1] - pad)
        x1 = min(w, bbox[2] + pad)
        y1 = min(h, bbox[3] + pad)

        crop_area = (x1 - x0) * (y1 - y0)
        orig_area = w * h
        if crop_area < orig_area * (1.0 - min_crop_pct):
            return img.crop((x0, y0, x1, y1))
        return img
    except Exception:
        return img


# ---------------------------------------------------------------------------
# 1c. Image Enhancement
# ---------------------------------------------------------------------------

def _enhance_image(img: Image.Image) -> Image.Image:
    """
    Multi-step enhancement: auto-contrast, noise reduction, sharpening,
    background cleanup. Adaptive — only applies heavy processing when needed.

    Key principle: DO NOT degrade clean images. Only enhance when measurably
    needed. Text-heavy images (invoices) have high Laplacian variance from
    edges, which is NOT noise — so we measure noise only in background regions.
    """
    try:
        arr_gray = np.array(img.convert("L"))
        mean_brightness = float(np.mean(arr_gray))
        std_brightness = float(np.std(arr_gray))

        # 1. Background cleanup — only for gray/dark backgrounds
        if mean_brightness < 220:
            img = _clean_background(img)

        # 2. Auto-contrast — only for genuinely low-contrast images
        #    Clean white-bg images (mean > 230) with std 30-55 don't need it
        if std_brightness < 30 or (std_brightness < 55 and mean_brightness < 230):
            img = ImageOps.autocontrast(img, cutoff=0.5)
            logger.info(f"AutoContrast applied (std was {std_brightness:.0f}, mean was {mean_brightness:.0f})")

        # 3. Noise reduction — measure noise in BACKGROUND regions only
        #    (text edges are NOT noise; previous approach falsely triggered)
        #    Threshold 40+ ensures only genuinely noisy images get filtered
        noise_level = _estimate_background_noise(img)
        if noise_level > 40:
            img = img.filter(ImageFilter.MedianFilter(size=3))
            logger.info(f"Noise reduction applied (bg_noise={noise_level:.0f})")

        # 4. Sharpening — light for clean images, stronger for noisy
        sharp_factor = 1.3 if noise_level > 40 else 1.1
        img = ImageEnhance.Sharpness(img).enhance(sharp_factor)

        # 5. Contrast normalization — only for genuinely faded images
        #    Don't boost clean white-bg images; high contrast boost damages small text
        arr_after = np.array(img.convert("L"))
        mean_after = float(np.mean(arr_after))
        if mean_after < 230:
            img = _normalize_contrast(img)

        return img
    except Exception as e:
        logger.warning(f"Enhancement failed, skipping: {e}")
        return img


def _estimate_background_noise(img: Image.Image) -> float:
    """
    Estimate noise level in background regions (non-text areas).
    Samples multiple background patches and measures their local variance.
    Returns a noise score — higher means noisier background.
    """
    try:
        arr = np.array(img.convert("L")).astype(np.float64)
        h, w = arr.shape

        # Sample patches from edges/corners (likely background, not text)
        patch_size = min(30, h // 6, w // 6)
        if patch_size < 5:
            return 0.0

        patches = []
        for y, x in [(0, 0), (0, w - patch_size), (h - patch_size, 0),
                      (h - patch_size, w - patch_size),
                      (h // 2, 0), (h // 2, w - patch_size)]:
            patch = arr[y:y + patch_size, x:x + patch_size]
            # Only use patches that look like background (high mean = light)
            if patch.mean() > 180:
                patches.append(float(np.std(patch)))

        if not patches:
            return 0.0

        return sum(patches) / len(patches)
    except Exception:
        return 0.0


def _clean_background(img: Image.Image) -> Image.Image:
    """
    Clean gray/noisy backgrounds while preserving text.
    Uses adaptive approach: if background is gray, apply local contrast
    enhancement to make text stand out against the background.
    """
    try:
        arr = np.array(img.convert("L"))
        h, w = arr.shape

        # Calculate background brightness (sample corners + center edges)
        patch = min(30, h // 4, w // 4)
        regions = [
            arr[0:patch, 0:patch],
            arr[0:patch, max(0, w - patch):w],
            arr[max(0, h - patch):h, 0:patch],
            arr[max(0, h - patch):h, max(0, w - patch):w],
        ]
        bg_mean = float(np.mean([r.mean() for r in regions if r.size > 0]))

        if bg_mean < 200:
            # Dark/gray background — need stronger processing
            # Use a gamma correction to lift dark backgrounds while preserving text
            rgb_arr = np.array(img).astype(np.float64)
            # Compute per-pixel lightness (max channel)
            lightness = rgb_arr.max(axis=2)
            # Build a mask: pixels brighter than text threshold get lifted
            text_threshold = bg_mean * 0.6  # text is darker than background
            bg_mask = (lightness > text_threshold).astype(np.float64)
            # Shift background pixels toward white
            target = 245.0
            shift = (target - bg_mean) * bg_mask
            rgb_arr = np.clip(rgb_arr + shift[:, :, np.newaxis] * 0.8, 0, 255)
            img = Image.fromarray(rgb_arr.astype(np.uint8))
            logger.info(f"Background cleanup: adaptive lift (bg was {bg_mean:.0f})")
        elif bg_mean < 230:
            # Slightly gray — gentle uniform shift
            shift = min(int(240 - bg_mean), 30)
            rgb_arr = np.array(img).astype(np.int16)
            rgb_arr = np.clip(rgb_arr + shift, 0, 255).astype(np.uint8)
            img = Image.fromarray(rgb_arr)
            logger.info(f"Background cleanup: shifted +{shift} (bg was {bg_mean:.0f})")

        return img
    except Exception:
        return img


def _normalize_contrast(img: Image.Image) -> Image.Image:
    """
    Normalize contrast to a consistent level.
    Only boosts if image is low-contrast.
    """
    try:
        arr = np.array(img.convert("L"))
        std = float(np.std(arr))

        # Target std dev around 60-70 for good text contrast
        if std < 40:
            # Low contrast — boost
            factor = min(70.0 / max(std, 10), 1.8)
            img = ImageEnhance.Contrast(img).enhance(factor)
            logger.info(f"Contrast normalized: std={std:.0f}, factor={factor:.2f}")
        elif std > 90:
            # Too high contrast — slight reduction
            img = ImageEnhance.Contrast(img).enhance(0.9)

        return img
    except Exception:
        return img


# ---------------------------------------------------------------------------
# 2. Multi-Page Classification
# ---------------------------------------------------------------------------

PAGE_TYPES = {"header", "line_items", "totals", "terms"}


async def classify_pages(images_b64: list, llm_key: str) -> list:
    """
    Classify each page of a multi-page document using one LLM call.
    Returns e.g. ['header', 'line_items', 'totals'].
    Falls back to heuristic on failure.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    prompt = (
        f"You are analyzing a {len(images_b64)}-page invoice/receipt document.\n"
        "For EACH page (image), classify it as exactly ONE of:\n"
        '- "header"     — vendor name, address, invoice number, date\n'
        '- "line_items" — table/list of purchased items with quantities & prices\n'
        '- "totals"     — subtotal, tax, total, payment summary\n'
        '- "terms"      — terms & conditions, notes, legal, mostly blank\n\n'
        "If a page has BOTH header info AND line items → \"header\".\n"
        "If a page has BOTH line items AND totals   → \"totals\".\n"
        "Default to the dominant content type.\n\n"
        "Return ONLY a JSON array of strings, one per page. Example:\n"
        '["header", "line_items", "totals"]\n'
    )

    try:
        chat = (
            LlmChat(
                api_key=llm_key,
                session_id=f"classify-{uuid.uuid4()}",
                system_message="Classify invoice pages. Return JSON arrays only.",
            )
            .with_model("openai", "gpt-5.2")
        )
        file_contents = [ImageContent(image_base64=b64) for b64 in images_b64]
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=file_contents)
        )

        match = re.search(r"\[[\s\S]*?\]", response)
        if match:
            raw = json.loads(match.group())
            result = [
                (c.lower().strip() if c.lower().strip() in PAGE_TYPES else "line_items")
                for c in raw
            ]
            # Pad / trim
            while len(result) < len(images_b64):
                result.append("line_items")
            result = result[: len(images_b64)]
            logger.info(f"Page classification: {result}")
            return result

        logger.warning("Could not parse classification response, using heuristic")
        return _default_classifications(len(images_b64))
    except Exception as e:
        logger.warning(f"Page classification LLM failed: {e}")
        return _default_classifications(len(images_b64))


def _default_classifications(n: int) -> list:
    """Heuristic fallback: first=header, middle=line_items, last=totals."""
    if n == 1:
        return ["header"]
    if n == 2:
        return ["header", "totals"]
    return ["header"] + ["line_items"] * (n - 2) + ["totals"]


# ---------------------------------------------------------------------------
# 3. Page-Type-Aware Extraction Prompt
# ---------------------------------------------------------------------------

def build_page_aware_prompt(
    page_types: list,
    vendor_hint: str = "",
) -> str:
    """
    Build a purchase-invoice extraction prompt that tells the LLM
    what each page contains, with explicit priority rules.
    Returns the full prompt string.
    """
    page_desc = "\n".join(
        f"  Page {i + 1}: {ptype.upper().replace('_', ' ')}"
        for i, ptype in enumerate(page_types)
    )

    return f"""You are reading a restaurant purchase invoice/receipt spanning {len(page_types)} page(s).

PAGE MAP (already classified for you):
{page_desc}

EXTRACTION INSTRUCTIONS BY PAGE TYPE:
- HEADER page(s)     → extract supplier_name, invoice_date, invoice_number
- LINE ITEMS page(s) → extract every line item (raw_name, quantity, pack_size, unit_price, total)
- TOTALS page(s)     → extract subtotal, tax, total — these VALUES OVERRIDE any totals on other pages
- TERMS page(s)      → SKIP entirely, do not extract anything

PRIORITY RULES (when same field appears on multiple pages):
- subtotal / tax / total   : TOTALS page wins  >  header page  >  line_items page
- supplier_name / date / # : HEADER page wins   >  totals page  >  line_items page

Output this exact JSON (one object, not per-page):
{{"supplier_name":"","invoice_date":"YYYY-MM-DD","invoice_number":"","items":[{{"raw_name":"","quantity":0,"pack_size":"","unit_price":0,"total":0}}],"subtotal":0,"tax":0,"total":0}}

CRITICAL item-level rules:
- total = quantity × unit_price per item
- If unit_price missing: unit_price = total / quantity
- If quantity missing: quantity = total / unit_price
- Dates → YYYY-MM-DD. Use 0 for missing numbers.
- pack_size: The pack/case size EXACTLY as shown on the invoice (e.g., "10/4 LB", "6/5 LB", "BAG 50 LB", "150 EA", "1 GAL", "2/17.5 LB", "1/25 LB"). Copy this field verbatim from the invoice. Leave empty string if not visible.
- Do NOT duplicate items across overlapping pages. Each item ONCE.
- Return ONLY the JSON object.{vendor_hint}"""


# ---------------------------------------------------------------------------
# 4. Document-Level Merge (fallback utility)
# ---------------------------------------------------------------------------

def merge_extractions(page_results: list, page_types: list) -> dict:
    """
    Merge per-page extraction dicts into one invoice.
    Priority for totals fields:  totals > header > line_items
    Priority for vendor fields:  header > totals > line_items
    """
    merged = {
        "supplier_name": "",
        "invoice_date": "",
        "invoice_number": "",
        "items": [],
        "subtotal": 0,
        "tax": 0,
        "total": 0,
    }

    # --- Vendor / header fields: header page wins ---
    vendor_priority = {"header": 0, "totals": 1, "line_items": 2, "terms": 3}
    for ptype, result in sorted(
        zip(page_types, page_results), key=lambda x: vendor_priority.get(x[0], 3)
    ):
        if not result or ptype == "terms":
            continue
        for fld in ("supplier_name", "invoice_date", "invoice_number"):
            if result.get(fld) and not merged[fld]:
                merged[fld] = result[fld]

    # --- Totals fields: totals page wins ---
    totals_priority = {"totals": 0, "header": 1, "line_items": 2, "terms": 3}
    for ptype, result in sorted(
        zip(page_types, page_results), key=lambda x: totals_priority.get(x[0], 3)
    ):
        if not result or ptype == "terms":
            continue
        if ptype == "totals":
            for fld in ("subtotal", "tax", "total"):
                val = float(result.get(fld, 0) or 0)
                if val:
                    merged[fld] = val
        elif not merged["total"]:
            for fld in ("subtotal", "tax", "total"):
                val = float(result.get(fld, 0) or 0)
                if val:
                    merged[fld] = val

    # --- Items: accumulate + dedup by (name, qty, price) ---
    seen_items = set()
    for ptype, result in zip(page_types, page_results):
        if not result or ptype == "terms":
            continue
        for item in result.get("items", []):
            key = (
                (item.get("raw_name", "") or "").lower().strip(),
                float(item.get("quantity", 0) or 0),
                float(item.get("unit_price", 0) or 0),
            )
            if key[0] and key not in seen_items:
                seen_items.add(key)
                merged["items"].append(item)

    return merged


# ---------------------------------------------------------------------------
# 5. Pack Size Parsing & Normalization (with strict validation)
# ---------------------------------------------------------------------------

# ONLY these units are trusted for $/LB normalization
NORMALIZABLE_UNITS = {"LB", "OZ"}

# Conversion to LB — ONLY LB and OZ
TO_LB = {
    "LB": 1.0,
    "OZ": 0.0625,
}

# All known units (for parsing, not normalization)
KNOWN_UNITS = {
    "LB", "LBS", "KG", "OZ", "G", "GM", "GR", "GRAM", "GRAMS",
    "GAL", "GALLON", "QT", "QUART", "L", "LITER", "ML", "PT", "PINT",
    "EA", "EACH", "CT", "COUNT", "PK", "PACK", "BX", "BOX",
    "CS", "CASE", "BG", "BAG", "DZ", "DOZEN",
    "DIM",  # Dimension-based packs (e.g., 1508X8X3)
}

# Canonical unit mapping
UNIT_CANONICAL = {
    "LBS": "LB", "POUND": "LB", "POUNDS": "LB", "#": "LB",
    "KGS": "KG", "KILO": "KG", "KILOS": "KG", "KILOGRAM": "KG",
    "OZS": "OZ", "OUNCE": "OZ", "OUNCES": "OZ",
    "GALLON": "GAL", "GALLONS": "GAL",
    "QUART": "QT", "QUARTS": "QT",
    "LITER": "L", "LITERS": "L", "LITRE": "L",
    "EACH": "EA", "COUNT": "CT",
    "PACK": "PK", "PACKS": "PK",
    "BOX": "BX", "BOXES": "BX",
    "CASE": "CS", "CASES": "CS",
    "BAG": "BG", "BAGS": "BG",
    "DOZEN": "DZ",
    "GRAM": "G", "GRAMS": "G", "GM": "G",
    "PINT": "PT", "PINTS": "PT",
}


def _canonicalize_unit(raw: str) -> str:
    """Normalize unit string to canonical form."""
    u = raw.strip().upper().rstrip(".")
    return UNIT_CANONICAL.get(u, u)


# Safe prefixes to strip (packaging descriptors that precede the actual size)
_STRIP_PREFIXES = {"CS", "BX", "BG", "PK", "CT", "BAG", "BOX", "CASE", "PACK"}


def _normalize_raw_text(text: str) -> str:
    """
    Clean OCR artifacts from pack size text BEFORE pattern matching.
    Only applies safe, deterministic transformations.
    """
    s = text.strip().upper()
    if not s:
        return s

    # 1. Collapse multiple spaces/tabs
    s = re.sub(r"\s+", " ", s)

    # 2. Remove duplicated separators: "//" → "/"
    s = re.sub(r"/{2,}", "/", s)

    # 3. Strip known prefix glued to digits FIRST (before space insertion)
    #    e.g., "CS1000/7 GM" → "1000/7 GM", "BX24/12 OZ" → "24/12 OZ"
    m = re.match(r"^([A-Z]{2,3})(\d+[/\d].*)", s)
    if m and m.group(1) in _STRIP_PREFIXES:
        s = m.group(2)

    # 4. "WORD+NUMBER" with no space → insert space (AFTER prefix strip)
    #    e.g., "BAG50 LB" → "BAG 50 LB"
    s = re.sub(r"^([A-Z]+)(\d)", r"\1 \2", s)

    # 5. "N/N# WORD" → extract just the "N/N#" part
    #    e.g., "6/7# JAR" → "6/7#" (JAR is packaging descriptor, not unit)
    m = re.match(r"^(\d+/\d+\.?\d*#)\s+[A-Z]+$", s)
    if m:
        s = m.group(1)

    # 6. Normalize spaces around slash: "10 / 4 LB" → "10/4 LB"
    s = re.sub(r"\s*/\s*", "/", s)

    return s.strip()


def parse_pack_size(raw: str) -> dict:
    """
    Parse a pack size string into structured components.
    Returns pack_parse_status: "parsed", "failed", or "not_applicable".

    Only returns structured data when parsing is confident.
    """
    text = (raw or "").strip()

    # --- NOT APPLICABLE: empty input ---
    if not text:
        return {
            "pack_size_raw": "",
            "pack_parse_status": "not_applicable",
            "packs_per_case": None,
            "weight_per_pack": None,
            "unit": None,
            "total_case_weight": None,
        }

    # Normalize OCR artifacts before matching
    upper = _normalize_raw_text(text)

    # --- Try patterns ---
    ppc, wpp, unit = None, None, None

    # Pattern 1: "N/N UNIT" or "N/NUNIT" (e.g., "10/4 LB", "4/5LB", "2/17.5 LB")
    m = re.match(r"^(\d+)\s*/\s*(\d+\.?\d*)\s*([A-Z#]+\.?)$", upper)
    if m:
        ppc, wpp, unit = int(m.group(1)), float(m.group(2)), _canonicalize_unit(m.group(3))

    # Pattern 2: "WORD N UNIT" (e.g., "BAG 50 LB", "CS 10 LB")
    if ppc is None:
        m = re.match(r"^([A-Z]+)\s+(\d+\.?\d*)\s*([A-Z#]+\.?)$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(2)), _canonicalize_unit(m.group(3))

    # Pattern 3: "N UNIT" (e.g., "50 LB", "150 EA", "1 GAL")
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)\s+([A-Z#]+\.?)$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), _canonicalize_unit(m.group(2))

    # Pattern 3b: "NUNIT" no space (e.g., "50LB", "5LB")
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)([A-Z]{2,})$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), _canonicalize_unit(m.group(2))

    # Pattern 4: "N#" (e.g., "10#" = 10 LB)
    if ppc is None:
        m = re.match(r"^(\d+\.?\d*)#$", upper)
        if m:
            ppc, wpp, unit = 1, float(m.group(1)), "LB"

    # Pattern 4b: "NxN" / "NxNUNIT" / "NxN UNIT" (e.g., "1x30", "1x30LB", "12x1 LB")
    if ppc is None:
        m = re.match(r"^(\d+)\s*[xX×]\s*(\d+\.?\d*)\s*([A-Z#]+\.?)?$", upper)
        if m:
            candidate_ppc = int(m.group(1))
            candidate_wpp = float(m.group(2))
            candidate_unit = _canonicalize_unit(m.group(3)) if m.group(3) else "LB"
            if candidate_ppc > 0 and candidate_wpp > 0 and candidate_unit in KNOWN_UNITS:
                ppc, wpp, unit = candidate_ppc, candidate_wpp, candidate_unit

    # Pattern 4c: "NxNxN" 3-segment dimensions (e.g., "1508X8X3" for napkins)
    # Dimension packs: no weight/volume, just a descriptor. Store as-is.
    if ppc is None:
        m = re.match(r"^(\d+)\s*[xX×]\s*(\d+)\s*[xX×]\s*(\d+)\s*$", upper)
        if m:
            ppc, wpp, unit = 1, 1, "DIM"

    # Pattern 5: "N/N#" (e.g., "6/7#" = 6 packs of 7 LB)
    if ppc is None:
        m = re.match(r"^(\d+)\s*/\s*(\d+\.?\d*)#$", upper)
        if m:
            ppc, wpp, unit = int(m.group(1)), float(m.group(2)), "LB"

    # Pattern 6: "N N UNIT" — spaced count+weight (e.g., "2 5 LB" = 2×5 LB)
    #   STRICT: only when all three tokens are clearly [int] [number] [known_unit]
    #   and the first number is small (≤50, typical case count)
    if ppc is None:
        m = re.match(r"^(\d+)\s+(\d+\.?\d*)\s+([A-Z]+)$", upper)
        if m:
            candidate_ppc = int(m.group(1))
            candidate_wpp = float(m.group(2))
            candidate_unit = _canonicalize_unit(m.group(3))
            # Safety: ppc must be ≤ 50 (reasonable case count)
            #         wpp must be > 0
            #         unit must be a known unit
            if (candidate_ppc <= 50 and candidate_wpp > 0
                    and candidate_unit in KNOWN_UNITS):
                ppc, wpp, unit = candidate_ppc, candidate_wpp, candidate_unit

    # --- Validate parsed result ---
    if ppc is not None and wpp is not None and unit is not None:
        # Reject if unit is not a known unit
        if unit not in KNOWN_UNITS:
            logger.warning(
                f"PACK_PARSE_FAILED: '{text}' — unknown unit '{unit}'"
            )
            return {
                "pack_size_raw": text,
                "pack_parse_status": "failed",
                "packs_per_case": None,
                "weight_per_pack": None,
                "unit": None,
                "total_case_weight": None,
            }

        # Reject nonsensical values
        if ppc <= 0 or wpp <= 0:
            logger.warning(
                f"PACK_PARSE_FAILED: '{text}' — invalid values ppc={ppc} wpp={wpp}"
            )
            return {
                "pack_size_raw": text,
                "pack_parse_status": "failed",
                "packs_per_case": None,
                "weight_per_pack": None,
                "unit": None,
                "total_case_weight": None,
            }

        tcw = round(ppc * wpp, 4)
        return {
            "pack_size_raw": text,
            "pack_parse_status": "parsed",
            "packs_per_case": ppc,
            "weight_per_pack": wpp,
            "unit": unit,
            "total_case_weight": tcw,
        }

    # --- FAILED: could not match any pattern ---
    logger.warning(f"PACK_PARSE_FAILED: '{text}' — no pattern matched")
    return {
        "pack_size_raw": text,
        "pack_parse_status": "failed",
        "packs_per_case": None,
        "weight_per_pack": None,
        "unit": None,
        "total_case_weight": None,
    }


def enrich_item_with_pack_size(item: dict) -> dict:
    """
    Parse pack_size, validate, compute normalized $/LB ONLY when 100% reliable.
    Mutates and returns the item.
    """
    pack_size_raw = (
        item.get("pack_size") or item.get("pack_size_raw") or ""
    ).strip()
    parsed = parse_pack_size(pack_size_raw)

    # Always store raw + status
    item["pack_size_raw"] = parsed["pack_size_raw"]
    item["pack_parse_status"] = parsed["pack_parse_status"]

    if parsed["pack_parse_status"] == "parsed":
        item["packs_per_case"] = parsed["packs_per_case"]
        item["weight_per_pack"] = parsed["weight_per_pack"]
        item["pack_unit"] = parsed["unit"]
        item["total_case_weight"] = parsed["total_case_weight"]
    else:
        # Failed or not_applicable — null out all computed fields
        item["packs_per_case"] = None
        item["weight_per_pack"] = None
        item["pack_unit"] = None
        item["total_case_weight"] = None

    # --- $/LB is NOT computed here ---
    # Pricing mode (case_price vs weight_based) can only be determined
    # after math validation in validate_and_score_item().
    # $/LB computation is deferred there.
    item["normalized_price_per_lb"] = None

    return item



# ---------------------------------------------------------------------------
# 6b. Hard Invoice Robustness Layer
# ---------------------------------------------------------------------------

def sanitize_extracted_item(item: dict) -> dict:
    """
    Defensive cleanup of a raw extracted item before validation.
    Handles: type coercion, garbled values, negative numbers, nulls.
    Mutates and returns the item.
    """
    parse_issues = []

    # Coerce numeric fields safely
    for field in ("quantity", "unit_price", "total"):
        val = item.get(field)
        if val is None:
            item[field] = 0
            continue
        if isinstance(val, str):
            cleaned = re.sub(r'[^0-9.\-]', '', val)
            try:
                item[field] = float(cleaned) if cleaned else 0
            except ValueError:
                parse_issues.append(f"non-numeric {field}: {repr(val)}")
                item[field] = 0
        else:
            try:
                item[field] = float(val)
            except (ValueError, TypeError):
                parse_issues.append(f"unparseable {field}: {repr(val)}")
                item[field] = 0

    # Negative values handling:
    # - quantity and unit_price: likely OCR errors → convert to absolute
    # - total: may be a legitimate credit/return → preserve the sign
    for field in ("quantity", "unit_price"):
        if item[field] < 0:
            parse_issues.append(f"negative {field}: {item[field]}, using absolute value")
            item[field] = abs(item[field])

    if item["total"] < 0:
        # Preserve negative total for credit/return lines
        parse_issues.append(f"negative total: {item['total']}, preserved as credit")

    # Sanitize name
    name = item.get("raw_name", "")
    if isinstance(name, (int, float)):
        name = str(name)
    item["raw_name"] = (name or "").strip()

    # Sanitize pack_size
    ps = item.get("pack_size")
    if ps is None or (isinstance(ps, (int, float)) and ps == 0):
        item["pack_size"] = ""
    else:
        item["pack_size"] = str(ps).strip()

    if parse_issues:
        item["_parse_issues"] = parse_issues

    return item


def detect_column_misread(items: list) -> list:
    """
    Detect likely column misalignment from OCR/extraction.
    E.g., quantity column has values like 42.50 (looks like prices),
    or unit_price column has values like 2 (looks like quantities).
    Returns list of issue strings.
    """
    issues = []
    if len(items) < 3:
        return issues

    qty_vals = [float(it.get("quantity", 0) or 0) for it in items if float(it.get("quantity", 0) or 0) > 0]
    price_vals = [float(it.get("unit_price", 0) or 0) for it in items if float(it.get("unit_price", 0) or 0) > 0]

    if not qty_vals or not price_vals:
        return issues

    avg_qty = sum(qty_vals) / len(qty_vals)
    avg_price = sum(price_vals) / len(price_vals)

    # Typical restaurant: qty 1-50, price 5-500
    # If avg "quantity" is much higher than avg "price", they may be swapped
    if avg_qty > avg_price * 3 and avg_price < 20 and avg_qty > 10:
        issues.append(f"possible column swap: avg quantity={avg_qty:.1f} looks like prices, avg price={avg_price:.1f} looks like quantities")

    # Check if most quantities have cents (e.g., 42.50, 18.99)
    decimal_qtys = sum(1 for q in qty_vals if q != int(q) and q > 5)
    if decimal_qtys > len(qty_vals) * 0.5 and len(qty_vals) >= 3:
        issues.append("most quantities have decimal values — likely prices in quantity column")

    return issues


def compute_extraction_meta(items: list, extracted_data: dict) -> dict:
    """
    Compute invoice-level extraction quality metadata.
    Runs AFTER item-level validation. Returns a meta dict.
    """
    total_items = len(items)
    meta = {
        "extraction_confidence": "high",
        "extraction_issues": [],
        "items_extracted": total_items,
        "items_with_issues": 0,
        "partial_extraction": False,
    }

    if total_items == 0:
        meta["extraction_confidence"] = "low"
        meta["extraction_issues"].append("no items extracted")
        meta["partial_extraction"] = True
    else:
        issues_count = 0
        empty_names = 0
        garbled_names = 0
        zero_totals = 0

        for item in items:
            has_issue = False
            name = (item.get("raw_name") or "").strip()
            total = float(item.get("total", 0) or 0)

            if not name:
                empty_names += 1
                has_issue = True
            elif not _item_name_looks_clear(name):
                garbled_names += 1
                has_issue = True

            if total == 0:
                zero_totals += 1
                has_issue = True

            if item.get("needs_review"):
                has_issue = True

            if has_issue:
                issues_count += 1

        meta["items_with_issues"] = issues_count
        issue_ratio = issues_count / total_items

        if issue_ratio > 0.7:
            meta["extraction_confidence"] = "low"
        elif issue_ratio > 0.3:
            meta["extraction_confidence"] = "medium"

        if empty_names > total_items * 0.5:
            meta["extraction_issues"].append(f"{empty_names}/{total_items} items missing names")
            meta["extraction_confidence"] = "low"

        if garbled_names > total_items * 0.3:
            meta["extraction_issues"].append(f"{garbled_names}/{total_items} items have garbled names")

        if zero_totals > total_items * 0.5:
            meta["extraction_issues"].append(f"{zero_totals}/{total_items} items have zero totals")
            meta["partial_extraction"] = True

        # Column misread detection
        col_issues = detect_column_misread(items)
        if col_issues:
            meta["extraction_issues"].extend(col_issues)
            if meta["extraction_confidence"] == "high":
                meta["extraction_confidence"] = "medium"

        # Subtotal consistency
        items_sum = round(sum(float(it.get("total", 0) or 0) for it in items), 2)
        subtotal = float(extracted_data.get("subtotal", 0) or 0)
        if items_sum > 0 and subtotal > 0:
            diff_pct = abs(items_sum - subtotal) / subtotal
            if diff_pct > 0.20:
                meta["extraction_issues"].append(f"items sum (${items_sum:.2f}) differs from subtotal (${subtotal:.2f}) by {diff_pct*100:.0f}%")
                if meta["extraction_confidence"] == "high":
                    meta["extraction_confidence"] = "medium"

    # Missing header data
    if not (extracted_data.get("supplier_name") or "").strip():
        meta["extraction_issues"].append("supplier name not detected")
    if not (extracted_data.get("invoice_date") or "").strip():
        meta["extraction_issues"].append("invoice date not detected")
    if not (extracted_data.get("invoice_number") or "").strip():
        meta["extraction_issues"].append("invoice number not detected")

    return meta


def salvage_partial_extraction(raw_response: str) -> dict:
    """
    When JSON parsing fails entirely, try to salvage partial data
    from the raw GPT response using regex.
    Returns a best-effort dict (may be mostly empty).
    """
    result = {"items": [], "_salvaged": True}

    # Try individual JSON fields
    for field, pattern in [
        ("supplier_name", r'"supplier_name"\s*:\s*"([^"]*)"'),
        ("invoice_number", r'"invoice_number"\s*:\s*"([^"]*)"'),
        ("invoice_date", r'"invoice_date"\s*:\s*"([^"]*)"'),
    ]:
        m = re.search(pattern, raw_response)
        if m:
            result[field] = m.group(1).strip()

    # Try to find a date anywhere
    if not result.get("invoice_date"):
        m = re.search(r'(\d{4}-\d{2}-\d{2})', raw_response)
        if m:
            result["invoice_date"] = m.group(1)

    # Try to extract items array even if outer JSON is broken
    items_match = re.search(r'"items"\s*:\s*\[([\s\S]*?)\]', raw_response)
    if items_match:
        try:
            items_json = "[" + items_match.group(1) + "]"
            items = json.loads(items_json)
            if isinstance(items, list):
                result["items"] = items
        except (json.JSONDecodeError, ValueError):
            pass

    # Try to find total
    for field, patterns in [
        ("total", [r'"total"\s*:\s*([0-9.]+)', r'total[:\s]+\$?([0-9,.]+)']),
        ("subtotal", [r'"subtotal"\s*:\s*([0-9.]+)']),
        ("tax", [r'"tax"\s*:\s*([0-9.]+)']),
    ]:
        for p in patterns:
            m = re.search(p, raw_response, re.IGNORECASE)
            if m:
                try:
                    result[field] = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
                break

    return result


# ---------------------------------------------------------------------------
# 7. Confidence & Validation Layer (Strict — Trust > Coverage)
# ---------------------------------------------------------------------------

def _item_name_looks_clear(name: str) -> bool:
    """Heuristic: does the item name look like a real product name, not garbled OCR?"""
    if not name or len(name.strip()) < 2:
        return False
    s = name.strip()
    alpha = sum(1 for c in s if c.isalpha())
    if alpha < len(s) * 0.3:
        return False
    tokens = s.split()
    if len(tokens) == 1 and len(s) > 40:
        return False
    return True


def _detect_suspicious_patterns(item: dict) -> list:
    """Detect suspicious patterns that should prevent trusted status."""
    flags = []
    qty = float(item.get("quantity", 0) or 0)
    up = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)
    tcw = item.get("total_case_weight")

    # Unrealistic pack sizes — check case weight in LB equivalent
    ppc = item.get("packs_per_case")
    if ppc is not None and ppc > 200:
        flags.append(f"unrealistic packs_per_case: {ppc}")
    if tcw is not None and tcw > 0:
        pack_unit = (item.get("pack_unit") or "").upper()
        # Convert to LB for comparison: 5000 LB is unrealistic, but 5000 GM (11 LB) is normal
        unit_to_lb = {"LB": 1.0, "OZ": 0.0625, "G": 0.0022046, "GM": 0.0022046,
                      "KG": 2.2046, "DIM": 0}
        lb_factor = unit_to_lb.get(pack_unit, 1.0)
        tcw_in_lb = tcw * lb_factor
        if tcw_in_lb > 5000:
            flags.append(f"unrealistic case weight: {tcw} {pack_unit} ({tcw_in_lb:.0f} LB)")

    # Defaulted/placeholder values
    if qty == 1 and up == 0 and total == 0:
        flags.append("likely defaulted values (qty=1, price=0, total=0)")
    if qty > 0 and up > 0 and qty == up:
        flags.append(f"qty equals unit_price ({qty}) — possible OCR misread")

    # Extremely high or low prices
    if up > 50000:
        flags.append(f"unit_price suspiciously high: ${up}")
    if total > 0 and up > 0 and up > total:
        flags.append("unit_price > total")

    return flags


def _generate_suggested_fix(item: dict) -> dict | None:
    """
    Generate a lightweight, rule-based correction suggestion for a flagged item.
    Returns a dict with suggested field changes, or None if no suggestion available.

    Uses ONLY: math, raw text parsing, existing normalization data.
    No LLM calls. No fuzzy matching.
    """
    suggestion = {}
    reasons = []

    qty = float(item.get("quantity") or 0)
    up = float(item.get("unit_price") or 0)
    total = float(item.get("total") or 0)
    raw_name = (item.get("raw_name") or "").strip()
    pack_raw = (item.get("pack_size_raw") or item.get("pack_size") or "").strip()
    pack_status = item.get("pack_parse_status") or "not_applicable"
    tcw = float(item.get("total_case_weight") or 0)
    pack_unit = item.get("pack_unit") or ""
    pricing_mode = item.get("pricing_mode", "unknown")

    # --- 1. Math mismatch / missing fields → suggest corrected values ---
    # Use detected pricing mode; default to case_price (simple math)
    if pricing_mode == "weight_based" and tcw > 0:
        lb_factor = 1.0 if pack_unit == "LB" else 0.0625
        case_wt_lb = tcw * lb_factor
        if qty > 0 and up > 0 and total > 0:
            expected = round(qty * case_wt_lb * up, 2)
            tolerance = max(0.02, 0.01 * total)
            simple_expected = round(qty * up, 2)
            if abs(expected - total) > tolerance and abs(simple_expected - total) > tolerance:
                suggestion["total"] = expected
                reasons.append(f"Recalculate total: {qty} × {case_wt_lb:.1f}LB × ${up:.2f}/LB = ${expected:.2f}")
        elif qty > 0 and up > 0 and total == 0:
            computed = round(qty * case_wt_lb * up, 2)
            suggestion["total"] = computed
            reasons.append(f"Compute total: {qty} × {case_wt_lb:.1f}LB × ${up:.2f}/LB = ${computed:.2f}")
        elif total > 0 and qty > 0 and case_wt_lb > 0 and up == 0:
            computed = round(total / (qty * case_wt_lb), 2)
            suggestion["unit_price"] = computed
            reasons.append(f"Compute $/LB: ${total:.2f} ÷ ({qty} × {case_wt_lb:.1f}LB) = ${computed:.2f}/LB")
    else:
        # Case-price or unknown: Total = Qty × Price
        if qty > 0 and up > 0 and total > 0:
            expected = round(qty * up, 2)
            tolerance = max(0.02, 0.01 * total)
            if abs(expected - total) > tolerance:
                suggestion["total"] = expected
                reasons.append(f"Recalculate total: {qty} × ${up:.2f} = ${expected:.2f}")
        elif qty > 0 and up > 0 and total == 0:
            suggestion["total"] = round(qty * up, 2)
            reasons.append(f"Compute total: {qty} × ${up:.2f} = ${suggestion['total']:.2f}")
        elif total > 0 and qty > 0 and up == 0:
            suggestion["unit_price"] = round(total / qty, 2)
            reasons.append(f"Compute price: ${total:.2f} ÷ {qty} = ${suggestion['unit_price']:.2f}")
        elif total > 0 and up > 0 and qty == 0:
            suggestion["quantity"] = round(total / up, 2)
            reasons.append(f"Compute quantity: ${total:.2f} ÷ ${up:.2f} = {suggestion['quantity']}")

    # --- 2. Pack parse failure → try to recover from raw text ---
    if pack_status == "failed" and pack_raw:
        upper = pack_raw.upper().strip()
        # Try common OCR variants: "1x30" → "1/30", "1X30LB" → "1/30 LB"
        normalized = re.sub(r'[xX×]', '/', upper)
        # Ensure space before unit: "30LB" → "30 LB"
        normalized = re.sub(r'(\d)(LB|OZ|GAL|EA|CT|KG|QT|PT|CS|PK|BX)\b', r'\1 \2', normalized)
        if normalized != upper:
            # Try parsing the normalized version
            test_result = parse_pack_size(normalized)
            if test_result.get("pack_parse_status") == "parsed":
                suggestion["pack_size"] = normalized
                reasons.append(f"Normalize pack size: \"{pack_raw}\" → \"{normalized}\"")

    # --- 3. Correction memory match → already applied by pipeline, surface it ---
    correction = item.get("correction_applied")
    if correction and isinstance(correction, dict):
        if correction.get("corrected_name") and correction["corrected_name"] != raw_name:
            suggestion["raw_name"] = correction["corrected_name"]
            reasons.append(f"Learned correction: \"{raw_name}\" → \"{correction['corrected_name']}\"")
        if correction.get("corrected_specs") and isinstance(correction["corrected_specs"], dict):
            for k, v in correction["corrected_specs"].items():
                if v and str(v) != str(item.get(k, "")):
                    suggestion[k] = v
                    reasons.append(f"Learned {k}: \"{item.get(k, '')}\" → \"{v}\"")

    # --- 4. Missing name but has normalization data ---
    if not raw_name:
        clean = (item.get("clean_name") or "").strip()
        if clean:
            suggestion["raw_name"] = clean
            reasons.append(f"Use normalized name: \"{clean}\"")

    if not reasons:
        return None

    return {
        "fields": suggestion,
        "reasons": reasons,
        "type": "math" if "total" in suggestion or "unit_price" in suggestion or "quantity" in suggestion
            else "pack" if "pack_size" in suggestion
            else "correction" if correction
            else "missing",
    }



def validate_and_score_item(item: dict) -> dict:
    """
    Strict validation and confidence scoring.
    Uses HARD GATES: any critical failure forces 'unverified' status.
    Trust > Coverage — conservative classification.

    Mutates and returns the item with:
      - valid_calc: bool
      - validation_errors: list[str]
      - confidence_score: int (0-100)
      - confidence_level: "trusted" | "unverified"
    """
    errors = []
    score = 0
    hard_fail = False  # Any hard fail → forced unverified

    raw_name = (item.get("raw_name") or "").strip()
    qty = float(item.get("quantity", 0) or 0)
    up = float(item.get("unit_price", 0) or 0)
    total = float(item.get("total", 0) or 0)
    pack_status = item.get("pack_parse_status") or "not_applicable"
    pack_size_raw = item.get("pack_size_raw") or item.get("pack_size") or ""

    # ===== HARD GATE 1: Math validation + Pricing mode detection =====
    # Try SIMPLE math first: Qty × Price = Total  (CASE_PRICE mode)
    # Only if simple fails, try WEIGHT math: Qty × CaseWT × Price/LB = Total  (WEIGHT_BASED mode)
    valid_calc = False
    pack_status = item.get("pack_parse_status") or "not_applicable"
    pack_size_raw = item.get("pack_size_raw") or item.get("pack_size") or ""
    tcw = float(item.get("total_case_weight") or 0)
    pack_unit = item.get("pack_unit") or ""
    has_weight_pack = pack_status == "parsed" and tcw > 0 and pack_unit in ("LB", "OZ")
    pricing_mode = "unknown"

    if qty > 0 and up > 0 and total > 0:
        simple_expected = round(qty * up, 2)
        tolerance = max(0.02, 0.01 * total)

        if abs(simple_expected - total) <= tolerance:
            # Simple math passes → CASE_PRICE mode
            valid_calc = True
            score += 40
            pricing_mode = "case_price"
        elif has_weight_pack:
            # Simple math fails — try weight-based
            lb_factor = 1.0 if pack_unit == "LB" else 0.0625
            case_wt_lb = tcw * lb_factor
            weight_expected = round(qty * case_wt_lb * up, 2)
            if abs(weight_expected - total) <= tolerance:
                valid_calc = True
                score += 40
                pricing_mode = "weight_based"
            else:
                hard_fail = True
                errors.append(f"MATH MISMATCH: qty({qty})×price(${up:.2f})=${simple_expected:.2f} and qty({qty})×{case_wt_lb:.1f}LB×${up:.2f}=${weight_expected:.2f}, neither matches total(${total:.2f})")
        else:
            # No weight pack, simple math failed
            hard_fail = True
            errors.append(f"MATH MISMATCH: qty({qty})×price(${up:.2f})=${simple_expected:.2f} ≠ total(${total:.2f})")
    elif total > 0 and (qty == 0 or up == 0):
        hard_fail = True
        errors.append("total exists but qty or unit_price is missing/zero")
    elif qty > 0 and up > 0 and total == 0:
        hard_fail = True
        errors.append("qty and price exist but total is missing/zero")
        # Infer mode from simple math
        pricing_mode = "case_price"
    else:
        hard_fail = True
        errors.append("missing core numeric fields (qty, unit_price, total)")

    item["pricing_mode"] = pricing_mode

    # ===== Compute $/LB based on detected pricing mode =====
    if has_weight_pack and pricing_mode == "case_price" and up > 0 and tcw > 0:
        # Price is per case → derive $/LB = CasePrice / CaseWT
        lb_factor = 1.0 if pack_unit == "LB" else 0.0625
        total_lb = tcw * lb_factor
        if total_lb > 0:
            item["normalized_price_per_lb"] = round(up / total_lb, 4)
    elif has_weight_pack and pricing_mode == "weight_based" and up > 0:
        # Price IS $/LB directly
        item["normalized_price_per_lb"] = round(up, 4)
    # else: leave as None (set by enrich_item_with_pack_size)

    # ===== HARD GATE 2: Required fields =====
    missing = []
    if not raw_name:
        missing.append("item_name")
        hard_fail = True
    if qty <= 0:
        missing.append("qty")
    if up <= 0:
        missing.append("unit_price")
    if total <= 0:
        missing.append("line_total")
    if not missing:
        score += 20
    else:
        errors.append(f"missing: {', '.join(missing)}")

    # ===== Service row detection =====
    # Service rows (fuel surcharge, delivery, etc.) bypass pack validation
    SERVICE_KW = {"delivery", "fuel", "surcharge", "credit", "discount", "freight",
                  "handling", "service", "charge", "fee", "adjustment", "return",
                  "deposit", "rebate", "refund", "coupon", "promo", "minimum"}
    name_lower = raw_name.lower()
    name_words = set(name_lower.split())
    is_service_row = bool(name_words & SERVICE_KW) and len(name_words) <= 4

    # ===== HARD GATE 3: Pack size — context-aware =====
    # Service rows: skip pack validation entirely
    # Product rows: pack parse failure is NOT a hard fail when math passes
    has_pack = bool(pack_size_raw.strip())
    if is_service_row:
        score += 15  # Service rows get baseline pack credit
    elif has_pack:
        if pack_status == "parsed":
            score += 20
        elif pack_status == "failed":
            if valid_calc:
                # Math passes → pack failure is informational, NOT hard fail
                score += 10
                errors.append(f"pack_size format unrecognized: \"{pack_size_raw}\" (math OK, informational)")
            else:
                hard_fail = True
                errors.append(f"pack_size parse failed: \"{pack_size_raw}\"")
    else:
        score += 15

    # ===== CHECK 4: Item name quality =====
    if _item_name_looks_clear(raw_name):
        score += 20
    else:
        errors.append("item name may be garbled or missing")

    # ===== CHECK 5: Suspicious patterns =====
    sus_flags = _detect_suspicious_patterns(item)
    if sus_flags:
        hard_fail = True
        for f in sus_flags:
            errors.append(f"SUSPICIOUS: {f}")

    # ===== Normalized price safety =====
    nplb = item.get("normalized_price_per_lb")
    if nplb is not None and nplb > 0:
        if pack_status != "parsed":
            errors.append("normalized price exists but pack_parse_status != parsed — cleared")
            item["normalized_price_per_lb"] = None
        else:
            pack_unit = (item.get("pack_unit") or "").upper()
            if pack_unit not in NORMALIZABLE_UNITS:
                errors.append(f"normalized price exists but unit '{pack_unit}' is not weight-based — cleared")
                item["normalized_price_per_lb"] = None

    # ===== Final classification: Strict Decision Gate =====
    # No row becomes "trusted" unless ALL conditions pass:
    #   1. qty from defined column (qty > 0)
    #   2. unit_price from defined column (up > 0)
    #   3. total from defined column (total > 0)
    #   4. math validated (valid_calc = True)
    #   5. item name present
    #   6. no hard failures
    score = max(0, min(100, score))

    # Determine review status taxonomy:
    #   trusted            — all gates pass, no ambiguity
    #   needs_review_light — minor issues (pack format, name quality) but math OK
    #   needs_review_numeric — math mismatch or missing numeric field
    #   extraction_failed  — critical fields missing or garbled
    #   vendor_unsupported — vendor not yet supported (PFG limited, US Foods)

    all_fields_present = (qty > 0 and up > 0 and total > 0 and bool(raw_name))

    if hard_fail:
        if not raw_name or (qty == 0 and up == 0 and total == 0):
            level = "extraction_failed"
        elif not valid_calc:
            level = "needs_review_numeric"
        else:
            level = "needs_review_numeric"
    elif not all_fields_present:
        if total > 0 and (qty == 0 or up == 0):
            level = "needs_review_numeric"
        else:
            level = "extraction_failed"
    elif not valid_calc:
        level = "needs_review_numeric"
    elif score >= 85:
        level = "trusted"
    else:
        level = "needs_review_light"

    item["valid_calc"] = valid_calc
    item["validation_errors"] = errors
    item["confidence_score"] = score
    item["confidence_level"] = level

    # Human-readable primary reason
    if level == "trusted":
        item["confidence_reason"] = "All gates passed"
    elif level == "extraction_failed":
        if not raw_name:
            item["confidence_reason"] = "Missing item name — extraction failure"
        else:
            item["confidence_reason"] = "Critical fields missing — extraction failure"
    elif level == "needs_review_numeric":
        if not valid_calc and qty > 0 and up > 0 and total > 0:
            item["confidence_reason"] = "Math mismatch (qty × price ≠ total)"
        elif missing:
            item["confidence_reason"] = f"Missing numeric fields: {', '.join(missing)}"
        elif sus_flags:
            item["confidence_reason"] = "Suspicious numeric values"
        else:
            item["confidence_reason"] = "Numeric validation failed"
    elif level == "needs_review_light":
        if has_pack and pack_status == "failed":
            item["confidence_reason"] = "Pack format unrecognized (math OK)"
        else:
            item["confidence_reason"] = "Minor quality issues (math OK)"
    elif level == "vendor_unsupported":
        item["confidence_reason"] = "Vendor not yet fully supported"
    else:
        item["confidence_reason"] = "Review required"

    # needs_review: true for anything except trusted
    item["needs_review"] = level != "trusted"
    item["review_reason"] = item["confidence_reason"] if level != "trusted" else None

    # Row type classification
    item["row_type"] = "service" if is_service_row else "product"

    # Generate lightweight correction suggestion for flagged items
    if level != "trusted":
        item["suggested_fix"] = _generate_suggested_fix(item)
    else:
        item["suggested_fix"] = None

    return item


def validate_purchase_items(items: list) -> list:
    """
    Cross-item validation: detect suspicious patterns across all items in a purchase.
    Call AFTER individual validate_and_score_item on each item.
    """
    if len(items) < 2:
        return items

    # Detect repeated identical values across rows
    prices = [float(it.get("unit_price", 0) or 0) for it in items]
    totals = [float(it.get("total", 0) or 0) for it in items]
    names = [(it.get("raw_name") or "").strip().upper() for it in items]

    # Check for duplicate rows (same name + same price + same total)
    seen = set()
    for idx, it in enumerate(items):
        key = (names[idx], prices[idx], totals[idx])
        if key in seen and names[idx]:
            if "SUSPICIOUS: duplicate row" not in (it.get("validation_errors") or []):
                it.setdefault("validation_errors", []).append("SUSPICIOUS: duplicate row (same name, price, total)")
                it["confidence_level"] = "unverified"
        seen.add(key)

    # Check if ALL prices are identical (unlikely in real invoices with >3 items)
    nonzero_prices = [p for p in prices if p > 0]
    if len(nonzero_prices) >= 4 and len(set(nonzero_prices)) == 1:
        for it in items:
            if float(it.get("unit_price", 0) or 0) > 0:
                if "SUSPICIOUS: all items have identical price" not in (it.get("validation_errors") or []):
                    it.setdefault("validation_errors", []).append("SUSPICIOUS: all items have identical price")
                    it["confidence_level"] = "unverified"

    return items



def compute_review_status(items: list) -> str:
    """
    Compute invoice-level review status from item validation signals.
    Returns: "clean" | "warning" | "error"
    - clean:   no items need review
    - warning: some items need review (minor issues)
    - error:   items have hard errors (math mismatch, missing name, suspicious)

    Resilient: if needs_review isn't set on items, infers from raw data.
    """
    has_warning = False
    has_error = False
    for item in items:
        # Determine if this item needs review — use explicit flag when available,
        # otherwise infer from raw data (handles old items without validation fields)
        needs_review = item.get("needs_review")
        if needs_review is None:
            cl = item.get("confidence_level")
            if cl == "trusted":
                continue
            if cl == "unverified":
                needs_review = True
            else:
                # No validation fields at all — check raw data
                name = (item.get("raw_name") or "").strip()
                qty = float(item.get("quantity") or 0)
                up = float(item.get("unit_price") or 0)
                total = float(item.get("total") or 0)
                if not name:
                    needs_review = True
                elif qty > 0 and up > 0 and total > 0:
                    # Try simple math first (case price), then weight-based
                    tol = max(0.02, 0.01 * total)
                    simple = round(qty * up, 2)
                    if abs(simple - total) <= tol:
                        needs_review = False
                    else:
                        tcw_val = float(item.get("total_case_weight") or 0)
                        p_unit = item.get("pack_unit") or ""
                        if tcw_val > 0 and p_unit in ("LB", "OZ"):
                            lb_f = 1.0 if p_unit == "LB" else 0.0625
                            wb = round(qty * tcw_val * lb_f * up, 2)
                            needs_review = abs(wb - total) > tol
                        else:
                            needs_review = True
                elif qty <= 0 or up <= 0 or total <= 0:
                    needs_review = True
                else:
                    needs_review = False
        if not needs_review:
            continue

        # Determine severity: error vs warning
        errors = item.get("validation_errors", [])
        reason = (item.get("review_reason") or "").lower()
        name = (item.get("raw_name") or "").strip()
        is_hard = (
            any("math mismatch" in e.lower() or "suspicious" in e.lower() or "item_name" in e.lower() for e in errors)
            or "math mismatch" in reason
            or "missing item name" in reason
            or "suspicious" in reason
            or not name
        )
        # Also check raw math as fallback for items without validation_errors
        if not is_hard and not errors:
            qty = float(item.get("quantity") or 0)
            up = float(item.get("unit_price") or 0)
            total = float(item.get("total") or 0)
            if qty > 0 and up > 0 and total > 0:
                tol = max(0.02, 0.01 * total)
                simple = round(qty * up, 2)
                if abs(simple - total) <= tol:
                    pass  # Simple math passes — no error
                else:
                    tcw_val = float(item.get("total_case_weight") or 0)
                    p_unit = item.get("pack_unit") or ""
                    if tcw_val > 0 and p_unit in ("LB", "OZ"):
                        lb_f = 1.0 if p_unit == "LB" else 0.0625
                        wb = round(qty * tcw_val * lb_f * up, 2)
                        if abs(wb - total) > tol:
                            is_hard = True
                    else:
                        is_hard = True
        if is_hard:
            has_error = True
        else:
            has_warning = True
    if has_error:
        return "error"
    if has_warning:
        return "warning"
    return "clean"
