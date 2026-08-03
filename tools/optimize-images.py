#!/usr/bin/env python3
"""Generate the web-sized WebP derivatives that index.html actually loads.

Full-resolution captures live in assets/images/ and are never modified. This writes
downscaled WebP copies to assets/images/web/, which is what the page references.

Run after adding or replacing a screenshot:

    python3 tools/optimize-images.py

Requires Pillow (pip install pillow).
"""
import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "images")
OUT = os.path.join(SRC, "web")

# Large figures in the "Selected work" entries render up to ~780px wide (~1560 @2x).
# Everything else is a grid thumbnail at ~230px wide (~460 @2x).
FIGURE_PREFIXES = ("inrange-", "curlzone-", "birds-")
FIGURE_WIDTH, FIGURE_QUALITY = 1600, 82
THUMB_WIDTH, THUMB_QUALITY = 640, 80

SOURCE_EXTS = {".png", ".jpg", ".jpeg"}


def sources():
    for name in sorted(os.listdir(SRC)):
        path = os.path.join(SRC, name)
        stem, ext = os.path.splitext(name)
        if not os.path.isfile(path) or ext.lower() not in SOURCE_EXTS:
            continue
        # Untitled captures are kept as spare frames but not published.
        if name.startswith("Screenshot "):
            continue
        yield name, stem, path


def main():
    os.makedirs(OUT, exist_ok=True)
    total_in = total_out = 0

    for name, stem, path in sources():
        is_figure = stem.startswith(FIGURE_PREFIXES)
        width = FIGURE_WIDTH if is_figure else THUMB_WIDTH
        quality = FIGURE_QUALITY if is_figure else THUMB_QUALITY

        dst = os.path.join(OUT, stem + ".webp")
        im = Image.open(path)
        # Logos are transparent PNGs that sit directly on the dark plate — flattening
        # them to RGB would stamp a black box around the mark. WebP keeps the alpha.
        transparent = im.mode in ("RGBA", "LA", "P") and "transparency" in im.info \
            or (im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255)
        im = im.convert("RGBA" if transparent else "RGB")
        w, h = im.size
        if w > width:                      # never upscale
            im = im.resize((width, round(h * width / w)), Image.LANCZOS)
        im.save(dst, "WEBP", quality=quality, method=6)

        a, b = os.path.getsize(path), os.path.getsize(dst)
        total_in += a
        total_out += b
        print(f"{name:28s} {w}x{h} -> {im.size[0]}x{im.size[1]}  "
              f"{a / 1e6:6.2f} MB -> {b / 1e3:7.1f} KB")

    if not total_in:
        print("No source images found in", SRC)
        return 1
    print(f"\nTOTAL  {total_in / 1e6:.1f} MB -> {total_out / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
