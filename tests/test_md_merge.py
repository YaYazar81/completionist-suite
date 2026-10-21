from pathlib import Path

from core.md_merge import default_name, merge_files, rebase_paths


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_files_are_separated_by_hard_rule(tmp_path):
    a = write(tmp_path / "a.md", "# A\n\nText A\n")
    b = write(tmp_path / "b.md", "# B\n\nText B\n\n\n")
    out = merge_files([a, b], tmp_path / "ziel.md")
    assert out == "# A\n\nText A\n\n***\n\n# B\n\nText B\n"


def test_only_first_frontmatter_is_kept(tmp_path):
    a = write(tmp_path / "a.md", "---\ntitle: A\n---\n# A\n")
    b = write(tmp_path / "b.md", "---\ntitle: B\n---\n# B\n")
    out = merge_files([a, b], tmp_path / "ziel.md")
    assert out.startswith("---\ntitle: A\n---\n\n# A")
    assert "title: B" not in out


def test_image_paths_follow_target_folder(tmp_path):
    a = write(tmp_path / "kap" / "a.md", "![x](images/bild.png)\n<img src=\"images/b.png\" width=\"40%\">\n"
                                          "[Link](../c.md) [Web](https://x.de) ![d](data:image/png;base64,AA)\n")
    out = merge_files([a], tmp_path / "ziel.md")
    assert "![x](kap/images/bild.png)" in out
    assert '<img src="kap/images/b.png"' in out
    assert "[Link](c.md)" in out
    assert "https://x.de" in out and "data:image/png;base64,AA" in out


def test_code_blocks_are_untouched(tmp_path):
    text = "```md\n![x](images/a.png)\n```\n"
    assert rebase_paths(text, tmp_path / "kap", tmp_path) == text


def test_empty_files_are_skipped(tmp_path):
    a = write(tmp_path / "a.md", "A\n")
    b = write(tmp_path / "b.md", "\n\n")
    assert merge_files([a, b], tmp_path / "z.md") == "A\n"


def test_default_name():
    assert default_name([Path("Kapitel 1.md"), Path("Kapitel 2.md")]) == "Kapitel.md"
    assert default_name([Path("a.md"), Path("b.md")]) == "Zusammengeführt.md"
