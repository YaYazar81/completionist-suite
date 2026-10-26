"""Completionist Pro fuer CompletionistQR: Farben, ctk-Theme und Lucide-Icons.

Die Tokens entsprechen core/design.py (Schiefer & Smaragd), hier als
(hell, dunkel)-Paare fuer customtkinter. core/design.py selbst bleibt aussen
vor: CompletionistQR wird ohne Qt gebaut (build_exe.py, EXCLUDES_QR).
"""
from __future__ import annotations

from functools import lru_cache

import customtkinter as ctk
from PIL import Image

from ..core.fonts import assets_dir

THEME_FILE = assets_dir() / "theme" / "completionist_pro.json"
ICON_DIR = assets_dir() / "icons"

# (hell, dunkel) -- gleiche Werte wie LIGHT/DARK in core/design.py
BG = ("#F1F5F9", "#121619")
PANEL = ("#FFFFFF", "#1C2329")
INPUT = ("#F8FAFC", "#161B20")
BORDER = ("#CBD5E1", "#27323D")
HOVER = ("#E2E8F0", "#222C35")
TEXT = ("#0F172A", "#E2E8F0")
MUTED = ("#475569", "#94A3B8")
ACCENT_BG = ("#D1FAE5", "#112C27")
ACCENT = ("#059669", "#10B981")
ACCENT_HI = ("#047857", "#34D399")
WARN = ("#B45309", "#FBBF24")
DANGER = ("#B91C1C", "#F87171")

# Icons, die tools/make_qr_icons.py als PNG rendert
ICONS = ("info", "image", "clipboard-paste", "trash-2", "download", "clipboard-copy",
         "file-spreadsheet", "cloud-upload", "save", "x")


def secondary() -> dict:
    """Zurueckhaltender Knopf: nur Rahmen, Hover in Schiefer."""
    return dict(fg_color="transparent", border_width=1, border_color=BORDER,
                hover_color=HOVER, text_color=TEXT)


def primary() -> dict:
    """Hauptaktion: Smaragd-Flaeche mit Akzentkante (wie aktive Werkzeuge in MD/PDF)."""
    return dict(fg_color=ACCENT_BG, hover_color=("#A7F3D0", "#16382F"), border_width=1,
                border_color=ACCENT, text_color=ACCENT_HI)


@lru_cache(maxsize=None)
def icon(name: str, accent: bool = False, size: int = 18) -> ctk.CTkImage | None:
    """Lucide-Icon als CTkImage (hell/dunkel); ``None``, falls die Datei fehlt."""
    prefix = "accent_" if accent else ""
    try:
        light = Image.open(ICON_DIR / f"{name}_{prefix}light.png")
        dark = Image.open(ICON_DIR / f"{name}_{prefix}dark.png")
    except OSError:
        return None
    return ctk.CTkImage(light_image=light, dark_image=dark, size=(size, size))


def install_focus_ring(root) -> None:
    """Smaragd-Rahmen um das Eingabefeld mit dem Fokus (Entry, Textbox, ComboBox)."""

    def owner(widget):
        w = widget
        for _ in range(3):  # tk-Entry -> CTkEntry bzw. Canvas-Ebenen dazwischen
            w = getattr(w, "master", None)
            if isinstance(w, (ctk.CTkEntry, ctk.CTkTextbox, ctk.CTkComboBox)):
                return w
        return None

    def focus(event, on: bool):
        w = owner(event.widget)
        if w is not None and w.cget("border_width"):
            try:
                w.configure(border_color=ACCENT if on else BORDER)
            except Exception:
                pass

    root.bind_all("<FocusIn>", lambda e: focus(e, True), add="+")
    root.bind_all("<FocusOut>", lambda e: focus(e, False), add="+")
