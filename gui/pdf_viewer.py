"""PDF-Vorschau.

Bevorzugt ``QPdfView`` (PySide6 >= 6.4). Fehlt das QtPdf-Modul, zeigt ein
Ersatz-Widget von Typst gerenderte PNG-Seiten an -- ``needs_png`` sagt dem
Hauptfenster, welches Format es liefern muss.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import design

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    HAS_QTPDF = True
except ImportError:  # pragma: no cover - abhaengig von der Qt-Installation
    HAS_QTPDF = False


class PdfPreview(QWidget):
    """Vorschau mit Zoom-Leiste; behaelt die Scrollposition beim Neuladen."""

    page_count_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.needs_png = not HAS_QTPDF
        self._zoom = 1.0
        self._fit = "page"  # "page" | "width" | "" (eigener Zoom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self._btn_out = _tool("−", "Verkleinern", self.zoom_out, "zoom-out")
        self._btn_in = _tool("+", "Vergrößern", self.zoom_in, "zoom-in")
        self._btn_page = _tool("Ganze Seite", "Ganze Seite anzeigen", self.fit_page, "maximize")
        self._btn_fit = _tool("Breite", "An Fensterbreite anpassen", self.fit_width, "move-horizontal")
        for b in (self._btn_page, self._btn_fit):
            b.setCheckable(True)
        self._btn_page.setChecked(True)
        self._lbl_zoom = QLabel("")
        self._lbl_pages = QLabel("")
        for w in (self._btn_out, self._btn_in, self._btn_page, self._btn_fit, self._lbl_zoom):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self._lbl_pages)
        layout.addLayout(bar)

        if HAS_QTPDF:
            self._doc = QPdfDocument(self)
            self._buffer: QBuffer | None = None
            self._view = QPdfView(self)
            self._view.setDocument(self._doc)
            self._view.setPageMode(QPdfView.PageMode.MultiPage)
            self._view.setZoomMode(QPdfView.ZoomMode.FitInView)
            self._view.setPageSpacing(12)
            from core.pdf_select import PdfTextSelector

            self.selector = PdfTextSelector(self._view, lambda: self._doc)  # markieren, Strg+C
            layout.addWidget(self._view, 1)
        else:
            self._scroll = QScrollArea(self)
            self._scroll.setWidgetResizable(True)
            self._pages_host = QWidget()
            self._pages_layout = QVBoxLayout(self._pages_host)
            self._pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self._scroll.setWidget(self._pages_host)
            self._pixmaps: list[QPixmap] = []
            layout.addWidget(self._scroll, 1)

        self._update_labels(0)

    # ------------------------------------------------------------------ #

    @property
    def document(self):
        """Das angezeigte QPdfDocument (zum Drucken) oder None."""
        return self._doc if HAS_QTPDF else None

    def show_pdf(self, data: bytes) -> None:
        """Laedt ein neues PDF und stellt die alte Scrollposition wieder her."""
        if not HAS_QTPDF:
            return
        bar = self._view.verticalScrollBar()
        old_value, old_max = bar.value(), max(bar.maximum(), 1)

        self.selector.reset()
        old_buffer = self._buffer
        buffer = QBuffer(self)
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._doc.load(buffer)
        self._buffer = buffer
        if old_buffer is not None:
            old_buffer.close()
            old_buffer.deleteLater()

        # Relativ wiederherstellen, falls sich die Seitenzahl geaendert hat
        new_max = max(bar.maximum(), 1)
        bar.setValue(int(old_value * new_max / old_max) if old_max > 1 else old_value)
        self._update_labels(self._doc.pageCount())

    def show_pngs(self, pages: list[bytes]) -> None:
        if HAS_QTPDF:
            return
        bar = self._scroll.verticalScrollBar()
        old_value = bar.value()
        while self._pages_layout.count():
            item = self._pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pixmaps = []
        for raw in pages:
            pm = QPixmap()
            pm.loadFromData(raw)
            self._pixmaps.append(pm)
            lbl = QLabel()
            lbl.setStyleSheet("background: white; margin: 6px;")
            self._pages_layout.addWidget(lbl)
        self._apply_png_zoom()
        bar.setValue(old_value)
        self._update_labels(len(pages))

    def clear(self) -> None:
        if HAS_QTPDF:
            self.selector.reset()
            self._doc.close()
        else:
            self.show_pngs([])
        self._update_labels(0)

    # ------------------------------------------------------------------ #
    # Zoom
    # ------------------------------------------------------------------ #

    def zoom_in(self) -> None:
        self._set_zoom(self._current_zoom() * 1.2)

    def zoom_out(self) -> None:
        self._set_zoom(self._current_zoom() / 1.2)

    def fit_width(self) -> None:
        self._set_fit("width")

    def fit_page(self) -> None:
        self._set_fit("page")

    def _set_fit(self, mode: str) -> None:
        self._fit = mode
        self._btn_fit.setChecked(mode == "width")
        self._btn_page.setChecked(mode == "page")
        if HAS_QTPDF:
            if mode == "width":
                self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            elif mode == "page":
                self._view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self._apply_png_zoom()
        self._update_labels()

    def _current_zoom(self) -> float:
        if HAS_QTPDF:
            return self._view.zoomFactor()
        return self._zoom

    def _set_zoom(self, factor: float) -> None:
        factor = max(0.2, min(5.0, factor))
        self._zoom = factor
        self._fit = ""
        self._btn_fit.setChecked(False)
        self._btn_page.setChecked(False)
        if HAS_QTPDF:
            self._view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._view.setZoomFactor(factor)
        else:
            self._apply_png_zoom()
        self._update_labels()

    def _apply_png_zoom(self) -> None:
        width = self._scroll.viewport().width() - 24
        height = self._scroll.viewport().height() - 24
        for i, pm in enumerate(self._pixmaps):
            item = self._pages_layout.itemAt(i)
            lbl = item.widget() if item else None
            if not isinstance(lbl, QLabel) or pm.isNull():
                continue
            if self._fit == "width":
                scaled = pm.scaledToWidth(max(100, width), Qt.TransformationMode.SmoothTransformation)
            elif self._fit == "page":
                scaled = pm.scaled(max(100, width), max(100, height), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            else:
                scaled = pm.scaledToWidth(int(pm.width() * self._zoom), Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        super().resizeEvent(event)
        if not HAS_QTPDF and self._fit:
            self._apply_png_zoom()

    def _update_labels(self, pages: int | None = None) -> None:
        if pages is not None:
            self._pages = pages
            self._lbl_pages.setText(f"{pages} Seiten" if pages else "Keine Vorschau")
            self.page_count_changed.emit(pages)
        # Bei Einpassen zeigen die Knoepfe den Zustand, eine Prozentzahl waere irrefuehrend
        self._lbl_zoom.setText("" if self._fit else f"{self._current_zoom() * 100:.0f} %")


def _tool(text: str, tip: str, slot, icon: str) -> QToolButton:
    btn = QToolButton()
    btn.setText(text)
    btn.setIcon(design.icon(icon))
    btn.setIconSize(design.ICON_SIZE)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setToolTip(tip)
    btn.setAutoRaise(True)
    btn.clicked.connect(slot)
    return btn
