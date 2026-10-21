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
