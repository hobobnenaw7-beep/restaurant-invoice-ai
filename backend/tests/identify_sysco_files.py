"""Quick scan to identify Sysco invoices and gather metadata for diverse selection."""
import io
import os
import sys

sys.path.insert(0, "/app/backend")

from PIL import Image
from services.sysco_pipeline import _extract_words

UPLOADS_DIR = "/app/backend/uploads"

files = sorted([
    f for f in os.listdir(UPLOADS_DIR)
    if not f.startswith("scan_") and f.endswith((".jpg", ".png"))
])

print(f"Scanning {len(files)} images for Sysco content...\n")

sysco_files = []

for idx, fname in enumerate(files):
    fpath = os.path.join(UPLOADS_DIR, fname)
    try:
        img = Image.open(fpath)
        w, h = img.size
        fsize = os.path.getsize(fpath) // 1024  # KB

        if img.mode != "RGB":
            img = img.convert("RGB")

        words = _extract_words(img)
        text_upper = " ".join(wd["text"].upper() for wd in words[:150])

        if "SYSCO" in text_upper:
            # Count numeric words as proxy for line item density
            num_words = sum(1 for wd in words if any(c.isdigit() for c in wd["text"]))
            sysco_files.append({
                "file": fname,
                "width": w,
                "height": h,
                "size_kb": fsize,
                "total_words": len(words),
                "numeric_words": num_words,
            })
            print(f"  SYSCO #{len(sysco_files)}: {fname} | {w}x{h} | {fsize}KB | {len(words)} words | {num_words} nums")
    except Exception as e:
        pass

    if idx % 50 == 0 and idx > 0:
        print(f"  ... scanned {idx}/{len(files)}")

print(f"\n{'='*60}")
print(f"Total Sysco invoices found: {len(sysco_files)}")
print(f"\nDimension spread:")
for sf in sysco_files:
    print(f"  {sf['file'][:12]}... {sf['width']}x{sf['height']} {sf['size_kb']}KB words={sf['total_words']} nums={sf['numeric_words']}")
