"""Farben und Paletten -- gleicher Petrol-Akzent wie CompletionistPDF."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

ACCENT = "#00897b"

STYLESHEET = f"""
QToolBar {{ border: none; padding: 3px 6px; spacing: 2px; }}
QToolBar QToolButton {{ padding: 4px 7px; border-radius: 4px; }}
QToolBar QToolButton:hover {{ background: rgba(0, 137, 123, 0.22); }}
QToolBar QToolButton:checked {{ background: rgba(0, 137, 123, 0.38); }}
QToolBar::separator {{ width: 1px; background: palette(mid); margin: 4px 5px; }}
QStatusBar {{ border-top: 1px solid palette(mid); }}
QStatusBar QLabel {{ padding: 0 8px; }}
QLabel#saveState[state="dirty"] {{ color: #e0a030; }}
QLabel#saveState[state="saved"] {{ color: {ACCENT}; }}
QLabel#saveState[state="error"] {{ color: #d05050; }}

/* Vault-Explorer (mdeditor/vault.py) */
QLabel#vaultTitle {{ font-weight: 600; padding: 2px 0; }}
QLabel#vaultHint {{ color: palette(placeholder-text); padding: 6px 2px; }}
QFrame#vaultLine {{ color: palette(mid); }}
#vaultPanel QTreeView {{ border: none; background: palette(window); }}
#vaultPanel QTreeView::item {{ padding: 2px 0; }}
#vaultPanel QTreeView::item:selected {{ background: rgba(0, 137, 123, 0.38); color: palette(text); }}
QToolButton#bookmarkTile {{
    padding: 3px 9px;
    border: 1px solid palette(mid);
    border-radius: 9px;
    background: palette(button);
}}
QToolButton#bookmarkTile:hover {{ border-color: {ACCENT}; background: rgba(0, 137, 123, 0.22); }}
QSplitter::handle {{ background: palette(mid); width: 1px; }}
"""


def dark_palette() -> QPalette:
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
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6e6e6e"))
    return p


def light_palette() -> QPalette:
    p = QPalette()
    base, window, text = QColor("#ffffff"), QColor("#f2f2f2"), QColor("#1f1f1f")
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#e9e9e9"))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor("#e4e4e4"))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f1f1f"))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, QColor("#00695c"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8b8b8b"))
    p.setColor(QPalette.ColorRole.Mid, QColor("#c8c8c8"))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#a0a0a0"))
    return p


def palette_for(theme: str) -> QPalette:
    return light_palette() if theme == "light" else dark_palette()
