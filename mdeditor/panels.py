"""Zusatzflaechen des Hauptfensters.

* ``OutlinePanel``      -- Gliederung (Ueberschriften) als zweite Seitenleiste links
* ``FindBar``           -- Suchen und Ersetzen unter den Tabs (Strg+F / Strg+H)
* ``VaultSearchDialog`` -- Volltextsuche ueber alle Notizen im Vault (Strg+Umschalt+F)
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------- #
# Gliederung
# ---------------------------------------------------------------------- #


class OutlinePanel(QWidget):
    """Ueberschriften des aktiven Dokuments; Klick springt hin."""

    jump = Signal(int)  # Dokumentposition (ProseMirror)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("outlinePanel")
        self.setMinimumWidth(150)
        title = QLabel("Gliederung", self)
        title.setObjectName("vaultTitle")
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(lambda it, _c: self.jump.emit(int(it.data(0, Qt.ItemDataRole.UserRole))))
        self.tree.itemActivated.connect(lambda it, _c: self.jump.emit(int(it.data(0, Qt.ItemDataRole.UserRole))))
        self.empty = QLabel("Keine Überschriften", self)
        self.empty.setObjectName("vaultHint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(8, 4, 4, 2)
        head.addWidget(title, 1)
        lay.addLayout(head)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.empty, 1)
        self._sig = None
        self._current: int | None = None  # Position der Ueberschrift, in der man gerade ist
        self.set_items([])

    def set_items(self, items: list[dict]) -> None:
        """``items``: [{level, text, pos}] in Dokumentreihenfolge."""
        sig = [(i.get("level"), i.get("text"), i.get("pos")) for i in items]
        if sig == self._sig:
            return
        self._sig = sig
        self.tree.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for it in items:
            level = int(it.get("level", 1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else self.tree.invisibleRootItem()
            node = QTreeWidgetItem(parent, [str(it.get("text", ""))])
            node.setToolTip(0, str(it.get("text", "")))
            node.setData(0, Qt.ItemDataRole.UserRole, int(it.get("pos", 0)))
            stack.append((level, node))
        self.tree.expandAll()
        self.tree.setVisible(bool(items))
        self.empty.setVisible(not items)
        self.set_current(self._current)

    def set_current(self, pos: int | None) -> None:
        """Hebt die Ueberschrift an Dokumentposition ``pos`` hervor (fett,
        ausgewaehlt) und scrollt sie ins Bild; ``None`` hebt nichts hervor."""
        self._current = pos
        found = None
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            hit = pos is not None and int(item.data(0, Qt.ItemDataRole.UserRole)) == pos
            if item.font(0).bold() != hit:
                font = item.font(0)
                font.setBold(hit)
                item.setFont(0, font)
            if hit:
                found = item
            it += 1
        if found is not None:
            self.tree.setCurrentItem(found)
            self.tree.scrollToItem(found)
        else:
            self.tree.clearSelection()

    def current_text(self) -> str:
        """Titel der hervorgehobenen Ueberschrift (leer, wenn keine)."""
        item = self.tree.currentItem()
        return item.text(0) if item is not None and item.font(0).bold() else ""


# ---------------------------------------------------------------------- #
# Suchen und Ersetzen
# ---------------------------------------------------------------------- #


class FindBar(QWidget):
    """Leiste unter den Tabs. Die eigentliche Suche erledigt das Hauptfenster
    (im Markdown-Editor ueber JavaScript, im Text-Tab ueber QTextDocument)."""

    findRequested = Signal(str, bool)   # Text, Gross/klein beachten
    nextRequested = Signal(int)         # +1 / -1
    replaceRequested = Signal(str)
    replaceAllRequested = Signal(str)
    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("findBar")
        self.find_edit = QLineEdit(self)
        self.find_edit.setPlaceholderText("Suchen …")
        self.find_edit.setClearButtonEnabled(True)
        self.case = QCheckBox("Aa", self)
        self.case.setToolTip("Groß-/Kleinschreibung beachten")
        self.count = QLabel("", self)
        self.count.setMinimumWidth(70)
        prev_b = self._button("▲", "Vorheriger Treffer (Umschalt+F3)", lambda: self.nextRequested.emit(-1))
        next_b = self._button("▼", "Nächster Treffer (F3, Enter)", lambda: self.nextRequested.emit(1))
        close_b = self._button("✕", "Schließen (Esc)", self.close_bar)

        self.replace_edit = QLineEdit(self)
        self.replace_edit.setPlaceholderText("Ersetzen durch …")
        self.replace_b = QPushButton("Ersetzen", self)
        self.replace_all_b = QPushButton("Alle ersetzen", self)
        self.replace_b.clicked.connect(lambda: self.replaceRequested.emit(self.replace_edit.text()))
        self.replace_all_b.clicked.connect(lambda: self.replaceAllRequested.emit(self.replace_edit.text()))

        row1 = QHBoxLayout()
        row1.setContentsMargins(6, 4, 6, 2)
        for w in (self.find_edit, self.case, prev_b, next_b, self.count, close_b):
            row1.addWidget(w, 1 if w is self.find_edit else 0)
        row2 = QHBoxLayout()
        row2.setContentsMargins(6, 0, 6, 4)
        for w in (self.replace_edit, self.replace_b, self.replace_all_b):
            row2.addWidget(w, 1 if w is self.replace_edit else 0)
        self.replace_row = QWidget(self)
        self.replace_row.setLayout(row2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(row1)
        lay.addWidget(self.replace_row)

        # Tippen sucht nach kurzer Pause, Enter springt weiter
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._search)
        self.find_edit.textChanged.connect(lambda _t: self._debounce.start())
        self.case.toggled.connect(lambda _c: self._search())
        self.find_edit.returnPressed.connect(lambda: self.nextRequested.emit(1))
        self.replace_edit.returnPressed.connect(lambda: self.replaceRequested.emit(self.replace_edit.text()))
        for seq, slot in (("Escape", self.close_bar), ("F3", lambda: self.nextRequested.emit(1)),
                          ("Shift+F3", lambda: self.nextRequested.emit(-1))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        self.hide()

    def _button(self, text: str, tip: str, slot) -> QToolButton:
        b = QToolButton(self)
        b.setText(text)
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def open(self, replace: bool, text: str = "") -> None:
        self.replace_row.setVisible(replace)
        self.show()
        if text and "\n" not in text:
            self.find_edit.setText(text)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._search()

    def close_bar(self) -> None:
        self.hide()
        self.closed.emit()

    def _search(self) -> None:
        self.findRequested.emit(self.find_edit.text(), self.case.isChecked())

    def show_result(self, count: int, index: int) -> None:
        if not self.find_edit.text():
            self.count.setText("")
        elif count <= 0:
            self.count.setText("keine Treffer")
        else:
            self.count.setText(f"{index + 1} von {count}")


# ---------------------------------------------------------------------- #
# Volltextsuche im Vault
# ---------------------------------------------------------------------- #

SEARCH_SUFFIXES = (".md", ".markdown", ".txt")
MAX_HITS = 500


class _Signals(QObject):
    found = Signal(int, list)   # Lauf-Nr., [(Pfad, Zeile, Ausschnitt)]
    done = Signal(int, int)     # Lauf-Nr., Anzahl Dateien


class _SearchJob(QRunnable):
    def __init__(self, run: int, root: str, query: str, case: bool) -> None:
        super().__init__()
        self.run_no, self.root, self.query, self.case = run, root, query, case
        self.signals = _Signals()
        self.cancelled = False

    def run(self) -> None:
        needle = self.query if self.case else self.query.lower()
        hits, files, total = [], 0, 0
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(names):
                if self.cancelled:
                    return
                if not name.lower().endswith(SEARCH_SUFFIXES) or name.startswith("."):
                    continue
                path = os.path.join(folder, name)
                files += 1
                try:
                    with open(path, encoding="utf-8-sig", errors="replace") as fh:
                        lines = fh.read().splitlines()
                except OSError:
                    continue
                file_hits = []
                for no, line in enumerate(lines, 1):
                    hay = line if self.case else line.lower()
                    if needle in hay:
                        file_hits.append((path, no, line.strip()[:200]))
                if file_hits:
                    total += len(file_hits)
                    hits.extend(file_hits)
                    if len(hits) >= 40:
                        self.signals.found.emit(self.run_no, hits)
                        hits = []
                if total >= MAX_HITS:
                    break
            if total >= MAX_HITS:
                break
        if hits:
            self.signals.found.emit(self.run_no, hits)
        self.signals.done.emit(self.run_no, files)


class VaultSearchDialog(QDialog):
    """Suche ueber alle Notizen. Doppelklick/Enter oeffnet die Datei an der Stelle."""

    openHit = Signal(str, str)  # Pfad, Suchbegriff

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Im Vault suchen")
        self.resize(760, 520)
        self.root = ""
        self._run = 0
        self._job: _SearchJob | None = None
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Suchbegriff …")
        self.edit.setClearButtonEnabled(True)
        self.case = QCheckBox("Aa", self)
        self.case.setToolTip("Groß-/Kleinschreibung beachten")
        self.status = QLabel("", self)
        self.results = QTreeWidget(self)
        self.results.setHeaderLabels(["Fundstelle", "Zeile"])
        self.results.setColumnWidth(0, 600)
        self.results.itemActivated.connect(self._activate)
        self.results.itemDoubleClicked.connect(self._activate)
        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(self.case)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.results, 1)
        lay.addWidget(self.status)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.search)
        self.edit.textChanged.connect(lambda _t: self._debounce.start())
        self.case.toggled.connect(lambda _c: self.search())
        self._files: dict[str, QTreeWidgetItem] = {}

    def start(self, root: str, text: str = "") -> None:
        self.root = root
        self.setWindowTitle(f"Im Vault suchen – {Path(root).name}" if root else "Im Vault suchen")
        if text:
            self.edit.setText(text)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()

    def search(self) -> None:
        if self._job is not None:
            self._job.cancelled = True
        self._run += 1
        self.results.clear()
        self._files = {}
        query = self.edit.text()
        if not self.root or not Path(self.root).is_dir():
            self.status.setText("Kein Vault gewählt (⚙ Einstellungen → Vault-Verzeichnis).")
            return
        if len(query) < 2:
            self.status.setText("Mindestens zwei Zeichen eingeben.")
            return
        self.status.setText("Suche …")
        job = _SearchJob(self._run, self.root, query, self.case.isChecked())
        job.signals.found.connect(self._found)
        job.signals.done.connect(self._done)
        self._job = job
        QThreadPool.globalInstance().start(job)

    def _found(self, run: int, hits: list) -> None:
        if run != self._run:
            return
        for path, line, snippet in hits:
            parent = self._files.get(path)
            if parent is None:
                try:
                    rel = str(Path(path).relative_to(self.root))
                except ValueError:
                    rel = path
                parent = QTreeWidgetItem(self.results, [rel, ""])
                parent.setData(0, Qt.ItemDataRole.UserRole, path)
                parent.setExpanded(True)
                self._files[path] = parent
            child = QTreeWidgetItem(parent, [snippet, str(line)])
            child.setData(0, Qt.ItemDataRole.UserRole, path)

    def _done(self, run: int, files: int) -> None:
        if run != self._run:
            return
        hits = sum(self._files[p].childCount() for p in self._files)
        more = f" (nach {MAX_HITS} Treffern abgebrochen)" if hits >= MAX_HITS else ""
        self.status.setText(f"{hits} Treffer in {len(self._files)} von {files} Dateien{more}")

    def _activate(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.openHit.emit(path, self.edit.text())
