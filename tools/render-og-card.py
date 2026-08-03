#!/usr/bin/env python3
"""Rasterise the Open Graph card SVG to the PNG that index.html advertises.

The social scrapers (Facebook, LinkedIn, Slack, X) do not render SVG, so og:image has to
point at a bitmap. This renders assets/images/og_card_service_manual_concept.svg to
assets/images/og-card.png at the 1200x630 the scrapers expect.

Run after editing the card:

    python3 tools/render-og-card.py

Requires Pillow (pip install pillow) and, on first run, network access to fetch the two
Google Fonts the site uses. Fonts are cached in .cache/fonts/.

This is a mini renderer for the small SVG subset the card uses — rect, line, text and a
single embedded <image>. It reads geometry and styling out of the file rather than
hardcoding the layout, so ordinary edits to the card (moving things, retyping the spec
row, recolouring) carry through. It does NOT understand transforms, paths, gradients or
opacity; if the card ever grows one of those, this script needs to grow with it.
"""
import base64
import io
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "assets", "images", "og_card_service_manual_concept.svg")
OUT = os.path.join(ROOT, "assets", "images", "og-card.png")
FONT_DIR = os.path.join(ROOT, ".cache", "fonts")

OG_WIDTH, OG_HEIGHT = 1200, 630
SUPERSAMPLE = 2  # draw at 2x and downsample; ImageDraw does not antialias shapes

# Google Fonts only serves TTF to clients old enough not to understand woff2.
FONT_UA = ("Mozilla/5.0 (Linux; U; Android 4.0.3; en-us; Galaxy Nexus Build/IML74K) "
           "AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30")
FONTS = {
    "mono-400": "IBM+Plex+Mono:400",
    "sans-400": "Zen+Kaku+Gothic+New:400",
    "sans-500": "Zen+Kaku+Gothic+New:500",
    "sans-700": "Zen+Kaku+Gothic+New:700",
}
SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def font_path(key):
    """Return a local TTF for `key`, downloading it from Google Fonts once."""
    path = os.path.join(FONT_DIR, key + ".ttf")
    if os.path.exists(path):
        return path
    os.makedirs(FONT_DIR, exist_ok=True)
    css_url = "https://fonts.googleapis.com/css?family=" + FONTS[key]
    req = urllib.request.Request(css_url, headers={"User-Agent": FONT_UA})
    css = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    m = re.search(r"https://[^)']+\.ttf", css)
    if not m:
        sys.exit("could not resolve a TTF for %s — Google Fonts changed its response" % key)
    data = urllib.request.urlopen(m.group(0), timeout=60).read()
    with open(path, "wb") as fh:
        fh.write(data)
    print("  fetched %s" % os.path.basename(path))
    return path


_font_cache = {}


def load_font(family, weight, size_px):
    """Map an SVG font-family/weight onto one of the site's two typefaces."""
    if "mono" in (family or "").lower():
        key = "mono-400"
    else:
        w = int(weight or 400)
        key = "sans-700" if w >= 700 else "sans-500" if w >= 500 else "sans-400"
    ck = (key, size_px)
    if ck not in _font_cache:
        _font_cache[ck] = ImageFont.truetype(font_path(key), size_px)
    return _font_cache[ck]


def parse_style(el):
    """Inline style wins over presentation attributes, as it does in a browser."""
    props = dict(el.attrib)
    for decl in (el.get("style") or "").split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            props[k.strip()] = v.strip()
    return props


def colour(value, default=None):
    if not value or value in ("none", "transparent"):
        return default
    v = value.strip()
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", v)
    if m:
        return tuple(int(g) for g in m.groups())
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return default


def num(value, default=0.0):
    try:
        return float(str(value).strip().replace("px", ""))
    except (TypeError, ValueError):
        return default


