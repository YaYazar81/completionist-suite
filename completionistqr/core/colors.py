"""Füllungen: Vollton oder Farbverlauf. Die Berechnung ist so gewählt, dass
PIL-Raster und SVG-Gradient (userSpaceOnUse) denselben Verlauf ergeben.

Das Verlaufsbild entsteht ohne NumPy: eine kleine Vorlage (senkrechter Keil
bzw. Kreisverlauf) wird mit einer affinen Abbildung auf die Zielgröße gezogen.
Das rechnet Pillow in C, braucht keinen Zwischenspeicher in Bildgröße und
spart der fertigen .exe rund 26 MB.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageColor

# Stufen des Keils zwischen t=0 und t=1. Der Alpha-Blend danach kennt ohnehin
# nur 256 Stufen, feiner muss die Vorlage nicht sein.
_STEPS = 1024
# Reserve ober- und unterhalb, damit Werte ausserhalb 0..1 am Rand anliegen
# statt in die Fuellfarbe zu laufen.
_PAD = 1024
# Die Vorlage von Image.radial_gradient ist auf die Ecke normiert (Wert 255 bei
# 181 px Abstand); wir rechnen auf den Rand (128 px) um.
_RADIAL_EDGE = 128.0
_RADIAL_CORNER = math.hypot(_RADIAL_EDGE, _RADIAL_EDGE)


def rgb(color: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(color)[:3]


@lru_cache(maxsize=1)
def _linear_ramp() -> Image.Image:
    """Senkrechter Keil 0..255 mit festgehaltenen Enden, zwei Pixel breit."""
    rows = [0] * _PAD
    rows += [round(255 * i / (_STEPS - 1)) for i in range(_STEPS)]
    rows += [255] * _PAD
    ramp = Image.new("L", (2, len(rows)))
    ramp.putdata([v for v in rows for _ in range(2)])
    return ramp


@lru_cache(maxsize=1)
def _radial_ramp() -> Image.Image:
    """Kreisverlauf, auf den Randabstand normiert und ausserhalb gekappt."""
    lut = [min(255, round(v * _RADIAL_CORNER / _RADIAL_EDGE)) for v in range(256)]
    return Image.radial_gradient("L").point(lut)


@dataclass
class Solid:
    color: str


@dataclass
class Gradient:
    kind: str  # "linear" | "radial"
    c1: str
    c2: str
    angle: float  # Grad, 0 = links -> rechts, 90 = oben -> unten
    box: tuple[float, float, float, float]  # x, y, w, h in Einheiten

    def linear_points(self) -> tuple[float, float, float, float]:
        x, y, w, h = self.box
        a = math.radians(self.angle)
        dx, dy = math.cos(a), math.sin(a)
        length = abs(w * dx) + abs(h * dy)
        cx, cy = x + w / 2, y + h / 2
        return (cx - dx * length / 2, cy - dy * length / 2,
                cx + dx * length / 2, cy + dy * length / 2)

    def radial_params(self) -> tuple[float, float, float]:
        x, y, w, h = self.box
        return x + w / 2, y + h / 2, math.hypot(w, h) / 2

    def _mask(self, width: int, height: int, scale: float) -> Image.Image:
        """Graustufenbild: 0 = Farbe 1, 255 = Farbe 2.

        Pixel (x, y) liegt bei ((x + 0.5) / scale, (y + 0.5) / scale) in
        Einheiten -- genau wie in der SVG-Fassung.
        """
        if self.kind == "radial":
            cx, cy, r = self.radial_params()
            k = _RADIAL_EDGE / max(r * scale, 1e-9)
            # Mittelpunkt in Pixeln, Vorlage ist um (128, 128) zentriert.
            coeffs = (k, 0.0, _RADIAL_EDGE - k * (cx * scale - 0.5),
                      0.0, k, _RADIAL_EDGE - k * (cy * scale - 0.5))
            source, fill = _radial_ramp(), 255
        else:
            x1, y1, x2, y2 = self.linear_points()
            vx, vy = x2 - x1, y2 - y1
            den = max(vx * vx + vy * vy, 1e-9)
            # t = A*x + B*y + C, danach auf die Zeilen des Keils umgerechnet.
            n = _STEPS - 1
            a = n * vx / (scale * den)
            b = n * vy / (scale * den)
            c = _PAD + n * ((0.5 / scale - x1) * vx + (0.5 / scale - y1) * vy) / den
            coeffs = (0.0, 0.0, 0.5, a, b, c)
            source, fill = _linear_ramp(), 0

        return source.transform((width, height), Image.Transform.AFFINE, coeffs,
                                resample=Image.Resampling.BILINEAR, fillcolor=fill)

    def image(self, width: int, height: int, scale: float) -> Image.Image:
        """RGB-Bild der Größe width x height (Pixel) bei `scale` Pixel pro Einheit."""
        size = (width, height)
        return Image.composite(Image.new("RGB", size, rgb(self.c2)),
                               Image.new("RGB", size, rgb(self.c1)),
                               self._mask(width, height, scale))
