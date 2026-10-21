"""Vorlagen-Presets als JSON.

Mitgelieferte Presets liegen in ``<app>/presets`` (im PyInstaller-Bundle
schreibgeschuetzt). Eigene Presets speichert die App unter
``%APPDATA%/CompletionistPDF/presets``; gleichnamige eigene Presets
ueberdecken die mitgelieferten.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import DocumentConfig

# Diese Felder gehoeren zum einzelnen Dokument, nicht zur Vorlage.
_DOCUMENT_FIELDS = ("markdown_path", "output_path")


def user_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "CompletionistPDF"
    path.mkdir(parents=True, exist_ok=True)
    return path


class PresetStore:
    def __init__(self, bundled_dir: Path) -> None:
        self.bundled_dir = Path(bundled_dir)
        self.user_dir = user_data_dir() / "presets"
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def names(self) -> list[str]:
        names: set[str] = set()
        for d in (self.bundled_dir, self.user_dir):
            if d.is_dir():
                names.update(p.stem for p in d.glob("*.json"))
        return sorted(names, key=str.lower)

    def is_user_preset(self, name: str) -> bool:
        return (self.user_dir / f"{_slug(name)}.json").is_file()

    def load(self, name: str, base: DocumentConfig | None = None) -> DocumentConfig:
        """Laedt ein Preset; Dokumentfelder werden aus ``base`` uebernommen."""
        path = self._path(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _DOCUMENT_FIELDS:
            data.pop(key, None)
        cfg = DocumentConfig.from_dict(data)
        if base is not None:
            cfg.markdown_path = base.markdown_path
            cfg.output_path = base.output_path
        return cfg

    def save(self, name: str, config: DocumentConfig) -> Path:
        data = config.to_dict()
        for key in _DOCUMENT_FIELDS:
            data.pop(key, None)
        path = self.user_dir / f"{_slug(name)}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        path = self.user_dir / f"{_slug(name)}.json"
        if path.is_file():
            path.unlink()
            return True
        return False

    def _path(self, name: str) -> Path:
        user = self.user_dir / f"{_slug(name)}.json"
        if user.is_file():
            return user
        return self.bundled_dir / f"{name}.json"


def _slug(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "preset"
