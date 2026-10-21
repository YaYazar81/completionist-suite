"""CompletionistQR im echten Fenster: alle Inhaltstypen, Kopieren, Design merken."""
from __future__ import annotations

import json
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Zwischenablage und Fenster nur unter Windows")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        from completionistqr.app import CompletionistQRApp
        a = CompletionistQRApp()
    except Exception as exc:  # kein Bildschirm (z. B. CI)
        pytest.skip(f"Tk nicht verfuegbar: {exc}")
    a.update()
    yield a
    try:
        a.destroy()
    except Exception:
        pass


def pump(app, n=20):
    for _ in range(n):
        app.update()


def test_every_content_type_builds_a_payload(app):
    from completionistqr.ui.controls import CONTENT_LABELS, FIELDS

    c = app.controls
    samples = {"url": "example.org", "text": "Hallo", "ssid": "Netz", "first": "Max",
               "address": "a@b.de", "number": "+49 170 1234567", "name": "Max Mustermann",
               "iban": "DE89370400440532013000", "amount": "5", "handle": "max", "link": "example.org/x",
               "lat": "52.5", "lon": "13.4", "paypal": "max"}
    for ctype in CONTENT_LABELS:
        c._content_type_changed(ctype)
        for key, _label, kind in FIELDS[ctype]:
            if key in samples and kind in ("entry", "multi"):
                c._var(ctype, key, kind).set(samples[key])
        pump(app)
        assert c.payload_error.cget("text") == "", ctype
        assert app.design.payload, ctype


def test_copy_puts_png_on_clipboard(app):
    from PIL import ImageGrab

    app.controls.copy()
    img = ImageGrab.grabclipboard()
    assert img is not None and img.size[0] >= 512


def test_design_and_content_survive_restart(app, tmp_path):
    from completionistqr.app import CompletionistQRApp

    c = app.controls
    c._content_type_changed("whatsapp")
    c._var("whatsapp", "number", "entry").set("0170 1234567")
    app.design.fg_color = "#123456"
    pump(app)
    app._on_close()
    saved = json.loads((tmp_path / "CompletionistQR" / "settings.json").read_text(encoding="utf-8"))
    assert saved["design"]["fg_color"] == "#123456"

    again = CompletionistQRApp()
    try:
        pump(again)
        assert again.design.fg_color == "#123456"
        assert again.controls.content_type == "whatsapp"
        assert again.design.payload == "https://wa.me/491701234567"
    finally:
        again.destroy()
