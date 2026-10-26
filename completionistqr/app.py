"""Hauptfenster von CompletionistQR."""
from __future__ import annotations

import ctypes
import json
import os
import sys

import customtkinter as ctk

from . import __version__
from .core import fonts
from .core.config import QRDesign
from .core.userdir import user_dir
from .ui import dropfiles
from .ui.controls import LOGO_SUFFIXES, Controls
from .ui.preview import PreviewPanel


APPEARANCE = {"Hell": "light", "System": "system", "Dunkel": "dark"}


def _settings_file():
    return user_dir() / "settings.json"


def _load_settings() -> dict:
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict) -> None:
    try:
        path = _settings_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _register_fonts() -> None:
    """Macht die mitgelieferten Schriften für die Tk-Oberfläche (Vorschau) verfügbar."""
    for family in fonts.families():
        path, _ = fonts.font_file(family)
        if path.is_file():
            try:
                ctk.FontManager.load_font(str(path))
            except Exception:
                pass


class CompletionistQRApp(ctk.CTk):
    def __init__(self, splash: bool = False):
        super().__init__()
        # Startbild zeigen, solange das Hauptfenster (versteckt) aufgebaut wird
        self._splash = None
        if splash:
            self.withdraw()
            try:
                from .ui.splash import Splash

                self._splash = Splash(self)
            except Exception:
                self.deiconify()
        self.title(f"CompletionistQR {__version__}")
        self.geometry("1180x820")
        self.minsize(1000, 700)
        icon = fonts.assets_dir() / "icon.ico"
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except Exception:
                pass

        # Letztes Design vom vorigen Start (Inhalt kommt unten ueber die Formularwerte)
        saved = _load_settings()
        try:
            self.design = QRDesign.from_dict(saved.get("design") or {})
        except (TypeError, ValueError):
            self.design = QRDesign()
        if self.design.logo_path and not os.path.isfile(self.design.logo_path):
            self.design.logo_path = ""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.controls = Controls(self, self)
        self.controls.grid(row=0, column=0, sticky="nsw", padx=(14, 7), pady=14)
        self.preview = PreviewPanel(self)
        self.preview.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=14)

        # Umschalter für das Erscheinungsbild der Oberfläche (oben rechts über der Vorschau)
        current = _load_settings().get("appearance", "system")
        self.appearance = ctk.CTkSegmentedButton(self.preview, values=list(APPEARANCE),
                                                 command=self._appearance_changed)
        self.appearance.set(next((k for k, v in APPEARANCE.items() if v == current), "System"))
        self.appearance.place(relx=1.0, x=-60, y=16, anchor="ne")
        ctk.CTkButton(self.preview, text="ⓘ", width=34, command=self.show_about).place(
            relx=1.0, x=-16, y=16, anchor="ne")
        self.bind("<F1>", lambda _e: self.show_about())

        self.bind("<Control-s>", lambda _e: self.controls.save())
        # Strg+C / Strg+V nur, wenn kein Textfeld den Fokus hat -- dort kopieren sie Text
        self.bind_all("<Control-c>", self._on_copy, add="+")
        self.bind_all("<Control-v>", self._on_paste, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Bilder (Logo) und CSV-Listen (Stapel-Export) aus dem Explorer ins Fenster ziehen
        self.after(200, lambda: dropfiles.enable(self, self._on_drop))

        if isinstance(saved.get("content"), dict):
            self.controls.restore_content(saved["content"])
        self.controls.refresh()
        self.changed()
        if self._splash is not None:
            self._splash.finish(self.deiconify)

    def show_about(self) -> None:
        from .ui.about import AboutWindow

        AboutWindow(self)

    @staticmethod
    def _typing(widget) -> bool:
        return widget is not None and widget.winfo_class() in ("Entry", "Text", "TEntry")

    def _on_copy(self, event):
        if self._typing(event.widget):
            return None
        self.controls.copy()
        return "break"

    def _on_paste(self, event):
        if self._typing(event.widget):
            return None
        if self.controls.paste_logo():
            self.controls.set("Logo")
            return "break"
        return None

    def _on_drop(self, paths: list[str]) -> None:
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in (".csv", ".txt"):
                self.controls.set("Export")
                self.controls.batch_export(p)
                return
            if ext in LOGO_SUFFIXES:
                self.controls._set_logo(p)
                self.controls.set("Logo")
                return

    def _on_close(self) -> None:
        _save_settings({**_load_settings(), "design": self.design.to_dict(),
                        "content": self.controls.content_state()})
        self.destroy()

    def _appearance_changed(self, label: str) -> None:
        mode = APPEARANCE[label]
        ctk.set_appearance_mode(mode)
        _save_settings({**_load_settings(), "appearance": mode})

    def changed(self) -> None:
        self.preview.request(self.design)

    def apply_preset(self, style: dict) -> None:
        self.design = self.design.apply_style(style)
        self.controls.refresh()
        self.changed()


def main() -> None:
    if sys.platform == "win32":
        try:  # eigenes Taskleistensymbol statt des Python-Symbols
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CompletionistQR.App")
        except Exception:
            pass
    ctk.set_appearance_mode(_load_settings().get("appearance", "system"))
    ctk.set_default_color_theme("blue")
    _register_fonts()
    CompletionistQRApp(splash=True).mainloop()
