"""Broader Sysco scan - resize full image to small size, OCR entire thing."""
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

print(f"Broad-scanning {len(files)} images...\n")

sysco_files = []

for idx, fname in enumerate(files):
    fpath = os.path.join(UPLOADS_DIR, fname)
    try:
        img = Image.open(fpath)
        w, h = img.size
        fsize = os.path.getsize(fpath) // 1024

        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize full image to max 800px on longest side
        max_dim = max(w, h)
        if max_dim > 800:
            ratio = 800 / max_dim
            img_small = img.resize((int(w * ratio), int(h * ratio)))
        else:
            img_small = img

        text = pytesseract.image_to_string(img_small, config="--psm 6").upper()

        if "SYSCO" in text:
            # Count lines with numbers as rough line-item density
            lines = [l for l in text.split("\n") if any(c.isdigit() for c in l)]
            sysco_files.append({
                "file": fname,
                "width": w,
                "height": h,
                "size_kb": fsize,
                "aspect": round(w/h, 2) if h > 0 else 0,
                "num_lines": len(lines),
            })
            print(f"  SYSCO #{len(sysco_files)}: {fname} | {w}x{h} | {fsize}KB | ~{len(lines)} data lines")

    except Exception as e:
        pass

    if (idx+1) % 50 == 0:
        print(f"  ... scanned {idx+1}/{len(files)} ({len(sysco_files)} Sysco found)")

print(f"\n{'='*60}")
print(f"Total Sysco invoices found: {len(sysco_files)}")
for sf in sysco_files:
    print(f"  {sf['file']} | {sf['width']}x{sf['height']} | {sf['size_kb']}KB | ~{sf['num_lines']} lines")
