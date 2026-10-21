"""Fenster "Über CompletionistQR": Version, Copyright, Lizenz, Fremdkomponenten."""
from __future__ import annotations

import os
import webbrowser

import customtkinter as ctk

from .. import __version__


def _legal():
    # core.legal liegt im Suite-Paket "core" (ohne Qt); fehlt es, kurze Fassung
    try:
        from core import legal
        return legal
    except ImportError:
        return None


class AboutWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Über CompletionistQR")
        self.geometry("620x560")
        self.transient(master)
        legal = _legal()
        copyright_ = legal.COPYRIGHT if legal else "© 2026 Mike-Dominique Horch (Completionist Library)"
        copyright_ += "\nKontakt: " + (legal.CONTACT if legal else "mail@mike-horch.de")

        ctk.CTkLabel(self, text="CompletionistQR", font=ctk.CTkFont(size=22, weight="bold"),
                     anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(self, text=f"Version {__version__}  ·  Gestaltete QR-Codes\n{copyright_}",
                     anchor="w", justify="left").pack(fill="x", padx=18, pady=(2, 8))

        box = ctk.CTkTextbox(self, wrap="word")
        box.pack(fill="both", expand=True, padx=14, pady=4)
        text = ""
        if legal:
            text += f"Lizenz\n{legal.LICENSE_SUMMARY}\n{legal.LICENSE_URL}\n\n"
            text += legal.notices_text()
        box.insert("1.0", text)
        box.configure(state="disabled")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(6, 14))
        if legal:
            ctk.CTkButton(bar, text="Lizenz im Browser", width=150,
                          command=lambda: webbrowser.open(legal.LICENSE_URL)).pack(side="left")
            folder = legal.licenses_dir()
            if folder:
                ctk.CTkButton(bar, text="Lizenzordner öffnen", width=150,
                              command=lambda: os.startfile(str(folder))).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Schließen", width=110, command=self.destroy).pack(side="right")
        self.after(100, self.lift)
