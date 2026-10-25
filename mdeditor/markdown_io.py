"""Lesen und Schreiben der .md-Datei.

Der Editor speichert aggressiv (~300 ms nach der letzten Taste, aber nur, wenn
sich das Markdown wirklich geaendert hat). Dabei gilt:

* Geschrieben wird ausfallsicher: erst in eine versteckte Zwischendatei
  daneben, dann ersetzt sie die Datei in einem Schritt. Ein Absturz mitten im
  Schreiben hinterlaesst so nie eine leere oder halbe Notiz.
* Aeltere Fassungen landen im versteckten Ordner ``.completionistmd/verlauf/``
  neben der Datei (hoechstens alle ``SNAPSHOT_INTERVAL`` Sekunden eine, die
  letzten ``SNAPSHOT_KEEP`` bleiben). Ordner mit Punkt zeigt der
  Vault-Explorer nicht an, und der Drive-Sync laesst sie aus.
* YAML-Frontmatter wird nie durch den Editor geschleift, sondern unveraendert
  wieder vorangestellt.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

HIDDEN_DIR = ".completionistmd"
SNAPSHOT_INTERVAL = 10 * 60
SNAPSHOT_KEEP = 30

# "---\n ... \n---\n" bzw. "...\n" als Abschluss, nur direkt am Dateianfang.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)


@dataclass
class MarkdownFile:
    """Eine geoeffnete Markdown-Datei."""

    path: Path
    frontmatter: str = ""  # inkl. abschliessendem Zeilenumbruch, oder ""
    body: str = ""

    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: str | Path) -> "MarkdownFile":
        path = Path(path)
        # utf-8-sig entfernt ein BOM; sonst stuende es vor der ersten "#"-Zeile.
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        front, body = split_frontmatter(text)
        return cls(path=path, frontmatter=front, body=body)

    @classmethod
    def blank(cls, path: str | Path | None = None) -> "MarkdownFile":
        return cls(path=Path(path) if path else None, body="")  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #

    def compose(self, body: str) -> str:
        """Frontmatter + Rumpf, mit genau einem Zeilenumbruch am Ende."""
        body = body.replace("\r\n", "\n").rstrip("\n")
        front = self.frontmatter
        if front and not front.endswith("\n"):
            front += "\n"
        if front and body:
            front += "\n"
        return (front + body + "\n") if (front or body) else ""

    def save(self, body: str) -> Path:
        """Schreibt den Rumpf in die Datei und gibt deren Pfad zurueck."""
        if self.path is None:
            raise ValueError("Datei hat noch keinen Pfad")
        snapshot(self.path)
        write_safely(self.path, self.compose(body))
        self.body = body
        return self.path


# ---------------------------------------------------------------------- #


def split_frontmatter(text: str) -> tuple[str, str]:
    """Trennt YAML-Frontmatter vom Rest."""
    text = text.replace("\r\n", "\n")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return m.group(0), text[m.end():]


def write_safely(path: Path, data: str | bytes) -> None:
    """Schreibt ``data`` nach ``path``, ohne dass je eine halbe Datei entsteht.

    Erst in ``.<name>.tmp`` daneben, dann ``os.replace``. Haelt ein anderes
    Programm die Datei so offen, dass sie sich nicht ersetzen laesst, wird
    direkt hineingeschrieben (wie frueher).
    """
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        _write(tmp, raw)
        os.replace(tmp, path)
    except PermissionError:
        try:
            tmp.unlink()
        except OSError:
            pass
        _write(path, raw)


def _write(path: Path, raw: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------------- #
# Aeltere Fassungen
# ---------------------------------------------------------------------- #


def history_dir(path: Path) -> Path:
    path = Path(path)
    return path.parent / HIDDEN_DIR / "verlauf" / path.name


def snapshots(path: Path) -> list[Path]:
    """Gesicherte Fassungen von ``path``, neueste zuerst."""
    d = history_dir(path)
    if not d.is_dir():
        return []
    return sorted(d.glob("*" + Path(path).suffix), reverse=True)


def snapshot(path: Path, *, force: bool = False, data: bytes | None = None) -> Path | None:
    """Sichert den aktuellen Stand von ``path`` auf der Platte, bevor er
    ueberschrieben wird -- hoechstens alle ``SNAPSHOT_INTERVAL`` Sekunden.

    ``data`` sichert statt des Platteninhalts diesen Stand (z. B. den
    Editorinhalt, der gleich verworfen wird)."""
    path = Path(path)
    try:
        current = data if data is not None else path.read_bytes()
    except OSError:
        return None
    existing = snapshots(path)
    if existing and not force:
        try:
            if time.time() - existing[0].stat().st_mtime < SNAPSHOT_INTERVAL:
                return None
            if existing[0].read_bytes() == current:
                return None
        except OSError:
            pass
    target = history_dir(path) / (time.strftime("%Y-%m-%d_%H-%M-%S") + path.suffix)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _hide(path.parent / HIDDEN_DIR)
        _write(target, current)
    except OSError:
        return None
    for old in snapshots(path)[SNAPSHOT_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


def _hide(folder: Path) -> None:
    """Setzt unter Windows zusaetzlich das Versteckt-Attribut."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(folder), 0x02)
    except Exception:
        pass
