"""Eingebaute Design-Presets und eigene Presets unter %APPDATA%\\CompletionistQR\\presets."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import QRDesign
from .fonts import assets_dir
from .userdir import user_dir


def _user_dir() -> Path:
    return user_dir() / "presets"


def builtin() -> dict[str, dict]:
    try:
        return json.loads((assets_dir() / "presets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"Classic": {}}


def user() -> dict[str, dict]:
    out = {}
    d = _user_dir()
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return out


def all_presets() -> dict[str, dict]:
    return {**builtin(), **user()}


def save_user(name: str, design: QRDesign) -> Path:
    d = _user_dir()
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "Preset"
    path = d / f"{safe}.json"
    path.write_text(json.dumps(design.style_dict(), indent=2), encoding="utf-8")
    return path


def delete_user(name: str) -> None:
    (_user_dir() / f"{name}.json").unlink(missing_ok=True)
