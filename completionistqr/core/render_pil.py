"""Rendert eine Szene mit Pillow (für Vorschau, PNG und PDF)."""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import fonts
from .colors import Gradient, rgb
from .config import QRDesign
from .geometry import ImageItem, Layer, Scene, TextItem, build_scene, load_logo


def render_scene(scene: Scene, width_px: int, supersample: int = 3) -> Image.Image:
    """Rendert auf `width_px` Breite; Formen werden überabgetastet für Kantenglättung."""
    ss = max(1, supersample)
    s = width_px * ss / scene.width
    W, H = round(scene.width * s), round(scene.height * s)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    for item in scene.items:
        if isinstance(item, Layer):
            mask = Image.new("L", (W, H), 0)
            d = ImageDraw.Draw(mask)
            for shape in item.shapes:
                shape.draw(d, s, 255)
            if isinstance(item.paint, Gradient):
                fill = item.paint.image(W, H, s).convert("RGBA")
            else:
                fill = Image.new("RGBA", (W, H), rgb(item.paint.color) + (255,))
            fill.putalpha(mask)
            canvas.alpha_composite(fill)
        elif isinstance(item, ImageItem):
            x, y, w, h = item.box
            size = (max(1, round(w * s)), max(1, round(h * s)))
            logo = item.image.resize(size, Image.LANCZOS)
            canvas.alpha_composite(logo, (round(x * s), round(y * s)))
        elif isinstance(item, TextItem):
            font = fonts.load(item.family, item.bold, round(item.size * s))
            d = ImageDraw.Draw(canvas)
            for line, base in zip(item.lines, item.baselines):
                d.text((item.cx * s, base * s), line, font=font, fill=rgb(item.color) + (255,),
                       anchor="ms")

    out_size = (max(1, round(W / ss)), max(1, round(H / ss)))
    return canvas.resize(out_size, Image.LANCZOS) if ss > 1 else canvas


def render(design: QRDesign, width_px: int = 1024, supersample: int = 3) -> Image.Image:
    scene = build_scene(design, load_logo(design.logo_path))
    return render_scene(scene, width_px, supersample)


def flatten(img: Image.Image, color: str = "#FFFFFF") -> Image.Image:
    """RGBA -> RGB auf Volltonhintergrund (für PDF und die Scan-Prüfung)."""
    bg = Image.new("RGBA", img.size, rgb(color) + (255,))
    bg.alpha_composite(img)
    return bg.convert("RGB")
