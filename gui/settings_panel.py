"""Linke Seite: Datei, Vorlage und alle Formateinstellungen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    LEVEL_NAMES,
    PAGE_SIZES,
    TABLE_STYLES,
    WATERMARK_MODES,
    DocumentConfig,
)
from core.design import DARK

from .widgets import (
    Binder,
    ColorEdit,
    LabeledSlider,
    PathEdit,
    Section,
    combo,
    font_combo,
    ispin,
    spin,
)

IMAGE_FILTER = "Bilder (*.png *.jpg *.jpeg *.svg *.gif *.webp);;Alle Dateien (*)"
LANGUAGES = {
    "de": "Deutsch",
    "en": "Englisch",
    "fr": "Französisch",
    "es": "Spanisch",
    "it": "Italienisch",
    "nl": "Niederländisch",
}
MAX_LEVEL = 6  # Markdown kennt sechs Ueberschriftenebenen


class SettingsPanel(QWidget):
    config_changed = Signal()
    markdown_changed = Signal(str)

    preset_load_requested = Signal(str)
    preset_save_requested = Signal(str)  # leerer Name = "Speichern unter"
    preset_delete_requested = Signal(str)
    emoji_test_requested = Signal(str)

    def __init__(self, fonts: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fonts = fonts
        self.binder = Binder(self._on_any_change)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        scroll.setWidget(host)

        lay.addWidget(Section("Dokument", self._build_document(), expanded=True))
        lay.addWidget(Section("Vorlage (Preset)", self._build_presets(), expanded=True))
        lay.addWidget(Section("Deckblatt", self._build_cover(), expanded=True))
        lay.addWidget(Section("Seitenformat & Ränder", self._build_page()))
        lay.addWidget(Section("Schriften & Typografie", self._build_typography()))
        lay.addWidget(Section("Nummerierung & Inhaltsverzeichnis", self._build_toc()))
        lay.addWidget(Section("Kopf- & Fußzeile", self._build_header_footer()))
        lay.addWidget(Section("Wasserzeichen", self._build_watermark()))
        lay.addWidget(Section("Tabellen, Bilder & Code", self._build_content()))
        lay.addStretch(1)

    # ------------------------------------------------------------------ #
    # oeffentliche API
    # ------------------------------------------------------------------ #

    def load(self, cfg: DocumentConfig) -> None:
        self.binder.load(cfg)
        self._refresh_level_table()
        self._refresh_cover_thumb()
        self._refresh_watermark_state()

    def store(self, cfg: DocumentConfig) -> None:
        self.binder.store(cfg)

    def set_presets(self, names: list[str], current: str = "") -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(names)
        if current and current in names:
            self.preset_combo.setCurrentText(current)
        self.preset_combo.blockSignals(False)

    def current_preset(self) -> str:
        return self.preset_combo.currentText()

    def set_emoji_result(self, ok: bool, message: str) -> None:
        self.emoji_status.setText(("✔ " if ok else "✘ ") + message)
        self.emoji_status.setStyleSheet(f"color: {DARK['accent_hi'] if ok else DARK['danger']};")

    @property
    def auto_compile(self) -> bool:
        return self.chk_auto.isChecked()

    # ------------------------------------------------------------------ #

    def _b(self, path: str, widget: QWidget) -> QWidget:
        """Bindet ``widget`` an ``path`` und gibt es zurueck (fuer addRow)."""
        return self.binder.bind(path, widget)

    def _on_any_change(self) -> None:
        self._refresh_level_table()
        self._refresh_cover_thumb()
        self._refresh_watermark_state()
        self.config_changed.emit()

    # ------------------------------------------------------------------ #
    # Sektionen
    # ------------------------------------------------------------------ #

    def _build_document(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        self.md_edit = PathEdit(
            "Markdown-Datei öffnen",
            "Markdown (*.md *.markdown *.txt);;Alle Dateien (*)",
            placeholder="Markdown-Datei wählen …",
        )
        self.md_edit.changed.connect(lambda: self.markdown_changed.emit(self.md_edit.value()))
        f.addRow("Markdown:", self._b("markdown_path", self.md_edit))

        self.out_edit = PathEdit("PDF speichern unter", "PDF (*.pdf)", save=True,
                                 placeholder="Standard: gleicher Name wie die .md")
        self.out_edit.setToolTip("Vorschlag für den Speichern-Dialog beim Export")
        f.addRow("Ausgabe-PDF:", self._b("output_path", self.out_edit))

        self.chk_auto = QCheckBox("Bei Änderungen automatisch neu kompilieren")
        self.chk_auto.setChecked(True)
        f.addRow("", self.chk_auto)
        return w

    def _build_presets(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("Auswahl lädt die Vorlage. Markdown- und Ausgabepfad bleiben erhalten.")
        self.preset_combo.activated.connect(
            lambda _i: self.preset_load_requested.emit(self.preset_combo.currentText())
        )
        lay.addWidget(self.preset_combo)

        row = QHBoxLayout()
        for text, slot in (
            ("Speichern", lambda: self.preset_save_requested.emit(self.preset_combo.currentText())),
            ("Speichern unter …", lambda: self.preset_save_requested.emit("")),
            ("Löschen", lambda: self.preset_delete_requested.emit(self.preset_combo.currentText())),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        return w

    def _build_cover(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        f.addRow("", self._b("cover.enabled", QCheckBox("Deckblatt als erste Seite")))

        self.cover_edit = PathEdit("Deckblatt-Bild wählen", IMAGE_FILTER,
                                   placeholder="Ohne Bild: gesetzte Titelseite")
        f.addRow("Bild:", self._b("cover.image", self.cover_edit))

        self.cover_thumb = QLabel()
        self.cover_thumb.setFixedHeight(120)
        self.cover_thumb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        f.addRow("", self.cover_thumb)

        f.addRow("", self._b("cover.full_bleed",
                             QCheckBox("Randlos – Bild füllt die ganze Seite lückenlos")))
        f.addRow("Titel:", self._b("cover.title", QLineEdit()))
        f.addRow("Untertitel:", self._b("cover.subtitle", QLineEdit()))
        f.addRow("Autor:", self._b("cover.author", QLineEdit()))
        hint = _hint("Titel und Autor landen auch in den PDF-Eigenschaften. "
                     "Bei randlosem Bild wird der Titel nicht über das Bild gedruckt.")
        f.addRow("", hint)
        return w

    def _build_page(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        f.addRow("Format:", self._b("page_size", combo(PAGE_SIZES)))
        for key, label in (("margin_top", "Oben:"), ("margin_bottom", "Unten:"),
                           ("margin_left", "Links:"), ("margin_right", "Rechts:")):
            f.addRow(label, self._b(key, spin(0, 80, 1, 1, " mm")))
        bind = self._b("binding_offset", spin(0, 30, 1, 1, " mm"))
        bind.setToolTip("Zusätzlicher Rand links für die Bindung")
        f.addRow("Bundsteg:", bind)
        return w

    def _build_typography(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        f.addRow("Fließtext:", self._b("typography.body_font", font_combo(self._fonts)))
        f.addRow("Überschriften:", self._b("typography.heading_font", font_combo(self._fonts)))
        f.addRow("Code:", self._b("typography.mono_font", font_combo(self._fonts)))

        emoji_row = QWidget()
        er = QHBoxLayout(emoji_row)
        er.setContentsMargins(0, 0, 0, 0)
        self.emoji_combo = font_combo(self._fonts)
        er.addWidget(self._b("typography.emoji_font", self.emoji_combo), 1)
        test = QPushButton("Testen")
        test.setToolTip("Prüft, ob diese Schrift Emojis farbig ins PDF bringt")
        test.clicked.connect(lambda: self.emoji_test_requested.emit(self.emoji_combo.currentText()))
        er.addWidget(test)
        f.addRow("Emojis:", emoji_row)
        self.emoji_status = _hint("")
        self.emoji_status.setWordWrap(True)
        f.addRow("", self.emoji_status)

        f.addRow("Schriftgröße:", self._b("typography.body_size", spin(6, 24, 0.5, 1, " pt")))
        f.addRow("Zeilenabstand:", self._b("typography.leading", spin(0.2, 2.5, 0.05, 2, " em")))
        f.addRow("Absatzabstand:", self._b("typography.par_spacing", spin(0, 4, 0.1, 2, " em")))
        f.addRow("Erstzeileneinzug:", self._b("typography.first_line_indent", spin(0, 5, 0.1, 1, " em")))
        f.addRow("", self._b("typography.justify", QCheckBox("Blocksatz")))
        f.addRow("", self._b("typography.hyphenate", QCheckBox("Silbentrennung")))
        f.addRow("", self._b("typography.h2_rule", QCheckBox("Linie unter Überschrift 2 (##)")))
        breaks = QCheckBox("Einfache Zeilenumbrüche übernehmen")
        breaks.setToolTip(
            "An: Jede neue Zeile in der .md beginnt auch im PDF eine neue Zeile (wie in Obsidian/MarkText).\n"
            "Aus: Standard-Markdown – Zeilen ohne Leerzeile dazwischen fließen zu einem Absatz zusammen."
        )
        f.addRow("", self._b("content.soft_breaks_as_linebreaks", breaks))
        f.addRow("Sprache:", self._b("typography.lang", combo(LANGUAGES)))
        f.addRow("Linkfarbe:", self._b("typography.link_color", ColorEdit()))
        return w

    def _build_toc(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        f = QFormLayout()
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        lay.addLayout(f)

        f.addRow("", self._b("toc.enabled", QCheckBox("Inhaltsverzeichnis nach dem Deckblatt")))
        f.addRow("Titel:", self._b("toc.title", QLineEdit()))
        f.addRow("", self._b("toc.roman_front_matter",
                             QCheckBox("Verzeichnis mit römischen Seitenzahlen (i, ii …)")))

        names = [(i, f"„#“ = {LEVEL_NAMES[i]}") for i in range(2)]
        f.addRow("Oberste Ebene:", self._b("toc.first_level_name", combo(names)))

        offset = self._b("content.heading_offset", ispin(-2, 2))
        offset.setToolTip(
            "Verschiebt alle Überschriften.\n"
            "-1: „##“ wird zur obersten Ebene – sinnvoll, wenn „#“ nur der Dokumenttitel ist."
        )
        f.addRow("Ebenen verschieben:", offset)

        # Die beiden Regler aus dem LyX-Dialog
        lay.addWidget(QLabel("Nummerierung"))
        self.num_slider = LabeledSlider(0, MAX_LEVEL)
        lay.addWidget(self._b("toc.numbering_depth", self.num_slider))
        lay.addWidget(QLabel("Im Inhaltsverzeichnis und als Lesezeichen aufführen"))
        self.toc_slider = LabeledSlider(0, MAX_LEVEL)
        lay.addWidget(self._b("toc.toc_depth", self.toc_slider))

        self.level_table = QTableWidget(MAX_LEVEL, 4)
        self.level_table.setHorizontalHeaderLabels(["Ebene", "Markdown", "Nummeriert", "Im Verzeichnis"])
        self.level_table.verticalHeader().setVisible(False)
        self.level_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.level_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.level_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.level_table.setFixedHeight(self.level_table.verticalHeader().defaultSectionSize() * (MAX_LEVEL + 1) + 6)
        lay.addWidget(self.level_table)

        f2 = QFormLayout()
        lay.addLayout(f2)
        pattern = self._b("toc.numbering_pattern", QLineEdit())
        pattern.setToolTip("Typst-Nummernformat, z. B. 1.1.1 · I.1.a · A.1")
        f2.addRow("Nummernformat:", pattern)
        f2.addRow("", self._b("content.pagebreak_before_level1",
                              QCheckBox("Neue Seite vor jeder obersten Überschrift")))
        f2.addRow("", self._b("content.hr_as_pagebreak",
                              QCheckBox("Seitenumbruch bei *** (--- wird ignoriert)")))
        return w

    def _build_header_footer(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        f.addRow("", self._b("header_footer.header_enabled", QCheckBox("Kopfzeile")))
        head = QComboBox()
        head.setEditable(True)
        head.addItems(["{chapter}", "{title}"])
        head.setToolTip("{chapter} = aktueller Kapiteltitel, {title} = Dokumenttitel, sonst freier Text")
        f.addRow("Inhalt:", self._b("header_footer.header_text", head))
        f.addRow("", self._b("header_footer.header_rule", QCheckBox("Linie unter der Kopfzeile")))
        f.addRow("", self._b("header_footer.skip_on_chapter_start",
                             QCheckBox("Keine Kopfzeile auf Kapitelanfangsseiten")))
        f.addRow("", self._b("header_footer.footer_enabled", QCheckBox("Fußzeile")))
        foot = QLineEdit()
        foot.setToolTip("{page} = aktuelle Seite, {total} = Gesamtzahl der Inhaltsseiten")
        f.addRow("Format:", self._b("header_footer.footer_format", foot))
        f.addRow("", self._b("header_footer.footer_rule", QCheckBox("Linie über der Fußzeile")))
        return w

    def _build_watermark(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        self.wm_mode = combo(WATERMARK_MODES)
        f.addRow("Art:", self._b("watermark.mode", self.wm_mode))
        text = QComboBox()
        text.setEditable(True)
        text.addItems(["ENTWURF", "VERTRAULICH", "CONFIDENTIAL", "DRAFT", "KOPIE"])
        self.wm_text = self._b("watermark.text", text)
        f.addRow("Text:", self.wm_text)
        self.wm_image = self._b("watermark.image", PathEdit("Wasserzeichen-Bild", IMAGE_FILTER))
        f.addRow("Bild:", self.wm_image)
        f.addRow("Deckkraft:", self._b("watermark.opacity", LabeledSlider(0, 100, " %")))
        f.addRow("Winkel:", self._b("watermark.angle", LabeledSlider(-90, 90, "°")))
        self.wm_size = self._b("watermark.size", spin(5, 300, 1, 0))
        self.wm_size.setToolTip("Text: Schriftgröße in pt · Bild: Breite in % der Seite")
        f.addRow("Größe:", self.wm_size)
        self.wm_color = self._b("watermark.color", ColorEdit())
        f.addRow("Farbe:", self.wm_color)
        return w

    def _build_content(self) -> QWidget:
        w = QWidget()
        f = _form(w)
        f.addRow("Tabellenstil:", self._b("content.table_style", combo(TABLE_STYLES)))
        f.addRow("", self._b("content.table_zebra", QCheckBox("Zebrastreifen")))
        f.addRow("", self._b("content.table_header_bold", QCheckBox("Kopfzeile fett")))
        f.addRow("Bildbreite:", self._b("content.image_width", spin(10, 100, 5, 0, " %")))
        f.addRow("", self._b("content.figure_captions", QCheckBox("Alt-Text als Bildunterschrift")))
        f.addRow("Code-Hintergrund:", self._b("content.code_background", ColorEdit()))
        f.addRow("", self._b("content.code_border", QCheckBox("Rahmen um Codeblöcke")))
        f.addRow("Code-Größe:", self._b("content.code_size", spin(6, 16, 0.5, 1, " pt")))
        return w

    # ------------------------------------------------------------------ #
    # abhaengige Anzeigen
    # ------------------------------------------------------------------ #

    def _refresh_level_table(self) -> None:
        cfg = DocumentConfig()
        self.binder.store(cfg)
        first = cfg.toc.first_level_name
        offset = cfg.content.heading_offset
        for row in range(MAX_LEVEL):
            level = row + 1
            name_idx = first + row
            name = LEVEL_NAMES[name_idx] if name_idx < len(LEVEL_NAMES) else f"Ebene {level}"
            md_level = level - offset
            marker = "#" * md_level if 1 <= md_level <= 6 else "–"
            values = [
                name,
                marker,
                "Ja" if level <= cfg.toc.numbering_depth else "Nein",
                "Ja" if level <= cfg.toc.toc_depth else "Nein",
            ]
            for col, v in enumerate(values):
                item = self.level_table.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    self.level_table.setItem(row, col, item)
                item.setText(v)

    def _refresh_cover_thumb(self) -> None:
        path = self.cover_edit.value()
        if path and Path(path).is_file():
            pm = QPixmap(path)
            if not pm.isNull():
                self.cover_thumb.setPixmap(
                    pm.scaledToHeight(120, Qt.TransformationMode.SmoothTransformation)
                )
                return
        self.cover_thumb.clear()
        self.cover_thumb.setText("Kein Bild gewählt")

    def _refresh_watermark_state(self) -> None:
        mode = self.wm_mode.currentData()
        self.wm_text.setEnabled(mode == "text")
        self.wm_color.setEnabled(mode == "text")
        self.wm_image.setEnabled(mode == "image")


# ---------------------------------------------------------------------- #


def _form(w: QWidget) -> QFormLayout:
    f = QFormLayout(w)
    f.setContentsMargins(0, 0, 0, 0)
    f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return f


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
    return lbl
