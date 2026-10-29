"""Google Drive ohne GUI: Anmeldung, Token-Ablage und die REST-Aufrufe.

Gemeinsam genutzt von CompletionistMD (Vault-Sync, ``mdeditor/gdrive.py``) und
CompletionistQR (Datei hochladen und freigeben, ``completionistqr/ui/drive_upload.py``).
Kein Qt und kein Tk hier -- QR baut auf CustomTkinter und darf PySide6 nicht laden.

* ``TokenStore``  -- client_secret.json und das per Windows-DPAPI
  verschluesselte Token unter %LOCALAPPDATA%\\CompletionistLibrary\\
  CompletionistMD\\credentials (beide Apps teilen sich die Verknuepfung)
* ``DriveClient`` -- die paar REST-Aufrufe der Drive API v3 (ohne den
  schweren google-api-python-client)
* ``upload_and_share`` -- Datei hochladen, "Jeder mit dem Link" freigeben,
  Link zurueck (fuer den QR-Code)

Scope ist ``drive.file``: die App sieht nur Dateien, die sie selbst angelegt hat.
"""

from __future__ import annotations

import json
import mimetypes
import os
import random
import re
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
MULTIPART_LIMIT = 5 * 1024 * 1024  # darueber resumable Upload
CHUNK = 8 * 1024 * 1024  # Stueckgroesse beim resumable Upload (Vielfaches von 256 KiB)
TIMEOUT = (20, 120)  # Verbindungsaufbau, Antwort (s)
MAX_TRIES = 6        # je API-Aufruf, mit Pause 1, 2, 4, 8, 16 s


# ---------------------------------------------------------------------- #
# Fehlerarten (bestimmen in MD die Farbe in der Statusleiste)
# ---------------------------------------------------------------------- #


class SyncError(Exception):
    kind = "error"


class AuthRequired(SyncError):
    kind = "auth"


class Offline(SyncError):
    kind = "offline"


class Cancelled(SyncError):
    kind = "cancelled"


class NotFound(SyncError):
    """404: Ordner/Datei wurde in Drive geloescht oder die Liste war veraltet."""


class NoResponse(SyncError):
    """Anfrage ging raus, Antwort blieb aus -- unklar, ob Google sie ausgefuehrt hat."""


# ---------------------------------------------------------------------- #
# Ablage: client_secret.json + verschluesseltes Token
# ---------------------------------------------------------------------- #


def credentials_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CompletionistLibrary" / "CompletionistMD" / "credentials"


