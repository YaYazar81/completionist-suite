"""Linke Seitenleiste: Verzeichnisbaum des Vaults und Bookmarks.

Oben ein ``QTreeView`` auf ``QFileSystemModel`` (Ordner, Markdown, PDF, Text,
Bilder -- je mit farbigem Dateityp-Icon),
darunter ein fester Block mit Bookmark-Kacheln. Ein Klick auf eine Kachel
klappt den Baum bis zum Zielordner auf.

Die Leiste selbst kennt keine Einstellungsdatei: Vault-Pfad und Bookmarks
setzt das Hauptfenster (``set_root`` / ``set_bookmarks``), Aenderungen meldet
die Leiste ueber ``bookmarksChanged`` zurueck.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (
    QDir,
    QFile,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileSystemModel,  # bei PySide6 in QtWidgets (PyQt6: QtGui)
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

MD_SUFFIXES = (".md", ".markdown")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
TAB_SUFFIXES = MD_SUFFIXES + (".txt", ".pdf") + IMAGE_SUFFIXES  # im Editor als Tab darstellbar
# Nur Ordner und diese Dateien zeigt der Baum -- .bak, .tmp, .json usw. bleiben
# als Werkstatt-Reste unsichtbar.
NAME_FILTERS = ["*.md", "*.pdf", "*.txt", "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg"]


def is_markdown(path: str | Path) -> bool:
    return str(path).lower().endswith(MD_SUFFIXES)


def is_image(path: str | Path) -> bool:
    return str(path).lower().endswith(IMAGE_SUFFIXES)


def is_inside(path: str | Path, folder: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (ValueError, OSError):
        return False


def reveal_in_explorer(path: str | Path) -> None:
    path = Path(path)
    if sys.platform == "win32":
        if path.is_dir():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))


# ---------------------------------------------------------------------- #
# Kacheln im Fliesslayout
# ---------------------------------------------------------------------- #


class FlowLayout(QLayout):
    """Ordnet Widgets zeilenweise an und bricht um (Qt-Beispiel, gekuerzt)."""

    def __init__(self, parent=None, spacing: int = 4) -> None:
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect: QRect, dry: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        gap = self.spacing()
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() and line_h > 0:
                x = rect.x()
                y += line_h + gap
                line_h = 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + gap
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


# ---------------------------------------------------------------------- #
# Bookmark bearbeiten
# ---------------------------------------------------------------------- #


class BookmarkDialog(QDialog):
    """Anzeigename + Zielordner."""

    def __init__(self, parent=None, name: str = "", path: str = "", start_dir: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Bookmark")
        self._start = start_dir
        self.name_edit = QLineEdit(name, self)
        self.name_edit.setPlaceholderText("z. B. The Completionist Library")
        self.path_edit = QLineEdit(path, self)
        self.path_edit.setMinimumWidth(320)
        browse = QPushButton("…", self)
        browse.setFixedWidth(32)
        browse.setToolTip("Zielordner wählen")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Anzeigename:", self.name_edit)
        form.addRow("Zielpfad:", row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        start = self.path_edit.text() or self._start or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Zielordner wählen", start)
        if path:
            self.path_edit.setText(str(Path(path)))
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).name)

    def _accept(self) -> None:
        if not Path(self.path_edit.text().strip()).is_dir():
            QMessageBox.warning(self, "Bookmark", "Der Zielpfad ist kein vorhandener Ordner.")
            return
        if not self.name_edit.text().strip():
            self.name_edit.setText(Path(self.path_edit.text().strip()).name)
        self.accept()

    def value(self) -> dict:
        return {"name": self.name_edit.text().strip(), "path": str(Path(self.path_edit.text().strip()))}


# ---------------------------------------------------------------------- #
# Dateityp-Icons
# ---------------------------------------------------------------------- #

# Suite-Icons (128 px) in assets/filetypes: md blau, pdf rot, img violett, txt grau
ICON_KINDS = ("md", "pdf", "img", "txt")
ICON_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "filetypes"


def _make_icon(kind: str) -> QIcon:
    """Icon aus assets/filetypes, fuer die gaengigen Baumgroessen vorab
    weich herunterskaliert (Qt skaliert sonst grob)."""
    icon = QIcon()
    source = QPixmap(str(ICON_DIR / f"{kind}.png"))
    if source.isNull():
        return icon
    for size in (16, 20, 24, 32, 48, 64, 128):
        icon.addPixmap(source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
    return icon


class FileTypeIcons:
    """Suite-Icon je Dateiendung; Ordner behalten das System-Icon.

    Bewusst kein eigener ``QFileIconProvider``: ``QFileSystemModel`` fragt den
    Provider auch aus seinem Hintergrund-Thread ab, Pixmaps gehoeren aber in den
    GUI-Thread. Die Icons liefert deshalb der Proxy (``_HideDotFiles.data``).
    """

    def __init__(self) -> None:
        loaded = {kind: _make_icon(kind) for kind in ICON_KINDS}
        # Fehlt eine Datei, bleibt es beim System-Icon
        self._icons = {k: v for k, v in loaded.items() if not v.isNull()}

    def icon_for(self, path: str) -> QIcon | None:
        p = path.lower()
        if p.endswith(MD_SUFFIXES):
            kind = "md"
        elif p.endswith(".pdf"):
            kind = "pdf"
        elif p.endswith(IMAGE_SUFFIXES):
            kind = "img"
        elif p.endswith(".txt"):
            kind = "txt"
        else:
            return None
        return self._icons.get(kind)


# ---------------------------------------------------------------------- #
# Filter: versteckte Ordner (.obsidian, .trash, .git) ausblenden
# ---------------------------------------------------------------------- #


class _HideDotFiles(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.icons = FileTypeIcons()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            src = self.mapToSource(index)
            if not self.sourceModel().isDir(src):
                icon = self.icons.icon_for(self.sourceModel().fileName(src))
                if icon is not None:
                    return icon
        return super().data(index, role)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        idx = self.sourceModel().index(row, 0, parent)
        return not self.sourceModel().fileName(idx).startswith(".")

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        # Ordner zuerst, dann alphabetisch ohne Gross/Klein
        src = self.sourceModel()
        ld, rd = src.isDir(left), src.isDir(right)
        if ld != rd:
            return ld
        return src.fileName(left).lower() < src.fileName(right).lower()


# ---------------------------------------------------------------------- #


class VaultPanel(QWidget):
    """Verzeichnisbaum + Bookmarks."""

    openFile = Signal(str)               # Einfachklick: im aktiven Editor-Tab
    openInNewTab = Signal(str)           # Doppelklick: neuer Tab
    bookmarksChanged = Signal(list)
    aboutToChange = Signal(str)          # Pfad wird gleich umbenannt/geloescht
    pathRenamed = Signal(str, str)       # alt, neu
    pathRemoved = Signal(str)
    settingsRequested = Signal()
    handoffRequested = Signal(str, str)  # Suite-App ("CompletionistPDF" ...), Datei
    mergeRequested = Signal(list)        # mehrere .md (Strg/Umschalt+Klick) zusammenfuehren

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("vaultPanel")
        self.setMinimumWidth(170)
        self._root = ""
        self._vault = ""
        self._bookmarks: list[dict] = []
        self._click_path = ""
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._emit_click)

        # --- Kopf ---
        self.title = QLabel("Vault", self)
        self.title.setObjectName("vaultTitle")
        self.home_button = QToolButton(self)
        self.home_button.setText("⌂")
        self.home_button.setToolTip("Zurück zum Vault-Hauptverzeichnis")
        self.home_button.setAutoRaise(True)
        self.home_button.clicked.connect(lambda: self.set_root(self._vault, vault=True))
        self.collapse_button = QToolButton(self)
        self.collapse_button.setText("⇱")
        self.collapse_button.setToolTip("Alle Ordner einklappen")
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.clicked.connect(lambda: self.tree.collapseAll())
        head = QHBoxLayout()
        head.setContentsMargins(8, 4, 4, 2)
        head.addWidget(self.title, 1)
        head.addWidget(self.home_button)
        head.addWidget(self.collapse_button)

        # --- Baum ---
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilters(NAME_FILTERS)
        self.model.setNameFilterDisables(False)  # nicht passende Dateien ausblenden statt ausgrauen
        self.proxy = _HideDotFiles(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setDynamicSortFilter(True)

        self.tree = QTreeView(self)
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setAnimated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Strg/Umschalt+Klick waehlt mehrere Dateien (zum Zusammenfuehren)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        # Ordner klappen mit einem Klick auf und zu (siehe _on_clicked)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.clicked.connect(self._on_clicked)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        self.empty_hint = QLabel(
            "Kein Vault gewählt.\n\n⚙ Einstellungen → Vault-Verzeichnis", self
        )
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setObjectName("vaultHint")

        # --- Bookmarks ---
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("vaultLine")
        bm_title = QLabel("Bookmarks", self)
        bm_title.setObjectName("vaultTitle")
        add = QToolButton(self)
        add.setText("+")
        add.setToolTip("Bookmark hinzufügen")
        add.setAutoRaise(True)
        add.clicked.connect(lambda: self.add_bookmark())
        bm_head = QHBoxLayout()
        bm_head.setContentsMargins(8, 2, 4, 0)
        bm_head.addWidget(bm_title, 1)
        bm_head.addWidget(add)

        self.bm_box = QWidget(self)
        self.bm_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.bm_flow = FlowLayout(self.bm_box, spacing=4)
        self.bm_box.setContentsMargins(8, 2, 8, 8)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(head)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.empty_hint, 1)
        lay.addWidget(line)
        lay.addLayout(bm_head)
        lay.addWidget(self.bm_box)

        self._update_empty()

    # ------------------------------------------------------------------ #
    # Wurzel
    # ------------------------------------------------------------------ #

    def set_vault(self, path: str) -> None:
        self._vault = str(Path(path)) if path else ""
        self.set_root(self._vault, vault=True)

    def set_root(self, path: str, vault: bool = False) -> None:
        self._root = path if path and Path(path).is_dir() else ""
        if self._root:
            src = self.model.setRootPath(self._root)
            self.tree.setRootIndex(self.proxy.mapFromSource(src))
            name = Path(self._root).name or self._root
            self.title.setText(name if vault else f"{name}  (außerhalb)")
            self.title.setToolTip(self._root)
        else:
            self.title.setText("Vault")
            self.title.setToolTip("")
        self.home_button.setVisible(bool(self._vault) and not vault)
        self._update_empty()

    def _update_empty(self) -> None:
        has = bool(self._root)
        self.tree.setVisible(has)
        self.empty_hint.setVisible(not has)

    @property
    def vault(self) -> str:
        return self._vault

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _proxy_index(self, path: str) -> QModelIndex:
        return self.proxy.mapFromSource(self.model.index(str(Path(path))))

    def _path_of(self, index: QModelIndex) -> str:
        return self.model.filePath(self.proxy.mapToSource(index))

    def navigate_to(self, folder: str) -> None:
        """Baum bis ``folder`` aufklappen und dorthin rollen."""
        folder = str(Path(folder))
        if not Path(folder).is_dir():
            QMessageBox.warning(self, "Bookmark", f"Ordner nicht gefunden:\n{folder}")
            return
        if self._vault and is_inside(folder, self._vault):
            if self._root != self._vault:
                self.set_root(self._vault, vault=True)
        elif not (self._root and is_inside(folder, self._root)):
            self.set_root(folder)
        self.tree.collapseAll()
        # Vorfahren der Reihe nach aufklappen (QFileSystemModel laedt lazy).
        chain = []
        p = Path(folder)
        root = Path(self._root)
        while True:
            chain.append(p)
            if p == root or p.parent == p:
                break
            p = p.parent
        for anc in reversed(chain):
            idx = self._proxy_index(str(anc))
            if idx.isValid():
                self.tree.expand(idx)
        target = self._proxy_index(folder)
        if target.isValid():
            self.tree.setCurrentIndex(target)
            self.tree.scrollTo(target, QAbstractItemView.ScrollHint.PositionAtTop)

    def select_file(self, path: str) -> None:
        """Die geoeffnete Datei im Baum markieren (ohne etwas zu oeffnen)."""
        if not self._root or not is_inside(path, self._root):
            return
        idx = self._proxy_index(path)
        if idx.isValid():
            self.tree.setCurrentIndex(idx)
            self.tree.scrollTo(idx)

    # Einfachklick: .md im aktiven Editor-Tab, .txt/.pdf/Bilder im Vorschau-Tab
    # (den ersetzt der naechste Einfachklick), Ordner auf-/zuklappen.
    # Doppelklick: in einem neuen Tab. Der Einfachklick auf Dateien wartet
    # deshalb das Doppelklick-Intervall ab -- sonst wuerde ein Doppelklick erst
    # den aktiven Tab umstellen und dann noch einen neuen oeffnen.

    def _on_clicked(self, index: QModelIndex) -> None:
        mods = QApplication.keyboardModifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return  # Mehrfachauswahl, nichts oeffnen
        if self.model.isDir(self.proxy.mapToSource(index)):
            self.tree.setExpanded(index, not self.tree.isExpanded(index))
            return
        path = self._path_of(index)
        if path.lower().endswith(TAB_SUFFIXES) and Path(path).is_file():
            self._click_path = path
            self._click_timer.start(QApplication.styleHints().mouseDoubleClickInterval())

    def _emit_click(self) -> None:
        if self._click_path:
            path, self._click_path = self._click_path, ""
            self.openFile.emit(path)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        self._click_timer.stop()
        self._click_path = ""
        path = self._path_of(index)
        if not Path(path).is_file():
            return
        if path.lower().endswith(TAB_SUFFIXES):
            self.openInNewTab.emit(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------------ #
    # Kontextmenue des Baums
    # ------------------------------------------------------------------ #

    def selected_markdown(self) -> list[str]:
        """Markierte .md-Dateien in Baumreihenfolge."""
        rows = sorted(self.tree.selectionModel().selectedRows(0),
                      key=lambda i: self.tree.visualRect(i).top())
        paths = [self._path_of(i) for i in rows]
        return [p for p in paths if is_markdown(p) and Path(p).is_file()]

    def _tree_menu(self, pos: QPoint) -> None:
        menu = self.build_tree_menu(pos)
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def build_tree_menu(self, pos: QPoint) -> QMenu | None:
        if not self._root:
            return None
        index = self.tree.indexAt(pos)
        path = self._path_of(index) if index.isValid() else self._root
        is_dir = Path(path).is_dir()
        folder = path if is_dir else str(Path(path).parent)

        menu = QMenu(self)
        selected = self.selected_markdown()
        if len(selected) > 1 and path in selected:
            menu.addAction(f"{len(selected)} Dateien zusammenführen …",
                           lambda: self.mergeRequested.emit(selected))
            menu.addSeparator()
        if index.isValid() and not is_dir and path.lower().endswith(TAB_SUFFIXES):
            # "Öffnen": mit dem Standardprogramm des Systems (Bildbetrachter, PDF-Reader …)
            menu.addAction("Öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction("Hier öffnen", lambda: self.openFile.emit(path))
            menu.addAction("In neuem Tab öffnen", lambda: self.openInNewTab.emit(path))
            menu.addSeparator()
        # Uebergabe an die anderen Suite-Apps (Pfad kommt aus der Registry)
        if index.isValid() and not is_dir:
            if is_markdown(path):
                menu.addAction("► In PDF konvertieren …",
                               lambda: self.handoffRequested.emit("CompletionistPDF", path))
            elif is_image(path):
                menu.addAction("► In CompletionistIMG öffnen …",
                               lambda: self.handoffRequested.emit("CompletionistIMG", path))
            if not menu.isEmpty():
                menu.addSeparator()
        menu.addAction("Neue Datei erstellen …", lambda: self._new_file(folder))
        menu.addAction("Neuer Ordner …", lambda: self._new_folder(folder))
        menu.addSeparator()
        rename = menu.addAction("Umbenennen …", lambda: self._rename(path))
        delete = menu.addAction("Löschen", lambda: self._delete(path))
        if not index.isValid():
            rename.setEnabled(False)
            delete.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Im Windows Explorer anzeigen", lambda: reveal_in_explorer(path))
        if is_dir:
            menu.addAction("Als Bookmark hinzufügen …", lambda: self.add_bookmark(path))
        return menu

    def _ask_name(self, title: str, label: str, text: str = "") -> str | None:
        name, ok = QInputDialog.getText(self, title, label, QLineEdit.EchoMode.Normal, text)
        name = name.strip()
        if not ok or not name:
            return None
        if any(c in name for c in '<>:"/\\|?*'):
            QMessageBox.warning(self, title, 'Der Name darf keines dieser Zeichen enthalten:  < > : " / \\ | ? *')
            return None
        return name

    def _new_file(self, folder: str) -> None:
        name = self._ask_name("Neue Datei", "Dateiname:", "Neue Notiz")
        if not name:
            return
        if not is_markdown(name):
            name += ".md"
        target = Path(folder) / name
        if target.exists():
            QMessageBox.warning(self, "Neue Datei", f"„{name}“ gibt es dort schon.")
            return
        try:
            target.write_text(f"# {target.stem}\n\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Neue Datei", f"Datei konnte nicht angelegt werden:\n{exc}")
            return
        self.openFile.emit(str(target))
        self.select_file(str(target))

    def _new_folder(self, folder: str) -> None:
        name = self._ask_name("Neuer Ordner", "Ordnername:", "Neuer Ordner")
        if not name:
            return
        target = Path(folder) / name
        try:
            target.mkdir()
        except OSError as exc:
            QMessageBox.critical(self, "Neuer Ordner", f"Ordner konnte nicht angelegt werden:\n{exc}")
            return
        idx = self._proxy_index(folder)
        if idx.isValid():
            self.tree.expand(idx)

    def _rename(self, path: str) -> None:
        old = Path(path)
        name = self._ask_name("Umbenennen", "Neuer Name:", old.name)
        if not name or name == old.name:
            return
        if old.is_file() and is_markdown(old) and not is_markdown(name):
            name += old.suffix
        new = old.with_name(name)
        if new.exists() and new.resolve() != old.resolve():
            QMessageBox.warning(self, "Umbenennen", f"„{name}“ gibt es dort schon.")
            return
        self.aboutToChange.emit(str(old))
        try:
            old.rename(new)
        except OSError as exc:
            QMessageBox.critical(self, "Umbenennen", f"Umbenennen fehlgeschlagen:\n{exc}")
            return
        self.pathRenamed.emit(str(old), str(new))
        # Bookmarks auf den umbenannten Ordner mitziehen
        changed = False
        for bm in self._bookmarks:
            bp = Path(bm["path"])
            if bp == old or is_inside(bp, old):
                bm["path"] = str(new / bp.relative_to(old)) if bp != old else str(new)
                changed = True
        if changed:
            self._rebuild_bookmarks()
            self.bookmarksChanged.emit(self.bookmarks())

    def _delete(self, path: str) -> None:
        target = Path(path)
        kind = "den Ordner" if target.is_dir() else "die Datei"
        answer = QMessageBox.question(
            self,
            "Löschen",
            f"Soll {kind} „{target.name}“ in den Papierkorb verschoben werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.aboutToChange.emit(str(target))
        result = QFile.moveToTrash(str(target))  # PySide6: (ok, pfad_im_papierkorb)
        if not (result[0] if isinstance(result, tuple) else result):
            QMessageBox.critical(self, "Löschen", f"„{target.name}“ konnte nicht in den Papierkorb verschoben werden.")
            return
        self.pathRemoved.emit(str(target))

    # ------------------------------------------------------------------ #
    # Bookmarks
    # ------------------------------------------------------------------ #

    def bookmarks(self) -> list[dict]:
        return [dict(b) for b in self._bookmarks]

    def set_bookmarks(self, items: list) -> None:
        self._bookmarks = [
            {"name": str(b.get("name", "")), "path": str(b.get("path", ""))}
            for b in items
            if isinstance(b, dict) and b.get("path")
        ]
        self._rebuild_bookmarks()

    def _rebuild_bookmarks(self) -> None:
        while self.bm_flow.count():
            item = self.bm_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, bm in enumerate(self._bookmarks):
            b = QToolButton(self.bm_box)
            b.setObjectName("bookmarkTile")
            b.setText(bm["name"] or Path(bm["path"]).name)
            b.setToolTip(bm["path"])
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=bm["path"]: self.navigate_to(p))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, k=i, w=b: self._tile_menu(k, w, pos))
            self.bm_flow.addWidget(b)
        if not self._bookmarks:
            hint = QLabel("Noch keine – „+“ oder Rechtsklick auf einen Ordner.", self.bm_box)
            hint.setObjectName("vaultHint")
            hint.setWordWrap(True)
            self.bm_flow.addWidget(hint)
        self.bm_box.updateGeometry()

    def _tile_menu(self, k: int, widget: QWidget, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("Bearbeiten …", lambda: self._edit_bookmark(k))
        left = menu.addAction("Nach vorn", lambda: self._move_bookmark(k, -1))
        right = menu.addAction("Nach hinten", lambda: self._move_bookmark(k, 1))
        left.setEnabled(k > 0)
        right.setEnabled(k < len(self._bookmarks) - 1)
        menu.addSeparator()
        menu.addAction("Im Explorer anzeigen", lambda: reveal_in_explorer(self._bookmarks[k]["path"]))
        menu.addAction("Entfernen", lambda: self._remove_bookmark(k))
        menu.addSeparator()
        menu.addAction("Bookmarks verwalten …", self.settingsRequested.emit)
        menu.exec(widget.mapToGlobal(pos))

    def add_bookmark(self, path: str = "") -> None:
        dlg = BookmarkDialog(
            self, name=Path(path).name if path else "", path=path, start_dir=self._vault or self._root
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._bookmarks.append(dlg.value())
        self._rebuild_bookmarks()
        self.bookmarksChanged.emit(self.bookmarks())

    def _edit_bookmark(self, k: int) -> None:
        bm = self._bookmarks[k]
        dlg = BookmarkDialog(self, name=bm["name"], path=bm["path"], start_dir=self._vault)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._bookmarks[k] = dlg.value()
        self._rebuild_bookmarks()
        self.bookmarksChanged.emit(self.bookmarks())

    def _move_bookmark(self, k: int, delta: int) -> None:
        j = k + delta
        if 0 <= j < len(self._bookmarks):
            self._bookmarks[k], self._bookmarks[j] = self._bookmarks[j], self._bookmarks[k]
            self._rebuild_bookmarks()
            self.bookmarksChanged.emit(self.bookmarks())

    def _remove_bookmark(self, k: int) -> None:
        del self._bookmarks[k]
        self._rebuild_bookmarks()
        self.bookmarksChanged.emit(self.bookmarks())
