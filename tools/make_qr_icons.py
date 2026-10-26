"""Rendert die Lucide-Icons fuer CompletionistQR als PNG.

CompletionistQR (customtkinter) bringt kein Qt und keinen SVG-Renderer mit;
deshalb liegen die Icons dort fertig gerastert in completionistqr/assets/icons,
je Icon in den Farben von core/design.py (gedaempft bzw. Smaragd, hell/dunkel).

Aufruf nach dem Hinzufuegen eines Icons:  python tools/make_qr_icons.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QByteArray, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from core.design import DARK, LIGHT  # noqa: E402

SIZE = 48  # 2x/3x-tauglich fuer 18-20-px-Knoepfe
OUT = ROOT / "completionistqr" / "assets" / "icons"
VARIANTS = {
    "light": LIGHT["muted"],
    "dark": DARK["muted"],
    "accent_light": LIGHT["accent_hi"],
    "accent_dark": DARK["accent_hi"],
}


def icon_names() -> tuple[str, ...]:
    """ICONS aus completionistqr/ui/style.py -- gelesen statt importiert, denn
    der Import braucht Tkinter (customtkinter), dieses Werkzeug aber Qt."""
    tree = ast.parse((ROOT / "completionistqr" / "ui" / "style.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ICONS" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise SystemExit("ICONS nicht gefunden")


def render(name: str, color: str, target: Path) -> None:
    svg = (ROOT / "assets" / "icons" / "lucide" / f"{name}.svg").read_bytes()
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.replace(b"currentColor", color.encode()))).render(painter)
    painter.end()
    img.save(str(target))


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(["make_qr_icons", "-platform", "offscreen"])
    OUT.mkdir(parents=True, exist_ok=True)
    names = icon_names()
    for name in names:
        for variant, color in VARIANTS.items():
            render(name, color, OUT / f"{name}_{variant}.png")
    print(f"{len(names) * len(VARIANTS)} Icons in {OUT}")


if __name__ == "__main__":
    main()
