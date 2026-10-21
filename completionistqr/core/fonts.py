"""Registry der mitgelieferten Schriftarten (siehe tools/fetch_fonts.py)."""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


def assets_dir() -> Path:
    # In der PyInstaller-Exe liegen die Assets unter sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "completionistqr" / "assets"


FONT_DIR = assets_dir() / "fonts"
_WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_FALLBACKS = {False: ["segoeui.ttf", "arial.ttf"], True: ["segoeuib.ttf", "arialbd.ttf"]}


@lru_cache(maxsize=1)
def _manifest() -> dict:
    try:
        return json.loads((FONT_DIR / "fonts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def families() -> list[str]:
    names = [n for n, e in _manifest().items() if (FONT_DIR / e["dir"] / e["regular"]).exists()]
    return names or ["Segoe UI"]


def font_file(family: str, bold: bool = False) -> tuple[Path, bool]:
    """Liefert (Pfad, ist_variable_font). Fällt still auf Systemschriften zurück."""
    entry = _manifest().get(family)
    if entry:
        folder = FONT_DIR / entry["dir"]
        if bold and entry.get("bold") and (folder / entry["bold"]).exists():
            return folder / entry["bold"], False
        if (folder / entry["regular"]).exists():
            return folder / entry["regular"], bool(entry.get("variable"))
    for name in _FALLBACKS[bold]:
        p = _WINDOWS_FONTS / name
        if p.exists():
            return p, False
    return Path(""), False


def load(family: str, bold: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path, variable = font_file(family, bold)
    try:
        font = ImageFont.truetype(str(path), max(1, int(size)))
    except OSError:
        return ImageFont.load_default(size=max(1, int(size)))
    if variable:
        # Die Standardinstanz mancher Variable Fonts ist "Thin" – Gewicht daher immer setzen.
        weight = 700 if bold else 400
        try:
            axes = font.get_variation_axes()
            names = [bytes(a.get("name", b"")).lower() for a in axes]
            # wght ist bei Google Fonts die letzte Achse, falls kein lesbarer Name vorliegt
            idx = next((i for i, n in enumerate(names) if n.startswith(b"weight")), len(axes) - 1)
            values = [a.get("default", a["minimum"]) for a in axes]
            values[idx] = max(axes[idx]["minimum"], min(weight, axes[idx]["maximum"]))
            font.set_variation_by_axes(values)
        except (OSError, KeyError, AttributeError):
            pass
    return font
