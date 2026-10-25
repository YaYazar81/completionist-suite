"""Datenmodell fuer alle Dokument-Einstellungen.

Die Konfiguration wird als JSON in das Arbeitsverzeichnis geschrieben und vom
Typst-Template ueber ``json("config.json")`` eingelesen. Dadurch bleibt
``template.typ`` unveraendert -- es aendert sich nur die Konfiguration.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

# Seitenformate: Typst-Name -> Anzeigename
PAGE_SIZES = {
    "a4": "A4 (210 x 297 mm)",
    "a5": "A5 (148 x 210 mm)",
    "us-letter": "US Letter",
    "a3": "A3 (297 x 420 mm)",
}

TABLE_STYLES = {
    "none": "Rahmenlos",
    "header": "Nur Kopfzeile abgesetzt",
    "grid": "Volles Gitter",
}

WATERMARK_MODES = {
    "off": "Aus",
    "text": "Text",
    "image": "Bild",
}

# Beschriftung der Gliederungsebenen (wie im LyX-Dialog)
LEVEL_NAMES = [
    "Teil",
    "Kapitel",
    "Abschnitt",
    "Unterabschnitt",
    "Unterunterabschnitt",
    "Paragraph",
    "Unterparagraph",
]


@dataclass
class WatermarkConfig:
    mode: str = "off"  # off | text | image
    text: str = "ENTWURF"
    image: str = ""
    opacity: int = 12  # Prozent Deckkraft (0 = unsichtbar)
    angle: float = -45.0  # Grad
    size: float = 72.0  # pt bei Text, Prozent der Seitenbreite bei Bild
    color: str = "#707070"


@dataclass
class CoverConfig:
    enabled: bool = True
    image: str = ""  # absoluter Pfad; leer -> gesetzte Titelseite
    full_bleed: bool = True  # randlos ueber die ganze Seite
    title: str = ""
    subtitle: str = ""
    author: str = ""


@dataclass
class TocConfig:
    enabled: bool = True
    title: str = "Inhaltsverzeichnis"
    # Wie die beiden Schieberegler im LyX-Dialog:
    # bis zu welcher Ebene wird nummeriert bzw. im Verzeichnis aufgefuehrt.
    # 0 = gar nicht. Zaehlung in Markdown-Ebenen (1 = '#').
    numbering_depth: int = 0
    toc_depth: int = 2
    numbering_pattern: str = "1.1.1.1.1.1.1"
    # Nur fuer die Anzeige in der GUI: wie heisst die oberste Ebene?
    # Index in LEVEL_NAMES (0 = Teil, 1 = Kapitel).
    first_level_name: int = 1
    roman_front_matter: bool = True  # Verzeichnis mit roemischen Seitenzahlen


@dataclass
class TypographyConfig:
    body_font: str = "Georgia"
    heading_font: str = "Segoe UI"
    mono_font: str = "Consolas"
    emoji_font: str = "Segoe UI Emoji"
    body_size: float = 11.0
    leading: float = 0.75  # em
    par_spacing: float = 1.0  # em
    justify: bool = True
    hyphenate: bool = True
    lang: str = "de"
    first_line_indent: float = 0.0  # em
    link_color: str = "#1a4b8c"
    h2_rule: bool = True  # Linie unter "##"-Ueberschriften, wie im Editor


@dataclass
class HeaderFooterConfig:
    header_enabled: bool = True
    header_text: str = "{chapter}"  # {chapter} | {title} | freier Text
    header_rule: bool = True
    footer_enabled: bool = True
    footer_format: str = "Seite {page} von {total}"
    footer_rule: bool = False
    skip_on_chapter_start: bool = True


@dataclass
class ContentConfig:
    # Gliederung
    heading_offset: int = 0  # 0: '#' = Ebene 1, 1: '#' = Teil-Ebene ...
    pagebreak_before_level1: bool = True
    hr_as_pagebreak: bool = True  # '***' erzeugt einen Seitenumbruch, '---' wird ignoriert
    # Einfacher Zeilenumbruch in der .md -> Zeilenumbruch im PDF (wie in
    # Obsidian/MarkText). Aus: Standard-Markdown, Zeilen fliessen zusammen.
    soft_breaks_as_linebreaks: bool = True

    # Tabellen
    table_style: str = "header"
    table_zebra: bool = False
    table_header_bold: bool = True

    # Bilder
    image_width: float = 80.0  # Prozent der Textbreite
    figure_captions: bool = True

    # Code
    code_background: str = "#f4f4f6"
    code_border: bool = True
    code_size: float = 9.0


@dataclass
class DocumentConfig:
    # Dateien
    markdown_path: str = ""
    output_path: str = ""

    # Seite
    page_size: str = "a4"
    margin_top: float = 25.0
    margin_bottom: float = 25.0
    margin_left: float = 25.0
    margin_right: float = 25.0
    binding_offset: float = 0.0

    cover: CoverConfig = field(default_factory=CoverConfig)
    toc: TocConfig = field(default_factory=TocConfig)
    typography: TypographyConfig = field(default_factory=TypographyConfig)
    header_footer: HeaderFooterConfig = field(default_factory=HeaderFooterConfig)
    content: ContentConfig = field(default_factory=ContentConfig)
    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)

    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_template_dict(self) -> dict[str, Any]:
        """Konfiguration so, wie das Typst-Template sie erwartet.

        Pfade werden hier bewusst nicht mitgegeben -- die setzt die Engine,
        weil sie weiss, wohin Cover und Wasserzeichen kopiert wurden.
        """
        data = self.to_dict()
        data.pop("markdown_path", None)
        data.pop("output_path", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentConfig":
        return _build(cls, data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "DocumentConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def copy(self) -> "DocumentConfig":
        return DocumentConfig.from_dict(self.to_dict())


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Baut eine (verschachtelte) Dataclass aus einem dict.

    Unbekannte Schluessel werden ignoriert, fehlende behalten ihren Default --
    so bleiben aeltere Presets nach einem Update der App lesbar.
    """
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        if is_dataclass(f.type) and isinstance(value, dict):
            kwargs[f.name] = _build(f.type, value)  # type: ignore[arg-type]
        elif isinstance(value, dict) and f.name in _NESTED:
            kwargs[f.name] = _build(_NESTED[f.name], value)
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


_NESTED: dict[str, type] = {
    "cover": CoverConfig,
    "toc": TocConfig,
    "typography": TypographyConfig,
    "header_footer": HeaderFooterConfig,
    "content": ContentConfig,
    "watermark": WatermarkConfig,
}
