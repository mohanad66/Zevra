"""Regenerate the web favicon + PWA icons from public/logo.png.

The mark in logo.png is already centred on an opaque near-black square, so a
straight LANCZOS downscale is correct; cropping would clip the artwork.
"""
import base64
import io
import os

from PIL import Image

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public")
PUB = os.path.normpath(PUB)

src = Image.open(os.path.join(PUB, "logo.png")).convert("RGB")
print("source", src.size)


def write_png(rel_path, size):
    im = src.resize((size, size), Image.LANCZOS)
    path = os.path.join(PUB, rel_path)
    im.save(path, "PNG", optimize=True)
    print("%s: %dx%d (%.1f KB)" % (rel_path, size, size, os.path.getsize(path) / 1024))


write_png(os.path.join("icons", "icon-192.png"), 192)
write_png(os.path.join("icons", "icon-512.png"), 512)
write_png("favicon.png", 48)

# favicon.svg used to be a hand-drawn blue/purple "Z" that no longer matched the
# brand. logo.png is a raster, so embed a small PNG rather than ship a stale
# vector that diverges from the PNG icons.
svg_im = src.resize((64, 64), Image.LANCZOS)
buf = io.BytesIO()
svg_im.save(buf, "PNG", optimize=True)
b64 = base64.b64encode(buf.getvalue()).decode("ascii")
svg = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n'
    '  <image width="64" height="64" href="data:image/png;base64,' + b64 + '"/>\n'
    "</svg>\n"
)
svg_path = os.path.join(PUB, "favicon.svg")
with open(svg_path, "w", encoding="utf-8") as fh:
    fh.write(svg)
print("favicon.svg: embedded 64x64 png (%.1f KB)" % (os.path.getsize(svg_path) / 1024))
