"""Startet CompletionistQR als eigenes Programm.

CompletionistQR baut auf CustomTkinter auf, CompletionistPDF und CompletionistMD
auf Qt. Zwei Oberflaechen-Bibliotheken vertragen sich nicht in einem Prozess,
deshalb wird die App als eigener Prozess gestartet -- genauso, wie der Editor
CompletionistPDF startet.

Dieses Modul importiert absichtlich nichts aus ``completionistqr``: die beiden
Qt-Programme sollen weiterhin ohne CustomTkinter auskommen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXE_NAME = "CompletionistQR.exe"
SCRIPT_NAME = "run_completionistqr.py"
APP_DIR_NAME = "CompletionistQR"

# AppIds der Setups (installer/*.iss) -- unter dieser Kennung steht die App in
# der Uninstall-Liste. Muessen mit den .iss-Dateien uebereinstimmen.
APP_IDS = {
    "CompletionistQR": "{D1F91E29-E069-4F0E-927C-98957984379B}",
    "CompletionistPDF": "{D58A3655-430B-431B-81B2-5860BAE5E9C1}",
    "CompletionistMD": "{BBD71472-CB23-4208-A011-F09A4C2CE450}",
    # eigenes Projekt (G:\Claude Code\CompletionistIMG), installer/CompletionistIMG.iss
    "CompletionistIMG": "{6E1C4C1B-3F0E-4E6B-9B7A-2C8F3A1D5E42}",
}


# Gemeinsamer Suite-Schluessel: jedes Setup traegt dort seinen Programmordner
# ein (installer/*.iss, Abschnitt [Registry]), z. B.
# HKCU\Software\CompletionistLibrary\CompletionistPDF -> InstallPath.
SUITE_KEY = r"Software\CompletionistLibrary"


def registry_exe(app: str) -> Path | None:
    """Pfad der .exe laut Suite-Schluessel. ``InstallPath`` (oder der
    Standardwert) darf auf den Programmordner oder direkt auf die .exe zeigen."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"{SUITE_KEY}\{app}") as key:
                for name in ("InstallPath", ""):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except OSError:
                        continue
                    path = Path(os.path.expandvars(str(value)).strip('"'))
                    exe = path if path.suffix.lower() == ".exe" else path / f"{app}.exe"
                    if exe.is_file():
                        return exe
        except OSError:
            continue
    return None


def _installed_exe(app: str = APP_DIR_NAME) -> Path | None:
    """Pfad aus der Windows-Programmliste, falls ``app`` per Setup installiert ist."""
    if sys.platform != "win32" or app not in APP_IDS:
        return None
    try:
        import winreg
    except ImportError:
        return None
    key_path = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                rf"\{APP_IDS[app]}_is1")
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                path, _ = winreg.QueryValueEx(key, "Inno Setup: App Path")
        except OSError:
            continue
        exe = Path(path) / f"{app}.exe"
        if exe.is_file():
            return exe
    return None


def _candidates(home: Path, app: str = APP_DIR_NAME) -> list[Path]:
    """Orte, an denen die .exe liegen kann -- in der Reihenfolge der Suche."""
    exe_name = f"{app}.exe"
    found = []
    for base in (home, home / "dist"):
        # Einzeldatei neben dem Programm bzw. in dist/, dann der Programmordner
        # aus dem Ordner-Build (PyInstaller --onedir).
        found += [base / exe_name, base / app / exe_name]
    for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env)
        if root:
            found.append(Path(root) / "Programs" / app / exe_name
                         if env == "LOCALAPPDATA" else
                         Path(root) / app / exe_name)
    return found


def find_app_exe(home: Path, app: str) -> Path | None:
    """Sucht die .exe einer Suite-App (``"CompletionistPDF"`` usw.): erst ueber
    den Suite-Schluessel in der Registry, dann neben ``home``, im
    Standard-Installationsordner und zuletzt ueber die Uninstall-Liste."""
    exe = registry_exe(app)
    if exe is not None:
        return exe
    for exe in _candidates(home, app):
        if exe.is_file():
            return exe
    return _installed_exe(app)


def qr_command(app_dir: Path) -> tuple[list[str], Path] | None:
    """Befehl und Arbeitsordner zum Starten von CompletionistQR.

    ``None``, wenn weder die .exe noch das Startskript gefunden wird.
    """
    frozen = getattr(sys, "frozen", False)
    # Als .exe zeigt app_dir auf den temporaeren Entpackordner -- gesucht wird
    # dann neben der eigenen .exe.
    home = Path(sys.executable).resolve().parent if frozen else Path(app_dir)
    exe = find_app_exe(home, APP_DIR_NAME)
    if exe is not None:
        return [str(exe)], exe.parent

    script = Path(app_dir) / SCRIPT_NAME
    if not frozen and script.is_file():
        python = Path(sys.executable)
        # pythonw.exe: kein Konsolenfenster hinter der GUI
        windowed = python.with_name("pythonw.exe")
        if windowed.is_file():
            python = windowed
        return [str(python), str(script)], script.parent
    return None


def not_found_message(app_dir: Path) -> str:
    extra = "" if getattr(sys, "frozen", False) else f"\n– {SCRIPT_NAME} in {app_dir}"
    return (f"CompletionistQR wurde nicht gefunden. Gesucht wurde nach:\n"
            f"– {EXE_NAME} im selben Ordner wie dieses Programm\n"
            f"– einem Ordner {APP_DIR_NAME} daneben\n"
            f"– einer Installation (Setup){extra}")


def launch(app_dir: Path) -> str | None:
    """Startet CompletionistQR. Gibt ``None`` zurueck oder eine Fehlermeldung."""
    found = qr_command(app_dir)
    if found is None:
        return not_found_message(app_dir)
    command, cwd = found
    try:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) if sys.platform == "win32" else 0
        # cwd niemals im Entpackordner der eigenen .exe: der verschwindet,
        # sobald das startende Programm beendet wird.
        subprocess.Popen(command, cwd=str(cwd), creationflags=flags, close_fds=True)
    except OSError as exc:
        return f"Start fehlgeschlagen:\n{exc}"
    return None
