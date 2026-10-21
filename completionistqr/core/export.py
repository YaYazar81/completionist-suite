"""Speichern als PNG, SVG oder PDF sowie die Scan-Selbstprüfung."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import render_pdf, render_pil, render_svg
from .config import QRDesign

FORMATS = {"PNG": ".png", "SVG": ".svg", "PDF": ".pdf"}


def save(design: QRDesign, path: str | Path, width_px: int = 1024, dpi: int = 300) -> Path:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".svg":
        path.write_text(render_svg.render(design, width_px), encoding="utf-8")
    elif ext == ".pdf":
        # Vektor-PDF; Breite und dpi bestimmen nur noch die Seitengroesse
        try:
            data = render_pdf.render(design, width_px, dpi)
        except (ImportError, OSError) as exc:  # HarfBuzz oder Schrift fehlt: lieber Raster als nichts
            import logging

            logging.getLogger(__name__).warning("Vektor-PDF nicht moeglich (%s), nehme Raster", exc)
            img = render_pil.flatten(render_pil.render(design, width_px), design.bg_color)
            img.save(path, "PDF", resolution=dpi)
        else:
            path.write_bytes(data)
    else:
        img = render_pil.render(design, width_px)
        if not design.transparent_bg:
            img = img.convert("RGB")
        img.save(path, "PNG", dpi=(dpi, dpi))
    return path


def decode(img: Image.Image) -> str | None:
    """Liest den QR-Code im Bild mit ZXing (zxing-cpp) zurück; None, wenn nicht lesbar."""
    try:
        import zxingcpp
    except ImportError:
        return None
    rgb = render_pil.flatten(img) if img.mode == "RGBA" else img.convert("RGB")
    results = zxingcpp.read_barcodes(rgb, formats=zxingcpp.BarcodeFormat.QRCode)
    return results[0].text if results else None


def scan_check(design: QRDesign, img: Image.Image | None = None) -> bool:
    """True, wenn der gerenderte Code den Original-Inhalt exakt zurückliefert."""
    img = img if img is not None else render_pil.render(design, 640, supersample=2)
    return decode(img) == (design.payload or " ")
