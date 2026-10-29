"""Datei hochladen und freigeben (core/drive.py) mit einer gefälschten Drive-Sitzung.

Kein Netz: ``FakeDrive`` spielt die REST-Antworten von Google nach, so wie
``DriveClient`` sie ueber ``session.request`` bekommt.
"""
from __future__ import annotations

import json
import re
import sys

import pytest

from core import drive

FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeDrive:
    """Nimmt Uploads stueckweise an wie Googles resumable-Protokoll."""

    def __init__(self, folders=(), permission_status=200, lose_chunk=None):
        self.folders = list(folders)
        self.permission_status = permission_status
        self.lose_chunk = lose_chunk  # Nummer des Stuecks, dessen Antwort "verloren geht"
        self.calls: list[tuple[str, str, dict]] = []
        self.received = b""
        self.size = None
        self.meta = None
        self.permissions: list[dict] = []
        self.chunks = 0

    def request(self, method, url, timeout=None, **kw):
        self.calls.append((method, url, kw))
        if method == "GET" and url == f"{drive.API}/files":
            return Resp(body={"files": [{"id": f} for f in self.folders]})
        if method == "GET" and url.startswith(f"{drive.API}/files/"):
            return Resp(body={"id": url.rsplit("/", 1)[1], "trashed": False})
        if method == "POST" and url == f"{drive.API}/files":
            self.folders.append("folder-new")
            return Resp(body={"id": "folder-new"})
        if method == "POST" and url == f"{drive.UPLOAD_API}/files":
            assert kw["params"]["uploadType"] == "resumable"
            self.meta = kw["json"]
            self.size = int(kw["headers"]["X-Upload-Content-Length"])
            return Resp(headers={"Location": "https://upload.example/session-1"})
        if method == "PUT" and url == "https://upload.example/session-1":
            return self._chunk(kw)
        if method == "POST" and url.endswith("/permissions"):
            if self.permission_status != 200:
                return Resp(self.permission_status, {"error": {
                    "message": "Sharing outside of the domain is not allowed",
                    "errors": [{"reason": "cannotShareTeamDriveWithNonGoogleAccounts"}]}})
            self.permissions.append(kw["json"])
            return Resp(body={"id": "anyoneWithLink"})
        raise AssertionError(f"unerwartet: {method} {url}")

    def _chunk(self, kw):
        rng = kw["headers"]["Content-Range"]
        m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", rng)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            assert start == len(self.received), "Stueck nicht dort angesetzt, wo Google steht"
            data = kw["data"]
            assert len(data) == end - start + 1
            self.received += data
            self.chunks += 1
            if self.chunks == self.lose_chunk:
                import requests
                raise requests.ConnectionError("Antwort verloren")
        else:
            assert rng == f"bytes */{self.size}"  # Statusabfrage
        if len(self.received) == self.size:
            return Resp(200, {"id": FILE_ID,
                              "webViewLink": f"https://drive.google.com/file/d/{FILE_ID}/view?usp=drivesdk"})
        headers = {"Range": f"bytes=0-{len(self.received) - 1}"} if self.received else {}
        return Resp(308, headers=headers)


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr(drive, "CHUNK", 256 * 1024)


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "Urlaub 2026.mp4"
    p.write_bytes(bytes(range(256)) * 4000)  # 1 MB -> 4 Stuecke
    return p


def test_share_link_is_short_view_link():
    long = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=drivesdk"
    assert drive.share_link(FILE_ID, long) == f"https://drive.google.com/file/d/{FILE_ID}/view"
    assert drive.share_link(FILE_ID) == f"https://drive.google.com/file/d/{FILE_ID}/view"
    # Google-Docs-Links bleiben, wie Google sie liefert
    doc = "https://docs.google.com/document/d/xyz/edit?usp=drivesdk"
    assert drive.share_link("xyz", doc) == doc


def test_upload_and_share_creates_folder_uploads_in_chunks_and_shares(small_chunks, video):
    fake = FakeDrive()
    progress = []
    link = drive.upload_and_share(drive.DriveClient(session=fake), video,
                                  lambda s, t: progress.append((s, t)))

    assert link == f"https://drive.google.com/file/d/{FILE_ID}/view"
    assert fake.received == video.read_bytes()
    assert fake.chunks == 4
    assert fake.meta["name"] == "Urlaub 2026.mp4" and fake.meta["parents"] == ["folder-new"]
    # Ordner wurde gesucht, nicht gefunden und angelegt
    created = [c for c in fake.calls if c[0] == "POST" and c[1] == f"{drive.API}/files"]
    assert created[0][2]["json"] == {"name": drive.SHARE_FOLDER, "mimeType": drive.FOLDER_MIME}
    # Freigabe: jeder mit dem Link, nur ansehen, nicht ueber die Suche auffindbar
    assert fake.permissions == [{"type": "anyone", "role": "reader", "allowFileDiscovery": False}]
    perm_call = next(c for c in fake.calls if c[1].endswith("/permissions"))
    assert f"/files/{FILE_ID}/permissions" in perm_call[1]
    # Fortschritt steigt bis zur vollen Groesse
    sent = [s for s, _ in progress]
    assert sent == sorted(sent) and sent[-1] == video.stat().st_size
    assert all(t == video.stat().st_size for _, t in progress)


