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

    src = QPdfDocument(None)
    src.load(str(ROOT / "examples" / "demo.pdf"))
    assert src.pageCount() > 0
    print_document(None, src, "demo")

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
