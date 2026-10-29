"""Google-Drive-Sync fuer CompletionistMD.

Laedt den Vault (bzw. einen eingestellten Quellordner) geraeuschlos in einen
Ordner in Google Drive hoch -- nur Dateien, die neu sind oder sich geaendert
haben (MD5-Vergleich mit der Drive-Fassung). Die lokale Fassung hat immer
Vorrang: weicht Drive ab, wird ueberschrieben. Geloescht wird in Drive nichts.

Aufbau:

* ``TokenStore`` / ``DriveClient`` -- Anmeldung, Token-Ablage (DPAPI) und
  REST-Aufrufe; ohne Qt in ``core/drive.py``, weil CompletionistQR sie mitnutzt
* ``plan_sync`` / ``run_sync`` -- Differenz-Logik, ohne Qt testbar
* ``SyncWorker``   -- laeuft im eigenen ``QThread``; die Oberflaeche wartet nie
* ``GDriveSync``   -- Controller im GUI-Thread: Timer, Trigger, Status

Scope ist ``drive.file``: die App sieht nur Dateien, die sie selbst angelegt
hat. Den Zielordner legt sie deshalb selbst an.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QToolButton

from core.drive import (
    FOLDER_MIME, AuthRequired, Cancelled, DriveClient, NotFound, Offline, SyncError,
    TokenStore, parse_rfc3339,
)
from core.office import OFFICE_SYNC_SUFFIXES

# Notizen, PDFs, Bilder und Office-Dateien aller gaengigen Programme (Word, Excel,
# PowerPoint, OpenDocument/LibreOffice/OpenOffice, iWork, WPS). Office-Lock-Dateien
# (~$Bericht.docx, .~lock.…#) beginnen mit ~$ bzw. Punkt und bleiben aussen vor.
SYNC_SUFFIXES = (".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif") + OFFICE_SYNC_SUFFIXES
DEFAULT_FOLDER = "Completionist Vault"
DEFAULTS = {
    "enabled": False,
    "source": "",            # leer = Vault-Verzeichnis
    "folder": DEFAULT_FOLDER,
    "on_save": True,
    "periodic": True,
    "interval_min": 15,
}
SAVE_DEBOUNCE_MS = 5000
STARTUP_DELAY_MS = 4000
RETRY_MINUTES = (1, 2, 5, 10, 15)  # neuer Lauf nach Abbruch (offline/Fehler)


def settings_with_defaults(raw) -> dict:
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out.update({k: raw[k] for k in DEFAULTS if k in raw})
    try:
        out["interval_min"] = max(1, int(out["interval_min"]))
    except (TypeError, ValueError):
        out["interval_min"] = DEFAULTS["interval_min"]
    out["folder"] = str(out["folder"]).strip() or DEFAULT_FOLDER
    return out

# ---------------------------------------------------------------------- #
# Differenz-Logik (ohne Qt)
# ---------------------------------------------------------------------- #


def scan_local(source: Path) -> dict[str, Path]:
    """rel. Pfad (mit /) -> Datei. Versteckte Ordner (.obsidian, .git, .trash) bleiben aussen vor."""
    found: dict[str, Path] = {}
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in files:
            if name.startswith((".", "~$")) or not name.lower().endswith(SYNC_SUFFIXES):
                continue
            p = Path(root) / name
            found[p.relative_to(source).as_posix()] = p
    return found


class HashCache:
    """MD5 je Datei, nur neu berechnet, wenn sich Groesse oder Zeitstempel aendern."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, list] = {}
        if path:
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.data = {}

    def md5(self, p: Path) -> str:
        st = p.stat()
        key = str(p)
        hit = self.data.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        h = hashlib.md5()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
        self.data[key] = [st.st_size, st.st_mtime_ns, digest]
        return digest

    def save(self, keep: set[str]) -> None:
        if not self.path:
            return
        self.data = {k: v for k, v in self.data.items() if k in keep}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        except OSError:
            pass


@dataclass
class RemoteTree:
    top_id: str
    folders: dict[str, str] = field(default_factory=dict)  # rel. Ordner ("" = Zielordner) -> id
    files: dict[str, dict] = field(default_factory=dict)   # rel. Datei -> Drive-Eintrag


