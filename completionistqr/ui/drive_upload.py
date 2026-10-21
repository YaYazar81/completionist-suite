"""Datei in Google Drive hochladen, freigeben und den Link in den QR-Code setzen.

Die Anmeldung und die REST-Aufrufe kommen aus ``core/drive.py`` (dieselben wie
beim Vault-Sync von CompletionistMD; die Verknuepfung teilen sich beide Apps).
Hochgeladen wird in einem eigenen Thread, die Oberflaeche zeigt den Fortschritt.
"""
from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from core import drive

FILE_TYPES = [("PDF, Bilder und Videos",
               "*.pdf *.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.m4v *.webm *.avi *.mkv"),
              ("Alle Dateien", "*.*")]
CLIENT_HELP = ("Für das Hochladen braucht die App einmalig eine OAuth-Client-Datei von Google "
               "(client_secret.json):\n\n"
               "1. console.cloud.google.com → Projekt anlegen → „Google Drive API“ aktivieren\n"
               "2. Anmeldedaten → OAuth-Client-ID → Typ „Desktop-App“ → JSON herunterladen\n\n"
               "Ist CompletionistMD schon mit Google Drive verknüpft, ist sie bereits da.\n\n"
               "Jetzt die heruntergeladene Datei wählen?")

OK, MUTED, ERROR = ("#15803D", "#4ADE80"), ("gray35", "gray65"), ("#B91C1C", "#F87171")


def size_text(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} GB".replace(".", ",")


class DriveUploadPanel(ctk.CTkFrame):
    """Knopf „Datei hochladen …“ mit Fortschrittsbalken; meldet den Link an ``on_link``."""

    def __init__(self, master, on_link: Callable[[str], None],
                 store: drive.TokenStore | None = None):
        super().__init__(master, fg_color="transparent")
        self.on_link = on_link
        self.store = store or drive.TokenStore(app_name="CompletionistQR")
        self.cancel = threading.Event()
        self.busy = False
        # Rueckmeldungen aus dem Thread; Tk darf nur der GUI-Thread anfassen
        self._inbox: queue.Queue = queue.Queue()

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=(8, 0))
        self.button = ctk.CTkButton(bar, text="Datei in Google Drive hochladen …",
                                    command=self.pick_and_upload)
        self.button.pack(side="left")
        self.cancel_btn = ctk.CTkButton(bar, text="Abbrechen", width=90, fg_color="transparent",
                                        border_width=1, text_color=("gray20", "gray85"),
                                        command=self.cancel.set)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.status = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=380,
                                   text_color=MUTED)
        self.status.pack(fill="x", padx=4, pady=(4, 0))

    # ------------------------------------------------------------ Ablauf

    def pick_and_upload(self, path: str | None = None) -> None:
        if self.busy:
            return
        path = path or filedialog.askopenfilename(title="Datei für den QR-Code wählen",
                                                  filetypes=FILE_TYPES)
        if not path or not self._ensure_client():
            return
        name = os.path.basename(path)
        if not messagebox.askyesno(
                "In Google Drive hochladen",
                f"„{name}“ ({size_text(os.path.getsize(path))}) wird in Google Drive in den Ordner "
                f"„{drive.SHARE_FOLDER}“ hochgeladen und für „Jeder mit dem Link“ zum Ansehen "
                "freigegeben.\n\nWer den QR-Code scannt, kann die Datei öffnen. Fortfahren?",
                parent=self):
            return
        self.start(Path(path))

    def _ensure_client(self) -> bool:
        if self.store.client_config() is not None:
            return True
        if not messagebox.askyesno("Google Drive einrichten", CLIENT_HELP, parent=self):
            return False
        src = filedialog.askopenfilename(title="client_secret.json wählen",
                                         filetypes=[("JSON", "*.json"), ("Alle Dateien", "*.*")])
        if not src:
            return False
        try:
            self.store.import_client_config(src)
        except ValueError as exc:
            messagebox.showerror("Google Drive einrichten", str(exc), parent=self)
            return False
        return True

    def start(self, path: Path) -> None:
        """Startet den Hintergrund-Thread (Anmeldung falls noetig, Upload, Freigabe)."""
        self.busy = True
        self.cancel.clear()
        self.button.configure(state="disabled")
        self.progress.set(0)
        self._show("Verbinde mit Google Drive …", MUTED)

        def ui(fn, *args):
            self._inbox.put((fn, args))

        def progress(sent, total):
            ui(self._on_progress, sent, total)

        def work():
            try:
                link = self._run(path, progress, lambda: ui(
                    self._show, "Bitte im Browser bei Google anmelden …", MUTED))
            except drive.Cancelled:
                ui(self._finish, None, "Hochladen abgebrochen.")
            except drive.AuthRequired as exc:
                ui(self._finish, None, f"Anmeldung bei Google fehlgeschlagen: {exc}")
            except drive.Offline:
                ui(self._finish, None, "Keine Verbindung zu Google – später erneut versuchen.")
            except drive.SyncError as exc:
                ui(self._finish, None, str(exc))
            except ImportError as exc:
                ui(self._finish, None, f"Google-Bibliotheken fehlen ({exc.name})")
            except Exception as exc:  # nie den Thread sterben lassen
                ui(self._finish, None, f"{type(exc).__name__}: {exc}")
            else:
                ui(self._finish, link, path.name)

        threading.Thread(target=work, daemon=True, name="DriveUpload").start()
        self.after(50, self._poll)

    def _poll(self) -> None:
        while True:
            try:
                fn, args = self._inbox.get_nowait()
            except queue.Empty:
                break
            fn(*args)
        if self.busy:
            self.after(50, self._poll)

    def _run(self, path: Path, progress, on_login) -> str:
        """Im Thread: Credentials (notfalls Browser-Anmeldung), dann hochladen und freigeben."""
        try:
            creds = self.store.credentials()
        except drive.AuthRequired:
            on_login()
            self.store.link()
            creds = self.store.credentials()
        client = drive.DriveClient(creds, self.cancel)
        link = drive.upload_and_share(client, path, progress)
        if creds.token:  # AuthorizedSession erneuert unterwegs ggf. das Token
            self.store.save_info(creds.to_json())
        return link

    # ------------------------------------------------------------ Rueckmeldungen (GUI-Thread)

    def _show(self, text: str, color) -> None:
        self.status.configure(text=text, text_color=color)

    def _on_progress(self, sent: int, total: int) -> None:
        if not self.progress.winfo_ismapped():
            self.progress.pack(fill="x", padx=4, pady=(6, 0), before=self.status)
            self.cancel_btn.pack(side="left", padx=8)
        self.progress.set(sent / total if total else 1)
        self._show(f"Lade hoch … {size_text(sent)} von {size_text(total)}", MUTED)

    def _finish(self, link: str | None, message: str) -> None:
        self.busy = False
        self.button.configure(state="normal")
        self.progress.pack_forget()
        self.cancel_btn.pack_forget()
        if link is None:
            self._show(message, ERROR)
            return
        self.on_link(link)
        self._show(f"✓ „{message}“ hochgeladen und freigegeben – der Link steht im Code.", OK)
