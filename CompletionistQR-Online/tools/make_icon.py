r"""Erzeugt das Programmsymbol von CompletionistQR Online im Stil der Suite.

    python tools\make_icon.py     # assets\icon_source.png (1024 px) und assets\icon.ico

Wie die Symbole von CompletionistQR/-PDF/-MD: Scheibe mit Verlauf von oben links
(hell) nach unten rechts (dunkel), heller Rand, weisser "C"-Bogen, der nach unten
ausblendet, fettes Kuerzel in Montserrat. Eigene Farbe Violett, unter dem Kuerzel
ein kleines Balkendiagramm fuer die Scan-Statistik.

Gezeichnet wird vierfach ueberabgetastet und danach verkleinert (glatte Kanten).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
FONT = ROOT.parent / "completionistqr" / "assets" / "fonts" / "montserrat" / "Montserrat[wght].ttf"
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128),
         (256, 256)]

N = 1024          # Endgroesse
SS = 4            # Ueberabtastung
LIGHT = (155, 110, 250)   # oben links
DARK = (67, 26, 150)      # unten rechts


def _px(v: float) -> int:
    return round(v * SS)


def disc_fill(size: int) -> Image.Image:
    """Diagonaler Verlauf plus weicher Lichtfleck oben links."""
    # (x + y) / 2: Mittel aus senkrechtem und waagerechtem Keil -> Diagonale ohne Kanten
    down = Image.linear_gradient("L").resize((size, size), Image.Resampling.BICUBIC)
    # ROTATE_90 (gegen den Uhrzeigersinn) legt den Keil quer: links 0, rechts 255
    ramp = ImageChops.add(down, down.transpose(Image.Transpose.ROTATE_90), scale=2)
    fill = Image.composite(Image.new("RGB", (size, size), DARK),
                           Image.new("RGB", (size, size), LIGHT), ramp)
    glow = Image.new("L", (size, size), 0)
    g = ImageDraw.Draw(glow)
    r = size * 0.42
    g.ellipse([size * 0.3 - r, size * 0.28 - r, size * 0.3 + r, size * 0.28 + r], fill=45)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.12))
    return Image.composite(Image.new("RGB", (size, size), (255, 255, 255)), fill, glow)


def arc_layer(size: int) -> Image.Image:
    """Weisser C-Bogen von 45° bis 315° (offen nach rechts), unten schwaecher."""
    c, r, w = size / 2, _px(400), _px(68)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    start, end = 47, 313
    d.arc([c - r - w / 2, c - r - w / 2, c + r + w / 2, c + r + w / 2], start, end, fill=255,
          width=w)
    for deg in (start, end):  # runde Enden
        a = math.radians(deg)
        x, y = c + r * math.cos(a), c + r * math.sin(a)
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    # unten (y gross) auf rund 75 % ausblenden, oben voll
    fade = Image.linear_gradient("L").point(lambda v: 255 - round(v * 0.25)).resize((size, size))
    return ImageChops.multiply(mask, fade)


def text_layer(size: int) -> Image.Image:
    font = ImageFont.truetype(str(FONT), _px(300))
    try:
        font.set_variation_by_axes([800])  # ExtraBold wie die anderen Symbole
    except OSError:
        pass
    layer = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(layer)
    d.text((_px(517), _px(560)), "QR", font=font, fill=255, anchor="ms")
    # Balkendiagramm: drei steigende Balken mit runden Kappen
    bw, gap, base = _px(46), _px(24), _px(800)
    x0 = _px(517) - (3 * bw + 2 * gap) / 2
    for i, h in enumerate((70, 115, 165)):
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, base - _px(h), x + bw, base], radius=bw / 2.6, fill=255)
    return layer


def build() -> Image.Image:
    size = N * SS
    c, R = size / 2, _px(496)
    disc = Image.new("L", (size, size), 0)
    ImageDraw.Draw(disc).ellipse([c - R, c - R, c + R, c + R], fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(disc_fill(size), (0, 0), disc)
    # heller Rand innen an der Scheibe
    rim = Image.new("L", (size, size), 0)
    ImageDraw.Draw(rim).ellipse([c - R, c - R, c + R, c + R], outline=80, width=_px(9))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    img = Image.composite(white, img, ImageChops.multiply(rim, disc)).convert("RGBA")
    for layer in (arc_layer(size), text_layer(size)):
        img = Image.composite(white, img, layer)
    img.putalpha(disc)
    return img.resize((N, N), Image.Resampling.LANCZOS)


def main() -> int:
    if not FONT.is_file():
        print(f"Schrift fehlt: {FONT}", file=sys.stderr)
        return 1
    ASSETS.mkdir(exist_ok=True)
    img = build()
    img.save(ASSETS / "icon_source.png")
    img.save(ASSETS / "icon.ico", format="ICO", sizes=SIZES)
    print(f"{ASSETS / 'icon_source.png'}\n{ASSETS / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
