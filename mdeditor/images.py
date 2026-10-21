"""Bilder in den Ordner ``images/`` neben der .md-Datei legen.

Alles, was per Zwischenablage oder Drag & Drop in den Editor kommt, landet als
Datei neben dem Dokument -- nie als data-URI im Markdown. Der Editor verweist
anschliessend mit einem relativen Pfad (``images/bild-003.png``) darauf, damit
CompletionistPDF das Bild unter der Typst-Wurzel findet.
"""

from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QUrl
from PyQt6.QtGui import QImage

IMAGE_DIR = "images"
DEFAULT_STEM = "bild"

# Was wir aus Dateien uebernehmen (Rest wandert ungewandelt mit).
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
VECTOR_SUFFIXES = {".svg"}
IMAGE_SUFFIXES = RASTER_SUFFIXES | VECTOR_SUFFIXES

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def image_dir(md_path: Path) -> Path:
    return Path(md_path).resolve().parent / IMAGE_DIR


def ensure_image_dir(md_path: Path) -> Path:
    folder = image_dir(md_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """``bild.png`` -> erster freier Name ``bild-001.png``, ``bild-002.png`` ..."""
    stem = _SAFE_RE.sub("-", stem).strip("-") or DEFAULT_STEM
    n = 1
    while True:
        candidate = folder / f"{stem}-{n:03d}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def rel_src(md_path: Path, image_path: Path) -> str:
    """Pfad fuer das Markdown: relativ zur .md, mit Vorwaertsschraegstrichen."""
    md_dir = Path(md_path).resolve().parent
    try:
        rel = Path(image_path).resolve().relative_to(md_dir)
        return posixpath.join(*rel.parts)
    except ValueError:
        # Bild liegt ausserhalb -- dann hilft nur der absolute Pfad.
        return Path(image_path).resolve().as_posix()


# ---------------------------------------------------------------------- #
# Quellen
# ---------------------------------------------------------------------- #


def save_bytes(md_path: Path, data: bytes, suffix: str, stem: str = DEFAULT_STEM) -> Path:
    folder = ensure_image_dir(md_path)
    target = unique_path(folder, stem, suffix)
    target.write_bytes(data)
    return target


def save_image(md_path: Path, image: QImage, stem: str = DEFAULT_STEM) -> Path | None:
    """Ein QImage (z. B. aus der Zwischenablage) als PNG ablegen."""
    if image.isNull():
        return None
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buf, "PNG"):
        return None
    return save_bytes(md_path, bytes(buf.data()), ".png", stem)


def copy_file(md_path: Path, source: Path, stem: str | None = None) -> Path | None:
    """Eine vorhandene Bilddatei nach ``images/`` kopieren."""
    source = Path(source)
    if not source.is_file():
        return None
    suffix = source.suffix.lower() or ".png"
    folder = ensure_image_dir(md_path)
    # Schon im richtigen Ordner? Dann unveraendert verwenden.
    try:
        if source.resolve().parent == folder.resolve():
            return source.resolve()
    except OSError:
        pass
    target = unique_path(folder, stem or source.stem, suffix)
    shutil.copyfile(source, target)
    return target


def from_mime(md_path: Path, mime: QMimeData, stem: str = DEFAULT_STEM) -> list[Path]:
    """Bilder aus Zwischenablage/Drop-Daten ablegen. Reihenfolge = Fundreihenfolge."""
    saved: list[Path] = []

    # 1. Echte Dateien (Explorer, andere Programme)
    if mime.hasUrls():
        for url in mime.urls():
            path = _local_path(url)
            if path and path.suffix.lower() in IMAGE_SUFFIXES:
                target = copy_file(md_path, path)
                if target:
                    saved.append(target)
    if saved:
        return saved

    # 2. SVG als Markup -- verlustfrei uebernehmen statt zu rastern
    for fmt in ("image/svg+xml", "image/svg"):
        if mime.hasFormat(fmt):
            data = bytes(mime.data(fmt))
            if data.strip():
                saved.append(save_bytes(md_path, data, ".svg", stem))
                return saved

    # 3. PNG-Rohdaten (behaelt Transparenz sicher)
    if mime.hasFormat("image/png"):
        data = bytes(mime.data("image/png"))
        if data.strip():
            saved.append(save_bytes(md_path, data, ".png", stem))
            return saved

    # 4. Bitmap aus der Zwischenablage (Screenshots, Grafikprogramme)
    if mime.hasImage():
        image = QImage(mime.imageData())
        target = save_image(md_path, image, stem)
        if target:
            saved.append(target)

    return saved


def mime_has_image(mime: QMimeData) -> bool:
    """Ob ``from_mime`` etwas zu holen haette (fuer Drag-Over-Anzeige)."""
    if mime.hasImage() or mime.hasFormat("image/svg+xml") or mime.hasFormat("image/png"):
        return True
    if mime.hasUrls():
        return any(
            (p := _local_path(u)) is not None and p.suffix.lower() in IMAGE_SUFFIXES
            for u in mime.urls()
        )
    return False


def markdown_urls(mime: QMimeData) -> list[Path]:
    """.md-Dateien aus Drop-Daten (zum Oeffnen)."""
    out: list[Path] = []
    for url in mime.urls() if mime.hasUrls() else []:
        path = _local_path(url)
        if path and path.suffix.lower() in (".md", ".markdown", ".mdown", ".txt"):
            out.append(path)
    return out


def _local_path(url: QUrl) -> Path | None:
    if not url.isLocalFile():
        return None
    name = url.toLocalFile()
    return Path(name) if name else None


def data_uri_to_bytes(uri: str) -> tuple[bytes, str] | None:
    """``data:image/png;base64,...`` -> (Rohdaten, Endung)."""
    m = re.match(r"data:(image/[\w.+-]+);base64,(.*)$", uri.strip(), re.S)
    if not m:
        return None
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }.get(m.group(1).lower())
    if suffix is None:
        return None
    raw = QByteArray.fromBase64(m.group(2).encode("ascii"))
    return bytes(raw), suffix