def remote_tree(client, folder_name: str) -> RemoteTree:
    items = client.list_all()
    # Kein files/root: mit drive.file darf die App den Root-Ordner nicht lesen
    # (404 "File not found: 0A…PVA"). Zielordner ist deshalb der gleichnamige
    # Ordner, der nicht selbst in einem Ordner der App liegt.
    own = {i["id"] for i in items}
    candidates = [
        i for i in items if i.get("mimeType") == FOLDER_MIME and i.get("name") == folder_name
        and not own.intersection(i.get("parents") or [])
    ]
    # Die Liste kann kurz nach dem Loeschen noch verwaiste IDs enthalten:
    # den Kandidaten gezielt nachpruefen, sonst den Ordner im Root neu anlegen.
    top_id = next((c["id"] for c in candidates if client.exists(c["id"])), None)
    if top_id is None:
        top_id = client.create_folder(folder_name, None)
    children: dict[str, list[dict]] = {}
    for i in items:
        for parent in i.get("parents") or []:
            children.setdefault(parent, []).append(i)
    tree = RemoteTree(top_id, folders={"": top_id})
    stack = [("", top_id)]
    while stack:
        rel, fid = stack.pop()
        for child in children.get(fid, []):
            child_rel = f"{rel}/{child['name']}" if rel else child["name"]
            if child.get("mimeType") == FOLDER_MIME:
                if child_rel not in tree.folders:
                    tree.folders[child_rel] = child["id"]
                    stack.append((child_rel, child["id"]))
            else:
                tree.files.setdefault(child_rel, child)
    return tree


@dataclass
class Job:
    rel: str
    path: Path
    remote: dict | None   # None = neu
    conflict: bool = False  # Drive war neuer und anders -- lokal gewinnt trotzdem


def plan_sync(local: dict[str, Path], tree: RemoteTree, hashes: HashCache) -> list[Job]:
    jobs = []
    for rel, path in sorted(local.items()):
        remote = tree.files.get(rel)
        digest = hashes.md5(path)
        if remote is None:
            jobs.append(Job(rel, path, None))
        elif remote.get("md5Checksum") != digest:
            newer = parse_rfc3339(remote.get("modifiedTime", "")) > path.stat().st_mtime + 1
            jobs.append(Job(rel, path, remote, conflict=newer))
    return jobs


def run_sync(client, source: Path, folder_name: str, hashes: HashCache,
             on_planned=lambda n: None, on_progress=lambda done, total: None) -> dict:
    if not source.is_dir():
        raise SyncError(f"Quellordner nicht gefunden: {source}")
    local = scan_local(source)
    done: list[Job] = []
    failed: dict[str, str] = {}  # rel. Pfad -> Meldung (dauerhafte Fehler einzelner Dateien)
    # Zwei Anlaeufe: Liefert Drive mittendrin 404 (Zielordner, Unterordner oder
    # Datei geloescht bzw. Liste veraltet), wird der Baum neu eingelesen -- ein
    # fehlender Zielordner dabei im Root neu angelegt -- und neu geplant.
    # Schon Hochgeladenes hat dann denselben MD5 und faellt aus dem Plan.
    for attempt in (1, 2):
        tree = remote_tree(client, folder_name)
        jobs = [j for j in plan_sync(local, tree, hashes) if j.rel not in failed]
        on_planned(len(jobs))

        def folder_id(rel_dir: str) -> str:
            if rel_dir in tree.folders:
                return tree.folders[rel_dir]
            parent_rel, _, name = rel_dir.rpartition("/")
            fid = client.create_folder(name, folder_id(parent_rel))
            tree.folders[rel_dir] = fid
            return fid

        try:
            for n, job in enumerate(jobs, 1):
                parent_rel, _, name = job.rel.rpartition("/")
                try:
                    client.upload(job.path, name, folder_id(parent_rel),
                                  job.remote["id"] if job.remote else None)
                except (NotFound, AuthRequired, Offline, Cancelled):
                    raise  # betrifft den ganzen Lauf
                except SyncError as exc:
                    failed[job.rel] = str(exc)  # nur diese Datei -- weiter mit der naechsten
                except OSError as exc:  # lokal gesperrt/geloescht
                    failed[job.rel] = f"Datei nicht lesbar: {exc}"
                else:
                    done.append(job)
                on_progress(n, len(jobs))
        except NotFound:
            if attempt == 2:
                raise
            continue
        break
    hashes.save({str(p) for p in local.values()})
    return {
        "checked": len(local),
        "uploaded": len(done),
        "new": sum(1 for j in done if j.remote is None),
        "conflicts": sum(1 for j in done if j.conflict),
        "failed": failed,
        "time": time.time(),
    }


