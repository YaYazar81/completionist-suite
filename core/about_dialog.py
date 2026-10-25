"""Dialog "Über …" fuer CompletionistPDF und CompletionistMD (Qt)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from . import legal


class AboutDialog(QDialog):
    IMAGE_SIZE = 300  # Kantenlaenge des App-Bildes links neben den Reitern

    def __init__(self, app_name: str, version: str, description: str,
                 icon: QIcon | None = None, parent=None, image: Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Über {app_name}")
        self.resize(980, 600)

        head = QHBoxLayout()
        if icon is not None and not icon.isNull():
            pic = QLabel(self)
            pic.setPixmap(icon.pixmap(64, 64))
            head.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        title = QLabel(
            f"<h2 style='margin:0'>{app_name}</h2>"
            f"<p style='margin:2px 0'>Version {version}</p>"
            f"<p style='margin:2px 0'>{description}</p>"
            f"<p style='margin:6px 0 0'>{legal.COPYRIGHT}<br>"
            f"Kontakt: <a href='mailto:{legal.CONTACT}'>{legal.CONTACT}</a></p>", self)
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setOpenExternalLinks(True)
        head.addWidget(title, 1)

        tabs = QTabWidget(self)
        lic = QTextBrowser(self)
        lic.setOpenExternalLinks(True)
        folder = legal.licenses_dir()
        folder_html = (f"<p>Die vollständigen Lizenztexte liegen im Programmordner: "
                       f"<a href='file:///{folder.as_posix()}'>{folder}</a></p>" if folder else "")
        lic.setHtml(
            f"<h3>Lizenz</h3><p>{legal.LICENSE_SUMMARY}</p>"
            f"<p><a href='{legal.LICENSE_URL}'>{legal.LICENSE_URL}</a></p>"
            f"<h3>Qt und PySide6 (LGPL v3)</h3><p>{legal.lgpl_notice()}</p>{folder_html}")
        tabs.addTab(lic, "Lizenz")
        notes = QTextBrowser(self)
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(legal.notices_text())
        tabs.addTab(notes, "Fremdkomponenten")
        imprint = QTextBrowser(self)
        imprint.setOpenExternalLinks(True)
        imprint.setHtml(legal.impressum_html())
        tabs.addTab(imprint, "Impressum")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        if folder:
            open_b = buttons.addButton("Lizenzordner öffnen", QDialogButtonBox.ButtonRole.ActionRole)
            open_b.clicked.connect(lambda: os.startfile(str(folder)))  # type: ignore[attr-defined]
        buttons.rejected.connect(self.reject)

        right = QVBoxLayout()
        right.addLayout(head)
        right.addWidget(tabs, 1)
        body = QHBoxLayout()
        # Das App-Bild steht links neben den Reitern und bleibt bei jedem Reiter sichtbar
        pix = QPixmap(str(image)) if image is not None else QPixmap()
        if not pix.isNull():
            dpr = self.devicePixelRatioF()
            side = round(self.IMAGE_SIZE * dpr)
            pix = pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            art = QLabel(self)
            art.setPixmap(pix)
            body.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(right, 1)

        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(buttons)
