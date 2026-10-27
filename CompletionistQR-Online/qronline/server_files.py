"""Server-Dateien fuer den eigenen Webspace vorbereiten (ohne Oberflaeche, siehe server_setup.py).

Zufaelliger API-Schluessel, config.php aus der Vorlage, Kopie von index.php & Co. in einen
Ordner zum Hochladen und der Verbindungstest.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from .client import Client, ServerError

# Was auf den Webspace gehoert (config.sample.php nicht: config.php wird erzeugt)
SERVER_FILES = ("index.php", ".htaccess", "data/.htaccess")
KEY_LINE = re.compile(r"('api_key'\s*=>\s*)'[^']*'")
SHORT_LINE = re.compile(r"('short_url'\s*=>\s*)'[^']*'")

UPLOAD_HELP = (
    "Lade den Inhalt dieses Ordners per FTP auf deinen Webspace – in das Verzeichnis, auf das "
    "die Server-Adresse zeigt (z. B. FileZilla oder der Dateimanager deines Hosters). "
    "Wichtig: auch die Dateien .htaccess und data/.htaccess; manche FTP-Programme blenden "
    "Dateien mit Punkt am Anfang aus. Für die Adresse sollte SSL (https) eingeschaltet sein. "
    "Voraussetzung: PHP 8 mit SQLite, das haben fast alle Hoster.")


def generate_key() -> str:
    """Zufaelliger API-Schluessel (48 Hex-Zeichen, wie bin2hex(random_bytes(24)))."""
    return secrets.token_hex(24)


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return url


def server_source() -> Path:
    """Ordner mit index.php & Co.: im Programm (PyInstaller), neben der .exe (Setup) oder
    im Quellcode."""
    here = Path(__file__).resolve().parents[1]
    candidates = [Path(getattr(sys, "_MEIPASS", here)) / "server",
                  Path(sys.executable).resolve().parent / "server", here / "server"]
    for c in candidates:
        if (c / "index.php").is_file() and (c / "config.sample.php").is_file():
            return c
    raise FileNotFoundError("Die Server-Dateien (index.php) wurden nicht gefunden.")


def config_php(key: str, short_url: str = "", source: Path | None = None) -> str:
    """config.php aus der Vorlage, mit eingetragenem Schluessel."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16,200}", key):
        raise ValueError("Der API-Schlüssel braucht mindestens 16 Zeichen (Buchstaben, Ziffern, - oder _).")
    text = ((source or server_source()) / "config.sample.php").read_text(encoding="utf-8")
    text = KEY_LINE.sub(lambda m: f"{m.group(1)}'{key}'", text, count=1)
    if short_url:
        text = SHORT_LINE.sub(lambda m: f"{m.group(1)}'{normalize_url(short_url)}'", text, count=1)
    header = ("// Erzeugt von CompletionistQR Online. Der Schluessel steht so auch in der App\n"
              "// (Server …) -- wer ihn kennt, kann die Links aendern: nicht weitergeben.\n")
    return text.replace("<?php\n", "<?php\n" + header, 1)


def write_server_files(dest: Path, key: str, short_url: str = "") -> Path:
    """Legt in ``dest`` alles an, was auf den Webspace gehoert, und gibt den Ordner zurueck."""
    src = server_source()
    dest = Path(dest)
    (dest / "data").mkdir(parents=True, exist_ok=True)
    for name in SERVER_FILES:
        shutil.copyfile(src / name, dest / name)
    (dest / "config.php").write_text(config_php(key, short_url, src), encoding="utf-8")
    return dest


def default_folder() -> Path:
    docs = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "CompletionistQR Online - Server"


def open_folder(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 -- Explorer mit dem Ordner
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def check_connection(url: str, key: str) -> str:
    """Leerer Text = Server antwortet und der Schluessel passt; sonst die Fehlermeldung."""
    try:
        Client(url, key, timeout=10).ping()
    except ServerError as exc:
        return str(exc)
    return ""
