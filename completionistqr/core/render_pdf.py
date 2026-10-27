"""Rendert eine Szene als echtes Vektor-PDF – dieselben Formen wie render_pil und render_svg.

* Module, Augen, Rahmen: PDF-Pfade, gefüllt nach der Regel nonzero (siehe shapes.py)
* Farbverläufe: PDF-Shadings (axial/radial) mit denselben Koordinaten wie im SVG
* Logo: Bild in Originalauflösung, Transparenz als Soft Mask
* Beschriftung: Glyphen als Vektorkonturen. HarfBuzz setzt die Zeile (Unterschneidung,
  Ligaturen, Gewicht der Variable Fonts); dadurch braucht das PDF keine eingebettete
  Schrift und sieht in jedem Programm und auf jedem Drucker gleich aus.

Ohne Raster ist der Code in jeder Druckgröße randscharf. Die Seitengröße ergibt sich
wie beim PNG aus Breite und dpi (1024 px bei 300 dpi = 86,7 mm).
"""
from __future__ import annotations

import time
import zlib
from pathlib import Path

from PIL import Image

from . import fonts
from .colors import Gradient, rgb
from .config import QRDesign
from .geometry import ImageItem, Layer, Scene, TextItem, build_scene, load_logo
from .shapes import _f, _p

PRODUCER = "CompletionistQR"


def _color(color: str) -> str:
    return " ".join(_p(c / 255) for c in rgb(color))


# ---------------------------------------------------------------- Text

class _OutlinePen:
    """Sammelt Glyphen-Konturen von HarfBuzz als Pfad (Szene-Einheiten, y nach unten) --
    als PDF-Operatoren oder, mit ``svg``, als SVG-Pfaddaten."""

    def __init__(self, svg: bool = False) -> None:
        self.svg = svg
        self.ops: list[str] = []
        self.ox = self.oy = self.k = 0.0
        self.cur = (0.0, 0.0)

    def place(self, ox: float, oy: float, k: float) -> None:
        self.ox, self.oy, self.k = ox, oy, k

    def _pt(self, p) -> tuple[float, float]:
        return self.ox + p[0] * self.k, self.oy - p[1] * self.k  # Schrift: y nach oben

    def _emit(self, op: str, pts) -> None:
        fmt = _f if self.svg else _p
        coords = " ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts)
        if self.svg:
            self.ops.append({"m": "M", "l": "L", "c": "C"}[op] + coords)
        else:
            self.ops.append(f"{coords} {op}")
        self.cur = pts[-1]

    def moveTo(self, p) -> None:  # noqa: N802 -- Pen-Protokoll von fontTools/HarfBuzz
        self._emit("m", [self._pt(p)])

    def lineTo(self, p) -> None:  # noqa: N802
        self._emit("l", [self._pt(p)])

    def curveTo(self, *pts) -> None:  # noqa: N802
        self._emit("c", [self._pt(p) for p in pts])

    def qCurveTo(self, *pts) -> None:  # noqa: N802
        # TrueType: zwischen zwei Kontrollpunkten liegt implizit ein Kurvenpunkt
        pts = [self._pt(p) for p in pts]
        ctrl, end = pts[:-1], pts[-1]
        for i, c in enumerate(ctrl):
            nxt = end if i == len(ctrl) - 1 else ((c[0] + ctrl[i + 1][0]) / 2,
                                                   (c[1] + ctrl[i + 1][1]) / 2)
            p0 = self.cur
            c1 = (p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1]))
            c2 = (nxt[0] + 2 / 3 * (c[0] - nxt[0]), nxt[1] + 2 / 3 * (c[1] - nxt[1]))
            self._emit("c", [c1, c2, nxt])

    def closePath(self) -> None:  # noqa: N802
        self.ops.append("Z" if self.svg else "h")

    endPath = closePath  # noqa: N815


def _hb_font(path: Path, bold: bool, variable: bool):
    import uharfbuzz as hb

    font = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))
    if variable:
        # wie fonts.load: Gewicht immer setzen, die Standardinstanz ist teils "Thin"
        for axis in font.face.axis_infos:
            if axis.tag == "wght":
                font.set_variations({"wght": max(axis.min_value, min(700 if bold else 400,
                                                                      axis.max_value))})
    return font


def text_path(item: TextItem, svg: bool = False) -> str:
    """Alle Zeilen der Beschriftung als ein Pfad (PDF-Operatoren oder mit ``svg``
    SVG-Pfaddaten); wie in PIL mittig auf der Grundlinie."""
    import uharfbuzz as hb

    path, variable = fonts.font_file(item.family, item.bold)
    if not path.is_file():
        raise FileNotFoundError(f"Schrift „{item.family}“ nicht gefunden")
    font = _hb_font(path, item.bold, variable)
    k = item.size / font.face.upem
    pen = _OutlinePen(svg)
    for line, base in zip(item.lines, item.baselines):
        buf = hb.Buffer()
        buf.add_str(line)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        width = sum(p.x_advance for p in buf.glyph_positions)
        x = 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            pen.place(item.cx + (x + pos.x_offset - width / 2) * k, base - pos.y_offset * k, k)
            font.draw_glyph_with_pen(info.codepoint, pen)
            x += pos.x_advance
    return ("" if svg else "\n").join(pen.ops)


# ---------------------------------------------------------------- PDF-Datei

