"""Hauptfenster von CompletionistMD."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEventLoop, QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCursor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import __version__, images, theme
from .emoji_dialog import EmojiDialog
from .gdrive import GDriveSync, SyncStatusButton
from .history_dialog import HistoryDialog
from .markdown_io import MarkdownFile, snapshot, snapshots, write_safely
from .panels import FindBar, OutlinePanel, VaultSearchDialog
from .settings_dialog import SettingsDialog
from .tabs import BaseTab, ImageTab, MdTab, PdfTab, TextTab, kind_of, same_path
from .vault import FileTypeIcons, VaultPanel

APP_TITLE = "CompletionistMD"
WINDOW_TITLE = f"{APP_TITLE} {__version__}"  # Fenstertitel mit Version
SETTINGS_FILE = "completionistmd.json"
RECENT_MAX = 15
OPEN_FILTER = (
    "Unterstützte Dateien (*.md *.markdown *.txt *.pdf *.png *.jpg *.jpeg *.gif *.webp *.svg);;"
    "Markdown (*.md *.markdown);;Text (*.txt);;PDF (*.pdf);;"
    "Bilder (*.png *.jpg *.jpeg *.gif *.webp *.svg);;Alle Dateien (*)"
)


class _NullView:
    """Steht fuer den Editor, solange kein Markdown-Tab offen ist."""

    def call(self, *args, **kwargs) -> None:
        pass

    def run(self, *args, **kwargs) -> None:
        pass

    def setFocus(self) -> None:  # noqa: N802
        pass


_NULL_VIEW = _NullView()

EMOJIS = [
    ("📜", "Schriftrolle / Quest"),
    ("🗺️", "Karte / Fundort"),
    ("🏆", "Trophäe / Erfolg"),
    ("💎", "Sammelobjekt"),
    ("🚨", "Achtung / Missable"),
    ("✅", "Erledigt"),
    ("⚔️", "Kampf"),
    ("🧩", "Rätsel"),
    ("🔑", "Schlüssel / Zugang"),
    ("⭐", "Highlight"),
    ("⏱️", "Zeitkritisch"),
    ("📍", "Position"),
    ("🔴", "Rot / Gefahr"),
    ("🟢", "Grün / Sicher"),
]


def _was_inside(path: Path, folder: str) -> bool:
    """Lag ``path`` unterhalb von ``folder``? Rein textuell -- der Ordner ist ggf. schon weg."""
    try:
        Path(path).relative_to(Path(folder))
    except ValueError:
        return False
    return Path(path) != Path(folder)


# ---------------------------------------------------------------------- #
# Rasterauswahl fuer Tabellen
# ---------------------------------------------------------------------- #


class TableGrid(QWidget):
    """8x8-Raster: Ziehen/Zeigen waehlt die Groesse, Klick fuegt ein."""

    CELL = 18
    MAX = 8

    def __init__(self, on_pick) -> None:
        super().__init__()
        self._on_pick = on_pick
        self._rows = 0
        self._cols = 0
        self.setMouseTracking(True)
        self.setFixedSize(
            self.CELL * self.MAX + 13, self.CELL * self.MAX + 34
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.size()

    def _cell_at(self, pos: QPoint) -> tuple[int, int]:
        col = int((pos.x() - 6) // self.CELL) + 1
        row = int((pos.y() - 6) // self.CELL) + 1
        return max(0, min(self.MAX, row)), max(0, min(self.MAX, col))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._rows, self._cols = self._cell_at(event.position().toPoint())
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._rows = self._cols = 0
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        rows, cols = self._cell_at(event.position().toPoint())
        if rows and cols:
            self._on_pick(rows, cols)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pal = self.palette()
        for r in range(self.MAX):
            for c in range(self.MAX):
                x, y = 6 + c * self.CELL, 6 + r * self.CELL
                active = r < self._rows and c < self._cols
                p.setPen(QPen(pal.mid().color(), 1))
                p.setBrush(
                    QGuiApplication.palette().highlight() if active else pal.base()
                )
                p.drawRect(x, y, self.CELL - 3, self.CELL - 3)
        p.setPen(pal.windowText().color())
        label = (
            f"{self._rows} × {self._cols}  (Zeilen × Spalten)"
            if self._rows and self._cols
            else "Größe wählen …"
        )
        p.drawText(6, self.height() - 10, label)
        p.end()


# ---------------------------------------------------------------------- #


class MainWindow(QMainWindow):
    def __init__(self, app_dir: Path, secondary: bool = False) -> None:
        """``secondary``: es laeuft schon ein CompletionistMD-Fenster. Dann
        werden die zuletzt offenen Tabs nicht wiederhergestellt (sonst waeren
        dieselben Dateien doppelt offen) und die Tab-Liste nicht gespeichert."""
        super().__init__()
        self.app_dir = Path(app_dir)
        self.secondary = secondary
        self.theme = "dark"
        self._emoji_dialog: EmojiDialog | None = None
        self._vault_search: VaultSearchDialog | None = None
        self._md: MdTab | None = None  # zuletzt aktiver Markdown-Tab ("Hauptfenster")
        self._restoring = False

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1180, 900)

        # Rechts die Tabs: Markdown-Editoren, Text, PDF- und Bildvorschau
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("docTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabCloseRequested.connect(lambda i: self.close_tab(self.tabs.widget(i)))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().installEventFilter(self)  # Mittelklick schliesst
        self._tab_icons = FileTypeIcons()

        # Links der Vault-Explorer, rechts die Tabs
        self.vault_panel = VaultPanel(self)
        self.vault_panel.openFile.connect(self.open_file)
        self.vault_panel.openInNewTab.connect(lambda p: self.open_path(p, new_tab=True))
        self.vault_panel.bookmarksChanged.connect(self._on_bookmarks_changed)
        self.vault_panel.aboutToChange.connect(self._on_vault_about_to_change)
        self.vault_panel.pathRenamed.connect(self._on_vault_renamed)
        self.vault_panel.pathRemoved.connect(self._on_vault_removed)
        self.vault_panel.settingsRequested.connect(self.open_settings)
        self.vault_panel.handoffRequested.connect(self.hand_off)
        self.vault_panel.mergeRequested.connect(self.merge_dialog)

        # Zweite Seitenleiste: Gliederung des aktiven Dokuments
        self.outline_panel = OutlinePanel(self)
        self.outline_panel.jump.connect(lambda pos: self.view.call("gotoPos", pos))

        # Rechts: Tabs, darunter die Suchleiste
        self.find_bar = FindBar(self)
        self.find_bar.findRequested.connect(self._find)
        self.find_bar.nextRequested.connect(self._find_next)
        self.find_bar.replaceRequested.connect(self._replace)
        self.find_bar.replaceAllRequested.connect(self._replace_all)
        self.find_bar.closed.connect(self._find_closed)
        right = QWidget(self)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        right_lay.addWidget(self.tabs, 1)
        right_lay.addWidget(self.find_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.vault_panel)
        self.splitter.addWidget(self.outline_panel)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)
        for i in range(3):
            self.splitter.setCollapsible(i, False)
        self.splitter.setSizes([260, 200, 920])
        self.setCentralWidget(self.splitter)

        # Google-Drive-Sync: Netzwerk laeuft komplett in einem eigenen QThread
        self.gdrive = GDriveSync(self)

        self._build_toolbar()
        self._build_statusbar()
        self._new_md_tab()  # Haupt-Tab
        self._load_settings()
        if not secondary:
            self._restore_tabs()

    # ------------------------------------------------------------------ #
    # Tabs
    # ------------------------------------------------------------------ #

    # Der aktive Markdown-Tab -- alle Editor-Befehle (Toolbar, Kontextmenue,
    # Bilder, Einfuegen) wirken auf ihn.

    @property
    def md(self) -> MdTab | None:
        return self._md

    @property
    def view(self):
        return self._md.view if self._md is not None else _NULL_VIEW

    @property
    def file(self) -> MarkdownFile | None:
        return self._md.file if self._md is not None else None

    def all_tabs(self) -> list[BaseTab]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def current_tab(self) -> BaseTab | None:
        return self.tabs.currentWidget()

    def find_tab(self, path: str | Path) -> BaseTab | None:
        """Tab mit dieser Datei -- auch ein Editor-Tab, der sie gerade erst laedt."""
        return next((t for t in self.all_tabs() if same_path(t.path, path)
                     or (isinstance(t, MdTab) and same_path(t.pending, path))), None)

    def _add_tab(self, tab: BaseTab, activate: bool = True) -> BaseTab:
        index = self.tabs.addTab(tab, tab.title())
        tab.changed.connect(lambda t=tab: self._refresh_tab(t))
        self._refresh_tab(tab)
        if activate:
            self.tabs.setCurrentIndex(index)
        return tab

    def _new_md_tab(self, pending: str | None = None, activate: bool = True) -> MdTab:
        tab = MdTab(self.app_dir / "assets" / "editor", self.tabs)
        tab.pending = pending
        tab.view.bridge.command.connect(lambda d, t=tab: self._on_command(t, d))
        tab.view.imagesDropped.connect(self._on_images_dropped)
        tab.view.markdownDropped.connect(self._on_markdown_dropped)
        tab.view.loadFinished.connect(lambda ok, t=tab: self._on_load_finished(t, ok))
        tab.autosave.timeout.connect(lambda t=tab: self._save(reason="auto", tab=t))
        tab.disk_changed_signal.connect(lambda t=tab: self._on_md_disk_changed(t))
        if self._md is None:
            self._md = tab
        self._add_tab(tab, activate)
        tab.view.load_editor()
        return tab

    def _refresh_tab(self, tab: BaseTab) -> None:
        i = self.tabs.indexOf(tab)
        if i < 0:
            return
        self.tabs.setTabText(i, ("• " if tab.is_dirty() else "") + tab.title())
        self.tabs.setTabToolTip(i, str(tab.path) if tab.path else "")
        icon = self._tab_icons.icon_for(tab.path.name) if tab.path else None
        self.tabs.setTabIcon(i, icon if icon is not None else QIcon())
        if tab is self.current_tab():
            self._update_status()

    def _on_tab_changed(self, _index: int) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            self._md = tab
        is_md = isinstance(tab, MdTab)
        # Markdown-Werkzeuge nur im Editor-Tab -- sonst gaeben ihre Kurzbefehle
        # (Strg+0/1 …) den Tab-eigenen (Zoom) nicht frei.
        for w in self._md_only:
            w.setEnabled(is_md)
        if tab is not None and tab.path is not None:
            self.vault_panel.select_file(str(tab.path))
        self._refresh_outline()
        if self.find_bar.isVisible():
            self.find_bar._search()
        self._update_status()

    def _update_status(self) -> None:
        tab = self.current_tab()
        if tab is None:
            self.setWindowTitle(WINDOW_TITLE)
            return
        state, text = tab.save_state()
        self._set_state(state, text)
        self.stats_label.setText(tab.stats())
        if tab.path is not None:
            mark = "•  " if tab.is_dirty() else ""
            self.setWindowTitle(f"{mark}{tab.path.name} — {WINDOW_TITLE}")
            self.path_label.setText(str(tab.path))
        else:
            self.setWindowTitle(WINDOW_TITLE)
            self.path_label.setText("— keine Datei —")

    def open_path(self, path: str | Path, new_tab: bool = False, activate: bool = True) -> BaseTab | None:
        """Datei im passenden Tab oeffnen. Ist sie schon offen, nur dorthin wechseln.

        Markdown: ``new_tab`` False ersetzt den Inhalt des aktiven
        Markdown-Tabs (Einfachklick im Vault), True oeffnet einen neuen
        (Doppelklick). Alle anderen Typen bekommen immer einen eigenen Tab.
        """
        path = Path(path)
        existing = self.find_tab(path)
        if existing is not None:
            if activate:
                self.tabs.setCurrentWidget(existing)
            return existing
        if not path.is_file():
            QMessageBox.warning(self, APP_TITLE, f"Datei nicht gefunden:\n{path}")
            return None
        kind = kind_of(path)
        if kind == "md":
            if new_tab or self._md is None:
                return self._new_md_tab(pending=str(path), activate=activate)
            self._load_md(self._md, path)
            if activate:
                self.tabs.setCurrentWidget(self._md)
            return self._md
        try:
            if kind == "txt":
                tab = TextTab(path, self.tabs)
                tab.saved.connect(lambda _p: self.gdrive.notify_saved())
                tab.conflict.connect(lambda t=tab: self._on_text_conflict(t))
            elif kind == "pdf":
                tab = PdfTab(path, self.tabs)
            elif kind == "img":
                tab = ImageTab(path, self.tabs)
                tab.handoffRequested.connect(self.hand_off)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                return None
        except (OSError, ImportError) as exc:
            QMessageBox.critical(self, APP_TITLE, f"Datei konnte nicht geöffnet werden:\n{path}\n\n{exc}")
            return None
        return self._add_tab(tab, activate)

    def close_tab(self, tab: BaseTab | None) -> None:
        if tab is None:
            return
        if isinstance(tab, MdTab):
            self._flush_save(tab)
            tab.autosave.stop()
        else:
            tab.flush()
        self.tabs.removeTab(self.tabs.indexOf(tab))
        if tab is self._md:
            self._md = next((t for t in self.all_tabs() if isinstance(t, MdTab)), None)
        tab.deleteLater()
        if self.tabs.count() == 0:
            # Nie ein leeres Fenster: ein frischer Editor-Tab mit der Startseite
            self._new_md_tab()
        self._save_settings()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.tabs.tabBar() and event.type() == event.Type.MouseButtonRelease \
                and event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabs.tabBar().tabAt(event.position().toPoint())
            if index >= 0:
                self.close_tab(self.tabs.widget(index))
                return True
        return super().eventFilter(obj, event)

    def _restore_tabs(self) -> None:
        """Beim Start die zuletzt offenen Tabs wiederherstellen."""
        saved = [p for p in self._settings.get("tabs", []) if isinstance(p, str) and Path(p).is_file()]
        last = self._settings.get("last_file", "")
        if not saved and last and Path(last).is_file():
            saved = [last]
        self._restoring = True
        main = self._md
        for path in saved:
            if kind_of(path) == "md" and main is not None and main.pending is None:
                main.pending = path  # die erste .md in den Haupt-Tab
            elif kind_of(path) is not None and self.find_tab(path) is None \
                    and not any(isinstance(t, MdTab) and same_path(t.pending, path) for t in self.all_tabs()):
                self.open_path(path, new_tab=True, activate=False)
        self._restoring = False
        index = self._settings.get("tab_index", 0)
        if isinstance(index, int) and 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    # ------------------------------------------------------------------ #
    # Aufbau
    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> None:
        bar = QToolBar("Werkzeuge", self)
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(bar)
        self.toolbar = bar

        def act(text, slot, shortcut=None, tip=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            a.setToolTip(f"{tip or text}" + (f"  ({shortcut})" if shortcut else ""))
            a.setCheckable(checkable)
            bar.addAction(a)
            self.addAction(a)
            return a

        # --- Seitenleiste ---
        self.a_vault = act("📁", self.toggle_vault, "Ctrl+Shift+E",
                           "Vault-Explorer ein-/ausblenden", True)
        self.a_outline = act("☰", self.toggle_outline, "Ctrl+Shift+G",
                             "Gliederung (Überschriften) ein-/ausblenden", True)
        bar.addSeparator()

        # --- Datei ---
        act("Neu", self.new_file, "Ctrl+N")
        act("Öffnen", self.open_dialog, "Ctrl+O")
        act("Speichern", lambda: self._save(reason="manual"), "Ctrl+S",
            "Sofort speichern (geschieht ohnehin laufend automatisch)")
        file_button = QToolButton(self)
        file_button.setText("Datei ▾")
        file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        file_menu = QMenu(file_button)
        self.recent_menu = file_menu.addMenu("Zuletzt geöffnet")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        file_menu.addAction("Ältere Fassungen …", self.show_history)
        file_menu.addAction("Dateien zusammenführen …", lambda: self.merge_dialog([]))
        file_menu.addSeparator()
        for text, slot, keys in (("Suchen …", lambda: self.open_find(False), "Ctrl+F"),
                                 ("Ersetzen …", lambda: self.open_find(True), "Ctrl+H"),
                                 ("Im Vault suchen …", self.open_vault_search, "Ctrl+Shift+F")):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(keys))
            a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            a.triggered.connect(slot)
            file_menu.addAction(a)
            self.addAction(a)
        file_button.setMenu(file_menu)
        bar.addWidget(file_button)
        bar.addSeparator()

        # --- Absatzformat ---
        self.block_button = QToolButton(self)
        self.block_button.setText("Fließtext")
        self.block_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        block_menu = QMenu(self.block_button)
        self._block_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, label, shortcut in (
            ("p", "Fließtext", "Ctrl+0"),
            ("h1", "Überschrift 1", "Ctrl+1"),
            ("h2", "Überschrift 2", "Ctrl+2"),
            ("h3", "Überschrift 3", "Ctrl+3"),
            ("h4", "Überschrift 4", "Ctrl+4"),
            ("h5", "Überschrift 5", "Ctrl+5"),
            ("h6", "Überschrift 6", "Ctrl+6"),
        ):
            a = QAction(label, self)
            a.setCheckable(True)
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            a.triggered.connect(lambda _=False, k=key: self._exec(k))
            group.addAction(a)
            block_menu.addAction(a)
            self.addAction(a)
            self._block_actions[key] = a
        self.block_button.setMenu(block_menu)
        bar.addWidget(self.block_button)

        self.a_bold = act("B", lambda: self._exec("bold"), "Ctrl+B", "Fett", True)
        self.a_italic = act("I", lambda: self._exec("italic"), "Ctrl+I", "Kursiv", True)
        self.a_strike = act("S̶", lambda: self._exec("strikeThrough"), "Ctrl+Shift+X",
                            "Durchgestrichen", True)
        self.a_code = act("`Code`", lambda: self._exec("code"), "Ctrl+`", "Code", True)
        self.a_quote = act("❝", lambda: self._exec("quote"), "Ctrl+Shift+Q", "Zitat", True)
        bar.addSeparator()

        act("• Liste", lambda: self._exec("ul"), "Ctrl+Shift+L", "Aufzählung")
        act("1. Liste", lambda: self._exec("ol"), "Ctrl+Shift+O", "Nummerierung")
        act("☑ Aufgabe", lambda: self._exec("task"), "Ctrl+Shift+T", "Aufgabenliste")
        bar.addSeparator()

        # --- Tabelle (Rasterauswahl) ---
        self.table_button = QToolButton(self)
        self.table_button.setText("Tabelle ▾")
        self.table_button.setToolTip("Tabelle einfügen (Raster wählen)")
        self.table_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.table_menu = QMenu(self.table_button)
        grid_action = QWidgetAction(self.table_menu)
        grid_action.setDefaultWidget(TableGrid(self._insert_table))
        self.table_menu.addAction(grid_action)
        self.table_menu.addSeparator()
        for label, op in (
            ("Zeile oberhalb einfügen", "rowAbove"),
            ("Zeile unterhalb einfügen", "rowBelow"),
            ("Spalte links einfügen", "colLeft"),
            ("Spalte rechts einfügen", "colRight"),
            (None, None),
            ("Zeile löschen", "delRow"),
            ("Spalte löschen", "delCol"),
            (None, None),
            ("Kopfzeile umschalten", "toggleHeader"),
            ("Tabelle löschen", "delete"),
        ):
            if label is None:
                self.table_menu.addSeparator()
                continue
            a = QAction(label, self)
            a.triggered.connect(lambda _=False, o=op: self._table_op(o))
            self.table_menu.addAction(a)
        self.table_button.setMenu(self.table_menu)
        bar.addWidget(self.table_button)

        # --- Bild ---
        self.image_button = QToolButton(self)
        self.image_button.setText("Bild ▾")
        self.image_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        image_menu = QMenu(self.image_button)
        for label, align in (
            ("Bild einfügen: links umflossen", "left"),
            ("Bild einfügen: zentriert (Block)", "center"),
            ("Bild einfügen: rechts umflossen", "right"),
        ):
            a = QAction(label, self)
            a.triggered.connect(lambda _=False, al=align: self.insert_image_dialog(al))
            image_menu.addAction(a)
        image_menu.addSeparator()
        for label, align in (
            ("Auswahl links umfließen", "left"),
            ("Auswahl zentrieren", "center"),
            ("Auswahl rechts umfließen", "right"),
        ):
            a = QAction(label, self)
            a.triggered.connect(lambda _=False, al=align: self.view.call("imageOp", "align", al))
            image_menu.addAction(a)
        self.image_button.setMenu(image_menu)
        bar.addWidget(self.image_button)

        # --- Emoji ---
        self.emoji_button = QToolButton(self)
        self.emoji_button.setText("😀 ▾")
        self.emoji_button.setToolTip("Emoji einfügen")
        self.emoji_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        emoji_menu = QMenu(self.emoji_button)
        self._fill_emoji_menu(emoji_menu)
        self.emoji_button.setMenu(emoji_menu)
        bar.addWidget(self.emoji_button)

        bar.addSeparator()
        act("─ Linie", lambda: self._exec("rule"), None,
            "Visuelle Linie (---) -- nur Optik")
        act("✂ Trennlinie", lambda: self._exec("break"), None,
            "Harte Trennlinie (***) -- Seitenumbruch im PDF")
        act("{ } Code", lambda: self._exec("codeblock"), None, "Codeblock")
        bar.addSeparator()

        a_pdf = act("▶ PDF", self.open_in_pdf, "F5",
                    "Aktuelle Datei an CompletionistPDF übergeben")
        act("▣ QR", self.open_qr, None,
            "CompletionistQR starten (eigenes Fenster)")

        # Alles, was nur im Markdown-Editor Sinn ergibt (siehe _on_tab_changed)
        md_texts = {"• Liste", "1. Liste", "☑ Aufgabe", "─ Linie", "✂ Trennlinie", "{ } Code"}
        self._md_only = [
            self.block_button, self.table_button, self.image_button, self.emoji_button,
            self.a_bold, self.a_italic, self.a_strike, self.a_code, self.a_quote, a_pdf,
            *self._block_actions.values(),
            *(a for a in bar.actions() if a.text() in md_texts),
        ]


        # Einfuegen faengt Qt ab, damit Bilder als Datei landen statt als data-URI.
        paste = QAction("Einfügen", self)
        paste.setShortcut(QKeySequence.StandardKey.Paste)
        paste.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        paste.triggered.connect(self.paste)
        self.addAction(paste)

    def _build_statusbar(self) -> None:
        self.path_label = QLabel("— keine Datei —", self)
        self.state_label = QLabel("", self)
        self.state_label.setObjectName("saveState")
        self.stats_label = QLabel("", self)
        sb = self.statusBar()
        sb.addWidget(self.path_label, 1)
        sb.addPermanentWidget(self.stats_label)
        sb.addPermanentWidget(self.state_label)

        # Hell/Dunkel in der Statusleiste: in der Toolbar rutschte der Knopf
        # bei normaler Fensterbreite ins Ueberlaufmenue.
        self.a_theme = QAction("☾ Dunkel", self)
        self.a_theme.setToolTip("Hell/Dunkel umschalten")
        self.a_theme.triggered.connect(self.toggle_theme)
        theme_button = QToolButton(self)
        theme_button.setDefaultAction(self.a_theme)
        theme_button.setAutoRaise(True)
        sb.addPermanentWidget(theme_button)

        a_settings = QAction("⚙ Einstellungen", self)
        a_settings.setToolTip("Vault-Verzeichnis, Bookmarks und Google-Drive-Sync")
        a_settings.triggered.connect(self.open_settings)
        settings_button = QToolButton(self)
        settings_button.setDefaultAction(a_settings)
        settings_button.setAutoRaise(True)
        sb.addPermanentWidget(settings_button)

        a_about = QAction("ⓘ", self)
        a_about.setToolTip("Über CompletionistMD, Lizenz und Fremdkomponenten (F1)")
        a_about.setShortcut(QKeySequence("F1"))
        a_about.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        a_about.triggered.connect(self.show_about)
        self.addAction(a_about)
        about_button = QToolButton(self)
        about_button.setDefaultAction(a_about)
        about_button.setAutoRaise(True)
        sb.addPermanentWidget(about_button)

        # Ganz rechts: Google-Drive-Status (nur sichtbar, wenn der Sync aktiv ist)
        self.gdrive_button = SyncStatusButton(self)
        self.gdrive_button.clicked.connect(self._on_gdrive_clicked)
        self.gdrive.statusChanged.connect(self.gdrive_button.set_status)
        sb.addPermanentWidget(self.gdrive_button)

    # ------------------------------------------------------------------ #
    # Einstellungen
    # ------------------------------------------------------------------ #

    @property
    def settings_path(self) -> Path:
        from core.presets import user_data_dir

        return user_data_dir() / SETTINGS_FILE

    def _load_settings(self) -> None:
        self._settings: dict = {}
        try:
            self._settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        self.theme = self._settings.get("theme", "dark")
        self._apply_theme()
        geo = self._settings.get("geometry")
        if isinstance(geo, list) and len(geo) == 4:
            self.setGeometry(*geo)

        self.vault_panel.set_vault(self._settings.get("vault_dir", ""))
        self.vault_panel.set_bookmarks(self._settings.get("bookmarks", []))
        # "splitter3": seit der Gliederung drei Bereiche (der alte Wert passt nicht mehr)
        split = self._settings.get("splitter3")
        if isinstance(split, str) and split:
            self.splitter.restoreState(QByteArray.fromBase64(split.encode("ascii")))
        visible = bool(self._settings.get("vault_visible", True))
        self.vault_panel.setVisible(visible)
        self.a_vault.setChecked(visible)
        outline = bool(self._settings.get("outline_visible", False))
        self.outline_panel.setVisible(outline)
        self.a_outline.setChecked(outline)
        self.gdrive.configure(self._settings.get("gdrive", {}), self.vault_panel.vault, startup=True)

    def _save_settings(self) -> None:
        if self._restoring:
            return
        g = self.geometry()
        # Noch ladende Markdown-Tabs zaehlen mit ihrer wartenden Datei
        tab_paths = [str(t.path) if t.path else (t.pending if isinstance(t, MdTab) else None)
                     for t in self.all_tabs()]
        # Ein weiteres Fenster liest die Datei frisch ein und schreibt nur, was
        # nicht fensterbezogen ist -- so bleibt die Tab-Liste des ersten erhalten,
        # und Aenderungen (Bookmarks, zuletzt geoeffnet) gehen nicht verloren.
        if self.secondary:
            try:
                fresh = json.loads(self.settings_path.read_text(encoding="utf-8"))
                for k in ("tabs", "tab_index", "last_file", "geometry", "splitter3"):
                    if k in fresh:
                        self._settings[k] = fresh[k]
            except (OSError, json.JSONDecodeError):
                pass
        update = {
            "theme": self.theme,
            "vault_dir": self.vault_panel.vault,
            "bookmarks": self.vault_panel.bookmarks(),
            "vault_visible": self.vault_panel.isVisible() if self.isVisible()
            else self._settings.get("vault_visible", True),
            "outline_visible": self.outline_panel.isVisible() if self.isVisible()
            else self._settings.get("outline_visible", False),
        }
        if not self.secondary:
            update.update({
                "geometry": [g.x(), g.y(), g.width(), g.height()],
                "last_file": str(self.file.path) if self.file and self.file.path else "",
                "tabs": [p for p in tab_paths if p],
                "tab_index": max(0, self.tabs.currentIndex()),
                "splitter3": bytes(self.splitter.saveState().toBase64()).decode("ascii"),
            })
        self._settings.update(update)
        try:
            write_safely(self.settings_path,
                         json.dumps(self._settings, indent=2, ensure_ascii=False))
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Datei
    # ------------------------------------------------------------------ #

    def _on_load_finished(self, tab: MdTab, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(
                self,
                APP_TITLE,
                "Das Editor-Bundle in assets/editor konnte nicht geladen werden.",
            )
            return
        if tab.ready:  # loadFinished kommt u. U. mehrfach
            return
        tab.ready = True
        tab.view.call("setTheme", self.theme)
        if tab.pending and Path(tab.pending).is_file():
            path, tab.pending = tab.pending, None
            self._load_md(tab, path)
        else:
            tab.pending = None
            self._show_welcome(tab)

    def queue_open(self, path: str) -> None:
        """Datei aus der Befehlszeile oeffnen (Markdown, sobald der Editor bereit ist)."""
        if kind_of(path) != "md":
            self.open_path(path, new_tab=True)
            return
        main = self._md
        if main is not None and not main.ready and main.pending is None:
            main.pending = path
            self.tabs.setCurrentWidget(main)
        else:
            self.open_path(path, new_tab=True)

    def _show_welcome(self, tab: MdTab | None = None) -> None:
        tab = tab or self._md
        if tab is None:
            return
        tab.autosave.stop()
        tab.file = None
        tab.watch_path(None)
        tab.dirty = False
        tab.loading = True
        tab.view.call(
            "setMarkdown",
            "# CompletionistMD\n\n"
            "Willkommen. Dieses Dokument ist nur eine Vorschau -- es wird nicht gespeichert.\n\n"
            "- **Strg + O** öffnet eine `.md`-Datei\n"
            "- **Strg + N** legt eine neue an\n"
            "- Bilder per **Strg + V** oder Drag & Drop einwerfen; sie landen im Ordner "
            "`images/` neben dem Dokument\n"
            "- Rechtsklick öffnet Bearbeiten-, Emoji-, Tabellen- und Bildaktionen\n"
            "- **Strg + Shift + E** blendet den Vault-Explorer ein und aus; das "
            "Vault-Verzeichnis und die Bookmarks stehen unter **⚙ Einstellungen**\n"
            "- Im Vault-Explorer öffnet ein **Klick** eine Notiz hier, ein **Doppelklick** "
            "in einem neuen Tab -- auch Textdateien, PDFs und Bilder\n\n"
            "***\n\n"
            "Sobald eine Datei geöffnet ist, speichert der Editor jede Änderung nach "
            "etwa 300 ms von selbst.\n",
            "",
        )
        QTimer.singleShot(60, lambda: setattr(tab, "loading", False))
        tab.changed.emit()

    def new_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Neue Markdown-Datei", self._start_dir(), "Markdown (*.md)"
        )
        if not path:
            return
        if not path.lower().endswith((".md", ".markdown")):
            path += ".md"
        try:
            Path(path).write_text("# Neues Dokument\n\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Datei konnte nicht angelegt werden:\n{exc}")
            return
        self.open_file(path)

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Datei öffnen", self._start_dir(), OPEN_FILTER)
        if path:
            self.open_file(path)

    def _start_dir(self) -> str:
        tab = self.current_tab()
        if tab is not None and tab.path:
            return str(tab.path.parent)
        last = self._settings.get("last_file", "")
        if last:
            return str(Path(last).parent)
        return str(Path.home())

    def open_file(self, path: str | Path) -> None:
        """Markdown im aktiven Editor-Tab (wie bisher), alles andere im eigenen Tab."""
        self.open_path(path, new_tab=False)

    def _load_md(self, tab: MdTab, path: str | Path, flush: bool = True) -> None:
        """``flush`` False: den Editorinhalt vorher nicht speichern (Neu laden
        nach einer Aenderung von aussen)."""
        path = Path(path)
        if not tab.ready:
            tab.pending = str(path)  # Editor laedt noch -- dann gleich danach
            return
        if flush:
            self._flush_save(tab)
        tab.autosave.stop()
        try:
            tab.file = MarkdownFile.load(path)
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Datei konnte nicht gelesen werden:\n{exc}")
            return
        tab.watch_path(path)
        self._remember_recent(path)
        tab.loading = True
        tab.last_saved_text = tab.file.body
        base = QUrl.fromLocalFile(str(path.parent) + os.sep).toString()
        tab.view.call("setMarkdown", tab.file.body, base)
        QTimer.singleShot(80, lambda: setattr(tab, "loading", False))
        tab.dirty = False
        tab.error = False
        tab.changed.emit()
        self._save_settings()
        if tab is self.current_tab():
            self.vault_panel.select_file(str(path))

    # ------------------------------------------------------------------ #
    # Vault-Explorer
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Gliederung
    # ------------------------------------------------------------------ #

    def show_about(self) -> None:
        from core.about_dialog import AboutDialog

        AboutDialog(APP_TITLE, __version__, "WYSIWYG-Markdown-Editor der Completionist Suite",
                    self.windowIcon(), self).exec()

    def toggle_outline(self) -> None:
        visible = not self.outline_panel.isVisible()
        self.outline_panel.setVisible(visible)
        self.a_outline.setChecked(visible)
        self._refresh_outline()
        self._save_settings()

    def _refresh_outline(self) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab) and tab.ready:
            tab.view.call("outline", callback=lambda items: self.outline_panel.set_items(
                items if isinstance(items, list) and tab is self.current_tab() else []))
        else:
            self.outline_panel.set_items([])

    # ------------------------------------------------------------------ #
    # Suchen und Ersetzen
    # ------------------------------------------------------------------ #

    def open_find(self, replace: bool) -> None:
        tab = self.current_tab()
        if isinstance(tab, PdfTab):
            tab.find_edit.setFocus()  # der PDF-Tab hat seine eigene Suche
            tab.find_edit.selectAll()
            return
        if isinstance(tab, MdTab):
            tab.view.call("selectedText", callback=lambda t: self.find_bar.open(
                replace, t if isinstance(t, str) else ""))
        elif isinstance(tab, TextTab):
            self.find_bar.open(replace, tab.editor.textCursor().selectedText())
        else:
            self.find_bar.open(replace)

    def _find(self, text: str, case: bool) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            tab.view.call("find", text, case, callback=self._show_find)
        elif isinstance(tab, TextTab):
            self._text_find(tab, text, case, 0)
        else:
            self.find_bar.show_result(0, -1)

    def _find_next(self, step: int) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            tab.view.call("findNext", step, callback=self._show_find)
        elif isinstance(tab, TextTab):
            self._text_find(tab, self.find_bar.find_edit.text(), self.find_bar.case.isChecked(), step)

    def _replace(self, text: str) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            tab.view.call("replace", text, callback=self._show_find)
        elif isinstance(tab, TextTab):
            cur = tab.editor.textCursor()
            if cur.hasSelection():
                cur.insertText(text)
            self._find_next(1)

    def _replace_all(self, text: str) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            tab.view.call("replaceAll", text, callback=lambda r: (
                self.find_bar.show_result(0, -1),
                self.statusBar().showMessage(f"{(r or {}).get('replaced', 0)} Stelle(n) ersetzt", 5000)))
        elif isinstance(tab, TextTab):
            needle = self.find_bar.find_edit.text()
            if not needle:
                return
            doc = tab.editor.document()
            flags = self._text_flags(self.find_bar.case.isChecked())
            cur = tab.editor.textCursor()
            cur.beginEditBlock()
            n = 0
            hit = doc.find(needle, 0, flags)
            while not hit.isNull():
                hit.insertText(text)
                n += 1
                hit = doc.find(needle, hit.position(), flags)
            cur.endEditBlock()
            self.find_bar.show_result(0, -1)
            self.statusBar().showMessage(f"{n} Stelle(n) ersetzt", 5000)

    def _show_find(self, result) -> None:
        if isinstance(result, dict):
            self.find_bar.show_result(int(result.get("count", 0)), int(result.get("index", -1)))

    @staticmethod
    def _text_flags(case: bool):
        from PySide6.QtGui import QTextDocument

        return QTextDocument.FindFlag.FindCaseSensitively if case else QTextDocument.FindFlag(0)

    def _text_find(self, tab: TextTab, needle: str, case: bool, step: int) -> None:
        """Suche im Text-Tab: step 0 = ab Auswahlbeginn, +1/-1 = weiter/zurueck."""
        doc, ed = tab.editor.document(), tab.editor
        if not needle:
            self.find_bar.show_result(0, -1)
            return
        flags = self._text_flags(case)
        positions = []
        hit = doc.find(needle, 0, flags)
        while not hit.isNull():
            positions.append(hit.selectionStart())
            hit = doc.find(needle, hit.position(), flags)
        if not positions:
            self.find_bar.show_result(0, -1)
            return
        start = ed.textCursor().selectionStart()
        if step == 0:
            index = next((i for i, p in enumerate(positions) if p >= start), 0)
        elif step > 0:
            index = next((i for i, p in enumerate(positions) if p > start), 0)
        else:
            index = next((i for i in range(len(positions) - 1, -1, -1) if positions[i] < start),
                         len(positions) - 1)
        ed.setTextCursor(doc.find(needle, positions[index], flags))
        ed.ensureCursorVisible()
        self.find_bar.show_result(len(positions), index)

    def _find_closed(self) -> None:
        tab = self.current_tab()
        if isinstance(tab, MdTab):
            tab.view.call("clearFind")
            tab.view.setFocus()
        elif tab is not None:
            tab.setFocus()

    # ------------------------------------------------------------------ #
    # Im Vault suchen
    # ------------------------------------------------------------------ #

    def open_vault_search(self) -> None:
        if self._vault_search is None:
            self._vault_search = VaultSearchDialog(self)
            self._vault_search.openHit.connect(self._open_search_hit)
        root = self.vault_panel.vault or (str(self.file.path.parent) if self.file and self.file.path else "")
        self._vault_search.start(root, self.find_bar.find_edit.text() if self.find_bar.isVisible() else "")

    def _open_search_hit(self, path: str, query: str) -> None:
        tab = self.open_path(path, new_tab=kind_of(path) != "md")
        if tab is None:
            return
        # Treffer im Dokument markieren, sobald es geladen ist
        def mark(attempt: int = 0) -> None:
            if isinstance(tab, MdTab) and (not tab.ready or tab.loading or tab.pending) and attempt < 40:
                QTimer.singleShot(100, lambda: mark(attempt + 1))
                return
            self.find_bar.find_edit.blockSignals(True)
            self.find_bar.open(False, query)
            self.find_bar.find_edit.blockSignals(False)
        QTimer.singleShot(150, mark)

    # ------------------------------------------------------------------ #
    # Zuletzt geoeffnet, aeltere Fassungen, Zusammenfuehren
    # ------------------------------------------------------------------ #

    def _remember_recent(self, path: Path) -> None:
        recent = [p for p in self._settings.get("recent", []) if isinstance(p, str)]
        p = str(Path(path))
        recent = [p] + [r for r in recent if not same_path(r, p)]
        self._settings["recent"] = recent[:RECENT_MAX]

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = [p for p in self._settings.get("recent", []) if isinstance(p, str) and Path(p).is_file()]
        if not recent:
            self.recent_menu.addAction("(noch keine)").setEnabled(False)
            return
        for p in recent:
            a = self.recent_menu.addAction(Path(p).name, lambda path=p: self.open_path(path, new_tab=True))
            a.setToolTip(p)
        self.recent_menu.setToolTipsVisible(True)
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Liste leeren", lambda: self._settings.update(recent=[]))

    def show_history(self) -> None:
        tab = self.current_tab()
        path = tab.path if tab is not None else None
        if path is None or kind_of(path) not in ("md", "txt"):
            QMessageBox.information(self, APP_TITLE, "Ältere Fassungen gibt es für Markdown- und Textdateien.")
            return
        if not snapshots(path):
            QMessageBox.information(
                self, APP_TITLE,
                f"Für „{path.name}“ gibt es noch keine älteren Fassungen.\n\nSie entstehen beim "
                "Speichern (höchstens alle 10 Minuten) im versteckten Ordner .completionistmd daneben.")
            return
        dlg = HistoryDialog(path, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.chosen() is None:
            return
        try:
            data = dlg.chosen().read_bytes()
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Fassung nicht lesbar:\n{exc}")
            return
        if isinstance(tab, MdTab):
            self._flush_save(tab)
        else:
            tab.flush()
        snapshot(path, force=True)  # der jetzige Stand bleibt ebenfalls erhalten
        try:
            write_safely(path, data)
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Wiederherstellen fehlgeschlagen:\n{exc}")
            return
        if isinstance(tab, MdTab):
            self._load_md(tab, path, flush=False)
        elif isinstance(tab, TextTab):
            tab.reload()
        self.statusBar().showMessage("Ältere Fassung wiederhergestellt.", 6000)

    def merge_dialog(self, files: list) -> None:
        from core.merge_dialog import MergeDialog

        if not files:
            files = self.vault_panel.selected_markdown()
        if not files and self.file is not None and self.file.path is not None:
            files = [str(self.file.path)]
        # Offene Dateien erst speichern, damit der aktuelle Stand einfliesst
        for tab in self.all_tabs():
            if isinstance(tab, MdTab) and tab.path is not None and any(same_path(tab.path, f) for f in files):
                self._flush_save(tab)
        dlg = MergeDialog([Path(f) for f in files], self._start_dir(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.target is not None:
            self.open_path(dlg.target, new_tab=True)
            self.statusBar().showMessage(f"Zusammengeführt: {dlg.target}", 6000)

    def toggle_vault(self) -> None:
        visible = not self.vault_panel.isVisible()
        self.vault_panel.setVisible(visible)
        self.a_vault.setChecked(visible)
        self._save_settings()

    def open_settings(self, _checked: bool = False, start_tab: str = "") -> None:
        dlg = SettingsDialog(self, self.vault_panel.vault, self.vault_panel.bookmarks(),
                             gdrive=self._settings.get("gdrive", {}), sync=self.gdrive,
                             start_tab=start_tab)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.vault() != self.vault_panel.vault:
            self.vault_panel.set_vault(dlg.vault())
            if dlg.vault() and not self.vault_panel.isVisible():
                self.toggle_vault()
        self.vault_panel.set_bookmarks(dlg.bookmarks())
        self._settings["gdrive"] = dlg.gdrive_settings()
        self._save_settings()
        self.gdrive.configure(self._settings["gdrive"], self.vault_panel.vault)

    def _on_gdrive_clicked(self) -> None:
        # Ohne Anmeldung hilft kein Sync-Lauf -- direkt zu den Einstellungen
        if self.gdrive_button.state == "auth":
            self.open_settings(start_tab="gdrive")
        else:
            self.gdrive.sync_now()

    def _on_bookmarks_changed(self, _items: list) -> None:
        self._save_settings()

    def _tabs_under(self, path: str) -> list[BaseTab]:
        """Tabs, deren Datei ``path`` ist oder darin liegt."""
        return [t for t in self.all_tabs()
                if t.path is not None and (t.path == Path(path) or _was_inside(t.path, path))]

    def _on_vault_about_to_change(self, path: str) -> None:
        # Vor dem Umbenennen/Loeschen den aktuellen Stand noch an den alten Ort.
        for tab in self._tabs_under(path):
            if isinstance(tab, MdTab):
                self._flush_save(tab)
            else:
                tab.flush()

    def _on_vault_renamed(self, old: str, new: str) -> None:
        for tab in self._tabs_under(old):
            moved = Path(new) if tab.path == Path(old) else Path(new) / tab.path.relative_to(old)
            tab.set_path(moved)
            if isinstance(tab, MdTab) and Path(new).is_dir():
                # Ordner umbenannt: Bildpfade neu aufloesen
                self._load_md(tab, moved)
        self._update_status()
        self._save_settings()

    def _on_vault_removed(self, path: str) -> None:
        affected = self._tabs_under(path)
        if not affected:
            return
        for tab in affected:
            if isinstance(tab, MdTab) and tab is self._md:
                self._show_welcome(tab)  # der Haupt-Tab bleibt stehen
            else:
                if isinstance(tab, MdTab):
                    tab.autosave.stop()
                elif isinstance(tab, TextTab):
                    tab.autosave.stop()
                    tab.editor.document().setModified(False)  # nichts mehr zurueckschreiben
                self.tabs.removeTab(self.tabs.indexOf(tab))
                tab.deleteLater()
        if self.tabs.count() == 0:
            self._new_md_tab()
        self.statusBar().showMessage("Geöffnete Datei(en) wurden in den Papierkorb verschoben.", 6000)
        self._save_settings()

    # ------------------------------------------------------------------ #
    # Speichern
    # ------------------------------------------------------------------ #

    def _save(self, reason: str = "auto", tab: BaseTab | None = None) -> None:
        tab = tab or (self.current_tab() if reason == "manual" else self._md)
        if isinstance(tab, TextTab):
            tab.save()
            return
        if not isinstance(tab, MdTab) or tab.file is None or tab.file.path is None:
            if reason == "manual":
                QMessageBox.information(
                    self, APP_TITLE,
                    "In diesem Tab gibt es nichts zu speichern (Strg + N oder Strg + O).",
                )
            return
        if tab.loading:
            return
        tab.view.run("CM.getMarkdown()", lambda body, t=tab: self._write_body(t, body))

    def _write_body(self, tab: MdTab, body) -> None:
        if not isinstance(body, str) or tab.file is None or tab.file.path is None:
            return
        if body == tab.last_saved_text:
            tab.dirty = False
            tab.changed.emit()
            return
        try:
            tab.file.save(body)
        except OSError as exc:
            tab.error = True
            tab.changed.emit()
            self.statusBar().showMessage(f"Speichern fehlgeschlagen: {exc}", 8000)
            return
        tab.last_saved_text = body
        tab.dirty = False
        tab.error = False
        tab.watch_path(tab.file.path)  # eigenes Speichern ist keine Aenderung von aussen
        tab.changed.emit()
        self.gdrive.notify_saved()

    # ------------------------------------------------------------------ #
    # Aenderungen von aussen (zweites CompletionistMD-Fenster, andere Programme)
    # ------------------------------------------------------------------ #

    def _on_md_disk_changed(self, tab: MdTab) -> None:
        if tab.file is None or tab.file.path is None or not tab.file.path.is_file() \
                or getattr(tab, "_asking", False):
            return
        path = tab.file.path
        try:
            disk = MarkdownFile.load(path)
        except OSError:
            return
        if tab.last_saved_text is not None and \
                disk.compose(disk.body) == tab.file.compose(tab.last_saved_text):
            return  # nur der Zeitstempel hat sich geaendert
        if not tab.dirty:
            self._load_md(tab, path, flush=False)
            self.statusBar().showMessage(f"{path.name} wurde außerhalb geändert und neu geladen.", 6000)
            return
        tab.autosave.stop()
        tab._asking = True
        try:
            keep = self._ask_conflict(path)
        finally:
            tab._asking = False
        if keep:
            snapshot(path, force=True)  # die fremde Fassung bleibt im Verlauf
            tab.last_saved_text = None
            self._save(reason="auto", tab=tab)
        else:
            body = self._fetch_body(tab)
            if body is not None:  # die eigene Fassung bleibt im Verlauf
                snapshot(path, force=True, data=tab.file.compose(body).encode("utf-8"))
            self._load_md(tab, path, flush=False)

    def _on_text_conflict(self, tab: TextTab) -> None:
        tab.autosave.stop()
        if self._ask_conflict(tab.path):
            snapshot(tab.path, force=True)
            tab.save()
        else:
            snapshot(tab.path, force=True, data=tab.editor.toPlainText().encode("utf-8"))
            tab.editor.document().setModified(False)
            tab.reload()

    def _ask_conflict(self, path: Path) -> bool:
        """True = eigene Fassung behalten, False = Fassung von der Platte laden."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(APP_TITLE)
        box.setText(f"„{path.name}“ wurde außerhalb dieses Fensters geändert "
                    "(z. B. in einem zweiten CompletionistMD-Fenster).")
        box.setInformativeText("Hier gibt es ebenfalls ungespeicherte Änderungen. Welche Fassung "
                               "soll gelten? Die andere bleibt unter „Ältere Fassungen …“ erhalten.")
        mine = box.addButton("Meine Fassung behalten", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Andere Fassung laden", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(mine)
        box.exec()
        return box.clickedButton() is mine

    def _flush_save(self, tab: MdTab | None = None) -> None:
        """Synchron speichern -- fuer Dateiwechsel, Tab schliessen und Programmende."""
        tab = tab or self._md
        if tab is None or tab.file is None or tab.file.path is None or tab.loading or not tab.ready:
            return
        tab.autosave.stop()
        body = self._fetch_body(tab)
        if body is not None:
            self._write_body(tab, body)

    def _fetch_body(self, tab: MdTab) -> str | None:
        """Markdown des Editors synchron abholen (hoechstens 1,5 s warten)."""
        if not tab.ready:
            return None
        loop = QEventLoop()
        result: dict = {}

        def done(body):
            result["body"] = body
            loop.quit()

        tab.view.run("CM.getMarkdown()", done)
        QTimer.singleShot(1500, loop.quit)  # nie haengen bleiben
        loop.exec()
        body = result.get("body")
        return body if isinstance(body, str) else None

    def _set_state(self, state: str, text: str) -> None:
        self.state_label.setText(text)
        self.state_label.setProperty("state", state)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    # ------------------------------------------------------------------ #
    # Bruecke
    # ------------------------------------------------------------------ #

    def _on_command(self, tab: MdTab, data: dict) -> None:
        kind = data.get("type")
        if kind == "ready":
            tab.view.call("setTheme", self.theme)
        elif kind == "dirty":
            if tab.loading or tab.file is None:
                return
            tab.dirty = True
            tab.changed.emit()
            tab.autosave.start()
        elif kind == "state":
            stats = data.get("stats") or {}
            if stats:
                tab.words = f"{stats.get('words', 0)} Wörter"
            if tab is self.current_tab():
                self._apply_state(data)
        elif kind == "outline":
            if tab is self.current_tab():
                self.outline_panel.set_items(data.get("items") or [])
        elif kind == "pasteImage":
            # Strg+V mit Bild, von Chromium statt von der QAction verarbeitet
            QTimer.singleShot(0, lambda t=tab: self._paste_image(t))
        elif kind == "contextmenu":
            # Nicht im Konsolen-Callback der Seite ein Menue (eigene Ereignisschleife) oeffnen.
            pos = QCursor.pos()
            QTimer.singleShot(0, lambda: self._show_context_menu(data, pos))

    def _apply_state(self, st: dict) -> None:
        self.a_bold.setChecked(bool(st.get("bold")))
        self.a_italic.setChecked(bool(st.get("italic")))
        self.a_strike.setChecked(bool(st.get("strike")))
        self.a_code.setChecked(bool(st.get("code")))
        self.a_quote.setChecked(bool(st.get("quote")))
        block = st.get("block", "p")
        labels = {
            "p": "Fließtext", "h1": "Überschrift 1", "h2": "Überschrift 2",
            "h3": "Überschrift 3", "h4": "Überschrift 4", "h5": "Überschrift 5",
            "h6": "Überschrift 6", "ul": "Aufzählung", "ol": "Nummerierung",
            "task": "Aufgabe", "pre": "Codeblock", "td": "Tabelle", "th": "Tabelle",
        }
        self.block_button.setText(labels.get(block, "Fließtext"))
        if block in self._block_actions:
            self._block_actions[block].setChecked(True)
        self.table_button.setEnabled(True)
        stats = st.get("stats") or {}
        if stats:
            self.stats_label.setText(f"{stats.get('words', 0)} Wörter")

    # ------------------------------------------------------------------ #
    # Befehle
    # ------------------------------------------------------------------ #

    def _exec(self, cmd: str, arg=None) -> None:
        self.view.call("exec", cmd, arg)
        self.view.setFocus()

    def _table_op(self, op: str) -> None:
        self.view.call("tableOp", op, None)
        self.view.setFocus()

    def _insert_table(self, rows: int, cols: int) -> None:
        self.table_menu.close()
        self.view.call("insertTable", rows, cols)
        self.view.setFocus()

    def _web_action(self, action: QWebEnginePage.WebAction) -> None:
        self.view.setFocus()
        self.view.page().triggerAction(action)

    # ------------------------------------------------------------------ #
    # Emojis
    # ------------------------------------------------------------------ #

    def _fill_emoji_menu(self, menu: QMenu) -> None:
        for char, name in EMOJIS:
            a = menu.addAction(f"{char}   {name}")
            a.triggered.connect(lambda _=False, c=char: self._exec("text", c))
        menu.addSeparator()
        menu.addAction("Weitere Emojis …", self.open_emoji_dialog)

    def open_emoji_dialog(self) -> None:
        if self._emoji_dialog is None:
            self._emoji_dialog = EmojiDialog(self)
            self._emoji_dialog.picked.connect(self._insert_emoji)
        self._emoji_dialog.show()
        self._emoji_dialog.raise_()
        self._emoji_dialog.activateWindow()

    def _insert_emoji(self, char: str) -> None:
        # Der Dialog bleibt offen und behaelt den Fokus fuer weitere Klicks.
        self.view.call("exec", "text", char)

    # ------------------------------------------------------------------ #
    # Kontextmenue (Rechtsklick im Editor, ausgeloest aus main.js)
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, info: dict, pos: QPoint) -> None:
        menu = QMenu(self)
        has_sel = bool(info.get("hasSelection"))
        kind = info.get("kind", "text")

        def add(target: QMenu, text: str, slot, enabled: bool = True, keys: str = "") -> QAction:
            a = target.addAction(text + (f"\t{keys}" if keys else ""))
            a.triggered.connect(slot)
            a.setEnabled(bool(enabled))
            return a

        if kind in ("image", "inlineImage"):
            if kind == "image":
                for text, align in (("Links umflossen", "left"), ("Zentriert (Block)", "center"),
                                    ("Rechts umflossen", "right")):
                    add(menu, text, lambda _=False, al=align: self.view.call("imageOp", "align", al))
                menu.addSeparator()
                add(menu, "Breiter (+5 %)", lambda: self.view.call("imageOp", "width", "+"))
                add(menu, "Schmaler (−5 %)", lambda: self.view.call("imageOp", "width", "-"))
                add(menu, "Bildunterschrift …", lambda: self.view.call("imageOp", "alt"))
            add(menu, "Bild entfernen", lambda: self.view.call("imageOp", "delete"))
            menu.addSeparator()

        add(menu, "Rückgängig", lambda: self.view.call("undo"), info.get("canUndo"), "Strg+Z")
        add(menu, "Wiederholen", lambda: self.view.call("redo"), info.get("canRedo"), "Strg+Y")
        menu.addSeparator()
        add(menu, "Ausschneiden", lambda: self._web_action(QWebEnginePage.WebAction.Cut),
            has_sel, "Strg+X")
        add(menu, "Kopieren", lambda: self._web_action(QWebEnginePage.WebAction.Copy),
            has_sel, "Strg+C")
        add(menu, "Einfügen", self.paste, True, "Strg+V")
        add(menu, "Löschen", lambda: self.view.call("deleteSelection"), has_sel, "Entf")
        menu.addSeparator()
        add(menu, "Alles auswählen", lambda: self.view.call("selectAll"), True, "Strg+A")
        menu.addSeparator()

        emoji = menu.addMenu("Emoji einfügen")
        self._fill_emoji_menu(emoji)

        if kind == "text":
            fmt = menu.addMenu("Format")
            for text, cmd, keys in (
                ("Fett", "bold", "Strg+B"), ("Kursiv", "italic", "Strg+I"),
                ("Durchgestrichen", "strikeThrough", "Strg+Shift+X"), ("Code", "code", "Strg+`"),
            ):
                add(fmt, text, lambda _=False, c=cmd: self._exec(c), True, keys)
            fmt.addSeparator()
            add(fmt, "Link …", lambda: self._exec("link"))
            add(fmt, "Formatierung entfernen", lambda: self._exec("clear"))

            para = menu.addMenu("Absatz")
            for text, cmd in (
                ("Fließtext", "p"), ("Überschrift 1", "h1"), ("Überschrift 2", "h2"),
                ("Überschrift 3", "h3"), (None, None), ("Aufzählung", "ul"),
                ("Nummerierung", "ol"), ("Aufgabe", "task"), ("Zitat", "quote"),
                ("Codeblock", "codeblock"),
            ):
                if text is None:
                    para.addSeparator()
                    continue
                add(para, text, lambda _=False, c=cmd: self._exec(c))

            ins = menu.addMenu("Neu einfügen")
            add(ins, "Tabelle 3×3", lambda: self._insert_table(3, 3))
            add(ins, "Visuelle Linie (---)", lambda: self._exec("rule"))
            add(ins, "Harte Trennlinie (***)", lambda: self._exec("break"))
            add(ins, "Bild …", lambda: self.insert_image_dialog("center"))

        if info.get("inTable"):
            table = menu.addMenu("Tabelle")
            for text, op, arg in (
                ("Zeile oberhalb einfügen", "rowAbove", None),
                ("Zeile unterhalb einfügen", "rowBelow", None),
                ("Spalte links einfügen", "colLeft", None),
                ("Spalte rechts einfügen", "colRight", None),
                (None, None, None),
                ("Zeile löschen", "delRow", None),
                ("Spalte löschen", "delCol", None),
                (None, None, None),
                ("Kopfzeile umschalten", "toggleHeader", None),
                ("Spalte linksbündig", "align", "left"),
                ("Spalte zentriert", "align", "center"),
                ("Spalte rechtsbündig", "align", "right"),
                (None, None, None),
                ("Tabelle löschen", "delete", None),
            ):
                if text is None:
                    table.addSeparator()
                    continue
                add(table, text, lambda _=False, o=op, a=arg: self.view.call("tableOp", o, a))

        menu.exec(pos)
        menu.deleteLater()

    # ------------------------------------------------------------------ #
    # Bilder
    # ------------------------------------------------------------------ #

    def _require_file(self) -> bool:
        if self.file and self.file.path:
            return True
        QMessageBox.information(
            self,
            APP_TITLE,
            "Bilder brauchen eine gespeicherte Datei -- sie werden im Ordner "
            "images/ daneben abgelegt.\n\nBitte zuerst mit Strg + N oder Strg + O "
            "eine .md-Datei anlegen oder öffnen.",
        )
        return False

    def insert_image_dialog(self, align: str = "center") -> None:
        if not self._require_file():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Bild einfügen",
            self._start_dir(),
            "Bilder (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp);;Alle Dateien (*)",
        )
        for p in paths:
            target = images.copy_file(self.file.path, Path(p))
            if target:
                self._insert_saved(target, align)

    def _insert_saved(self, target: Path, align: str, point: QPoint | None = None) -> None:
        src = images.rel_src(self.file.path, target)
        width = "" if align == "center" else "40%"
        pos = {"x": point.x(), "y": point.y()} if point is not None else None
        self.view.call("insertImage", src, align, width, pos)
        self.view.setFocus()

    def paste(self) -> None:
        # Strg+V ist anwendungsweit belegt: ausserhalb des Markdown-Editors
        # (Text-Tab, PDF-Suche, Dialogfelder) einfach dort einfuegen.
        focus = QApplication.focusWidget()
        in_editor = self._md is not None and focus is not None and \
            (focus is self._md.view or self._md.view.isAncestorOf(focus))
        if not in_editor:
            if focus is not None and hasattr(focus, "paste"):
                focus.paste()
            return
        if self._paste_image(self._md):
            return
        # Kein Bild: normales Einfuegen im Editor
        self.view.page().triggerAction(QWebEnginePage.WebAction.Paste)

    def _paste_image(self, tab: MdTab | None) -> bool:
        """Bild(er) aus der Zwischenablage nach images/ legen und einfuegen."""
        mime = QGuiApplication.clipboard().mimeData()
        if tab is None or mime is None or not images.mime_has_image(mime):
            return False
        if tab is not self._md:
            self.tabs.setCurrentWidget(tab)
        if not self._require_file():
            return True
        saved = images.from_mime(self.file.path, mime, stem=self.file.path.stem)
        if not saved:
            self.statusBar().showMessage("Das Bild in der Zwischenablage ließ sich nicht lesen.", 6000)
            return True
        for target in saved:
            self._insert_saved(target, "center")
        self.statusBar().showMessage(f"{len(saved)} Bild(er) in images/ abgelegt", 4000)
        return True

    def _on_images_dropped(self, mime, pos: QPoint) -> None:
        if not self._require_file():
            return
        saved = images.from_mime(self.file.path, mime, stem=self.file.path.stem)
        if not saved:
            return
        for i, target in enumerate(saved):
            self._insert_saved(target, "center", pos if i == 0 else None)
        self.statusBar().showMessage(f"{len(saved)} Bild(er) in images/ abgelegt", 4000)

    def _on_markdown_dropped(self, paths: list) -> None:
        if paths:
            self.open_file(paths[0])

    # ------------------------------------------------------------------ #
    # Darstellung
    # ------------------------------------------------------------------ #

    def toggle_theme(self) -> None:
        self.theme = "light" if self.theme == "dark" else "dark"
        self._apply_theme()
        for tab in self.all_tabs():
            if isinstance(tab, MdTab):
                tab.view.call("setTheme", self.theme)
        self._save_settings()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.palette_for(self.theme))
            app.setStyleSheet(theme.STYLESHEET)
        if hasattr(self, "a_theme"):
            self.a_theme.setText("☀ Hell" if self.theme == "dark" else "☾ Dunkel")

    # ------------------------------------------------------------------ #
    # CompletionistPDF
    # ------------------------------------------------------------------ #

    def open_in_pdf(self) -> None:
        if self.file is None or self.file.path is None:
            QMessageBox.information(self, APP_TITLE, "Erst eine Datei öffnen.")
            return
        self._launch_pdf(self.file.path)

    def hand_off(self, app: str, path: str) -> None:
        """Datei aus dem Vault-Explorer an eine andere Suite-App uebergeben."""
        if app == "CompletionistPDF":
            self._launch_pdf(Path(path))
            return
        from core.qr_launcher import SUITE_KEY, find_app_exe

        # Erst der Suite-Schluessel in der Registry, dann die ueblichen Orte
        home = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else self.app_dir
        exe = find_app_exe(home, app)
        if exe is None:
            QMessageBox.warning(
                self, APP_TITLE,
                f"{app} wurde nicht gefunden.\nDer Programmpfad wird in der Registry "
                f"unter HKCU\\{SUITE_KEY}\\{app} (Wert „InstallPath“) oder in einer "
                "Installation (Setup) erwartet.",
            )
            return
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) if sys.platform == "win32" else 0
            subprocess.Popen([str(exe), str(Path(path))], cwd=str(Path(path).parent),
                             creationflags=flags, close_fds=True)
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Start fehlgeschlagen:\n{exc}")
            return
        self.statusBar().showMessage(f"An {app} übergeben", 4000)

    def _launch_pdf(self, md_path: Path) -> None:
        # Offene Datei erst speichern, damit CompletionistPDF den aktuellen Stand sieht
        tab = self.find_tab(md_path)
        if isinstance(tab, MdTab):
            self._flush_save(tab)
        command = self._pdf_command(md_path)
        if command is None:
            QMessageBox.warning(
                self,
                APP_TITLE,
                "CompletionistPDF wurde nicht gefunden.\nErwartet wird "
                "CompletionistPDF.exe im selben Ordner wie dieses Programm, "
                "ein Ordner CompletionistPDF daneben oder eine Installation (Setup)"
                + ("" if getattr(sys, "frozen", False) else f" oder main.py in {self.app_dir}")
                + ".",
            )
            return
        try:
            flags = 0
            if sys.platform == "win32":
                flags = getattr(subprocess, "DETACHED_PROCESS", 0)
            # cwd = Dokumentordner: der temporaere Entpackordner der .exe
            # verschwindet, sobald CompletionistMD beendet wird.
            subprocess.Popen(command, cwd=str(md_path.parent), creationflags=flags,
                             close_fds=True)
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, f"Start fehlgeschlagen:\n{exc}")
            return
        self.statusBar().showMessage("An CompletionistPDF übergeben", 4000)

    def open_qr(self) -> None:
        from core.qr_launcher import launch

        error = launch(self.app_dir)
        if error:
            QMessageBox.warning(self, APP_TITLE, error)
            return
        self.statusBar().showMessage("CompletionistQR gestartet", 4000)

    def _pdf_command(self, md_path: Path) -> list[str] | None:
        frozen = getattr(sys, "frozen", False)
        # Als .exe zeigt app_dir auf den temporaeren Entpackordner -- gesucht
        # wird dann neben der CompletionistMD.exe selbst.
        home = Path(sys.executable).resolve().parent if frozen else self.app_dir
        # Neben der eigenen .exe, in dist/ oder dort, wo das Setup CompletionistPDF
        # installiert hat (eigener Programmordner).
        from core.qr_launcher import find_app_exe

        exe = find_app_exe(home, "CompletionistPDF")
        if exe is not None:
            return [str(exe), str(md_path)]
        script = self.app_dir / "main.py"
        if not frozen and script.is_file():
            python = Path(sys.executable)
            # pythonw.exe: kein Konsolenfenster hinter der GUI
            windowed = python.with_name("pythonw.exe")
            if windowed.is_file():
                python = windowed
            return [str(python), str(script), str(md_path)]
        return None

    # ------------------------------------------------------------------ #

    def closeEvent(self, event) -> None:  # noqa: N802
        for tab in self.all_tabs():
            if isinstance(tab, MdTab):
                self._flush_save(tab)
            else:
                tab.flush()
        self._save_settings()
        self.gdrive.shutdown()
        super().closeEvent(event)
