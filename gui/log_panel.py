"""Protokoll der Typst-Meldungen."""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.typst_engine import Diagnostic

_COLORS = {
    "error": QColor("#e5534b"),
    "warning": QColor("#d4a72c"),
    "info": QColor("#8b949e"),
}
_LABELS = {"error": "Fehler", "warning": "Warnung", "info": "Info"}


class LogPanel(QWidget):
    """Liste der Meldungen; Doppelklick oeffnet die Markdown-Datei an der Zeile."""

    counts_changed = pyqtSignal(int, int)  # Fehler, Warnungen

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.markdown_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Zeit", "Art", "Zeile", "Meldung"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 70)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 55)
        self.tree.setWordWrap(True)
        self.tree.itemDoubleClicked.connect(self._open_location)
        layout.addWidget(self.tree, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 2, 6, 4)
        hint = QLabel("Doppelklick auf eine Meldung öffnet die Markdown-Datei an der Zeile.")
        hint.setStyleSheet("color: palette(placeholder-text);")
        bar.addWidget(hint, 1)
        clear = QPushButton("Alles löschen")
        clear.clicked.connect(self.clear)
        bar.addWidget(clear)
        layout.addLayout(bar)

    def clear(self) -> None:
        self.tree.clear()
        self.counts_changed.emit(0, 0)

    def set_diagnostics(self, diags: list[Diagnostic], summary: str = "") -> None:
        """Ersetzt den Inhalt -- das Protokoll zeigt immer nur den letzten Lauf."""
        self.tree.clear()
        stamp = time.strftime("%H:%M:%S")
        if summary:
            self._add(stamp, Diagnostic("info", summary))
        for d in diags:
            self._add(stamp, d)
        errors = sum(1 for d in diags if d.severity == "error")
        warnings = sum(1 for d in diags if d.severity == "warning")
        self.counts_changed.emit(errors, warnings)

    def add_info(self, text: str) -> None:
        self._add(time.strftime("%H:%M:%S"), Diagnostic("info", text))

    def _add(self, stamp: str, d: Diagnostic) -> None:
        line = str(d.md_line) if d.md_line else ""
        item = QTreeWidgetItem([stamp, _LABELS.get(d.severity, d.severity), line, d.message])
        item.setForeground(1, QBrush(_COLORS.get(d.severity, QColor("#8b949e"))))
        item.setData(0, Qt.ItemDataRole.UserRole, d.md_line)
        item.setToolTip(3, d.message)
        self.tree.addTopLevelItem(item)

    def _open_location(self, item: QTreeWidgetItem, _col: int) -> None:
        line = item.data(0, Qt.ItemDataRole.UserRole)
        if not self.markdown_path:
            return
        open_in_editor(self.markdown_path, line)


def open_in_editor(path: str, line: int | None) -> None:
    """Oeffnet ``path`` -- in VS Code oder Notepad++ an der Zeile, sonst mit
    dem Standardprogramm."""
    code = shutil.which("code")
    if code and line:
        subprocess.Popen([code, "-g", f"{path}:{line}"], shell=False)
        return
    npp = shutil.which("notepad++") or _first_existing(
        r"C:\Program Files\Notepad++\notepad++.exe",
        r"C:\Program Files (x86)\Notepad++\notepad++.exe",
    )
    if npp and line:
        subprocess.Popen([npp, f"-n{line}", path], shell=False)
        return
    os.startfile(path)  # type: ignore[attr-defined]  # nur Windows


def _first_existing(*paths: str) -> str | None:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None
