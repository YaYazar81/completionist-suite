"""Die Tabs von CompletionistMD.

* ``MdTab``    -- der WYSIWYG-Editor (eigene ``EditorView`` je Tab). Laden und
  Speichern steuert das Hauptfenster, der Tab haelt nur den Zustand.
* ``TextTab``  -- schlichter Texteditor fuer ``.txt`` mit Auto-Save. Bewusst
  nicht der Markdown-Editor: der wuerde ``*``, ``#`` oder ``_`` als Markdown
  deuten und die Datei beim Speichern umschreiben.
* ``PdfTab``   -- schreibgeschuetzte Vorschau (QtPdf) mit Zoom, Seiten, Suche.
* ``ImageTab`` -- schreibgeschuetzte Bildansicht mit Zoom und Uebergabe an
  CompletionistIMG; laedt neu, sobald die Datei gespeichert wird.

PDF- und Bild-Tabs beobachten ihre Datei (``FileWatch``), damit Aenderungen aus
CompletionistIMG bzw. CompletionistPDF sofort sichtbar werden.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QFileSystemWatcher,
    QIODevice,
    QObject,
    QPointF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFontDatabase, QImageReader, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .markdown_io import MarkdownFile, snapshot, write_safely

# Auf Modulebene: QtWebEngine muss importiert sein, bevor die QApplication
# entsteht (main_md.py importiert das Fenster -- und damit dies -- vorher).
from .webview import EditorView

MD_SUFFIXES = (".md", ".markdown")
TEXT_SUFFIXES = (".txt",)
PDF_SUFFIXES = (".pdf",)
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
AUTOSAVE_MS = 300


def kind_of(path: str | Path) -> str | None:
    """"md", "txt", "pdf", "img" oder None (nicht im Editor darstellbar)."""
    p = str(path).lower()
    for kind, suffixes in (("md", MD_SUFFIXES), ("txt", TEXT_SUFFIXES),
                           ("pdf", PDF_SUFFIXES), ("img", IMAGE_SUFFIXES)):
        if p.endswith(suffixes):
            return kind
    return None


def same_path(a: str | Path | None, b: str | Path | None) -> bool:
    if a is None or b is None:
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return Path(a) == Path(b)


class BaseTab(QWidget):
    """Gemeinsame Schnittstelle fuer das Hauptfenster."""

    kind = ""
    changed = Signal()  # Titel, Speicherstand oder Statuszeile neu zeichnen
    # Die Datei wurde ausserhalb geaendert (anderes Fenster, anderes Programm),
    # waehrend der Tab ungespeicherte Aenderungen hat -- das Hauptfenster fragt nach.
    conflict = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.path: Path | None = None

    def title(self) -> str:
        return self.path.name if self.path else "Ohne Titel"

    def is_dirty(self) -> bool:
        return False

    def save_state(self) -> tuple[str, str]:
        """(state, text) fuer die Speicheranzeige; state: saved/dirty/error/readonly."""
        return "readonly", "schreibgeschützt"

    def stats(self) -> str:
        return ""

    def flush(self) -> None:
        """Ausstehende Aenderungen sofort schreiben (Tab schliessen, Ende)."""

    def set_path(self, path: Path) -> None:
        """Datei wurde umbenannt/verschoben."""
        self.path = Path(path)
        self.changed.emit()


# ---------------------------------------------------------------------- #
# Markdown
# ---------------------------------------------------------------------- #


class MdTab(BaseTab):
    """Ein Editor-Tab. Die Logik (Laden/Speichern ueber JavaScript) liegt im
    Hauptfenster; hier steht nur, was je Tab gilt."""

    kind = "md"
    disk_changed_signal = Signal()  # die Datei wurde ausserhalb geaendert

    def __init__(self, editor_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.view = EditorView(editor_dir, self)
        self.file: MarkdownFile | None = None
        self.loading = False
        self.dirty = False
        self.ready = False            # Editor-Bundle geladen
        self.pending: str | None = None  # Datei, sobald der Editor bereit ist
        self.last_saved_text: str | None = None
        self.error = False
        self.words = ""
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(AUTOSAVE_MS)
        self.watch: FileWatch | None = None  # Aenderungen von aussen (zweites Fenster)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

    def watch_path(self, path: Path | None) -> None:
        """Beobachtet ``path``; ``disk_changed_signal`` meldet fremde Aenderungen."""
        if path is None:
            if self.watch is not None:
                self.watch.deleteLater()
                self.watch = None
            return
        if self.watch is None:
            self.watch = FileWatch(path, self)
            self.watch.changed.connect(self.disk_changed_signal)
        else:
            self.watch.set_path(path)

    @property
    def path(self) -> Path | None:  # type: ignore[override]
        return self.file.path if self.file else None

    @path.setter
    def path(self, value) -> None:
        pass  # wird ueber self.file gefuehrt

    def title(self) -> str:
        return self.file.path.name if self.file and self.file.path else "Willkommen"

    def is_dirty(self) -> bool:
        return self.dirty

    def save_state(self) -> tuple[str, str]:
        if self.file is None:
            return "readonly", "Vorschau"
        if self.error:
            return "error", "Fehler beim Speichern"
        return ("dirty", "ungespeichert …") if self.dirty else ("saved", "gespeichert")

    def stats(self) -> str:
        return self.words

    def set_path(self, path: Path) -> None:
        if self.file is not None:
            self.file.path = Path(path)
            self.watch_path(self.file.path)
        self.changed.emit()


# ---------------------------------------------------------------------- #
# Text
# ---------------------------------------------------------------------- #


class TextTab(BaseTab):
    """``.txt`` mit Auto-Save, Undo/Redo (Strg+Z / Strg+Y) des Editors."""

    kind = "txt"
    saved = Signal(str)  # Pfad -- fuer den Drive-Sync

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("textTab")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(max(font.pointSizeF(), 10.5))
        self.editor.setFont(font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self._encoding = "utf-8"
        self._bom = False
        self._crlf = False
        self._error = False
        self._words = ""
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(AUTOSAVE_MS)
        self.autosave.timeout.connect(self.save)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.editor)
        self.load()
        self.editor.textChanged.connect(self._on_changed)
        self.watch = FileWatch(self.path, self)
        self.watch.changed.connect(self._on_disk_changed)

    def _on_disk_changed(self) -> None:
        if not self.path.is_file():
            return
        if self.is_dirty():
            self.conflict.emit()
        else:
            self.reload()

    def reload(self) -> None:
        """Stand von der Platte uebernehmen; Cursor bleibt ungefaehr stehen."""
        pos = self.editor.textCursor().position()
        bar = self.editor.verticalScrollBar().value()
        try:
            self.load()
        except OSError:
            return
        cur = self.editor.textCursor()
        cur.setPosition(min(pos, len(self.editor.toPlainText())))
        self.editor.setTextCursor(cur)
        self.editor.verticalScrollBar().setValue(bar)
        self.changed.emit()

    def set_path(self, path: Path) -> None:
        super().set_path(path)
        self.watch.set_path(self.path)

    def load(self) -> None:
        raw = self.path.read_bytes()
        self._bom = raw.startswith(b"\xef\xbb\xbf")
        if self._bom:
            raw = raw[3:]
        try:
            text = raw.decode("utf-8")
            self._encoding = "utf-8"
        except UnicodeDecodeError:
            # aeltere Windows-Textdateien: beim Speichern dieselbe Kodierung behalten
            text = raw.decode("cp1252", errors="replace")
            self._encoding = "cp1252"
        self._crlf = "\r\n" in text
        self.editor.setPlainText(text.replace("\r\n", "\n"))
        self.editor.document().setModified(False)
        self._count()

    def _on_changed(self) -> None:
        if not self.editor.document().isModified():
            return
        self._count()
        self.changed.emit()
        self.autosave.start()

    def _count(self) -> None:
        self._words = f"{len(self.editor.toPlainText().split())} Wörter"

    def save(self) -> bool:
        self.autosave.stop()
        if not self.editor.document().isModified():
            return True
        text = self.editor.toPlainText()
        if self._crlf:
            text = text.replace("\n", "\r\n")
        try:
            data = text.encode(self._encoding, errors="replace")
            if self._bom:
                data = b"\xef\xbb\xbf" + data
            # wie bei .md: aeltere Fassung sichern, dann ausfallsicher schreiben
            snapshot(self.path)
            write_safely(self.path, data)
            self.watch.set_path(self.path)  # eigenes Speichern nicht als fremde Aenderung melden
        except OSError:
            self._error = True
            self.changed.emit()
            return False
        self._error = False
        self.editor.document().setModified(False)
        self.changed.emit()
        self.saved.emit(str(self.path))
        return True

    def flush(self) -> None:
        self.save()

    def is_dirty(self) -> bool:
        return self.editor.document().isModified()

    def save_state(self) -> tuple[str, str]:
        if self._error:
            return "error", "Fehler beim Speichern"
        return ("dirty", "ungespeichert …") if self.is_dirty() else ("saved", "gespeichert")

    def stats(self) -> str:
        return self._words


# ---------------------------------------------------------------------- #
# Datei beobachten (PDF, Bild)
# ---------------------------------------------------------------------- #


class FileWatch(QObject):
    """Meldet Aenderungen an einer Datei -- auch wenn ein Programm sie beim
    Speichern ersetzt (dann verliert QFileSystemWatcher sie aus den Augen)."""

    changed = Signal()

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self._w = QFileSystemWatcher(self)
        self._w.fileChanged.connect(self._poke)
        self._w.directoryChanged.connect(self._poke)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)  # Schreibvorgang abwarten
        self._debounce.timeout.connect(self._fire)
        self._stamp = self._signature()
        self._arm()

    def _signature(self):
        try:
            st = self.path.stat()
            return st.st_size, st.st_mtime_ns
        except OSError:
            return None

    def _arm(self) -> None:
        for old in self._w.files() + self._w.directories():
            self._w.removePath(old)
        if self.path.exists():
            self._w.addPath(str(self.path))
        if self.path.parent.is_dir():
            self._w.addPath(str(self.path.parent))

    def set_path(self, path: Path) -> None:
        self.path = Path(path)
        self._stamp = self._signature()
        self._arm()

    def _poke(self, *_args) -> None:
        self._debounce.start()

    def _fire(self) -> None:
        if str(self.path) not in self._w.files() and self.path.exists():
            self._w.addPath(str(self.path))  # nach dem Ersetzen wieder anmelden
        stamp = self._signature()
        if stamp is not None and stamp != self._stamp:
            self._stamp = stamp
            self.changed.emit()


def _tool(bar: QToolBar, text: str, tip: str, slot, shortcut: str | None = None) -> QToolButton:
    b = QToolButton(bar)
    b.setText(text)
    b.setToolTip(tip + (f"  ({shortcut})" if shortcut else ""))
    b.setAutoRaise(True)
    b.clicked.connect(slot)
    if shortcut:
        sc = QShortcut(QKeySequence(shortcut), bar.parentWidget())
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(slot)
    bar.addWidget(b)
    return b


def _spacer(bar: QToolBar) -> None:
    w = QWidget(bar)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    bar.addWidget(w)


# ---------------------------------------------------------------------- #
# PDF
# ---------------------------------------------------------------------- #


class PdfTab(BaseTab):
    kind = "pdf"
    ZOOM_STEP = 1.25
    SEARCH_PATIENCE_MS = 1500  # so lange heisst es "sucht …" statt "keine Treffer"

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
        from PySide6.QtPdfWidgets import QPdfView

        self.path = Path(path)
        self._buffer: QBuffer | None = None
        self.doc = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.search = QPdfSearchModel(self)
        self.search.setDocument(self.doc)
        self.view.setSearchModel(self.search)
        self._QPdfView = QPdfView
        from core.pdf_select import PdfTextSelector

        self.selector = PdfTextSelector(self.view, lambda: self.doc)  # markieren, Strg+C

        bar = QToolBar(self)
        bar.setObjectName("tabBar")
        self.toolbar = bar
        _tool(bar, "−", "Verkleinern", self.zoom_out, "Ctrl+-")
        _tool(bar, "+", "Vergrößern", self.zoom_in, "Ctrl++")
        _tool(bar, "↔ Breite", "An Fensterbreite anpassen", self.fit_width, "Ctrl+0")
        self.zoom_label = QLabel(bar)
        self.zoom_label.setMinimumWidth(48)
        bar.addWidget(self.zoom_label)
        bar.addSeparator()
        _tool(bar, "◀", "Vorige Seite", self.prev_page, "PgUp")
        self.page_spin = QSpinBox(bar)
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setToolTip("Seite eingeben")
        self.page_spin.valueChanged.connect(lambda v: self.go_to(v - 1))
        bar.addWidget(self.page_spin)
        self.page_total = QLabel(bar)
        bar.addWidget(self.page_total)
        _tool(bar, "▶", "Nächste Seite", self.next_page, "PgDown")
        bar.addSeparator()
        self.find_edit = QLineEdit(bar)
        self.find_edit.setPlaceholderText("Im PDF suchen …")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setMaximumWidth(240)
        self.find_edit.returnPressed.connect(self.find_next)
        self.find_edit.textChanged.connect(lambda _t: self._find_timer.start())
        bar.addWidget(self.find_edit)
        _tool(bar, "▲", "Vorheriger Treffer", self.find_prev, "Shift+F3")
        _tool(bar, "▼", "Nächster Treffer", self.find_next, "F3")
        self.find_label = QLabel(bar)
        bar.addWidget(self.find_label)
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

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.view, 1)

        self.watch = FileWatch(self.path, self)
        self.watch.changed.connect(self.reload)
        self.load()

    # --- Laden ---

    def load(self) -> None:
        # Aus dem Speicher laden: eine geoeffnete Datei waere unter Windows
        # gesperrt, und CompletionistPDF koennte sie nicht neu schreiben.
        data = QByteArray(self.path.read_bytes())
        buf = QBuffer(self)
        buf.setData(data)
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        self.selector.reset()
        self.doc.load(buf)
        if self._buffer is not None:
            self._buffer.deleteLater()
        self._buffer = buf
        n = max(1, self.doc.pageCount())
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(n)
        self.page_spin.blockSignals(False)
        self.page_total.setText(f" / {self.doc.pageCount()} ")
        self._update_zoom_label()
        self.changed.emit()

    def reload(self) -> None:
        page = self.current_page()
        try:
            self.load()
        except OSError:
            return
        self.go_to(min(page, self.doc.pageCount() - 1))
        if self.find_edit.text():
            self._run_search()

    def set_path(self, path: Path) -> None:
        super().set_path(path)
        self.watch.set_path(self.path)

    # --- Seiten ---

    def current_page(self) -> int:
        return self.view.pageNavigator().currentPage()

    def go_to(self, page: int) -> None:
        if 0 <= page < self.doc.pageCount():
            nav = self.view.pageNavigator()
            nav.jump(page, QPointF(), nav.currentZoom())

    def prev_page(self) -> None:
        self.go_to(self.current_page() - 1)

    def next_page(self) -> None:
        self.go_to(self.current_page() + 1)

    def _on_page(self, page: int) -> None:
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page + 1)
        self.page_spin.blockSignals(False)
        self.changed.emit()

    # --- Zoom ---

    def effective_zoom(self) -> float:
        """Tatsaechlicher Zoom, auch im Modus "Fensterbreite"."""
        if self.view.zoomMode() == self._QPdfView.ZoomMode.Custom or self.doc.pageCount() == 0:
            return self.view.zoomFactor()
        page_pt = self.doc.pagePointSize(max(0, self.current_page()))
        if page_pt.width() <= 0:
            return self.view.zoomFactor()
        margins = self.view.documentMargins()
        avail = self.view.viewport().width() - margins.left() - margins.right()
        px_per_pt = self.logicalDpiX() / 72.0
        return max(0.05, avail / (page_pt.width() * px_per_pt))

    def _set_zoom(self, factor: float) -> None:
        self.view.setZoomMode(self._QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(max(0.1, min(8.0, factor)))
        self._update_zoom_label()

    def zoom_in(self) -> None:
        self._set_zoom(self.effective_zoom() * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self.effective_zoom() / self.ZOOM_STEP)

    def fit_width(self) -> None:
        self.view.setZoomMode(self._QPdfView.ZoomMode.FitToWidth)
        QTimer.singleShot(0, self._update_zoom_label)

    def _update_zoom_label(self) -> None:
        fit = self.view.zoomMode() == self._QPdfView.ZoomMode.FitToWidth
        self.zoom_label.setText(f" {round(self.effective_zoom() * 100)} %" + (" ↔" if fit else ""))
        self.changed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_zoom_label()

    # --- Suche ---

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
            QTimer.singleShot(self.SEARCH_PATIENCE_MS, self._update_find_label)
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
            searching = time.monotonic() - self._search_started < self.SEARCH_PATIENCE_MS / 1000
            self.find_label.setText(" sucht …" if self._jump_pending and searching else " keine Treffer")
        else:
            self.find_label.setText(f" {cur + 1 if cur >= 0 else '–'} / {n}")

    def stats(self) -> str:
        n = self.doc.pageCount()
        return f"Seite {self.current_page() + 1} / {n}" if n else ""


# ---------------------------------------------------------------------- #
# Bild
# ---------------------------------------------------------------------- #


class ImageTab(BaseTab):
    kind = "img"
    handoffRequested = Signal(str, str)  # App, Datei
    ZOOM_STEP = 1.25

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.image_size = QSize()
        self._source: QPixmap | None = None
        self.fit = True
        self.zoom = 1.0

        bar = QToolBar(self)
        bar.setObjectName("tabBar")
        self.toolbar = bar
        _tool(bar, "−", "Verkleinern", self.zoom_out, "Ctrl+-")
        _tool(bar, "+", "Vergrößern", self.zoom_in, "Ctrl++")
        _tool(bar, "100 %", "Originalgröße", self.actual_size, "Ctrl+1")
        _tool(bar, "⤢ Einpassen", "An die Tab-Größe anpassen", self.fit_to_view, "Ctrl+0")
        self.zoom_label = QLabel(bar)
        bar.addWidget(self.zoom_label)
        _spacer(bar)
        self.img_button = _tool(
            bar, "► IMG", "In CompletionistIMG bearbeiten – die Vorschau aktualisiert sich "
            "beim Speichern von selbst",
            lambda: self.handoffRequested.emit("CompletionistIMG", str(self.path)))
        self.img_button.setObjectName("handoffButton")

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("imageScroll")
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.viewport().installEventFilter(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.scroll, 1)

        self.watch = FileWatch(self.path, self)
        self.watch.changed.connect(self.reload)
        self.load()

    # --- Laden ---

    def _read(self, scaled: QSize | None = None) -> QPixmap:
        reader = QImageReader(str(self.path))
        reader.setAutoTransform(True)  # EXIF-Drehung beachten
        if scaled is not None and scaled.isValid():
            reader.setScaledSize(scaled)  # SVG scharf in der Zielgroesse rendern
        image = reader.read()
        if image.isNull():
            raise OSError(reader.errorString())
        return QPixmap.fromImage(image)

    def load(self) -> None:
        self._source = self._read()
        self.image_size = self._source.size()
        self._render()
        self.changed.emit()

    def reload(self) -> None:
        try:
            self.load()
        except OSError:
            pass  # Datei wird evtl. gerade noch geschrieben; der naechste Hinweis kommt

    def set_path(self, path: Path) -> None:
        super().set_path(path)
        self.watch.set_path(self.path)

    # --- Zoom ---

    def effective_zoom(self) -> float:
        if not self.fit or self.image_size.isEmpty():
            return self.zoom
        vp = self.scroll.viewport().size()
        return min(1.0, vp.width() / self.image_size.width(), vp.height() / self.image_size.height())

    def _render(self) -> None:
        if self._source is None or self.image_size.isEmpty():
            return
        factor = self.effective_zoom()
        dpr = self.devicePixelRatioF()
        target = QSize(max(1, round(self.image_size.width() * factor)),
                       max(1, round(self.image_size.height() * factor)))
        device = QSize(round(target.width() * dpr), round(target.height() * dpr))
        if self.path.suffix.lower() == ".svg":
            try:
                pix = self._read(device)
            except OSError:
                pix = self._source.scaled(device, Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
        elif device == self._source.size():
            pix = QPixmap(self._source)
        else:
            pix = self._source.scaled(device, Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        self.label.setPixmap(pix)
        self.zoom_label.setText(f"  {round(factor * 100)} %" + ("  ⤢" if self.fit else ""))
        self.changed.emit()

    def _set_zoom(self, factor: float) -> None:
        self.fit = False
        self.zoom = max(0.05, min(16.0, factor))
        self._render()

    def zoom_in(self) -> None:
        self._set_zoom(self.effective_zoom() * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self.effective_zoom() / self.ZOOM_STEP)

    def actual_size(self) -> None:
        self._set_zoom(1.0)

    def fit_to_view(self) -> None:
        self.fit = True
        self._render()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.fit:
            QTimer.singleShot(0, self._render)

    def eventFilter(self, obj, event):  # noqa: N802
        # Strg + Mausrad zoomt
        if obj is self.scroll.viewport() and event.type() == event.Type.Wheel \
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            (self.zoom_in if event.angleDelta().y() > 0 else self.zoom_out)()
            return True
        return super().eventFilter(obj, event)

    def stats(self) -> str:
        if self.image_size.isEmpty():
            return ""
        return f"{self.image_size.width()} × {self.image_size.height()} px"
