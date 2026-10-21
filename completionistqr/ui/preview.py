"""Live-Vorschau: rendert verzögert (debounced) in einem Hintergrund-Thread und prüft
dabei die Lesbarkeit des Codes."""
from __future__ import annotations

import threading
from dataclasses import replace

import customtkinter as ctk
from PIL import Image

from ..core import export
from ..core.config import QRDesign
from ..core.geometry import build_scene, load_logo
from ..core.render_pil import render_scene

PREVIEW_PX = 520
DEBOUNCE_MS = 250


def _checkerboard(size: tuple[int, int], cell: int = 12) -> Image.Image:
    img = Image.new("RGBA", size, (255, 255, 255, 255))
    dark = Image.new("RGBA", (cell, cell), (222, 222, 222, 255))
    for y in range(0, size[1], cell):
        for x in range((y // cell) % 2 * cell, size[0], cell * 2):
            img.paste(dark, (x, y))
    return img


class PreviewPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=12)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.image_label = ctk.CTkLabel(self, text="", width=PREVIEW_PX, height=PREVIEW_PX)
        self.image_label.grid(row=0, column=0, padx=20, pady=(20, 8))
        self.info = ctk.CTkLabel(self, text="", text_color=("gray35", "gray65"))
        self.info.grid(row=1, column=0)
        self.status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13, weight="bold"),
                                   wraplength=PREVIEW_PX)
        self.status.grid(row=2, column=0, pady=(2, 18))

        self._pending = None
        self._generation = 0
        self._logo_cache: tuple[str, Image.Image | None] = ("", None)
        self._ctk_image = None
        self.readable: bool | None = None  # Ergebnis der letzten Scan-Pruefung

    # ------------------------------------------------------------------ öffentlich

    def request(self, design: QRDesign) -> None:
        """Plant eine Neuberechnung; schnelle Folgeänderungen werden zusammengefasst."""
        if self._pending:
            self.after_cancel(self._pending)
        snapshot = replace(design)
        self._pending = self.after(DEBOUNCE_MS, lambda: self._start(snapshot))

    # ------------------------------------------------------------------ intern

    def _logo(self, path: str) -> Image.Image | None:
        if self._logo_cache[0] != path:
            self._logo_cache = (path, load_logo(path))
        return self._logo_cache[1]

    def _start(self, design: QRDesign) -> None:
        self._pending = None
        self._generation += 1
        gen = self._generation
        logo = self._logo(design.logo_path)
        threading.Thread(target=self._work, args=(gen, design, logo), daemon=True).start()

    def _work(self, gen: int, design: QRDesign, logo) -> None:
        try:
            scene = build_scene(design, logo)
            longest = max(scene.width, scene.height)
            width_px = round(PREVIEW_PX * scene.width / longest)
            img = render_scene(scene, width_px, supersample=2)
            readable = export.decode(img) == (design.payload or " ")
            result = (img, scene, readable, None)
        except Exception as exc:  # Darstellungsfehler nie die App abstürzen lassen
            result = (None, None, False, exc)
        self.after(0, lambda: self._show(gen, design, *result))

    def _show(self, gen: int, design: QRDesign, img, scene, readable: bool, error) -> None:
        if gen != self._generation:
            return  # Inzwischen wurde schon eine neuere Vorschau angefordert
        self.readable = None if error is not None else readable
        if error is not None:
            self.status.configure(text=f"Fehler bei der Darstellung: {error}",
                                  text_color=("#B91C1C", "#F87171"))
            return
        if design.transparent_bg:  # Schachbrett zeigt, wo das Bild durchsichtig ist
            shown = _checkerboard(img.size)
            shown.alpha_composite(img)
        else:
            shown = img
        self._ctk_image = ctk.CTkImage(light_image=shown, dark_image=shown, size=img.size)
        self.image_label.configure(image=self._ctk_image)

        m = scene.matrix
        self.info.configure(text=f"Version {m.version}  ·  {m.size}×{m.size} Module  ·  "
                                 f"Fehlerkorrektur {design.ecc}")
        if readable:
            self.status.configure(text="✓  Scan-Prüfung bestanden – der Code ist lesbar",
                                  text_color=("#15803D", "#4ADE80"))
        else:
            tips = []
            if design.logo_path and design.logo_size > 0.2:
                tips.append("Logo verkleinern")
            if design.ecc != "H" and design.logo_path:
                tips.append("Fehlerkorrektur auf H stellen")
            tips.append("Kontrast erhöhen oder eckigere Augen wählen")
            self.status.configure(text="⚠  Scan-Prüfung nicht bestanden – " + ", ".join(tips),
                                  text_color=("#B45309", "#FBBF24"))
