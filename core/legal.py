"""Rechtliche Angaben der Suite an einer Stelle: Copyright, Lizenz, Fremdkomponenten.

Ohne Qt -- CompletionistQR (Tkinter) nutzt dieselben Texte wie PDF und MD.
"""

from __future__ import annotations

import sys
from pathlib import Path

COPYRIGHT = "© 2026 Mike-Dominique Horch (Completionist Library)"
PUBLISHER = "Completionist Library"
CONTACT = "mail@mike-horch.de"
LICENSE_NAME = "CC BY-NC-ND 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.de"
LICENSE_SUMMARY = (
    "Der eigene Code dieses Programms steht unter der Creative-Commons-Lizenz "
    "Namensnennung – Nicht kommerziell – Keine Bearbeitungen 4.0 International "
    f"({LICENSE_NAME}). Weitergabe erlaubt mit Namensnennung, nicht kommerziell, "
    "ohne veränderte Fassungen."
)
LGPL_NOTICE = (
    "Dieses Programm nutzt Qt und PySide6 (Qt for Python) unter der GNU Lesser General "
    "Public License v3 (LGPL v3). Die Qt- und PySide6-Bibliotheken liegen als eigene "
    "DLL-/PYD-Dateien im Programmordner (_internal) und dürfen durch eigene, kompatible "
    "Fassungen ersetzt werden. Quellcode: https://download.qt.io/official_releases/qt/ "
    "und https://code.qt.io/cgit/pyside/pyside-setup.git/ (unveränderte Fassung "
    "PySide6 {pyside} von PyPI)."
)


def lgpl_notice() -> str:
    try:
        import PySide6

        v = PySide6.__version__
    except Exception:
        v = "6"
    return LGPL_NOTICE.replace("{pyside}", v)


# Impressum (freiwillig): privates, kostenloses Freizeitprojekt
IMPRESSUM_NOTE = (
    "Diese App ist ein rein privates, kostenloses Freizeitprojekt. Es wird keinerlei "
    "kommerzieller Zweck verfolgt und kein Geld mit der App verdient."
)
IMPRESSUM_DEVELOPER = "Mike-Dominique Horch [YaYazar81]"
IMPRESSUM_EMAIL = "kontakt@completionist-library.de"
IMPRESSUM_GITHUB = "https://github.com/YaYazar81/completionist-suite"


def impressum_html() -> str:
    """Impressum fuer den Reiter im Qt-Dialog "Über …"."""
    return (
        "<h3>Impressum</h3>"
        "<h4>Kontakt &amp; Support</h4>"
        f"<p>{IMPRESSUM_NOTE}</p>"
        "<h4>Entwickler</h4>"
        f"<p>{IMPRESSUM_DEVELOPER}</p>"
        "<h4>Kontakt</h4>"
        f"<p><b>E-Mail:</b> <a href='mailto:{IMPRESSUM_EMAIL}'>{IMPRESSUM_EMAIL}</a> oder via<br>"
        f"<b>GitHub:</b> <a href='{IMPRESSUM_GITHUB}'>{IMPRESSUM_GITHUB}</a></p>"
    )


def impressum_text() -> str:
    """Impressum als reiner Text (CompletionistQR, Tkinter)."""
    return (
        "Impressum\n\n"
        f"Kontakt & Support\n{IMPRESSUM_NOTE}\n\n"
        f"Entwickler\n{IMPRESSUM_DEVELOPER}\n\n"
        f"Kontakt\nE-Mail: {IMPRESSUM_EMAIL} oder via\nGitHub: {IMPRESSUM_GITHUB}\n"
    )


NOTICES_FILE = "THIRD_PARTY_NOTICES.md"
LICENSES_DIR = "Lizenzen"


def program_dir() -> Path:
    """Ordner der .exe (bzw. das Projekt beim Start aus dem Quellcode)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def licenses_dir() -> Path | None:
    """Ordner mit den vollstaendigen Lizenztexten (nur in der installierten App)."""
    d = program_dir() / LICENSES_DIR
    return d if d.is_dir() else None


def notices_text() -> str:
    """Inhalt von THIRD_PARTY_NOTICES.md (Programmordner, Bundle oder Projekt)."""
    candidates = [program_dir() / LICENSES_DIR / NOTICES_FILE, program_dir() / NOTICES_FILE]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / NOTICES_FILE)
    for c in candidates:
        try:
            return c.read_text(encoding="utf-8")
        except OSError:
            continue
    return "Die Liste der Fremdkomponenten (THIRD_PARTY_NOTICES.md) wurde nicht gefunden."
