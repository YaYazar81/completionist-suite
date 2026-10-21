"""Geometrische Primitive, die mit Pillow, als SVG-Pfad und als PDF-Pfad gezeichnet werden.

Alle Koordinaten sind in "Einheiten" (1 Einheit = 1 QR-Modul). Die PIL-Methode
bekommt den Skalierungsfaktor in Pixel pro Einheit.

SVG und PDF entstehen aus derselben Kontur (``_outline``). Sie läuft bei y nach
unten im Uhrzeigersinn, Löcher (``hole=True``) gegen ihn. Gefüllt wird nach der
Regel nonzero: sich überlappende Formen verschmelzen wie in Pillow, statt sich
wie bei evenodd gegenseitig auszustanzen (z. B. die Punkt-Pupillen, die sich
absichtlich berühren).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import ImageDraw

# Kreisbogen als kubische Bézierkurve: Abstand der Kontrollpunkte je Viertelkreis
KAPPA = 0.5522847498307936


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _p(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def contour(start: tuple[float, float], segs: list, reverse: bool = False,
            svg: bool = False) -> str:
    """Geschlossene Kontur als SVG-Pfaddaten oder PDF-Pfadoperatoren.

    ``segs``: ("L", Punkt) oder ("C", Kontrolle1, Kontrolle2, Punkt).
    ``reverse`` kehrt die Laufrichtung um (für Löcher).
    """
    if reverse:
        pts = [start] + [s[-1] for s in segs]
        rev = []
        for i in range(len(segs) - 1, -1, -1):
            s = segs[i]
            rev.append(("L", pts[i]) if s[0] == "L" else ("C", s[2], s[1], pts[i]))
        start, segs = pts[-1], rev
    if svg:
        out = [f"M{_f(start[0])} {_f(start[1])}"]
        for s in segs:
            out.append(("L" if s[0] == "L" else "C") + " ".join(f"{_f(a)} {_f(b)}" for a, b in s[1:]))
        return "".join(out) + "Z"
    out = [f"{_p(start[0])} {_p(start[1])} m"]
    for s in segs:
        out.append(" ".join(f"{_p(a)} {_p(b)}" for a, b in s[1:]) + (" l" if s[0] == "L" else " c"))
    return " ".join(out) + " h\n"


class _Outlined:
    """svg() und pdf() aus ``_outline() -> (Start, Segmente, laeuft_gegen_Uhrzeigersinn)``."""

    def svg(self, hole: bool = False) -> str:
        start, segs, ccw = self._outline()
        return contour(start, segs, hole != ccw, svg=True)

    def pdf(self, hole: bool = False) -> str:
        start, segs, ccw = self._outline()
        return contour(start, segs, hole != ccw)


@dataclass
class RRect(_Outlined):
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
        for i, (rounded, (cx, cy)) in enumerate(zip(self.corners, (
                (x0, y0), (x1 - 2 * r, y0), (x1 - 2 * r, y1 - 2 * r), (x0, y1 - 2 * r)))):
            if rounded:
                d.ellipse([cx, cy, cx + 2 * r, cy + 2 * r], fill=fill)
            else:
                # Ecke ueber ihre Nummer bestimmen, nicht ueber cx == x0: bei Radius =
                # halbe Breite fallen linke und rechte Ecke zusammen (Stil "Abgerundet")
                sx = x0 if i in (0, 3) else x1 - r
                sy = y0 if i in (0, 1) else y1 - r
                d.rectangle([sx, sy, sx + r, sy + r], fill=fill)

    def _outline(self):
        r, k = self._radius(), KAPPA
        tl, tr, br, bl = (r if c else 0.0 for c in self.corners)
        x, y, w, h = self.x, self.y, self.w, self.h
        segs = [("L", (x + w - tr, y))]
        if tr:
            segs.append(("C", (x + w - tr + k * tr, y), (x + w, y + tr - k * tr), (x + w, y + tr)))
        segs.append(("L", (x + w, y + h - br)))
        if br:
            segs.append(("C", (x + w, y + h - br + k * br), (x + w - br + k * br, y + h),
                         (x + w - br, y + h)))
        segs.append(("L", (x + bl, y + h)))
        if bl:
            segs.append(("C", (x + bl - k * bl, y + h), (x, y + h - bl + k * bl), (x, y + h - bl)))
        segs.append(("L", (x, y + tl)))
        if tl:
            segs.append(("C", (x, y + tl - k * tl), (x + tl - k * tl, y), (x + tl, y)))
        return (x + tl, y), segs, False


@dataclass
class Circle(_Outlined):
    cx: float
    cy: float
    r: float

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        x0, y0 = (self.cx - self.r) * s, (self.cy - self.r) * s
        d.ellipse([x0, y0, max(x0, (self.cx + self.r) * s - 1),
                   max(y0, (self.cy + self.r) * s - 1)], fill=fill)

    def _outline(self):
        cx, cy, r = self.cx, self.cy, self.r
        k = KAPPA * r
        segs = [("C", (cx + r, cy + k), (cx + k, cy + r), (cx, cy + r)),
                ("C", (cx - k, cy + r), (cx - r, cy + k), (cx - r, cy)),
                ("C", (cx - r, cy - k), (cx - k, cy - r), (cx, cy - r)),
                ("C", (cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))]
        return (cx + r, cy), segs, False


@dataclass
class Poly(_Outlined):
    points: list[tuple[float, float]]

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        d.polygon([(x * s, y * s) for x, y in self.points], fill=fill)

    def _outline(self):
        pts = self.points
        # Flaeche > 0 heisst bei y nach unten: im Uhrzeigersinn
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
        return pts[0], [("L", p) for p in pts[1:]], area < 0


@dataclass
class Compound:
    """Eine Form mit Löchern (z. B. der Augen-Ring oder ein Rahmen mit Aussparung).

    Löcher müssen vollständig innerhalb der äußeren Form liegen und dürfen sich
    nicht überlappen.
    """
    outer: object
    holes: list = field(default_factory=list)

    def draw(self, d: ImageDraw.ImageDraw, s: float, fill: int) -> None:
        self.outer.draw(d, s, fill)
        for h in self.holes:
            h.draw(d, s, 0)

    def svg(self, hole: bool = False) -> str:
        return self.outer.svg(hole) + "".join(h.svg(not hole) for h in self.holes)

    def pdf(self, hole: bool = False) -> str:
        return self.outer.pdf(hole) + "".join(h.pdf(not hole) for h in self.holes)


def half_disc(cx: float, cy: float, r: float, facing: str, steps: int = 24) -> Poly:
    """Halbkreis, dessen gerade Kante auf x=cx liegt; facing 'right' oder 'left'."""
    sign = 1 if facing == "right" else -1
    pts = []
    for i in range(steps + 1):
        a = -math.pi / 2 + math.pi * i / steps
        pts.append((cx + sign * r * math.cos(a), cy + r * math.sin(a)))
    return Poly(pts)
