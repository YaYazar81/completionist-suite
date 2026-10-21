"""CompletionistMD im echten Fenster: Suchen/Ersetzen, Gliederung, Strg+V mit
Bild, Aenderungen von aussen, aeltere Fassungen."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Ohne Bildschirm hat Chromium keinen GPU-Kontext und stuerzt beim Beenden ab
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mdeditor import markdown_io  # noqa: E402
from mdeditor.window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_KEEP_ALIVE: list = []


@pytest.fixture(scope="module")
def qapp():
    # QtWebEngine braucht einen Programmnamen in argv, sonst stuerzt Chromium ab
    app = QApplication.instance() or QApplication(["pytest"])
    _KEEP_ALIVE.append(app)  # QApplication darf vor QtWebEngine nicht verschwinden
    yield app


def wait_for(app, condition, seconds: float = 8) -> bool:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return bool(condition())


def settle(app, seconds: float = 0.6) -> None:
    wait_for(app, lambda: False, seconds)


def js(app, tab, script):
    box = {}
    tab.view.run(script, lambda r: box.setdefault("r", r))
    wait_for(app, lambda: "r" in box)
    return box.get("r")


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    # Ein Fenster fuer alle Tests: QtWebEngine vertraegt das wiederholte
    # Anlegen und Abraeumen ganzer Fenster in einem Prozess schlecht.
    old = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp_path_factory.mktemp("appdata"))
    win = MainWindow(ROOT, secondary=True)
    win.resize(1000, 700)
    win.show()
    yield win
    win.hide()
    # Nicht abraeumen: das Zerstoeren von QWebEngineView mitten im Lauf bringt
    # Chromium zum Absturz. Der Prozess endet ohnehin hart (conftest.py).
    _KEEP_ALIVE.append(win)
    if old is not None:
        os.environ["APPDATA"] = old


@pytest.fixture
def window(qapp, main_window, tmp_path):
    win = main_window
    doc = tmp_path / "notiz.md"
    doc.write_text("# Titel\n\nApfel und Birne.\n\n## Unterpunkt\n\nNoch ein Apfel.\n", encoding="utf-8")
    tab = win._md
    assert wait_for(qapp, lambda: tab.ready)
    win._load_md(tab, doc)
    assert wait_for(qapp, lambda: tab.file is not None and tab.file.path == doc and not tab.loading)
    settle(qapp)
    yield win, tab, doc
    win._flush_save(tab)
    win._show_welcome(tab)
    settle(qapp, 0.2)


def test_find_and_replace(qapp, window):
    win, tab, doc = window
    res = js(qapp, tab, "CM.find('apfel', false)")
    assert res["count"] == 2
    res = js(qapp, tab, "CM.findNext(1)")
    assert res["index"] == 1
    js(qapp, tab, "CM.find('Apfel', true)")
    js(qapp, tab, "CM.replaceAll('Kirsche')")
    assert wait_for(qapp, lambda: "Kirsche und Birne" in doc.read_text(encoding="utf-8"))
    assert "Apfel" not in doc.read_text(encoding="utf-8")


def test_outline_lists_headings(qapp, window):
    win, tab, doc = window
    items = js(qapp, tab, "CM.outline()")
    assert [(i["level"], i["text"]) for i in items] == [(1, "Titel"), (2, "Unterpunkt")]
    win.toggle_outline()
    assert wait_for(qapp, lambda: win.outline_panel.tree.topLevelItemCount() == 1)


def test_ctrl_v_with_image_lands_in_images_folder(qapp, window):
    win, tab, doc = window
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    QGuiApplication.clipboard().setImage(img)
    tab.view.setFocus()
    js(qapp, tab, "CM.focusEditor('end')")
    target = tab.view.focusProxy() or tab.view
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(target, QKeyEvent(kind, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier, "v"))
    folder = doc.parent / "images"
    assert wait_for(qapp, lambda: folder.is_dir() and any(folder.iterdir()))
    assert wait_for(qapp, lambda: "images/notiz-001.png" in doc.read_text(encoding="utf-8"))


def test_external_change_reloads_clean_tab(qapp, window):
    win, tab, doc = window
    time.sleep(0.05)
    doc.write_text("# Von außen\n\nNeuer Text.\n", encoding="utf-8")
    assert wait_for(qapp, lambda: "Neuer Text." in (js(qapp, tab, "CM.getMarkdown()") or ""), 6)
    assert not tab.dirty


def test_own_saves_are_not_reported_as_external(qapp, window, monkeypatch):
    win, tab, doc = window
    asked = []
    monkeypatch.setattr(win, "_ask_conflict", lambda p: asked.append(p) or True)
    js(qapp, tab, "CM.exec('text', 'Getippt ')")
    assert wait_for(qapp, lambda: "Getippt" in doc.read_text(encoding="utf-8"))
    settle(qapp, 1.0)
    assert asked == []


def test_save_keeps_older_version(qapp, window, monkeypatch):
    win, tab, doc = window
    monkeypatch.setattr(markdown_io, "SNAPSHOT_INTERVAL", 0)
    before = doc.read_text(encoding="utf-8")
    js(qapp, tab, "CM.exec('text', 'Neu ')")
    assert wait_for(qapp, lambda: "Neu " in doc.read_text(encoding="utf-8"))
    snaps = markdown_io.snapshots(doc)
    assert snaps and snaps[0].read_text(encoding="utf-8") == before
    assert snaps[0].parent.parent.parent.name == ".completionistmd"
    assert not list(doc.parent.glob(".*.tmp"))  # keine Zwischendatei liegen geblieben
