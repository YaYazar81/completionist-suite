"""CompletionistQR Online nutzt den Gestalter von CompletionistQR: gleiche Bedienleiste, gleicher Export,
der Kurzlink als fester Inhalt, das Design je Link gemerkt."""
from __future__ import annotations

import pytest

ctk = pytest.importorskip("customtkinter", exc_type=ImportError)

from qronline import settings  # noqa: E402
from qronline.client import Link  # noqa: E402

LINK = Link(code="A7KX9P", target="https://example.org/ziel", label="Flyer", created="2026-10-27",
            scans=3, last_scan=None, url="https://c10t.de/A7KX9P")


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        r = ctk.CTk()
    except Exception as exc:  # kein Bildschirm
        pytest.skip(f"Tk nicht verfuegbar: {exc}")
    r.withdraw()
    yield r
    r.destroy()


def pump(widget, n=20):
    for _ in range(n):
        widget.update()


def test_design_window_uses_completionistqr_with_short_link(root, tmp_path):
    from completionistqr.core import export
    from completionistqr.ui.controls import Controls
    from qronline.design import DesignWindow

    prefs: dict = {}
    win = DesignWindow(root, LINK, prefs)
    pump(win)
    assert isinstance(win.controls, Controls)
    assert win.design.payload == LINK.url
    assert win.controls.fixed_var.get() == LINK.url
    # Dieselben Reiter wie in CompletionistQR
    assert list(win.controls._name_list) == ["Inhalt", "Design", "Logo", "Beschriftung", "Export"]
    assert win.export_name == "qr-A7KX9P"

    # Vorlage wie in CompletionistQR anwenden, dann als SVG speichern
    from completionistqr.core import presets
    win.apply_preset(presets.builtin()["Scan-Me Banner"])
    assert win.design.payload == LINK.url and win.design.caption
    out = export.save(win.design, tmp_path / "qr.svg", width_px=512)
    assert "<svg" in out.read_text(encoding="utf-8")

    # Beim Schliessen merkt sich CompletionistQR Online das Design fuer diesen Link
    win.close()
    assert prefs["designs"][LINK.code]["frame"] == win.design.frame
    assert settings.load()["designs"][LINK.code] == prefs["designs"][LINK.code]

    # Ein zweites Oeffnen beginnt mit dem gemerkten Design
    again = DesignWindow(root, LINK, prefs)
    pump(again)
    assert again.design.frame == prefs["designs"][LINK.code]["frame"]
    assert again.design.payload == LINK.url
    again.destroy()


def test_about_window_shows_qr_online(root):
    from completionistqr.ui.about import AboutWindow
    from qronline import __version__
    from qronline.design import about_info

    win = AboutWindow(root, **about_info())
    pump(win)
    assert win.title() == "Über CompletionistQR Online"
    texts = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, ctk.CTkLabel):
                texts.append(c.cget("text"))
            walk(c)
    walk(win)
    assert any(f"Version {__version__}" in t for t in texts)
    win.destroy()


def test_settings_move_from_old_name(tmp_path, monkeypatch):
    """Bis 1.1 hiess das Programm QR-Online: dessen Einstellungen werden übernommen."""
    import json

    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "QR-Online"
    old.mkdir()
    (old / "settings.json").write_text(json.dumps({"base_url": "https://c10t.de",
                                                   "designs": {"A7KX9P": {"frame": "card"}}}))
    data = settings.load()
    assert data["base_url"] == "https://c10t.de" and data["designs"]["A7KX9P"]["frame"] == "card"
    assert (tmp_path / "CompletionistQR Online" / "settings.json").is_file()
    settings.save({**data, "range": "7 Tage"})
    assert json.loads((old / "settings.json").read_text())["base_url"] == "https://c10t.de"  # alt bleibt
    assert settings.load()["range"] == "7 Tage"


