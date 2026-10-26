"""Startbild (Splash-Screen) fuer CompletionistPDF und CompletionistMD (Qt).

Das Bild steht rund 1,2 Sekunden; das Hauptfenster wird in der Zeit schon
aufgebaut und erscheint, sobald das Bild verschwindet.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen, QWidget

DURATION_MS = 1200
SIZE = 520  # Kantenlaenge in logischen Pixeln (das Bild ist quadratisch)


def show(app: QApplication, image: Path) -> QSplashScreen | None:
    """Zeigt das Startbild; None, wenn das Bild fehlt."""
    pix = QPixmap(str(image))
    if pix.isNull():
        return None
    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    side = round(SIZE * dpr)
    pix = pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    pix.setDevicePixelRatio(dpr)
    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    splash.setProperty("shown_at", time.monotonic())
    return splash


def finish(splash: QSplashScreen | None, win: QWidget) -> None:
    """Zeigt das Hauptfenster, sobald das Startbild seine Zeit gestanden hat."""
    if splash is None:
        win.show()
        return
    elapsed = int((time.monotonic() - splash.property("shown_at")) * 1000)

    def done() -> None:
        win.show()
        splash.finish(win)

    QTimer.singleShot(max(0, DURATION_MS - elapsed), done)
