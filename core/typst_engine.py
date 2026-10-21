"""Kompilierung: Markdown -> Typst -> PDF.

Die Typst-Wurzel (``root``) ist immer der Ordner der Markdown-Datei. Damit
funktionieren Bildpfade aus der .md unveraendert. Die generierten Dateien
liegen in einem Unterordner ``.completionistpdf``; Cover- und Wasserzeichen-
Bilder von ausserhalb werden dorthin kopiert, weil Typst nur auf Dateien
unterhalb der Wurzel zugreifen darf.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import typst

from .config import DocumentConfig
from .md_converter import MarkdownToTypst

WORK_DIR_NAME = ".completionistpdf"

# "error: unexpected ... " / "  ┌─ C:\...\content.typ:12:4"
_LOCATION_RE = re.compile(
    r"(?P<file>[^\s:][^\n:]*\.typ):(?P<line>\d+):(?P<col>\d+)"
)
_SEVERITY_RE = re.compile(r"^\s*(error|warning)\s*:\s*(?P<msg>.*)$", re.I)


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning" | "info"
    message: str
    md_line: int | None = None
    typ_line: int | None = None
    source: str = ""

    def format(self) -> str:
        if self.md_line:
            return f"Zeile {self.md_line}: {self.message}"
        return self.message


@dataclass
class CompileResult:
    ok: bool
    pdf_path: Path | None = None
    # Ohne Ausgabepfad: PDF als bytes bzw. PNG als Liste (eine pro Seite)
    data: bytes | list[bytes] | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    duration: float = 0.0
    typst_source: str = ""

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]


class TypstEngine:
    """Kapselt den Typst-Compiler samt Font-Cache."""

    def __init__(self, app_dir: Path | None = None) -> None:
        self.app_dir = Path(app_dir) if app_dir else _app_dir()
        self.template_path = self.app_dir / "templates" / "template.typ"
        self.font_dirs: list[Path] = []
        bundled = self.app_dir / "assets" / "fonts"
        if bundled.is_dir():
            self.font_dirs.append(bundled)

        self._compiler: typst.Compiler | None = None
        self._compiler_key: tuple | None = None

    # ------------------------------------------------------------------ #

    def available_fonts(self) -> list[str]:
        """Schriftfamilien, die Typst tatsaechlich nutzen kann."""
        try:
            fonts = typst.Fonts(
                font_paths=[str(p) for p in self.font_dirs],
                include_system_fonts=True,
            )
            return sorted({f for f in fonts.families()})
        except Exception:
            return []

    # ------------------------------------------------------------------ #

    def compile(
        self,
        config: DocumentConfig,
        *,
        output: Path | None = None,
        fmt: str = "pdf",
        ppi: float | None = None,
    ) -> CompileResult:
        started = time.perf_counter()
        md_path = Path(config.markdown_path)
        if not md_path.is_file():
            return CompileResult(
                ok=False,
                diagnostics=[
                    Diagnostic("error", f"Markdown-Datei nicht gefunden: {md_path}")
                ],
            )

        root = md_path.parent
        work = root / WORK_DIR_NAME
        try:
            work.mkdir(exist_ok=True)
            (work / ".probe").write_bytes(b"")
        except OSError as exc:
            # Typischer Fall unter Windows: der Ordner wurde geloescht, waehrend
            # ein anderes Programm ihn noch offen hatte ("Loeschen ausstehend").
            return CompileResult(
                ok=False,
                diagnostics=[
                    Diagnostic(
                        "error",
                        f"Arbeitsordner {work} ist nicht beschreibbar ({exc.strerror or exc}). "
                        "Meist hält ein anderes Programm (Explorer-Fenster, Virenscanner) "
                        "den Ordner noch fest; er gibt sich von selbst frei, spätestens "
                        "nach einem Neustart.",
                    )
                ],
                duration=time.perf_counter() - started,
            )
        _hide(work)

        diagnostics: list[Diagnostic] = []

        # 1. Markdown uebersetzen
        converter = MarkdownToTypst(
            heading_offset=config.content.heading_offset,
            hr_as_pagebreak=config.content.hr_as_pagebreak,
            image_width=config.content.image_width,
            figure_captions=config.content.figure_captions,
            root_dir=root,
            external_dir=WORK_DIR_NAME,
            soft_breaks_as_linebreaks=config.content.soft_breaks_as_linebreaks,
        )
        # utf-8-sig: entfernt ein BOM am Dateianfang (schreibt z. B. MarkText).
        # Sonst stuende es vor dem ersten "#", und die Ueberschrift fiele aus.
        text = md_path.read_text(encoding="utf-8-sig", errors="replace")
        result = converter.convert(text, root)
        for miss in result.missing_images:
            diagnostics.append(
                Diagnostic("warning", f"Bild nicht gefunden: {miss}")
            )
        for name, source in result.external_images.items():
            try:
                _place_external(work / name, source)
            except OSError as exc:
                diagnostics.append(
                    Diagnostic("warning", f"Bild konnte nicht übernommen werden: {source} ({exc})")
                )

        (work / "content.typ").write_text(result.typst, encoding="utf-8")

        # 2. Konfiguration schreiben, externe Bilder einsammeln
        data = config.to_template_dict()
        data["cover"]["image"] = self._localize(config.cover.image, work, root)
        data["watermark"]["image"] = self._localize(
            config.watermark.image, work, root
        )
        _write_json(work / "config.json", data)

        shutil.copyfile(self.template_path, work / "main.typ")
        shutil.copyfile(self.template_path.with_name("helpers.typ"), work / "helpers.typ")

        # 3. Kompilieren -- ohne Ausgabepfad direkt in den Speicher, damit
        # der Viewer keine Datei sperrt, die der naechste Lauf ueberschreibt.
        out_path = Path(output) if output else None
        compiler = self._get_compiler(root)
        try:
            data, warnings = compiler.compile_with_warnings(
                input=str(work / "main.typ"),
                output=str(out_path) if out_path else None,
                format=fmt,
                ppi=ppi,
            )
            diagnostics.extend(
                self._parse(_warning_text(warnings), "warning", result.line_map)
            )
        except typst.TypstError as exc:
            # `diagnostic` traegt die volle Meldung inkl. Datei:Zeile:Spalte,
            # str(exc) nur die Kurzfassung.
            text = getattr(exc, "diagnostic", None) or str(exc)
            diagnostics.extend(self._parse(text, "error", result.line_map))
            return CompileResult(
                ok=False,
                diagnostics=diagnostics,
                duration=time.perf_counter() - started,
                typst_source=result.typst,
            )
        except Exception as exc:  # pragma: no cover - unerwartete Fehler
            diagnostics.append(Diagnostic("error", f"{type(exc).__name__}: {exc}"))
            return CompileResult(
                ok=False,
                diagnostics=diagnostics,
                duration=time.perf_counter() - started,
                typst_source=result.typst,
            )

        return CompileResult(
            ok=True,
            pdf_path=out_path,
            data=data,
            diagnostics=diagnostics,
            duration=time.perf_counter() - started,
            typst_source=result.typst,
        )

    # ------------------------------------------------------------------ #

    def _get_compiler(self, root: Path) -> typst.Compiler:
        key = (str(root), tuple(str(p) for p in self.font_dirs))
        if self._compiler is None or self._compiler_key != key:
            self._compiler = typst.Compiler(
                root=str(root),
                font_paths=[str(p) for p in self.font_dirs],
                ignore_system_fonts=False,
            )
            self._compiler_key = key
        return self._compiler

    def invalidate_fonts(self) -> None:
        """Erzwingt beim naechsten Lauf einen frischen Compiler."""
        self._compiler = None
        self._compiler_key = None

    @staticmethod
    def _localize(path_str: str, work: Path, root: Path) -> str:
        """Gibt einen Typst-tauglichen, wurzelrelativen Pfad zurueck.

        Bilder ausserhalb der Wurzel werden ins Arbeitsverzeichnis kopiert.
        """
        if not path_str:
            return ""
        src = Path(path_str)
        if not src.is_file():
            return ""
        try:
            rel = src.resolve().relative_to(root.resolve())
            return "/" + "/".join(rel.parts)
        except ValueError:
            pass
        target = work / f"_ext_{_safe_name(src)}"
        if not target.exists() or target.stat().st_mtime < src.stat().st_mtime:
            shutil.copyfile(src, target)
        return "/" + WORK_DIR_NAME + "/" + target.name

    def _parse(
        self, text: str, default_severity: str, line_map: dict[int, int]
    ) -> list[Diagnostic]:
        """Zerlegt die Ausgabe von Typst in einzelne Meldungen."""
        diags: list[Diagnostic] = []
        if not text:
            return diags

        blocks: list[list[str]] = []
        for line in text.splitlines():
            if _SEVERITY_RE.match(line) or not blocks:
                blocks.append([line])
            else:
                blocks[-1].append(line)

        for block in blocks:
            joined = "\n".join(block)
            head = _SEVERITY_RE.match(block[0])
            severity = head.group(1).lower() if head else default_severity
            message = head.group("msg").strip() if head else block[0].strip()
            if not message:
                continue

            typ_line = None
            md_line = None
            source = ""
            loc = _LOCATION_RE.search(joined)
            if loc:
                source = Path(loc.group("file")).name
                typ_line = int(loc.group("line"))
                if source == "content.typ":
                    md_line = _nearest(line_map, typ_line)
                else:
                    message = f"{message}  [{source}:{typ_line}]"

            # Hinweiszeilen unter der Meldung (z. B. "hint: ...") anhaengen
            hints = [
                b.strip()
                for b in block[1:]
                if b.strip().startswith("hint:")
            ]
            if hints:
                message = message + " -- " + "; ".join(h[5:].strip() for h in hints)

            diags.append(
                Diagnostic(
                    severity=severity,
                    message=message,
                    md_line=md_line,
                    typ_line=typ_line,
                    source=source,
                )
            )
        return diags

    # ------------------------------------------------------------------ #

    def test_emoji_font(self, font: str) -> tuple[bool, str]:
        """Prueft, ob ``font`` Emojis farbig ins PDF bekommt.

        Typsts PDF-Export kann COLRv1-Farbverlaeufe noch nicht einbetten --
        betroffene Schriften (u. a. Segoe UI Emoji unter Windows 11) rendern
        dann schwarze Kaesten. Der Test kompiliert eine Miniseite nach PNG und
        zaehlt die Farben.
        """
        import tempfile

        sample = "\U0001f5fa\U0001f6a8\U0001f3c6\U0001f48e"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "emoji.typ"
            src.write_text(
                f'#set page(width: auto, height: auto, margin: 6pt, fill: white)\n'
                # fallback: false -- sonst springt Typst still auf eine andere
                # Emoji-Schrift und der Test waere bedeutungslos.
                f'#set text(font: ("{font}",), size: 24pt, fallback: false)\n'
                f"{sample}\n",
                encoding="utf-8",
            )
            png = tmp_path / "emoji.png"
            try:
                typst.compile(
                    input=str(src),
                    output=str(png),
                    root=str(tmp_path),
                    format="png",
                    ppi=144,
                )
            except Exception as exc:
                return False, f"Testlauf fehlgeschlagen: {exc}"

            saturated = count_saturated_pixels(png)

        if saturated > 40:
            return True, f"'{font}' liefert farbige Emojis."
        return False, (
            f"'{font}' liefert keine farbigen Emojis -- entweder fehlen die "
            "Glyphen (leere Kaesten) oder die Schrift nutzt ein Farbformat, "
            "das Typst nicht ins PDF einbetten kann. Empfehlung: "
            "'Segoe UI Emoji' waehlen oder NotoColorEmoji.ttf nach "
            "assets/fonts/ legen."
        )


# ---------------------------------------------------------------------- #


def count_saturated_pixels(png: Path) -> int:
    """Zaehlt die deutlich farbigen Pixel eines PNG (Kanalspanne > 30).

    Liest mit QImage statt Pillow, damit CompletionistPDF Pillow nicht
    mitbringen muss. QImage kommt ohne laufende QApplication aus.
    """
    from PySide6.QtGui import QImage

    img = QImage(str(png))
    if img.isNull():
        return 0
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    width, bpl = img.width(), img.bytesPerLine()
    data = img.constBits().asstring(img.sizeInBytes())
    count = 0
    for y in range(img.height()):
        row = data[y * bpl:y * bpl + 3 * width]
        for r, g, b in zip(row[0::3], row[1::3], row[2::3]):
            if max(r, g, b) - min(r, g, b) > 30:
                count += 1
    return count


def _app_dir() -> Path:
    """Verzeichnis mit templates/, presets/ und assets/.

    Im PyInstaller-Bundle liegen die Daten unter ``sys._MEIPASS``.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


