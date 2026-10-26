"""PDF-Tab von CompletionistMD: Suche, die im Hintergrund laeuft."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

# Beim Sammeln importieren, also bevor irgendein Test eine QApplication
# anlegt: mdeditor zieht QtWebEngineWidgets nach, und das muss vorher geladen sein.
from mdeditor.tabs import PdfTab  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["pytest"])  # argv[0] braucht QtWebEngine
    yield app


def wait_for(app, condition, seconds: float = 5) -> bool:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return condition()


def test_search_enter_right_after_typing_jumps_to_first_hit(qapp):
    # "Guide" kommt in examples/demo.pdf zweimal vor.
    tab = PdfTab(ROOT / "examples" / "demo.pdf")
    tab.resize(800, 600)
    tab.find_edit.setText("Guide")
    tab.find_next()  # Enter, bevor die Suche im Hintergrund fertig ist
    assert wait_for(qapp, lambda: tab.find_label.text().strip().startswith("1 /"))
    assert wait_for(qapp, lambda: tab.search.count() == 2)
    assert tab.view.currentSearchResultIndex() == 0
    assert tab.find_label.text().strip() == "1 / 2"

    tab.find_next()
    assert tab.find_label.text().strip() == "2 / 2"
    tab.find_next()  # wieder von vorn
    assert tab.find_label.text().strip() == "1 / 2"
    tab.find_prev()
    assert tab.find_label.text().strip() == "2 / 2"


def test_text_can_be_selected_and_copied(qapp):
    from PySide6.QtGui import QGuiApplication

    tab = PdfTab(ROOT / "examples" / "demo.pdf")
    tab.resize(800, 600)
    tab.show()
    tab.selector.select_all()
    assert "Zweites Kapitel" in tab.selector.text()
    tab.selector.copy()
    assert "Zweites Kapitel" in QGuiApplication.clipboard().text()
    tab.close()
