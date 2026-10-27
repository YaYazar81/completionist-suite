"""PDF-Viewer fuer fertige PDF-Dateien (Viewer-Modus).

Anders als ``PdfPreview`` zeigt dieses Widget eine Datei von der Platte:
mit Seitennavigation, Suche, Inhaltsverzeichnis (PDF-Lesezeichen),
klickbaren Links und automatischem Neuladen, sobald sich die Datei aendert.
Braucht weder Typst noch die Einstellungen.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument, QPdfLink, QPdfLinkModel, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QSpinBox,
    QSplitter,
    QToolButton,
    QToolTip,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core import design, pdf_select
from core.watcher import DebouncedWatcher

PDF_SUFFIXES = (".pdf",)
SEARCH_PATIENCE_MS = 1500  # so lange heisst es "sucht …" statt "keine Treffer"
# Externe Links oeffnet der Viewer nur mit diesen Schemata (kein file:, kein javascript:)
LINK_SCHEMES = ("http", "https", "mailto")
CLICK_SLOP = 4  # Pixel: mehr Bewegung zwischen Druecken und Loslassen ist kein Klick


class PdfFileView(QWidget):
    """Zeigt eine PDF-Datei an und laedt sie bei Aenderungen neu."""

    ZOOM_STEP = 1.25

    changed = Signal()  # Seite, Zoom oder Datei gewechselt -> Statuszeile
    load_failed = Signal(str)  # Fehlermeldung fuer den Nutzer

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path: Path | None = None
        self._buffer: QBuffer | None = None
        self._password = ""

        self.doc = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setPageSpacing(12)
        self.search = QPdfSearchModel(self)
        self.search.setDocument(self.doc)
        self.view.setSearchModel(self.search)

        # Links: QPdfView zeichnet sie, reagiert aber nicht auf Klicks
        self._links: dict[int, QPdfLinkModel] = {}
        self._press_pos: QPoint | None = None
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().installEventFilter(self)
        # Text markieren und kopieren; den Mauszeiger (Hand ueber Links) setzt die Auswahl
        self.selector = pdf_select.PdfTextSelector(self.view, lambda: self.doc, self.link_at)

        # Inhaltsverzeichnis aus den Lesezeichen des PDFs
        self.bookmarks = QPdfBookmarkModel(self)
        self.bookmarks.setDocument(self.doc)
        self.toc = QTreeView()
        self.toc.setModel(self.bookmarks)
        self.toc.setHeaderHidden(True)
        self.toc.setUniformRowHeights(True)
        self.toc.setExpandsOnDoubleClick(False)
        self.toc.clicked.connect(self._on_toc_clicked)
        self.toc.activated.connect(self._on_toc_clicked)  # Enter auf einem Eintrag
        self._sidebar_wanted = True  # Wunsch des Nutzers; sichtbar nur mit Lesezeichen

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self._btn_toc = self._tool(bar, "Inhalt", "Inhaltsverzeichnis ein-/ausblenden", self.toggle_sidebar, "F4",
                                   "list-tree", show_text=True)
        self._btn_toc.setCheckable(True)
        bar.addSpacing(12)
        self._tool(bar, "−", "Verkleinern", self.zoom_out, "Ctrl+-", "zoom-out")
        self._tool(bar, "+", "Vergrößern", self.zoom_in, "Ctrl++", "zoom-in")
        self._btn_width = self._tool(bar, "Breite", "An Fensterbreite anpassen", self.fit_width, "Ctrl+0",
                                     "move-horizontal")
        self._btn_page = self._tool(bar, "Ganze Seite", "Ganze Seite anzeigen", self.fit_page, "Ctrl+9",
                                    "maximize")
        for b in (self._btn_width, self._btn_page):
            b.setCheckable(True)
        self._btn_page.setChecked(True)
        self.zoom_label = QLabel()
        self.zoom_label.setMinimumWidth(48)
        bar.addWidget(self.zoom_label)
        bar.addSpacing(12)

        self._tool(bar, "◀", "Vorige Seite", self.prev_page, "PgUp", "chevron-left")
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setToolTip("Seite eingeben")
        self.page_spin.valueChanged.connect(lambda v: self.go_to(v - 1))
        bar.addWidget(self.page_spin)
        self.page_total = QLabel()
        bar.addWidget(self.page_total)
        self._tool(bar, "▶", "Nächste Seite", self.next_page, "PgDown", "chevron-right")
        bar.addSpacing(12)

        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Im PDF suchen …  (Strg+F)")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setMaximumWidth(260)
        self.find_edit.returnPressed.connect(self.find_next)
        self.find_edit.textChanged.connect(lambda _t: self._find_timer.start())
        bar.addWidget(self.find_edit)
        self._tool(bar, "▲", "Vorheriger Treffer", self.find_prev, "Shift+F3", "chevron-up")
        self._tool(bar, "▼", "Nächster Treffer", self.find_next, "F3", "chevron-down")
        self.find_label = QLabel()
        bar.addWidget(self.find_label)
        bar.addStretch(1)

        find_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        find_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_sc.activated.connect(lambda: (self.find_edit.setFocus(), self.find_edit.selectAll()))

        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(250)
        self._find_timer.timeout.connect(self._run_search)
        self._jump_pending = False
        self._search_started = 0.0
        self.search.rowsInserted.connect(lambda *_: self._on_results())
        self.search.modelReset.connect(self._on_results)

        nav = self.view.pageNavigator()
        nav.currentPageChanged.connect(self._on_page)
        self.view.zoomFactorChanged.connect(lambda *_: self._update_zoom_label())
        self.view.zoomModeChanged.connect(lambda *_: self._update_zoom_label())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.toc)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([260, 1000])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Navigationsleiste als eigene Flaeche (Hintergrund und Trennlinie aus theme.qss)
        bar_widget = QWidget(self)
        bar_widget.setObjectName("viewerBar")
        bar_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar_widget.setLayout(bar)
        layout.addWidget(bar_widget)
        layout.addWidget(self.splitter, 1)

        # Neu laden, sobald ein anderes Programm (z. B. der Export) die Datei schreibt
        self.watcher = DebouncedWatcher(350, self)
        self.watcher.changed.connect(self.reload)

        self._update_pages()
        self._update_sidebar()

    def _tool(self, bar: QHBoxLayout, text: str, tip: str, slot, shortcut: str,
              icon: str | None = None, show_text: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        if icon:
            btn.setIcon(design.icon(icon))
            btn.setIconSize(design.ICON_SIZE)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if show_text
                                   else Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setToolTip(f"{tip}  ({shortcut})")
        btn.setAutoRaise(True)
        btn.clicked.connect(slot)
        sc = QShortcut(QKeySequence(shortcut), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(slot)
        bar.addWidget(btn)
        return btn

    # ------------------------------------------------------------------ #
    # Laden
    # ------------------------------------------------------------------ #

    def open(self, path: str | Path) -> bool:
        """Oeffnet ``path``. Gibt ``False`` zurueck (und meldet ``load_failed``),
        wenn die Datei nicht lesbar ist."""
        path = Path(path)
        self._password = ""
        if not self._load(path, ask_password=True):
            return False
        self.path = path
        self.watcher.set_paths([str(path)])
        self.go_to(0)
        if self.find_edit.text().strip():
            self._run_search()
        self.changed.emit()
        return True

    def reload(self) -> None:
        """Laedt die aktuelle Datei neu und bleibt auf derselben Seite."""
        if self.path is None or not self.path.is_file():
            return
        page = self.current_page()
        # Schlaegt das Laden fehl (Datei wird gerade noch geschrieben), bleibt
        # das bisherige Dokument stehen; der naechste Watcher-Lauf versucht es erneut.
        if not self._load(self.path, ask_password=False, quiet=True):
            return
        self.go_to(min(page, self.doc.pageCount() - 1))
        if self.find_edit.text().strip():
            self._run_search()
        self.changed.emit()

    def _load(self, path: Path, *, ask_password: bool, quiet: bool = False) -> bool:
        try:
            # Aus dem Speicher laden: eine geoeffnete Datei waere unter Windows
            # gesperrt, und der Export koennte sie nicht ueberschreiben.
            raw = path.read_bytes()
        except OSError as exc:
            if not quiet:
                self.load_failed.emit(f"„{path.name}“ konnte nicht gelesen werden:\n{exc.strerror or exc}")
            return False

        doc = QPdfDocument(self)
        buf = QBuffer(self)
        buf.setData(QByteArray(raw))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        doc.setPassword(self._password)
        doc.load(buf)
        while doc.error() == QPdfDocument.Error.IncorrectPassword and ask_password:
            prompt = "Kennwort für dieses PDF:" if not self._password else "Falsches Kennwort. Bitte erneut eingeben:"
            pw, ok = QInputDialog.getText(self, path.name, prompt, QLineEdit.EchoMode.Password)
            if not ok:
                break
            self._password = pw
            doc.close()
            buf.seek(0)
            doc.setPassword(pw)
            doc.load(buf)

        if doc.error() != QPdfDocument.Error.None_:
            if not quiet:
                self.load_failed.emit(f"„{path.name}“ ist kein lesbares PDF ({_error_text(doc.error())}).")
            doc.deleteLater()
            buf.deleteLater()
            return False

        self.selector.reset()
        old_doc, old_buf = self.doc, self._buffer
        self.doc, self._buffer = doc, buf
        self.view.setDocument(doc)
        self.search.setDocument(doc)
        self.bookmarks.setDocument(doc)
        for model in self._links.values():
            model.deleteLater()
        self._links.clear()
        if old_doc is not None:
            old_doc.close()
            old_doc.deleteLater()
        if old_buf is not None:
            old_buf.close()
            old_buf.deleteLater()
        self._update_pages()
        self._update_sidebar()
        return True

    def close_document(self) -> None:
        self.selector.reset()
        self.path = None
        self.watcher.set_paths([])
        self.doc.close()
        self._links.clear()
        self._update_pages()
        self._update_sidebar()
        self.changed.emit()

    # ------------------------------------------------------------------ #
    # Seiten
    # ------------------------------------------------------------------ #

    def page_count(self) -> int:
        return self.doc.pageCount()

    def current_page(self) -> int:
        return self.view.pageNavigator().currentPage()

    def go_to(self, page: int, location: QPointF | None = None) -> None:
        """Springt zu ``page``; mit ``location`` (PDF-Punkte, oben links) an
        genau diese Stelle der Seite statt an ihren Anfang."""
        if not 0 <= page < self.doc.pageCount():
            return
        nav = self.view.pageNavigator()
        nav.jump(page, location or QPointF(), nav.currentZoom())
        if location is not None and location.y() > 0:
            # QPdfView scrollt beim Sprung nur an den Seitenanfang
            rects = self.page_rects(scrolled=False)
            pt_h = self.doc.pagePointSize(page).height()
            if page < len(rects) and pt_h > 0:
                scale = rects[page].height() / pt_h
                y = rects[page].top() + round(location.y() * scale) - self.view.pageSpacing()
                self.view.verticalScrollBar().setValue(max(0, y))

    def prev_page(self) -> None:
        self.go_to(self.current_page() - 1)

    def next_page(self) -> None:
        self.go_to(self.current_page() + 1)

    def _on_page(self, page: int) -> None:
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page + 1)
        self.page_spin.blockSignals(False)
        self.changed.emit()

    def _update_pages(self) -> None:
        n = self.doc.pageCount()
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, n))
        self.page_spin.setValue(min(self.current_page() + 1, max(1, n)))
        self.page_spin.blockSignals(False)
        self.page_spin.setEnabled(n > 0)
        self.page_total.setText(f" / {n} ")
        self._update_zoom_label()

    # ------------------------------------------------------------------ #
    # Seitengeometrie
    # ------------------------------------------------------------------ #

    def page_rects(self, *, scrolled: bool = True) -> list[QRect]:
        """Lage jeder Seite in Pixeln -- im Viewport (``scrolled``) oder im
        ganzen Dokument (siehe core/pdf_select.py)."""
        return pdf_select.page_rects(self.view, self.doc, scrolled=scrolled)

    def page_at(self, pos: QPoint) -> tuple[int, QPointF] | None:
        """Seite und Stelle in PDF-Punkten unter ``pos`` (Viewport-Pixel)."""
        return pdf_select.page_at(self.view, self.doc, pos)

    # ------------------------------------------------------------------ #
    # Links
    # ------------------------------------------------------------------ #

    def link_at(self, pos: QPoint) -> QPdfLink | None:
        """Link unter ``pos`` (Viewport-Pixel) oder ``None``."""
        hit = self.page_at(pos)
        if hit is None:
            return None
        page, point = hit
        model = self._links.get(page)
        if model is None:
            model = QPdfLinkModel(self)
            model.setDocument(self.doc)
            model.setPage(page)
            self._links[page] = model
        # linkAt prueft nur Links mit Seitenziel; externe (Seite -1) per Hand
        for row in range(model.rowCount(QModelIndex())):
            idx = model.index(row, 0)
            if model.data(idx, QPdfLinkModel.Role.Rectangle.value).contains(point):
                return model.data(idx, QPdfLinkModel.Role.Link.value)
        return None

    def follow_link(self, link: QPdfLink) -> None:
        url = link.url()
        if url.isValid() and not url.isEmpty():
            if url.scheme().lower() in LINK_SCHEMES:
                QDesktopServices.openUrl(url)
            return
        if link.page() >= 0:
            self.go_to(link.page(), link.location())

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt-API)
        if obj is self.view.viewport():
            et = event.type()
            if et == QEvent.Type.MouseMove:
                link = self.link_at(event.position().toPoint())
                url = link.url() if link is not None else None
                if url is not None and not url.isEmpty():
                    QToolTip.showText(event.globalPosition().toPoint(), url.toString(), self.view.viewport())
                else:
                    QToolTip.hideText()
            elif et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._press_pos = event.position().toPoint()
            elif et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                press, self._press_pos = self._press_pos, None
                pos = event.position().toPoint()
                if press is not None and (pos - press).manhattanLength() <= CLICK_SLOP:
                    link = self.link_at(pos)
                    if link is not None:
                        self.follow_link(link)
                        return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    # Inhaltsverzeichnis
    # ------------------------------------------------------------------ #

    def has_bookmarks(self) -> bool:
        return self.bookmarks.rowCount(QModelIndex()) > 0

    def toggle_sidebar(self, *_args) -> None:
        if not self.has_bookmarks():
            self._btn_toc.setChecked(False)
            return
        self._sidebar_wanted = not self.toc.isVisible()
        self._update_sidebar()

    def _update_sidebar(self) -> None:
        has = self.has_bookmarks()
        self._btn_toc.setEnabled(has)
        self._btn_toc.setToolTip(
            "Inhaltsverzeichnis ein-/ausblenden  (F4)" if has
            else "Dieses PDF hat kein Inhaltsverzeichnis (keine Lesezeichen)")
        show = has and self._sidebar_wanted
        self.toc.setVisible(show)
        self._btn_toc.setChecked(show)
        if has:
            self.toc.expandToDepth(0)

    def _on_toc_clicked(self, index: QModelIndex) -> None:
        page = self.bookmarks.data(index, QPdfBookmarkModel.Role.Page.value)
        location = self.bookmarks.data(index, QPdfBookmarkModel.Role.Location.value)
        if isinstance(page, int) and page >= 0:
            self.go_to(page, location if isinstance(location, QPointF) else None)

    # ------------------------------------------------------------------ #
    # Zoom
    # ------------------------------------------------------------------ #

    def effective_zoom(self) -> float:
        """Tatsaechlicher Zoom, auch in den Einpass-Modi."""
        mode = self.view.zoomMode()
        if mode == QPdfView.ZoomMode.Custom or self.doc.pageCount() == 0:
            return self.view.zoomFactor()
        page_pt = self.doc.pagePointSize(max(0, self.current_page()))
        if page_pt.width() <= 0 or page_pt.height() <= 0:
            return self.view.zoomFactor()
        margins = self.view.documentMargins()
        px_per_pt = self.logicalDpiX() / 72.0
        avail_w = self.view.viewport().width() - margins.left() - margins.right()
        zoom = avail_w / (page_pt.width() * px_per_pt)
        if mode == QPdfView.ZoomMode.FitInView:
            avail_h = self.view.viewport().height() - margins.top() - margins.bottom()
            zoom = min(zoom, avail_h / (page_pt.height() * px_per_pt))
        return max(0.05, zoom)

    def _set_zoom(self, factor: float) -> None:
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(max(0.1, min(8.0, factor)))
        self._sync_fit_buttons()

    def zoom_in(self) -> None:
        self._set_zoom(self.effective_zoom() * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self.effective_zoom() / self.ZOOM_STEP)

    def fit_width(self) -> None:
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._sync_fit_buttons()

    def fit_page(self) -> None:
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._sync_fit_buttons()

    def _sync_fit_buttons(self) -> None:
        mode = self.view.zoomMode()
        self._btn_width.setChecked(mode == QPdfView.ZoomMode.FitToWidth)
        self._btn_page.setChecked(mode == QPdfView.ZoomMode.FitInView)
        QTimer.singleShot(0, self._update_zoom_label)

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f" {round(self.effective_zoom() * 100)} %" if self.doc.pageCount() else "")
        self.changed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        super().resizeEvent(event)
        self._update_zoom_label()

    # ------------------------------------------------------------------ #
    # Suche
    # ------------------------------------------------------------------ #

    def _run_search(self) -> None:
        self._jump_pending = False
        self._search_started = time.monotonic()
        self.search.setSearchString(self.find_edit.text().strip())
        self.view.setCurrentSearchResultIndex(-1)
        QTimer.singleShot(0, self._update_find_label)

    def _on_results(self) -> None:
        # QPdfSearchModel sucht seitenweise im Hintergrund: ein Sprung, der vor
        # dem ersten Treffer angefordert wurde, wird hier nachgeholt.
        if self._jump_pending and self.search.count():
            self._jump_pending = False
            self._jump_to_result(0)
        else:
            self._update_find_label()

    def _jump_to_result(self, index: int) -> None:
        n = self.search.count()
        if not n:
            self._update_find_label()
            return
        index %= n
        self.view.setCurrentSearchResultIndex(index)
        link = self.search.resultAtIndex(index)
        nav = self.view.pageNavigator()
        nav.jump(link.page(), link.location(), nav.currentZoom())
        self._update_find_label()

    def _start_search_if_changed(self) -> bool:
        """Startet die Suche neu, falls sich der Suchtext geaendert hat.
        Gibt ``True`` zurueck, wenn noch keine Treffer da sind."""
        if self.search.searchString() != self.find_edit.text().strip():
            self._find_timer.stop()
            self._run_search()
        if not self.search.count() and self.find_edit.text().strip():
            self._jump_pending = True
            self._update_find_label()
            # Das Modell meldet kein "fertig" -- nach einer Weile ohne Treffer
            # zeigt das Label "keine Treffer"; ein spaeter Treffer springt trotzdem.
            QTimer.singleShot(SEARCH_PATIENCE_MS, self._update_find_label)
            return True
        return False

    def find_next(self) -> None:
        if self._start_search_if_changed():
            return
        self._jump_to_result(self.view.currentSearchResultIndex() + 1)

    def find_prev(self) -> None:
        if self._start_search_if_changed():
            return
        cur = self.view.currentSearchResultIndex()
        self._jump_to_result((cur if cur >= 0 else 0) - 1)

    def _update_find_label(self) -> None:
        if not self.find_edit.text().strip():
            self.find_label.setText("")
            return
        n = self.search.count()
        cur = self.view.currentSearchResultIndex()
        if n == 0:
            left_ms = SEARCH_PATIENCE_MS - (time.monotonic() - self._search_started) * 1000
            searching = self._jump_pending and left_ms > 0
            self.find_label.setText(" sucht …" if searching else " keine Treffer")
            if searching:
                # Qt-Timer duerfen bis zu 5 % zu frueh feuern -- sonst bliebe
                # "sucht …" stehen, weil keine weitere Aktualisierung kommt
                QTimer.singleShot(int(left_ms) + 1, self._update_find_label)
        else:
            self.find_label.setText(f" {cur + 1 if cur >= 0 else '–'} / {n}")

    def status_text(self) -> str:
        n = self.doc.pageCount()
        return f"Seite {self.current_page() + 1} von {n}" if n else ""


def _error_text(error: QPdfDocument.Error) -> str:
    return {
        QPdfDocument.Error.FileNotFound: "Datei nicht gefunden",
        QPdfDocument.Error.InvalidFileFormat: "ungültiges Dateiformat",
        QPdfDocument.Error.IncorrectPassword: "Kennwort fehlt oder ist falsch",
        QPdfDocument.Error.UnsupportedSecurityScheme: "Verschlüsselung wird nicht unterstützt",
        QPdfDocument.Error.DataNotYetAvailable: "Daten unvollständig",
    }.get(error, "unbekannter Fehler")
