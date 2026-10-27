"""Übersetzt ein QRDesign in eine auflösungsunabhängige Szene.

Die Szene ist eine geordnete Liste aus Ebenen (Formen + Füllung), dem Logo und
der Beschriftung. render_pil und render_svg zeichnen dieselbe Szene, deshalb
sehen PNG, PDF und SVG identisch aus. 1 Einheit = 1 QR-Modul.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import Image

from . import fonts
from .colors import Gradient, Solid
from .config import QRDesign
from .matrix import QRMatrix, build
from .shapes import Circle, Compound, Poly, RRect, half_disc


@dataclass
class Layer:
    paint: Solid | Gradient
    shapes: list = field(default_factory=list)


@dataclass
class ImageItem:
    image: Image.Image  # RGBA
    box: tuple[float, float, float, float]


@dataclass
class TextItem:
    lines: list[str]
    family: str
    bold: bool
    size: float  # Schriftgröße in Einheiten
    color: str
    cx: float
    baselines: list[float]


@dataclass
class Scene:
    width: float
    height: float
    items: list
    matrix: QRMatrix
    code_box: tuple[float, float, float, float]


# ---------------------------------------------------------------- Module

def _module_shapes(style: str, on, n: int, ox: float, oy: float) -> list:
    out: list = []
    if style in ("vertical_bars", "horizontal_bars"):
        vertical = style == "vertical_bars"
        for a in range(n):
            b = 0
            while b < n:
                x, y = (a, b) if vertical else (b, a)
                if not on(x, y):
                    b += 1
                    continue
                start = b
                while b < n and on(*((a, b) if vertical else (b, a))):
                    b += 1
                length = b - start
                if vertical:
                    out.append(RRect(ox + a + 0.1, oy + start + 0.06, 0.8, length - 0.12, r=0.4))
                else:
                    out.append(RRect(ox + start + 0.06, oy + a + 0.1, length - 0.12, 0.8, r=0.4))
        return out

    for y in range(n):
        for x in range(n):
            if not on(x, y):
                continue
            px, py = ox + x, oy + y
            if style == "gapped_square":
                out.append(RRect(px + 0.1, py + 0.1, 0.8, 0.8))
            elif style == "circle":
                out.append(Circle(px + 0.5, py + 0.5, 0.45))
            elif style == "diamond":
                out.append(Poly([(px + 0.5, py - 0.02), (px + 1.02, py + 0.5),
                                 (px + 0.5, py + 1.02), (px - 0.02, py + 0.5)]))
            elif style == "rounded":
                up, down, left, right = on(x, y - 1), on(x, y + 1), on(x - 1, y), on(x + 1, y)
                corners = (not (up or left), not (up or right),
                           not (down or right), not (down or left))
                out.append(RRect(px, py, 1, 1, r=0.5, corners=corners))
            else:
                out.append(RRect(px, py, 1, 1))
    return out


# ---------------------------------------------------------------- Augen

_LEAF = {0: (True, False, True, False), 1: (False, True, False, True), 2: (False, True, False, True)}
_DROP = (False, True, False, True)  # alle drei Augen gleich: oben rechts und unten links rund


def _eye_outer(style: str, ex: float, ey: float, idx: int) -> list:
    if style == "dots":
        return [Circle(ex + i + 0.5, ey + j + 0.5, 0.46)
                for j in range(7) for i in range(7) if i in (0, 6) or j in (0, 6)]
    if style == "circle":
        return [Compound(Circle(ex + 3.5, ey + 3.5, 3.5), [Circle(ex + 3.5, ey + 3.5, 2.5)])]
    if style == "rounded":
        return [Compound(RRect(ex, ey, 7, 7, r=2.2), [RRect(ex + 1, ey + 1, 5, 5, r=1.4)])]
    if style == "leaf":
        c = _LEAF[idx]
        return [Compound(RRect(ex, ey, 7, 7, r=3.0, corners=c),
                         [RRect(ex + 1, ey + 1, 5, 5, r=2.0, corners=c)])]
    if style == "drop":
        return [Compound(RRect(ex, ey, 7, 7, r=2.2, corners=_DROP),
                         [RRect(ex + 1, ey + 1, 5, 5, r=1.4, corners=_DROP)])]
    return [Compound(RRect(ex, ey, 7, 7), [RRect(ex + 1, ey + 1, 5, 5)])]


def _eye_inner(style: str, ex: float, ey: float, idx: int) -> list:
    x, y = ex + 2, ey + 2
    if style == "dots":
        # Punkte berühren sich, damit das Finder-Verhältnis 1:1:3:1:1 für Scanner erhalten bleibt
        return [Circle(x + i + 0.5, y + j + 0.5, 0.52) for j in range(3) for i in range(3)]
    if style == "circle":
        return [Circle(x + 1.5, y + 1.5, 1.5)]
    if style == "rounded":
        return [RRect(x, y, 3, 3, r=0.9)]
    if style == "leaf":
        return [RRect(x, y, 3, 3, r=1.5, corners=_LEAF[idx])]
    if style == "drop":
        return [RRect(x, y, 3, 3, r=0.9, corners=_DROP)]
    return [RRect(x, y, 3, 3)]


# ---------------------------------------------------------------- Logo

def load_logo(path: str) -> Image.Image | None:
    if not path:
        return None
    try:
        with Image.open(path) as im:
            return im.convert("RGBA")
    except (OSError, ValueError):
        return None


def _logo_boxes(d: QRDesign, logo: Image.Image, n: int, ox: float, oy: float):
    longest = d.logo_size * n
    w, h = logo.size
    lw, lh = (longest, longest * h / w) if w >= h else (longest * w / h, longest)
    pad = d.logo_padding * longest
    cx, cy = ox + n / 2, oy + n / 2
    logo_box = (cx - lw / 2, cy - lh / 2, lw, lh)
    plate_box = (cx - lw / 2 - pad, cy - lh / 2 - pad, lw + 2 * pad, lh + 2 * pad)
    return logo_box, plate_box


# ---------------------------------------------------------------- Pfeil

def _bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def _arrow_shapes(a: float, s: float, cap_h: float, flip_h: float | None) -> list:
    """Handgezeichneter Pfeil links neben der Karte (Breite ``a``, Karte ``s`` hoch).

    Er beginnt neben der Beschriftung unter der Karte, schwingt nach links aus und zeigt
    mit der Spitze schräg nach oben auf die Karte. ``flip_h``: Gesamthöhe, an der der
    Pfeil gespiegelt wird -- für die Beschriftung über der Karte.
    """
    tail = (0.70 * a, s + 0.50 * cap_h)
    tip = (0.96 * a, 0.47 * s)
    c1, c2 = (-0.08 * a, s + 0.05 * cap_h), (0.22 * a, 0.70 * s)
    w_max = 0.034 * s  # Strichbreite in der Mitte; zu den Enden hin schmaler wie mit dem Pinsel

    # Spitze: schlank, mit nach innen gebogenen Flanken und hinten eingekerbt
    ux, uy = tip[0] - c2[0], tip[1] - c2[1]
    n = math.hypot(ux, uy) or 1
    ux, uy = ux / n, uy / n
    vx, vy = -uy, ux
    length, half_w = 0.16 * s, 0.058 * s
    back = (tip[0] - ux * length, tip[1] - uy * length)
    notch = (tip[0] - ux * length * 0.62, tip[1] - uy * length * 0.62)

    # Schaft: endet innerhalb der Spitze, sonst stumpft sein Ende die Spitze ab
    steps = 48
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        x, y = _bezier(tail, c1, c2, tip, t)
        if math.dist((x, y), tip) < length * 0.45:
            break
        dx, dy = _bezier(tail, c1, c2, tip, min(1, t + 1e-3))
        ex, ey = _bezier(tail, c1, c2, tip, max(0, t - 1e-3))
        tx, ty = dx - ex, dy - ey
        n = math.hypot(tx, ty) or 1
        nx, ny = -ty / n, tx / n
        half = w_max / 2 * (0.4 + 0.6 * math.sin(math.pi * t))
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    shaft = Poly(left + right[::-1])
    tail_r = math.dist(left[0], right[0]) / 2
    cap = Circle(tail[0], tail[1], tail_r)

    def barb(sign: int) -> list[tuple[float, float]]:
        end = (back[0] + sign * vx * half_w, back[1] + sign * vy * half_w)
        ctrl = (tip[0] - ux * length * 0.5 + sign * vx * half_w * 0.12,
                tip[1] - uy * length * 0.5 + sign * vy * half_w * 0.12)
        pts = []
        for i in range(1, 13):
            t = i / 12
            pts.append(((1 - t) ** 2 * tip[0] + 2 * (1 - t) * t * ctrl[0] + t * t * end[0],
                        (1 - t) ** 2 * tip[1] + 2 * (1 - t) * t * ctrl[1] + t * t * end[1]))
        return pts

    head = Poly([tip] + barb(1) + [notch] + barb(-1)[::-1])
    shapes = [shaft, cap, head]
    if flip_h is not None:
        shapes = [_mirror_y(sh, flip_h) for sh in shapes]
    return shapes


def _mirror_y(shape, h: float):
    if isinstance(shape, Circle):
        return Circle(shape.cx, h - shape.cy, shape.r)
    return Poly([(x, h - y) for x, y in shape.points])


# ---------------------------------------------------------------- Text

def _text_item(d: QRDesign, box: tuple[float, float, float, float]) -> TextItem | None:
    lines = [ln for ln in d.caption.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    bx, by, bw, bh = box
    ref = 200
    font = fonts.load(d.caption_font, d.caption_bold, ref)
    asc, desc = font.getmetrics()
    widest = max(font.getlength(ln) for ln in lines) or 1
    size_w = bw * 0.86 / widest * ref
    size_h = bh * 0.78 / (len(lines) * (asc + desc)) * ref
    size = min(size_w, size_h) * max(30, min(100, d.caption_size)) / 100
    k = size / ref
    line_h = (asc + desc) * k
    top = by + bh / 2 - line_h * len(lines) / 2
    baselines = [top + i * line_h + asc * k for i in range(len(lines))]
    return TextItem(lines, d.caption_font, d.caption_bold, size, d.caption_color,
                    bx + bw / 2, baselines)


# ---------------------------------------------------------------- Szene

def build_scene(d: QRDesign, logo: Image.Image | None = None, matrix: QRMatrix | None = None) -> Scene:
    m = matrix or build(d.payload, d.ecc)
    n, b = m.size, max(0, d.border)
    C = n + 2 * b
    has_cap = bool(d.caption.strip())
    frame = d.frame

    # --- Layout: Leinwand, Position des Code-Panels, Rahmen, Textfeld
    top = d.caption_position == "top"
    frame_shapes: list = []
    arrow_shapes: list = []
    card = None
    text_box = None
    radius = 0.0
    if frame in ("banner_bottom", "banner_top", "ticket"):
        p, radius = 1.4, 3.0
        cap_h = C * 0.22
        W = C + 2 * p
        if frame == "ticket":
            ys = p + C + p * 0.7
            H = ys + cap_h + p * 0.4
            px, py = p, p
            holes = [RRect(px, py, C, C, r=1.6),
                     half_disc(0, ys, p * 0.9, "right"), half_disc(W, ys, p * 0.9, "left")]
            x = p * 1.2
            while x + 0.8 <= W - p * 1.2:
                holes.append(RRect(x, ys - 0.11, 0.8, 0.22, r=0.11))
                x += 1.4
            text_box = (p, ys + 0.3, C, H - ys - 0.3 - p * 0.4)
        else:
            H = C + 2 * p + cap_h
            if frame == "banner_bottom":
                px, py = p, p
                text_box = (p, p + C + 0.2, C, cap_h + p - 0.6)
            else:
                px, py = p, p + cap_h
                text_box = (p, 0.4, C, cap_h + p - 0.6)
            holes = [RRect(px, py, C, C, r=1.6)]
        frame_shapes = [Compound(RRect(0, 0, W, H, r=radius), holes)]
    elif frame == "arrow":
        # Karte mit feiner Linie, links daneben der Pfeil, darunter (oder darüber) die Schrift
        lw = max(0.2, C * 0.008)
        S = C + 2 * lw
        radius = S * 0.05
        A = S * 0.2
        cap_h = S * 0.40
        W, H = A + S, S + cap_h
        cy = cap_h if top else 0.0
        px, py = A + lw, cy + lw
        card = RRect(A, cy, S, S, r=radius)
        frame_shapes = [Compound(card, [RRect(A + lw, cy + lw, C, C, r=max(0.0, radius - lw))])]
        arrow_shapes = _arrow_shapes(A, S, cap_h, H if top else None)
        text_box = (A, 0.02 * cap_h if top else S + 0.08 * cap_h, S, cap_h * 0.9)
        radius = 0.0  # die Leinwand selbst bleibt eckig
    elif frame in ("thin", "card"):
        lw, radius, inner_r = (0.5, 1.2, 0.8) if frame == "thin" else (1.2, 3.0, 2.0)
        W = C + 2 * lw
        cap_h = C * 0.2 if has_cap else 0
        H = W + cap_h
        px, py = lw, lw + (cap_h if top else 0)
        frame_shapes = [Compound(RRect(0, 0, W, H, r=radius),
                                 [RRect(lw, lw, W - 2 * lw, H - 2 * lw, r=inner_r)])]
        if has_cap:
            text_box = (lw, lw + b * 0.6 if top else lw + C - b * 0.6, C, cap_h)
    else:
        W = C
        cap_h = C * 0.2 if has_cap else 0
        H = C + cap_h
        px, py = 0, (cap_h if top else 0)
        if has_cap:
            text_box = (0, b * 0.6 if top else C - b * 0.6, C, cap_h)

    ox, oy = px + b, py + b
    items: list = []
    if not d.transparent_bg:
        items.append(Layer(Solid(d.bg_color), [RRect(0, 0, W, H, r=radius)]))
    elif card is not None:
        items.append(Layer(Solid(d.bg_color), [card]))  # die Karte bleibt deckend
    if frame_shapes:
        items.append(Layer(Solid(d.frame_color), frame_shapes))
    if arrow_shapes:
        items.append(Layer(Solid(d.arrow_color), arrow_shapes))

    # --- Logo: Freifläche bestimmen
    logo_box = plate_box = None
    if logo is not None:
        logo_box, plate_box = _logo_boxes(d, logo, n, ox, oy)

    def cleared(x: int, y: int) -> bool:
        if plate_box is None:
            return False
        qx, qy, qw, qh = plate_box
        inset = 0.15
        return (ox + x + 1 > qx + inset and ox + x < qx + qw - inset and
                oy + y + 1 > qy + inset and oy + y < qy + qh - inset)

    def on(x: int, y: int) -> bool:
        return m.dark(x, y) and not m.in_finder(x, y) and not cleared(x, y)

    # --- Module und Augen
    if d.gradient in ("linear", "radial"):
        paint = Gradient(d.gradient, d.fg_color, d.gradient_color, d.gradient_angle, (ox, oy, n, n))
    else:
        paint = Solid(d.fg_color)
    rings, pupils = [], []
    for idx, (fx, fy) in enumerate(m.finder_origins()):
        rings += _eye_outer(d.eye_outer_style, ox + fx, oy + fy, idx)
        pupils += _eye_inner(d.eye_inner_style, ox + fx, oy + fy, idx)
    modules = _module_shapes(d.module_style, on, n, ox, oy)

    if d.eye_custom_color:
        items.append(Layer(paint, modules))
        items.append(Layer(Solid(d.eye_outer_color), rings))
        items.append(Layer(Solid(d.eye_inner_color), pupils))
    else:
        # Ringe zuerst: ihre Löcher werden in PIL ausradiert und dürfen keine Pupille treffen.
        items.append(Layer(paint, rings + pupils + modules))

    # --- Logo
    if logo is not None:
        if d.logo_plate:
            qx, qy, qw, qh = plate_box
            items.append(Layer(Solid(d.logo_plate_color),
                               [RRect(qx, qy, qw, qh, r=d.logo_radius * min(qw, qh))]))
        items.append(ImageItem(logo, logo_box))

    # --- Beschriftung
    if text_box:
        t = _text_item(d, text_box)
        if t:
            items.append(t)

    return Scene(W, H, items, m, (ox, oy, n, n))
