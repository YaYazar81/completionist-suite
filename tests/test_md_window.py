"""CompletionistMD im echten Fenster: Suchen/Ersetzen, Gliederung, Strg+V mit
Bild, Aenderungen von aussen, aeltere Fassungen."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Ohne Bildschirm hat Chromium keinen GPU-Kontext und stuerzt beim Beenden ab
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
# Als root (Linux-Container, CI) startet Chromium nur ohne eigene Sandbox
if getattr(os, "geteuid", lambda: 1)() == 0:
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

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


def test_clicking_around_does_not_touch_the_file(qapp, window):
    """Nur echte Aenderungen speichern -- auch nicht "neu formatiert" beim
    Schliessen, wenn der Editor das Markdown anders schreiben wuerde."""
    win, tab, doc = window
    raw = "# Titel\n\n* Punkt eins\n* Punkt zwei\n\n## **Fett** im Titel\n\nText __dick__.\n"
    doc.write_text(raw, encoding="utf-8")
    win._load_md(tab, doc, flush=False)
    assert wait_for(qapp, lambda: not tab.loading)
    settle(qapp)
    stamp = doc.stat().st_mtime_ns
    for heading in ("Fett", "Titel"):
        js(qapp, tab, f"(()=>{{const o=CM.outline().find(i=>i.text.includes('{heading}'));"
                      "CM.gotoPos(o.pos + 3); CM.focusEditor();})()")
        settle(qapp, 0.5)
    assert not tab.dirty
    win._flush_save(tab)
    assert doc.read_text(encoding="utf-8") == raw
    assert doc.stat().st_mtime_ns == stamp


def test_bold_heading_keeps_its_level_after_leaving_it(qapp, window):
    win, tab, doc = window
    doc.write_text("Davor\n\n## **Überschrift**\n\nDanach\n", encoding="utf-8")
    win._load_md(tab, doc, flush=False)
    assert wait_for(qapp, lambda: not tab.loading)
    settle(qapp)
    js(qapp, tab, "(()=>{const o=CM.outline()[0]; CM.gotoPos(o.pos + 4); CM.focusEditor();})()")
    settle(qapp, 0.3)
    js(qapp, tab, "CM.focusEditor('end')")
    settle(qapp, 0.3)
    assert "## **Überschrift**" in js(qapp, tab, "CM.getMarkdown()")


def press(app, tab, *keys) -> None:
    """Tasten an den Editor schicken: Qt.Key oder ein einzelnes Zeichen."""
    target = tab.view.focusProxy() or tab.view
    for key in keys:
        text = key if isinstance(key, str) else ""
        code = Qt.Key(ord(text.upper())) if text else key
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(kind, code, Qt.KeyboardModifier.NoModifier, text))
        settle(app, 0.05)


def load_text(qapp, win, tab, doc, text: str) -> None:
    doc.write_text(text, encoding="utf-8")
    win._load_md(tab, doc, flush=False)
    assert wait_for(qapp, lambda: not tab.loading)
    settle(qapp)
    tab.view.setFocus()


def test_dash_before_bold_text_becomes_a_list(qapp, window):
    """Tippt man "- " vor "**Begriff**", entsteht eine Liste, nicht "\\- **Begriff**"."""
    win, tab, doc = window
    load_text(qapp, win, tab, doc, "Davor\n\n**Begriff**: Erklärung\n\nDanach\n")
    js(qapp, tab, "(()=>{CM.gotoPos(7); CM.focusEditor();})()")
    settle(qapp, 0.2)
    press(qapp, tab, Qt.Key.Key_Home, "-", " ")
    js(qapp, tab, "CM.focusEditor('end')")
    settle(qapp, 0.2)
    assert "\n- **Begriff**: Erklärung\n" in js(qapp, tab, "CM.getMarkdown()")


def test_undo_restores_deleted_heading_hashes(qapp, window):
    """Rauten geloescht, Zeile verlassen, Rueckgaengig: wieder "## ", nicht "\\##"."""
    win, tab, doc = window
    load_text(qapp, win, tab, doc, "Davor\n\n## Überschrift\n\nDanach\n")
    js(qapp, tab, "(()=>{const o=CM.outline()[0]; CM.gotoPos(o.pos + 4); CM.focusEditor();})()")
    settle(qapp, 0.2)
    press(qapp, tab, Qt.Key.Key_Home, Qt.Key.Key_Delete, Qt.Key.Key_Delete, Qt.Key.Key_Delete)
    js(qapp, tab, "CM.focusEditor('end')")
    settle(qapp, 0.2)
    assert "\n## " not in js(qapp, tab, "CM.getMarkdown()")
    for _ in range(3):
        js(qapp, tab, "CM.undo()")
    js(qapp, tab, "CM.focusEditor('end')")
    settle(qapp, 0.2)
    assert "\n## Überschrift\n" in js(qapp, tab, "CM.getMarkdown()")


def test_dropping_markdown_file_on_editor_is_caught(qapp, window, tmp_path):
    # Der Drop landet im internen Kindwidget von QWebEngineView; der Filter
    # sitzt dort (kein Anwendungsfilter mehr, siehe mdeditor/webview.py).
    from PySide6.QtCore import QMimeData, QObject, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    win, tab, doc = window
    other = tmp_path / "andere.md"
    other.write_text("# Andere\n", encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(other))])
    target = tab.view.focusProxy()
    assert target is not None and target is not tab.view
    got, reached_view = [], []

    class Probe(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            if event.type() == QEvent.Type.Drop:
                reached_view.append(obj)
            return False

    probe = Probe()
    tab.view.installEventFilter(probe)
    tab.view.markdownDropped.connect(got.append)
    try:
        enter = QDragEnterEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, enter)
        assert enter.isAccepted()
        drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, drop)
    finally:
        tab.view.markdownDropped.disconnect(got.append)
        tab.view.removeEventFilter(probe)
    assert len(got) == 1 and [str(p) for p in got[0]] == [str(other)]
    # Schon im Kindwidget abgefangen (dort nimmt Chromium echte Drops sonst an),
    # nicht erst, wenn Qt den Drop an die Ansicht weiterreicht
    assert reached_view == []


def _png(path: Path, color: str) -> Path:
    img = QImage(20, 20, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    assert img.save(str(path))
    return path


def test_single_click_shows_images_in_one_preview_tab(qapp, window, tmp_path):
    win, tab, doc = window
    a = _png(tmp_path / "a.png", "red")
    b = _png(tmp_path / "b.png", "blue")
    count = win.tabs.count()
    win.vault_panel.openFile.emit(str(a))
    assert win.tabs.count() == count + 1
    preview = win.current_tab()
    assert preview.path == a
    index = win.tabs.indexOf(preview)
    # Der naechste Einfachklick ersetzt die Vorschau an derselben Stelle
    win.vault_panel.openFile.emit(str(b))
    assert win.tabs.count() == count + 1
    assert win.current_tab().path == b and win.tabs.indexOf(win.current_tab()) == index
    # Doppelklick auf die Vorschau macht sie zum festen Tab ...
    win.vault_panel.openInNewTab.emit(str(b))
    assert win.tabs.count() == count + 1
    # ... der naechste Einfachklick oeffnet daher eine neue Vorschau
    win.vault_panel.openFile.emit(str(a))
    assert win.tabs.count() == count + 2
    for t in [t for t in win.all_tabs() if t.path in (a, b)]:
        win.close_tab(t)
    assert win._preview is None


def _wait_for_row(qapp, panel, path: Path):
    assert wait_for(qapp, lambda: panel._proxy_index(str(path)).isValid())
    return panel._proxy_index(str(path))


def test_vault_folder_expands_on_single_click(qapp, window, tmp_path):
    win, tab, doc = window
    panel = win.vault_panel
    (tmp_path / "Ordner").mkdir()
    (tmp_path / "Ordner" / "drin.md").write_text("# x\n", encoding="utf-8")
    panel.set_root(str(tmp_path))
    idx = _wait_for_row(qapp, panel, tmp_path / "Ordner")
    assert not panel.tree.isExpanded(idx)
    panel._on_clicked(idx)
    assert panel.tree.isExpanded(idx)
    panel._on_clicked(idx)
    assert not panel.tree.isExpanded(idx)
    # Einfachklick auf ein Bild oeffnet es (nach dem Doppelklick-Intervall)
    img = _png(tmp_path / "bild.png", "red")
    panel._on_clicked(_wait_for_row(qapp, panel, img))
    assert wait_for(qapp, lambda: win.current_tab().path == img, 3)
    win.close_tab(win.current_tab())


def test_vault_menu_offers_system_open_for_all_types(qapp, window, tmp_path):
    win, tab, doc = window
    panel = win.vault_panel
    files = [_png(tmp_path / "bild.png", "red"), tmp_path / "notiz.txt", tmp_path / "text.md"]
    files[1].write_text("x", encoding="utf-8")
    files[2].write_text("# x\n", encoding="utf-8")
    panel.set_root(str(tmp_path))
    for f in files:
        idx = _wait_for_row(qapp, panel, f)
        panel.tree.scrollTo(idx)
        menu = panel.build_tree_menu(panel.tree.visualRect(idx).center())
        texts = [a.text() for a in menu.actions()]
        assert {"Öffnen", "Hier öffnen", "In neuem Tab öffnen"} <= set(texts), (f.name, texts)


def test_outline_is_visible_by_default_and_highlights_current_section(qapp, window, tmp_path):
    win, tab, doc = window
    assert win.a_outline.isChecked() == win.outline_panel.isVisible()
    if not win.outline_panel.isVisible():
        win.toggle_outline()  # ein frueherer Test hat sie ausgeblendet
    long_doc = tmp_path / "kapitel.md"
    parts = ["# Kapitel"]
    for i in range(1, 6):
        parts.append(f"## Abschnitt {i}")
        parts += [f"Absatz {i}.{k} mit etwas Text, damit die Seite lang wird." for k in range(25)]
    long_doc.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    win._load_md(tab, long_doc)
    assert wait_for(qapp, lambda: tab.file is not None and tab.file.path == long_doc and not tab.loading)
    assert wait_for(qapp, lambda: win.outline_panel.tree.topLevelItemCount() == 1)

    # Cursor in Abschnitt 3 -> Abschnitt 3 ist hervorgehoben
    items = js(qapp, tab, "CM.outline()")
    pos3 = next(i["pos"] for i in items if i["text"] == "Abschnitt 3")
    tab.view.call("gotoPos", pos3 + 5)
    assert wait_for(qapp, lambda: win.outline_panel.current_text() == "Abschnitt 3")

    # Weggescrollt (Cursor nicht mehr zu sehen): die oberste Ueberschrift im Sichtfeld
    js(qapp, tab, "(window.scrollTo(0, document.body.scrollHeight), true)")
    assert wait_for(qapp, lambda: win.outline_panel.current_text() == "Abschnitt 5")
    win._load_md(tab, doc)
    assert wait_for(qapp, lambda: tab.file is not None and tab.file.path == doc and not tab.loading)


def test_source_view_shows_markdown_and_follows_editor(qapp, window):
    win, tab, doc = window
    win.set_view_mode("source")
    try:
        assert tab.source.isVisible() and not tab.view.isVisible()
        assert wait_for(qapp, lambda: "## Unterpunkt" in tab.source.toPlainText())
        win.set_view_mode("split")
        assert tab.source.isVisible() and tab.view.isVisible()
        # Getippt im WYSIWYG-Editor: der Quelltext zieht nach der Tipp-Pause nach
        tab.view.setFocus()
        js(qapp, tab, "CM.gotoPos(0) || CM.exec('text', 'Neu ')")
        assert wait_for(qapp, lambda: "Neu Titel" in tab.source.toPlainText())
    finally:
        win.set_view_mode("wysiwyg")


def test_typing_in_source_reaches_editor_and_file(qapp, window):
    win, tab, doc = window
    win.set_view_mode("split")
    try:
        assert wait_for(qapp, lambda: "Apfel und Birne." in tab.source.toPlainText())
        tab.source.setFocus()
        cur = tab.source.textCursor()
        text = tab.source.toPlainText()
        cur.setPosition(text.index("Birne"))
        cur.insertText("**Kiwi** ")
        tab.source.setTextCursor(cur)
        # nicht sofort -- erst nach der Tipp-Pause
        assert "Kiwi" not in js(qapp, tab, "CM.getMarkdown()")
        assert wait_for(qapp, lambda: "Apfel und **Kiwi** Birne." in doc.read_text(encoding="utf-8"))
        assert "**Kiwi**" in js(qapp, tab, "CM.getMarkdown()")
        # Der Schritt ist im Editor rueckgaengig zu machen
        js(qapp, tab, "CM.undo()")
        assert wait_for(qapp, lambda: "Kiwi" not in js(qapp, tab, "CM.getMarkdown()"))
    finally:
        win.set_view_mode("wysiwyg")


def test_toolbar_commands_and_find_work_in_source(qapp, window):
    win, tab, doc = window
    win.set_view_mode("source")
    try:
        assert wait_for(qapp, lambda: "Apfel und Birne." in tab.source.toPlainText())
        cur = tab.source.textCursor()
        start = tab.source.toPlainText().index("Birne")
        cur.setPosition(start)
        cur.setPosition(start + len("Birne"), cur.MoveMode.KeepAnchor)
        tab.source.setTextCursor(cur)
        win._exec("bold")
        assert "Apfel und **Birne**." in tab.source.toPlainText()
        cur = tab.source.textCursor()
        cur.setPosition(tab.source.toPlainText().index("Noch ein"))
        tab.source.setTextCursor(cur)
        win._exec("h3")
        assert "### Noch ein Apfel." in tab.source.toPlainText()
        win._find("apfel", False)
        assert tab.source.textCursor().selectedText() == "Apfel"
        win._flush_save(tab)  # wartet nicht auf die Tipp-Pause
        assert "### Noch ein Apfel." in doc.read_text(encoding="utf-8")
    finally:
        win.set_view_mode("wysiwyg")


def test_split_sides_can_be_swapped_and_are_remembered(qapp, window):
    win, tab, doc = window
    win.set_view_mode("split")
    try:
        assert tab.split.widget(1) is tab.source
        win.swap_view_sides()
        assert tab.split.widget(0) is tab.source and tab.split.widget(1) is tab.view
        settings = win._settings
        assert settings["view_mode"] == "split" and settings["source_first"] is True
        win.swap_view_sides()
        assert tab.split.widget(1) is tab.source
    finally:
        win.set_view_mode("wysiwyg")
    assert win._settings["view_mode"] == "wysiwyg"


def test_outline_jump_scrolls_source(qapp, window):
    win, tab, doc = window
    body = "# Anfang\n\n" + "".join(f"Zeile {i}\n\n" for i in range(200)) + "## Ende\n\nSchluss.\n"
    doc.write_text(body, encoding="utf-8")
    win._load_md(tab, doc, flush=False)
    win.set_view_mode("source")
    try:
        assert wait_for(qapp, lambda: "## Ende" in tab.source.toPlainText())
        assert wait_for(qapp, lambda: win.outline_panel.index_of(-1) == -1 and len(win.outline_panel._sig or []) == 2)
        pos = win.outline_panel._sig[1][2]
        win._outline_jump(pos)
        assert tab.source.textCursor().block().text() == "## Ende"
        assert tab.source.verticalScrollBar().value() > 0
    finally:
        win.set_view_mode("wysiwyg")


def test_replace_markdown_matches_fresh_load(qapp, window):
    """CM.replaceMarkdown ersetzt nur den geaenderten Bereich -- das Ergebnis
    muss trotzdem genau dem frisch geladenen Dokument entsprechen."""
    win, tab, doc = window
    variants = [
        "# Titel\n\nApfel und Birne.\n\n## Unterpunkt\n\nNoch ein Apfel.\n",
        "# Titel\n\nApfel und Birne.\n\nApfel und Birne.\n\n## Unterpunkt\n\nNoch ein Apfel.\n",
        "# Titel\n\nApfel und Birne.\n",
        "- eins\n- zwei\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n```py\nx = 1\n```\n",
        "- eins\n- zwei\n- drei\n\n| a | b |\n| --- | --- |\n| 1 | 3 |\n\n```py\nx = 2\n```\n",
        "",
        "Nur ein Satz mit **fett** und *kursiv*.\n",
    ]
    for md in variants:
        js(qapp, tab, f"CM.replaceMarkdown({json.dumps(md)})")
        got = js(qapp, tab, "CM.getMarkdown()")
        expected = js(qapp, tab, f"(() => {{ const keep = CM.getMarkdown(); "
                                 f"CM.setMarkdown({json.dumps(md)}, ''); const r = CM.getMarkdown(); "
                                 f"CM.setMarkdown(keep, ''); return r; }})()")
        assert got == expected, md


def test_code_block_containing_fence_survives_reload(qapp, window):
    """Ein Codeblock mit ``` darin wird mit ```` umzaeunt -- und muss beim
    Laden auch erst an ```` enden."""
    win, tab, doc = window
    md = "````\n```py\nx = 1\n```\n````\n\nDanach.\n"
    js(qapp, tab, f"CM.setMarkdown({json.dumps(md)}, '')")
    assert js(qapp, tab, "CM.getMarkdown()") == md


def test_replace_markdown_random_edits_follow_source(qapp, window):
    """Zufaellige Aenderungen im Quelltext: das nur teilweise neu geparste
    Dokument muss dem frisch geladenen entsprechen -- oder, wo der frische
    Parse den Quelltext selbst nicht trifft (exotische Escapes), dem Quelltext."""
    win, tab, doc = window
    script = r"""(() => {
      let seed = 11; const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
      const pieces = ["# Titel", "## Abschnitt", "Ein Absatz mit **fett**.", "- eins\n- zwei", "- [ ] auf\n- [x] zu",
        "1. a\n2. b", "> Zitat\n> weiter", "```js\nx = 1\n\ny = 2\n```", "| a | b |\n| --- | --- |\n| 1 | 2 |",
        "---", "***", "![Bild](images/a.png)", "<div>html</div>", "Zeile eins\nZeile zwei", "~~~\ncode\n~~~"];
      const inserts = ["\n\n", "\n", "```", "# ", "- ", "| x |", "\n\n```\n", "a", "**", "> ", "1. ", "~~~"];
      const bad = [];
      for (let round = 0; round < 12; round++) {
        let md = "";
        for (let i = 0, n = 3 + rnd(10); i < n; i++) md += pieces[rnd(pieces.length)] + "\n\n";
        CM.setMarkdown(md, "");
        for (let step = 0; step < 15; step++) {
          const cur = CM.getMarkdown();
          const pos = rnd(cur.length + 1);
          const op = rnd(3);
          const next = op === 0 ? cur.slice(0, pos) + inserts[rnd(inserts.length)] + cur.slice(pos)
            : op === 1 ? cur.slice(0, pos) + cur.slice(pos + 1 + rnd(8))
            : cur.slice(0, pos) + pieces[rnd(pieces.length)] + cur.slice(pos);
          CM.replaceMarkdown(next);
          const got = CM.getMarkdown();
          CM.setMarkdown(next, "");
          const want = CM.getMarkdown();
          if (got !== want) {
            const lines = new Set(next.split("\n"));
            const wantLines = new Set(want.split("\n"));
            const extra = got.split("\n").filter((l) => !wantLines.has(l) && !lines.has(l));
            if (extra.length) bad.push({ next, got, want });
          }
        }
      }
      return bad.slice(0, 2);
    })()"""
    assert js(qapp, tab, script) == []
