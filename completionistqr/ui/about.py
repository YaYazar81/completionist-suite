"""Fenster "Über CompletionistQR": Version, Copyright, Lizenz, Fremdkomponenten, Impressum."""
from __future__ import annotations

import os
import webbrowser

import customtkinter as ctk
from PIL import Image

from .. import __version__
from ..core import fonts

IMAGE_SIZE = 280  # Kantenlaenge des App-Bildes links neben den Reitern


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
        self.geometry("940x580")
        self.transient(master)
        legal = _legal()
        copyright_ = legal.COPYRIGHT if legal else "© 2026 Mike-Dominique Horch (Completionist Library)"
        copyright_ += "\nKontakt: " + (legal.CONTACT if legal else "kontakt@completionist-library.de")

        # Unten zuerst packen, damit die Knoepfe bei kleinem Fenster sichtbar bleiben
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=14, pady=(6, 14))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        # Das App-Bild steht links neben den Reitern und bleibt bei jedem Reiter sichtbar
        try:
            img = Image.open(fonts.assets_dir() / "splash.jpg")
            self._art = ctk.CTkImage(light_image=img, dark_image=img, size=(IMAGE_SIZE, IMAGE_SIZE))
            ctk.CTkLabel(body, image=self._art, text="").pack(side="left", anchor="n",
                                                             padx=(14, 4), pady=(16, 4))
        except OSError:
            pass
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(right, text="CompletionistQR", font=ctk.CTkFont(size=22, weight="bold"),
                     anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(right, text=f"Version {__version__}  ·  Gestaltete QR-Codes\n{copyright_}",
                     anchor="w", justify="left").pack(fill="x", padx=18, pady=(2, 8))

        tabs = ctk.CTkTabview(right)
        tabs.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        pages = []
        if legal:
            pages = [("Lizenz", f"Lizenz\n{legal.LICENSE_SUMMARY}\n{legal.LICENSE_URL}\n"),
                     ("Fremdkomponenten", legal.notices_text()),
                     ("Impressum", legal.impressum_text())]
        for name, text in pages:
            box = ctk.CTkTextbox(tabs.add(name), wrap="word")
            box.pack(fill="both", expand=True)
            box.insert("1.0", text)
            box.configure(state="disabled")

        if legal:
            ctk.CTkButton(bar, text="Lizenz im Browser", width=150,
                          command=lambda: webbrowser.open(legal.LICENSE_URL)).pack(side="left")
            folder = legal.licenses_dir()
            if folder:
                ctk.CTkButton(bar, text="Lizenzordner öffnen", width=150,
                              command=lambda: os.startfile(str(folder))).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Schließen", width=110, command=self.destroy).pack(side="right")
        self.after(100, self.lift)
