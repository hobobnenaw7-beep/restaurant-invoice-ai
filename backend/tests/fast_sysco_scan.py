"""Fast Sysco identification - crops header region, resizes, quick OCR."""
import os
import sys
sys.path.insert(0, "/app/backend")

import pytesseract
from PIL import Image

UPLOADS_DIR = "/app/backend/uploads"

files = sorted([
    f for f in os.listdir(UPLOADS_DIR)
    if not f.startswith("scan_") and f.endswith((".jpg", ".png"))
])

print(f"Fast-scanning {len(files)} images...\n")

sysco_files = []

for idx, fname in enumerate(files):
    fpath = os.path.join(UPLOADS_DIR, fname)
    try:
        img = Image.open(fpath)
        w, h = img.size
        fsize = os.path.getsize(fpath) // 1024

        if img.mode != "RGB":
            img = img.convert("RGB")

        # Crop top 25% of image (header where SYSCO logo/name appears)
        header = img.crop((0, 0, w, h // 4))
        # Resize to max 600px wide for speed
        if header.width > 600:
            ratio = 600 / header.width
            header = header.resize((600, int(header.height * ratio)))

        text = pytesseract.image_to_string(header, config="--psm 6").upper()

        if "SYSCO" in text:
            sysco_files.append({
                "file": fname,
                "width": w,
                "height": h,
                "size_kb": fsize,
                "aspect": round(w/h, 2) if h > 0 else 0,
            })
            print(f"  SYSCO #{len(sysco_files)}: {fname} | {w}x{h} | {fsize}KB | AR={round(w/h,2)}")

    except Exception as e:
        pass

    if (idx+1) % 50 == 0:
        print(f"  ... scanned {idx+1}/{len(files)} ({len(sysco_files)} Sysco found)")

print(f"\n{'='*60}")
print(f"Total Sysco invoices found: {len(sysco_files)}")

# Sort by diversity (different sizes, aspect ratios)
print(f"\nAll Sysco files:")
for sf in sysco_files:
    print(f"  {sf['file']} | {sf['width']}x{sf['height']} | {sf['size_kb']}KB")
