"""QR-Online nutzt den Gestalter von CompletionistQR: gleiche Bedienleiste, gleicher Export,
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

    # Beim Schliessen merkt sich QR-Online das Design fuer diesen Link
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
    assert win.title() == "Über QR-Online"
    texts = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, ctk.CTkLabel):
                texts.append(c.cget("text"))
            walk(c)
    walk(win)
    assert any(f"Version {__version__}" in t for t in texts)
    win.destroy()
