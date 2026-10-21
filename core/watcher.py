"""Datei-Ueberwachung mit Entprellung."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal


class DebouncedWatcher(QObject):
    """Meldet Aenderungen an Dateien gebuendelt nach ``delay_ms``.

    Viele Editoren speichern per "in temporaere Datei schreiben, dann
    umbenennen". Danach ist die alte Datei aus Sicht des Watchers geloescht --
    deshalb wird jeder Pfad nach einem Ereignis neu registriert.
    """

    changed = pyqtSignal()

    def __init__(self, delay_ms: int = 400, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_event)
        self._paths: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._fire)

    def set_paths(self, paths: list[str]) -> None:
        wanted = {str(Path(p)) for p in paths if p}
        current = set(self._watcher.files())
        if current:
            self._watcher.removePaths(list(current))
        self._paths = wanted
        self._rearm()

    def _on_event(self, _path: str) -> None:
        self._timer.start()

    def _fire(self) -> None:
        self._rearm()
        self.changed.emit()

    def _rearm(self) -> None:
        current = set(self._watcher.files())
        missing = [p for p in self._paths if p not in current and Path(p).exists()]
        if missing:
            self._watcher.addPaths(missing)
