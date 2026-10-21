"""Kleine wiederverwendbare Widgets und das Binding Widget <-> Konfiguration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------- #
# Eingabe-Widgets
# ---------------------------------------------------------------------- #


class PathEdit(QWidget):
    """Zeile mit Dateiauswahl-Knopf und Loeschen-Knopf."""

    changed = Signal()

    def __init__(
        self,
        caption: str,
        file_filter: str,
        *,
        save: bool = False,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caption = caption
        self._filter = file_filter
        self._save = save

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.editingFinished.connect(self.changed)
        lay.addWidget(self.edit, 1)

        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Datei auswählen")
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)

        clear = QToolButton()
        clear.setText("✕")
        clear.setToolTip("Leeren")
        clear.clicked.connect(lambda: self.set_value(""))
        clear.clicked.connect(self.changed)
        lay.addWidget(clear)

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, value: str) -> None:
        self.edit.setText(value or "")

    def _browse(self) -> None:
        start = self.value() or str(Path.home())
        if self._save:
            # Hier wird nur ein Pfad gewaehlt, noch nichts geschrieben -- die
            # Ueberschreib-Rueckfrage kommt erst beim Export.
            path, _ = QFileDialog.getSaveFileName(
                self, self._caption, start, self._filter,
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(self, self._caption, start, self._filter)
        if path:
            self.set_value(str(Path(path)))
            self.changed.emit()


class ColorEdit(QWidget):
    """Hex-Farbe mit Farbfeld; Klick oeffnet den Farbdialog."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.swatch = QToolButton()
        self.swatch.setFixedWidth(28)
        self.swatch.clicked.connect(self._pick)
        lay.addWidget(self.swatch)
        self.edit = QLineEdit()
        self.edit.setMaxLength(9)
        self.edit.setFixedWidth(90)
        self.edit.editingFinished.connect(self._on_edit)
        lay.addWidget(self.edit)
        lay.addStretch(1)

    def value(self) -> str:
        return self.edit.text().strip() or "#000000"

    def set_value(self, value: str) -> None:
        self.edit.setText(value)
        self._paint()

    def _on_edit(self) -> None:
        if QColor(self.value()).isValid():
            self._paint()
            self.changed.emit()

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self.value()), self, "Farbe wählen")
        if color.isValid():
            self.set_value(color.name())
            self.changed.emit()

    def _paint(self) -> None:
        self.swatch.setStyleSheet(
            f"QToolButton {{ background: {self.value()}; border: 1px solid #555; }}"
        )


class LabeledSlider(QWidget):
    """Schieberegler mit Wertanzeige."""

    valueChanged = Signal(int)

    def __init__(self, lo: int, hi: int, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._suffix = suffix
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.label = QLabel()
        self.label.setMinimumWidth(44)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)
        self.slider.valueChanged.connect(self._on_change)
        self._on_change(self.slider.value())

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, v: int) -> None:  # noqa: N802 (Qt-Stil)
        self.slider.setValue(int(v))
        self._on_change(self.slider.value())

    def _on_change(self, v: int) -> None:
        self.label.setText(f"{v}{self._suffix}")
        self.valueChanged.emit(v)


def spin(lo: float, hi: float, step: float = 1.0, decimals: int = 1, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def ispin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def combo(items: dict[str, str] | list[tuple[Any, str]]) -> QComboBox:
    """Combo mit (Wert, Anzeigetext)-Paaren; der Wert steht in currentData()."""
    c = QComboBox()
    pairs = items.items() if isinstance(items, dict) else items
    for value, label in pairs:
        c.addItem(label, value)
    return c


def font_combo(fonts: list[str]) -> QComboBox:
    c = QComboBox()
    c.setEditable(True)
    c.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    c.addItems(fonts)
    c.setMaxVisibleItems(20)
    c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return c


# ---------------------------------------------------------------------- #
# Aufklappbare Sektion
# ---------------------------------------------------------------------- #


class Section(QWidget):
    def __init__(self, title: str, content: QWidget, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.toggle = QToolButton()
        self.toggle.setText(title.replace("&", "&&"))  # sonst Tastenkuerzel-Markierung
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggle.setObjectName("sectionHeader")
        self.toggle.toggled.connect(self._on_toggle)
        lay.addWidget(self.toggle)

        self.body = QFrame()
        self.body.setObjectName("sectionBody")
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(10, 6, 6, 10)
        body_lay.addWidget(content)
        lay.addWidget(self.body)
        self._on_toggle(expanded)

    def _on_toggle(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.body.setVisible(on)


# ---------------------------------------------------------------------- #
# Binding
# ---------------------------------------------------------------------- #


class Binder:
    """Verknuepft Widgets mit Punkt-Pfaden in der Konfiguration.

    ``bind("cover.title", line_edit)`` sorgt dafuer, dass ``load()`` den Wert
    ins Widget schreibt, ``store()`` ihn zurueckliest und jede Aenderung
    ``on_change`` ausloest -- ausser waehrend ``load()``.
    """

    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self._items: list[tuple[str, Callable[[], Any], Callable[[Any], None]]] = []
        self._loading = False

    def bind(self, path: str, widget: QWidget, cast: Callable[[Any], Any] | None = None) -> QWidget:
        getter, setter, signal = _accessors(widget)
        if cast is not None:
            raw_get = getter
            getter = lambda: cast(raw_get())  # noqa: E731
        self._items.append((path, getter, setter))
        signal.connect(self._changed)
        return widget

    def load(self, cfg: Any) -> None:
        self._loading = True
        try:
            for path, _get, set_ in self._items:
                set_(_get_path(cfg, path))
        finally:
            self._loading = False

    def store(self, cfg: Any) -> None:
        for path, get, _set in self._items:
            _set_path(cfg, path, get())

    def _changed(self, *_args: Any) -> None:
        if not self._loading:
            self._on_change()


def _accessors(w: QWidget):
    if isinstance(w, (PathEdit, ColorEdit)):
        return w.value, w.set_value, w.changed
    if isinstance(w, QCheckBox):
        return w.isChecked, lambda v: w.setChecked(bool(v)), w.toggled
    if isinstance(w, QDoubleSpinBox):
        return w.value, lambda v: w.setValue(float(v)), w.valueChanged
    if isinstance(w, QSpinBox):
        return w.value, lambda v: w.setValue(int(v)), w.valueChanged
    if isinstance(w, LabeledSlider):
        return w.value, w.setValue, w.valueChanged
    if isinstance(w, QSlider):
        return w.value, lambda v: w.setValue(int(v)), w.valueChanged
    if isinstance(w, QComboBox):
        if w.isEditable():
            return (
                lambda: w.currentText().strip(),
                lambda v: w.setCurrentText(str(v)),
                w.currentTextChanged,
            )

        def set_data(v: Any) -> None:
            idx = w.findData(v)
            if idx >= 0:
                w.setCurrentIndex(idx)

        return w.currentData, set_data, w.currentIndexChanged
    if isinstance(w, QLineEdit):
        return w.text, lambda v: w.setText(str(v)), w.textChanged
    raise TypeError(f"Kein Binding fuer {type(w).__name__}")


def _get_path(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _set_path(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)
