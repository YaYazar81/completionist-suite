"""Vektor-Export: PDF ohne Raster, SVG/PDF füllen wie Pillow (nonzero), Ecken der Module."""
from __future__ import annotations

import os
import re

import pytest
from PIL import Image, ImageDraw

from completionistqr.core import export, presets, render_pdf, render_svg
from completionistqr.core.config import QRDesign
from completionistqr.core.geometry import Layer, Scene
from completionistqr.core.colors import Solid
from completionistqr.core.shapes import Circle, Compound, RRect

PAYLOAD = "https://example.com/qr-studio?ref=test-1234"


@pytest.fixture(scope="module")
def logo_path(tmp_path_factory):
    img = Image.new("RGBA", (400, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, 399, 239], radius=60, fill=(220, 38, 38, 255))
    d.ellipse([140, 40, 260, 200], fill=(255, 255, 255, 255))
    p = tmp_path_factory.mktemp("logo") / "logo.png"
    img.save(p)
    return str(p)


@pytest.fixture(scope="module")
def rasterize():
    """PDF -> PIL-Bild über QtPdf (wie der Viewer von CompletionistPDF)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtPdf")
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["pytest"])

    def run(path, width: int) -> Image.Image:
        doc = QPdfDocument()
        assert doc.load(str(path)) == QPdfDocument.Error.None_
        pt = doc.pagePointSize(0)
        qimg = doc.render(0, QSize(width, round(width * pt.height() / pt.width())))
        qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        img = Image.frombuffer("RGBA", (qimg.width(), qimg.height()), bytes(qimg.constBits()),
                               "raw", "RGBA", qimg.bytesPerLine(), 1)
        white = Image.new("RGBA", img.size, "white")
        white.alpha_composite(img)
        doc.close()
        return white.convert("RGB")

    yield run
    del app


def test_rrect_square_corners_land_where_asked():
    """Radius = halbe Breite (Stil "Abgerundet"): eckige Ecke rechts, runde links."""
    img = Image.new("L", (100, 100), 0)
    RRect(0, 0, 1, 1, r=0.5, corners=(True, False, False, True)).draw(ImageDraw.Draw(img), 100, 255)
    assert img.getpixel((97, 2)) == 255 and img.getpixel((97, 97)) == 255  # rechts eckig
    assert img.getpixel((2, 2)) == 0 and img.getpixel((2, 97)) == 0  # links rund


def test_hole_paths_run_against_outer():
    ring = Compound(RRect(0, 0, 7, 7), [RRect(1, 1, 5, 5)])
    outer, hole = ring.pdf().strip().splitlines()
    # Aussen erst nach rechts (Uhrzeigersinn bei y nach unten), das Loch umgekehrt
    assert outer.startswith("0 0 m 7 0 l")
    assert hole.startswith("1 1 m 1 6 l")
    assert ring.svg().startswith("M0 0L7 0") and "M1 1L1 6" in ring.svg()


def test_overlaps_merge_and_holes_stay_open(tmp_path, rasterize):
    """Sich überlappende Punkte (Pupille "Punkte") dürfen keine Schlitze stanzen."""
    scene = Scene(10, 10, [Layer(Solid("#000000"), [
        Compound(RRect(0, 0, 10, 10), [RRect(2, 2, 6, 6)]),  # Ring mit Loch
        Circle(4.5, 5, 0.52), Circle(5.5, 5, 0.52)])], matrix=None, code_box=(0, 0, 10, 10))
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(render_pdf.scene_to_pdf(scene, 200))
    img = rasterize(pdf, 400).convert("L")
    assert img.getpixel((200, 200)) < 40   # Überlappung der beiden Punkte: gefüllt
    assert img.getpixel((120, 120)) > 215  # im Loch des Rings: frei
    assert img.getpixel((20, 20)) < 40     # Ring selbst
    assert 'fill-rule="nonzero"' in render_svg.scene_to_svg(scene)


@pytest.mark.parametrize("name", list(presets.builtin()))
def test_pdf_is_vector_and_scans(name, tmp_path, logo_path, rasterize):
    style = presets.builtin()[name]
    d = QRDesign(payload=PAYLOAD, logo_path=logo_path, logo_size=0.2).apply_style(style)
    d.caption = style.get("caption") or "SCAN ME – Wäh"
    out = export.save(d, tmp_path / "qr.pdf", width_px=1024, dpi=300)
    data = out.read_bytes()
    assert data.startswith(b"%PDF-1.7") and data.rstrip().endswith(b"%%EOF")
    assert b"/Font" not in data  # Schrift als Konturen, keine Schriftabhängigkeit
    # Logo in Originalauflösung statt herunterskaliert
    assert b"/Width 400 /Height 240" in data
    if d.gradient != "none":
        assert b"/ShadingType" in data
    assert export.decode(rasterize(out, 900)) == PAYLOAD, f"{name}: PDF nicht lesbar"


def test_pdf_page_size_and_xref(tmp_path):
    data = render_pdf.render(QRDesign(payload=PAYLOAD), width_px=1024, dpi=300)
    # 1024 px bei 300 dpi = 3,413 Zoll = 245,76 pt
    assert b"/MediaBox [0 0 245.76 245.76]" in data
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    entries = data[xref:].split(b"\n")[3:]
    for i, line in enumerate(entries, 1):
        if not line.endswith(b" n "):
            break
        offset = int(line[:10])
        assert data[offset:].startswith(f"{i} 0 obj".encode())


def test_svg_caption_is_outlined_not_a_font(tmp_path):
    """Die Beschriftung steht als Kontur im SVG: eine per @font-face eingebettete
    Schrift zeigen nur Browser, Grafikprogramme fielen auf Ersatzschriften zurück."""
    style = presets.builtin()["Scan-Me Banner"]
    d = QRDesign(payload=PAYLOAD).apply_style(style)
    d.caption = "SCAN ME – Wäh"
    svg = render_svg.render(d)
    assert "<text" not in svg and "@font-face" not in svg
    assert 'aria-label="SCAN ME – Wäh"' in svg
    caption = svg[svg.index('aria-label="SCAN ME'):]
    assert ' d="M' in caption[:200] and "C" in caption.split('"')[3]