class _Writer:
    def __init__(self) -> None:
        self.objects: list[bytes] = []

    def add(self, body: bytes | str) -> int:
        self.objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(self.objects)

    def stream(self, data: bytes, extra: str = "") -> int:
        packed = zlib.compress(data, 9)
        return self.add(f"<< /Length {len(packed)} /Filter /FlateDecode {extra}>>\nstream\n"
                        .encode("latin-1") + packed + b"\nendstream")

    def reserve(self) -> int:
        self.objects.append(b"")
        return len(self.objects)

    def set(self, num: int, body: str) -> None:
        self.objects[num - 1] = body.encode("latin-1")

    def output(self, root: int, info: int) -> bytes:
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(self.objects, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
        out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode("latin-1")
        out += (f"trailer\n<< /Size {len(self.objects) + 1} /Root {root} 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
        return bytes(out)


def _shading(w: _Writer, paint: Gradient) -> int:
    fn = (f"<< /FunctionType 2 /Domain [0 1] /C0 [{_color(paint.c1)}] "
          f"/C1 [{_color(paint.c2)}] /N 1 >>")
    if paint.kind == "radial":
        cx, cy, r = paint.radial_params()
        coords, kind = f"{_p(cx)} {_p(cy)} 0 {_p(cx)} {_p(cy)} {_p(r)}", 3
    else:
        coords, kind = " ".join(_p(v) for v in paint.linear_points()), 2
    # Extend: ueber die Endpunkte hinaus mit der Endfarbe weiter, wie PIL und SVG
    return w.add(f"<< /ShadingType {kind} /ColorSpace /DeviceRGB /Coords [{coords}] "
                 f"/Function {fn} /Extend [true true] >>")


def _image(w: _Writer, img: Image.Image) -> int:
    rgba = img.convert("RGBA")
    width, height = rgba.size
    smask = ""
    alpha = rgba.getchannel("A")
    if alpha.getextrema() != (255, 255):
        num = w.stream(alpha.tobytes(), f"/Type /XObject /Subtype /Image /Width {width} "
                                        f"/Height {height} /ColorSpace /DeviceGray "
                                        f"/BitsPerComponent 8 /Interpolate true ")
        smask = f"/SMask {num} 0 R "
    return w.stream(rgba.convert("RGB").tobytes(),
                    f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
                    f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate true {smask}")


def _date() -> str:
    t = time.localtime()
    off = -time.timezone if not t.tm_isdst else -time.altzone
    sign = "+" if off >= 0 else "-"
    return time.strftime("D:%Y%m%d%H%M%S", t) + f"{sign}{abs(off) // 3600:02d}'{abs(off) % 3600 // 60:02d}'"


def scene_to_pdf(scene: Scene, width_pt: float, title: str = "QR-Code") -> bytes:
    """PDF mit einer Seite von ``width_pt`` Punkt Breite (Höhe nach Seitenverhältnis)."""
    from .. import __version__

    s = width_pt / scene.width
    height_pt = scene.height * s
    w = _Writer()
    catalog, pages, page = w.reserve(), w.reserve(), w.reserve()
    shadings: dict[str, int] = {}
    images: dict[str, int] = {}
    ops = [f"1 0 0 -1 0 {_p(height_pt)} cm", f"{_p(s)} 0 0 {_p(s)} 0 0 cm"]  # Szene, y nach unten

    for item in scene.items:
        if isinstance(item, Layer):
            if not item.shapes:
                continue
            path = "".join(shape.pdf() for shape in item.shapes)
            if isinstance(item.paint, Gradient):
                name = f"Sh{len(shadings)}"
                shadings[name] = _shading(w, item.paint)
                ops.append(f"q\n{path}W n /{name} sh Q")
            else:
                ops.append(f"{_color(item.paint.color)} rg\n{path}f")
        elif isinstance(item, ImageItem):
            name = f"Im{len(images)}"
            images[name] = _image(w, item.image)
            x, y, bw, bh = item.box
            # Bildraum (0,0)-(1,1) mit erster Zeile oben auf die Box
            ops.append(f"q {_p(bw)} 0 0 {_p(-bh)} {_p(x)} {_p(y + bh)} cm /{name} Do Q")
        elif isinstance(item, TextItem):
            ops.append(f"{_color(item.color)} rg\n{text_path(item)}\nf")

    content = w.stream("\n".join(ops).encode("latin-1"))
    resources = []
    if shadings:
        resources.append("/Shading << " + " ".join(f"/{k} {v} 0 R" for k, v in shadings.items()) + " >>")
    if images:
        resources.append("/XObject << " + " ".join(f"/{k} {v} 0 R" for k, v in images.items()) + " >>")
    w.set(page, f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {_p(width_pt)} {_p(height_pt)}] "
                f"/Resources << {' '.join(resources)} >> /Contents {content} 0 R >>")
    w.set(pages, f"<< /Type /Pages /Kids [{page} 0 R] /Count 1 >>")
    w.set(catalog, f"<< /Type /Catalog /Pages {pages} 0 R >>")
    # Bewusst nicht der Inhalt des Codes: der kann z. B. ein WLAN-Passwort sein
    info = w.add(f"<< /Title {_pdf_text(title)} /Producer ({PRODUCER} {__version__}) "
                 f"/Creator ({PRODUCER} {__version__}) /CreationDate ({_date()}) >>")
    return w.output(catalog, info)


def _pdf_text(text: str) -> str:
    """PDF-Textstring als UTF-16BE mit BOM (Hex), damit auch Umlaute stimmen."""
    return "<FEFF" + text.encode("utf-16-be").hex().upper() + ">"


def render(design: QRDesign, width_px: int = 1024, dpi: int = 300) -> bytes:
    scene = build_scene(design, load_logo(design.logo_path))
    return scene_to_pdf(scene, width_px / dpi * 72)
