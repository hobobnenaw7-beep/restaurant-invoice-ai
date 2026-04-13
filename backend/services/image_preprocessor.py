"""
Invoice Image Preprocessor
Normalizes invoice photos before GPT-5.2 vision extraction:
- Auto-rotate based on EXIF orientation
- Resize to optimal dimensions for GPT vision (max 2048px on long side)
- Enhance contrast and sharpness for text readability
- Convert to RGB if needed
- Compress to reduce payload size
"""
import io
import logging
from PIL import Image, ImageEnhance, ImageFilter, ExifTags

logger = logging.getLogger("restaurant_ai")

# GPT vision works best at 2048px max dimension — larger images get downscaled
# by the API anyway, wasting tokens on metadata. Smaller = faster + more consistent.
MAX_DIMENSION = 2048
JPEG_QUALITY = 85
CONTRAST_FACTOR = 1.15   # Slight contrast boost for text readability
SHARPNESS_FACTOR = 1.3   # Sharpen to counteract phone camera softness


def preprocess_invoice_image(image_bytes: bytes, filename: str = "") -> bytes:
    """
    Preprocess an invoice photo for GPT vision extraction.
    Returns optimized JPEG bytes.
    """
    img = Image.open(io.BytesIO(image_bytes))
    original_size = len(image_bytes)
    original_dims = img.size

    # Step 1: Auto-rotate from EXIF
    img = _fix_orientation(img)

    # Step 2: Convert to RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Step 3: Resize — keep aspect ratio, max 2048px on long side
    img = _resize_to_max(img, MAX_DIMENSION)

    # Step 4: Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(CONTRAST_FACTOR)

    # Step 5: Sharpen
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(SHARPNESS_FACTOR)

    # Step 6: Compress to JPEG
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    result = output.getvalue()

    new_size = len(result)
    reduction = (1 - new_size / original_size) * 100 if original_size > 0 else 0

    logger.info(
        f"Image preprocessed: {filename} "
        f"{original_dims[0]}x{original_dims[1]} -> {img.size[0]}x{img.size[1]}, "
        f"{original_size/1024:.0f}KB -> {new_size/1024:.0f}KB ({reduction:.0f}% reduction)"
    )

    return result


def _fix_orientation(img: Image.Image) -> Image.Image:
    """Auto-rotate based on EXIF orientation tag."""
    try:
        exif = img._getexif()
        if exif is None:
            return img

        orientation_key = None
        for tag, name in ExifTags.TAGS.items():
            if name == "Orientation":
                orientation_key = tag
                break

        if orientation_key is None or orientation_key not in exif:
            return img

        orientation = exif[orientation_key]
        if orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
    except (AttributeError, KeyError):
        pass

    return img


def _resize_to_max(img: Image.Image, max_dim: int) -> Image.Image:
    """Resize keeping aspect ratio so long side <= max_dim."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img

    if w > h:
        new_w = max_dim
        new_h = int(h * (max_dim / w))
    else:
        new_h = max_dim
        new_w = int(w * (max_dim / h))

    return img.resize((new_w, new_h), Image.LANCZOS)