class FakeClient:
    """Statt des Servers: zählt Instanzen und Aufrufe."""
    instances = 0

    def __init__(self, base_url, api_key, **_kw):
        FakeClient.instances += 1
        self.base_url, self.api_key = base_url.strip().rstrip("/"), api_key.strip()
        self.calls: list[str] = []
        self.rows = [Link(code=c, target=f"https://example.org/{c}", label=f"Link {c}",
                          created="2026-10-27", scans=i, last_scan=None, url=f"https://c10t.de/{c}")
                     for i, c in enumerate(("AAAAAA", "BBBBBB", "CCCCCC"))]

    def links(self):
        self.calls.append("links")
        return list(self.rows)

    def scans(self, code, since=None):
        self.calls.append(f"scans {code}")
        return []

    def update(self, code, target=None, label=None):
        self.calls.append(f"update {code}")
        old = next(r for r in self.rows if r.code == code)
        return Link(code=code, target=target or old.target, label=label or "", created=old.created,
                    scans=old.scans, last_scan=None, url=old.url)


def test_app_reuses_connection_and_avoids_reloads(tmp_path, monkeypatch):
    import time

    from qronline import app as appmod

    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings.save({"base_url": "https://c10t.de", "api_key": "x" * 24})
    FakeClient.instances = 0
    monkeypatch.setattr(appmod, "Client", FakeClient)
    try:
        app = appmod.QROnlineApp()
    except Exception as exc:  # kein Bildschirm
        pytest.skip(f"Tk nicht verfuegbar: {exc}")

    def settle(cond, seconds=5.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not cond():
            app.update()
            time.sleep(0.01)
        assert cond()

    try:
        settle(lambda: len(app._items) == 3 and app._client and "scans AAAAAA" in app._client.calls)
        client = app._client
        item_b = app._items["BBBBBB"][0]

        # Anderen Link waehlen: Liste bleibt stehen, nur die Scans werden geladen
        app.select("BBBBBB")
        settle(lambda: "scans BBBBBB" in client.calls)
        assert app._items["BBBBBB"][0] is item_b
        assert client.calls.count("links") == 1

        # Speichern: die Antwort des Servers reicht, kein Neuladen der Liste
        app.label_var.set("Neuer Name")
        app.save_link()
        settle(lambda: "update BBBBBB" in client.calls and app.current.label == "Neuer Name")
        assert app._items["BBBBBB"][1].cget("text") == "Neuer Name"
        assert client.calls.count("links") == 1
        assert FakeClient.instances == 1  # eine Verbindung fuer die ganze Sitzung

        # Gestalter: einmal gebaut, fuer den naechsten Link wiederverwendet
        app.design_qr()
        win = app._design_window
        win.close()
        app.select("CCCCCC")
        app.design_qr()
        app.update()
        assert app._design_window is win and win.link.code == "CCCCCC"
        assert win.design.payload == "https://c10t.de/CCCCCC"
    finally:
        app.destroy()


def test_server_dialog_prepares_new_server(root, tmp_path, monkeypatch):
    from qronline import server_setup

    folder = tmp_path / "Hochladen"
    folder.mkdir()
    monkeypatch.setattr(server_setup.filedialog, "askdirectory", lambda **_kw: str(folder))
    opened = []
    monkeypatch.setattr(server_setup, "open_folder", opened.append)

    dlg = server_setup.ServerDialog(root, first_start=True)
    pump(dlg)
    key = dlg.key_var.get()
    assert len(key) == 48 and dlg.mode.get() == "new" and dlg.steps.winfo_manager() == "grid"
    dlg.url_var.set("c10t.de/")
    dlg._save_files()
    assert opened == [folder]
    assert f"'api_key' => '{key}'" in (folder / "config.php").read_text(encoding="utf-8")
    dlg._ok()
    assert dlg.result == {"base_url": "https://c10t.de", "api_key": key}


def test_server_dialog_connects_existing(root):
    from qronline import server_setup

    dlg = server_setup.ServerDialog(root, "https://c10t.de", "k" * 32)
    pump(dlg)
    assert dlg.mode.get() == "existing" and dlg.steps.winfo_manager() == ""
    assert dlg.key_var.get() == "k" * 32
    dlg.switch.set("Neuen Server einrichten")
    dlg._mode_changed("Neuen Server einrichten")
    pump(dlg)
    assert dlg.steps.winfo_manager() == "grid"
    dlg.destroy()
