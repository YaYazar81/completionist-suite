"""Hauptfenster von CompletionistQR Online: Links verwalten, Scans als Graphen anzeigen."""
from __future__ import annotations

import ctypes
import queue
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from . import __version__, settings, stats
from .client import Client, Link, ServerError

# Farben von Completionist Pro wie in CompletionistQR (completionistqr/ui/style.py)
CARD = ("#FFFFFF", "#1C2329")  # wie charts.CARD; charts wird erst spaeter geladen
SELECTED, HOVER = ("#D1FAE5", "#112C27"), ("#E2E8F0", "#222C35")

RANGES = {"7 Tage": 7, "30 Tage": 30, "90 Tage": 90, "1 Jahr": 365}
OK, MUTED, ERROR = ("#15803D", "#4ADE80"), ("gray35", "gray65"), ("#B91C1C", "#F87171")
SERVER_HELP = ("Adresse, unter der index.php aus dem Ordner server/ liegt, z. B. "
               "https://qr.example.de – und der API-Schlüssel aus der config.php dort.")


def local_time(ts: str | None, today: date | None = None) -> str:
    """Zeit eines Scans kurz: „heute 14:05“, „gestern 09:12“, sonst das Datum."""
    if not ts:
        return "–"
    try:
        t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return ts
    days = ((today or date.today()) - t.date()).days
    if days == 0:
        return t.strftime("heute %H:%M")
    if days == 1:
        return t.strftime("gestern %H:%M")
    return t.strftime("%d.%m.%Y")


