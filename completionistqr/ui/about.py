"""Fenster "Über …": Version, Copyright, Lizenz, Fremdkomponenten, Impressum.

Gemeinsam fuer CompletionistQR und CompletionistQR Online (Name, Version, Bild und Icon je App)."""
from __future__ import annotations

import os
import re
import tkinter as tk
import webbrowser
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from .. import __version__
from ..core import fonts

IMAGE_SIZE = 280  # Kantenlaenge des App-Bildes links neben den Reitern
LINK_COLOR = ("#1f6aa5", "#5aa9e6")  # hell, dunkel
# Webadressen und E-Mail-Adressen; Satzzeichen am Ende gehoeren nicht dazu
LINK_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+[^\s<>\"'()\[\].,;:!?]|[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _target(link: str) -> str:
    return link if link.startswith("http") else "mailto:" + link


def _open(link: str) -> None:
    webbrowser.open(_target(link))


def _legal():
    # core.legal liegt im Suite-Paket "core" (ohne Qt); fehlt es, kurze Fassung
    try:
        from core import legal
        return legal
    except ImportError:
        return None


class AboutWindow(ctk.CTkToplevel):
    def __init__(self, master, name: str = "CompletionistQR", version: str = __version__,
                 subtitle: str = "Gestaltete QR-Codes", image: Path | None = None,
                 icon: Path | None = None):
        super().__init__(master)
        self.title(f"Über {name}")
        self._icon_file = icon or fonts.assets_dir() / "icon.ico"
        self.geometry("940x580")
        self.transient(master)
        legal = _legal()
        copyright_ = legal.COPYRIGHT if legal else "© 2026 Mike-Dominique Horch (Completionist Library)"
        contact = legal.CONTACT if legal else "kontakt@completionist-library.de"
        self._set_icon_later()

        # Unten zuerst packen, damit die Knoepfe bei kleinem Fenster sichtbar bleiben
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=14, pady=(6, 14))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        # Das App-Bild steht links neben den Reitern und bleibt bei jedem Reiter sichtbar
        try:
            img = Image.open(image or fonts.assets_dir() / "splash.jpg")
            self._art = ctk.CTkImage(light_image=img, dark_image=img, size=(IMAGE_SIZE, IMAGE_SIZE))
            ctk.CTkLabel(body, image=self._art, text="").pack(side="left", anchor="n",
                                                             padx=(14, 4), pady=(16, 4))
        except OSError:
            pass
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(right, text=name, font=ctk.CTkFont(size=22, weight="bold"),
                     anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(right, text=f"Version {version}  ·  {subtitle}\n{copyright_}",
                     anchor="w", justify="left").pack(fill="x", padx=18, pady=(2, 0))
        line = ctk.CTkFrame(right, fg_color="transparent")
        line.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(line, text="Kontakt:").pack(side="left")
        mail = ctk.CTkLabel(line, text=contact, text_color=LINK_COLOR, cursor="hand2",
                            font=ctk.CTkFont(underline=True))
        mail.pack(side="left", padx=(4, 0))
        mail.bind("<Button-1>", lambda _e: _open(contact))

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
            _link_up(box, text)
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

    def _set_icon_later(self) -> None:
        # CTkToplevel setzt unter Windows nach 200 ms sein eigenes Icon -- danach
        # unseres, sonst stuende im Fenster "Über" das CustomTkinter-Logo.
        self.after(250, self._set_icon)

    def _set_icon(self) -> None:
        icon = Path(self._icon_file)
        try:
            self.iconbitmap(str(icon))
            return
        except tk.TclError:
            pass  # .ico kennt Tk nur unter Windows
        try:
            from PIL import ImageTk

            self._icon = ImageTk.PhotoImage(Image.open(icon.with_name("icon_source.png")))
            self.iconphoto(False, self._icon)
        except (OSError, tk.TclError):
            pass


def _link_up(box: ctk.CTkTextbox, text: str) -> None:
    """Webadressen und E-Mail-Adressen in ``box`` klickbar machen."""
    for i, m in enumerate(LINK_RE.finditer(text)):
        tag = f"link{i}"
        box.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        box.tag_config(tag, foreground=LINK_COLOR[ctk.get_appearance_mode() == "Dark"],
                       underline=True)
        box.tag_bind(tag, "<Button-1>", lambda _e, link=m.group(): _open(link))
        box.tag_bind(tag, "<Enter>", lambda _e: box.configure(cursor="hand2"))
        box.tag_bind(tag, "<Leave>", lambda _e: box.configure(cursor=""))