_ENTROPY = b"CompletionistMD/gdrive"


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows-DPAPI: nur dasselbe Windows-Konto kann wieder entschluesseln."""
    if sys.platform != "win32":
        return data
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    def blob(raw: bytes):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    inp, _keep1 = blob(data)
    ent, _keep2 = blob(_ENTROPY)
    out = Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ui_forbidden = 0x1
    if not fn(ctypes.byref(inp), None, ctypes.byref(ent), None, None, ui_forbidden, ctypes.byref(out)):
        raise OSError(ctypes.GetLastError(), "DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


class TokenStore:
    CLIENT_FILE = "client_secret.json"
    TOKEN_FILE = "token.json.dpapi"

    def __init__(self, folder: Path | None = None, app_name: str = "CompletionistMD") -> None:
        self.folder = Path(folder) if folder else credentials_dir()
        self.app_name = app_name

    # --- OAuth-Client (Google Cloud Console, Typ "Desktop-App") ---

    def client_config(self) -> dict | None:
        try:
            data = json.loads((self.folder / self.CLIENT_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) and "installed" in data else None

    def import_client_config(self, source: str | Path) -> None:
        """Prueft und uebernimmt die heruntergeladene client_secret*.json."""
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Datei konnte nicht gelesen werden: {exc}") from exc
        if not isinstance(data, dict) or "installed" not in data:
            if isinstance(data, dict) and "web" in data:
                raise ValueError(
                    "Das ist ein OAuth-Client vom Typ „Webanwendung“. Benötigt wird "
                    "ein Client vom Typ „Desktop-App“."
                )
            raise ValueError("Keine OAuth-Client-Datei (client_secret.json) von Google.")
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, self.folder / self.CLIENT_FILE)

    # --- Token ---

    def has_token(self) -> bool:
        return (self.folder / self.TOKEN_FILE).is_file()

    def load_info(self) -> dict | None:
        try:
            raw = _dpapi((self.folder / self.TOKEN_FILE).read_bytes(), protect=False)
            return json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return None

    def save_info(self, info_json: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / self.TOKEN_FILE
        # eigener Name je Prozess: MD und QR koennen gleichzeitig erneuern
        tmp = target.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(_dpapi(info_json.encode("utf-8"), protect=True))
        os.replace(tmp, target)

    def forget(self) -> None:
        try:
            (self.folder / self.TOKEN_FILE).unlink()
        except OSError:
            pass

    # --- Google-Credentials ---

    def credentials(self):
        """Gespeicherte Credentials, bei Bedarf erneuert (Netzwerk!)."""
        info = self.load_info()
        if not info:
            raise AuthRequired("Kein Google-Konto verknüpft")
        from google.auth.exceptions import RefreshError, TransportError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        from . import net

        net.install()  # IPv4 zuerst, sonst bis zu 20 s Warten bei kaputtem IPv6

        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if not creds.valid:
            if not creds.refresh_token:
                raise AuthRequired("Anmeldung abgelaufen")
            try:
                creds.refresh(Request())  # Timeout setzt google-auth selbst (120 s)
            except RefreshError as exc:
                raise AuthRequired(f"Anmeldung abgelaufen ({exc})") from exc
            except TransportError as exc:
                raise Offline(str(exc)) from exc
            self.save_info(creds.to_json())
        return creds

    def link(self) -> None:
        """Einmaliger OAuth2-Flow im Standard-Browser (blockiert bis zur Antwort)."""
        config = self.client_config()
        if config is None:
            raise SyncError("Es ist noch keine client_secret.json hinterlegt.")
        from google_auth_oauthlib.flow import InstalledAppFlow

        from . import net

        net.install()  # IPv4 zuerst (siehe core/net.py)

        flow = InstalledAppFlow.from_client_config(config, SCOPES)
        try:
            creds = flow.run_local_server(
                host="localhost",
                port=0,
                open_browser=True,
                timeout_seconds=300,
                authorization_prompt_message="",
                success_message=f"{self.app_name} ist mit Google Drive verknüpft. "
                "Dieses Fenster kann geschlossen werden.",
                prompt="consent",  # sorgt fuer ein Refresh-Token auch beim erneuten Verknuepfen
            )
        except Exception as exc:  # Abbruch, Zeitueberschreitung, Ablehnung
            raise AuthRequired(f"Anmeldung nicht abgeschlossen ({exc})") from exc
        if not getattr(creds, "refresh_token", None):
            raise AuthRequired("Google hat kein Refresh-Token geliefert.")
        self.save_info(creds.to_json())


# ---------------------------------------------------------------------- #
# Drive REST
# ---------------------------------------------------------------------- #


def rfc3339(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_rfc3339(text: str) -> float:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 0.0


def guess_mime(name: str) -> str:
    if name.lower().endswith(".md"):
        return "text/markdown"
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class DriveClient:
    def __init__(self, creds=None, cancel: threading.Event | None = None, session=None) -> None:
        """``session`` statt ``creds``: ein fertiges Objekt mit ``request()`` (Tests)."""
        from . import net

        net.install()  # IPv4 zuerst (siehe core/net.py)
        if session is None:
            from google.auth.transport.requests import AuthorizedSession

            session = AuthorizedSession(creds)
        self.session = session
        self.cancel = cancel or threading.Event()

    def _req(self, method: str, url: str, *, idempotent: bool | None = None, **kw):
        """Ein API-Aufruf mit Wiederholung bei voruebergehenden Fehlern.

        Wiederholt werden Verbindungsfehler/Timeouts, 429, 5xx und Googles
        Rate-Limit (403) -- mit Pause 1, 2, 4 … s. Ein POST, der eine Datei
        anlegt, wird nur wiederholt, wenn er Google sicher nicht erreicht hat
        (Verbindungsaufbau gescheitert, 429/503); sonst drohen Doppelte.
        """
        import requests
        from google.auth.exceptions import RefreshError, TransportError

        if idempotent is None:
            idempotent = method != "POST"
        delay = 1.0
        for attempt in range(1, MAX_TRIES + 1):
            if self.cancel.is_set():
                raise Cancelled("abgebrochen")
            try:
                r = self.session.request(method, url, timeout=TIMEOUT, **kw)
            except RefreshError as exc:
                raise AuthRequired(str(exc)) from exc
            except requests.ConnectTimeout as exc:  # nie beim Server angekommen
                error, retry = Offline(str(exc)), True
            except (requests.ConnectionError, requests.Timeout, TransportError) as exc:
                if not idempotent:
                    # Anfrage ging raus, Antwort blieb aus: nicht wiederholen (Doppelte).
                    raise NoResponse(f"Keine Antwort von Google ({exc}) – wird beim nächsten "
                                     "Lauf geprüft") from exc
                error, retry = Offline(str(exc)), True
            else:
                if r.status_code < 400:
                    return r
                if r.status_code == 401:
                    raise AuthRequired("Google lehnt die Anmeldung ab (401)")
                try:
                    err = r.json()["error"]
                    msg = err.get("message", "")
                    reasons = {e.get("reason") for e in err.get("errors", [])}
                except (ValueError, KeyError, TypeError, AttributeError):
                    msg, reasons = r.text[:200], set()
                text = f"Drive-Fehler {r.status_code}: {msg}"
                if r.status_code == 404:
                    raise NotFound(text)
                rate_limited = r.status_code == 429 or (
                    r.status_code == 403 and reasons & {"rateLimitExceeded", "userRateLimitExceeded"})
                if not (rate_limited or r.status_code >= 500):
                    raise SyncError(text)
                error = SyncError(text)
                retry = idempotent or rate_limited or r.status_code == 503
            if not retry or attempt == MAX_TRIES:
                raise error
            if self.cancel.wait(min(delay, 32) + random.uniform(0, 0.5)):
                raise Cancelled("abgebrochen")
            delay *= 2
        raise AssertionError("unerreichbar")

    def exists(self, file_id: str) -> bool:
        """Gibt es den Eintrag noch (und liegt er nicht im Papierkorb)?"""
        try:
            info = self._req("GET", f"{API}/files/{file_id}", params={"fields": "id, trashed"}).json()
        except NotFound:
            return False
        return not info.get("trashed", False)

    def list_all(self) -> list[dict]:
        """Alle fuer die App sichtbaren Dateien (drive.file: nur eigene)."""
        items, token = [], None
        while True:
            params = {
                "q": "trashed = false",
                "spaces": "drive",
                "pageSize": 1000,
                "fields": "nextPageToken, files(id, name, mimeType, parents, md5Checksum, modifiedTime, createdTime)",
            }
            if token:
                params["pageToken"] = token
            data = self._req("GET", f"{API}/files", params=params).json()
            items += data.get("files", [])
            token = data.get("nextPageToken")
            if not token:
                return items

    def find_folders(self, name: str) -> list[str]:
        """IDs der eigenen Ordner mit diesem Namen (nicht im Papierkorb)."""
        quoted = name.replace("\\", "\\\\").replace("'", "\\'")
        data = self._req("GET", f"{API}/files", params={
            "q": f"mimeType = '{FOLDER_MIME}' and name = '{quoted}' and trashed = false",
            "spaces": "drive", "fields": "files(id)", "pageSize": 10,
        }).json()
        return [f["id"] for f in data.get("files", [])]

    def create_folder(self, name: str, parent: str | None) -> str:
        meta = {"name": name, "mimeType": FOLDER_MIME}
        if parent:
            meta["parents"] = [parent]
        return self._req("POST", f"{API}/files", params={"fields": "id"}, json=meta).json()["id"]

    def upload(self, path: Path, name: str, parent: str, file_id: str | None) -> dict:
        """Neu anlegen (``file_id`` None) oder Inhalt ersetzen."""
        stat = path.stat()
        mime = guess_mime(name)
        meta = {"name": name, "modifiedTime": rfc3339(stat.st_mtime)}
        if not file_id:
            meta["parents"] = [parent]
        method = "PATCH" if file_id else "POST"
        url = f"{UPLOAD_API}/files" + (f"/{file_id}" if file_id else "")
        fields = "id, md5Checksum, modifiedTime"
        if stat.st_size <= MULTIPART_LIMIT:
            boundary = f"cmd{uuid.uuid4().hex}"
            body = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
                + json.dumps(meta).encode("utf-8")
                + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
                + path.read_bytes()
                + f"\r\n--{boundary}--\r\n".encode()
            )
            return self._req(
                method, url, params={"uploadType": "multipart", "fields": fields}, data=body,
                headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            ).json()
        # Der Start einer resumable Session legt noch keine Datei an -> wiederholbar
        init = self._req(
            method, url, params={"uploadType": "resumable", "fields": fields}, json=meta,
            headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(stat.st_size)},
            idempotent=True,
        )
        # Inhalt als bytes, damit eine Wiederholung ihn erneut senden kann
        return self._req("PUT", init.headers["Location"], data=path.read_bytes(),
                         headers={"Content-Type": mime}).json()

    def upload_chunked(self, path: Path, parent: str, fields: str = "id",
                       on_progress=lambda sent, total: None) -> dict:
        """Neue Datei per resumable Upload in Stuecken -- mit Fortschritt, auch fuer Videos.

        Bleibt die Antwort auf ein Stueck aus, fragt der Client Google nach dem
        angekommenen Stand und macht dort weiter, statt blind neu zu senden.
        """
        size = path.stat().st_size
        mime = guess_mime(path.name)
        meta = {"name": path.name, "parents": [parent], "modifiedTime": rfc3339(path.stat().st_mtime)}
        init = self._req(
            "POST", f"{UPLOAD_API}/files", params={"uploadType": "resumable", "fields": fields},
            json=meta, headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)},
            idempotent=True,
        )
        session_url = init.headers["Location"]
        offset, lost = 0, 0
        on_progress(0, size)
        with path.open("rb") as fh:
            while True:
                fh.seek(offset)
                chunk = fh.read(CHUNK)
                headers = {"Content-Type": mime}
                if chunk:
                    headers["Content-Range"] = f"bytes {offset}-{offset + len(chunk) - 1}/{size}"
                else:  # leere Datei
                    headers["Content-Range"] = f"bytes */{size}"
                try:
                    r = self._req("PUT", session_url, data=chunk, headers=headers, idempotent=False)
                except NoResponse:
                    lost += 1
                    if lost >= MAX_TRIES:
                        raise
                    r = self._req("PUT", session_url, headers={"Content-Range": f"bytes */{size}"},
                                  idempotent=True)
                if r.status_code in (200, 201):
                    on_progress(size, size)
                    return r.json()
                if r.status_code != 308:
                    raise SyncError(f"Unerwartete Antwort beim Hochladen ({r.status_code})")
                # 308 "Resume Incomplete": Range sagt, was angekommen ist
                m = re.match(r"bytes=0-(\d+)", r.headers.get("Range", ""))
                offset = int(m.group(1)) + 1 if m else 0
                on_progress(offset, size)

    def share_anyone(self, file_id: str) -> None:
        """Freigabe "Jeder mit dem Link: Betrachter" (nicht auffindbar per Suche)."""
        # Dieselbe Freigabe zweimal anzulegen schadet nicht -> wiederholbar
        self._req("POST", f"{API}/files/{file_id}/permissions",
                  params={"fields": "id"},
                  json={"type": "anyone", "role": "reader", "allowFileDiscovery": False},
                  idempotent=True)


# ---------------------------------------------------------------------- #
# Datei hochladen und als Link freigeben (CompletionistQR)
# ---------------------------------------------------------------------- #

SHARE_FOLDER = "CompletionistQR Dateien"


def share_link(file_id: str, web_view_link: str = "") -> str:
    """Kurzer Ansehen-Link fuer den QR-Code.

    Googles ``webViewLink`` haengt ``?usp=drivesdk`` an; ohne ist der Code
    kleiner (weniger Module) und der Link oeffnet genauso. Ordner- und
    Docs-Links bleiben, wie Google sie liefert.
    """
    if web_view_link and "/file/d/" not in web_view_link:
        return web_view_link
    return f"https://drive.google.com/file/d/{file_id}/view"


def share_folder_id(client, name: str = SHARE_FOLDER) -> str:
    """Zielordner in Drive (bei drive.file nur selbst angelegte sichtbar), sonst neu anlegen."""
    for fid in client.find_folders(name):
        if client.exists(fid):
            return fid
    return client.create_folder(name, None)


def upload_and_share(client, path: Path, on_progress=lambda sent, total: None,
                     folder: str = SHARE_FOLDER) -> str:
    """Laedt ``path`` hoch, gibt ihn fuer "Jeder mit dem Link" frei und liefert den Link."""
    path = Path(path)
    if not path.is_file():
        raise SyncError(f"Datei nicht gefunden: {path}")
    parent = share_folder_id(client, folder)
    info = client.upload_chunked(path, parent, fields="id, webViewLink", on_progress=on_progress)
    client.share_anyone(info["id"])
    return share_link(info["id"], info.get("webViewLink", ""))
