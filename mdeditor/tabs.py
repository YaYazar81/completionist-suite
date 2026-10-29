"""Die Tabs von CompletionistMD.

* ``MdTab``    -- der WYSIWYG-Editor (eigene ``EditorView`` je Tab), wahlweise
  mit Quellcode-Ansicht daneben oder statt seiner (``SourceEdit``). Laden und
  Speichern steuert das Hauptfenster, der Tab haelt nur den Zustand.
* ``TextTab``  -- schlichter Texteditor fuer ``.txt`` mit Auto-Save. Bewusst
  nicht der Markdown-Editor: der wuerde ``*``, ``#`` oder ``_`` als Markdown
  deuten und die Datei beim Speichern umschreiben.
* ``PdfTab``   -- schreibgeschuetzte Vorschau (QtPdf) mit Zoom, Seiten, Suche.
* ``ImageTab`` -- schreibgeschuetzte Bildansicht mit Zoom und Uebergabe an
  CompletionistIMG; laedt neu, sobald die Datei gespeichert wird.
* ``OfficeTab`` -- schreibgeschuetzte Ansicht von Word-, Excel-, PowerPoint-,
  OpenDocument- und weiteren Office-Dateien (PDF ueber LibreOffice bzw.
  Microsoft Office, sonst Text und Tabellen); Google-Verknuepfungen als Link.

Jeder Tab liefert mit ``print_job`` seinen Druckauftrag (``core/printing.py``).

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
from PySide6.QtGui import QFontDatabase, QImageReader, QKeySequence, QPixmap, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import design, office

from .markdown_io import MarkdownFile, snapshot, write_safely

# Auf Modulebene: QtWebEngine muss importiert sein, bevor die QApplication
# entsteht (main_md.py importiert das Fenster -- und damit dies -- vorher).
from .webview import EditorView

MD_SUFFIXES = (".md", ".markdown")
TEXT_SUFFIXES = (".txt",)
PDF_SUFFIXES = (".pdf",)
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
OFFICE_SUFFIXES = office.OFFICE_SUFFIXES
AUTOSAVE_MS = 300
# Quellcode <-> WYSIWYG erst nach einer kurzen Tipp-Pause abgleichen: bei
# 300-Seiten-Guides soll nicht jeder Buchstabe das ganze Dokument umbauen.
SYNC_MS = 200
VIEW_MODES = ("wysiwyg", "source", "split")


def kind_of(path: str | Path) -> str | None:
    """"md", "txt", "pdf", "img", "office" oder None (nicht im Editor darstellbar)."""
    p = str(path).lower()
    for kind, suffixes in (("md", MD_SUFFIXES), ("txt", TEXT_SUFFIXES),
                           ("pdf", PDF_SUFFIXES), ("img", IMAGE_SUFFIXES),
                           ("office", OFFICE_SUFFIXES)):
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

    def print_job(self):
        """``core.printing.PrintJob`` fuer Drucken und Seitenansicht, None = nichts zu drucken.
        Darf blockieren (der Markdown-Tab laesst Chromium erst ein PDF setzen)."""
        return None

    def set_path(self, path: Path) -> None:
        """Datei wurde umbenannt/verschoben."""
        self.path = Path(path)
        self.changed.emit()


# ---------------------------------------------------------------------- #
# Markdown
# ---------------------------------------------------------------------- #


class SourceEdit(QPlainTextEdit):
    """Der reine Markdown-Text eines Editor-Tabs.

    Formatbefehle aus der Toolbar (Fett, Ueberschrift, Liste …) setzen hier
    die Markdown-Zeichen selbst, damit sie auch im Quellcode-Modus wirken."""

    WRAP = {"bold": "**", "italic": "*", "strikeThrough": "~~", "code": "`"}
    PREFIX = {"ul": "- ", "ol": "1. ", "task": "- [ ] ", "quote": "> "}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sourceEdit")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(max(font.pointSizeF(), 10.5))
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setPlaceholderText("Markdown-Quellcode")

    def replace_text(self, text: str) -> None:
        """Ersetzt nur den geaenderten Mittelteil -- Cursor und Scrollposition
        bleiben stehen, und ein grosses Dokument wird nicht ganz neu gesetzt.
        Der Schritt landet nicht im Undo-Verlauf des Quellcodes (er kommt aus
        dem WYSIWYG-Editor, der seinen eigenen hat)."""
        old = self.toPlainText()
        if old == text:
            return
        start = _common_prefix(old, text)
        end = _common_suffix(old, text, min(len(old), len(text)) - start)
        doc = self.document()
        bar = self.verticalScrollBar().value()
        doc.setUndoRedoEnabled(False)
        cur = self.textCursor()
        cur.setPosition(start)
        cur.setPosition(len(old) - end, cur.MoveMode.KeepAnchor)
        cur.insertText(text[start:len(text) - end])
        doc.setUndoRedoEnabled(True)
        doc.setModified(False)
        self.verticalScrollBar().setValue(bar)

    def scroll_to_heading(self, index: int, place_cursor: bool = False) -> None:
        """Die ``index``-te Ueberschrift (Zaehlung wie in der Gliederung) an
        den oberen Rand holen; Codebloecke zaehlen nicht mit."""
        block = self.document().firstBlock()
        fence = ""
        count = -1
        while block.isValid():
            line = block.text()
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                mark = stripped[:3]
                fence = "" if fence == mark else (fence or mark)
            elif not fence and _is_heading(line):
                count += 1
                if count == index:
                    break
            block = block.next()
        if not block.isValid():
            return
        if place_cursor:
            cur = self.textCursor()
            cur.setPosition(block.position())
            self.setTextCursor(cur)
        # Die Scrollleiste von QPlainTextEdit zaehlt (umbrochene) Zeilen, nicht Pixel
        bar = self.verticalScrollBar()
        bar.setValue(min(bar.maximum(), block.firstLineNumber()))

    # --- Formatbefehle ---

    def apply(self, cmd: str, arg=None) -> bool:
        """Toolbar-Befehl auf den Quelltext anwenden; False = hier nicht moeglich."""
        cur = self.textCursor()
        if cmd in self.WRAP:
            mark = self.WRAP[cmd]
            text = cur.selectedText()
            cur.insertText(f"{mark}{text}{mark}")
            if not text:
                cur.setPosition(cur.position() - len(mark))
            self.setTextCursor(cur)
        elif cmd == "p" or (len(cmd) == 2 and cmd[0] == "h" and cmd[1].isdigit()):
            level = 0 if cmd == "p" else int(cmd[1])
            self._edit_lines(lambda line: ("#" * level + " " if level else "")
                             + _strip_heading(line))
        elif cmd in self.PREFIX:
            prefix = self.PREFIX[cmd]
            self._edit_lines(lambda line: line[len(prefix):] if line.startswith(prefix)
                             else prefix + line)
        elif cmd in ("rule", "break"):
            self._insert_block("---" if cmd == "rule" else "***")
        elif cmd == "codeblock":
            text = cur.selectedText().replace("\u2029", "\n")
            self._insert_block(f"```\n{text}\n```")
        elif cmd == "text" and isinstance(arg, str):
            cur.insertText(arg)
        else:
            return False
        return True

    def _edit_lines(self, change) -> None:
        cur = self.textCursor()
        start, end = sorted((cur.anchor(), cur.position()))
        doc = self.document()
        first, last = doc.findBlock(start), doc.findBlock(end)
        cur.beginEditBlock()
        block = first
        while block.isValid():
            line = QTextCursor(block)
            line.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            line.insertText(change(block.text()))
            if block == last:
                break
            block = block.next()
        cur.endEditBlock()

    def _insert_block(self, text: str) -> None:
        cur = self.textCursor()
        before = "" if cur.atBlockStart() and not cur.hasSelection() else "\n"
        cur.insertText(f"{before}\n{text}\n\n")
        self.setTextCursor(cur)


def _common_prefix(a: str, b: str, step: int = 4096) -> int:
    """Laenge des gemeinsamen Anfangs -- erst in Bloecken verglichen (in C),
    dann zeichenweise: bei einem 300-Seiten-Guide Millisekunden statt Zehntel."""
    n = min(len(a), len(b))
    i = 0
    while i + step <= n and a[i:i + step] == b[i:i + step]:
        i += step
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _common_suffix(a: str, b: str, limit: int, step: int = 4096) -> int:
    """Laenge des gemeinsamen Endes, hoechstens ``limit``."""
    la, lb = len(a), len(b)
    i = 0
    while i + step <= limit and a[la - i - step:la - i] == b[lb - i - step:lb - i]:
        i += step
    while i < limit and a[la - 1 - i] == b[lb - 1 - i]:
        i += 1
    return i


def _is_heading(line: str) -> bool:
    hashes = len(line) - len(line.lstrip("#"))
    return 1 <= hashes <= 6 and (len(line) == hashes or line[hashes] in " \t")


def _strip_heading(line: str) -> str:
    return line.lstrip("#").lstrip(" \t") if _is_heading(line) else line


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

        # Quellcode-Ansicht: neben dem WYSIWYG-Editor oder statt seiner. Der
        # Editor bleibt die Quelle der Wahrheit -- getippter Quelltext wird
        # nach SYNC_MS uebernommen (CM.replaceMarkdown), Speichern und Undo
        # laufen dort wie beim Tippen.
        self.source = SourceEdit(self)
        self.mode = "wysiwyg"
        self.source_first = False    # True: Quellcode links, Editor rechts
        self.source_focus = False    # zuletzt im Quellcode getippt/geklickt
        self._source_stale = True    # Quelltext muss beim Einblenden geholt werden
        self._syncing = False
        self.to_source = QTimer(self)
        self.to_source.setSingleShot(True)
        self.to_source.setInterval(SYNC_MS)
        self.to_source.timeout.connect(self.pull_source)
        self.to_editor = QTimer(self)
        self.to_editor.setSingleShot(True)
        self.to_editor.setInterval(SYNC_MS)
        self.to_editor.timeout.connect(self.push_source)
        self.source.textChanged.connect(self._on_source_edited)
        self.source.installEventFilter(self)

        self.split = QSplitter(Qt.Orientation.Horizontal, self)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.view)
        self.split.addWidget(self.source)
        self.source.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.split)

    # --- Ansicht ---

    def set_view_mode(self, mode: str, source_first: bool | None = None) -> None:
        """``mode``: "wysiwyg", "source" oder "split" (beide nebeneinander)."""
        if mode not in VIEW_MODES:
            mode = "wysiwyg"
        if source_first is not None and source_first != self.source_first:
            self.source_first = source_first
            sizes = self.split.sizes()
            self.split.insertWidget(0, self.source if source_first else self.view)
            self.split.setSizes(sizes[::-1])
        if mode == self.mode:
            return
        was_source = self.source_visible()
        self.push_source_now()
        self.mode = mode
        self.view.setVisible(mode != "source")
        self.source.setVisible(mode != "wysiwyg")
        if mode == "split":
            total = max(2, sum(self.split.sizes()) or self.width())
            self.split.setSizes([total // 2, total - total // 2])
        if self.source_visible() and (not was_source or self._source_stale):
            self.pull_source()
        if mode == "source":
            self.source_focus = True
            self.source.setFocus()
        elif mode == "wysiwyg":
            self.source_focus = False
            self.view.setFocus()

    def source_visible(self) -> bool:
        return self.mode != "wysiwyg"

    def source_active(self) -> bool:
        """Wirken Befehle (Toolbar, Suche) auf den Quellcode?"""
        return self.mode == "source" or (self.mode == "split" and self.source_focus)

    # --- Abgleich ---

    def editor_changed(self) -> None:
        """Der WYSIWYG-Editor hat sich geaendert: Quelltext gedrosselt nachziehen.
        Nicht, solange im Quelltext getippt wird -- sonst sprange der Cursor."""
        self._source_stale = True
        if self.source_visible() and not self.source.hasFocus() and not self.to_editor.isActive():
            self.to_source.start()

    def reset_source(self) -> None:
        """Neues Dokument im Editor (Laden, Startseite): Quelltext neu holen,
        ausstehende Uebernahmen verwerfen, Undo des Quelltexts leeren."""
        self.to_editor.stop()
        self.to_source.stop()
        self._source_stale = True
        if self.source_visible():
            self.pull_source(fresh=True)

    def pull_source(self, fresh: bool = False) -> None:
        self.to_source.stop()
        if not self.ready:
            return
        self.view.run("CM.getMarkdown()", lambda md, f=fresh: self._set_source(md, f))

    def _set_source(self, md, fresh: bool = False) -> None:
        if not isinstance(md, str) or self.to_editor.isActive():
            return  # inzwischen im Quelltext getippt -- der gewinnt
        self._syncing = True
        try:
            if fresh:
                self.source.setPlainText(md)
            else:
                self.source.replace_text(md)
        finally:
            self._syncing = False
        self._source_stale = False

    def _on_source_edited(self) -> None:
        if self._syncing:
            return
        self.to_source.stop()
        self.to_editor.start()

    def push_source(self) -> None:
        self.to_editor.stop()
        if self.ready:
            self.view.call("replaceMarkdown", self.source.toPlainText())

    def push_source_now(self) -> None:
        """Ausstehenden Quelltext sofort an den Editor geben (vor dem Speichern;
        Skripte laufen der Reihe nach, das Speichern sieht ihn also schon)."""
        if self.to_editor.isActive():
            self.push_source()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.source:
            if event.type() == event.Type.FocusIn:
                self.source_focus = True
            elif event.type() == event.Type.FocusOut:
                # Getipptes uebernehmen; danach zeigt der Quelltext, wie der
                # Editor das Markdown schreibt (z. B. "*" statt "_").
                self.push_source_now()
                if self.source_visible():
                    self.to_source.start()
        return super().eventFilter(obj, event)

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

    def print_job(self):
        from .printing import WebPdfJob

        return WebPdfJob(self.view.page(), self.title())

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

    def print_job(self):
        from core.printing import TextDocumentJob

        return TextDocumentJob(self.editor.document(), self.path.name)

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


def _tool(bar: QToolBar, text: str, tip: str, slot, shortcut: str | None = None,
          icon: str | None = None, show_text: bool = False) -> QToolButton:
    b = QToolButton(bar)
    b.setText(text)
    if icon:
        b.setIcon(design.icon(icon))
        b.setIconSize(design.ICON_SIZE)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if show_text
                             else Qt.ToolButtonStyle.ToolButtonIconOnly)
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

    def __init__(self, path: Path, parent=None, loader=None) -> None:
        """``loader``: liefert die PDF-Bytes statt ``path`` zu lesen (Office-Ansicht);
        die Datei wird dann nicht beobachtet."""
        super().__init__(parent)
        from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
        from PySide6.QtPdfWidgets import QPdfView

        self.path = Path(path)
        self.loader = loader
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
        _tool(bar, "−", "Verkleinern", self.zoom_out, "Ctrl+-", "zoom-out")
        _tool(bar, "+", "Vergrößern", self.zoom_in, "Ctrl++", "zoom-in")
        _tool(bar, "Breite", "An Fensterbreite anpassen", self.fit_width, "Ctrl+0", "move-horizontal")
        self.zoom_label = QLabel(bar)
        self.zoom_label.setMinimumWidth(48)
        bar.addWidget(self.zoom_label)
        bar.addSeparator()
        _tool(bar, "◀", "Vorige Seite", self.prev_page, "PgUp", "chevron-left")
        self.page_spin = QSpinBox(bar)
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setToolTip("Seite eingeben")
        self.page_spin.valueChanged.connect(lambda v: self.go_to(v - 1))
        bar.addWidget(self.page_spin)
        self.page_total = QLabel(bar)
        bar.addWidget(self.page_total)
        _tool(bar, "▶", "Nächste Seite", self.next_page, "PgDown", "chevron-right")
        bar.addSeparator()
        self.find_edit = QLineEdit(bar)
        self.find_edit.setPlaceholderText("Im PDF suchen …")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setMaximumWidth(240)
        self.find_edit.returnPressed.connect(self.find_next)
        self.find_edit.textChanged.connect(lambda _t: self._find_timer.start())
        bar.addWidget(self.find_edit)
        _tool(bar, "▲", "Vorheriger Treffer", self.find_prev, "Shift+F3", "chevron-up")
        _tool(bar, "▼", "Nächster Treffer", self.find_next, "F3", "chevron-down")
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

        self.watch = FileWatch(self.path, self) if loader is None else None
        if self.watch is not None:
            self.watch.changed.connect(self.reload)
        self.load()

    # --- Laden ---

    def load(self) -> None:
        # Aus dem Speicher laden: eine geoeffnete Datei waere unter Windows
        # gesperrt, und CompletionistPDF koennte sie nicht neu schreiben.
        data = QByteArray(self.loader() if self.loader is not None else self.path.read_bytes())
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
        if self.watch is not None:
            self.watch.set_path(self.path)

    def print_job(self):
        from core.printing import PdfJob

        return PdfJob(self.doc, self.path.name) if self.doc.pageCount() else None

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
        _tool(bar, "−", "Verkleinern", self.zoom_out, "Ctrl+-", "zoom-out")
        _tool(bar, "+", "Vergrößern", self.zoom_in, "Ctrl++", "zoom-in")
        _tool(bar, "100 %", "Originalgröße", self.actual_size, "Ctrl+1")
        _tool(bar, "Einpassen", "An die Tab-Größe anpassen", self.fit_to_view, "Ctrl+0", "maximize")
        self.zoom_label = QLabel(bar)
        bar.addWidget(self.zoom_label)
        _spacer(bar)
        self.img_button = _tool(
            bar, "► IMG", "In CompletionistIMG bearbeiten – die Vorschau aktualisiert sich "
            "beim Speichern von selbst",
            lambda: self.handoffRequested.emit("CompletionistIMG", str(self.path)),
            icon="image", show_text=True)
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

    def print_job(self):
        from core.printing import ImageJob

        return ImageJob(self._source.toImage(), self.path.name) if self._source is not None else None

    def stats(self) -> str:
        if self.image_size.isEmpty():
            return ""
        return f"{self.image_size.width()} × {self.image_size.height()} px"


# ---------------------------------------------------------------------- #
# Office (schreibgeschuetzt)
# ---------------------------------------------------------------------- #


class OfficeConverter(QObject):
    """Wandelt Office-Dokumente nacheinander nach PDF (``core.office.converters``).

    Eine Umwandlung nach der anderen: LibreOffice teilt sich sein Profil
    (``lo-profile`` im Cache, nur beim ersten Mal langsam) und vertraegt keine
    zwei Laeufe darauf gleichzeitig. Ergebnis: ``callback(name, pdf_bytes)``,
    bei Misserfolg ``(None, b"")``.
    """

    TIMEOUT_MS = 120_000
    _instance: "OfficeConverter | None" = None

    @classmethod
    def instance(cls) -> "OfficeConverter":
        if cls._instance is None:
            from PySide6.QtWidgets import QApplication

            cls._instance = cls(QApplication.instance())
        return cls._instance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import QStandardPaths

        cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        self.base = Path(cache or Path.home() / ".cache") / "completionistmd-office"
        self.queue: list = []   # (Quelldatei, callback, Aufrufer)
        self.current = None
        self.process = None
        self._attempts: list = []
        self._started = 0.0
        self._target: tuple = ("", Path())
        self._poll = QTimer(self)  # fertig? alle 200 ms nachsehen
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._check)

    def submit(self, source: Path, callback, owner: QObject) -> None:
        """``callback`` wird nur gerufen, solange ``owner`` (der Tab) noch lebt."""
        # Ein neuer Auftrag desselben Tabs ersetzt seinen wartenden
        self.queue = [job for job in self.queue if job[2] is not owner]
        self.queue.append((Path(source), callback, owner))
        if self.current is None:
            self._next_job()

    @staticmethod
    def _deliver(job, name, data: bytes) -> None:
        import shiboken6

        if shiboken6.isValid(job[2]):  # Tab inzwischen geschlossen: niemand mehr da
            job[1](name, data)

    def _next_job(self) -> None:
        import shutil

        import shiboken6

        self.current = None
        while self.queue:
            job = self.queue.pop(0)
            source, _callback, owner = job
            if not shiboken6.isValid(owner):
                continue
            work = self.base / "job"
            shutil.rmtree(work, ignore_errors=True)
            try:
                work.mkdir(parents=True, exist_ok=True)
                # Mit einer Kopie arbeiten: kurze ASCII-Namen, und das Original
                # bleibt frei, auch wenn es gerade in Word offen ist.
                copy = work / ("dokument" + source.suffix.lower())
                shutil.copyfile(source, copy)
            except OSError:
                self._deliver(job, None, b"")
                continue
            self.current = job
            self._attempts = office.converters(copy, work, self.base / "lo-profile")
            self._try_next()
            return

    def _try_next(self) -> None:
        import subprocess
        import sys

        if not self._attempts:
            self._finish(None, b"")
            return
        name, cmd, target = self._attempts.pop(0)
        self._target = (name, target)
        # subprocess statt QProcess: nur so startet PowerShell (Weg ueber
        # Microsoft Office) unter Windows ohne aufblitzendes Konsolenfenster.
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        except OSError:
            self._try_next()
            return
        self._started = time.monotonic()
        self._poll.start()

    def _check(self) -> None:
        proc = self.process
        if proc is None:
            self._poll.stop()
            return
        if proc.poll() is None:
            if time.monotonic() - self._started > self.TIMEOUT_MS / 1000:
                proc.kill()  # haengt: beim naechsten Blick ist er beendet
            return
        self._poll.stop()
        self.process = None
        name, target = self._target
        try:
            data = target.read_bytes()
        except OSError:
            data = b""
        if data.startswith(b"%PDF"):
            self._finish(name, data)
        else:
            self._try_next()

    def _finish(self, name, data: bytes) -> None:
        current = self.current
        self.current = None
        if current is not None:
            self._deliver(current, name, data)
        self._next_job()


class OfficeTab(BaseTab):
    """Office-Dokument zum Lesen: als PDF ueber LibreOffice bzw. Microsoft Office,
    sonst Text und Tabellen aus der eingebauten Ansicht (``core.office``)."""

    kind = "office"

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QStackedWidget, QTextBrowser

        self.path = Path(path)
        self.pdf: PdfTab | None = None
        self._pdf_data = b""
        self.mode = ""          # "pdf", "html", "google", "error", "" = wird umgewandelt

        bar = QToolBar(self)
        bar.setObjectName("tabBar")
        self.toolbar = bar
        self.info = QLabel(bar)
        bar.addWidget(self.info)
        _spacer(bar)
        self.open_button = _tool(bar, "Im Standardprogramm öffnen",
                                 "Mit dem Programm öffnen, das Windows dafür eingetragen hat (zum Bearbeiten)",
                                 self.open_external, icon="folder-open", show_text=True)

        self.message = QLabel(self)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.message.setOpenExternalLinks(True)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        self.browser.setObjectName("officeView")
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.message)
        self.stack.addWidget(self.browser)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.stack, 1)

        self.watch = FileWatch(self.path, self)
        self.watch.changed.connect(self.load)
        self.load()

    # --- Laden ---

    def load(self) -> None:
        if office.is_google(self.path):
            self._show_google()
            return
        if not office.can_convert(self.path):
            self._show_html()
            return
        if self.mode != "pdf":
            self.mode = ""
            self.info.setText("  Wird für die Ansicht umgewandelt …")
            self.message.setText("Das Dokument wird für die Ansicht umgewandelt …")
            self.stack.setCurrentWidget(self.message)
        OfficeConverter.instance().submit(self.path, self._on_converted, self)
        self.changed.emit()

    def _on_converted(self, name, data: bytes) -> None:
        if not data:
            self._show_html(note="Die Umwandlung ist fehlgeschlagen – ")
            return
        self._pdf_data = data
        if self.pdf is None:
            self.pdf = PdfTab(self.path, self.stack, loader=lambda: self._pdf_data)
            self.pdf.changed.connect(self.changed)
            self.stack.addWidget(self.pdf)
        else:
            self.pdf.reload()
        self.mode = "pdf"
        self.info.setText(f"  Schreibgeschützte Ansicht · umgewandelt mit {name}")
        self.stack.setCurrentWidget(self.pdf)
        self.changed.emit()

    def _show_html(self, note: str = "") -> None:
        try:
            html = office.to_html(self.path)
        except (office.Unsupported, OSError) as exc:
            self.mode = "error"
            self.info.setText("  Keine Ansicht möglich")
            self.message.setText(
                f"<p>{exc}</p><p>Für eine originalgetreue Ansicht aller Office-Formate "
                "<a href='https://de.libreoffice.org/download/download/'>LibreOffice</a> "
                "installieren (kostenlos) – oder die Datei im Standardprogramm öffnen.</p>")
            self.stack.setCurrentWidget(self.message)
        else:
            self.mode = "html"
            self.info.setText(f"  {note}Textansicht ohne Layout · für die Originalansicht "
                              "LibreOffice oder Microsoft Office installieren")
            self.browser.setHtml(html)
            self.stack.setCurrentWidget(self.browser)
        self.changed.emit()

    def _show_google(self) -> None:
        url = office.google_url(self.path)
        self.mode = "google"
        self.info.setText("  Google-Dokument (Verknüpfung)")
        if url:
            self.message.setText(f"<p>Dieses Dokument liegt in Google Drive.</p>"
                                 f"<p><a href='{url}'>Im Browser öffnen</a></p>")
        else:
            self.message.setText("Die Verknüpfung enthält keine Adresse.")
        self.stack.setCurrentWidget(self.message)
        self.changed.emit()

    def open_external(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def set_path(self, path: Path) -> None:
        super().set_path(path)
        self.watch.set_path(self.path)
        if self.pdf is not None:
            self.pdf.path = self.path

    # --- Drucken, Suche ---

    def print_job(self):
        if self.mode == "pdf" and self.pdf is not None:
            return self.pdf.print_job()
        if self.mode == "html":
            from core.printing import TextDocumentJob

            return TextDocumentJob(self.browser.document(), self.path.name)
        return None

    def stats(self) -> str:
        return self.pdf.stats() if self.mode == "pdf" and self.pdf is not None else ""
