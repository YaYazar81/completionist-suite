"""CompletionistMD -- WYSIWYG-Markdown-Editor fuer CompletionistPDF.

Start:  python main_md.py [datei.md]
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Vor dem QApplication importieren: QtWebEngine richtet dabei den
# gemeinsamen OpenGL-Kontext ein, den es spaeter braucht.
from mdeditor import theme  # noqa: E402
from mdeditor.window import MainWindow  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    if sys.platform == "win32":
        # Eigene App-ID: Ohne sie nimmt die Taskleiste das Icon aus dem
        # Shell-Cache von Windows (abgeleitet vom .exe-Pfad), der nach dem
        # Austausch der .exe leer bleiben kann. Mit ID zeigt sie das Fenster-Icon.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CompletionistMD.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("CompletionistMD")
    app.setApplicationDisplayName("CompletionistMD")
    app.setStyle("Fusion")
    app.setPalette(theme.dark_palette())
    app.setStyleSheet(theme.STYLESHEET)

    icon_path = APP_DIR / "assets" / "icon_md.ico"
    if icon_path.is_file():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon_path)))

    # Mehrere Fenster sind ausdruecklich erlaubt (Alt+Tab zwischen Dateien).
    # Nur das erste stellt die letzten Tabs wieder her und merkt sie sich.
    from PySide6.QtCore import QLockFile

    from core.presets import user_data_dir

    lock_dir = user_data_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "completionistmd.lock"))
    secondary = not lock.tryLock(0)

    win = MainWindow(APP_DIR, secondary=secondary)
    win._instance_lock = lock  # haelt die Sperre bis Programmende

    # Markdown-Datei als Argument (z. B. per "Oeffnen mit")
    for arg in sys.argv[1:]:
        if Path(arg).is_file():
            win.queue_open(arg)
            break

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