# ---------------------------------------------------------------------- #
# Worker im eigenen Thread
# ---------------------------------------------------------------------- #


class SyncWorker(QObject):
    planned = Signal(int)
    progress = Signal(int, int)
    finished = Signal(dict)
    failed = Signal(str, str)      # Art (auth/offline/error/cancelled), Meldung
    linkFinished = Signal(bool, str)

    def __init__(self, store: TokenStore) -> None:
        super().__init__()
        self.store = store
        self.cancel = threading.Event()

    @Slot(str, str)
    def sync(self, source: str, folder_name: str) -> None:
        try:
            creds = self.store.credentials()
            client = DriveClient(creds, self.cancel)
            hashes = HashCache(self.store.folder.parent / "gdrive_hashes.json")
            result = run_sync(client, Path(source), folder_name, hashes,
                              self.planned.emit, self.progress.emit)
            if creds.token:  # AuthorizedSession erneuert unterwegs ggf. das Token
                self.store.save_info(creds.to_json())
        except SyncError as exc:
            self.failed.emit(exc.kind, str(exc))
        except ImportError as exc:
            self.failed.emit("error", f"Google-Bibliotheken fehlen ({exc.name})")
        except Exception as exc:  # nie den Thread sterben lassen
            self.failed.emit("error", f"{type(exc).__name__}: {exc}")
        else:
            self.finished.emit(result)

    @Slot()
    def link(self) -> None:
        try:
            self.store.link()
        except SyncError as exc:
            self.linkFinished.emit(False, str(exc))
        except ImportError as exc:
            self.linkFinished.emit(False, f"Google-Bibliotheken fehlen ({exc.name})")
        except Exception as exc:
            self.linkFinished.emit(False, f"{type(exc).__name__}: {exc}")
        else:
            self.linkFinished.emit(True, "")


# ---------------------------------------------------------------------- #
# Controller im GUI-Thread
# ---------------------------------------------------------------------- #


