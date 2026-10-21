"""Markdown -> Typst-Markup.

Gearbeitet wird auf dem Token-Stream von markdown-it-py statt mit regulaeren
Ausdruecken: verschachtelte Listen, Inline-Code mit Sonderzeichen und Bilder in
Tabellenzellen ueberstehen das zuverlaessig.

Listen, Tabellen und Zitate werden in Funktionsform (``#list(...)``,
``#md-table(...)``) ausgegeben. Das ist unleserlicher als native Typst-Syntax,
aber unempfindlich gegen Einrueckungsfehler.

Emojis werden absichtlich nicht angefasst -- sie wandern als UTF-8 durch, den
Rest erledigt die Font-Fallback-Kette im Template.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

# Zeichen, die in Typst-Markup eine Sonderbedeutung haben.
# "~" ist in Typst ein geschuetztes Leerzeichen.
_SPECIAL = "#$*_@<>\\`[]~"
_ESCAPE_RE = re.compile("([" + re.escape(_SPECIAL) + "])")
# "//" leitet in Typst einen Zeilenkommentar ein und wuerde den Rest der Zeile
# verschlucken -- ausser in URLs ("https://"), die Typst selbst erkennt.
_COMMENT_RE = re.compile(r"(?<!:)//")
# "-?" ist in Typst ein weicher Trennstrich.
_SOFT_HYPHEN_RE = re.compile(r"-\?")

# Am Zeilenanfang leiten diese Zeichen in Typst eine Struktur ein.
_LINE_START_RE = re.compile(r"^([=+\-/])")
# "3. Platz" am Zeilenanfang waere in Typst eine nummerierte Liste.
_ENUM_START_RE = re.compile(r"^(\d+)\.(?=\s|$)")

# Wird content.typ vorangestellt (siehe MarkdownToTypst.convert).
PREAMBLE = '#import "helpers.typ": md-table, md-checkbox, md-task, md-tasklist, md-wrap\n'

# Diese Bloecke beenden den Text, der ein umflossenes Bild umfliesst.
_WRAP_STOP = ("heading_open", "hr", "table_open", "footnote_block_open")
# Standardbreite umflossener Bilder ohne width-Angabe
_WRAP_WIDTH = "40%"

_BR_RE = re.compile(r"<br\s*/?>", re.I)
# "- [ ] Aufgabe" / "- [x] erledigt" (GitHub-Aufgabenlisten)
_TASK_RE = re.compile(r"\[([ xX])\](?:[ \t]+|$)")
_TASK_ARG = {None: "none", "open": "false", "done": "true"}
# <img ...> aus HTML -- MarkText & Co. fuegen Bilder so ein
_IMG_RE = re.compile(r"<img\b([^>]*?)/?>", re.I | re.S)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')


def escape(text: str) -> str:
    """Maskiert Typst-Sonderzeichen in Fliesstext."""
    text = _ESCAPE_RE.sub(r"\\\1", text)
    text = _COMMENT_RE.sub(r"\\/\\/", text)
    return _SOFT_HYPHEN_RE.sub(r"\\-?", text)


@dataclass
class ConversionResult:
    typst: str
    # Typst-Zeile (1-basiert) -> Markdown-Zeile (1-basiert)
    line_map: dict[int, int] = field(default_factory=dict)
    # Bilder, die nicht gefunden wurden
    missing_images: list[str] = field(default_factory=list)
    # Bilder ausserhalb der Typst-Wurzel: Dateiname im Arbeitsordner -> Quelle
    # (Datei oder, bei data:-URIs, die dekodierten Bytes). Die Engine legt sie
    # vor dem Kompilieren dort ab.
    external_images: dict[str, Path | bytes] = field(default_factory=dict)


class MarkdownToTypst:
    def __init__(
        self,
        *,
        heading_offset: int = 0,
        hr_as_pagebreak: bool = True,
        image_width: float = 80.0,
        figure_captions: bool = True,
        root_dir: Path | None = None,
        external_dir: str = ".completionistpdf",
        soft_breaks_as_linebreaks: bool = True,
    ) -> None:
        self.soft_breaks_as_linebreaks = soft_breaks_as_linebreaks
        self.heading_offset = heading_offset
        self.hr_as_pagebreak = hr_as_pagebreak
        self.image_width = image_width
        self.figure_captions = figure_captions
        self.root_dir = root_dir
        # Ordner unterhalb der Wurzel, in den externe Bilder kopiert werden
        self.external_dir = external_dir

        self.md = (
            MarkdownIt("commonmark", {"typographer": False})
            .enable(["table", "strikethrough"])
            .use(footnote_plugin)
        )

    # ------------------------------------------------------------------ #
    # oeffentliche API
    # ------------------------------------------------------------------ #

    def convert(self, text: str, base_dir: Path) -> ConversionResult:
        self._base_dir = Path(base_dir)
        self._root = Path(self.root_dir or base_dir)
        self._lines: list[str] = []
        self._line_map: dict[int, int] = {}
        self._missing: list[str] = []
        self._external: dict[str, Path] = {}
        self._footnotes: dict[int, str] = {}

        tokens = self.md.parse(text)
        self._collect_footnotes(tokens)
        self._render_blocks(tokens, 0, len(tokens))

        # content.typ wird von Typst als eigenes Modul geladen und sieht die
        # Definitionen aus main.typ nicht -- daher der Import.
        preamble = PREAMBLE.splitlines()
        offset = len(preamble)
        line_map = {t + offset: m for t, m in self._line_map.items()}

        return ConversionResult(
            typst="\n".join(preamble + self._lines) + "\n",
            line_map=line_map,
            # Ein Bild als ganzer Absatz wird inline und als Abbildung
            # aufgeloest -- jede fehlende Datei nur einmal melden.
            missing_images=list(dict.fromkeys(self._missing)),
            external_images=self._external,
        )

    # ------------------------------------------------------------------ #
    # Ausgabe-Helfer
    # ------------------------------------------------------------------ #

    def _emit(
        self, text: str = "", token: Token | None = None, sub_map: dict[int, int] | None = None
    ) -> None:
        """Haengt Zeilen an. ``sub_map`` ordnet weitere Zeilen innerhalb von
        ``text`` (0-basierter Versatz) einer Markdown-Zeile zu."""
        for i, line in enumerate(text.split("\n")):
            self._lines.append(line)
            if i == 0 and token is not None and token.map:
                self._line_map[len(self._lines)] = token.map[0] + 1
            elif sub_map and i in sub_map:
                self._line_map[len(self._lines)] = sub_map[i]

    # ------------------------------------------------------------------ #
    # Blockebene
    # ------------------------------------------------------------------ #

    def _render_blocks(self, tokens: list[Token], start: int, end: int) -> None:
        """Rendert Block-Tokens direkt in die Ausgabe."""
        for chunk in self._split_blocks(tokens, start, end):
            self._emit(*chunk)
            self._emit()

    def _split_blocks(self, tokens: list[Token], start: int, end: int) -> list[tuple]:
        """Zerlegt einen Token-Bereich in gerenderte Bloecke.

        Jeder Eintrag ist ``(text, token)`` oder -- bei mehrzeiligen Bloecken
        mit eigener Zeilenzuordnung -- ``(text, token, sub_map)``, passend zu
        den Argumenten von ``_emit``.
        """
        out: list[tuple] = []
        i = start
        while i < end:
            tok = tokens[i]
            t = tok.type

            if t == "heading_open":
                inline = tokens[i + 1]
                level = int(t_lvl(tok)) + self.heading_offset
                level = max(1, min(6, level))
                body = self._render_inline(inline)
                out.append(("=" * level + " " + body, tok))
                i = self._skip_to(tokens, i, "heading_close") + 1

            elif t == "paragraph_open":
                inline = tokens[i + 1]
                body = self._render_inline(inline)
                rendered = self._paragraph(inline, body)
                if rendered:
                    out.append((rendered, tok))
                i = self._skip_to(tokens, i, "paragraph_close") + 1

            elif t == "hr":
                # Nur "***" (auch "* * *") bricht die Seite um. "---" und "___"
                # werden ignoriert -- markup traegt das verwendete Zeichen.
                if self.hr_as_pagebreak and tok.markup.startswith("*"):
                    out.append(("#pagebreak(weak: true)", tok))
                i += 1

            elif t in ("fence", "code_block"):
                out.append((self._fence(tok), tok))
                i += 1

            elif t in ("bullet_list_open", "ordered_list_open"):
                close = "bullet_list_close" if t.startswith("bullet") else "ordered_list_close"
                j = self._matching(tokens, i, t, close)
                out.append((self._list(tokens, i, j), tok))
                i = j + 1

            elif t == "blockquote_open":
                j = self._matching(tokens, i, t, "blockquote_close")
                inner = self._blocks_to_content(tokens, i + 1, j)
                out.append((f"#quote(block: true)[{inner}]", tok))
                i = j + 1

            elif t == "table_open":
                j = self._matching(tokens, i, t, "table_close")
                out.append((self._table(tokens, i, j), tok))
                i = j + 1

            elif t == "footnote_block_open":
                j = self._matching(tokens, i, t, "footnote_block_close")
                i = j + 1  # Definitionen stehen bereits bei den Referenzen

            elif t == "html_block":
                side = self._wrap_side(tok)
                if side:
                    j = self._wrap_body_end(tokens, i + 1, end)
                    wrapped = self._wrap(tok, side, tokens, i + 1, j)
                    if wrapped:
                        out.append(wrapped)
                        i = j
                        continue
                rendered = self._html_block(tok)
                if rendered:
                    out.append((rendered, tok))
                i += 1

            else:
                i += 1

        return out

    def _paragraph(self, inline: Token, body: str) -> str:
        """Ein Absatz -- oder, wenn er nur aus einem Bild besteht, eine Abbildung."""
        img = _sole_image(inline)
        return self._figure(img) if img else body

    # -- umflossene Bilder ------------------------------------------------ #

    @staticmethod
    def _wrap_side(tok: Token) -> str | None:
        """``"left"``/``"right"``, wenn der HTML-Block nur aus einem ``<img>``
        mit ``align="left|right"`` besteht (so schreibt CompletionistMD
        umflossene Bilder)."""
        m = _IMG_RE.fullmatch(tok.content.strip())
        if not m:
            return None
        align = _attrs(m.group(1)).get("align", "").strip().lower()
        return align if align in ("left", "right") else None

    def _wrap_body_end(self, tokens: list[Token], start: int, end: int) -> int:
        """Ende des Textes, der ein umflossenes Bild umfliesst: bis zur
        naechsten Ueberschrift, Trennlinie, Tabelle oder zum naechsten Bild."""
        i = start
        while i < end:
            tok = tokens[i]
            if tok.type in _WRAP_STOP:
                break
            if tok.type == "html_block" and _IMG_RE.search(tok.content):
                break
            if tok.type == "paragraph_open" and _sole_image(tokens[i + 1]):
                break
            if tok.nesting == 1:
                i = self._matching(tokens, i, tok.type, tok.type[: -len("open")] + "close") + 1
            else:
                i += 1
        return i

    def _wrap(
        self, tok: Token, side: str, tokens: list[Token], start: int, end: int
    ) -> tuple | None:
        """``#md-wrap(...)`` fuer ein umflossenes Bild samt Textbloecken.

        Jeder Textblock beginnt auf einer eigenen Zeile, die per ``sub_map``
        auf seine Markdown-Zeile zeigt -- Fehlermeldungen und die
        Vorschau-Synchronisation treffen so weiter den richtigen Absatz.
        """
        attrs = _attrs(_IMG_RE.fullmatch(tok.content.strip()).group(1))
        path = self._image_path(attrs.get("src", ""))
        if path is None:
            return None

        width = _html_length(attrs.get("width"))
        height = _html_length(attrs.get("height"))
        if width is None and height is not None:
            img, width = f"image({_str(path)}, height: {height})", "auto"
        else:
            img, width = f"image({_str(path)}, width: 100%)", width or _WRAP_WIDTH
        alt = escape(attrs.get("alt", "").strip())
        if alt and self.figure_captions:
            img = f"figure({img}, caption: [{alt}])"

        parts = [f"#md-wrap({_str(side)}, {width}, {img}, ("]
        offset = 1  # Zeilenversatz des naechsten Blocks innerhalb des Aufrufs
        sub_map: dict[int, int] = {}
        for block in self._split_blocks(tokens, start, end):
            text, btok = block[0], block[1]
            if not text:
                continue
            if btok is not None and btok.map:
                sub_map[offset] = btok.map[0] + 1
            parts.append(f"  [{text}],")
            offset += text.count("\n") + 1
        parts.append("))")
        return ("\n".join(parts), tok, sub_map)

    def _fence(self, tok: Token) -> str:
        lang = (tok.info or "").strip().split()[0] if (tok.info or "").strip() else ""
        code = tok.content.rstrip("\n")
        # Genug Backticks, damit Backticks im Code den Block nicht beenden.
        fence = "`" * max(3, _longest_backtick_run(code) + 1)
        return f"{fence}{lang}\n{code}\n{fence}"

    def _list(self, tokens: list[Token], start: int, end: int) -> str:
        ordered = tokens[start].type == "ordered_list_open"
        items: list[tuple[str | None, str]] = []  # (Aufgaben-Status, Inhalt)
        i = start + 1
        while i < end:
            if tokens[i].type == "list_item_open":
                j = self._matching(tokens, i, "list_item_open", "list_item_close")
                state = self._take_task_marker(tokens, i + 1, j)
                items.append((state, self._blocks_to_content(tokens, i + 1, j)))
                i = j + 1
            else:
                i += 1

        has_tasks = any(state is not None for state, _ in items)
        if has_tasks and not ordered:
            # Kaestchen statt Aufzaehlungspunkt; normale Punkte in derselben
            # Liste behalten ihren Punkt (Helfer in helpers.typ).
            args = [f"md-task({_TASK_ARG[state]}, [{body}])" for state, body in items]
            return "#md-tasklist(\n  " + ",\n  ".join(args) + ",\n)"

        fn = "enum" if ordered else "list"
        args = []
        if ordered:
            start_attr = tokens[start].attrGet("start")
            if start_attr:
                args.append(f"start: {start_attr}")
        for state, body in items:
            # In nummerierten Listen bleibt die Nummer; das Kaestchen steht davor im Text.
            prefix = f"#md-checkbox({_TASK_ARG[state]}) " if state is not None else ""
            args.append(f"[{prefix}{body}]")
        return f"#{fn}(\n  " + ",\n  ".join(args) + ",\n)"

    @staticmethod
    def _take_task_marker(tokens: list[Token], start: int, end: int) -> str | None:
        """Erkennt ``[ ]`` / ``[x]`` am Anfang eines Listenpunkts (GitHub-
        Aufgabenliste) und entfernt die Markierung aus dem Text.

        Gibt ``"open"``, ``"done"`` oder ``None`` (keine Aufgabe) zurueck.
        """
        # Erster Absatz des Punkts -- auch in "engen" Listen vorhanden, dort
        # nur als hidden markiert.
        if start + 1 >= end or tokens[start].type != "paragraph_open":
            return None
        inline = tokens[start + 1]
        if inline.type != "inline" or not inline.children:
            return None
        first = inline.children[0]
        if first.type != "text":
            return None
        m = _TASK_RE.match(first.content)
        if not m:
            return None
        first.content = first.content[m.end():]
        return "done" if m.group(1) in "xX" else "open"

    def _table(self, tokens: list[Token], start: int, end: int) -> str:
        aligns: list[str] = []
        header: list[str] = []
        rows: list[list[str]] = []

        in_head = False
        current: list[str] = []
        i = start + 1
        while i < end:
            tok = tokens[i]
            if tok.type == "thead_open":
                in_head = True
            elif tok.type == "thead_close":
                in_head = False
            elif tok.type == "tr_open":
                current = []
            elif tok.type == "tr_close":
                if in_head:
                    header = current
                else:
                    rows.append(current)
            elif tok.type in ("th_open", "td_open"):
                if in_head:
                    aligns.append(_align_of(tok))
                close = "th_close" if tok.type == "th_open" else "td_close"
                j = self._matching(tokens, i, tok.type, close)
                cell = ""
                for k in range(i + 1, j):
                    if tokens[k].type == "inline":
                        cell = self._render_inline(tokens[k])
                current.append(cell)
                i = j
            i += 1

        columns = max(len(header), max((len(r) for r in rows), default=0), 1)
        aligns = (aligns + ["left"] * columns)[:columns]

        parts = [
            f"  columns: {columns}",
            "  aligns: (" + ", ".join(aligns) + ("," if columns == 1 else "") + ")",
            f"  has-header: {'true' if header else 'false'}",
        ]
        cells = [_pad(header, columns)] if header else []
        cells.extend(_pad(r, columns) for r in rows)
        body = ",\n".join(
            "  " + ", ".join(f"[{c}]" for c in row) for row in cells
        )
        return "#md-table(\n" + ",\n".join(parts) + ",\n" + body + ",\n)"

    def _blocks_to_content(self, tokens: list[Token], start: int, end: int) -> str:
        """Rendert Bloecke als Inhalt fuer ein ``[...]``-Argument."""
        blocks = self._split_blocks(tokens, start, end)
        return "\n\n".join(b[0] for b in blocks if b[0])

    def _html_block(self, tok: Token) -> str:
        content = tok.content.strip()
        # Kommentare verschwinden. <img> wird zum Bild; von sonstigem HTML
        # bleibt der Text ohne Tags erhalten, damit kein Inhalt verloren geht.
        if content.startswith("<!--"):
            return ""
        parts: list[str] = []
        pos = 0
        for m in _IMG_RE.finditer(content):
            parts.append(self._html_text(content[pos:m.start()]))
            parts.append(self._html_image(m.group(1), block=True))
            pos = m.end()
        parts.append(self._html_text(content[pos:]))
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _html_text(fragment: str) -> str:
        fragment = _BR_RE.sub("\n", fragment)
        text = re.sub(r"<[^>]+>", "", fragment).strip()
        return "\n\n".join(escape(p.strip()) for p in re.split(r"\n\s*\n", text) if p.strip())

    def _html_image(self, attr_text: str, *, block: bool) -> str:
        """``<img src=... width=...>`` als Typst-Bild."""
        attrs = _attrs(attr_text)
        path = self._image_path(attrs.get("src", ""))
        if path is None:
            return ""

        size = _html_length(attrs.get("width"))
        key = "width"
        if size is None:
            size = _html_length(attrs.get("height"))
            key = "height"
        if size is None:
            size, key = (f"{self.image_width}%", "width") if block else ("1em", "height")
        img = f"image({_str(path)}, {key}: {size})"

        if not block:
            return f"#box({img})"
        alt = escape(attrs.get("alt", "").strip())
        if alt and self.figure_captions:
            return f"#figure({img}, caption: [{alt}])"
        return f"#figure({img})"

    # ------------------------------------------------------------------ #
    # Inline-Ebene
    # ------------------------------------------------------------------ #

    def _render_inline(self, token: Token) -> str:
        return self._inline_children(token.children or [])

    def _inline_children(self, children: list[Token]) -> str:
        out: list[str] = []
        stack: list[str] = []
        low_quote_open = False  # ein „ wartet auf sein Gegenstueck
        i = 0
        while i < len(children):
            tok = children[i]
            t = tok.type

            if t == "text":
                content, low_quote_open = _pair_quotes(tok.content, low_quote_open)
                text = escape(content)
                if not out or out[-1].endswith("\n"):
                    text = _LINE_START_RE.sub(r"\\\1", text)
                    text = _ENUM_START_RE.sub(r"\1\\.", text)
                out.append(text)

            elif t == "softbreak":
                # " \" + Zeilenende = Zeilenumbruch in Typst; ein blosses
                # Zeilenende waere nur ein Leerzeichen.
                out.append(" \\\n" if self.soft_breaks_as_linebreaks else "\n")
            elif t == "hardbreak":
                out.append(" \\\n")

            elif t == "code_inline":
                # Immer die Funktionsform: unempfindlich gegen Backticks und
                # Sonderzeichen im Code.
                out.append(f"#raw({_str(tok.content)})")

            elif t == "strong_open":
                out.append("#strong[")
                stack.append("]")
            elif t == "em_open":
                out.append("#emph[")
                stack.append("]")
            elif t == "s_open":
                out.append("#strike[")
                stack.append("]")
            elif t in ("strong_close", "em_close", "s_close"):
                out.append(stack.pop() if stack else "]")

            elif t == "link_open":
                href = tok.attrGet("href") or ""
                out.append(f"#link({_str(href)})[")
                stack.append("]")
            elif t == "link_close":
                out.append(stack.pop() if stack else "]")

            elif t == "image":
                out.append(self._inline_image(tok))

            elif t == "footnote_ref":
                out.append(self._footnote_ref(tok))

            elif t == "html_inline":
                # <br> ist in Markdown gebraeuchlich genug, um es zu
                # uebersetzen. Alles andere (auch "<spitz>" im Fliesstext, das
                # markdown-it fuer ein Tag haelt) bleibt als Text sichtbar.
                content = tok.content.strip()
                img = _IMG_RE.fullmatch(content)
                if _BR_RE.fullmatch(content):
                    out.append(" \\\n")
                elif img:
                    out.append(self._html_image(img.group(1), block=False))
                elif not content.startswith("<!--"):
                    out.append(escape(tok.content))

            i += 1

        while stack:
            out.append(stack.pop())
        return "".join(out)

    def _inline_image(self, tok: Token) -> str:
        path = self._image_path(tok.attrGet("src") or "")
        if path is None:
            return ""
        return f'#box(image({_str(path)}, height: 1em))'

    def _figure(self, tok: Token) -> str:
        path = self._image_path(tok.attrGet("src") or "")
        if path is None:
            return ""
        alt = self._inline_children(tok.children or []).strip()
        img = f'image({_str(path)}, width: {self.image_width}%)'
        if alt and self.figure_captions:
            return f"#figure({img}, caption: [{alt}])"
        return f"#figure({img})"

    def _collect_footnotes(self, tokens: list[Token]) -> None:
        """Rendert alle Fussnoten-Definitionen vor, damit ``[^1]`` an der
        Fundstelle durch ``#footnote[...]`` ersetzt werden kann."""
        i = 0
        while i < len(tokens):
            if tokens[i].type == "footnote_open":
                j = self._matching(tokens, i, "footnote_open", "footnote_close")
                fid = (tokens[i].meta or {}).get("id")
                if fid is not None:
                    self._footnotes[int(fid)] = self._blocks_to_content(
                        tokens, i + 1, j
                    )
                i = j + 1
            else:
                i += 1

    def _footnote_ref(self, tok: Token) -> str:
        fid = (tok.meta or {}).get("id")
        text = self._footnotes.get(int(fid), "") if fid is not None else ""
        return f"#footnote[{text}]" if text else ""

    def _image_path(self, src: str) -> str | None:
        """Bildquelle -> wurzelrelativer Typst-Pfad (oder ``None``).

        Versteht relative und absolute Pfade, ``file:///``-URLs (so speichert
        MarkText eingefuegte Bilder) und ``data:``-URIs. Bilder ausserhalb der
        Wurzel werden zum Kopieren in den Arbeitsordner vorgemerkt -- Typst
        darf nur auf Dateien unterhalb der Wurzel zugreifen.
        """
        from urllib.parse import unquote, urlparse
        from urllib.request import url2pathname

        src = src.strip()
        if not src:
            return None

        if src.lower().startswith("data:"):
            return self._data_uri_image(src)

        if src.lower().startswith("file:"):
            parsed = urlparse(src)
            raw = url2pathname(parsed.path)
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                raw = "\\\\" + parsed.netloc + raw  # UNC-Pfad \\server\freigabe
        elif re.match(r"^[a-z][a-z0-9+.-]+://", src, re.I):
            # Typst kann keine Bilder aus dem Netz laden
            self._missing.append(f"{src} (Bilder aus dem Internet werden nicht geladen)")
            return None
        else:
            raw = unquote(src)

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self._base_dir / raw
        candidate = candidate.resolve()

        if not candidate.is_file():
            self._missing.append(raw)
            return None

        try:
            rel = candidate.relative_to(self._root.resolve())
        except ValueError:
            return self._register_external(candidate.name, candidate, str(candidate))
        # Fuehrender Slash = relativ zur Typst-Wurzel, unabhaengig davon, wo
        # content.typ liegt.
        return "/" + posixpath.join(*rel.parts)

    def _data_uri_image(self, src: str) -> str | None:
        import base64
        from urllib.parse import unquote_to_bytes

        m = re.match(r"data:([\w.+-]+/[\w.+-]+)?((?:;[^,;]*)*?)(;base64)?,(.*)", src, re.S | re.I)
        if not m:
            self._missing.append("data:-Bild mit unbekanntem Format")
            return None
        mime = (m.group(1) or "").lower()
        ext = _MIME_EXT.get(mime)
        if ext is None:
            self._missing.append(f"data:-Bild vom Typ {mime or '?'} wird nicht unterstützt")
            return None
        try:
            payload = m.group(4)
            data = base64.b64decode(re.sub(r"\s+", "", payload)) if m.group(3) else unquote_to_bytes(payload)
        except ValueError:
            self._missing.append("data:-Bild ist nicht lesbar (Base64 fehlerhaft)")
            return None
        return self._register_external(f"inline{ext}", data, hashlib.sha1(data).hexdigest())

    def _register_external(self, name: str, source: Path | bytes, identity: str) -> str:
        """Merkt ein Bild zum Kopieren in den Arbeitsordner vor."""
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
        target = f"_img_{digest}_{_safe_filename(name)}"
        self._external[target] = source
        return f"/{self.external_dir}/{target}"

    # ------------------------------------------------------------------ #
    # Token-Navigation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _skip_to(tokens: list[Token], start: int, close: str) -> int:
        i = start
        while i < len(tokens) and tokens[i].type != close:
            i += 1
        return i

    @staticmethod
    def _matching(tokens: list[Token], start: int, open_t: str, close_t: str) -> int:
        """Index des zum Oeffner passenden Schliessers (verschachtelungsfest)."""
        depth = 0
        for i in range(start, len(tokens)):
            if tokens[i].type == open_t:
                depth += 1
            elif tokens[i].type == close_t:
                depth -= 1
                if depth == 0:
                    return i
        return len(tokens) - 1