def _write_json(path: Path, data: dict) -> None:
    import json

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _warning_text(warnings) -> str:
    if not warnings:
        return ""
    if not isinstance(warnings, (list, tuple)):
        warnings = [warnings]
    parts = []
    for w in warnings:
        text = getattr(w, "diagnostic", None) or str(w)
        if not _SEVERITY_RE.match(text.splitlines()[0] if text else ""):
            text = "warning: " + text
        parts.append(text)
    return "\n".join(parts)


def _nearest(line_map: dict[int, int], typ_line: int) -> int | None:
    """Naechstgelegene gemappte Typst-Zeile <= typ_line."""
    best = None
    for t, m in line_map.items():
        if t <= typ_line and (best is None or t > best[0]):
            best = (t, m)
    return best[1] if best else None


def _place_external(target: Path, source: Path | bytes) -> None:
    """Legt ein externes Bild im Arbeitsordner ab -- nur wenn es sich
    geaendert hat, damit die Live-Vorschau nicht jedes Mal kopiert."""
    if isinstance(source, bytes):
        if not target.exists() or target.read_bytes() != source:
            target.write_bytes(source)
        return
    if (
        not target.exists()
        or target.stat().st_mtime < source.stat().st_mtime
        or target.stat().st_size != source.stat().st_size
    ):
        shutil.copyfile(source, target)


def _safe_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", path.name)


def _hide(path: Path) -> None:
    """Arbeitsordner unter Windows ausblenden."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
    except Exception:
        pass
