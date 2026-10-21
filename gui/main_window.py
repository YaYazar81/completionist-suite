"""Hauptfenster mit zwei Modi.

* **Markdown-Modus:** Einstellungen links, Vorschau und Protokoll rechts.
* **Viewer-Modus:** nur eine PDF-Datei, ohne Einstellungsleiste.

Typst, die Einstellungsleiste und die letzte Sitzung werden erst geladen,
wenn der Markdown-Modus zum ersten Mal gebraucht wird. Wer nur ein PDF
ansieht, wartet nicht auf die Schriftsuche und das Kompilieren.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from core import __version__, qr_launcher
from core.config import DocumentConfig
from core.presets import PresetStore, user_data_dir
from core.watcher import DebouncedWatcher

from .pdf_file_view import PDF_SUFFIXES, PdfFileView
from .pdf_viewer import PdfPreview

if TYPE_CHECKING:
    from core.typst_engine import CompileResult, TypstEngine

APP_NAME = f"CompletionistPDF {__version__}"  # Fenstertitel mit Version
DEFAULT_PRESET = "Standard"
SESSION_FILE = "session.json"
RECENT_FILE = "completionistpdf_recent.json"
RECENT_MAX = 15
MD_SUFFIXES = (".md", ".markdown", ".txt")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")


def next_free_name(path: Path) -> Path:
    """``Guide.pdf`` -> ``Guide (1).pdf``, bzw. die naechste freie Nummer.

    Ein vorhandener Zusatz wird weitergezaehlt: ``Guide (1).pdf`` ->
    ``Guide (2).pdf`` statt ``Guide (1) (1).pdf``.
    """
    import re

    m = re.fullmatch(r"(.*) \((\d+)\)", path.stem)
    base, n = (m.group(1), int(m.group(2)) + 1) if m else (path.stem, 1)
    while True:
        candidate = path.with_name(f"{base} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# ---------------------------------------------------------------------- #
# Hintergrund-Kompilierung
# ---------------------------------------------------------------------- #


class _Signals(QObject):
    done = Signal(object, object)  # CompileResult, Auftrag


class _Job(QRunnable):
    def __init__(self, engine: TypstEngine, cfg: DocumentConfig, output: Path | None,
                 fmt: str, ppi: float | None) -> None:
        super().__init__()
        self.engine, self.cfg, self.output, self.fmt, self.ppi = engine, cfg, output, fmt, ppi
        self.signals = _Signals()

    def run(self) -> None:
        try:
            res = self.engine.compile(self.cfg, output=self.output, fmt=self.fmt, ppi=self.ppi)
        except Exception as exc:  # letzte Absicherung, damit die GUI weiterlebt
            from core.typst_engine import CompileResult, Diagnostic
            res = CompileResult(ok=False, diagnostics=[Diagnostic("error", f"{type(exc).__name__}: {exc}")])
        self.signals.done.emit(res, self)


class _Call(QRunnable):
    """Fuehrt ``func`` im Hintergrund aus; ``done`` traegt das Ergebnis oder die Ausnahme."""

    def __init__(self, func) -> None:
        super().__init__()
        self.func = func
        self.signals = _Signals()

    def run(self) -> None:
        try:
            res = self.func()
        except Exception as exc:
            res = exc
        self.signals.done.emit(res, self)


# ---------------------------------------------------------------------- #


class MainWindow(QMainWindow):
    def __init__(self, app_dir: Path, path: str | None = None) -> None:
        """``path`` (optional): Datei, die sofort geoeffnet wird. Eine ``.pdf``
        startet im Viewer-Modus, ohne Typst und Sitzung zu laden."""
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1500, 950)
        self.setAcceptDrops(True)

        self.app_dir = app_dir
        self._engine: TypstEngine | None = None
        self.presets = PresetStore(app_dir / "presets")
        self.config = DocumentConfig()
        self.settings = None  # SettingsPanel, entsteht mit dem Markdown-Modus

        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(max(2, self._pool.maxThreadCount()))
        self._busy = False
        self._pending: tuple | None = None  # (output, fmt, ppi) des naechsten Laufs

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self.compile_preview)

        self.watcher = DebouncedWatcher(300, self)
        self.watcher.changed.connect(self._on_file_changed)

        self.viewer = PdfFileView()
        self.viewer.changed.connect(self._on_viewer_changed)
        self.viewer.load_failed.connect(lambda msg: QMessageBox.warning(self, "PDF öffnen", msg))
        self.stack = QStackedWidget()
        self.stack.addWidget(self.viewer)
        self.setCentralWidget(self.stack)
        self._editor: QWidget | None = None

        self.status_label = QLabel("Bereit")
        self.statusBar().addWidget(self.status_label, 1)

        self._build_toolbar()

        if path and Path(path).suffix.lower() in PDF_SUFFIXES and Path(path).is_file():
            self.open_pdf(path)
            if self.viewer.path is not None:
                return
        self._show_editor()
        if path and Path(path).is_file() and Path(path).suffix.lower() in MD_SUFFIXES:
            self.set_markdown(path)

    @property
    def engine(self) -> TypstEngine:
        """Typst-Compiler, beim ersten Zugriff geladen."""
        if self._engine is None:
            from core.typst_engine import TypstEngine

            self._engine = TypstEngine(self.app_dir)
        return self._engine

    def is_viewer_mode(self) -> bool:
        return self.stack.currentWidget() is self.viewer

    # ------------------------------------------------------------------ #
    # Aufbau
    # ------------------------------------------------------------------ #

    def _ensure_editor(self) -> None:
        """Baut den Markdown-Modus beim ersten Bedarf und stellt die Sitzung her."""
        if self._editor is not None:
            return
        self._build_ui()
        self._restore_session()

    def _show_editor(self) -> None:
        self._ensure_editor()
        self.stack.setCurrentWidget(self._editor)
        self._update_mode()

    def _show_viewer(self) -> None:
        self.stack.setCurrentWidget(self.viewer)
        self._update_mode()

    def _build_ui(self) -> None:
        # log_panel importiert core.typst_engine (und damit typst) -- deshalb erst hier
        from .log_panel import LogPanel
        from .settings_panel import SettingsPanel

        self.settings = SettingsPanel(self.engine.available_fonts())
        self.settings.setMinimumWidth(380)
        self.settings.config_changed.connect(self._on_config_changed)
        self.settings.markdown_changed.connect(self._on_markdown_changed)
        self.settings.preset_load_requested.connect(self.load_preset)
        self.settings.preset_save_requested.connect(self.save_preset)
        self.settings.preset_delete_requested.connect(self.delete_preset)
        self.settings.emoji_test_requested.connect(self.test_emoji)

        self.preview = PdfPreview()
        self.log = LogPanel()
        self.log.counts_changed.connect(self._on_log_counts)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.preview, "Vorschau")
        self.tabs.addTab(self.log, "Protokoll")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.settings)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 1060])
        self._editor = splitter
        self.stack.addWidget(splitter)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Werkzeuge")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        def act(text: str, slot, shortcut: str | None = None, tip: str = "") -> QAction:
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(f"{tip or text} ({shortcut})" if shortcut else (tip or text))
            tb.addAction(a)
            return a

        act("Öffnen …", self.open_file, "Ctrl+O", "Markdown- oder PDF-Datei öffnen")
        recent_button = QToolButton(self)
        recent_button.setText("Zuletzt ▾")
        recent_button.setToolTip("Zuletzt geöffnete Dateien")
        recent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_menu = QMenu(recent_button)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        recent_button.setMenu(self.recent_menu)
        tb.addWidget(recent_button)
        act("Drucken …", self.print_pdf, "Ctrl+P", "PDF bzw. Vorschau drucken")
        act("Zusammenführen …", self.merge_files, None,
            "Mehrere Markdown-Dateien zu einer zusammenführen (getrennt durch *** = Seitenumbruch)")
        # Ein F5 fuer beide Modi: Viewer laedt neu, Markdown-Modus kompiliert
        self._act_refresh = act("Neu kompilieren", self.refresh, "F5")
        self._act_export = act("PDF exportieren …", self.export_pdf, "Ctrl+S", "PDF speichern unter …")
        self._sep_editor = tb.addSeparator()
        self._act_editor = act("In Editor öffnen", self._open_md_in_editor, "Ctrl+E")
        self._act_view_pdf = act("PDF ansehen", self.view_output_pdf, None,
                                 "Das exportierte PDF im Viewer-Modus öffnen")
        self._act_markdown = act("◀ Markdown → PDF", self._show_editor, None,
                                 "Zurück zum Markdown-Modus (Einstellungen und Vorschau)")
        act("Ordner öffnen", self._open_output_dir, None, "Ordner der Datei im Explorer öffnen")
        tb.addSeparator()
        act("▣ QR", self.open_qr, None, "CompletionistQR starten (eigenes Fenster)")
        act("ⓘ", self.show_about, "F1", "Über CompletionistPDF, Lizenz und Fremdkomponenten")

    def _update_mode(self) -> None:
        viewer = self.is_viewer_mode()
        for a in (self._act_export, self._act_editor, self._act_view_pdf, self._sep_editor):
            a.setVisible(not viewer)
            a.setEnabled(not viewer)
        self._act_markdown.setVisible(viewer)
        self._act_markdown.setEnabled(viewer)
        self._act_refresh.setText("Neu laden" if viewer else "Neu kompilieren")
        self._act_refresh.setToolTip(("PDF neu laden" if viewer else "Neu kompilieren") + " (F5)")
        self._update_title()
        if viewer:
            self._on_viewer_changed()
        else:
            self.status_label.setText("Bereit")

    # ------------------------------------------------------------------ #
    # Datei-Handling
    # ------------------------------------------------------------------ #

    def open_file(self) -> None:
        if self.is_viewer_mode() and self.viewer.path is not None:
            start = str(self.viewer.path.parent)
        else:
            start = self.config.markdown_path or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Datei öffnen", start,
            "Markdown oder PDF (*.md *.markdown *.txt *.pdf);;Markdown (*.md *.markdown *.txt);;"
            "PDF (*.pdf);;Alle Dateien (*)",
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        """Oeffnet eine Datei passend zu ihrer Endung im richtigen Modus."""
        if Path(path).suffix.lower() in PDF_SUFFIXES:
            self.open_pdf(path)
        else:
            self.set_markdown(path)

    def open_pdf(self, path: str) -> None:
        if self.viewer.open(path):
            self._remember_recent(path)
            self._show_viewer()

    # ------------------------------------------------------------------ #
    # Zuletzt geoeffnet, Drucken, Zusammenfuehren
    # ------------------------------------------------------------------ #

    @staticmethod
    def _recent() -> list[str]:
        try:
            data = json.loads((user_data_dir() / RECENT_FILE).read_text(encoding="utf-8"))
            return [p for p in data if isinstance(p, str)]
        except (OSError, ValueError, TypeError):
            return []

    def _remember_recent(self, path: str | Path) -> None:
        p = str(Path(path))
        recent = [p] + [r for r in self._recent() if Path(r) != Path(p)]
        try:
            (user_data_dir() / RECENT_FILE).write_text(
                json.dumps(recent[:RECENT_MAX], indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = [p for p in self._recent() if Path(p).is_file()]
        if not recent:
            self.recent_menu.addAction("(noch keine)").setEnabled(False)
            return
        for p in recent:
            a = self.recent_menu.addAction(("📄  " if p.lower().endswith(".pdf") else "📝  ") + Path(p).name,
                                           lambda path=p: self.open_path(path))
            a.setToolTip(p)
        self.recent_menu.setToolTipsVisible(True)

    def show_about(self) -> None:
        from core.about_dialog import AboutDialog

        AboutDialog("CompletionistPDF", __version__, "Markdown zu PDF mit Typst · PDF-Viewer",
                    self.windowIcon(), self).exec()

    def print_pdf(self) -> None:
        from .printing import print_document

        if self.is_viewer_mode():
            doc = self.viewer.doc
            title = self.viewer.path.name if self.viewer.path else "PDF"
        else:
            doc = self.preview.document if self.settings is not None else None
            md = self.config.markdown_path
            title = Path(md).with_suffix(".pdf").name if md else "Vorschau"
            if doc is None or doc.pageCount() == 0:
                QMessageBox.information(self, "Drucken", "Die Vorschau ist noch leer -- erst kompilieren (F5).")
                return
        print_document(self, doc, title)

    def merge_files(self) -> None:
        from core.merge_dialog import MergeDialog

        start = str(Path(self.config.markdown_path).parent) if self.config.markdown_path else str(Path.home())
        files = [Path(self.config.markdown_path)] if self.config.markdown_path and not self.is_viewer_mode() else []
        dlg = MergeDialog(files, start, self)
        if dlg.exec() == MergeDialog.DialogCode.Accepted and dlg.target is not None:
            self.set_markdown(str(dlg.target))
            self.status_label.setText(f"Zusammengeführt: {dlg.target}")

    def view_output_pdf(self) -> None:
        out = self._output_path()
        if out is None or not out.is_file():
            QMessageBox.information(self, "PDF ansehen",
                                    "Es gibt noch kein exportiertes PDF. Erst mit „PDF exportieren …“ speichern.")
            return
        self.open_pdf(str(out))

    def refresh(self) -> None:
        if self.is_viewer_mode():
            self.viewer.reload()
            self._on_viewer_changed()
        else:
            self.compile_preview()

    def _on_viewer_changed(self) -> None:
        if self.is_viewer_mode():
            self.status_label.setText(self.viewer.status_text() or "Kein PDF geöffnet")

    def set_markdown(self, path: str) -> None:
        self._remember_recent(path)
        self._show_editor()
        self.settings.md_edit.set_value(str(Path(path)))
        self._on_markdown_changed(str(Path(path)))

    def _on_markdown_changed(self, path: str) -> None:
        self._sync_config()
        self.log.markdown_path = path
        self._update_title()
        self._rewatch()
        self.compile_preview()

    def _on_file_changed(self) -> None:
        if self.settings is not None and self.settings.auto_compile:
            self.compile_preview()

    def _rewatch(self) -> None:
        cfg = self.config
        self.watcher.set_paths([cfg.markdown_path, cfg.cover.image, cfg.watermark.image])

    def _output_path(self) -> Path | None:
        if self.config.output_path:
            return Path(self.config.output_path)
        if self.config.markdown_path:
            return Path(self.config.markdown_path).with_suffix(".pdf")
        return None

    # ------------------------------------------------------------------ #
    # Kompilieren
    # ------------------------------------------------------------------ #

    def _sync_config(self) -> None:
        if self.settings is not None:
            self.settings.store(self.config)

    def _on_config_changed(self) -> None:
        self._sync_config()
        self._rewatch()
        if self.settings.auto_compile:
            self._debounce.start()

    def compile_preview(self) -> None:
        if self.settings is None:
            return
        fmt = "png" if self.preview.needs_png else "pdf"
        self._enqueue(None, fmt, 110 if fmt == "png" else None)

    def export_pdf(self) -> None:
        self._sync_config()
        suggested = self._output_path()
        if suggested is None:
            QMessageBox.information(self, "PDF exportieren", "Bitte zuerst eine Markdown-Datei wählen.")
            return

        # Die Ueberschreib-Rueckfrage des Systemdialogs kennt nur Ja/Nein --
        # deshalb abschalten und selbst mit der "(1)"-Variante fragen.
        path, _ = QFileDialog.getSaveFileName(
            self, "PDF speichern unter", str(suggested), "PDF (*.pdf)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != ".pdf":
            out = out.with_name(out.name + ".pdf")

        if out.exists():
            out = self._ask_overwrite(out)
            if out is None:
                return

        # Gewaehlten Pfad merken, damit der Dialog ihn beim naechsten Mal vorschlaegt
        self.settings.out_edit.set_value(str(out))
        self._sync_config()
        self._enqueue(out, "pdf", None)

    def _ask_overwrite(self, path: Path) -> Path | None:
        """Fragt bei einer vorhandenen Datei nach. Gibt den Zielpfad zurueck
        oder ``None`` bei Abbruch."""
        alternative = next_free_name(path)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Datei existiert bereits")
        box.setText(f"„{path.name}“ existiert bereits in\n{path.parent}")
        box.setInformativeText("Soll die Datei ersetzt oder unter einem neuen Namen gespeichert werden?")
        btn_new = box.addButton(f"Als „{alternative.name}“ speichern", QMessageBox.ButtonRole.AcceptRole)
        btn_over = box.addButton("Überschreiben", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_new)  # Enter zerstoert nichts
        box.setEscapeButton(btn_cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked is btn_new:
            return alternative
        if clicked is btn_over:
            return path
        return None

    def _enqueue(self, output: Path | None, fmt: str, ppi: float | None) -> None:
        self._sync_config()
        if not self.config.markdown_path:
            self.status_label.setText("Keine Markdown-Datei gewählt")
            return
        if self._busy:
            # Ein Export darf nicht von einer spaeteren Vorschau verdraengt
            # werden; ein neuerer Export ersetzt den wartenden aber.
            if output is not None or self._pending is None or self._pending[0] is None:
                self._pending = (output, fmt, ppi)
            return
        self._busy = True
        self.status_label.setText("Kompiliere …" if output is None else f"Exportiere nach {output} …")
        job = _Job(self.engine, self.config.copy(), output, fmt, ppi)
        job.signals.done.connect(self._on_compiled)
        self._pool.start(job)

    def _on_compiled(self, res: CompileResult, job: _Job) -> None:
        self._busy = False
        exported = job.output is not None

        if res.ok:
            if exported:
                summary = f"PDF exportiert: {job.output}  ({res.duration:.2f} s)"
            else:
                summary = f"Kompiliert in {res.duration:.2f} s"
                if isinstance(res.data, bytes):
                    self.preview.show_pdf(res.data)
                elif isinstance(res.data, list):
                    self.preview.show_pngs(res.data)
            self.status_label.setText(summary)
        else:
            summary = f"Kompilierung fehlgeschlagen ({len(res.errors)} Fehler)"
            self.status_label.setText(summary + " – Details im Protokoll")
            if res.errors:
                self.tabs.setCurrentWidget(self.log)
        self.log.set_diagnostics(res.diagnostics, summary)

        if self._pending is not None:
            nxt, self._pending = self._pending, None
            self._enqueue(*nxt)

    def _on_log_counts(self, errors: int, warnings: int) -> None:
        label = "Protokoll"
        if errors or warnings:
            parts = []
            if errors:
                parts.append(f"{errors} Fehler")
            if warnings:
                parts.append(f"{warnings} Warn.")
            label += " (" + ", ".join(parts) + ")"
        self.tabs.setTabText(self.tabs.indexOf(self.log), label)

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #

    def load_preset(self, name: str) -> None:
        if not name:
            return
        self._sync_config()
        try:
            cfg = self.presets.load(name, base=self.config)
        except Exception as exc:
            QMessageBox.warning(self, "Vorlage laden", f"Vorlage „{name}“ konnte nicht geladen werden:\n{exc}")
            return
        self.config = cfg
        self.settings.load(cfg)
        self._rewatch()
        self.status_label.setText(f"Vorlage „{name}“ geladen")
        self.compile_preview()

    def save_preset(self, name: str) -> None:
        if not name or not self.presets.is_user_preset(name):
            suggested = name or ""
            name, ok = QInputDialog.getText(self, "Vorlage speichern", "Name der Vorlage:", text=suggested)
            if not ok or not name.strip():
                return
            name = name.strip()
        self._sync_config()
        self.presets.save(name, self.config)
        self.settings.set_presets(self.presets.names(), name)
        self.status_label.setText(f"Vorlage „{name}“ gespeichert")

    def delete_preset(self, name: str) -> None:
        if not name:
            return
        if not self.presets.is_user_preset(name):
            QMessageBox.information(self, "Vorlage löschen",
                                    f"„{name}“ ist eine mitgelieferte Vorlage und kann nicht gelöscht werden.")
            return
        if QMessageBox.question(self, "Vorlage löschen", f"Vorlage „{name}“ wirklich löschen?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.presets.delete(name)
        self.settings.set_presets(self.presets.names())

    # ------------------------------------------------------------------ #
    # Emoji-Test
    # ------------------------------------------------------------------ #

    def test_emoji(self, font: str) -> None:
        # Im Hintergrund: der Testlauf kompiliert mit Typst und wuerde sonst
        # das Fenster kurz einfrieren.
        self.status_label.setText(f"Teste Emoji-Schrift „{font}“ …")
        self.settings.set_emoji_result(True, "wird geprüft …")
        job = _Call(lambda: self.engine.test_emoji_font(font))
        job.signals.done.connect(self._on_emoji_tested)
        self._pool.start(job)

    def _on_emoji_tested(self, result, _job) -> None:
        ok, msg = result if isinstance(result, tuple) else (False, f"Testlauf fehlgeschlagen: {result}")
        self.settings.set_emoji_result(ok, msg)
        self.status_label.setText(msg)

    # ------------------------------------------------------------------ #
    # Sitzung
    # ------------------------------------------------------------------ #

    def _restore_session(self) -> None:
        self.settings.set_presets(self.presets.names(), DEFAULT_PRESET)
        session = user_data_dir() / SESSION_FILE
        cfg = None
        if session.is_file():
            try:
                cfg = DocumentConfig.from_dict(json.loads(session.read_text(encoding="utf-8")))
            except Exception:
                cfg = None
        if cfg is None and DEFAULT_PRESET in self.presets.names():
            cfg = self.presets.load(DEFAULT_PRESET)
        self.config = cfg or DocumentConfig()
        self.settings.load(self.config)
        self.log.markdown_path = self.config.markdown_path
        self._update_title()
        self._rewatch()
        if self.config.markdown_path and Path(self.config.markdown_path).is_file():
            QTimer.singleShot(0, self.compile_preview)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        # Nur speichern, wenn der Markdown-Modus geladen war -- sonst wuerde ein
        # reiner Viewer-Start die letzte Sitzung mit einer leeren ueberschreiben.
        if self.settings is not None:
            self._sync_config()
            try:
                self.config.save(user_data_dir() / SESSION_FILE)
            except OSError:
                pass
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # Sonstiges
    # ------------------------------------------------------------------ #

    def _update_title(self) -> None:
        if self.is_viewer_mode():
            pdf = self.viewer.path
            self.setWindowTitle(f"{pdf.name} – {APP_NAME}" if pdf else APP_NAME)
            return
        md = self.config.markdown_path
        self.setWindowTitle(f"{Path(md).name} – {APP_NAME}" if md else APP_NAME)

    def _open_md_in_editor(self) -> None:
        if self.config.markdown_path:
            from .log_panel import open_in_editor

            open_in_editor(self.config.markdown_path, None)

    def open_qr(self) -> None:
        error = qr_launcher.launch(self.app_dir)
        if error:
            QMessageBox.warning(self, "CompletionistQR", error)
            return
        self.status_label.setText("CompletionistQR gestartet")

    def _open_output_dir(self) -> None:
        out = self.viewer.path if self.is_viewer_mode() else self._output_path()
        if out is not None and out.parent.is_dir():
            os.startfile(str(out.parent))  # type: ignore[attr-defined]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            suffix = Path(path).suffix.lower()
            if suffix in PDF_SUFFIXES:
                self.open_pdf(path)
                return
            if suffix in MD_SUFFIXES:
                self.set_markdown(path)
                return
            # Ein Bild wird zum Deckblatt -- das gibt es nur im Markdown-Modus
            if suffix in IMAGE_SUFFIXES and not self.is_viewer_mode():
                self.settings.cover_edit.set_value(path)
                self.settings.cover_edit.changed.emit()
                return