def test_existing_folder_is_reused(small_chunks, video):
    fake = FakeDrive(folders=["folder-old"])
    drive.upload_and_share(drive.DriveClient(session=fake), video)
    assert fake.meta["parents"] == ["folder-old"]
    assert not [c for c in fake.calls if c[0] == "POST" and c[1] == f"{drive.API}/files"]


def test_lost_answer_resumes_where_google_stands(small_chunks, video):
    fake = FakeDrive(lose_chunk=2)
    link = drive.upload_and_share(drive.DriveClient(session=fake), video)
    assert link.endswith("/view")
    assert fake.received == video.read_bytes()  # nichts doppelt, nichts fehlt
    assert any(c[2].get("headers", {}).get("Content-Range") == f"bytes */{fake.size}"
               for c in fake.calls)


def test_small_and_empty_files(tmp_path):
    for data in (b"%PDF-1.7 klein", b""):
        p = tmp_path / "flyer.pdf"
        p.write_bytes(data)
        fake = FakeDrive()
        drive.upload_and_share(drive.DriveClient(session=fake), p)
        assert fake.received == data
        assert fake.permissions


def test_refused_sharing_gives_no_link(small_chunks, video):
    fake = FakeDrive(permission_status=403)
    with pytest.raises(drive.SyncError, match="403"):
        drive.upload_and_share(drive.DriveClient(session=fake), video)


def test_cancel_stops_before_upload(video):
    client = drive.DriveClient(session=FakeDrive())
    client.cancel.set()
    with pytest.raises(drive.Cancelled):
        drive.upload_and_share(client, video)


def test_missing_file(tmp_path):
    with pytest.raises(drive.SyncError, match="nicht gefunden"):
        drive.upload_and_share(drive.DriveClient(session=FakeDrive()), tmp_path / "weg.pdf")


def test_drive_link_scans_in_every_preset():
    from completionistqr.core import export, payload, presets, render_pil
    from completionistqr.core.config import QRDesign

    link = payload.url(drive.share_link(FILE_ID))
    for name, style in presets.builtin().items():
        img = render_pil.render(QRDesign(payload=link).apply_style(style), 800, supersample=2)
        assert export.decode(img) == link, name


def _imports_without_qt(modules: str) -> None:
    import subprocess

    code = f"import {modules}, sys; print('PySide6' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_core_drive_does_not_pull_in_qt():
    _imports_without_qt("core.drive")


def test_qr_drive_upload_does_not_pull_in_qt():
    # Die QR-Oberflaeche braucht Tk (unter Windows bei Python dabei, unter
    # Linux ein eigenes Paket) und customtkinter -- ohne beides nur ueberspringen.
    import importlib.util

    for mod in ("tkinter", "customtkinter"):
        if importlib.util.find_spec(mod) is None:
            pytest.skip(f"{mod} nicht installiert")
    _imports_without_qt("core.drive, completionistqr.ui.drive_upload")


# ------------------------------------------------------------------ im Fenster


@pytest.mark.skipif(sys.platform != "win32", reason="Fenster nur unter Windows")
def test_upload_panel_puts_link_into_code(tmp_path, monkeypatch, video):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        from completionistqr.app import CompletionistQRApp
        app = CompletionistQRApp()
    except Exception as exc:  # kein Bildschirm
        pytest.skip(f"Tk nicht verfuegbar: {exc}")
    try:
        c = app.controls
        c._content_type_changed("file")
        app.update()
        panel = c.drive_upload
        assert panel.winfo_ismapped()
        link = drive.share_link(FILE_ID)

        def fake_run(path, progress, on_login):  # laeuft im Hintergrund-Thread
            progress(0, 10)
            progress(10, 10)
            return link

        monkeypatch.setattr(panel, "_run", fake_run)
        panel.start(video)
        for _ in range(500):
            app.update()
            if not panel.busy:
                break
            __import__("time").sleep(0.01)
        assert not panel.busy
        assert app.design.payload == link
        assert c.payload_error.cget("text") == ""
        assert "hochgeladen" in panel.status.cget("text")
        # anderer Inhaltstyp: Knopf verschwindet
        c._content_type_changed("url")
        app.update()
        assert not panel.winfo_ismapped()
    finally:
        app.destroy()
