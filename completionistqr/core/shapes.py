"""Geometrische Primitive, die sowohl mit Pillow als auch als SVG-Pfad gezeichnet werden.

Alle Koordinaten sind in "Einheiten" (1 Einheit = 1 QR-Modul). Die PIL-Methode
bekommt den Skalierungsfaktor in Pixel pro Einheit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import ImageDraw


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


@dataclass
class RRect:
    x: float
    y: float
    w: float
    h: float
    r: float = 0.0
    corners: tuple[bool, bool, bool, bool] = (True, True, True, True)  # tl, tr, br, bl

    def _radius(self) -> float:
        return max(0.0, min(self.r, self.w / 2, self.h / 2))

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        x0, y0 = self.x * s, self.y * s
        # Bei sehr kleinen Ausgaben kann eine Form schmaler als ein Pixel werden
        x1, y1 = max(x0, (self.x + self.w) * s - 1), max(y0, (self.y + self.h) * s - 1)
        r = min(self._radius() * s, (x1 - x0) / 2, (y1 - y0) / 2)
        if r < 1 or not any(self.corners):
            d.rectangle([x0, y0, x1, y1], fill=fill)
            return
        # Eigene Umsetzung statt ImageDraw.rounded_rectangle: dessen Teil-Ecken-Logik
        # bricht bei Radius = halbe Höhe ab. Kreuz aus zwei Rechtecken + je Ecke Kreis/Quadrat.
        d.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
        d.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
        for rounded, (cx, cy) in zip(self.corners, ((x0, y0), (x1 - 2 * r, y0),
                                                     (x1 - 2 * r, y1 - 2 * r), (x0, y1 - 2 * r))):
            if rounded:
                d.ellipse([cx, cy, cx + 2 * r, cy + 2 * r], fill=fill)
            else:
                sx = x0 if cx == x0 else x1 - r
                sy = y0 if cy == y0 else y1 - r
                d.rectangle([sx, sy, sx + r, sy + r], fill=fill)

    def svg(self) -> str:
        r = self._radius()
        tl, tr, br, bl = (r if c else 0.0 for c in self.corners)
        x, y, w, h = self.x, self.y, self.w, self.h
        p = [f"M{_f(x + tl)} {_f(y)}", f"H{_f(x + w - tr)}"]
        if tr:
            p.append(f"A{_f(tr)} {_f(tr)} 0 0 1 {_f(x + w)} {_f(y + tr)}")
        p.append(f"V{_f(y + h - br)}")
        if br:
            p.append(f"A{_f(br)} {_f(br)} 0 0 1 {_f(x + w - br)} {_f(y + h)}")
        p.append(f"H{_f(x + bl)}")
        if bl:
            p.append(f"A{_f(bl)} {_f(bl)} 0 0 1 {_f(x)} {_f(y + h - bl)}")
        p.append(f"V{_f(y + tl)}")
        if tl:
            p.append(f"A{_f(tl)} {_f(tl)} 0 0 1 {_f(x + tl)} {_f(y)}")
        return "".join(p) + "Z"


@dataclass
class Circle:
    cx: float
    cy: float
    r: float

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        x0, y0 = (self.cx - self.r) * s, (self.cy - self.r) * s
        d.ellipse([x0, y0, max(x0, (self.cx + self.r) * s - 1),
                   max(y0, (self.cy + self.r) * s - 1)], fill=fill)

    def svg(self) -> str:
        r = self.r
        return (f"M{_f(self.cx - r)} {_f(self.cy)}"
                f"a{_f(r)} {_f(r)} 0 1 0 {_f(2 * r)} 0"
                f"a{_f(r)} {_f(r)} 0 1 0 {_f(-2 * r)} 0Z")


@dataclass
class Poly:
    points: list[tuple[float, float]]

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        d.polygon([(x * s, y * s) for x, y in self.points], fill=fill)

    def svg(self) -> str:
        (x0, y0), *rest = self.points
        return f"M{_f(x0)} {_f(y0)}" + "".join(f"L{_f(x)} {_f(y)}" for x, y in rest) + "Z"


@dataclass
class Compound:
    """Eine Form mit Löchern (z. B. der Augen-Ring oder ein Rahmen mit Aussparung).

    Löcher müssen vollständig innerhalb der äußeren Form liegen und dürfen sich
    nicht überlappen, damit die SVG-Regel evenodd dasselbe Ergebnis liefert.
    """
    outer: object
    holes: list = field(default_factory=list)

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        self.outer.draw(d, s, fill)
        for h in self.holes:
            h.draw(d, s, 0)

    def svg(self) -> str:
        return self.outer.svg() + "".join(h.svg() for h in self.holes)


def half_disc(cx: float, cy: float, r: float, facing: str, steps: int = 24) -> Poly:
    """Halbkreis, dessen gerade Kante auf x=cx liegt; facing 'right' oder 'left'."""
    sign = 1 if facing == "right" else -1
    pts = []
    for i in range(steps + 1):
        a = -math.pi / 2 + math.pi * i / steps
        pts.append((cx + sign * r * math.cos(a), cy + r * math.sin(a)))
    return Poly(pts)