def draw_text(draw, el, props, s):
    text = "".join(el.itertext())
    if not text.strip():
        return
    size = max(1, int(round(num(props.get("font-size"), 12) * s)))
    font = load_font(props.get("font-family"), num(props.get("font-weight"), 400), size)
    fill = colour(props.get("fill"), (0, 0, 0))
    spacing = num(props.get("letter-spacing")) * s
    x, y = num(props.get("x")) * s, num(props.get("y")) * s

    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)
    anchor = props.get("text-anchor", "start")
    if anchor == "end":
        x -= total
    elif anchor == "middle":
        x -= total / 2

    if not spacing:
        draw.text((x, y), text, font=font, fill=fill, anchor="ls")
        return
    for ch, w in zip(text, widths):          # Pillow has no letter-spacing of its own
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += w + spacing


def draw_rect(draw, props, s):
    x, y = num(props.get("x")) * s, num(props.get("y")) * s
    w, h = num(props.get("width")) * s, num(props.get("height")) * s
    box = [x, y, x + w, y + h]
    fill = colour(props.get("fill"))
    stroke = colour(props.get("stroke"))
    sw = max(1, int(round(num(props.get("stroke-width"), 1) * s))) if stroke else 0
    if fill or stroke:
        draw.rectangle(box, fill=fill, outline=stroke, width=sw)


def draw_line(draw, props, s):
    stroke = colour(props.get("stroke"))
    if not stroke:
        return
    sw = max(1, int(round(num(props.get("stroke-width"), 1) * s)))
    draw.line([num(props.get("x1")) * s, num(props.get("y1")) * s,
               num(props.get("x2")) * s, num(props.get("y2")) * s], fill=stroke, width=sw)


def draw_image(canvas, el, props, s):
    href = el.get(XLINK_HREF) or el.get("href") or ""
    if not href.startswith("data:"):
        sys.exit("the <image> must be an embedded data URI — external refs do not load "
                 "when an SVG is used as an image")
    payload = base64.b64decode(href.split(",", 1)[1])
    im = Image.open(io.BytesIO(payload)).convert("RGB")
    w = int(round(num(props.get("width")) * s))
    h = int(round(num(props.get("height")) * s))
    # every plate in this design is a "slice" fit: cover the box, crop the overflow
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(round(im.width * scale))), max(1, int(round(im.height * scale)))),
                   Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 2
    im = im.crop((left, top, left + w, top + h))
    canvas.paste(im, (int(round(num(props.get("x")) * s)), int(round(num(props.get("y")) * s))))


def main():
    tree = ET.parse(SVG)
    root = tree.getroot()

    # The card content is the full-bleed background rect. The viewBox on this file is a
    # little larger than the artwork, and using it would letterbox the result.
    bg = root.find("%srect" % SVG_NS)
    box_w, box_h = num(bg.get("width"), 680), num(bg.get("height"), 357)
    if abs(box_w / box_h - OG_WIDTH / OG_HEIGHT) > 0.02:
        print("  note: card is %g:%g, OG target is 1200x630 — output will be stretched"
              % (box_w, box_h))

    s = (OG_WIDTH / box_w) * SUPERSAMPLE
    canvas = Image.new("RGB", (OG_WIDTH * SUPERSAMPLE, OG_HEIGHT * SUPERSAMPLE), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    counts = {}
    for el in root.iter():
        tag = el.tag.replace(SVG_NS, "")
        if tag in ("svg", "title", "desc", "defs", "metadata"):
            continue
        props = parse_style(el)
        if tag == "rect":
            draw_rect(draw, props, s)
        elif tag == "line":
            draw_line(draw, props, s)
        elif tag == "text":
            draw_text(draw, el, props, s)
        elif tag == "image":
            draw_image(canvas, el, props, s)
        else:
            print("  skipped unsupported <%s>" % tag)
            continue
        counts[tag] = counts.get(tag, 0) + 1

    canvas = canvas.resize((OG_WIDTH, OG_HEIGHT), Image.LANCZOS)
    canvas.save(OUT, "PNG", optimize=True)
    print("wrote %s (%dx%d, %.0f KB) from %s"
          % (os.path.relpath(OUT, ROOT), OG_WIDTH, OG_HEIGHT,
             os.path.getsize(OUT) / 1024, ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items()))))


if __name__ == "__main__":
    main()
