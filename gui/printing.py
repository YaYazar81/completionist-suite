"""PDF drucken: Seiten aus einem QPdfDocument ueber den Windows-Druckdialog.

QtPdf rendert jede Seite als Bild in Druckaufloesung (hoechstens 300 dpi,
damit grosse Dokumente den Speicher nicht sprengen) und setzt es
seitenfuellend, mit erhaltenem Seitenverhaeltnis, auf das Blatt.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

MAX_DPI = 300


def print_document(parent: QWidget, doc, title: str) -> None:
    """``doc``: geladenes ``QPdfDocument``."""
    from PySide6.QtGui import QPainter
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter

    pages = doc.pageCount() if doc is not None else 0
    if pages <= 0:
        QMessageBox.information(parent, "Drucken", "Es ist kein PDF geladen.")
        return
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(title)
    printer.setFromTo(1, pages)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle(f"Drucken – {title}")
    dlg.setMinMax(1, pages)
    if dlg.exec() != QPrintDialog.DialogCode.Accepted:
        return

    first, last = printer.fromPage(), printer.toPage()
    if first == 0:  # "Alle Seiten"
        first, last = 1, pages
    dpi = min(printer.resolution(), MAX_DPI)

    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, "Drucken", "Der Drucker ließ sich nicht ansprechen.")
        return
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        for n, page in enumerate(range(first - 1, last)):
            if n:
                printer.newPage()
            pt = doc.pagePointSize(page)
            size = QSize(max(1, round(pt.width() / 72 * dpi)), max(1, round(pt.height() / 72 * dpi)))
            image = doc.render(page, size)
            target = QRectF(painter.viewport())
            scale = min(target.width() / size.width(), target.height() / size.height())
            w, h = size.width() * scale, size.height() * scale
            painter.drawImage(QRectF(target.x() + (target.width() - w) / 2,
                                     target.y() + (target.height() - h) / 2, w, h), image)
            QApplication.processEvents()
    finally:
        painter.end()
        QApplication.restoreOverrideCursor()
