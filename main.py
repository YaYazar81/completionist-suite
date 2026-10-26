"""CompletionistPDF -- Markdown zu professionellem PDF ueber Typst, dazu PDF-Viewer."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    if sys.platform == "win32":
        # Eigene App-ID: Ohne sie leitet die Taskleiste das Programm aus dem
        # .exe-Pfad ab und nimmt das Icon aus dem Shell-Cache von Windows. Der
        # hielt nach dem Austausch der .exe einen leeren Eintrag fest. Mit ID
        # zeigt sie das Fenster-Icon (wie bei CompletionistQR).
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CompletionistPDF.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("CompletionistPDF")
    # Ja/Nein/Abbrechen und Kontextmenues auf Deutsch statt Englisch
    from core import qt_translations

    qt_translations.install(app)
    # Completionist Pro (Schiefer & Smaragd), gemeinsam mit CompletionistMD
    from core import design

    design.apply(app)

    # Fenster- und Taskleisten-Icon (das .exe-Icon setzt build_exe.py)
    icon_path = APP_DIR / "assets" / "icon_pdf.ico"
    if icon_path.is_file():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon_path)))

    # Startbild, waehrend das Hauptfenster aufgebaut wird
    from core import splash

    splash_screen = splash.show(app, APP_DIR / "assets" / "splash_pdf.jpg")

    # Datei als Argument (z. B. per "Öffnen mit"): .md startet den
    # Markdown-Modus, .pdf den Viewer-Modus ohne Typst
    path = sys.argv[1] if len(sys.argv) > 1 and Path(sys.argv[1]).is_file() else None
    win = MainWindow(APP_DIR, path)
    splash.finish(splash_screen, win)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
