"""Stapel-Export: viele QR-Codes im aktuellen Design aus einer CSV-Liste.

Die CSV braucht nur eine Spalte mit dem Inhalt (Link, Text ...). Optional
eine zweite Spalte mit dem Dateinamen. Eine Kopfzeile wird erkannt, wenn
sie "inhalt"/"url"/"link"/"text" bzw. "name"/"dateiname" enthaelt.
Trennzeichen ; , oder Tab werden erkannt (Excel speichert in Deutschland mit ;).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

from . import export
from .config import QRDesign

CONTENT_HEADERS = {"inhalt", "url", "link", "text", "payload", "daten"}
NAME_HEADERS = {"name", "dateiname", "datei", "filename", "titel", "beschriftung"}


def read_rows(path: str | Path) -> list[tuple[str, str]]:
    """[(Inhalt, Dateiname oder "")] aus einer CSV-Datei."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        class dialect(csv.excel):  # noqa: N801 -- csv.excel selbst nicht veraendern
            delimiter = ";" if text.count(";") > text.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        return []
    content_col, name_col = 0, 1
    head = [c.strip().lower() for c in rows[0]]
    if any(h in CONTENT_HEADERS | NAME_HEADERS for h in head):
        content_col = next((i for i, h in enumerate(head) if h in CONTENT_HEADERS), 0)
        name_col = next((i for i, h in enumerate(head) if h in NAME_HEADERS), -1)
        rows = rows[1:]
    out = []
    for r in rows:
        content = r[content_col].strip() if content_col < len(r) else ""
        name = r[name_col].strip() if 0 <= name_col < len(r) and name_col != content_col else ""
        if content:
            out.append((content, name))
    return out


def safe_name(text: str, fallback: str) -> str:
    name = re.sub(r"^[a-z]+://", "", text.strip(), flags=re.I)
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("._")[:60]
    return name or fallback


def export_all(design: QRDesign, rows: list[tuple[str, str]], folder: str | Path, ext: str,
               width_px: int, dpi: int, check: bool = True,
               progress: Callable[[int, int], None] = lambda done, total: None,
               cancelled: Callable[[], bool] = lambda: False) -> tuple[list[Path], list[str]]:
    """Schreibt alle Codes. Liefert (Dateien, Namen der nicht lesbaren Codes)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    unreadable: list[str] = []
    used: set[str] = set()
    for i, (content, name) in enumerate(rows, 1):
        if cancelled():
            break
        base = safe_name(name or content, f"qr-{i:03d}")
        stem, n = base, 2
        while stem.lower() in used or (folder / (stem + ext)).exists():
            stem, n = f"{base}-{n}", n + 1
        used.add(stem.lower())
        d = replace(design, payload=content)
        written.append(export.save(d, folder / (stem + ext), width_px=width_px, dpi=dpi))
        if check and not export.scan_check(d):
            unreadable.append(stem + ext)
        progress(i, len(rows))
    return written, unreadable
