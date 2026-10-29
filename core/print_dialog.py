"""Druckdialog mit Seitenansicht -- fuer CompletionistPDF und CompletionistMD.

Warum ein eigener Dialog: Der Druckdialog von Windows 11 zeigt eine Vorschau nur
fuer Apps, die ueber die Druckschnittstelle der Store-Apps drucken. Qt druckt
ueber den klassischen Weg, dort steht immer "Diese App unterstuetzt keine
Seitenansicht". Hier sitzt die Vorschau (``QPrintPreviewWidget``) deshalb direkt
neben den Einstellungen und folgt jeder Aenderung.

Links: Drucker (oder "Als PDF speichern"), Ausrichtung, Papier, Raender, Kopien,
Farbe, beidseitig, Seiten ("1-3, 5"). Druckerspezifisches (Papierart, Qualitaet)
bleibt dem Windows-Dialog: "Windows-Druckdialog …" schliesst diesen und druckt
von dort.

Alle Einstellungen landen im Drucker der Sitzung (``printing.shared_printer``)
und gelten so auch fuer den naechsten Ausdruck.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, Qt, QTimer
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewWidget
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import printing

PDF_TARGET = "Als PDF speichern"
UPDATE_MS = 250  # Vorschau erst nach einer kurzen Pause neu setzen
STANDARD_SIZES = (QPageSize.PageSizeId.A4, QPageSize.PageSizeId.A5, QPageSize.PageSizeId.A3,
                  QPageSize.PageSizeId.Letter, QPageSize.PageSizeId.Legal)
DUPLEX = (("Einseitig", QPrinter.DuplexMode.DuplexNone),
          ("Beidseitig, lange Kante", QPrinter.DuplexMode.DuplexLongSide),
          ("Beidseitig, kurze Kante", QPrinter.DuplexMode.DuplexShortSide))


class PrintDialog(QDialog):
    def __init__(self, job: printing.PrintJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.printer = printing.shared_printer()
        self.pdf_path: str | None = None  # Ziel fuer "Als PDF speichern" (sonst Dateidialog)
        self.setWindowTitle(f"Drucken – {job.title}")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        # --- Einstellungen ---
        self.printer_box = QComboBox()
        self.printer_box.addItems(QPrinterInfo.availablePrinterNames())
        self.printer_box.addItem(PDF_TARGET)
        self.orientation_box = QComboBox()
        self.orientation_box.addItems(["Hochformat", "Querformat"])
        self.paper_box = QComboBox()
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setDecimals(0)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.setToolTip("Rand auf allen vier Seiten")
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 999)
        self.color_box = QComboBox()
        self.color_box.addItems(["Farbe", "Graustufen"])
        self.duplex_box = QComboBox()
        for text, mode in DUPLEX:
            self.duplex_box.addItem(text, mode)
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("Alle – oder z. B. 1-3, 5")
        self.pages_edit.setClearButtonEnabled(True)
        self.pages_hint = QLabel()
        self.pages_hint.setObjectName("hint")
        self.pages_hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Drucker", self.printer_box)
        form.addRow("Ausrichtung", self.orientation_box)
        form.addRow("Papier", self.paper_box)
        form.addRow("Ränder", self.margin_spin)
        form.addRow("Kopien", self.copies_spin)
        form.addRow("Farbmodus", self.color_box)
        form.addRow("Beidseitig", self.duplex_box)
        form.addRow("Seiten", self.pages_edit)
        form.addRow("", self.pages_hint)
        native = QPushButton("Windows-Druckdialog …")
        native.setToolTip("Druckerspezifische Einstellungen wie Papierart oder Druckqualität – "
                          "gedruckt wird dann von dort")
        native.setAutoDefault(False)  # Enter druckt, nicht dieser Knopf
        native.clicked.connect(self._native)
        left = QVBoxLayout()
        left.addLayout(form)
        left.addWidget(native)
        left.addStretch(1)
        left_box = QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(320)

        # --- Vorschau ---
        self.preview = QPrintPreviewWidget(self.printer, self)
        self.preview.paintRequested.connect(self._paint)
        self.preview.previewChanged.connect(self._update_nav)
        nav = QHBoxLayout()

        def tool(text: str, tip: str, slot) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            nav.addWidget(b)
            return b

        tool("◀", "Vorige Seite", lambda: self._go(-1))
        self.page_label = QLabel()
        nav.addWidget(self.page_label)
        tool("▶", "Nächste Seite", lambda: self._go(1))
        nav.addStretch(1)
        tool("−", "Verkleinern", self.preview.zoomOut)
        tool("+", "Vergrößern", self.preview.zoomIn)
        tool("Ganze Seite", "Ganze Seite zeigen", self.preview.fitInView)
        tool("Breite", "An die Breite anpassen", self.preview.fitToWidth)
        right = QVBoxLayout()
        right.addLayout(nav)
        right.addWidget(self.preview, 1)

        body = QHBoxLayout()
        body.addWidget(left_box)
        body.addLayout(right, 1)

        self.buttons = QDialogButtonBox()
        self.print_button = self.buttons.addButton("Drucken", QDialogButtonBox.ButtonRole.AcceptRole)
        self.print_button.setDefault(True)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.buttons)

        if parent is not None:
            win = parent.window().geometry()
            self.resize(max(900, int(win.width() * 0.85)), max(620, int(win.height() * 0.9)))
        else:
            self.resize(1000, 720)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(UPDATE_MS)
        self._timer.timeout.connect(self._update_preview)
        self._load_from_printer()
        self.printer_box.currentIndexChanged.connect(self._on_printer_changed)
        for box in (self.orientation_box, self.paper_box, self.color_box, self.duplex_box):
            box.currentIndexChanged.connect(self._schedule)
        self.margin_spin.valueChanged.connect(self._schedule)
        self.pages_edit.textChanged.connect(self._schedule)
        self.apply()

    # --- Drucker <-> Felder ---

    def is_pdf(self) -> bool:
        return self.printer_box.currentText() == PDF_TARGET

    def _load_from_printer(self) -> None:
        p = self.printer
        name = p.printerName() if p.outputFormat() == QPrinter.OutputFormat.NativeFormat else ""
        index = self.printer_box.findText(name) if name else -1
        if index < 0 and not name:
            index = self.printer_box.findText(QPrinterInfo.defaultPrinterName())
        self.printer_box.blockSignals(True)
        self.printer_box.setCurrentIndex(index if index >= 0 else self.printer_box.count() - 1)
        self.printer_box.blockSignals(False)
        self._fill_capabilities()
        layout = p.pageLayout()
        self.orientation_box.setCurrentIndex(1 if layout.orientation() == QPageLayout.Orientation.Landscape else 0)
        self._select_paper(layout.pageSize().id())
        self.margin_spin.setValue(round(layout.margins(QPageLayout.Unit.Millimeter).left()))
        self.copies_spin.setValue(max(1, p.copyCount()))
        self.color_box.setCurrentIndex(1 if p.colorMode() == QPrinter.ColorMode.GrayScale else 0)
        self.duplex_box.setCurrentIndex(max(0, self.duplex_box.findData(p.duplex())))

    def _fill_capabilities(self) -> None:
        """Papierformate und Beidseitig-Druck, die der gewaehlte Drucker kann."""
        info = None if self.is_pdf() else QPrinterInfo.printerInfo(self.printer_box.currentText())
        sizes = [s for s in (info.supportedPageSizes() if info and not info.isNull() else []) if s.isValid()]
        if not sizes:
            sizes = [QPageSize(i) for i in STANDARD_SIZES]
        current = self.paper_box.currentData()
        self.paper_box.blockSignals(True)
        self.paper_box.clear()
        for size in sizes:
            self.paper_box.addItem(size.name(), size)
        self.paper_box.blockSignals(False)
        if isinstance(current, QPageSize):
            self._select_paper(current.id())
        modes = set(info.supportedDuplexModes()) if info and not info.isNull() else set()
        can_duplex = bool(modes - {QPrinter.DuplexMode.DuplexNone, QPrinter.DuplexMode.DuplexAuto})
        self.duplex_box.setEnabled(can_duplex)
        if not can_duplex:
            self.duplex_box.setCurrentIndex(0)

    def _select_paper(self, size_id) -> None:
        for i in range(self.paper_box.count()):
            if self.paper_box.itemData(i).id() == size_id:
                self.paper_box.setCurrentIndex(i)
                return
        a4 = next((i for i in range(self.paper_box.count())
                   if self.paper_box.itemData(i).id() == QPageSize.PageSizeId.A4), 0)
        self.paper_box.setCurrentIndex(a4)

    def _on_printer_changed(self) -> None:
        self._fill_capabilities()
        self._schedule()

    def apply(self) -> bool:
        """Felder auf den Drucker uebertragen. False, wenn die Seitenangabe nicht stimmt."""
        p = self.printer
        if self.is_pdf():
            p.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        else:
            p.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
            p.setPrinterName(self.printer_box.currentText())
        size = self.paper_box.currentData()
        if isinstance(size, QPageSize):
            p.setPageSize(size)
        p.setPageOrientation(QPageLayout.Orientation.Landscape if self.orientation_box.currentIndex()
                             else QPageLayout.Orientation.Portrait)
        m = self.margin_spin.value()
        p.setPageMargins(QMarginsF(m, m, m, m), QPageLayout.Unit.Millimeter)
        p.setCopyCount(self.copies_spin.value())
        p.setColorMode(QPrinter.ColorMode.GrayScale if self.color_box.currentIndex() else QPrinter.ColorMode.Color)
        p.setDuplex(self.duplex_box.currentData() if self.duplex_box.isEnabled() else QPrinter.DuplexMode.DuplexNone)
        ranges = printing.parse_pages(self.pages_edit.text())
        valid = ranges is not None
        if valid and not ranges.isEmpty():
            p.setPrintRange(QPrinter.PrintRange.PageRange)
            p.setPageRanges(ranges)
        else:
            p.setPrintRange(QPrinter.PrintRange.AllPages)
        self.pages_hint.setText("" if valid else "Seiten wie 1-3, 5 angeben")
        self.print_button.setEnabled(valid)
        return valid

    # --- Vorschau ---

    def _schedule(self, *_args) -> None:
        self._timer.start()

    def _update_preview(self) -> None:
        if self.apply():
            self.preview.updatePreview()

    def _paint(self, target) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.job.paint(target)
        finally:
            QApplication.restoreOverrideCursor()

    def _go(self, step: int) -> None:
        self.preview.setCurrentPage(self.preview.currentPage() + step)
        self._update_nav()

    def _update_nav(self) -> None:
        n = self.preview.pageCount()
        self.page_label.setText(f" Seite {self.preview.currentPage()} von {n} " if n else " keine Seiten ")

    # --- Drucken ---

    def print_now(self) -> bool:
        """Mit den Einstellungen drucken; False, wenn der Dateidialog abgebrochen wurde."""
        if not self.apply():
            return False
        p = self.printer
        if self.is_pdf():
            path = self.pdf_path
            if path is None:
                start = str(Path.home() / f"{Path(self.job.title).stem or 'Druck'}.pdf")
                path, _f = QFileDialog.getSaveFileName(self, PDF_TARGET, start, "PDF (*.pdf)")
            if not path:
                return False
            p.setOutputFileName(path)
        else:
            p.setOutputFileName("")
        try:
            printing._run(self, self.job, p)
        finally:
            p.setOutputFileName("")
        return True

    def accept(self) -> None:
        if self.print_now():
            super().accept()

    def _native(self) -> None:
        self.apply()
        self.hide()
        if printing.print_job_native(self.parentWidget(), self.job):
            super().accept()
            return
        self._load_from_printer()  # der Windows-Dialog kann Drucker und Format geaendert haben
        self.show()
        self._schedule()
