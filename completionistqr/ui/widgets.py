"""Wiederverwendbare Bedienelemente: Farbwähler, Regler mit Wertanzeige, Auswahlmenüs."""
from __future__ import annotations

import re
from tkinter import colorchooser
from typing import Callable

import customtkinter as ctk

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def section(parent, title: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
    lbl.pack(fill="x", padx=4, pady=(14, 2))
    return lbl


def row(parent, label: str) -> ctk.CTkFrame:
    """Zeile mit Beschriftung links; das Bedienelement kommt in die rechte Spalte."""
    fr = ctk.CTkFrame(parent, fg_color="transparent")
    fr.pack(fill="x", padx=4, pady=3)
    fr.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(fr, text=label, width=118, anchor="w").grid(row=0, column=0, sticky="w")
    return fr


class ColorPicker(ctk.CTkFrame):
    """Farbfläche (öffnet den Windows-Farbdialog) plus Hex-Eingabefeld."""

    def __init__(self, master, color: str, command: Callable[[str], None]):
        super().__init__(master, fg_color="transparent")
        self._command = command
        self.swatch = ctk.CTkButton(self, text="", width=34, height=26, corner_radius=6,
                                    border_width=1, border_color=("#94A3B8", "#334250"),
                                    command=self._pick)
        self.swatch.pack(side="left")
        self.entry = ctk.CTkEntry(self, width=90)
        self.entry.pack(side="left", padx=(8, 0))
        self.entry.bind("<Return>", self._typed)
        self.entry.bind("<FocusOut>", self._typed)
        self.set(color)

    def set(self, color: str) -> None:
        self._color = color.upper()
        self.swatch.configure(fg_color=self._color, hover_color=self._color)
        self.entry.delete(0, "end")
        self.entry.insert(0, self._color)

    def _pick(self) -> None:
        _, hex_color = colorchooser.askcolor(color=self._color, parent=self.winfo_toplevel())
        if hex_color:
            self.set(hex_color)
            self._command(self._color)

    def _typed(self, _event=None) -> None:
        value = self.entry.get().strip()
        if not value.startswith("#"):
            value = "#" + value
        if _HEX.match(value) and value.upper() != self._color:
            self.set(value)
            self._command(self._color)
        elif not _HEX.match(value):
            self.set(self._color)


class ValueSlider(ctk.CTkFrame):
    """Regler mit Wertanzeige; `fmt` formatiert den Wert für die Anzeige."""

    def __init__(self, master, from_: float, to: float, value: float,
                 command: Callable[[float], None], steps: int | None = None,
                 fmt: Callable[[float], str] = lambda v: f"{v:.0f}"):
        super().__init__(master, fg_color="transparent")
        self._command, self._fmt = command, fmt
        self.grid_columnconfigure(0, weight=1)
        self.slider = ctk.CTkSlider(self, from_=from_, to=to, number_of_steps=steps,
                                    command=self._moved)
        self.slider.grid(row=0, column=0, sticky="ew")
        self.label = ctk.CTkLabel(self, width=48, anchor="e")
        self.label.grid(row=0, column=1, padx=(6, 0))
        self.set(value)

    def set(self, value: float) -> None:
        self.slider.set(value)
        self.label.configure(text=self._fmt(value))

    def _moved(self, value: float) -> None:
        self.label.configure(text=self._fmt(value))
        self._command(value)


class Choice(ctk.CTkOptionMenu):
    """Auswahlmenü, das intern Schlüssel verwendet, aber deutsche Bezeichnungen zeigt."""

    def __init__(self, master, labels: dict[str, str], value: str,
                 command: Callable[[str], None], **kw):
        self._labels = labels
        self._keys = {v: k for k, v in labels.items()}
        self._cb = command
        super().__init__(master, values=list(labels.values()), command=self._chosen,
                         dynamic_resizing=False, **kw)
        self.set_key(value)

    def set_key(self, key: str) -> None:
        self.set(self._labels.get(key, next(iter(self._labels.values()))))

    def _chosen(self, label: str) -> None:
        self._cb(self._keys[label])
