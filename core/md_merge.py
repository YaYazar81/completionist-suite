"""Mehrere Markdown-Dateien zu einer zusammenfuehren.

Zwischen je zwei Dateien steht eine harte Trennlinie ``***`` -- CompletionistPDF
macht daraus einen Seitenumbruch. Relative Bild- und Linkpfade werden auf den
Ordner der Zieldatei umgerechnet, damit Bilder aus anderen Ordnern weiter
gefunden werden. YAML-Frontmatter bleibt nur von der ersten Datei erhalten.

Wird von CompletionistMD (Vault-Explorer, Datei-Menue) und CompletionistPDF
(Datei-Menue) benutzt, deshalb ohne Qt.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote

SEPARATOR = "***"

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)
# ![alt](pfad "titel") und [text](pfad) -- Pfad ohne Leerzeichen oder in <...>
_MD_LINK_RE = re.compile(r"(!?\[(?:[^\]\\]|\\.)*\]\()(<[^>]*>|[^)\s]+)((?:\s+\"[^\"]*\")?\))")
_HTML_SRC_RE = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")


def merge_files(files: list[Path], target: Path, separator: str = SEPARATOR) -> str:
    """Liefert den zusammengefuehrten Text (schreibt nichts)."""
    target_dir = Path(target).resolve().parent
    parts: list[str] = []
    for i, f in enumerate(files):
        f = Path(f)
        text = f.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
        front = ""
        m = _FRONTMATTER_RE.match(text)
        if m:
            front, text = m.group(0), text[m.end():]
        text = rebase_paths(text, f.resolve().parent, target_dir).strip("\n")
        if i == 0 and front:
            text = front.rstrip("\n") + "\n\n" + text
        if text.strip():
            parts.append(text)
    return (f"\n\n{separator}\n\n".join(parts) + "\n") if parts else ""


def rebase_paths(text: str, source_dir: Path, target_dir: Path) -> str:
    """Relative Pfade in Bildern/Links von ``source_dir`` auf ``target_dir`` umrechnen.

    Codebloecke bleiben unangetastet.
    """
    if Path(source_dir) == Path(target_dir):
        return text
    out, fence = [], None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(2)[0]
        elif fence is not None and m and m.group(2)[0] == fence:
            fence = None
        elif fence is None:
            line = _MD_LINK_RE.sub(lambda mm: mm.group(1) + _rebase(mm.group(2), source_dir, target_dir)
                                   + mm.group(3), line)
            line = _HTML_SRC_RE.sub(lambda mm: mm.group(1) + mm.group(2)
                                    + _rebase(mm.group(3), source_dir, target_dir) + mm.group(2), line)
        out.append(line)
    return "\n".join(out)


def _rebase(src: str, source_dir: Path, target_dir: Path) -> str:
    bracketed = src.startswith("<") and src.endswith(">")
    raw = src[1:-1] if bracketed else src
    if not raw or raw.startswith(("#", "/", "\\")) or re.match(r"^[a-z][a-z0-9+.-]*:", raw, re.I):
        return src  # Anker, absolut, URL, data:, C:\...
    path_part, sep, anchor = raw.partition("#")
    absolute = (Path(source_dir) / unquote(path_part)).resolve()
    try:
        rel = os.path.relpath(absolute, Path(target_dir).resolve())
    except ValueError:  # anderes Laufwerk
        rel = str(absolute)
    rel = rel.replace(os.sep, "/")
    if " " in rel and not bracketed:
        rel = rel.replace(" ", "%20")
    new = posixpath.normpath(rel) + (sep + anchor if sep else "")
    return f"<{new}>" if bracketed else new


def default_name(files: list[Path]) -> str:
    """Vorschlag fuer den Dateinamen: gemeinsamer Anfang der Namen oder "Zusammengefuehrt"."""
    stems = [Path(f).stem for f in files]
    prefix = os.path.commonprefix(stems).strip(" -_.0123456789")
    return (prefix or "Zusammengeführt") + ".md"
