"""QWebEngineView mit dem lokalen Editor-Bundle aus ``assets/editor``.

Bruecke JS -> Python
-------------------
Statt QWebChannel (dessen ``qwebchannel.js`` nur als Qt-Ressource existiert und
von einer ``file://``-Seite nicht geladen werden darf) nutzt der Editor den
Konsolenkanal: ``console.log("@@CM@@" + JSON.stringify(...))``. Hier wird die
Zeile abgefangen und als Signal weitergegeben.

Gross ist nur der Dokumentinhalt, und der fliesst in die andere Richtung --
Python fragt ihn per ``runJavaScript`` ab, wenn der Debounce zuschlaegt. Durch
die Konsole gehen also ausschliesslich kurze Meldungen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

from . import images

BRIDGE_PREFIX = "@@CM@@"


class EditorPage(QWebEnginePage):
    """Seite, die Bruecken-Meldungen aussortiert und Links extern oeffnet."""

    command = Signal(dict)

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        if message.startswith(BRIDGE_PREFIX):
            payload = message[len(BRIDGE_PREFIX):]
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"[CompletionistMD] defekte Bruecken-Meldung: {payload[:200]}", file=sys.stderr)
                return
            if isinstance(data, dict):
                self.command.emit(data)
            return
        # Alles andere ist Diagnose und soll im Terminal sichtbar sein.
        print(f"[editor:{line}] {message}", file=sys.stderr)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame) -> bool:  # noqa: N802
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class EditorView(QWebEngineView):
    """Der Editor als Widget. Drag & Drop wird auf Qt-Ebene abgefangen."""

    imagesDropped = Signal(object, QPoint)  # QMimeData, Position im Widget
    markdownDropped = Signal(list)

    def __init__(self, editor_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor_dir = Path(editor_dir)

        self._page = EditorPage(self)
        self.setPage(self._page)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, False)

        # Der Drop landet in einem internen Kindwidget von QWebEngineView; der
        # Filter sitzt deshalb auf jedem Kindwidget (siehe childEvent). Kein
        # Anwendungsfilter: Der zwang PySide, fuer jedes interne QtQuick-Objekt
        # von QtWebEngine einen Python-Wrapper zu bauen, was erneut Events
        # ausloest -- Endlosschleife und Absturz.
        self.installEventFilter(self)

    def childEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        super().childEvent(event)
        # ChildPolished statt ChildAdded: erst dann ist das Kindwidget fertig gebaut
        if event.type() == event.Type.ChildPolished:
            child = event.child()
            if isinstance(child, QWidget):
                for w in (child, *child.findChildren(QWidget)):
                    w.installEventFilter(self)  # doppeltes Installieren ist harmlos

    # ------------------------------------------------------------------ #

    @property
    def bridge(self) -> EditorPage:
        return self._page

    def load_editor(self) -> None:
        index = self.editor_dir / "index.html"
        self.load(QUrl.fromLocalFile(str(index)))

    def run(self, script: str, callback=None) -> None:
        if callback is None:
            self._page.runJavaScript(script)
            return
        # Ergebnisse als JSON uebergeben: PySide6 wandelt JS-Objekte und
        # -Arrays sonst nicht verlaesslich in dict/list um.
        def done(raw, cb=callback):
            try:
                cb(json.loads(raw) if isinstance(raw, str) else None)
            except json.JSONDecodeError:
                cb(None)
        self._page.runJavaScript(f"JSON.stringify(({script}))", 0, done)

    def call(self, name: str, *args, callback=None) -> None:
        """``CM.<name>(...)`` mit JSON-serialisierten Argumenten aufrufen."""
        arglist = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        self.run(f"CM.{name}({arglist})", callback)

    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event):  # noqa: N802
        kind = event.type()
        if kind not in (
            event.Type.DragEnter,
            event.Type.DragMove,
            event.Type.Drop,
        ):
            return super().eventFilter(obj, event)
        if not isinstance(obj, QWidget) or not (obj is self or self.isAncestorOf(obj)):
            return super().eventFilter(obj, event)

        mime = event.mimeData()
        md_files = images.markdown_urls(mime)
        has_image = images.mime_has_image(mime)
        if not (md_files or has_image):
            return super().eventFilter(obj, event)

        if kind in (event.Type.DragEnter, event.Type.DragMove):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return True

        # Drop -- Position in Koordinaten des Editor-Widgets umrechnen.
        pos = event.position().toPoint()
        local = obj.mapTo(self, pos) if obj is not self else pos
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if md_files:
            self.markdownDropped.emit(md_files)
        else:
            # Die Drop-Daten gehoeren dem Event; eine Kopie ueberlebt es.
            # Die Referenz bleibt am Objekt, damit sie nicht sofort eingesammelt wird.
            self._dropped = _clone_mime(mime)
            self.imagesDropped.emit(self._dropped, local)
        return True


def _clone_mime(mime: QMimeData) -> QMimeData:
    copy = QMimeData()
    for fmt in mime.formats():
        copy.setData(fmt, mime.data(fmt))
    if mime.hasUrls():
        copy.setUrls(mime.urls())
    if mime.hasImage():
        copy.setImageData(mime.imageData())
    return copy