class GDriveSync(QObject):
    """Haelt Thread, Timer und Status. ``statusChanged(state, text, tooltip)``
    mit state in off/idle/ok/busy/offline/auth/error."""

    statusChanged = Signal(str, str, str)
    linkFinished = Signal(bool, str)
    _doSync = Signal(str, str)
    _doLink = Signal()

    def __init__(self, parent=None, store: TokenStore | None = None) -> None:
        super().__init__(parent)
        self.store = store or TokenStore()
        self.settings = settings_with_defaults({})
        self.vault = ""
        self.running = False
        self.linking = False
        self._again = False
        self._last_ok: float | None = None
        self._last_result: dict = {}
        self.state = "off"

        self.thread = QThread(self)
        self.thread.setObjectName("GDriveSync")
        self.worker = SyncWorker(self.store)
        self.worker.moveToThread(self.thread)
        self._doSync.connect(self.worker.sync)
        self._doLink.connect(self.worker.link)
        self.worker.planned.connect(self._on_planned)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.linkFinished.connect(self._on_linked)
        self.thread.start()

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(SAVE_DEBOUNCE_MS)
        self.debounce.timeout.connect(self.sync_now)
        self.periodic = QTimer(self)
        self.periodic.timeout.connect(self.sync_now)
        self.clock = QTimer(self)  # "vor 3 Min" aktuell halten
        self.clock.setInterval(30_000)
        self.clock.timeout.connect(self._refresh_ok_text)
        self.clock.start()
        # Nach einem Abbruch (offline/Fehler) selbst neu versuchen: 1, 2, 5, 10, 15 Min
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self.sync_now)
        self._retry_step = 0

    # --- Konfiguration ---

    @property
    def source(self) -> str:
        return self.settings["source"] or self.vault

    def configure(self, settings: dict, vault: str, startup: bool = False) -> None:
        self.settings = settings_with_defaults(settings)
        self.vault = vault
        self.periodic.stop()
        self.debounce.stop()
        if not self.settings["enabled"]:
            self._set("off", "", "")
            return
        if self.settings["periodic"]:
            self.periodic.start(self.settings["interval_min"] * 60_000)
        if not self.store.has_token():
            self._set("auth", "Google Drive: Authentifizierung erforderlich",
                      "Einstellungen → Google Drive → „Google Account verknüpfen“")
            return
        if self.state in ("off", "auth"):
            self._set("idle", "Google Drive: bereit", "Klick: jetzt synchronisieren")
        # Beim Start (und nach Aenderungen) einmal abgleichen -- erneuert dabei
        # auch das Token, damit nie wieder eine Anmeldung noetig ist.
        QTimer.singleShot(STARTUP_DELAY_MS if startup else 0, self.sync_now)

    # --- Trigger ---

    def notify_saved(self) -> None:
        if self.settings["enabled"] and self.settings["on_save"] and self.store.has_token():
            self.debounce.start()

    def sync_now(self) -> None:
        if not self.settings["enabled"] or self.linking:
            return
        if not self.store.has_token():
            self._set("auth", "Google Drive: Authentifizierung erforderlich",
                      "Einstellungen → Google Drive → „Google Account verknüpfen“")
            return
        if not self.source:
            self._set("error", "Google Drive: kein Quellordner",
                      "Vault-Verzeichnis oder Quell-Pfad in den Einstellungen festlegen")
            return
        if self.running:
            self._again = True
            return
        self.running = True
        self._again = False
        self.debounce.stop()
        self.retry.stop()
        self._set("busy", "Google Drive: prüfe Änderungen …", self.source)
        self._doSync.emit(self.source, self.settings["folder"])

    def link_account(self) -> None:
        if self.linking:
            return
        self.linking = True
        self._doLink.emit()

    def unlink(self) -> None:
        self.store.forget()
        if self.settings["enabled"]:
            self._set("auth", "Google Drive: Authentifizierung erforderlich",
                      "Einstellungen → Google Drive → „Google Account verknüpfen“")

    def shutdown(self) -> None:
        self.periodic.stop()
        self.debounce.stop()
        self.retry.stop()
        self.worker.cancel.set()
        self.thread.quit()
        if not self.thread.wait(8000):
            # haengender Netzwerkaufruf oder offener Browser-Login: Programm endet ohnehin
            self.thread.terminate()
            self.thread.wait(2000)

    # --- Rueckmeldungen aus dem Worker ---

    @staticmethod
    def _files(n: int) -> str:
        return f"{n} Datei" if n == 1 else f"{n} Dateien"

    def _on_planned(self, n: int) -> None:
        if n:
            self._on_progress(0, n)

    def _on_progress(self, done: int, total: int) -> None:
        self._set("busy", f"Google Drive: Synchronisiere {self._files(total)} … ({done}/{total})",
                  f"{done} von {total} hochgeladen\nBereits Hochgeladenes bleibt auch bei einem "
                  "Abbruch erhalten.")

    def _on_finished(self, result: dict) -> None:
        self.running = False
        self._retry_step = 0
        self._last_ok = result.get("time", time.time())
        self._last_result = result
        self._refresh_ok_text(force=True)
        if self._again:
            self.sync_now()

    def _on_failed(self, kind: str, message: str) -> None:
        self.running = False
        self._again = False
        if kind == "cancelled":
            return
        if kind == "auth":
            self._set("auth", "Google Drive: Authentifizierung erforderlich", message)
            return
        # Bereits Hochgeladenes ist in Drive; der naechste Lauf macht dort weiter.
        minutes = RETRY_MINUTES[min(self._retry_step, len(RETRY_MINUTES) - 1)]
        self._retry_step += 1
        self.retry.start(minutes * 60_000)
        later = f"Nächster Versuch in {minutes} Min – oder jetzt per Klick."
        if kind == "offline":
            self._set("offline", "Google Drive: Offline",
                      f"Keine Verbindung zu Google. {later}\n\n{message}")
        else:
            self._set("error", "Google Drive: Fehler", f"{later}\n\n{message}")

    def _on_linked(self, ok: bool, message: str) -> None:
        self.linking = False
        self.linkFinished.emit(ok, message)
        if ok and self.settings["enabled"]:
            self.sync_now()

    # --- Status ---

    def _refresh_ok_text(self, force: bool = False) -> None:
        if self._last_ok is None or (self.state != "ok" and not force):
            return
        r = self._last_result
        tip = (f"Quelle: {self.source}\nZiel: Google Drive / {self.settings['folder']}\n"
               f"Zuletzt: {r.get('uploaded', 0)} hochgeladen, {r.get('checked', 0)} geprüft")
        if r.get("conflicts"):
            tip += f"\n{r['conflicts']} Konflikt(e) – lokale Fassung hat Vorrang"
        failed = r.get("failed") or {}
        if failed:
            tip += f"\n\n{self._files(len(failed))} übersprungen (nächster Lauf versucht es erneut):"
            for rel, msg in list(failed.items())[:8]:
                tip += f"\n• {rel}: {msg}"
            if len(failed) > 8:
                tip += f"\n• … und {len(failed) - 8} weitere"
        tip += "\nKlick: jetzt synchronisieren"
        text = f"Google Drive: Synchronisiert ({ago(self._last_ok)})"
        if failed:
            text += f", {len(failed)} übersprungen"
        # "ok" auch mit Uebersprungenen: die Uhr aktualisiert den Text weiter
        self._set("ok", text, tip)

    def _set(self, state: str, text: str, tooltip: str) -> None:
        self.state = state
        self.statusChanged.emit(state, text, tooltip)


