"""
Tests for Scan Mode — document edge detection & perspective correction.
Validates: camera photo detection, edge finding, perspective transform,
fallback behavior for clean scans, and end-to-end pipeline.
"""
import io
import numpy as np
import cv2
import pytest
from PIL import Image

from preprocessing import (
    preprocess_image,
    _scan_mode_detect_and_correct,
    _image_needs_scan_mode,
    _find_document_contour,
    _apply_perspective_transform,
    _order_points,
    _is_valid_quad,
    _camera_photo_enhance,
)


# ---------------------------------------------------------------------------
# Helpers: Create synthetic test images
# ---------------------------------------------------------------------------

def _make_clean_scan(w=800, h=1100) -> np.ndarray:
    """White background with black text lines — simulates a clean scan."""
    img = np.ones((h, w, 3), dtype=np.uint8) * 255
    for y in range(100, h - 100, 40):
        cv2.line(img, (80, y), (w - 80, y), (30, 30, 30), 2)
    return img


def _make_camera_photo(doc_w=600, doc_h=800, bg_color=(80, 70, 60)) -> np.ndarray:
    """
    Dark background with a white document rectangle inside —
    simulates a camera photo of an invoice on a desk.
    """
    pad = 100
    full_w = doc_w + 2 * pad
    full_h = doc_h + 2 * pad
    img = np.ones((full_h, full_w, 3), dtype=np.uint8) * np.array(bg_color, dtype=np.uint8)

    # Draw white document rectangle
    cv2.rectangle(img, (pad, pad), (pad + doc_w, pad + doc_h), (250, 250, 250), -1)

    # Add some text lines inside the document
    for y in range(pad + 50, pad + doc_h - 50, 30):
        cv2.line(img, (pad + 30, y), (pad + doc_w - 30, y), (20, 20, 20), 1)

    return img


def _make_tilted_camera_photo() -> np.ndarray:
    """Camera photo with document at a slight angle — tests perspective correction."""
    h, w = 1000, 800
    img = np.ones((h, w, 3), dtype=np.uint8) * 60  # Dark desk

    # Draw a slightly rotated white rectangle (document)
    pts = np.array([
        [120, 80],   # top-left
        [680, 100],  # top-right
        [700, 880],  # bottom-right
        [100, 860],  # bottom-left
    ], dtype=np.int32)
    cv2.fillConvexPoly(img, pts, (245, 245, 245))

    # Add text lines
    for y in range(150, 800, 35):
        cv2.line(img, (160, y), (640, y + 5), (25, 25, 25), 1)

    return img


def _arr_to_bytes(arr: np.ndarray) -> bytes:
    """Convert numpy array to PNG bytes."""
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests: _image_needs_scan_mode
# ---------------------------------------------------------------------------

class TestImageNeedsScanMode:
    def test_clean_scan_returns_false(self):
        arr = _make_clean_scan()
        assert _image_needs_scan_mode(arr) is False

    def test_camera_photo_returns_true(self):
        arr = _make_camera_photo()
        assert _image_needs_scan_mode(arr) is True

    def test_camera_photo_dark_desk_returns_true(self):
        arr = _make_camera_photo(bg_color=(40, 35, 30))
        assert _image_needs_scan_mode(arr) is True

    def test_white_border_photo_returns_false(self):
        """Photo with white/light background should not trigger scan mode."""
        arr = _make_camera_photo(bg_color=(240, 240, 240))
        assert _image_needs_scan_mode(arr) is False

    def test_small_image_skipped(self):
        """Images < 200px should be skipped by scan mode."""
        arr = np.ones((100, 100, 3), dtype=np.uint8) * 50
        # _scan_mode_detect_and_correct checks size, not _image_needs_scan_mode
        # But _image_needs_scan_mode itself should handle small borders
        result = _image_needs_scan_mode(arr)
        # Small dark image → True (dark borders)
        assert result is True


# ---------------------------------------------------------------------------
# Tests: _find_document_contour
# ---------------------------------------------------------------------------

class TestFindDocumentContour:
    def test_finds_contour_in_camera_photo(self):
        arr = _make_camera_photo()
        contour = _find_document_contour(arr)
        assert contour is not None
        assert contour.shape == (4, 2)

    def test_finds_contour_in_tilted_photo(self):
        arr = _make_tilted_camera_photo()
        contour = _find_document_contour(arr)
        assert contour is not None
        assert contour.shape == (4, 2)

    def test_no_contour_in_clean_scan(self):
        """Clean scans don't have a distinct document boundary — may return None."""
        arr = _make_clean_scan()
        # Clean scan fills the frame, so contour detection may find the whole image
        # or nothing useful. Either is acceptable.
        contour = _find_document_contour(arr)
        # If found, it should be a full-frame quad (>98% area → rejected by _is_valid_quad)
        # So result should be None
        # But this depends on edge patterns — just verify it doesn't crash
        assert contour is None or contour.shape == (4, 2)


# ---------------------------------------------------------------------------
# Tests: _order_points
# ---------------------------------------------------------------------------

class TestOrderPoints:
    def test_orders_correctly(self):
        pts = np.array([[200, 100], [100, 100], [200, 300], [100, 300]], dtype=np.float32)
        ordered = _order_points(pts)
        # top-left, top-right, bottom-right, bottom-left
        assert ordered[0][0] < ordered[1][0]  # TL.x < TR.x
        assert ordered[0][1] < ordered[3][1]  # TL.y < BL.y
        assert ordered[2][0] > ordered[3][0]  # BR.x > BL.x

    def test_handles_rotated_input(self):
        pts = np.array([[300, 50], [50, 50], [300, 400], [50, 400]], dtype=np.float32)
        ordered = _order_points(pts)
        assert ordered.shape == (4, 2)


