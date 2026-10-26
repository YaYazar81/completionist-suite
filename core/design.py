"""Completionist Pro -- gemeinsames Design-System der Suite (Qt-Apps).

Dunkler Schiefer-Grund mit Smaragd-Akzent, 6-px-Radien und monochrome
Lucide-Icons. CompletionistMD und CompletionistPDF rufen beim Start
:func:`apply` auf; das Stylesheet liegt in ``assets/theme/theme.qss``, die
Icons in ``assets/icons/lucide`` (ISC-Lizenz, siehe THIRD_PARTY_NOTICES.md).

CompletionistQR (customtkinter) nutzt dieselben Tokens ueber ein eigenes
ctk-Theme (completionistqr/assets/theme/completionist_pro.json).
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
QSS_FILE = ROOT / "assets" / "theme" / "theme.qss"
ICON_DIR = ROOT / "assets" / "icons" / "lucide"

ICON_SIZE = QSize(20, 20)  # Icons 20 px auf 34-px-Knoepfen (6 px Innenabstand + Rahmen)

# ---------------------------------------------------------------- Tokens

DARK = {
    "bg": "#121619",          # Fenster / Canvas
    "panel": "#1C2329",       # Panels, Sidebars, Karten
    "panel_alt": "#1F272E",
    "input": "#161B20",       # Eingabefelder, inaktive Tabs
    "border": "#27323D",      # Trennlinien, Rahmen
    "border_hi": "#334250",
    "hover": "#222C35",
    "text": "#E2E8F0",        # Text primaer
    "bright": "#F8FAFC",      # Text/Icon bei Hover
    "muted": "#94A3B8",       # Text sekundaer, Icons im Ruhezustand
    "disabled": "#4B5866",
    "accent_bg": "#112C27",   # Smaragd: aktiv / ausgewaehlt (Flaeche)
    "accent": "#10B981",      # Smaragd: Fokusrahmen
    "accent_hi": "#34D399",   # Smaragd: aktives Icon, Hover-Kante
    "warn": "#FBBF24",
    "danger": "#F87171",
}

LIGHT = {
    "bg": "#F1F5F9",
    "panel": "#FFFFFF",
    "panel_alt": "#F8FAFC",
    "input": "#F8FAFC",
    "border": "#CBD5E1",
    "border_hi": "#94A3B8",
    "hover": "#E2E8F0",
    "text": "#0F172A",
    "bright": "#020617",
    "muted": "#475569",
    "disabled": "#A0AEC0",
    "accent_bg": "#D1FAE5",
    "accent": "#059669",
    "accent_hi": "#047857",
    "warn": "#B45309",
    "danger": "#B91C1C",
}

# Farben der Dateityp-Icons im Vault (unabhaengig vom Thema gut lesbar)
FILE_COLORS = {"md": "#34D399", "pdf": "#F87171", "img": "#A78BFA", "txt": "#94A3B8"}

_theme = "dark"


def tokens(theme: str | None = None) -> dict[str, str]:
    return LIGHT if (theme or _theme) == "light" else DARK


def current_theme() -> str:
    return _theme


# ---------------------------------------------------------------- Palette


def palette(theme: str = "dark") -> QPalette:
    t = tokens(theme)
    c = {k: QColor(v) for k, v in t.items()}
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, c["bg"])
    p.setColor(R.WindowText, c["text"])
    p.setColor(R.Base, c["panel"])
    p.setColor(R.AlternateBase, c["panel_alt"])
    p.setColor(R.Text, c["text"])
    p.setColor(R.Button, c["panel"])
    p.setColor(R.ButtonText, c["text"])
    p.setColor(R.BrightText, c["bright"])
    p.setColor(R.ToolTipBase, c["panel"])
    p.setColor(R.ToolTipText, c["text"])
    p.setColor(R.Highlight, c["accent_bg"])
    p.setColor(R.HighlightedText, c["accent_hi"])
    p.setColor(R.Link, c["accent_hi"])
    p.setColor(R.LinkVisited, c["accent"])
    p.setColor(R.PlaceholderText, c["muted"])
    p.setColor(R.Light, c["border_hi"])
    p.setColor(R.Midlight, c["border"])
    p.setColor(R.Mid, c["border"])
    p.setColor(R.Dark, c["bg"])
    p.setColor(R.Shadow, QColor("#000000"))
    for role in (R.Text, R.ButtonText, R.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c["disabled"])
    return p


# ---------------------------------------------------------------- Stylesheet

_TOKEN = re.compile(r"@([a-z_]+)")


def _tinted_icon_dir(theme: str) -> Path:
    """Legt die Lucide-SVGs, die das Stylesheet als url() braucht (Pfeile der
    Spin- und Auswahlfelder), in der Thema-Farbe ab. Qt-Stylesheets kennen
    kein ``currentColor``."""
    out = Path(tempfile.gettempdir()) / "completionist-pro-icons" / theme
    color = tokens(theme)["muted"]
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name in ("chevron-up", "chevron-down", "x"):
            svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", color)
            target = out / f"{name}.svg"
            if not target.is_file() or target.read_text(encoding="utf-8") != svg:
                target.write_text(svg, encoding="utf-8")
    except OSError:
        pass
    return out


def stylesheet(theme: str = "dark") -> str:
    t = dict(tokens(theme))
    t["icons"] = _tinted_icon_dir(theme).as_posix()
    try:
        qss = QSS_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    return _TOKEN.sub(lambda m: t.get(m.group(1), m.group(0)), qss)


def apply(app, theme: str = "dark", extra: str = "") -> None:
    """Fusion-Stil, Palette, Schrift und Stylesheet fuer die ganze Anwendung."""
    global _theme
    _theme = "light" if theme == "light" else "dark"
    app.setStyle("Fusion")
    app.setPalette(palette(_theme))
    font = QFont(app.font())
    font.setFamilies(["Segoe UI", "Inter", font.family()])
    font.setPointSizeF(9.75)  # 13 px bei 96 dpi
    app.setFont(font)
    app.setStyleSheet(stylesheet(_theme) + extra)


# ---------------------------------------------------------------- Icons


class _LucideEngine(QIconEngine):
    """Zeichnet ein Lucide-SVG in der Farbe, die zum Zustand und zum aktuellen
    Thema passt: Ruhe gedaempft, Hover hell, aktiv/ausgewaehlt Smaragd.
    Nach einem Themawechsel stimmen die Farben deshalb ohne neue Icons."""

    def __init__(self, name: str, svg: bytes, color: str | None) -> None:
        super().__init__()
        self._name = name
        self._svg = svg
        self._color = color
        self._cache: dict[tuple, QPixmap] = {}

    def _color_for(self, mode: QIcon.Mode, state: QIcon.State) -> str:
        t = tokens()
        if mode == QIcon.Mode.Disabled:
            return t["disabled"]
        if self._color:
            return self._color
        if state == QIcon.State.On or mode == QIcon.Mode.Selected:
            return t["accent_hi"]
        if mode == QIcon.Mode.Active:
            return t["bright"]
        return t["muted"]

    def _renderer(self, color: str) -> QSvgRenderer:
        return QSvgRenderer(QByteArray(self._svg.replace(b"currentColor", color.encode())))

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        self._renderer(self._color_for(mode, state)).render(painter, rect.toRectF())

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State, scale: float) -> QPixmap:  # noqa: N802
        color = self._color_for(mode, state)
        key = (size.width(), size.height(), color, scale)
        pm = self._cache.get(key)
        if pm is None:
            pm = QPixmap(QSize(round(size.width() * scale), round(size.height() * scale)))
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._renderer(color).render(painter)
            painter.end()
            pm.setDevicePixelRatio(scale)
            self._cache[key] = pm
        return pm

    def actualSize(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QSize:  # noqa: N802
        return size

    def clone(self) -> QIconEngine:
        engine = _LucideEngine(self._name, self._svg, self._color)
        _engines.append(engine)
        return engine

    def key(self) -> str:
        return "completionist-lucide"

    def iconName(self) -> str:  # noqa: N802
        return self._name


_icons: dict[tuple[str, str | None], QIcon] = {}
_engines: list[_LucideEngine] = []  # Python-Engines am Leben halten (Qt uebernimmt sie nicht)


def icon(name: str, color: str | None = None) -> QIcon:
    """Lucide-Icon ``name`` (Dateiname ohne .svg). Ohne ``color`` folgt die
    Farbe Zustand und Thema; fehlt die Datei, kommt ein leeres Icon zurueck
    (der Knopf zeigt dann seinen Text)."""
    key = (name, color)
    cached = _icons.get(key)
    if cached is not None:
        return cached
    try:
        svg = (ICON_DIR / f"{name}.svg").read_bytes()
    except OSError:
        print(f"Completionist Pro: Icon '{name}' fehlt in {ICON_DIR}", file=sys.stderr)
        return QIcon()
    engine = _LucideEngine(name, svg, color)
    _engines.append(engine)
    ico = QIcon(engine)
    _icons[key] = ico
    return ico


def file_icon(kind: str) -> QIcon:
    """Farbiges Dateityp-Icon fuer Baeume (md, pdf, img, txt)."""
    name = {"img": "file-image", "txt": "file"}.get(kind, "file-text")
    return icon(name, FILE_COLORS.get(kind))

