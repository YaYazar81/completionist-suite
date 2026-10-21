"""Rendert eine Szene als SVG – dieselben Formen wie render_pil, aber als Vektor."""
from __future__ import annotations

import base64
import io
from xml.sax.saxutils import escape

from . import fonts
from .colors import Gradient
from .config import QRDesign
from .geometry import ImageItem, Layer, Scene, TextItem, build_scene, load_logo
from .shapes import _f


def _paint(paint, idx: int, defs: list[str]) -> str:
    if not isinstance(paint, Gradient):
        return escape(paint.color)
    gid = f"g{idx}"
    stops = (f'<stop offset="0" stop-color="{escape(paint.c1)}"/>'
             f'<stop offset="1" stop-color="{escape(paint.c2)}"/>')
    if paint.kind == "radial":
        cx, cy, r = paint.radial_params()
        defs.append(f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                    f'cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(r)}">{stops}</radialGradient>')
    else:
        x1, y1, x2, y2 = paint.linear_points()
        defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                    f'x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}">{stops}</linearGradient>')
    return f"url(#{gid})"


def _font_face(item: TextItem) -> str:
    path, variable = fonts.font_file(item.family, item.bold)
    if fonts.FONT_DIR not in path.parents:
        return ""  # Systemschriften (Fallback) dürfen nicht weitergegeben werden
    try:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    weight = "100 900" if variable else ("700" if item.bold else "400")
    return ("<style>@font-face{font-family:'QRCaption';"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');"
            f"font-weight:{weight};}}</style>")


def scene_to_svg(scene: Scene, width_px: int = 1024) -> str:
    defs: list[str] = []
    body: list[str] = []
    for idx, item in enumerate(scene.items):
        if isinstance(item, Layer):
            if not item.shapes:
                continue
            d = "".join(s.svg() for s in item.shapes)
            body.append(f'<path fill="{_paint(item.paint, idx, defs)}" fill-rule="nonzero" d="{d}"/>')
        elif isinstance(item, ImageItem):
            buf = io.BytesIO()
            item.image.save(buf, "PNG")
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            x, y, w, h = item.box
            body.append(f'<image x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" '
                        f'preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{data}"/>')
        elif isinstance(item, TextItem):
            defs.append(_font_face(item))
            weight = 700 if item.bold else 400
            for line, base in zip(item.lines, item.baselines):
                body.append(f'<text x="{_f(item.cx)}" y="{_f(base)}" text-anchor="middle" '
                            f"font-family=\"'QRCaption', '{escape(item.family)}', sans-serif\" "
                            f'font-weight="{weight}" font-size="{_f(item.size)}" '
                            f'fill="{escape(item.color)}">{escape(line)}</text>')

    height_px = round(width_px * scene.height / scene.width)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" '
            f'viewBox="0 0 {_f(scene.width)} {_f(scene.height)}" shape-rendering="geometricPrecision">'
            f'<defs>{"".join(defs)}</defs>{"".join(body)}</svg>')


def render(design: QRDesign, width_px: int = 1024) -> str:
    return scene_to_svg(build_scene(design, load_logo(design.logo_path)), width_px)
