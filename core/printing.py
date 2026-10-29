"""Drucken, Seitenansicht und Seite einrichten -- fuer CompletionistPDF und CompletionistMD.

Ein ``PrintJob`` kennt seine Seitenzahl und malt sich auf einen ``QPrinter``.
Alle drei Wege nutzen denselben Drucker der Sitzung, damit Papierformat,
Hoch-/Querformat und Raender aus *Seite einrichten* bis zum Programmende gelten:

* ``print_job``   -- Druckdialog (Drucker, Seiten, Kopien), dann drucken
* ``preview_job`` -- Seitenansicht (``QPrintPreviewDialog``): Zoom, Seite/Doppelseite/
  Uebersicht, Hoch-/Querformat, Seite einrichten und Drucken direkt aus der Vorschau
* ``page_setup``  -- Papierformat, Ausrichtung, Raender

PDF-Seiten rendert QtPdf als Bild in Druckaufloesung (hoechstens 600 dpi:
scharfe Schrift auch auf Laserdruckern; eine A4-Seite braucht dabei rund
140 MB, gerendert wird immer nur eine Seite auf einmal) und setzt es
seitenfuellend, mit erhaltenem Seitenverhaeltnis, auf das Blatt. Die
Seitenansicht haelt dagegen alle Seiten im Speicher und rendert deshalb
grober (``preview_dpi``).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

MAX_DPI = 600
PREVIEW_MAX_DPI = 150
PREVIEW_MIN_DPI = 50
PREVIEW_BUDGET = 400 * 1024 * 1024  # Bytes fuer alle Seiten der Seitenansicht zusammen

_printer = None


def shared_printer():
    """Der Drucker der Sitzung -- haelt Papierformat, Ausrichtung und Raender."""
    global _printer
    if _printer is None:
        from PySide6.QtPrintSupport import QPrinter

        _printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    return _printer


def is_preview(painter) -> bool:
    """Malt der Painter in die Seitenansicht (QPicture) statt auf einen Drucker?"""
    from PySide6.QtGui import QPaintEngine

    engine = painter.paintEngine()
    return engine is not None and engine.type() == QPaintEngine.Type.Picture


def preview_dpi(pages: int, page_inch2: float = 8.27 * 11.69) -> int:
    """Aufloesung, bei der alle Seiten zusammen ins Speicherbudget passen."""
    if pages <= 0:
        return PREVIEW_MAX_DPI
    dpi = math.sqrt(PREVIEW_BUDGET / (pages * page_inch2 * 4))
    return int(max(PREVIEW_MIN_DPI, min(PREVIEW_MAX_DPI, dpi)))


def page_range(printer, pages: int) -> tuple[int, int]:
    """Gewaehlte Seiten (1-basiert, einschliesslich) -- ohne Auswahl alle."""
    from PySide6.QtPrintSupport import QPrinter

    first, last = printer.fromPage(), printer.toPage()
    if printer.printRange() != QPrinter.PrintRange.PageRange or first == 0:
        return 1, pages
    return max(1, first), min(pages, last or pages)


# ---------------------------------------------------------------------- #
# Druckauftraege
# ---------------------------------------------------------------------- #


class PrintJob:
    """Basis: ``page_count`` (0 = unbekannt) und ``paint``."""

    def __init__(self, title: str) -> None:
        self.title = title

    def page_count(self) -> int:
        return 0

    def paint(self, printer) -> bool:
        """Auf ``printer`` drucken; False, wenn sich der Drucker nicht ansprechen liess."""
        raise NotImplementedError


class PdfJob(PrintJob):
    """Seiten eines geladenen ``QPdfDocument``."""

    def __init__(self, doc, title: str) -> None:
        super().__init__(title)
        self.doc = doc

    def page_count(self) -> int:
        return self.doc.pageCount() if self.doc is not None else 0

    def paint(self, printer) -> bool:
        from PySide6.QtGui import QPainter

        pages = self.page_count()
        first, last = page_range(printer, pages)
        painter = QPainter()
        if not painter.begin(printer):
            return False
        dpi = preview_dpi(last - first + 1) if is_preview(painter) else min(printer.resolution(), MAX_DPI)
        try:
            for n, page in enumerate(range(first - 1, last)):
                if n:
                    printer.newPage()
                pt = self.doc.pagePointSize(page)
                size = QSize(max(1, round(pt.width() / 72 * dpi)), max(1, round(pt.height() / 72 * dpi)))
                image = self.doc.render(page, size)
                target = QRectF(painter.viewport())
                scale = min(target.width() / size.width(), target.height() / size.height())
                w, h = size.width() * scale, size.height() * scale
                painter.drawImage(QRectF(target.x() + (target.width() - w) / 2,
                                         target.y() + (target.height() - h) / 2, w, h), image)
                QApplication.processEvents()
        finally:
            painter.end()
        return True


class TextDocumentJob(PrintJob):
    """Ein ``QTextDocument`` (Text-Tab, Office-Ansicht ohne LibreOffice).
    Qt bricht den Text selbst auf die Seiten um."""

    def __init__(self, document, title: str) -> None:
        super().__init__(title)
        self.document = document

    def paint(self, printer) -> bool:
        doc = self.document.clone()
        doc.print_(printer)
        doc.deleteLater()
        return True


class ImageJob(PrintJob):
    """Ein Bild, eingepasst und zentriert auf einer Seite."""

    def __init__(self, image, title: str) -> None:
        super().__init__(title)
        self.image = image  # QImage

    def page_count(self) -> int:
        return 1

    def paint(self, printer) -> bool:
        from PySide6.QtGui import QPainter

        painter = QPainter()
        if not painter.begin(printer):
            return False
        try:
            target = QRectF(painter.viewport())
            w, h = self.image.width(), self.image.height()
            if w and h:
                # kleine Bilder nicht aufblasen: hoechstens 1:1 bei 96 dpi
                natural = printer.resolution() / 96
                scale = min(target.width() / w, target.height() / h, natural)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(QRectF(target.x() + (target.width() - w * scale) / 2,
                                         target.y() + (target.height() - h * scale) / 2,
                                         w * scale, h * scale), self.image)
        finally:
            painter.end()
        return True


# ---------------------------------------------------------------------- #
# Dialoge
# ---------------------------------------------------------------------- #


def _run(parent: QWidget | None, job: PrintJob, printer) -> None:
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        ok = job.paint(printer)
    finally:
        QApplication.restoreOverrideCursor()
    if not ok:
        QMessageBox.warning(parent, "Drucken", "Der Drucker ließ sich nicht ansprechen.")


def _prepare(job: PrintJob):
    from PySide6.QtPrintSupport import QPrinter

    printer = shared_printer()
    printer.setDocName(job.title)
    printer.setPrintRange(QPrinter.PrintRange.AllPages)
    pages = job.page_count()
    if pages:
        printer.setFromTo(1, pages)
    else:
        printer.setFromTo(0, 0)
    return printer, pages


def print_job(parent: QWidget | None, job: PrintJob) -> None:
    """Druckdialog zeigen und drucken."""
    from PySide6.QtPrintSupport import QPrintDialog

    printer, pages = _prepare(job)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle(f"Drucken – {job.title}")
    dlg.setMinMax(1, pages or 9999)
    if dlg.exec() != QPrintDialog.DialogCode.Accepted:
        return
    _run(parent, job, printer)


def preview_job(parent: QWidget | None, job: PrintJob) -> None:
    """Seitenansicht; aus ihr heraus lassen sich Seite einrichten und drucken."""
    from PySide6.QtPrintSupport import QPrintPreviewDialog

    printer, _pages = _prepare(job)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f"Seitenansicht – {job.title}")
    dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    if parent is not None:
        win = parent.window().geometry()
        dlg.resize(max(800, int(win.width() * 0.85)), max(600, int(win.height() * 0.9)))

    def paint(target) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            job.paint(target)
        finally:
            QApplication.restoreOverrideCursor()

    dlg.paintRequested.connect(paint)
    dlg.exec()


def page_setup(parent: QWidget | None) -> bool:
    """Papierformat, Ausrichtung und Raender fuer alle weiteren Ausdrucke."""
    from PySide6.QtPrintSupport import QPageSetupDialog

    dlg = QPageSetupDialog(shared_printer(), parent)
    dlg.setWindowTitle("Seite einrichten")
    return dlg.exec() == QPageSetupDialog.DialogCode.Accepted


def print_document(parent: QWidget | None, doc, title: str) -> None:
    """``doc``: geladenes ``QPdfDocument`` -- Druckdialog, dann drucken."""
    if doc is None or doc.pageCount() <= 0:
        QMessageBox.information(parent, "Drucken", "Es ist kein PDF geladen.")
        return
    print_job(parent, PdfJob(doc, title))


def preview_document(parent: QWidget | None, doc, title: str) -> None:
    """``doc``: geladenes ``QPdfDocument`` -- Seitenansicht."""
    if doc is None or doc.pageCount() <= 0:
        QMessageBox.information(parent, "Seitenansicht", "Es ist kein PDF geladen.")
        return
    preview_job(parent, PdfJob(doc, title))
