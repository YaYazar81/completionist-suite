"""Einstellungen von CompletionistMD: Vault-Verzeichnis, Bookmarks, Google Drive."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .gdrive import DEFAULT_FOLDER, settings_with_defaults
from .vault import BookmarkDialog


class SettingsDialog(QDialog):
    def __init__(self, parent=None, vault: str = "", bookmarks: list | None = None,
                 gdrive: dict | None = None, sync=None, start_tab: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.resize(640, 500)
        self._sync = sync  # GDriveSync (fuer Verknuepfen/Trennen), optional

        # --- Vault ---
        self.vault_edit = QLineEdit(vault, self)
        self.vault_edit.setPlaceholderText(r"z. B. G:\Mein Vault")
        browse = QPushButton("Ordner wählen …", self)
        browse.clicked.connect(self._browse_vault)
        row = QHBoxLayout()
        row.addWidget(self.vault_edit, 1)
        row.addWidget(browse)
        vault_box = QGroupBox("Vault-Verzeichnis", self)
        vb = QVBoxLayout(vault_box)
        vb.addLayout(row)
        hint = QLabel(
            "Die linke Seitenleiste (Strg + Shift + E) zeigt diesen Ordner beim Start als "
            "Verzeichnisbaum.",
            self,
        )
        hint.setWordWrap(True)
        vb.addWidget(hint)

        # --- Bookmarks ---
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Anzeigename", "Zielpfad"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        for bm in bookmarks or []:
            self._append(bm)

        buttons = QVBoxLayout()
        for text, slot in (
            ("Neu …", self._add),
            ("Bearbeiten …", self._edit),
            ("Entfernen", self._remove),
            (None, None),
            ("Nach oben", lambda: self._move(-1)),
            ("Nach unten", lambda: self._move(1)),
        ):
            if text is None:
                buttons.addSpacing(10)
                continue
            b = QPushButton(text, self)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        table_row = QHBoxLayout()
        table_row.addWidget(self.table, 1)
        table_row.addLayout(buttons)
        bm_box = QGroupBox("Bookmarks (Schnellzugriff unten in der Seitenleiste)", self)
        bb = QVBoxLayout(bm_box)
        bb.addLayout(table_row)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        general = QWidget(self)
        gl = QVBoxLayout(general)
        gl.addWidget(vault_box)
        gl.addWidget(bm_box, 1)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(general, "Vault && Bookmarks")
        self.tabs.addTab(self._build_gdrive(settings_with_defaults(gdrive)), "Google Drive")
        if start_tab == "gdrive":
            self.tabs.setCurrentIndex(1)

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(box)

    # ------------------------------------------------------------------ #
    # Google Drive
    # ------------------------------------------------------------------ #

    def _build_gdrive(self, cfg: dict) -> QWidget:
        page = QWidget(self)
        self.gd_enabled = QCheckBox("Google-Drive-Sync aktivieren", page)
        self.gd_enabled.setChecked(bool(cfg["enabled"]))

        self.gd_source = QLineEdit(cfg["source"], page)
        self.gd_source.setPlaceholderText("leer = Vault-Verzeichnis")
        src_browse = QPushButton("Ordner wählen …", page)
        src_browse.clicked.connect(self._browse_source)
        src_row = QHBoxLayout()
        src_row.addWidget(self.gd_source, 1)
        src_row.addWidget(src_browse)

        self.gd_folder = QLineEdit(cfg["folder"], page)
        self.gd_folder.setPlaceholderText(DEFAULT_FOLDER)

        self.gd_on_save = QCheckBox("Bei Speichern / Auto-Save (nach 5 Sekunden Ruhe)", page)
        self.gd_on_save.setChecked(bool(cfg["on_save"]))
        self.gd_periodic = QCheckBox("Periodisch alle", page)
        self.gd_periodic.setChecked(bool(cfg["periodic"]))
        self.gd_interval = QSpinBox(page)
        self.gd_interval.setRange(1, 1440)
        self.gd_interval.setSuffix(" Minuten")
        self.gd_interval.setValue(int(cfg["interval_min"]))
        self.gd_interval.setEnabled(self.gd_periodic.isChecked())
        self.gd_periodic.toggled.connect(self.gd_interval.setEnabled)
        per_row = QHBoxLayout()
        per_row.addWidget(self.gd_periodic)
        per_row.addWidget(self.gd_interval)
        per_row.addStretch(1)

        form = QFormLayout()
        form.addRow("Lokaler Quell-Pfad:", src_row)
        form.addRow("Ziel-Ordner in Drive:", self.gd_folder)
        trig = QVBoxLayout()
        trig.addWidget(self.gd_on_save)
        trig.addLayout(per_row)
        form.addRow("Sync-Trigger:", trig)

        # --- Konto ---
        self.gd_account = QLabel(page)
        self.gd_account.setWordWrap(True)
        self.gd_link = QPushButton("Google Account verknüpfen", page)
        self.gd_link.clicked.connect(self._link)
        self.gd_unlink = QPushButton("Trennen", page)
        self.gd_unlink.clicked.connect(self._unlink)
        self.gd_client = QPushButton("client_secret.json …", page)
        self.gd_client.setToolTip("OAuth-Client (Typ „Desktop-App“) aus der Google Cloud Console")
        self.gd_client.clicked.connect(self._import_client)
        acc_row = QHBoxLayout()
        acc_row.addWidget(self.gd_link)
        acc_row.addWidget(self.gd_unlink)
        acc_row.addStretch(1)
        acc_row.addWidget(self.gd_client)
        acc_box = QGroupBox("Google-Konto", page)
        ab = QVBoxLayout(acc_box)
        ab.addWidget(self.gd_account)
        ab.addLayout(acc_row)

        hint = QLabel(
            "Hochgeladen werden nur neue oder geänderte Dateien: Notizen (.md, .txt), PDFs, "
            "Bilder (.png, .jpg, .gif) und Office-Dateien (Word, Excel, PowerPoint, "
            "LibreOffice/OpenOffice …); versteckte Ordner wie .obsidian bleiben außen vor. Bei "
            "Abweichungen gewinnt die lokale Fassung. In Drive wird nie etwas gelöscht. Ein Klick "
            "auf die Anzeige unten rechts startet den Abgleich sofort; jeder Lauf steht im "
            "Protokoll gdrive.log neben den Zugangsdaten.",
            page,
        )
        hint.setWordWrap(True)
        hint.setObjectName("vaultHint")

        lay = QVBoxLayout(page)
        lay.addWidget(self.gd_enabled)
        lay.addLayout(form)
        lay.addWidget(acc_box)
        lay.addWidget(hint)
        lay.addStretch(1)

        if self._sync is not None:
            self._sync.linkFinished.connect(self._on_linked)
        self._update_account()
        return page

    def _browse_source(self) -> None:
        start = self.gd_source.text() or self.vault_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Quellordner wählen", start)
        if path:
            self.gd_source.setText(str(Path(path)))

    def _update_account(self, busy: bool = False) -> None:
        if self._sync is None:
            self.gd_account.setText("Nicht verfügbar.")
            for b in (self.gd_link, self.gd_unlink, self.gd_client):
                b.setEnabled(False)
            return
        store = self._sync.store
        has_client = store.client_config() is not None
        linked = store.has_token()
        if busy:
            text = ("Browser geöffnet – bitte dort bei Google anmelden und den Zugriff erlauben. "
                    "(Wartet bis zu 5 Minuten.)")
        elif linked:
            text = "✔ Verknüpft. Die Anmeldung wird automatisch erneuert."
        elif has_client:
            text = "Noch nicht verknüpft."
        else:
            text = ("Zuerst die OAuth-Client-Datei hinterlegen: Google Cloud Console → Drive API "
                    "aktivieren → Anmeldedaten → OAuth-Client-ID vom Typ „Desktop-App“ → JSON "
                    "herunterladen → „client_secret.json …“.")
        self.gd_account.setText(text)
        self.gd_link.setText("Erneut verknüpfen" if linked else "Google Account verknüpfen")
        self.gd_link.setEnabled(has_client and not busy)
        self.gd_unlink.setEnabled(linked and not busy)
        self.gd_client.setEnabled(not busy)

    def _import_client(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "OAuth-Client-Datei wählen", str(Path.home() / "Downloads"), "JSON (*.json)"
        )
        if not path:
            return
        try:
            self._sync.store.import_client_config(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Google Drive", str(exc))
            return
        self._update_account()

    def _link(self) -> None:
        self._update_account(busy=True)
        self._sync.link_account()

    def _on_linked(self, ok: bool, message: str) -> None:
        self._update_account()
        if ok:
            self.gd_enabled.setChecked(True)
        else:
            QMessageBox.warning(self, "Google Drive", f"Verknüpfen fehlgeschlagen:\n{message}")

    def _unlink(self) -> None:
        if QMessageBox.question(
            self, "Google Drive",
            "Verknüpfung lösen? Das gespeicherte Token wird gelöscht; die Dateien in Drive bleiben.",
        ) == QMessageBox.StandardButton.Yes:
            self._sync.unlink()
            self._update_account()

    def done(self, result: int) -> None:  # noqa: D401 - Signal beim Schliessen trennen
        if self._sync is not None:
            try:
                self._sync.linkFinished.disconnect(self._on_linked)
            except TypeError:
                pass
        super().done(result)

    def gdrive_settings(self) -> dict:
        return settings_with_defaults({
            "enabled": self.gd_enabled.isChecked(),
            "source": str(Path(self.gd_source.text().strip())) if self.gd_source.text().strip() else "",
            "folder": self.gd_folder.text().strip() or DEFAULT_FOLDER,
            "on_save": self.gd_on_save.isChecked(),
            "periodic": self.gd_periodic.isChecked(),
            "interval_min": self.gd_interval.value(),
        })

    # ------------------------------------------------------------------ #

    def _browse_vault(self) -> None:
        start = self.vault_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Vault-Verzeichnis wählen", start)
        if path:
            self.vault_edit.setText(str(Path(path)))

    def _append(self, bm: dict, row: int | None = None) -> None:
        row = self.table.rowCount() if row is None else row
        self.table.insertRow(row)
        self._set_row(row, bm)

    def _set_row(self, row: int, bm: dict) -> None:
        self.table.setItem(row, 0, QTableWidgetItem(bm.get("name", "")))
        self.table.setItem(row, 1, QTableWidgetItem(bm.get("path", "")))

    def _row_value(self, row: int) -> dict:
        return {"name": self.table.item(row, 0).text(), "path": self.table.item(row, 1).text()}

    def _add(self) -> None:
        dlg = BookmarkDialog(self, start_dir=self.vault_edit.text())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._append(dlg.value())
            self.table.selectRow(self.table.rowCount() - 1)

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        bm = self._row_value(row)
        dlg = BookmarkDialog(self, name=bm["name"], path=bm["path"], start_dir=self.vault_edit.text())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._set_row(row, dlg.value())

    def _remove(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _move(self, delta: int) -> None:
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        a, b = self._row_value(row), self._row_value(target)
        self._set_row(row, b)
        self._set_row(target, a)
        self.table.selectRow(target)

    # ------------------------------------------------------------------ #

    def vault(self) -> str:
        text = self.vault_edit.text().strip()
        return str(Path(text)) if text else ""

    def bookmarks(self) -> list[dict]:
        return [self._row_value(r) for r in range(self.table.rowCount())]