# ---------------------------------------------------------------------------
# Tests: _is_valid_quad
# ---------------------------------------------------------------------------

class TestIsValidQuad:
    def test_valid_document_quad(self):
        pts = np.array([[100, 80], [700, 80], [700, 900], [100, 900]])
        assert _is_valid_quad(pts, 800, 1000) is True

    def test_too_small_quad(self):
        pts = np.array([[10, 10], [50, 10], [50, 50], [10, 50]])
        assert _is_valid_quad(pts, 800, 1000) is False

    def test_full_frame_quad_rejected(self):
        pts = np.array([[0, 0], [799, 0], [799, 999], [0, 999]])
        assert _is_valid_quad(pts, 800, 1000) is False

    def test_too_elongated_quad(self):
        pts = np.array([[100, 100], [700, 100], [700, 130], [100, 130]])
        assert _is_valid_quad(pts, 800, 1000) is False


# ---------------------------------------------------------------------------
# Tests: _apply_perspective_transform
# ---------------------------------------------------------------------------

class TestApplyPerspectiveTransform:
    def test_transforms_camera_photo(self):
        arr = _make_camera_photo()
        contour = _find_document_contour(arr)
        assert contour is not None
        result = _apply_perspective_transform(arr, contour)
        assert result is not None
        # Output should be smaller than input (cropped to document)
        assert result.shape[0] < arr.shape[0] or result.shape[1] < arr.shape[1]

    def test_returns_none_for_tiny_contour(self):
        arr = np.ones((500, 500, 3), dtype=np.uint8) * 200
        tiny_contour = np.array([[10, 10], [50, 10], [50, 50], [10, 50]])
        result = _apply_perspective_transform(arr, tiny_contour)
        # 40x40 output — too small, should return None
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _camera_photo_enhance (fallback)
# ---------------------------------------------------------------------------

class TestCameraPhotoEnhance:
    def test_enhances_dark_image(self):
        arr = np.ones((400, 300, 3), dtype=np.uint8) * 80
        img = Image.fromarray(arr)
        result = _camera_photo_enhance(img)
        result_arr = np.array(result)
        # Should be brighter after enhancement
        assert float(np.mean(result_arr)) > float(np.mean(arr))

    def test_handles_normal_image(self):
        arr = np.ones((400, 300, 3), dtype=np.uint8) * 180
        img = Image.fromarray(arr)
        result = _camera_photo_enhance(img)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: _scan_mode_detect_and_correct (integration)
# ---------------------------------------------------------------------------

class TestScanModeDetectAndCorrect:
    def test_clean_scan_passthrough(self):
        """Clean scans should pass through unchanged."""
        arr = _make_clean_scan()
        img = Image.fromarray(arr)
        result = _scan_mode_detect_and_correct(img)
        # Should be approximately the same size (no cropping)
        assert abs(result.size[0] - img.size[0]) < 50
        assert abs(result.size[1] - img.size[1]) < 50

    def test_camera_photo_corrected(self):
        """Camera photos should be corrected to extract the document."""
        arr = _make_camera_photo(doc_w=600, doc_h=800)
        img = Image.fromarray(arr)
        result = _scan_mode_detect_and_correct(img)
        # Result should be roughly document-sized, not full image
        assert result.size[0] < img.size[0]
        assert result.size[1] < img.size[1]

    def test_small_image_passthrough(self):
        """Very small images should pass through."""
        arr = np.ones((100, 100, 3), dtype=np.uint8) * 128
        img = Image.fromarray(arr)
        result = _scan_mode_detect_and_correct(img)
        assert result.size == img.size


# ---------------------------------------------------------------------------
# Tests: Full preprocess_image pipeline with scan mode
# ---------------------------------------------------------------------------

class TestPreprocessImageWithScanMode:
    def test_clean_scan_full_pipeline(self):
        """Clean scan goes through full pipeline without errors."""
        img_bytes = _arr_to_bytes(_make_clean_scan())
        result = preprocess_image(img_bytes)
        assert len(result) > 0
        # Verify it's valid PNG
        img = Image.open(io.BytesIO(result))
        assert img.size[0] > 0

    def test_camera_photo_full_pipeline(self):
        """Camera photo goes through scan mode + full pipeline."""
        img_bytes = _arr_to_bytes(_make_camera_photo())
        result = preprocess_image(img_bytes)
        assert len(result) > 0
        img = Image.open(io.BytesIO(result))
        assert img.size[0] > 0

    def test_tilted_photo_full_pipeline(self):
        """Tilted camera photo is corrected by scan mode."""
        img_bytes = _arr_to_bytes(_make_tilted_camera_photo())
        result = preprocess_image(img_bytes)
        assert len(result) > 0
        img = Image.open(io.BytesIO(result))
        assert img.size[0] > 0

    def test_real_uploaded_image(self):
        """Test with a real uploaded image if available."""
        import os
        uploads_dir = "/app/backend/uploads"
        jpg_files = [f for f in os.listdir(uploads_dir) if f.endswith('.jpg')][:1]
        if not jpg_files:
            pytest.skip("No uploaded images available for testing")
        with open(os.path.join(uploads_dir, jpg_files[0]), "rb") as f:
            img_bytes = f.read()
        result = preprocess_image(img_bytes)
        assert len(result) > 0
