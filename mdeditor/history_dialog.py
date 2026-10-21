"""Aeltere Fassungen einer Datei ansehen und wiederherstellen.

Die Fassungen legt ``markdown_io.snapshot`` beim Speichern an
(``.completionistmd/verlauf/<Datei>/`` neben der Datei).
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
)

from .markdown_io import snapshots


class HistoryDialog(QDialog):
    """Liste links, Inhalt rechts. ``chosen()`` liefert die gewaehlte Fassung."""

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Ältere Fassungen – {Path(path).name}")
        self.resize(900, 600)
        self._files = snapshots(path)

        self.list = QListWidget(self)
        for f in self._files:
            st = f.stat()
            stamp = time.strftime("%d.%m.%Y  %H:%M:%S", time.localtime(st.st_mtime))
            item = QListWidgetItem(f"{stamp}   ({st.st_size / 1024:.1f} KB)")
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self._show)

        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        split = QSplitter(self)
        split.addWidget(self.list)
        split.addWidget(self.preview)
        split.setSizes([260, 640])

        hint = QLabel("Gesichert wird beim Speichern höchstens alle 10 Minuten; die letzten 30 "
                      "Fassungen bleiben. Wiederherstellen sichert vorher den jetzigen Stand.", self)
        hint.setWordWrap(True)
        if not self._files:
            hint.setText("Für diese Datei gibt es noch keine älteren Fassungen.")

        buttons = QDialogButtonBox(self)
        self.restore = buttons.addButton("Diese Fassung wiederherstellen",
                                         QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.restore.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        row.addWidget(hint, 1)
        row.addWidget(buttons)
        lay.addLayout(row)
        if self._files:
            self.list.setCurrentRow(0)

    def _show(self, item: QListWidgetItem | None) -> None:
        self.restore.setEnabled(item is not None)
        if item is None:
            self.preview.clear()
            return
        try:
            text = Path(item.data(Qt.ItemDataRole.UserRole)).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = f"(nicht lesbar: {exc})"
        self.preview.setPlainText(text)

    def chosen(self) -> Path | None:
        item = self.list.currentItem()
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item else None
