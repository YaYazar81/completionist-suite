"""CompletionistPDF -- Markdown zu professionellem PDF ueber Typst, dazu PDF-Viewer."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from gui.main_window import MainWindow  # noqa: E402

ACCENT = "#00897b"  # Petrol, wie im LyX-Dialog

STYLESHEET = f"""
QToolButton#sectionHeader {{
    text-align: left;
    font-weight: 600;
    padding: 6px 4px;
    border: none;
    border-bottom: 1px solid palette(mid);
}}
QToolButton#sectionHeader:hover {{ color: {ACCENT}; }}
QFrame#sectionBody {{ border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: palette(mid); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px;
    border: 2px solid palette(base);
}}
QTabBar::tab:selected {{ border-bottom: 2px solid {ACCENT}; }}
"""


def _dark_palette() -> QPalette:
    p = QPalette()
    base, window, text = QColor("#1e1e1e"), QColor("#2b2b2b"), QColor("#e6e6e6")
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#262626"))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor("#353535"))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#353535"))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, QColor("#4db6ac"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8b8b8b"))
    p.setColor(QPalette.ColorRole.Mid, QColor("#444444"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6e6e6e"))
    return p


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
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(STYLESHEET)

    # Fenster- und Taskleisten-Icon (das .exe-Icon setzt build_exe.py)
    icon_path = APP_DIR / "assets" / "icon_pdf.ico"
    if icon_path.is_file():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon_path)))

    # Datei als Argument (z. B. per "Öffnen mit"): .md startet den
    # Markdown-Modus, .pdf den Viewer-Modus ohne Typst
    path = sys.argv[1] if len(sys.argv) > 1 and Path(sys.argv[1]).is_file() else None
    win = MainWindow(APP_DIR, path)
    win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
