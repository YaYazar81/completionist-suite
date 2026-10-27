"""Hauptfenster von CompletionistQR."""
from __future__ import annotations

import ctypes
import json
import sys

import customtkinter as ctk

from . import __version__
from .core import fonts
from .core.userdir import user_dir
from .ui import style
from .ui.designer import DesignerMixin, design_from, register_fonts


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


class CompletionistQRApp(DesignerMixin, ctk.CTk):
    about_info = {"name": "CompletionistQR", "version": __version__,
                  "subtitle": "Gestaltete QR-Codes"}

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
        self.build_designer(design_from(saved.get("design")))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if isinstance(saved.get("content"), dict):
            self.controls.restore_content(saved["content"])
        self.controls.refresh()
        self.changed()
        if self._splash is not None:
            self._splash.finish(self.deiconify)

    def load_setting(self, key: str, default=None):
        return _load_settings().get(key, default)

    def store_setting(self, key: str, value) -> None:
        _save_settings({**_load_settings(), key: value})

    def _on_close(self) -> None:
        _save_settings({**_load_settings(), "design": self.design.to_dict(),
                        "content": self.controls.content_state()})
        self.destroy()


def main() -> None:
    if sys.platform == "win32":
        try:  # eigenes Taskleistensymbol statt des Python-Symbols
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CompletionistQR.App")
        except Exception:
            pass
    ctk.set_appearance_mode(_load_settings().get("appearance", "system"))
    # Completionist Pro (Schiefer & Smaragd) wie CompletionistMD und -PDF
    style.apply_theme()
    register_fonts()
    CompletionistQRApp(splash=True).mainloop()
