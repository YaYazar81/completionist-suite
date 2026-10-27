"""Server einrichten: beim ersten Start (und unter „Server …").

Wer noch keinen Server hat, bekommt hier alles fertig: einen zufaelligen API-Schluessel,
die Server-Dateien samt passender config.php in einem Ordner seiner Wahl und die
Anleitung, sie per FTP auf den eigenen Webspace zu laden. Danach prueft „Verbindung
testen", ob unter der Adresse wirklich der Server mit diesem Schluessel antwortet.
Wer schon einen Server hat, traegt nur Adresse und Schluessel ein.
"""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from .server_files import (UPLOAD_HELP, check_connection, default_folder, generate_key,
                           normalize_url, open_folder, write_server_files)

OK, MUTED, ERROR = ("#15803D", "#4ADE80"), ("gray35", "gray65"), ("#B91C1C", "#F87171")


class ServerDialog(ctk.CTkToplevel):
    """Einrichtung des Servers; ``result`` ist danach {"base_url", "api_key"} oder None."""

    def __init__(self, master, base_url: str = "", api_key: str = "", first_start: bool = False):
        super().__init__(master)
        self.title("Server einrichten" if first_start or not api_key else "Server")
        self.resizable(False, False)
        self.result: dict | None = None
        self.folder: Path | None = None
        new = not api_key
        self.mode = ctk.StringVar(value="new" if new else "existing")
        self.url_var = ctk.StringVar(value=base_url or "https://")
        self.key_var = ctk.StringVar(value=api_key or generate_key())

        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=18, pady=16)
        f.grid_columnconfigure(1, weight=1)
        row = 0
        if first_start:
            ctk.CTkLabel(f, text="Willkommen bei CompletionistQR Online", anchor="w",
                         font=ctk.CTkFont(size=18, weight="bold")).grid(
                row=row, column=0, columnspan=3, sticky="w")
            row += 1
            ctk.CTkLabel(f, anchor="w", justify="left", wraplength=560, text_color=MUTED, text=(
                "Die QR-Codes zeigen auf eine kurze Adresse auf deinem eigenen Webspace. Ein kleines "
                "PHP-Programm zählt dort jeden Scan und leitet zum Ziel weiter. Hier richtest du "
                "diesen Server einmalig ein – oder verbindest einen vorhandenen.")).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(2, 10))
            row += 1
        self.switch = ctk.CTkSegmentedButton(f, values=["Neuen Server einrichten", "Vorhandenen verbinden"],
                                             command=self._mode_changed)
        self.switch.set("Neuen Server einrichten" if new else "Vorhandenen verbinden")
        self.switch.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1

        ctk.CTkLabel(f, text="Server-Adresse", anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 10))
        self.url_entry = ctk.CTkEntry(f, textvariable=self.url_var, width=380)
        self.url_entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        row += 1
        self.url_hint = ctk.CTkLabel(f, anchor="w", justify="left", wraplength=560, text_color=MUTED,
                                     text="Unter dieser Adresse wird der Server erreichbar sein, z. B. "
                                          "https://qr.example.de oder https://example.de/qr")
        self.url_hint.grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1
        ctk.CTkLabel(f, text="API-Schlüssel", anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 10))
        self.key_entry = ctk.CTkEntry(f, textvariable=self.key_var, width=380)
        self.key_entry.grid(row=row, column=1, sticky="ew", pady=3)
        self.new_key = ctk.CTkButton(f, text="Neu erzeugen", width=110, fg_color="transparent",
                                     border_width=1, text_color=("gray20", "gray85"),
                                     command=lambda: self.key_var.set(generate_key()))
        self.new_key.grid(row=row, column=2, padx=(8, 0))
        row += 1

        # Schritte fuer einen neuen Server
        self.steps = ctk.CTkFrame(f, fg_color="transparent")
        self.steps.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.steps.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.steps, text="1.  Server-Dateien speichern", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(self.steps, anchor="w", justify="left", wraplength=560, text_color=MUTED,
                     text="Legt index.php, .htaccess, data/ und eine config.php mit dem Schlüssel "
                          "von oben in einen Ordner auf deinem Rechner.").grid(row=1, column=0, sticky="w")
        bar = ctk.CTkFrame(self.steps, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="w", pady=4)
        ctk.CTkButton(bar, text="Server-Dateien speichern …", command=self._save_files).pack(side="left")
        self.open_button = ctk.CTkButton(bar, text="Ordner öffnen", width=110, fg_color="transparent",
                                         border_width=1, text_color=("gray20", "gray85"),
                                         state="disabled", command=lambda: open_folder(self.folder))
        self.open_button.pack(side="left", padx=8)
        self.folder_label = ctk.CTkLabel(self.steps, text="", anchor="w", wraplength=560, justify="left")
        self.folder_label.grid(row=3, column=0, sticky="w")
        ctk.CTkLabel(self.steps, text="2.  Per FTP hochladen", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ctk.CTkLabel(self.steps, text=UPLOAD_HELP, anchor="w", justify="left", wraplength=560,
                     text_color=MUTED).grid(row=5, column=0, sticky="w")
        ctk.CTkLabel(self.steps, text="3.  Verbindung testen und speichern", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=6, column=0, sticky="w", pady=(8, 0))
        row += 1
        self.existing_hint = ctk.CTkLabel(
            f, anchor="w", justify="left", wraplength=560, text_color=MUTED,
            text="Adresse, unter der index.php liegt, und der API-Schlüssel aus der config.php "
                 "dort ('api_key').")
        self.existing_hint.grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))
        row += 1

        self.message = ctk.CTkLabel(f, text="", anchor="w", wraplength=560, justify="left")
        self.message.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        row += 1
        buttons = ctk.CTkFrame(f, fg_color="transparent")
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.test_button = ctk.CTkButton(buttons, text="Verbindung testen", fg_color="transparent",
                                         border_width=1, text_color=("gray20", "gray85"),
                                         command=self._test)
        self.test_button.pack(side="left", padx=(0, 8))
        ctk.CTkButton(buttons, text="Später" if first_start else "Abbrechen", width=90,
                      fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
                      command=self.destroy).pack(side="left")
        ctk.CTkButton(buttons, text="Speichern", width=100, command=self._ok).pack(side="left", padx=(8, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._mode_changed(self.switch.get())

        self.transient(master)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 4
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(100, lambda: (self.grab_set(), self.url_entry.focus_set()))

    # --- Ablauf ---

    def _mode_changed(self, label: str) -> None:
        new = label.startswith("Neuen")
        self.mode.set("new" if new else "existing")
        if new:
            self.steps.grid()
            self.new_key.grid()
            self.existing_hint.grid_remove()
        else:
            self.steps.grid_remove()
            self.new_key.grid_remove()
            self.existing_hint.grid()
        self.key_entry.configure(show="" if new else "•")

    def values(self) -> dict:
        return {"base_url": normalize_url(self.url_var.get()), "api_key": self.key_var.get().strip()}

    def _save_files(self) -> None:
        start = default_folder()
        start.parent.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.askdirectory(parent=self, title="Ordner für die Server-Dateien",
                                         initialdir=str(start.parent))
        if not chosen:
            return
        target = Path(chosen)
        if any(target.iterdir()) and target.name != start.name:
            target = target / start.name  # nicht zwischen fremde Dateien legen
        try:
            self.folder = write_server_files(target, self.values()["api_key"])
        except (OSError, ValueError) as exc:
            self.folder_label.configure(text=str(exc), text_color=ERROR)
            return
        self.folder_label.configure(text=f"✓ Gespeichert in {self.folder}", text_color=OK)
        self.open_button.configure(state="normal")
        open_folder(self.folder)

    def _test(self, then: Callable[[], None] | None = None) -> None:
        v = self.values()
        self.message.configure(text="Prüfe …", text_color=MUTED)
        self.test_button.configure(state="disabled")

        def work():
            error = check_connection(v["base_url"], v["api_key"])
            self.after(0, lambda: self._tested(error, then))
        threading.Thread(target=work, daemon=True).start()

    def _tested(self, error: str, then) -> None:
        if not self.winfo_exists():
            return
        self.test_button.configure(state="normal")
        self.message.configure(text=error or "✓ Verbindung steht, der Schlüssel passt.",
                               text_color=ERROR if error else OK)
        if then and not error:
            then()

    def _ok(self) -> None:
        v = self.values()
        if not v["base_url"].lower().startswith(("http://", "https://")) or v["base_url"] in (
                "http://", "https://"):
            self.message.configure(text="Bitte die Server-Adresse eintragen.", text_color=ERROR)
            return
        if len(v["api_key"]) < 16:
            self.message.configure(text="Der API-Schlüssel braucht mindestens 16 Zeichen.",
                                   text_color=ERROR)
            return
        self.result = v
        self.destroy()

    def ask(self) -> dict | None:
        self.wait_window()
        return self.result
