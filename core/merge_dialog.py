"""Dialog "Dateien zusammenfuehren" fuer CompletionistMD und CompletionistPDF.

Reihenfolge per Ziehen oder mit den Pfeilen, Zieldatei waehlen, fertig. Die
eigentliche Arbeit macht ``core.md_merge``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .md_merge import SEPARATOR, default_name, merge_files

MD_FILTER = "Markdown (*.md *.markdown);;Alle Dateien (*)"


class MergeDialog(QDialog):
    """``exec()`` == Accepted -> ``target`` ist geschrieben."""

    def __init__(self, files: list[Path], start_dir: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dateien zusammenführen")
        self.resize(640, 480)
        self._start_dir = start_dir
        self.target: Path | None = None

        intro = QLabel(f"Die Dateien werden in dieser Reihenfolge zu einer neuen Datei "
                       f"zusammengefügt, getrennt durch eine harte Trennlinie ({SEPARATOR}) – "
                       "in CompletionistPDF ein Seitenumbruch. Reihenfolge per Ziehen ändern.", self)
        intro.setWordWrap(True)

        self.list = QListWidget(self)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for f in files:
            self._add(Path(f))

        side = QVBoxLayout()
        for text, slot in (("Hinzufügen …", self._browse), ("Entfernen", self._remove),
                           ("▲ Nach oben", lambda: self._move(-1)), ("▼ Nach unten", lambda: self._move(1)),
                           ("A–Z sortieren", self._sort)):
            b = QPushButton(text, self)
            b.clicked.connect(slot)
            side.addWidget(b)
        side.addStretch(1)

        mid = QHBoxLayout()
        mid.addWidget(self.list, 1)
        mid.addLayout(side)

        self.target_edit = QLineEdit(self)
        pick = QPushButton("…", self)
        pick.setFixedWidth(32)
        pick.clicked.connect(self._pick_target)
        row = QHBoxLayout()
        row.addWidget(QLabel("Neue Datei:", self))
        row.addWidget(self.target_edit, 1)
        row.addWidget(pick)

        buttons = QDialogButtonBox(self)
        self.ok = buttons.addButton("Zusammenführen", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._merge)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addLayout(mid, 1)
        lay.addLayout(row)
        lay.addWidget(buttons)
        self._suggest_target()

    # ------------------------------------------------------------------ #

    def files(self) -> list[Path]:
        return [Path(self.list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.list.count())]

    def _add(self, path: Path) -> None:
        if any(f == path for f in self.files()):
            return
        item = QListWidgetItem(path.name)
        item.setToolTip(str(path))
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        self.list.addItem(item)

    def _browse(self) -> None:
        start = str(self.files()[-1].parent) if self.files() else self._start_dir
        paths, _ = QFileDialog.getOpenFileNames(self, "Markdown-Dateien hinzufügen", start, MD_FILTER)
        for p in paths:
            self._add(Path(p))
        self._suggest_target()

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        new = row + step
        if row < 0 or not 0 <= new < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(new, item)
        self.list.setCurrentRow(new)

    def _sort(self) -> None:
        self.list.sortItems()

    def _suggest_target(self) -> None:
        files = self.files()
        if self.target_edit.text().strip() or not files:
            return
        self.target_edit.setText(str(files[0].parent / default_name(files)))

    def _pick_target(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Neue Datei", self.target_edit.text() or self._start_dir,
                                              "Markdown (*.md)")
        if path:
            self.target_edit.setText(path)

    def _merge(self) -> None:
        files = self.files()
        if len(files) < 2:
            QMessageBox.information(self, self.windowTitle(), "Bitte mindestens zwei Dateien wählen.")
            return
        text = self.target_edit.text().strip()
        if not text:
            QMessageBox.information(self, self.windowTitle(), "Bitte einen Namen für die neue Datei angeben.")
            return
        target = Path(text)
        if target.suffix.lower() not in (".md", ".markdown"):
            target = target.with_name(target.name + ".md")
        if any(target.resolve() == f.resolve() for f in files):
            QMessageBox.warning(self, self.windowTitle(),
                                "Die neue Datei darf keine der Quelldateien sein.")
            return
        if target.exists() and QMessageBox.question(
                self, self.windowTitle(), f"„{target.name}“ gibt es schon. Ersetzen?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            content = merge_files(files, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, self.windowTitle(), f"Zusammenführen fehlgeschlagen:\n{exc}")
            return
        self.target = target
        self.accept()
