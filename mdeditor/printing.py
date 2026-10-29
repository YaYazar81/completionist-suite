"""Markdown drucken: Chromium setzt die Editor-Seite als PDF, gedruckt wird das PDF.

Das PDF entsteht passend zum Druckbereich des Druckers (Papierformat minus
Raender aus *Seite einrichten*), ohne eigene Raender -- auf das Blatt kommt es
dann 1:1. Aendert man in der Seitenansicht Format oder Ausrichtung, setzt
Chromium das Dokument neu. Wie es auf Papier aussieht, regelt ``@media print``
in ``assets/editor/editor.css`` (immer hell, ``***`` = Seitenumbruch,
aufgeklappte Syntax und Suchtreffer bleiben weg).
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QMarginsF, QSizeF, QTimer
from PySide6.QtGui import QPageLayout, QPageSize

from core.printing import PdfJob, shared_printer

RENDER_TIMEOUT_MS = 120_000  # 300-Seiten-Guides brauchen einige Sekunden


def content_layout(printer) -> QPageLayout:
    """Seite in der Groesse des bedruckbaren Bereichs, ohne Raender."""
    rect = printer.pageLayout().paintRect(QPageLayout.Unit.Point)
    size = QPageSize(QSizeF(rect.width(), rect.height()), QPageSize.Unit.Point, "",
                     QPageSize.SizeMatchPolicy.ExactMatch)
    return QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))


class WebPdfJob(PdfJob):
    """Druckauftrag fuer eine ``QWebEnginePage`` (den Markdown-Editor)."""

    def __init__(self, page, title: str) -> None:
        from PySide6.QtPdf import QPdfDocument

        super().__init__(QPdfDocument(None), title)
        self.page = page
        self._layout: QPageLayout | None = None
        self._buffer: QBuffer | None = None
        self.error = ""

    def render(self, layout: QPageLayout) -> bool:
        """Seite als PDF setzen (wartet darauf). False bei Fehler oder Zeitueberschreitung."""
        if self._layout is not None and self._layout.isEquivalentTo(layout):
            return self.doc.pageCount() > 0
        loop = QEventLoop()
        result: dict = {}

        def done(data) -> None:
            result["data"] = bytes(data)
            loop.quit()

        self.page.printToPdf(done, layout)
        QTimer.singleShot(RENDER_TIMEOUT_MS, loop.quit)
        loop.exec()
        data = result.get("data", b"")
        if not data:
            self.error = "Das Dokument ließ sich nicht für den Druck setzen."
            return False
        buf = QBuffer()
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        self.doc.load(buf)
        self._buffer = buf  # muss leben, solange das Dokument geladen ist
        self._layout = QPageLayout(layout)
        return self.doc.pageCount() > 0

    def page_count(self) -> int:
        # Fuer den Druckdialog (Seitenbereich): im aktuell eingerichteten Format setzen
        if self._layout is None:
            self.render(content_layout(shared_printer()))
        return self.doc.pageCount()

    def paint(self, printer) -> bool:
        if not self.render(content_layout(printer)):
            return True  # nichts zu drucken; die Meldung zeigt der Aufrufer
        return super().paint(printer)
