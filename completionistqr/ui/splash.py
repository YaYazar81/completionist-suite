"""Startbild (Splash-Screen): steht rund 1,2 Sekunden, solange das Hauptfenster entsteht."""
from __future__ import annotations

import time
import tkinter as tk

from PIL import Image, ImageTk

from ..core import fonts

DURATION_MS = 1200
SIZE = 520  # Kantenlaenge in Bildschirmpixeln (bei 100 % Skalierung)


class Splash(tk.Toplevel):
    """Rahmenloses Fenster mit dem Startbild, mittig auf dem Bildschirm."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        scale = max(1.0, master.winfo_fpixels("1i") / 96)
        side = round(SIZE * scale)
        img = Image.open(fonts.assets_dir() / "splash.jpg").convert("RGB")
        self._photo = ImageTk.PhotoImage(img.resize((side, side), Image.LANCZOS))
        tk.Label(self, image=self._photo, borderwidth=0, highlightthickness=0).pack()
        x = (self.winfo_screenwidth() - side) // 2
        y = (self.winfo_screenheight() - side) // 2
        self.geometry(f"{side}x{side}+{x}+{y}")
        self.update()
        self._shown_at = time.monotonic()

    def finish(self, on_done) -> None:
        """Schliesst das Startbild nach Ablauf der Zeit und ruft dann on_done auf."""
        elapsed = int((time.monotonic() - self._shown_at) * 1000)

        def done() -> None:
            self.destroy()
            on_done()

        self.after(max(0, DURATION_MS - elapsed), done)
