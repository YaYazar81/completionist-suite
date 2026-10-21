"""Qt-eigene Texte in der Systemsprache: Ja/Nein/Abbrechen in Dialogen,
Kontextmenues von Textfeldern (Kopieren, Einfuegen ...), bei MD auch das
Kontextmenue der Editor-Ansicht. Ohne Uebersetzer zeigt Qt diese auf Englisch.

Die .qm-Dateien liegen in PySide6/translations; build_exe.py nimmt die
benoetigten mit (KEEP_QT_TRANSLATIONS).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator


def _folders() -> list[str]:
    folders = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    try:  # in der gepackten App zeigt QLibraryInfo nicht immer auf _internal
        import PySide6

        pkg = Path(PySide6.__file__).resolve().parent
        folders += [str(pkg / "translations"), str(pkg / "Qt" / "translations")]  # Windows, Linux
    except Exception:
        pass
    return folders


def install(app: QCoreApplication, catalogs: tuple[str, ...] = ("qtbase",)) -> list[str]:
    """Laedt die Kataloge fuer die Systemsprache; gibt die geladenen zurueck."""
    locale = QLocale.system()
    loaded = []
    for name in catalogs:
        translator = QTranslator(app)
        if any(translator.load(locale, name, "_", folder) for folder in _folders()):
            app.installTranslator(translator)
            loaded.append(name)
    return loaded
