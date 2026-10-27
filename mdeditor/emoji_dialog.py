"""Emoji-Auswahl: alle Emoji-Gruppen im Raster, mit Suche und Kategorien.

Die Liste entsteht zur Laufzeit aus ``unicodedata`` (Unicode-Namen) und den
Unicode-Bloecken -- keine Datendatei, kein Netz. Gesucht wird ueber den
englischen Unicode-Namen, die deutsche Kategorie und ein paar deutsche
Stichworte fuer die gaengigen Guide-Symbole.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

EMOJI_FONT = "Segoe UI Emoji"
VS16 = "️"  # Emoji-Darstellung erzwingen

ALL = "Alle"

# (Kategorie, [(von, bis), ...]) -- Reihenfolge = Reihenfolge im Dialog.
# Bereiche gelten inklusive; spaetere Eintraege ueberschreiben fruehere nicht.
_RANGES: list[tuple[str, list[tuple[int, int]]]] = [
    ("Smileys & Gefühle", [
        (0x1F600, 0x1F64F), (0x1F910, 0x1F92F), (0x1F970, 0x1F97B),
        (0x1FAE0, 0x1FAEF), (0x263A, 0x263A), (0x2639, 0x2639),
    ]),
    ("Personen & Körper", [
        (0x1F440, 0x1F487), (0x1F930, 0x1F93A), (0x1F9B0, 0x1F9BF),
        (0x1F9CD, 0x1F9DF), (0x1FAF0, 0x1FAF8), (0x270A, 0x270D), (0x261D, 0x261D),
    ]),
    ("Tiere & Natur", [
        (0x1F300, 0x1F32C), (0x1F330, 0x1F344), (0x1F400, 0x1F43F),
        (0x1F980, 0x1F9AE), (0x1FAB0, 0x1FABD), (0x1FAB7, 0x1FABF),
        (0x2600, 0x2604), (0x26A1, 0x26A1), (0x2744, 0x2744), (0x26C4, 0x26C8),
    ]),
    ("Essen & Trinken", [
        (0x1F32D, 0x1F32F), (0x1F345, 0x1F37F), (0x1F950, 0x1F96F),
        (0x1F9C0, 0x1F9CB), (0x1FAD0, 0x1FADB), (0x2615, 0x2615),
    ]),
    ("Aktivitäten & Feiern", [
        (0x1F380, 0x1F3DF), (0x1F93B, 0x1F94F), (0x1F004, 0x1F004),
        (0x1F0CF, 0x1F0CF), (0x1FA70, 0x1FA7C), (0x26BD, 0x26BE), (0x26F3, 0x26F3),
    ]),
    ("Reisen & Orte", [
        (0x1F3E0, 0x1F3F0), (0x1F680, 0x1F6FF), (0x1F5FA, 0x1F5FF),
        (0x26EA, 0x26FD), (0x2708, 0x2708),
    ]),
    ("Gegenstände", [
        (0x1F4B0, 0x1F4FF), (0x1F506, 0x1F52E), (0x1F546, 0x1F54F),
        (0x1F56F, 0x1F5F9), (0x1F97C, 0x1F97F), (0x1F9E0, 0x1F9FF),
        (0x1FA80, 0x1FAAF), (0x231A, 0x231B), (0x2328, 0x2328),
        (0x23CF, 0x23CF), (0x23F0, 0x23F3), (0x260E, 0x260E), (0x2692, 0x2697),
        (0x2699, 0x269B), (0x2702, 0x2702), (0x2709, 0x2709), (0x270F, 0x2712),
    ]),
    ("Symbole", [
        (0x1F488, 0x1F4AF), (0x1F500, 0x1F505), (0x1F52F, 0x1F53D),
        (0x1F549, 0x1F54E), (0x1F550, 0x1F567), (0x1F7E0, 0x1F7EB),
        (0x1F170, 0x1F251), (0x2600, 0x26FF), (0x2700, 0x27BF),
        (0x23E9, 0x23EF), (0x23F8, 0x23FA), (0x2B1B, 0x2B1C), (0x2B50, 0x2B55),
        (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x203C), (0x2049, 0x2049),
        (0x2122, 0x2122), (0x2139, 0x2139), (0x24C2, 0x24C2), (0x3030, 0x3030),
        (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299),
    ]),
    ("Pfeile", [
        (0x2190, 0x21FF), (0x27F0, 0x27FF), (0x2900, 0x297F), (0x2B00, 0x2B11),
        (0x1F800, 0x1F8FF),
    ]),
    ("Formen", [(0x25A0, 0x25FF), (0x1F780, 0x1F7D8)]),
]

# Pfeile, die echte Emoji sind (alle anderen bleiben ohne Variantenzeichen).
_EMOJI_ARROWS = set(range(0x2194, 0x219A)) | {0x21A9, 0x21AA, 0x2934, 0x2935, 0x2B05, 0x2B06, 0x2B07}

# Haeufige Flaggen (Regionalindikatoren -- unicodedata kennt keine Paare).
_FLAGS = (
    "DE AT CH LI LU NL BE FR IT ES PT GB IE DK SE NO FI IS PL CZ SK HU SI HR "
    "GR TR UA RU US CA MX BR AR CL JP CN KR TW IN AU NZ ZA EG IL EU UN"
)

# Deutsche Stichworte fuer die Suche (Zeichen ohne Variantenzeichen).
_KEYWORDS_DE = {
    "📜": "schriftrolle quest auftrag", "🗺": "karte fundort welt", "🏆": "trophäe pokal erfolg",
    "💎": "diamant edelstein sammelobjekt", "🚨": "achtung alarm warnung missable",
    "✅": "haken erledigt fertig ok", "⚔": "schwerter kampf", "🧩": "puzzle rätsel",
    "🔑": "schlüssel zugang", "⭐": "stern highlight", "⏱": "stoppuhr zeit zeitkritisch",
    "📍": "pin position ort markierung", "🔴": "rot kreis punkt gefahr",
    "🟢": "grün kreis punkt ok", "🟡": "gelb kreis", "🔵": "blau kreis",
    "❤": "herz liebe", "🔥": "feuer", "💀": "totenkopf tod", "⚠": "warnung achtung",
    "❌": "kreuz falsch nein", "❓": "frage", "❗": "ausrufezeichen wichtig",
    "💡": "glühbirne idee tipp", "📌": "pinnadel", "🎯": "ziel", "🛡": "schild verteidigung",
    "🏹": "bogen pfeil", "🪙": "münze geld", "💰": "geldsack geld", "🗝": "alter schlüssel",
    "📖": "buch lesen", "📝": "notiz schreiben", "🔒": "schloss gesperrt", "🔓": "offen entsperrt",
    "👑": "krone", "🎮": "spiel controller", "🕹": "joystick spiel", "🧭": "kompass",
    "⏳": "sanduhr zeit", "🔍": "lupe suche", "⚙": "zahnrad einstellungen", "🧪": "trank labor",
    "👀": "augen", "👍": "daumen hoch gut", "👎": "daumen runter", "➡": "pfeil rechts",
    "⬅": "pfeil links", "⬆": "pfeil hoch", "⬇": "pfeil runter", "🏁": "zielflagge",
    "🚩": "flagge markierung", "🐉": "drache", "👻": "geist", "🧙": "magier zauberer",
}


# Englische Woerter aus Unicode-Namen -> deutsche Suchbegriffe
_WORDS_DE = {
    "heart": "herz", "star": "stern", "arrow": "pfeil", "circle": "kreis", "square": "quadrat",
    "face": "gesicht", "smiling": "lächeln", "grinning": "grinsen", "crying": "weinen",
    "angry": "wütend", "hand": "hand", "finger": "finger", "thumbs": "daumen", "cat": "katze",
    "dog": "hund", "horse": "pferd", "bird": "vogel", "fish": "fisch", "dragon": "drache",
    "snake": "schlange", "flower": "blume", "tree": "baum", "leaf": "blatt", "sun": "sonne",
    "moon": "mond", "cloud": "wolke", "rain": "regen", "snow": "schnee", "fire": "feuer",
    "water": "wasser", "book": "buch", "key": "schlüssel", "lock": "schloss", "clock": "uhr",
    "money": "geld", "coin": "münze", "sword": "schwert", "shield": "schild", "crown": "krone",
    "house": "haus", "car": "auto", "train": "zug", "ship": "schiff", "map": "karte",
    "music": "musik", "bell": "glocke", "light": "licht", "check": "haken", "cross": "kreuz",
    "warning": "warnung", "question": "frage", "exclamation": "ausrufezeichen", "red": "rot",
    "green": "grün", "blue": "blau", "yellow": "gelb", "orange": "orange", "purple": "lila",
    "black": "schwarz", "white": "weiß", "brown": "braun", "up": "hoch oben", "down": "runter unten",
    "left": "links", "right": "rechts", "trophy": "trophäe pokal", "medal": "medaille",
    "game": "spiel", "dice": "würfel", "skull": "totenkopf", "ghost": "geist", "eye": "auge",
    "eyes": "augen", "food": "essen", "drink": "trinken", "beer": "bier", "wine": "wein",
    "coffee": "kaffee", "cake": "kuchen", "apple": "apfel", "pin": "nadel", "flag": "flagge",
    "mountain": "berg", "castle": "burg schloss", "tent": "zelt", "compass": "kompass",
    "hammer": "hammer", "wrench": "schraubenschlüssel", "gear": "zahnrad", "bomb": "bombe",
    "potion": "trank", "magic": "magie", "wizard": "zauberer", "mage": "magier",
    "bow": "bogen", "gem": "edelstein", "diamond": "diamant", "scroll": "schriftrolle",
    "hourglass": "sanduhr", "stopwatch": "stoppuhr", "timer": "zeit", "telephone": "telefon",
    "letter": "brief", "envelope": "umschlag", "pencil": "stift", "memo": "notiz",
    "calendar": "kalender", "camera": "kamera", "computer": "computer", "phone": "handy",
}


def _german(name: str) -> str:
    return " ".join(_WORDS_DE[w] for w in name.split() if w in _WORDS_DE)


def _with_vs(cp: int, ch: str) -> str:
    """Variantenzeichen anhaengen, wo das Zeichen sonst als Text erscheint."""
    if cp >= 0x1F000:
        return ch
    arrows = 0x2190 <= cp <= 0x21FF or 0x27F0 <= cp <= 0x27FF or 0x2900 <= cp <= 0x297F or 0x2B00 <= cp <= 0x2BFF
    if arrows:
        emoji = cp in _EMOJI_ARROWS or cp in (0x2B1B, 0x2B1C, 0x2B50, 0x2B55)
        return ch + VS16 if emoji else ch
    if 0x25A0 <= cp <= 0x25FF:
        return ch + VS16 if cp in (0x25AA, 0x25AB, 0x25B6, 0x25C0, 0x25FB, 0x25FC, 0x25FD, 0x25FE) else ch
    return ch + VS16


@lru_cache(maxsize=1)
def all_emojis() -> list[tuple[str, str, str]]:
    """[(zeichen, suchtext, kategorie), ...] in Dialog-Reihenfolge."""
    seen: set[int] = set()
    out: list[tuple[str, str, str]] = []
    for category, ranges in _RANGES:
        for lo, hi in ranges:
            for cp in range(lo, hi + 1):
                if cp in seen or 0x1F3FB <= cp <= 0x1F3FF or 0x1F1E6 <= cp <= 0x1F1FF:
                    continue
                ch = chr(cp)
                name = unicodedata.name(ch, "")
                if not name or unicodedata.category(ch) not in ("So", "Sm"):
                    continue
                seen.add(cp)
                text = _with_vs(cp, ch)
                low = name.lower()
                keys = f"{low} {_german(low)} {category.lower()} {_KEYWORDS_DE.get(ch, '')}"
                out.append((text, keys, category))
    for d in "0123456789#*":
        out.append((d + VS16 + "⃣", f"keycap taste {d} ziffer symbole", "Symbole"))
    for code in _FLAGS.split():
        flag = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)
        out.append((flag, f"flag flagge {code.lower()} flaggen", "Flaggen"))
    return out


def categories() -> list[str]:
    return [ALL] + [c for c, _ in _RANGES] + ["Flaggen"]


def display_name(char: str) -> str:
    base = char.replace(VS16, "")
    if len(base) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in base):
        return "Flagge " + "".join(chr(ord(c) - 0x1F1E6 + ord("A")) for c in base)
    try:
        return unicodedata.name(base[0]).title()
    except (ValueError, IndexError):
        return base


# ---------------------------------------------------------------------- #


class EmojiDialog(QDialog):
    """Nicht-modales Fenster; jeder Klick fuegt ein Emoji am Cursor ein."""

    picked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Emoji einfügen")
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(640, 520)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Suchen – z. B. Herz, Stern, arrow, Pfeile, Symbole …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.cats = QListWidget(self)
        self.cats.setFixedWidth(170)
        for c in categories():
            self.cats.addItem(c)
        self.cats.currentTextChanged.connect(self._filter)

        emoji_font = QFont(EMOJI_FONT)
        emoji_font.setPointSize(20)
        self.grid = QListWidget(self)
        # Ohne den Innenabstand der Listen aus theme.qss: sonst bleibt fuer das Emoji in
        # der Zelle zu wenig Breite, und Qt kuerzt es zu "…"
        self.grid.setObjectName("emojiGrid")
        self.setStyleSheet("QListView#emojiGrid::item { padding: 0px; }")
        self.grid.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setUniformItemSizes(True)
        self.grid.setGridSize(QSize(46, 46))
        self.grid.setFont(emoji_font)
        self.grid.setMouseTracking(True)
        self.grid.setWordWrap(False)
        self.grid.itemClicked.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.grid.itemEntered.connect(lambda it: self.info.setText(it.toolTip()))

        self.info = QLabel("Klick fügt das Emoji an der Cursorposition ein.", self)

        for char, keys, cat in all_emojis():
            it = QListWidgetItem(char)
            it.setData(Qt.ItemDataRole.UserRole, char)
            it.setData(Qt.ItemDataRole.UserRole + 1, keys)
            it.setData(Qt.ItemDataRole.UserRole + 2, cat)
            it.setToolTip(f"{display_name(char)}  ·  {cat}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it.setSizeHint(QSize(44, 44))
            self.grid.addItem(it)

        body = QHBoxLayout()
        body.addWidget(self.cats)
        body.addWidget(self.grid, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addLayout(body, 1)
        lay.addWidget(self.info)

        self.cats.setCurrentRow(0)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.search.setFocus()
        self.search.selectAll()

    def _filter(self, *_args) -> None:
        words = self.search.text().lower().split()
        cat = self.cats.currentItem().text() if self.cats.currentItem() else ALL
        shown = 0
        self.grid.setUpdatesEnabled(False)
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            keys = it.data(Qt.ItemDataRole.UserRole + 1)
            ok = all(w in keys for w in words) if words else True
            # Mit Suchbegriff wird ueber alle Kategorien gesucht.
            if not words and cat != ALL:
                ok = it.data(Qt.ItemDataRole.UserRole + 2) == cat
            it.setHidden(not ok)
            shown += ok
        self.grid.setUpdatesEnabled(True)
        self.info.setText(f"{shown} Emojis – Klick fügt an der Cursorposition ein.")