class SyncStatusButton(QToolButton):
    """Statusleisten-Anzeige; Klick loest einen Abgleich aus."""

    COLORS = {
        "ok": "#10B981",       # Smaragd: gekoppelt & aktuell
        "idle": "#10B981",
        "busy": "#38BDF8",     # blau: laeuft
        "offline": "#FBBF24",  # gelb
        "auth": "#F87171",     # rot
        "error": "#F87171",
    }
    SYMBOLS = {"ok": "☁", "idle": "☁", "offline": "⚠", "auth": "⚠", "error": "⚠"}
    SPINNER = "◐◓◑◒"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("gdriveStatus")
        self._text = ""
        self._state = "off"
        self._frame = 0
        self._spin = QTimer(self)
        self._spin.setInterval(150)
        self._spin.timeout.connect(self._tick)
        self.hide()

    @property
    def state(self) -> str:
        return self._state

    def set_status(self, state: str, text: str, tooltip: str) -> None:
        self._state, self._text = state, text
        self.setVisible(state != "off")
        self.setToolTip(tooltip)
        self.setStyleSheet(f"QToolButton#gdriveStatus {{ color: {self.COLORS.get(state, '')}; }}")
        if state == "busy":
            if not self._spin.isActive():
                self._spin.start()
        else:
            self._spin.stop()
        self._render()

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(self.SPINNER)
        self._render()

    def _render(self) -> None:
        sym = self.SPINNER[self._frame] if self._state == "busy" else self.SYMBOLS.get(self._state, "")
        self.setText(f"{sym}  {self._text}")


def ago(ts: float, now: float | None = None) -> str:
    sec = max(0, (now or time.time()) - ts)
    if sec < 60:
        return "gerade eben"
    if sec < 3600:
        return f"vor {int(sec // 60)} Min"
    if sec < 86400:
        return f"vor {int(sec // 3600)} Std"
    return datetime.fromtimestamp(ts).strftime("am %d.%m. %H:%M")
