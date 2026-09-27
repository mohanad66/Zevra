"""Generate Android launcher icons from public/logo.png.

Produces three sets per density, matching the Capacitor Android template:

  ic_launcher.png            legacy square launcher icon (48dp)
  ic_launcher_round.png      legacy round launcher icon (48dp)
  ic_launcher_foreground.png adaptive-icon foreground (108dp canvas)

Adaptive icons are 108x108dp but launchers may crop up to 18dp off each edge, so
the artwork is inset to the centre 72dp. The inset copy still carries the logo's
own dark background, and values/ic_launcher_background.xml is recoloured to match,
so the two layers blend with no visible seam and no alpha thresholding.
"""
import os

from PIL import Image, ImageDraw

RES = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "android", "app", "src", "main", "res")
)
LOGO = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "logo.png")
)

# density -> legacy icon px, adaptive canvas px, inset px (canvas * 2/3)
DENSITIES = {
    "mdpi": (48, 108, 72),
    "hdpi": (72, 162, 108),
    "xhdpi": (96, 216, 144),
    "xxhdpi": (144, 324, 216),
    "xxxhdpi": (192, 432, 288),
}

src = Image.open(LOGO).convert("RGB")
print("logo:", src.size)


def border_color(im):
    """Average the outer ring so the adaptive background matches the artwork."""
    w, h = im.size
    ring = []
    step = max(1, w // 64)
    for x in range(0, w, step):
        ring.append(im.getpixel((x, 0)))
        ring.append(im.getpixel((x, h - 1)))
    for y in range(0, h, step):
        ring.append(im.getpixel((0, y)))
        ring.append(im.getpixel((w - 1, y)))
    r = sum(p[0] for p in ring) / len(ring)
    g = sum(p[1] for p in ring) / len(ring)
    b = sum(p[2] for p in ring) / len(ring)
    return (round(r), round(g), round(b))


BG = border_color(src)
print("sampled background: rgb%s -> #%02X%02X%02X" % (BG, *BG))


def write(im, *parts):
    path = os.path.join(RES, *parts)
    im.save(path, "PNG", optimize=True)
    print("  %s (%dx%d)" % (os.path.join(*parts), im.size[0], im.size[1]))


for density, (legacy, canvas, inset) in DENSITIES.items():
    folder = "mipmap-" + density
    print(density + ":")

    write(src.resize((legacy, legacy), Image.LANCZOS), folder, "ic_launcher.png")

    round_im = src.resize((legacy, legacy), Image.LANCZOS)
    mask = Image.new("L", (legacy * 4, legacy * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, legacy * 4 - 1, legacy * 4 - 1), fill=255)
    round_im.putalpha(mask.resize((legacy, legacy), Image.LANCZOS))
    write(round_im, folder, "ic_launcher_round.png")

    fg = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    art = src.resize((inset, inset), Image.LANCZOS)
    off = (canvas - inset) // 2
    fg.paste(art, (off, off))
    write(fg, folder, "ic_launcher_foreground.png")

# Recolour the adaptive-icon background layer to match the artwork.
colors = os.path.join(RES, "values", "ic_launcher_background.xml")
with open(colors, "w", encoding="utf-8") as fh:
    fh.write(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        '    <color name="ic_launcher_background">#%02X%02X%02X</color>\n' % BG
        + "</resources>\n"
    )
print("wrote", colors)