class FormDialog(ctk.CTkToplevel):
    """Kleiner modaler Dialog mit Eingabefeldern; ``result`` ist danach ein dict oder None."""

    def __init__(self, master, title: str, fields: list[tuple[str, str, str]], hint: str = "",
                 test: Callable[[dict], str] | None = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: dict | None = None
        self.vars: dict[str, ctk.StringVar] = {}
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(1, weight=1)
        first = None
        for i, (key, label, value) in enumerate(fields):
            ctk.CTkLabel(frame, text=label, anchor="w").grid(row=i, column=0, sticky="w", padx=(0, 10),
                                                             pady=4)
            var = self.vars[key] = ctk.StringVar(value=value)
            entry = ctk.CTkEntry(frame, textvariable=var, width=380,
                                 show="•" if key == "api_key" else "")
            entry.grid(row=i, column=1, sticky="ew", pady=4)
            first = first or entry
        row = len(fields)
        if hint:
            ctk.CTkLabel(frame, text=hint, text_color=MUTED, wraplength=480, justify="left",
                         anchor="w").grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.message = ctk.CTkLabel(frame, text="", anchor="w", wraplength=480, justify="left")
        self.message.grid(row=row + 1, column=0, columnspan=2, sticky="w")
        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.grid(row=row + 2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        if test:
            ctk.CTkButton(bar, text="Verbindung testen", fg_color="transparent", border_width=1,
                          text_color=("gray20", "gray85"),
                          command=lambda: self._test(test)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Abbrechen", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).pack(side="left")
        ctk.CTkButton(bar, text="OK", width=90, command=self._ok).pack(side="left", padx=(8, 0))
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(master)
        # Mittig ueber dem Hauptfenster statt irgendwo auf dem Bildschirm
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(100, lambda: (self.grab_set(), first.focus_set() if first else None))

    def values(self) -> dict:
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _test(self, test) -> None:
        self.message.configure(text="Prüfe …", text_color=MUTED)
        self.update_idletasks()
        error = test(self.values())
        self.message.configure(text=error or "✓ Verbindung steht, Schlüssel passt.",
                               text_color=ERROR if error else OK)

    def _ok(self) -> None:
        self.result = self.values()
        self.destroy()

    def ask(self) -> dict | None:
        self.wait_window()
        return self.result


class QROnlineApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"CompletionistQR Online {__version__}")
        # In der gepackten App liegen die Assets unter sys._MEIPASS
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets" / "icon.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except Exception:  # z. B. unter Linux: .ico nicht als Fenstersymbol
                pass
        self.geometry("1240x860")
        self.minsize(1000, 680)
        self.settings = settings.load()
        self.links: list[Link] = []
        self.current: Link | None = None
        self.scans: list[stats.Scan] = []
        self._inbox: queue.Queue = queue.Queue()
        self._busy = 0
        self._design_windows: dict = {}  # Code -> offenes Fenster "QR-Code gestalten"
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_list()
        self._build_details()
        self.bind("<F1>", lambda _e: self.show_about())
        self.after(100, self._poll)
        if self.client():
            self.refresh()
        else:
            self.after(300, self.edit_server)

    # ================================================================ Server

    def client(self) -> Client | None:
        url, key = self.settings.get("base_url", ""), self.settings.get("api_key", "")
        return Client(url, key) if url and key else None

    def _run(self, work: Callable, done: Callable, busy: str) -> None:
        """``work`` läuft im Hintergrund; ``done(result)`` danach im GUI-Thread."""
        self._busy += 1
        self.set_status(busy, MUTED)
        self.configure(cursor="watch")

        def target():
            try:
                self._inbox.put((done, work(), None))
            except Exception as exc:  # Fehler in die Oberflaeche melden
                self._inbox.put((done, None, exc))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                done, result, error = self._inbox.get_nowait()
                self._busy -= 1
                if not self._busy:
                    self.configure(cursor="")
                if error is not None:
                    self.set_status(str(error) if isinstance(error, ServerError)
                                    else f"Fehler: {error}", ERROR)
                    continue
                self.set_status("", MUTED)
                try:
                    done(result)
                except Exception as exc:  # nicht die ganze Abfrage-Schleife verlieren
                    self.set_status(f"Fehler: {exc}", ERROR)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll)

    def set_status(self, text: str, color=MUTED) -> None:
        self.status.configure(text=text, text_color=color)

    def edit_server(self) -> None:
        def test(values: dict) -> str:
            try:
                Client(values["base_url"], values["api_key"], timeout=8).ping()
            except ServerError as exc:
                return str(exc)
            return ""
        result = FormDialog(self, "Server", [
            ("base_url", "Adresse", self.settings.get("base_url", "https://")),
            ("api_key", "API-Schlüssel", self.settings.get("api_key", ""))],
            hint=SERVER_HELP, test=test).ask()
        if result:
            self.settings.update(result)
            settings.save(self.settings)
            self.refresh()

    # ================================================================ Aufbau

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 0))
        ctk.CTkButton(bar, text="＋ Neuer Link …", command=self.new_link).pack(side="left")
        ctk.CTkButton(bar, text="↻ Aktualisieren", width=120, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray85"),
                      command=self.refresh).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Server …", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.edit_server).pack(side="left")
        from .design import style  # completionistqr (design.py findet das Paket)

        info_icon = style.icon("info")
        ctk.CTkButton(bar, text="" if info_icon else "ⓘ", image=info_icon, width=34, height=34,
                      **style.secondary(), command=self.show_about).pack(side="right")
        self.status = ctk.CTkLabel(bar, text="", anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=12)

    def _build_list(self) -> None:
        self.list_frame = ctk.CTkScrollableFrame(self, width=300, label_text="Meine QR-Links")
        self.list_frame.grid(row=1, column=0, sticky="nsw", padx=(14, 7), pady=12)

    def _build_details(self) -> None:
        d = self.details = ctk.CTkScrollableFrame(self)
        d.grid(row=1, column=1, sticky="nsew", padx=(7, 14), pady=12)
        d.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")

        self.heading = ctk.CTkLabel(d, text="Links links auswählen oder neu anlegen",
                                    font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        self.heading.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=(4, 8))

        form = ctk.CTkFrame(d, fg_color="transparent")
        form.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6)
        form.grid_columnconfigure(1, weight=1)
        self.short_var, self.target_var, self.label_var = (ctk.StringVar() for _ in range(3))
        for i, (text, var) in enumerate((("Im QR-Code", self.short_var), ("Ziel", self.target_var),
                                         ("Name", self.label_var))):
            ctk.CTkLabel(form, text=text, anchor="w", width=90).grid(row=i, column=0, sticky="w", pady=3)
            entry = ctk.CTkEntry(form, textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", pady=3)
            if var is self.short_var:
                entry.configure(state="readonly")
        ctk.CTkButton(form, text="Kopieren", width=110, command=self.copy_link).grid(
            row=0, column=2, padx=(8, 0))
        ctk.CTkButton(form, text="Speichern", width=110, command=self.save_link).grid(
            row=1, column=2, rowspan=2, padx=(8, 0))
        ctk.CTkLabel(d, text="Das Ziel lässt sich jederzeit ändern – der gedruckte Code bleibt "
                             "gültig. Gestalten (Vorlagen, Logo, Rahmen, Beschriftung) und als "
                             "PNG, SVG oder PDF speichern wie in CompletionistQR.",
                     text_color=MUTED, anchor="w", justify="left", wraplength=760).grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(2, 0))
        bar = ctk.CTkFrame(d, fg_color="transparent")
        bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 4))
        ctk.CTkButton(bar, text="QR-Code gestalten und speichern …",
                      command=self.design_qr).pack(side="left")
        ctk.CTkButton(bar, text="Löschen …", width=90, fg_color="transparent", border_width=1,
                      text_color=ERROR, command=self.delete_link).pack(side="left", padx=8)
        self.range = ctk.CTkSegmentedButton(bar, values=list(RANGES),
                                            command=lambda _v: self.load_scans())
        self.range.set(self.settings.get("range", "30 Tage"))
        self.range.pack(side="right")

        self.summary = ctk.CTkFrame(d, fg_color="transparent")
        self.summary.grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 4))
        self.tiles = {}
        for i, key in enumerate(("Im Zeitraum", "Heute", "Insgesamt", "Letzter Scan")):
            tile = ctk.CTkFrame(self.summary, corner_radius=12, fg_color=CARD)
            tile.grid(row=0, column=i, sticky="ew", padx=4)
            self.summary.grid_columnconfigure(i, weight=1, uniform="t")
            ctk.CTkLabel(tile, text=key, text_color=MUTED).pack(anchor="w", padx=12, pady=(8, 0))
            value = ctk.CTkLabel(tile, text="–", font=ctk.CTkFont(size=22, weight="bold"))
            value.pack(anchor="w", padx=12, pady=(0, 8))
            self.tiles[key] = value

        # Die Graphen (matplotlib) kommen nach, sobald das Fenster steht
        self.charts: dict | None = None
        self._pending_stats: tuple | None = None
        self.after(50, self._build_charts)

    def _build_charts(self) -> None:
        from .charts import Chart

        d = self.details
        self.charts = {
            "time": Chart(d, "Scans pro Tag", height=240),
            "hour": Chart(d, "Uhrzeit"), "weekday": Chart(d, "Wochentag"),
            "device": Chart(d, "Gerät", horizontal=True),
            "os": Chart(d, "Betriebssystem", horizontal=True),
            "lang": Chart(d, "Sprache", horizontal=True)}
        self.charts["time"].grid(row=5, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        self.charts["hour"].grid(row=6, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        self.charts["weekday"].grid(row=6, column=2, sticky="ew", padx=6, pady=6)
        for i, key in enumerate(("device", "os", "lang")):
            self.charts[key].grid(row=7, column=i, sticky="ew", padx=6, pady=6)
        if self._pending_stats:
            self._show_stats(*self._pending_stats)

    # ================================================================ Links

    def refresh(self) -> None:
        client = self.client()
        if not client:
            self.set_status("Noch kein Server eingetragen – „Server …“", ERROR)
            return
        self._run(client.links, self._show_links, "Lade Links …")

    def _show_links(self, links: list[Link]) -> None:
        self.links = links
        for child in self.list_frame.winfo_children():
            child.destroy()
        if not links:
            ctk.CTkLabel(self.list_frame, text="Noch keine Links.\n„＋ Neuer Link …“ legt einen an.",
                         text_color=MUTED).pack(pady=20)
        for link in links:
            self._list_item(link, self.current is not None and link.code == self.current.code)
        if self.current:
            self.select(self.current.code)
        elif links:
            self.select(links[0].code)

    def _list_item(self, link: Link, selected: bool) -> None:
        """Eintrag in der Liste: Name fett, darunter Code und Scan-Zahl; ganze Fläche klickbar."""
        base = SELECTED if selected else CARD
        item = ctk.CTkFrame(self.list_frame, corner_radius=10, fg_color=base, cursor="hand2")
        item.pack(fill="x", pady=3)
        title = ctk.CTkLabel(item, text=link.title, anchor="w", justify="left", wraplength=250,
                             font=ctk.CTkFont(weight="bold"))
        title.pack(fill="x", padx=12, pady=(8, 0))
        info = ctk.CTkLabel(item, anchor="w", text_color=MUTED,
                            text=f"{link.code} · {link.scans} {'Scan' if link.scans == 1 else 'Scans'}")
        info.pack(fill="x", padx=12, pady=(0, 8))
        for w in (item, title, info):
            w.bind("<Button-1>", lambda _e, c=link.code: self.select(c))
            if not selected:
                w.bind("<Enter>", lambda _e: item.configure(fg_color=HOVER))
                w.bind("<Leave>", lambda _e: item.configure(fg_color=base))

    def select(self, code: str) -> None:
        link = next((l for l in self.links if l.code == code), None)
        if link is None:
            self.current = None
            return
        changed = self.current is None or self.current.code != code
        self.current = link
        self.heading.configure(text=link.title)
        self.short_var.set(link.url)
        self.target_var.set(link.target)
        self.label_var.set(link.label)
        self.tiles["Insgesamt"].configure(text=str(link.scans))
        self.tiles["Letzter Scan"].configure(text=local_time(link.last_scan))
        if changed:
            # Markierung in der Liste nachziehen
            self._show_links(self.links)
            return
        self.load_scans()

    def new_link(self) -> None:
        client = self.client()
        if not client:
            self.edit_server()
            return
        result = FormDialog(self, "Neuer QR-Link", [
            ("target", "Ziel-Adresse", "https://"), ("label", "Name (optional)", "")],
            hint="Der QR-Code enthält eine kurze Adresse auf deinem Server, die jeden Scan "
                 "zählt und sofort zum Ziel weiterleitet.").ask()
        if not result:
            return
        target = result["target"]
        if target and "://" not in target:
            target = "https://" + target

        def done(link: Link):
            self.current = link
            self.set_status(f"✓ Angelegt: {link.url}", OK)
            self.refresh()
        self._run(lambda: client.create(target, result["label"]), done, "Lege Link an …")

    def save_link(self) -> None:
        client, link = self.client(), self.current
        if not client or not link:
            return
        target = self.target_var.get().strip()
        if target and "://" not in target:
            target = "https://" + target

        def done(updated: Link):
            self.current = updated
            self.refresh()
        self._run(lambda: client.update(link.code, target=target, label=self.label_var.get().strip()),
                  done, "Speichere …")

    def delete_link(self) -> None:
        client, link = self.client(), self.current
        if not client or not link:
            return
        if not messagebox.askyesno(
                "Link löschen", f"„{link.title}“ samt {link.scans} gezählten Scans löschen?\n\n"
                                "Gedruckte Codes mit diesem Link funktionieren danach nicht mehr.",
                icon="warning", parent=self):
            return

        def done(_):
            win = self._design_windows.pop(link.code, None)
            if win is not None and win.winfo_exists():
                win.destroy()  # der Code gilt nicht mehr
            self.settings.get("designs", {}).pop(link.code, None)
            settings.save(self.settings)
            self.current = None
            self.refresh()
        self._run(lambda: client.delete(link.code), done, "Lösche …")

    def copy_link(self) -> None:
        if self.current:
            self.clipboard_clear()
            self.clipboard_append(self.current.url)
            self.set_status("✓ Link kopiert", OK)

    def design_qr(self) -> None:
        """Der Gestalter von CompletionistQR mit dem Kurzlink als Inhalt (design.py)."""
        link = self.current
        if not link:
            return
        win = self._design_windows.get(link.code)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            return
        from .design import DesignWindow

        self._design_windows[link.code] = DesignWindow(self, link, self.settings)

    def show_about(self) -> None:
        from completionistqr.ui.about import AboutWindow

        from .design import about_info

        AboutWindow(self, **about_info())

    # ================================================================ Statistik

    def load_scans(self) -> None:
        client, link = self.client(), self.current
        if not client or not link:
            return
        days = RANGES[self.range.get()]
        if self.settings.get("range") != self.range.get():
            self.settings["range"] = self.range.get()
            settings.save(self.settings)
        since = stats.query_since(days, date.today())

        def done(rows):
            if self.current and self.current.code == link.code:
                self._show_stats(stats.parse(rows), days)
        self._run(lambda: client.scans(link.code, since), done, "Lade Scans …")

    def _show_stats(self, scans: list[stats.Scan], days: int) -> None:
        today = date.today()
        scans = stats.in_range(scans, days, today)
        per_day = stats.daily(scans, days, today)
        self.tiles["Im Zeitraum"].configure(text=str(len(scans)))
        self.tiles["Heute"].configure(text=str(per_day[-1][1]))
        if self.charts is None:
            self._pending_stats = (scans, days)
            return
        c = self.charts
        if days > 90:
            c["time"].title = "Scans pro Woche"
            c["time"].set_data([(d.strftime("%d.%m."), n) for d, n in stats.weekly(per_day)],
                               label_every=4)
        else:
            c["time"].title = "Scans pro Tag"
            c["time"].set_data([(d.strftime("%d.%m."), n) for d, n in per_day],
                               label_every={7: 1, 30: 3}.get(days, 10))
        c["hour"].set_data(stats.hourly(scans), label_every=3)
        c["weekday"].set_data(stats.by_weekday(scans))
        c["device"].set_data(stats.breakdown(scans, "device"))
        c["os"].set_data(stats.breakdown(scans, "os"))
        c["lang"].set_data([(stats.language_name(lang), n)
                            for lang, n in stats.breakdown(scans, "lang")])

def main() -> None:
    if sys.platform == "win32":
        try:  # eigenes Taskleistensymbol statt des Python-Symbols
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CompletionistQR.Online")
        except Exception:
            pass
    ctk.set_appearance_mode(settings.load().get("appearance", "system"))
    from .design import apply_theme, register_fonts

    apply_theme()     # Completionist Pro wie CompletionistQR
    register_fonts()  # Schriften für die Vorschau im Gestalter
    QROnlineApp().mainloop()
