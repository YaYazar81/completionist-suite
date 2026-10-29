"""Drucken in CompletionistPDF -- auf einen PDF-"Drucker" statt auf Papier."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtPrintSupport  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from gui.printing import print_document  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["pytest"])
    yield app


def test_all_pages_are_printed(qapp, tmp_path, monkeypatch):
    out = tmp_path / "gedruckt.pdf"

    class FakeDialog:
        def __init__(self, printer, parent=None):
            printer.setOutputFormat(QtPrintSupport.QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(out))
            printer.setResolution(72)

        def setWindowTitle(self, _t):  # noqa: N802
            pass

        def setMinMax(self, *_a):  # noqa: N802
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    FakeDialog.DialogCode = QDialog.DialogCode
    monkeypatch.setattr(QtPrintSupport, "QPrintDialog", FakeDialog)

    from core import printing

    src = QPdfDocument(None)
    src.load(str(ROOT / "examples" / "demo.pdf"))
    assert src.pageCount() > 0
    assert printing.print_job_native(None, printing.PdfJob(src, "demo"))

    printed = QPdfDocument(None)
    printed.load(str(out))
    assert printed.pageCount() == src.pageCount()


def test_preview_renders_every_page_with_low_resolution(qapp, monkeypatch):
    from PySide6.QtPrintSupport import QPrintPreviewWidget

    from core import printing

    src = QPdfDocument(None)
    src.load(str(ROOT / "examples" / "demo.pdf"))
    job = printing.PdfJob(src, "demo")
    seen = []
    real_render = src.render
    monkeypatch.setattr(src, "render", lambda page, size: (seen.append(size), real_render(page, size))[1])

    printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.PrinterMode.HighResolution)
    widget = QPrintPreviewWidget(printer)
    widget.paintRequested.connect(job.paint)
    widget.updatePreview()
    assert widget.pageCount() == src.pageCount()
    # Seitenansicht: hoechstens PREVIEW_MAX_DPI statt Druckaufloesung
    assert max(s.width() for s in seen) <= round(8.5 * printing.PREVIEW_MAX_DPI)


def test_page_range_and_preview_dpi():
    from core import printing

    printer = QtPrintSupport.QPrinter()
    assert printing.page_range(printer, 7) == (1, 7)
    printer.setPrintRange(QtPrintSupport.QPrinter.PrintRange.PageRange)
    printer.setFromTo(2, 4)
    assert printing.page_range(printer, 7) == (2, 4)
    assert printing.preview_dpi(1) == printing.PREVIEW_MAX_DPI
    assert printing.preview_dpi(300) < printing.PREVIEW_MAX_DPI
    assert printing.preview_dpi(100_000) == printing.PREVIEW_MIN_DPI


def _demo_dialog(tmp_path):
    from core import printing
    from core.print_dialog import PDF_TARGET, PrintDialog

    src = QPdfDocument(None)
    src.load(str(ROOT / "examples" / "demo.pdf"))
    dlg = PrintDialog(printing.PdfJob(src, "demo.pdf"))
    dlg.printer_box.setCurrentIndex(dlg.printer_box.findText(PDF_TARGET))
    dlg.pdf_path = str(tmp_path / "out.pdf")
    return dlg, src


def test_print_dialog_preview_follows_settings_and_prints_page_ranges(qapp, tmp_path):
    from PySide6.QtGui import QPageLayout

    dlg, src = _demo_dialog(tmp_path)
    dlg._update_preview()
    assert dlg.preview.pageCount() == src.pageCount()

    dlg.pages_edit.setText("2-3")
    dlg.orientation_box.setCurrentIndex(1)
    dlg._update_preview()
    assert dlg.preview.pageCount() == 2  # die Vorschau zeigt, was gedruckt wird
    assert dlg.printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape
    assert "von 2" in dlg.page_label.text()

    assert dlg.print_now()
    printed = QPdfDocument(None)
    printed.load(str(tmp_path / "out.pdf"))
    assert printed.pageCount() == 2
    size = printed.pagePointSize(0)
    assert size.width() > size.height()  # Querformat


def test_print_dialog_rejects_bad_page_ranges(qapp, tmp_path):
    dlg, _src = _demo_dialog(tmp_path)
    dlg.pages_edit.setText("drei")
    assert not dlg.apply()
    assert not dlg.print_button.isEnabled()
    assert dlg.pages_hint.text()
    dlg.pages_edit.setText("1, 3-")
    assert dlg.apply() and dlg.print_button.isEnabled()


def test_text_document_honours_page_ranges(qapp, tmp_path):
    from PySide6.QtGui import QTextDocument

    from core import printing

    doc = QTextDocument()
    doc.setPlainText("\n".join(f"Zeile {n}" for n in range(400)))
    out = tmp_path / "text.pdf"
    printer = QtPrintSupport.QPrinter()
    printer.setOutputFormat(QtPrintSupport.QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(out))
    printer.setPrintRange(QtPrintSupport.QPrinter.PrintRange.PageRange)
    printer.setPageRanges(printing.parse_pages("2"))
    printing.TextDocumentJob(doc, "t").paint(printer)
    printed = QPdfDocument(None)
    printed.load(str(out))
    assert printed.pageCount() == 1


def test_cancel_windows_dialog_then_print_dialog(qapp, tmp_path, monkeypatch):
    """Windows-Druckdialog abbrechen, dann den eigenen: der eigene Dialog muss dabei
    durchgehend laufen (frueher beendete hide() seine Schleife -> Absturz)."""
    from PySide6.QtCore import QTimer

    from core import printing
    from core.print_dialog import PrintDialog

    src = QPdfDocument(None)
    src.load(str(ROOT / "examples" / "demo.pdf"))
    steps = []

    def fake_native(parent, job):
        steps.append(("native", parent.isVisible()))
        return False  # abgebrochen

    monkeypatch.setattr(printing, "print_job_native", fake_native)
    created = []
    real_init = PrintDialog.__init__

    def track(self, *a, **kw):
        real_init(self, *a, **kw)
        created.append(self)

    monkeypatch.setattr(PrintDialog, "__init__", track)

    def drive():
        dlg = created[0]
        dlg._native()
        steps.append(("after", dlg.isVisible()))
        QTimer.singleShot(0, dlg.reject)

    QTimer.singleShot(0, drive)
    printing.print_job(None, printing.PdfJob(src, "demo"))
    assert steps == [("native", True), ("after", True)]
