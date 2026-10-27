"""Fenster "QR-Code gestalten" -- der Gestalter von CompletionistQR mit dem Kurzlink.

Kein eigener Nachbau: Bedienleiste, Vorschau, Vorlagen, Logo, Beschriftung, Export (PNG,
SVG, PDF, Zwischenablage), Scan-Pruefung und das Fenster "Über" kommen aus dem Paket
completionistqr (completionistqr/ui/designer.py). Was CompletionistQR kann, kann CompletionistQR Online
damit automatisch auch. Fest steht nur der Inhalt: die kurze Adresse des Links.

Das Design merkt sich CompletionistQR Online je Link (settings.json, "designs"); ein neuer
Link beginnt mit dem zuletzt benutzten Design.
"""
from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

from . import __version__, settings

try:
    import completionistqr  # noqa: F401
except ImportError:  # aus dem Quellcode gestartet: das Paket liegt eine Ebene ueber CompletionistQR-Online
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from completionistqr.ui.designer import DesignerMixin, design_from, register_fonts  # noqa: E402
from completionistqr.ui import style  # noqa: E402
from completionistqr.ui.style import apply_theme  # noqa: E402

__all__ = ["DesignWindow", "about_info", "apply_theme", "register_fonts", "style"]

HINT = ("Im Code steht die kurze Adresse deines CompletionistQR-Online-Servers. Sie zählt jeden Scan und "
        "leitet zum Ziel weiter – das Ziel lässt sich jederzeit ändern, der gedruckte Code "
        "bleibt gültig.")


def assets_dir() -> Path:
    # In der gepackten App liegen die Assets unter sys._MEIPASS
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"


def about_info() -> dict:
    return {"name": "CompletionistQR Online", "version": __version__,
            "subtitle": "QR-Codes mit Scan-Statistik",
            "image": assets_dir() / "icon_source.png", "icon": assets_dir() / "icon.ico"}


class DesignWindow(DesignerMixin, ctk.CTkToplevel):
    """Wird einmal aufgebaut und dann wiederverwendet: der Aufbau der Bedienleiste dauert
    knapp eine Sekunde. Schliessen versteckt das Fenster nur, ``show_link`` zeigt es fuer
    einen (anderen) Link wieder."""

    def __init__(self, master, link, prefs: dict):
        super().__init__(master)
        self.link = link
        self.prefs = prefs  # das Einstellungs-dict des Hauptfensters (wird mitgespeichert)
        self.about_info = about_info()
        self.geometry("1180x820")
        self.minsize(1000, 700)
        self.build_designer(self._saved_design(link), fixed_payload=link.url, fixed_hint=HINT)
        self._show(link)
        self.protocol("WM_DELETE_WINDOW", self.close)
        # CTkToplevel setzt unter Windows nach 200 ms sein eigenes Icon
        self.after(250, self._set_icon)
        self.after(100, self.lift)

    def _saved_design(self, link):
        return design_from((self.prefs.get("designs") or {}).get(link.code) or self.prefs.get("design"))

    def _show(self, link) -> None:
        self.link = link
        self.export_name = f"qr-{link.code}"
        self.title(f"QR-Code gestalten – {link.title}")
        self.controls.set_fixed_payload(link.url)
        self.controls.refresh()
        self.changed()

    def show_link(self, link) -> None:
        """Fenster (wieder) zeigen -- fuer denselben oder einen anderen Link."""
        if self.winfo_viewable() and self.link.code != link.code:
            self.remember()  # Design des bisherigen Links nicht verlieren
        if self.link.code != link.code or not self.winfo_viewable():
            self.design = self._saved_design(link)
        self._show(link)
        self.deiconify()
        self.lift()
        self.focus_force()

    def _set_icon(self) -> None:
        try:
            self.iconbitmap(str(assets_dir() / "icon.ico"))
        except Exception:  # z. B. unter Linux: .ico nicht als Fenstersymbol
            pass

    def load_setting(self, key: str, default=None):
        return self.prefs.get(key, default)

    def store_setting(self, key: str, value) -> None:
        self.prefs[key] = value
        settings.save(self.prefs)

    def remember(self) -> None:
        design = self.design.to_dict()
        self.prefs.setdefault("designs", {})[self.link.code] = design
        self.prefs["design"] = design
        settings.save(self.prefs)

    def close(self) -> None:
        self.remember()
        self.withdraw()
