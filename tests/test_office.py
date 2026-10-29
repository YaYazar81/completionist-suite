"""Office-Dokumente: Drive-Sync, eingebaute Ansicht, Konverter, Office-Tab."""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import office  # noqa: E402

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def make_docx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        # Paketteile, ohne die LibreOffice die Datei nicht als Word erkennt
        z.writestr("[Content_Types].xml",
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/'
                   'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", f"""<w:document {W}><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Kapitel 1</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Hallo </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>fett</w:t></w:r></w:p>
<w:p><w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t>&lt;normal&gt;</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B1</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>""")
    return path


def make_xlsx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {S} {R}><sheets>'
                   '<sheet name="Bosse" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f"<sst {S}><si><t>Name</t></si><si><t>Drache</t></si></sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"""<worksheet {S}><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1"><v>42</v></c></row>
<row r="3"><c r="B3" t="s"><v>1</v></c></row>
</sheetData></worksheet>""")
    return path


# --- Drive-Sync -----------------------------------------------------------


def test_drive_sync_takes_office_files_but_not_lock_files_or_google_links(tmp_path):
    from mdeditor.gdrive import scan_local

    names = ["Bericht.docx", "Alt.doc", "Liste.xlsx", "Daten.csv", "Folien.pptx", "Text.odt",
             "Tabelle.ods", "Praesentation.odp", "Brief.rtf", "Word2003.xml", "Pages.pages",
             "~$Bericht.docx", ".~lock.Text.odt#", "Online.gdoc", "notiz.md", "programm.exe"]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    found = set(scan_local(tmp_path))
    assert {"Bericht.docx", "Alt.doc", "Liste.xlsx", "Daten.csv", "Folien.pptx", "Text.odt",
            "Tabelle.ods", "Praesentation.odp", "Brief.rtf", "Word2003.xml", "Pages.pages",
            "notiz.md"} == found


def test_office_suffix_lists():
    for suffix in (".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".doc", ".xls", ".ppt", ".gsheet"):
        assert office.is_office("a" + suffix.upper())
    assert ".gdoc" not in office.OFFICE_SYNC_SUFFIXES
    assert office.family("x.ODS") == "excel" and office.family("x.key") == "powerpoint"
    assert office.family("x.gdoc") == "google" and office.family("x.odt") == "word"


# --- Eingebaute Ansicht ---------------------------------------------------


def test_docx_to_html(tmp_path):
    html = office.to_html(make_docx(tmp_path / "a.docx"))
    assert "<h2>Kapitel 1</h2>" in html
    assert "Hallo <b>fett</b>" in html
    assert "<p>&lt;normal&gt;</p>" in html  # w:val="0": nicht fett, Text maskiert
    assert "<td>A1</td><td>B1</td>" in html


def test_xlsx_to_html_keeps_cell_positions(tmp_path):
    html = office.to_html(make_xlsx(tmp_path / "a.xlsx"))
    assert "Bosse" in html
    assert "<tr><td>Name</td><td></td><td>42</td></tr>" in html
    assert "<tr><td></td><td>Drache</td><td></td></tr>" in html


def test_csv_to_html_detects_semicolons(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Name;Level\nDrache;99\n", encoding="cp1252")
    html = office.to_html(p)
    assert "<th>Name</th><th>Level</th>" in html and "<td>Drache</td><td>99</td>" in html


def test_opendocument_flat_xml(tmp_path):
    p = tmp_path / "a.fodt"
    p.write_text("""<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>
<text:h text:outline-level="2">Quest</text:h><text:p>A<text:s text:c="2"/>B</text:p>
</office:text></office:body></office:document>""", encoding="utf-8")
    html = office.to_html(p)
    assert "<h2>Quest</h2>" in html and "<p>A  B</p>" in html


def test_legacy_binary_needs_a_converter(tmp_path):
    p = tmp_path / "alt.doc"
    p.write_bytes(b"\xd0\xcf\x11\xe0" + b"\0" * 100)
    with pytest.raises(office.Unsupported):
        office.to_html(p)


def test_google_shortcut_url(tmp_path):
    p = tmp_path / "Plan.gsheet"
    p.write_text(json.dumps({"doc_id": "abc123"}), encoding="utf-8")
    assert office.google_url(p) == "https://docs.google.com/spreadsheets/d/abc123/edit"
    p.write_text(json.dumps({"url": "https://docs.google.com/document/d/x/edit"}), encoding="utf-8")
    assert office.google_url(p) == "https://docs.google.com/document/d/x/edit"


# --- Konverter -------------------------------------------------------------


def test_libreoffice_command_uses_own_profile(tmp_path):
    cmd = office.libreoffice_command("soffice", tmp_path / "a.docx", tmp_path / "out", tmp_path / "prof")
    assert cmd[1].startswith("-env:UserInstallation=file:")
    assert cmd[-5:] == ["--convert-to", "pdf", "--outdir", str(tmp_path / "out"), str(tmp_path / "a.docx")]


def test_ms_office_script_quotes_paths():
    cmd = office.ms_office_command(Path("C:/Guides/O'Brien.xlsx"), Path("C:/tmp/o.pdf"))
    body = cmd[-1]
    assert "Excel.Application" in body and "'C:/Guides/O''Brien.xlsx'" in body
    assert office.ms_office_command(Path("a.odg"), Path("o.pdf")) is None  # kein MS-Programm dafuer


# --- Office-Tab --------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from mdeditor.tabs import OfficeTab  # noqa: F401  (QtWebEngine vor der QApplication laden)
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication(["pytest"])


def wait_for(app, condition, seconds: float = 60) -> bool:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    return bool(condition())


def test_office_tab_without_converter_shows_text(qapp, tmp_path, monkeypatch):
    from mdeditor.tabs import OfficeTab

    monkeypatch.setattr(office, "can_convert", lambda _p: False)
    tab = OfficeTab(make_docx(tmp_path / "a.docx"))
    assert tab.mode == "html"
    assert "Kapitel 1" in tab.browser.toPlainText()
    assert tab.print_job() is not None


@pytest.mark.skipif(office.find_libreoffice() is None, reason="LibreOffice nicht installiert")
def test_office_tab_converts_with_libreoffice(qapp, tmp_path):
    from mdeditor.tabs import OfficeTab

    src = tmp_path / "Bericht mit Ümlaut.docx"
    make_docx(src)
    tab = OfficeTab(src)
    assert wait_for(qapp, lambda: tab.mode in ("pdf", "html"), 120)
    assert tab.mode == "pdf", tab.info.text()
    assert tab.pdf.doc.pageCount() >= 1
    assert "LibreOffice" in tab.info.text()
    assert tab.print_job().page_count() == tab.pdf.doc.pageCount()
    shutil.rmtree(tmp_path, ignore_errors=True)