# ---------------------------------------------------------------------- #
# Hilfsfunktionen
# ---------------------------------------------------------------------- #


def t_lvl(tok: Token) -> int:
    return int(tok.tag[1:])


def _align_of(tok: Token) -> str:
    style = tok.attrGet("style") or ""
    if "right" in style:
        return "right"
    if "center" in style:
        return "center"
    return "left"


def _attrs(attr_text: str) -> dict[str, str]:
    """HTML-Attribute eines Tags als dict (Namen klein geschrieben)."""
    return {
        m.group(1).lower(): next(g for g in m.groups()[1:] if g is not None)
        for m in _ATTR_RE.finditer(attr_text)
    }


def _sole_image(inline: Token) -> Token | None:
    """Das Bild-Token, wenn ein Absatz nur aus einem Markdown-Bild besteht."""
    children = [c for c in (inline.children or []) if c.type != "softbreak"]
    if len(children) == 1 and children[0].type == "image":
        return children[0]
    return None


def _pad(row: list[str], n: int) -> list[str]:
    return (row + [""] * n)[:n]


_MIME_EXT = {
    "image/svg+xml": ".svg",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _html_length(value: str | None) -> str | None:
    """HTML-Groessenangabe -> Typst-Laenge.

    ``281`` und ``281px`` sind CSS-Pixel (96 pro Zoll = 0,75 pt), ``50%``
    bleibt eine Prozentangabe.
    """
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(px|%)?\s*", value, re.I)
    if not m:
        return None
    number = float(m.group(1))
    if number <= 0:
        return None
    if m.group(2) == "%":
        return f"{min(number, 100):g}%"
    return f"{number * 0.75:g}pt"


def _pair_quotes(text: str, low_open: bool) -> tuple[str, bool]:
    """Schliesst ein typografisches „ mit “, wenn im Text ein gerades " folgt.

    Viele Editoren setzen das oeffnende „ typografisch, das schliessende aber
    gerade. Typst kennt das „ nicht als Anfang eines Paars und macht aus dem
    geraden Zeichen ein weiteres oeffnendes „. ``low_open`` traegt den
    Zustand ueber Formatierungsgrenzen hinweg (z. B. „**fett**").
    """
    out = []
    for ch in text:
        if ch == "„":
            low_open = True
        elif ch in "“”":
            low_open = False
        elif ch == '"' and low_open:
            ch = "“"
            low_open = False
        out.append(ch)
    return "".join(out), low_open


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[-60:] or "bild"


def _longest_backtick_run(text: str) -> int:
    return max((len(m) for m in re.findall(r"`+", text)), default=0)


def _str(value: str) -> str:
    """Python-String als Typst-String-Literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
