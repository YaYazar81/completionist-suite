"""Ablage fuer Einstellungen und eigene Vorlagen unter %APPDATA%\\CompletionistQR.

Die App hiess frueher QR Studio. Ist nur der alte Ordner vorhanden, wird er
beim ersten Zugriff einmalig uebernommen, damit eigene Vorlagen erhalten
bleiben.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

LEGACY_NAME = "QRStudio"


def user_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home()))
    path = base / "CompletionistQR"
    if not path.exists():
        legacy = base / LEGACY_NAME
        if legacy.is_dir():
            try:
                shutil.copytree(legacy, path)
            except OSError:
                pass
    return path
