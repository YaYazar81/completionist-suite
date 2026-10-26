"""Text markieren und kopieren in einer ``QPdfView`` (Qt).

``QPdfView`` zeigt Seiten nur an; Auswahl, Hervorhebung und Strg+C ergaenzt
``PdfTextSelector``. Genutzt von allen PDF-Ansichten der Suite: Vorschau und
Reader in CompletionistPDF, PDF-Tab in CompletionistMD.

Ziehen mit der linken Maustaste markiert (auch ueber Seitengrenzen),
Doppelklick ein Wort, Dreifachklick eine Zeile, Strg+A alles,
Strg+C oder das Kontextmenue kopiert, Esc hebt die Auswahl auf.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QPolygonF, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QApplication, QMenu, QWidget
from shiboken6 import isValid

DRAG_SLOP = 4  # Pixel: weniger Bewegung ist ein Klick, keine Auswahl
SELECTION_COLOR = QColor(0, 120, 215, 90)


# ---------------------------------------------------------------------- #
# Seitengeometrie
# ---------------------------------------------------------------------- #


def page_rects(view: QPdfView, doc: QPdfDocument, *, scrolled: bool = True) -> list[QRect]:
    """Lage jeder Seite in Pixeln -- im Viewport (``scrolled``) oder im
    ganzen Dokument.

    QPdfView gibt seine Seitengeometrie nicht heraus. Die Rechnung bildet
    ``QPdfViewPrivate::calculateDocumentLayout`` (Qt 6.11) nach; ein Test
    vergleicht sie mit dem gerenderten Bild (tests/test_pdf_viewer.py).
    """
    vp = view.viewport().size()
    m = view.documentMargins()
    spacing = view.pageSpacing()
    mode = view.zoomMode()
    screen = QGuiApplication.primaryScreen()
    res = (screen.logicalDotsPerInch() if screen else 96.0) / 72.0

    sizes: list[QSize] = []
    for page in range(doc.pageCount()):
        pt = doc.pagePointSize(page)
        if mode == QPdfView.ZoomMode.Custom:
            size = QSizeF(pt.width() * res * view.zoomFactor(), pt.height() * res * view.zoomFactor()).toSize()
        else:
            size = QSizeF(pt.width() * res, pt.height() * res).toSize()
            if size.width() <= 0 or size.height() <= 0:
                sizes.append(QSize())
                continue
            if mode == QPdfView.ZoomMode.FitToWidth:
                size = size * ((vp.width() - m.left() - m.right()) / size.width())
            else:  # FitInView
                avail = QSize(vp.width() - m.left() - m.right(), vp.height() - spacing)
                size = size.scaled(avail, Qt.AspectRatioMode.KeepAspectRatio)
        sizes.append(size)

    total_w = max((s.width() for s in sizes), default=0) + m.left() + m.right()
    dx = view.horizontalScrollBar().value() if scrolled else 0
    dy = view.verticalScrollBar().value() if scrolled else 0
    rects: list[QRect] = []
    y = m.top()
    for size in sizes:
        x = (max(total_w, vp.width()) - size.width()) // 2
        rects.append(QRect(QPoint(x - dx, y - dy), size))
        y += size.height() + spacing
    return rects


def page_at(view: QPdfView, doc: QPdfDocument, pos: QPoint) -> tuple[int, QPointF] | None:
    """Seite und Stelle in PDF-Punkten unter ``pos`` (Viewport-Pixel)."""
    for page, rect in enumerate(page_rects(view, doc)):
        if rect.contains(pos):
            pt = doc.pagePointSize(page)
            if rect.width() <= 0 or rect.height() <= 0:
                return None
            return page, QPointF((pos.x() - rect.left()) * pt.width() / rect.width(),
                                 (pos.y() - rect.top()) * pt.height() / rect.height())
    return None


def nearest_page(view: QPdfView, doc: QPdfDocument, pos: QPoint) -> tuple[int, QPointF] | None:
    """Wie ``page_at``, aber ausserhalb der Seiten (Rand, Zwischenraum) die
    naechstgelegene Seite, mit der Stelle auf ihren Rand begrenzt -- so laeuft
    eine Auswahl beim Ziehen ueber den Seitenzwischenraum weiter."""
    rects = page_rects(view, doc)
    best = None
    for page, rect in enumerate(rects):
        if rect.width() <= 0 or rect.height() <= 0:
            continue
        dy = 0 if rect.top() <= pos.y() <= rect.bottom() else min(abs(pos.y() - rect.top()),
                                                                  abs(pos.y() - rect.bottom()))
        if best is None or dy < best[0]:
            best = (dy, page, rect)
    if best is None:
        return None
    _dy, page, rect = best
    pt = doc.pagePointSize(page)
    x = min(max(pos.x(), rect.left()), rect.right())
    y = min(max(pos.y(), rect.top()), rect.bottom())
    return page, QPointF((x - rect.left()) * pt.width() / rect.width(),
                         (y - rect.top()) * pt.height() / rect.height())


def _is_symbol(ch: str) -> bool:
    return unicodedata.category(ch) in ("So", "Sk") or ch in "\ufe0f\u200d"


def tidy_text(text: str) -> str:
    """Raeumt PDF-Text zum Kopieren auf: Silbentrennung ("Kon-" + Zeilenumbruch +
    "verter") wird wieder ein Wort; Emojis stehen im PDF als eigene Textlaeufe,
    die PDFium auf eigene Zeilen setzt -- sie kommen zurueck in ihren Satz."""
    text = re.sub(r"\n?\u00ad\n?", "", text)
    lines = text.split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        prev = out[-1]
        lone_punct = 0 < len(line.strip()) <= 2 and not any(c.isalnum() for c in line)
        if (line[:1] and _is_symbol(line[0])) or (prev[-1:] and _is_symbol(prev[-1])) or lone_punct:
            out[-1] = prev + line
        else:
            out.append(line)
    return "\n".join(out)


def _lines(boxes: list[QRectF]) -> list[QRectF]:
    """Fasst Textboxen (je nach PDF ganze Laeufe oder einzelne Glyphen) zu
    Zeilen zusammen: Boxen, die sich senkrecht zur Haelfte ueberlappen."""
    lines: list[QRectF] = []
    for b in sorted(boxes, key=lambda r: (r.center().y(), r.left())):
        if lines:
            last = lines[-1]
            overlap = min(last.bottom(), b.bottom()) - max(last.top(), b.top())
            if overlap >= 0.5 * min(last.height(), b.height()):
                lines[-1] = last.united(b)
                continue
        lines.append(QRectF(b))
    return lines


# ---------------------------------------------------------------------- #
# Auswahl
# ---------------------------------------------------------------------- #


class _Overlay(QWidget):
    """Durchsichtige Schicht ueber dem Viewport, zeichnet die Auswahl."""

    def __init__(self, selector: "PdfTextSelector", parent: QWidget) -> None:
        super().__init__(parent)
        self._sel = selector
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        parts = self._sel.parts
        if not parts:
            return
        rects = page_rects(self._sel.view, self._sel.doc)
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(SELECTION_COLOR)
        for page, selection in parts:
            if page >= len(rects):
                continue
            r = rects[page]
            pt = self._sel.doc.pagePointSize(page)
            if pt.width() <= 0 or pt.height() <= 0 or not r.intersects(self.rect()):
                continue
            sx, sy = r.width() / pt.width(), r.height() / pt.height()
            for poly in selection.bounds():
                p.drawPolygon(QPolygonF([QPointF(r.left() + q.x() * sx, r.top() + q.y() * sy) for q in poly]))
        p.end()


class PdfTextSelector(QObject):
    """Haengt Textauswahl an eine ``QPdfView``.

    ``document`` liefert das gerade angezeigte Dokument (manche Ansichten
    tauschen es beim Neuladen aus). ``link_at`` (optional) meldet einen Link
    unter einer Viewport-Position -- dort zeigt der Mauszeiger die Hand. Einem
    Link folgt die Ansicht selbst beim Klick; Ziehen markiert auch dort Text.
    """

    def __init__(self, view: QPdfView, document: Callable[[], QPdfDocument] | None = None,
                 link_at: Callable[[QPoint], object] | None = None) -> None:
        super().__init__(view)
        self.view = view
        self._document = document or view.document
        self._link_at = link_at
        self.parts: list[tuple[int, object]] = []  # [(Seite, QPdfSelection)]
        self._anchor: tuple[int, QPointF] | None = None
        self._press: QPoint | None = None
        self._dragging = False
        self._clicks = 0
        self._last_click = 0.0
        self._last_pos: QPoint | None = None
        self._page_cache: dict[tuple[int, int], tuple[list[str], list[QRectF]]] = {}
        self._index_cache: dict[tuple, int | None] = {}  # (Dokument, Seite, x, y) -> Index

        vp = self._viewport = view.viewport()
        vp.setMouseTracking(True)
        vp.installEventFilter(self)
        self.overlay = _Overlay(self, vp)
        self.overlay.resize(vp.size())
        self.overlay.show()
        for sb in (view.verticalScrollBar(), view.horizontalScrollBar()):
            sb.valueChanged.connect(self.overlay.update)
        view.zoomFactorChanged.connect(lambda *_: self.overlay.update())
        view.zoomModeChanged.connect(lambda *_: self.overlay.update())

        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._menu)
        for keys, slot in ((QKeySequence.StandardKey.Copy, self.copy),
                           (QKeySequence.StandardKey.SelectAll, self.select_all),
                           (QKeySequence("Escape"), self.clear)):
            sc = QShortcut(QKeySequence(keys), view)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

    @property
    def doc(self) -> QPdfDocument:
        return self._document()

    # --- Zeichen einer Seite ---
    #
    # Jeder Aufruf in PDFium kostet rund 10 ms (es liest den Seitentext neu);
    # Zeichenboxen einzeln abzufragen dauerte bei einer vollen Seite eine
    # Minute. Deshalb: je Seite einmal Text und Glyphenboxen (getAllText), den
    # Mauspunkt in Python auf die naechste Glyphe einrasten und nur die Auswahl
    # selbst von PDFium holen. PDFium findet ein Zeichen nur, wenn der Punkt fast
    # genau darauf liegt -- eingerastet trifft es auch im Leerraum.

    def _page(self, page: int) -> tuple[list[str], list[QRectF]]:
        """Zeichen je PDFium-Index und die Textzeilen der Seite (PDF-Punkte).

        PDFium zaehlt UTF-16-Einheiten: ein Emoji belegt zwei Indizes. Die Liste
        hat deshalb je Index einen Eintrag (der zweite eines Emojis ist leer)."""
        doc = self.doc
        key = (id(doc), page)
        if key not in self._page_cache:
            whole = doc.getAllText(page)
            chars: list[str] = []
            for ch in whole.text():
                chars.append(ch)
                if ord(ch) > 0xFFFF:
                    chars.append("")
            boxes = [b for b in (poly.boundingRect() for poly in whole.bounds())
                     if b.width() > 0 and b.height() > 0]
            self._page_cache[key] = (chars, _lines(boxes))
        return self._page_cache[key]

    def _nearest_boxes(self, page: int, pt: QPointF, n: int) -> list[QRectF]:
        """Die ``n`` Textzeilen, die ``pt`` am naechsten liegen (dieselbe Hoehe geht vor)."""
        def score(r: QRectF) -> float:
            dy = 0.0 if r.top() <= pt.y() <= r.bottom() else min(abs(pt.y() - r.top()), abs(pt.y() - r.bottom()))
            dx = 0.0 if r.left() <= pt.x() <= r.right() else min(abs(pt.x() - r.left()), abs(pt.x() - r.right()))
            return dy * 100 + dx
        return sorted(self._page(page)[1], key=score)[:n]

    def _caret_at(self, page: int, pt: QPointF) -> int | None:
        """Caret-Stelle (PDFium-Index der Grenze vor einem Zeichen), die ``pt``
        am naechsten liegt.

        ``pt`` wird in die naechste Textzeile gerueckt, die x-Stelle bleibt. Qts
        getSelection meldet die Grenzen zweier Punkte, aber nichts, wenn beide auf
        dieselbe fallen -- deshalb vom Zeilenanfang bis ``pt`` (Ende = gesuchte
        Grenze), sonst von ``pt`` bis zum Zeilenende (Anfang). Manche Glyphen
        findet PDFium ueber Koordinaten gar nicht (z. B. Seitenzahlen) -- dann die
        naechste Zeile."""
        key = (id(self.doc), page, round(pt.x(), 1), round(pt.y(), 1))
        if key in self._index_cache:
            return self._index_cache[key]
        found = None
        for box in self._nearest_boxes(page, pt, 4):
            y = box.center().y()
            left, right = QPointF(box.left() + 0.5, y), QPointF(box.right() - 0.5, y)
            c = QPointF(min(max(pt.x(), left.x()), right.x()), y)
            sel = self.doc.getSelection(page, left, c)
            if sel.isValid() and sel.text():
                found = sel.endIndex()
                break
            sel = self.doc.getSelection(page, c, right)
            if sel.isValid() and sel.text():
                found = sel.startIndex()
                break
        if len(self._index_cache) > 256:
            self._index_cache.clear()
        self._index_cache[key] = found
        return found

    def _range(self, page: int, a: int, b: int):
        """Zeichen ``a`` bis ausschliesslich ``b``."""
        a, b = max(0, min(a, b)), max(a, b)
        return self.doc.getSelectionAtIndex(page, a, b - a) if b > a else None

    # --- Auswahl ---

    def text(self) -> str:
        """Markierter Text; Seiten durch Zeilenumbruch getrennt, Zeilenenden als \\n."""
        raw = "\n".join(s.text().replace("\r\n", "\n").replace("\r", "\n") for _p, s in self.parts)
        return tidy_text(raw).strip("\n")

    def has_selection(self) -> bool:
        return bool(self.text())

    def clear(self) -> None:
        if self.parts:
            self.parts = []
            self.overlay.update()

    def reset(self) -> None:
        """Nach dem (Neu-)Laden eines Dokuments: Auswahl und Zeichenboxen verwerfen."""
        self._page_cache.clear()
        self._index_cache.clear()
        self.clear()

    def select(self, start: tuple[int, QPointF], end: tuple[int, QPointF]) -> None:
        """Markiert von ``start`` bis ``end`` (je Seite und Stelle in PDF-Punkten)."""
        (p0, a), (p1, b) = start, end
        ia, ib = self._caret_at(p0, a), self._caret_at(p1, b)
        if (p1, ib if ib is not None else 0) < (p0, ia if ia is not None else 0):
            (p0, ia), (p1, ib) = (p1, ib), (p0, ia)
        parts = []
        if p0 == p1:
            if ia is not None and ib is not None:
                parts.append((p0, self._range(p0, ia, ib)))
        else:
            # Erste Seite ab dem Anker bis zum Ende, dazwischen ganz, letzte bis zur Maus
            if ia is not None:
                parts.append((p0, self._range(p0, ia, len(self._page(p0)[0]))))
            parts += [(page, self.doc.getAllText(page)) for page in range(p0 + 1, p1)]
            if ib is not None:
                parts.append((p1, self._range(p1, 0, ib)))
        self.parts = [(p, s) for p, s in parts if s is not None and s.isValid() and s.text()]
        self.overlay.update()

    def select_all(self) -> None:
        doc = self.doc
        parts = [(p, doc.getAllText(p)) for p in range(doc.pageCount())]
        self.parts = [(p, s) for p, s in parts if s.isValid() and s.text()]
        self.overlay.update()

    def _select_unit(self, hit: tuple[int, QPointF], line: bool) -> None:
        """Wort (bzw. Zeile) unter ``hit``: von Leerraum bis Leerraum im Seitentext."""
        page, pt = hit
        chars = self._page(page)[0]
        idx = self._caret_at(page, pt)
        stops = {"\r", "\n"} | (set() if line else {" ", "\t"})
        if idx is not None and idx > 0 and (idx >= len(chars) or chars[idx] in stops):
            idx -= 1  # Caret hinter dem letzten Zeichen eines Worts
        if idx is None or idx >= len(chars) or chars[idx] in stops:
            self.clear()
            return
        a = idx
        while a > 0 and chars[a - 1] not in stops:
            a -= 1
        b = idx
        while b < len(chars) and chars[b] not in stops:
            b += 1
        sel = self._range(page, a, b)
        self.parts = [(page, sel)] if sel is not None and sel.isValid() and sel.text() else []
        self.overlay.update()

    def copy(self) -> None:
        text = self.text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _menu(self, pos: QPoint) -> None:
        menu = QMenu(self.view)
        a = menu.addAction("Kopieren", self.copy)
        a.setShortcut(QKeySequence.StandardKey.Copy)
        a.setEnabled(self.has_selection())
        b = menu.addAction("Alles auswählen", self.select_all)
        b.setShortcut(QKeySequence.StandardKey.SelectAll)
        # Bei Scroll-Bereichen kommt ``pos`` schon in Viewport-Koordinaten
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # --- Maus ---

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt-API)
        # Beim Abbauen kommen noch Events am Viewport an, wenn die Ansicht schon weg ist
        if obj is not self._viewport or not isValid(self.view):
            return False
        et = event.type()
        if et == QEvent.Type.Resize:
            self.overlay.resize(event.size())
        elif et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick) \
                and event.button() == Qt.MouseButton.LeftButton:
            # Den zweiten Klick meldet Qt als DblClick; gezaehlt wird selbst (Dreifachklick)
            pos = event.position().toPoint()
            now = time.monotonic()
            interval = QApplication.styleHints().mouseDoubleClickInterval() / 1000
            near = self._last_pos is not None and (pos - self._last_pos).manhattanLength() <= 2 * DRAG_SLOP
            self._clicks = self._clicks + 1 if near and now - self._last_click < interval else 1
            self._last_pos = pos
            if et == QEvent.Type.MouseButtonDblClick:
                self._clicks = max(self._clicks, 2)
            self._last_click = now
            # Auf einem Link: Klick folgt ihm (macht die Ansicht), Ziehen markiert trotzdem
            hit = page_at(self.view, self.doc, pos)
            if self._clicks >= 2 and hit is not None:
                self._select_unit(hit, line=self._clicks >= 3)
                self._press = None
                return True
            self.view.setFocus(Qt.FocusReason.MouseFocusReason)
            self._press = pos
            self._anchor = hit or nearest_page(self.view, self.doc, pos)
            self._dragging = False
        elif et == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
                if not self._dragging and (pos - self._press).manhattanLength() > DRAG_SLOP:
                    self._dragging = True
                if self._dragging and self._anchor is not None:
                    end = nearest_page(self.view, self.doc, pos)
                    if end is not None:
                        self.select(self._anchor, end)
                    self._autoscroll(pos)
                    return True
            self._update_cursor(pos)
        elif et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            press, self._press = self._press, None
            if press is not None and not self._dragging and self._clicks < 2:
                self.clear()  # einfacher Klick hebt die Auswahl auf
            dragged, self._dragging = self._dragging, False
            if dragged:
                return True
        return False

    def _autoscroll(self, pos: QPoint) -> None:
        """Beim Ziehen ueber den oberen/unteren Rand weiterscrollen."""
        bar = self.view.verticalScrollBar()
        h = self.view.viewport().height()
        if pos.y() < 0:
            bar.setValue(bar.value() + pos.y())
        elif pos.y() > h:
            bar.setValue(bar.value() + pos.y() - h)

    def _update_cursor(self, pos: QPoint) -> None:
        vp = self.view.viewport()
        if self._link_at is not None and self._link_at(pos) is not None:
            vp.setCursor(Qt.CursorShape.PointingHandCursor)
        elif page_at(self.view, self.doc, pos) is not None:
            vp.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            vp.unsetCursor()
