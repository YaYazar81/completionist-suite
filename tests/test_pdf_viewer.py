"""Viewer-Modus von CompletionistPDF: PdfFileView und Start mit einer .pdf."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool  # noqa: E402
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["pytest"])  # argv[0] braucht QtWebEngine
    yield app


def make_pdf(path: Path, pages: int, word: str = "Zauberwort") -> Path:
    """Schreibt ein PDF mit ``pages`` Seiten; jede Seite enthaelt ``word``."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    painter = QPainter(writer)
    for i in range(pages):
        if i:
            writer.newPage()
        painter.drawText(200, 400, f"Seite {i + 1} {word}")
    painter.end()
    return path


def process(app, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()


# ---------------------------------------------------------------------- #
# PdfFileView
# ---------------------------------------------------------------------- #


def test_open_and_navigate(qapp, tmp_path):
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.resize(800, 600)
    view.show()  # ohne sichtbaren Viewport rechnet QPdfView mit Mini-Seiten
    assert view.open(make_pdf(tmp_path / "a.pdf", 3))
    assert view.page_count() == 3
    assert view.page_total.text().strip() == "/ 3"

    view.go_to(2)
    process(qapp)
    assert view.current_page() == 2
    assert view.page_spin.value() == 3
    view.prev_page()
    process(qapp)
    assert view.current_page() == 1
    assert view.status_text() == "Seite 2 von 3"


def wait_for(app, condition, seconds: float = 5) -> bool:
    import time

    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return condition()


def test_search_enter_right_after_typing_jumps_to_first_hit(qapp):
    # QPdfWriter schreibt im Offscreen-Betrieb keinen Text -- deshalb das
    # mit Typst erzeugte Beispiel. "Guide" kommt darin zweimal vor.
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.resize(800, 600)
    view.open(ROOT / "examples" / "demo.pdf")
    view.find_edit.setText("Guide")
    view.find_next()  # Enter, bevor die Suche im Hintergrund fertig ist
    assert wait_for(qapp, lambda: view.find_label.text().strip().startswith("1 /"))
    assert wait_for(qapp, lambda: view.search.count() == 2)
    assert view.view.currentSearchResultIndex() == 0

    view.find_next()
    assert view.find_label.text().strip() == "2 / 2"
    view.find_next()  # wieder von vorn
    assert view.find_label.text().strip() == "1 / 2"
    view.find_prev()
    assert view.find_label.text().strip() == "2 / 2"


def test_search_without_hits(qapp):
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.open(ROOT / "examples" / "demo.pdf")
    view.find_edit.setText("gibtsnichtxyz")
    view.find_next()
    assert view.find_label.text().strip() == "sucht …"
    assert wait_for(qapp, lambda: view.find_label.text().strip() == "keine Treffer", 3)
    assert view.search.count() == 0
    # Ein spaeterer Treffer-Suchtext springt nicht wegen des alten Auftrags
    view.find_edit.setText("Guide")
    view._run_search()
    assert wait_for(qapp, lambda: view.search.count() == 2)
    assert view.view.currentSearchResultIndex() == -1


def test_reload_picks_up_new_content_and_keeps_page(qapp, tmp_path):
    from gui.pdf_file_view import PdfFileView

    pdf = make_pdf(tmp_path / "a.pdf", 3)
    view = PdfFileView()
    view.resize(800, 600)
    view.open(pdf)
    view.go_to(1)
    process(qapp)

    # Datei darf waehrend der Anzeige ueberschrieben werden (keine Sperre)
    make_pdf(pdf, 5)
    view.reload()
    process(qapp)
    assert view.page_count() == 5
    assert view.current_page() == 1


def test_broken_reload_keeps_old_document(qapp, tmp_path):
    from gui.pdf_file_view import PdfFileView

    pdf = make_pdf(tmp_path / "a.pdf", 2)
    view = PdfFileView()
    view.open(pdf)
    errors: list[str] = []
    view.load_failed.connect(errors.append)

    pdf.write_bytes(b"%PDF-1.7 halb geschrieben")
    view.reload()
    assert view.page_count() == 2
    assert errors == []  # beim Neuladen still, der naechste Lauf versucht es erneut


def test_open_invalid_file_reports_error(qapp, tmp_path):
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    good = make_pdf(tmp_path / "gut.pdf", 1)
    view.open(good)
    bad = tmp_path / "kaputt.pdf"
    bad.write_bytes(b"kein pdf")
    errors: list[str] = []
    view.load_failed.connect(errors.append)

    assert not view.open(bad)
    assert errors and "kaputt.pdf" in errors[0]
    assert view.path == good
    assert view.page_count() == 1


def test_watcher_reloads_after_external_write(qapp, tmp_path):
    import time

    from gui.pdf_file_view import PdfFileView

    pdf = make_pdf(tmp_path / "a.pdf", 1)
    view = PdfFileView()
    view.open(pdf)
    make_pdf(pdf, 4)
    deadline = time.monotonic() + 5
    while view.page_count() != 4 and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert view.page_count() == 4


def test_default_zoom_is_whole_page(qapp, tmp_path):
    from PySide6.QtPdfWidgets import QPdfView

    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.open(make_pdf(tmp_path / "a.pdf", 2))
    assert view.view.zoomMode() == QPdfView.ZoomMode.FitInView
    assert view._btn_page.isChecked() and not view._btn_width.isChecked()


def white_rows_and_cols(img, x: int, y: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Ausdehnung des weissen Bereichs durch den Punkt (x, y): (oben, unten), (links, rechts)."""
    def white(px, py):
        c = img.pixelColor(px, py)
        return min(c.red(), c.green(), c.blue()) > 245

    top = y
    while top > 0 and white(x, top - 1):
        top -= 1
    bottom = y
    while bottom < img.height() - 1 and white(x, bottom + 1):
        bottom += 1
    left = x
    while left > 0 and white(left - 1, y):
        left -= 1
    right = x
    while right < img.width() - 1 and white(right + 1, y):
        right += 1
    return (top, bottom), (left, right)


@pytest.mark.parametrize("mode", ["page", "width", "custom"])
def test_page_rects_match_rendering(qapp, tmp_path, mode):
    # Leere weisse Seiten: der weisse Bereich im Bild ist genau die Seite
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.resize(1000, 700)
    view.show()
    view.open(make_pdf(tmp_path / "a.pdf", 3))
    {"page": view.fit_page, "width": view.fit_width, "custom": lambda: view._set_zoom(0.6)}[mode]()
    wait_for(qapp, lambda: False, 0.3)
    view.view.verticalScrollBar().setValue(view.view.verticalScrollBar().maximum() // 3)
    wait_for(qapp, lambda: False, 0.3)

    img = view.view.viewport().grab().toImage()
    visible = [r for r in view.page_rects() if r.top() >= 0 and r.bottom() < img.height()] or \
              [r for r in view.page_rects() if r.bottom() > 0 and r.top() < img.height()]
    rect = visible[0]
    cy = max(0, rect.top()) + 5
    (top, bottom), (left, right) = white_rows_and_cols(img, rect.center().x(), cy)
    assert (left, right) == (rect.left(), rect.right())
    if rect.top() >= 0:
        assert top == rect.top()
    if rect.bottom() < img.height():
        assert bottom == rect.bottom()
    view.close()


def demo_view(qapp):
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.resize(1000, 700)
    view.show()
    view.open(ROOT / "examples" / "demo.pdf")
    wait_for(qapp, lambda: False, 0.3)
    return view


def point_to_viewport(view, page, point):
    from PySide6.QtCore import QPoint

    rect = view.page_rects()[page]
    pt = view.doc.pagePointSize(page)
    return QPoint(rect.left() + round(point.x() * rect.width() / pt.width()),
                  rect.top() + round(point.y() * rect.height() / pt.height()))


def test_click_on_internal_link_jumps(qapp):
    # demo.pdf, Seite 2 (Index 1): Inhaltsverzeichnis; "Zweites Kapitel" fuehrt auf Index 3
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    view = demo_view(qapp)
    view.go_to(1)
    wait_for(qapp, lambda: False, 0.2)
    pos = point_to_viewport(view, 1, QPointF(200, 163))
    link = view.link_at(pos)
    assert link is not None and link.page() == 3

    QTest.mouseClick(view.view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert wait_for(qapp, lambda: view.current_page() == 3)


def test_drag_is_not_a_click(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest

    view = demo_view(qapp)
    view.go_to(1)
    wait_for(qapp, lambda: False, 0.2)
    pos = point_to_viewport(view, 1, QPointF(200, 163))
    vp = view.view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=pos + QPoint(0, 40))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=pos)
    wait_for(qapp, lambda: False, 0.2)
    assert view.current_page() == 1


def test_external_link_opens_only_safe_schemes(qapp, monkeypatch):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QDesktopServices

    import gui.pdf_file_view as pfv

    opened = []
    monkeypatch.setattr(pfv.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    view = demo_view(qapp)
    view.go_to(2)
    wait_for(qapp, lambda: False, 0.2)
    link = view.link_at(point_to_viewport(view, 2, QPointF(250, 148)))
    assert link is not None
    view.follow_link(link)
    assert opened == ["https://typst.app"]
    assert QDesktopServices is pfv.QDesktopServices


def test_toc_sidebar_shows_bookmarks_and_jumps(qapp):
    view = demo_view(qapp)
    assert view.has_bookmarks()
    assert view.toc.isVisible() and view._btn_toc.isChecked()

    titles = [view.bookmarks.index(r, 0).data() for r in range(view.bookmarks.rowCount())]
    assert "Inhaltsverzeichnis" in titles
    kapitel = view.bookmarks.index(titles.index(next(t for t in titles if "Zweites Kapitel" in t)), 0)
    view.toc.clicked.emit(kapitel)
    assert wait_for(qapp, lambda: view.current_page() == 3)

    # Unterkapitel "Tabelle" liegt weiter unten auf Seite 3 (Index 2): Sprung an die Stelle
    willkommen = view.bookmarks.index(next(i for i, t in enumerate(titles) if "Willkommen" in t), 0)
    tabelle = view.bookmarks.index(1, 0, willkommen)
    assert tabelle.data() == "Tabelle"
    view.toc.clicked.emit(tabelle)
    wait_for(qapp, lambda: False, 0.2)
    assert view.current_page() == 2
    page_top = view.page_rects(scrolled=False)[2].top()
    assert view.view.verticalScrollBar().value() > page_top + 100

    view.toggle_sidebar()
    assert not view.toc.isVisible() and not view._btn_toc.isChecked()
    view.reload()  # Neuladen holt die ausgeblendete Leiste nicht zurueck
    assert not view.toc.isVisible()
    view.toggle_sidebar()
    assert view.toc.isVisible()


def test_pdf_without_bookmarks_has_no_sidebar(qapp, tmp_path):
    from gui.pdf_file_view import PdfFileView

    view = PdfFileView()
    view.show()
    view.open(make_pdf(tmp_path / "a.pdf", 2))
    assert not view.has_bookmarks()
    assert not view.toc.isVisible()
    assert not view._btn_toc.isEnabled()
    view.toggle_sidebar()  # F4 ohne Lesezeichen: nichts passiert
    assert not view.toc.isVisible()


# ---------------------------------------------------------------------- #
# Hauptfenster
# ---------------------------------------------------------------------- #


@pytest.fixture
def isolated_session(tmp_path, monkeypatch):
    """Sitzungsdatei in tmp statt unter %APPDATA%."""
    import gui.main_window as mw

    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(mw, "user_data_dir", lambda: data)
    return data


def test_start_with_pdf_skips_typst_and_session(qapp, tmp_path, isolated_session):
    from gui.main_window import MainWindow

    pdf = make_pdf(tmp_path / "Guide.pdf", 2)
    win = MainWindow(ROOT, str(pdf))
    assert win.is_viewer_mode()
    assert win._engine is None  # Typst nicht angefasst
    assert win.settings is None  # Einstellungsleiste nicht gebaut
    from core import __version__
    assert win.windowTitle() == f"Guide.pdf – CompletionistPDF {__version__}"
    assert not win._act_export.isVisible() and not win._act_export.isEnabled()
    assert win._act_refresh.text() == "Neu laden"

    win.close()
    # Ein reiner Viewer-Start ueberschreibt die letzte Sitzung nicht
    assert not (isolated_session / "session.json").exists()


def test_viewer_start_does_not_import_typst(tmp_path):
    # Eigener Prozess: im Testlauf haben andere Tests typst laengst importiert
    import subprocess
    import sys

    pdf = ROOT / "examples" / "demo.pdf"
    code = (
        "import os, sys; os.environ['QT_QPA_PLATFORM'] = 'offscreen'; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "from PySide6.QtWidgets import QApplication; app = QApplication([]); "
        "from gui.main_window import MainWindow; "
        f"w = MainWindow(__import__('pathlib').Path({str(ROOT)!r}), {str(pdf)!r}); "
        "print(w.is_viewer_mode(), 'typst' in sys.modules, 'core.md_converter' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         timeout=60, env={**os.environ, "APPDATA": str(tmp_path)})
    assert out.stdout.split() == ["True", "False", "False"], out.stderr


def test_switch_from_viewer_to_markdown(qapp, tmp_path, isolated_session):
    from gui.main_window import MainWindow

    pdf = make_pdf(tmp_path / "Guide.pdf", 1)
    md = tmp_path / "Guide.md"
    shutil.copyfile(ROOT / "examples" / "demo.md", md)

    win = MainWindow(ROOT, str(pdf))
    win.open_path(str(md))
    assert not win.is_viewer_mode()
    assert win.settings is not None and win._engine is not None
    assert win._act_export.isEnabled()
    assert win._act_refresh.text() == "Neu kompilieren"

    QThreadPool.globalInstance().waitForDone(60000)
    process(qapp)

    # Zurueck in den Viewer, ohne den Markdown-Modus zu verlieren
    win.open_path(str(pdf))
    assert win.is_viewer_mode()
    win.close()
    assert (isolated_session / "session.json").exists()


def test_start_with_broken_pdf_falls_back_to_markdown_mode(qapp, tmp_path, isolated_session, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from gui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    bad = tmp_path / "kaputt.pdf"
    bad.write_bytes(b"kein pdf")
    win = MainWindow(ROOT, str(bad))
    assert not win.is_viewer_mode()
    QThreadPool.globalInstance().waitForDone(60000)
    win.close()


# ---------------------------------------------------------------------- #
# Text markieren und kopieren (core/pdf_select.py)
# ---------------------------------------------------------------------- #

# demo.pdf, Index 1: "Guide" steht bei (184, 109) und ist 33 x 9 Punkte gross
GUIDE_PAGE = 1


def _mouse(vp, kind, pos, buttons):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    button = Qt.MouseButton.LeftButton if kind != QMouseEvent.Type.MouseMove else Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, QPointF(pos), vp.mapToGlobal(QPointF(pos)), button, buttons,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)


def drag(vp, start, end):
    from PySide6.QtCore import QEvent, Qt

    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    _mouse(vp, QEvent.Type.MouseButtonPress, start, left)
    for k in range(1, 6):
        _mouse(vp, QEvent.Type.MouseMove, start + (end - start) * k / 5, left)
    _mouse(vp, QEvent.Type.MouseButtonRelease, end, none)


def test_drag_selects_text_and_ctrl_c_copies_it(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    view = demo_view(qapp)
    view.go_to(GUIDE_PAGE)
    wait_for(qapp, lambda: False, 0.2)
    vp = view.view.viewport()
    drag(vp, point_to_viewport(view, GUIDE_PAGE, QPointF(185, 113)),
         point_to_viewport(view, GUIDE_PAGE, QPointF(218, 113)))
    assert view.selector.text() == "Guide"
    QGuiApplication.clipboard().clear()
    QTest.keyClick(view.view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "Guide"
    # Ein einfacher Klick hebt die Auswahl auf, Esc ebenso
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=point_to_viewport(view, GUIDE_PAGE, QPointF(300, 400)))
    assert view.selector.text() == ""
    view.close()


def test_double_click_selects_word_and_select_all(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    view = demo_view(qapp)
    view.go_to(2)  # Fliesstext, kein Link ("Dies ist ein Testdokument ...")
    wait_for(qapp, lambda: False, 0.2)
    # "Testdokument" ueber die Suche finden; doppelgeklickt wird mitten ins Wort
    hit = view.doc.getSelection(2, QPointF(0, 0), QPointF(0, 0))
    whole = view.doc.getAllText(2).text()
    assert "Testdokument" in whole and not hit.isValid()
    view.find_edit.setText("Testdokument")
    view.find_next()
    assert wait_for(qapp, lambda: view.search.count() > 0)
    rect = view.search.resultAtIndex(0).rectangles()[0]
    QTest.mouseDClick(view.view.viewport(), Qt.MouseButton.LeftButton,
                      pos=point_to_viewport(view, 2, rect.center()))
    assert view.selector.text() == "Testdokument"
    QTest.keyClick(view.view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    text = view.selector.text()
    assert "Zweites Kapitel" in text and "\r" not in text
    QTest.keyClick(view.view, Qt.Key.Key_Escape)
    assert view.selector.text() == ""
    view.close()


def test_selection_runs_across_pages(qapp):
    from PySide6.QtCore import QPointF

    view = demo_view(qapp)
    view.fit_width()
    view.go_to(GUIDE_PAGE, QPointF(0, 780))
    wait_for(qapp, lambda: False, 0.3)
    rects = view.page_rects()
    start = point_to_viewport(view, GUIDE_PAGE, QPointF(60, 800))
    end = point_to_viewport(view, GUIDE_PAGE + 1, QPointF(300, 60))
    assert 0 <= start.y() < end.y() <= view.view.viewport().height(), rects
    drag(view.view.viewport(), start, end)
    assert [p for p, _s in view.selector.parts][-1] == GUIDE_PAGE + 1
    assert view.selector.text()
    view.close()


def test_link_click_still_follows_link_with_selection(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    view = demo_view(qapp)
    view.go_to(1)
    wait_for(qapp, lambda: False, 0.2)
    view.selector.select_all()
    QTest.mouseClick(view.view.viewport(), Qt.MouseButton.LeftButton,
                     pos=point_to_viewport(view, 1, QPointF(200, 163)))
    assert wait_for(qapp, lambda: view.current_page() == 3)
    view.close()


def test_preview_in_main_window_can_select_text(qapp):
    from gui.pdf_viewer import HAS_QTPDF, PdfPreview

    if not HAS_QTPDF:
        pytest.skip("QtPdf fehlt")
    preview = PdfPreview()
    preview.resize(800, 600)
    preview.show()
    preview.show_pdf((ROOT / "examples" / "demo.pdf").read_bytes())
    preview.selector.select_all()
    assert "Zweites Kapitel" in preview.selector.text()
    preview.show_pdf((ROOT / "examples" / "demo.pdf").read_bytes())  # Neu laden hebt sie auf
    assert preview.selector.text() == ""
    preview.close()


def test_copied_text_joins_hyphenation_and_emoji_runs():
    from core.pdf_select import tidy_text

    raw = "die der Kon\n\u00ad\nverter beherrschen muss — wie \n🚨, \n🏆 und \n💎\n.\nNeue Zeile"
    assert tidy_text(raw) == "die der Konverter beherrschen muss — wie 🚨, 🏆 und 💎.\nNeue Zeile"
    assert tidy_text("Zeile eins\nZeile zwei\n\nAbsatz") == "Zeile eins\nZeile zwei\n\nAbsatz"
