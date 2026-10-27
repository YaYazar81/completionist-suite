"""Der Gestalter: links die Bedienleiste, rechts die Vorschau.

Dasselbe Fenster-Innere fuer CompletionistQR (Hauptfenster) und QR-Online (Fenster
"QR-Code gestalten" mit dem Kurzlink als festem Inhalt). Wer ``DesignerMixin`` nutzt, ist
ein CTk- bzw. CTkToplevel-Fenster und liefert die Einstellungen ueber ``load_setting``
und ``store_setting``; alles andere -- Vorlagen, Logo, Beschriftung, Export, Scan-Pruefung,
Tastenkuerzel, das Fenster "Über" -- kommt von hier und ist in beiden Apps gleich.
"""
from __future__ import annotations

import os

import customtkinter as ctk

from ..core import fonts
from ..core.config import QRDesign
from . import dropfiles
from .controls import LOGO_SUFFIXES, Controls
from .preview import PreviewPanel

APPEARANCE = {"Hell": "light", "System": "system", "Dunkel": "dark"}


def register_fonts() -> None:
    """Macht die mitgelieferten Schriften für die Tk-Oberfläche (Vorschau) verfügbar."""
    for family in fonts.families():
        path, _ = fonts.font_file(family)
        if path.is_file():
            try:
                ctk.FontManager.load_font(str(path))
            except Exception:
                pass


def design_from(data) -> QRDesign:
    """Gespeichertes Design (dict) -- ein fehlendes Logo wird still entfernt."""
    try:
        design = QRDesign.from_dict(data or {})
    except (TypeError, ValueError):
        design = QRDesign()
    if design.logo_path and not os.path.isfile(design.logo_path):
        design.logo_path = ""
    return design


class DesignerMixin:
    """Baut den Gestalter in das Fenster ``self`` (CTk oder CTkToplevel)."""

    #: Angaben fuer das Fenster "Über" (siehe about.AboutWindow)
    about_info: dict = {}
    #: Vorschlag fuer den Dateinamen beim Speichern
    export_name = "qr-code"

    def load_setting(self, key: str, default=None):
        raise NotImplementedError

    def store_setting(self, key: str, value) -> None:
        raise NotImplementedError

    def build_designer(self, design: QRDesign, fixed_payload: str | None = None,
                       fixed_hint: str = "") -> None:
        self.design = design
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.controls = Controls(self, self, fixed_payload=fixed_payload, fixed_hint=fixed_hint)
        self.controls.grid(row=0, column=0, sticky="nsw", padx=(14, 7), pady=14)
        self.preview = PreviewPanel(self)
        self.preview.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=14)

        # Umschalter für das Erscheinungsbild der Oberfläche (oben rechts über der Vorschau)
        current = self.load_setting("appearance", "system")
        self.appearance = ctk.CTkSegmentedButton(self.preview, values=list(APPEARANCE),
                                                 command=self._appearance_changed)
        self.appearance.set(next((k for k, v in APPEARANCE.items() if v == current), "System"))
        self.appearance.place(relx=1.0, x=-60, y=16, anchor="ne")
        ctk.CTkButton(self.preview, text="ⓘ", width=34, command=self.show_about).place(
            relx=1.0, x=-16, y=16, anchor="ne")
        self.bind("<F1>", lambda _e: self.show_about())

        self.bind("<Control-s>", lambda _e: self.controls.save())
        # Strg+C / Strg+V nur, wenn kein Textfeld den Fokus hat -- dort kopieren sie Text.
        # Am Fenster statt bind_all: ein zweites Fenster (QR-Online) behaelt seine Kuerzel.
        self.bind("<Control-c>", self._on_copy, add="+")
        self.bind("<Control-v>", self._on_paste, add="+")
        # Bilder (Logo) und CSV-Listen (Stapel-Export) aus dem Explorer ins Fenster ziehen
        self.after(200, lambda: dropfiles.enable(self, self._on_drop))

    def show_about(self) -> None:
        from .about import AboutWindow

        AboutWindow(self, **self.about_info)

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
            if ext in (".csv", ".txt") and self.controls.fixed_payload is None:
                self.controls.set("Export")
                self.controls.batch_export(p)
                return
            if ext in LOGO_SUFFIXES:
                self.controls._set_logo(p)
                self.controls.set("Logo")
                return

    def _appearance_changed(self, label: str) -> None:
        mode = APPEARANCE[label]
        ctk.set_appearance_mode(mode)
        self.store_setting("appearance", mode)

    def changed(self) -> None:
        self.preview.request(self.design)

    def apply_preset(self, style: dict) -> None:
        self.design = self.design.apply_style(style)
        self.controls.refresh()
        self.changed()
