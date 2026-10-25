"""Markdown -> Typst: Maskierung und Bloecke, geprueft am echten Typst-Compiler."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import typst

from core.config import DocumentConfig
from core.md_converter import MarkdownToTypst, escape

ROOT = Path(__file__).resolve().parents[1]


def convert(md: str, tmp_path: Path, **kw) -> str:
    return MarkdownToTypst(root_dir=tmp_path, **kw).convert(md, tmp_path).typst


def query(md: str, tmp_path: Path, selector: str, **kw) -> list:
    """Wandelt um, kompiliert und liefert die Elemente zu ``selector``."""
    shutil.copyfile(ROOT / "templates" / "helpers.typ", tmp_path / "helpers.typ")
    # helpers.typ liest die Einstellungen aus config.json
    (tmp_path / "config.json").write_text(
        json.dumps(DocumentConfig().to_template_dict()), encoding="utf-8")
    src = tmp_path / "content.typ"
    src.write_text(convert(md, tmp_path, **kw), encoding="utf-8")
    return json.loads(typst.query(str(src), selector, root=str(tmp_path)))


def plain_text(md: str, tmp_path: Path) -> str:
    """Der Fliesstext des Dokuments, so wie Typst ihn setzt."""
    pars = query(md, tmp_path, "par")
    return " ".join(_text_of(p) for p in pars)


def _text_of(node) -> str:
    if isinstance(node, dict):
        if node.get("func") == "space":
            return " "
        if "text" in node:
            return node["text"]
        return "".join(_text_of(v) for k, v in node.items() if k in ("body", "children"))
    if isinstance(node, list):
        return "".join(_text_of(n) for n in node)
    return ""


# ---------------------------------------------------------------------- #


@pytest.mark.parametrize("md", [
    "Er wurde am Ende\n3. Platz im Turnier.",   # Zahl am Anfang einer Folgezeile
    "3\\. Platz im Turnier.",                    # maskierte Zahl am Absatzanfang
    "Ende\n2024. war gut",
])
def test_number_at_line_start_is_no_list(md, tmp_path):
    assert query(md, tmp_path, "enum") == []


@pytest.mark.parametrize("soft", [True, False])
def test_number_at_line_start_without_linebreaks(soft, tmp_path):
    md = "Er wurde am Ende\n3. Platz im Turnier."
    assert query(md, tmp_path, "enum", soft_breaks_as_linebreaks=soft) == []


def test_real_ordered_list_stays_list(tmp_path):
    enums = query("1. eins\n2. zwei\n", tmp_path, "enum")
    assert len(enums) == 1 and len(enums[0]["children"]) == 2


@pytest.mark.parametrize("md", [
    "Begriff\n/ kein Term",
    "Text\n= keine Überschrift",
    "Text\n\\+ keine Liste",       # maskiert, sonst macht schon Markdown eine Liste
    "Text\n\\- keine Liste",
])
def test_markup_at_line_start_is_text(md, tmp_path):
    assert query(md, tmp_path, "heading") == []
    assert query(md, tmp_path, "list") == []
    assert query(md, tmp_path, "enum") == []
    assert query(md, tmp_path, "terms") == []


@pytest.mark.parametrize("md, expected", [
    ("Kostet 5 $ oder 10 $.", "$"),
    ("C# und F#", "C# und F#"),
    ("a // b", "a // b"),
    ("info@example.com", "@"),
    ("Pfad C:\\\\Temp", "C:\\Temp"),
    ("weich-?trennen", "-?"),
])
def test_special_characters_survive(md, expected, tmp_path):
    assert expected in plain_text(md, tmp_path)


def test_escape_marks_typst_syntax():
    assert escape("#x $y *z* _a_ @b <c>") == r"\#x \$y \*z\* \_a\_ \@b \<c\>"
    assert escape("a // b") == r"a \/\/ b"
    assert escape("https://x.de") == "https://x.de"


def pages(md: str, tmp_path: Path, **kw) -> int:
    query(md, tmp_path, "heading", **kw)  # legt content.typ samt Hilfsdateien an
    out = typst.compile(str(tmp_path / "content.typ"), root=str(tmp_path), format="png", ppi=10)
    return len(out) if isinstance(out, list) else 1


def test_star_rule_is_pagebreak_dash_rule_is_not(tmp_path):
    assert pages("A\n\n***\n\nB", tmp_path) == 2
    assert pages("A\n\n---\n\nB", tmp_path) == 1
    assert pages("A\n\n***\n\nB", tmp_path, hr_as_pagebreak=False) == 1


def test_heading_levels_and_offset(tmp_path):
    levels = [h["level"] for h in query("# A\n\n## B\n", tmp_path, "heading")]
    assert levels == [1, 2]
    levels = [h["level"] for h in query("# A\n", tmp_path, "heading", heading_offset=1)]
    assert levels == [2]


def test_table_and_task_list_compile(tmp_path):
    md = "| a | b |\n|:--|--:|\n| 1 | 2 |\n\n- [ ] offen\n- [x] erledigt\n"
    assert query(md, tmp_path, "table")


def test_missing_image_is_reported(tmp_path):
    res = MarkdownToTypst(root_dir=tmp_path).convert("![x](fehlt.png)", tmp_path)
    assert res.missing_images == ["fehlt.png"]


def test_line_map_points_to_markdown_lines(tmp_path):
    res = MarkdownToTypst(root_dir=tmp_path).convert("# Titel\n\nText\n", tmp_path)
    assert sorted(res.line_map.values()) == [1, 3]


def test_h2_rule_can_be_switched(tmp_path):
    """"##" bekommt wie im Editor eine Linie darunter; abschaltbar je Vorlage."""
    from core.typst_engine import TypstEngine

    md = tmp_path / "doc.md"
    md.write_text("# Titel\n\n## Überschrift\n\nText.\n", encoding="utf-8")
    pages = {}
    for on in (True, False):
        cfg = DocumentConfig.load(ROOT / "presets" / "Standard.json")
        assert cfg.typography.h2_rule
        cfg.markdown_path = str(md)
        cfg.cover.enabled = False
        cfg.toc.enabled = False
        cfg.typography.h2_rule = on
        out = tmp_path / f"h2_{on}.png"
        res = TypstEngine(ROOT).compile(cfg, output=out, fmt="png", ppi=30)
        assert res.ok, [d.format() for d in res.errors]
        pages[on] = out.read_bytes()
    assert pages[True] != pages[False]
