"""Office-Dokumente: Dateiendungen, Umwandlung nach PDF und einfache HTML-Ansicht.

Gedacht fuer die schreibgeschuetzte Office-Ansicht in CompletionistMD und den
Google-Drive-Sync. Ohne Qt, damit es sich testen laesst.

Die originalgetreue Ansicht entsteht als PDF, und zwar mit dem, was auf dem
Rechner installiert ist (``converters``):

1. **LibreOffice** (``soffice --headless --convert-to pdf``) -- kann alle Formate.
   Laeuft mit eigenem Profil, stoert also ein offenes LibreOffice nicht.
2. **Microsoft Office** (nur Windows) -- Word, Excel bzw. PowerPoint exportieren
   per COM (PowerShell) unsichtbar ein PDF, jeweils nur fuer ihre Formate.

Ist keins von beiden da, liest ``to_html`` die modernen Formate (Word/Excel/
PowerPoint ab 2007, OpenDocument, CSV) selbst aus -- nur Text und Tabellen, ohne
Layout. Die alten Binaerformate (``.doc``, ``.xls``, ``.ppt``) gehen nur ueber
einen Konverter.

Google Docs/Tabellen/Praesentationen liegen lokal nur als Verknuepfung
(``.gdoc``, ``.gsheet``, ``.gslides`` von Google Drive fuer Desktop) -- die zeigt
die Ansicht als Link zum Dokument im Browser.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# --- Dateiendungen ------------------------------------------------------- #

WORD_SUFFIXES = (".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm", ".rtf")
EXCEL_SUFFIXES = (".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm", ".csv")
POWERPOINT_SUFFIXES = (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".pot", ".potx", ".potm")
# Word/Excel 2003 als XML ("XML-Dokument", "XML-Tabelle")
MS_XML_SUFFIXES = (".xml",)
OPENDOCUMENT_SUFFIXES = (
    ".odt", ".ott", ".fodt",   # Writer
    ".ods", ".ots", ".fods",   # Calc
    ".odp", ".otp", ".fodp",   # Impress
    ".odg", ".otg", ".fodg",   # Draw
)
# Apple iWork, WPS Office, Works -- LibreOffice kann sie lesen
OTHER_SUFFIXES = (".pages", ".numbers", ".key", ".wps", ".wpt", ".et", ".ett", ".dps", ".dpt")
GOOGLE_SUFFIXES = (".gdoc", ".gsheet", ".gslides", ".gdraw", ".gform")

# Alles, was als Office-Dokument gilt (Ansicht im Editor)
OFFICE_SUFFIXES = (WORD_SUFFIXES + EXCEL_SUFFIXES + POWERPOINT_SUFFIXES + MS_XML_SUFFIXES
                   + OPENDOCUMENT_SUFFIXES + OTHER_SUFFIXES + GOOGLE_SUFFIXES)
# Was der Drive-Sync hochlaedt: die Dateien selbst. Google-Verknuepfungen nicht --
# deren Dokumente liegen ohnehin in Google Drive, hochgeladen kaeme nur ein JSON-Stummel an.
OFFICE_SYNC_SUFFIXES = tuple(s for s in OFFICE_SUFFIXES if s not in GOOGLE_SUFFIXES)


def is_office(path: str | Path) -> bool:
    return str(path).lower().endswith(OFFICE_SUFFIXES)


def is_google(path: str | Path) -> bool:
    return str(path).lower().endswith(GOOGLE_SUFFIXES)


def family(path: str | Path) -> str:
    """"word", "excel", "powerpoint", "google" oder "other" -- fuer Icon und MS-Office-Weg."""
    p = str(path).lower()
    if p.endswith(GOOGLE_SUFFIXES):
        return "google"
    if p.endswith(WORD_SUFFIXES + (".odt", ".ott", ".fodt", ".pages", ".wps", ".wpt")):
        return "word"
    if p.endswith(EXCEL_SUFFIXES + (".ods", ".ots", ".fods", ".numbers", ".et", ".ett")):
        return "excel"
    if p.endswith(POWERPOINT_SUFFIXES + (".odp", ".otp", ".fodp", ".key", ".dps", ".dpt")):
        return "powerpoint"
    return "other"


# --- Konverter ----------------------------------------------------------- #


def find_libreoffice() -> str | None:
    """Pfad zu ``soffice`` oder None."""
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    candidates: list[Path] = []
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
                if env == "LOCALAPPDATA":
                    candidates.append(Path(base) / "Programs" / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    else:
        candidates += [Path("/usr/bin/soffice"), Path("/usr/lib/libreoffice/program/soffice"),
                       Path("/opt/libreoffice/program/soffice")]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def libreoffice_command(soffice: str, source: Path, out_dir: Path, profile_dir: Path) -> list[str]:
    """Befehl, der ``source`` als PDF nach ``out_dir`` schreibt (Name: ``<Stamm>.pdf``)."""
    return [
        soffice,
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--headless", "--invisible", "--norestore", "--nodefault", "--nolockcheck",
        "--convert-to", "pdf", "--outdir", str(out_dir), str(source),
    ]


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


# PowerShell: Office unsichtbar starten, schreibgeschuetzt oeffnen, als PDF
# exportieren, ohne Speichern schliessen. Makros bleiben aus (AutomationSecurity 3).
_MS_SCRIPTS = {
    "word": """
$app = New-Object -ComObject Word.Application
try {{
  $app.Visible = $false; $app.DisplayAlerts = 0; $app.AutomationSecurity = 3
  $doc = $app.Documents.Open({src}, $false, $true, $false)
  $doc.ExportAsFixedFormat({dst}, 17)
  $doc.Close(0)
}} finally {{ $app.Quit() }}
""",
    "excel": """
$app = New-Object -ComObject Excel.Application
try {{
  $app.Visible = $false; $app.DisplayAlerts = $false; $app.AutomationSecurity = 3
  $book = $app.Workbooks.Open({src}, 0, $true)
  $book.ExportAsFixedFormat(0, {dst})
  $book.Close($false)
}} finally {{ $app.Quit() }}
""",
    "powerpoint": """
$app = New-Object -ComObject PowerPoint.Application
try {{
  $app.AutomationSecurity = 3
  $pres = $app.Presentations.Open({src}, -1, 0, 0)
  $pres.SaveAs({dst}, 32)
  $pres.Close()
}} finally {{ $app.Quit() }}
""",
}


def ms_office_command(source: Path, target: Path) -> list[str] | None:
    """PowerShell-Befehl fuer den PDF-Export ueber Microsoft Office (nur Windows)."""
    script = _MS_SCRIPTS.get(family(source))
    if script is None:
        return None
    body = "$ErrorActionPreference = 'Stop'\n" + script.format(src=_ps_quote(source), dst=_ps_quote(target))
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", body]


def ms_office_available(kind: str) -> bool:
    """Ist Word/Excel/PowerPoint als COM-Server registriert?"""
    if sys.platform != "win32":
        return False
    prog = {"word": "Word.Application", "excel": "Excel.Application",
            "powerpoint": "PowerPoint.Application"}.get(kind)
    if prog is None:
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog + r"\CLSID"))
        return True
    except OSError:
        return False


def can_convert(source: Path) -> bool:
    """Gibt es auf diesem Rechner einen Weg zur originalgetreuen PDF-Ansicht?"""
    return not is_google(source) and (find_libreoffice() is not None or ms_office_available(family(source)))


def converters(source: Path, out_dir: Path, profile_dir: Path | None = None) -> list[tuple[str, list[str], Path]]:
    """Moegliche Wege zum PDF, bester zuerst: (Name, Befehl, erwartete PDF-Datei).
    ``profile_dir``: LibreOffice-Profil (Standard: ``out_dir/lo-profile``)."""
    out: list[tuple[str, list[str], Path]] = []
    if is_google(source):
        return out
    soffice = find_libreoffice()
    if soffice:
        out.append(("LibreOffice",
                    libreoffice_command(soffice, source, out_dir, profile_dir or out_dir / "lo-profile"),
                    out_dir / (source.stem + ".pdf")))
    kind = family(source)
    if ms_office_available(kind):
        target = out_dir / (source.stem + ".ms.pdf")
        cmd = ms_office_command(source, target)
        if cmd:
            name = {"word": "Microsoft Word", "excel": "Microsoft Excel",
                    "powerpoint": "Microsoft PowerPoint"}[kind]
            out.append((name, cmd, target))
    return out


# --- Google-Verknuepfungen ---------------------------------------------- #

_GOOGLE_PATHS = {".gdoc": "document", ".gsheet": "spreadsheets", ".gslides": "presentation",
                 ".gdraw": "drawings", ".gform": "forms"}


def google_url(path: Path) -> str | None:
    """Adresse des Dokuments aus einer ``.gdoc``/``.gsheet``/``.gslides``-Verknuepfung."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    url = data.get("url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    doc_id = data.get("doc_id") or data.get("resource_id", "").rpartition(":")[2]
    if doc_id:
        return f"https://docs.google.com/{_GOOGLE_PATHS.get(path.suffix.lower(), 'document')}/d/{doc_id}/edit"
    return None


# --- Eingebaute Ansicht: Text und Tabellen als HTML ---------------------- #

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
}
MAX_ROWS = 2000      # je Tabellenblatt -- riesige Tabellen sollen die Ansicht nicht lahmlegen
MAX_COLS = 60
STYLE = """
<style>
body { font-family: 'Segoe UI', sans-serif; font-size: 10.5pt; }
table { border-collapse: collapse; margin: 6px 0 14px 0; }
td, th { border: 1px solid #94a3b8; padding: 2px 6px; vertical-align: top; }
th { background: #e2e8f0; }
h2.sheet { font-size: 12pt; margin-top: 16px; }
p.slide { color: #64748b; font-size: 9pt; margin-top: 18px; border-top: 1px solid #cbd5e1; }
</style>
"""


class Unsupported(Exception):
    """Dieses Format kann die eingebaute Ansicht nicht lesen."""


def _q(ns: str, tag: str) -> str:
    return f"{{{NS[ns]}}}{tag}"


def _esc(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def _table(rows: list[list[str]], header: bool = False) -> str:
    rows = [r[:MAX_COLS] for r in rows[:MAX_ROWS]]
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    out = ["<table>"]
    for n, row in enumerate(rows):
        cell = "th" if header and n == 0 else "td"
        out.append("<tr>" + "".join(f"<{cell}>{_esc(c)}</{cell}>" for c in row + [""] * (width - len(row)))
                   + "</tr>")
    out.append("</table>")
    return "".join(out)


def _switched_on(rpr, tag: str) -> bool:
    """Fett/kursiv in den Zeichen-Eigenschaften eines Word-Laufs (``<w:b/>``, ``<w:b w:val="0"/>``)."""
    el = rpr.find(_q("w", tag)) if rpr is not None else None
    return el is not None and el.get(_q("w", "val"), "true") not in ("0", "false")


def _docx(z: zipfile.ZipFile) -> str:
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(_q("w", "body"))
    if body is None:
        return ""

    def para(p) -> str:
        parts = []
        for run in p.iter(_q("w", "r")):
            text ="".join((t.text or "") if t.tag == _q("w", "t") else "\t" if t.tag == _q("w", "tab")
                           else "\n" if t.tag in (_q("w", "br"), _q("w", "cr")) else ""
                           for t in run)
            if not text:
                continue
            rpr = run.find(_q("w", "rPr"))
            chunk = _esc(text)
            if _switched_on(rpr, "b"):
                chunk = f"<b>{chunk}</b>"
            if _switched_on(rpr, "i"):
                chunk = f"<i>{chunk}</i>"
            parts.append(chunk)
        content = "".join(parts)
        style = p.find(f"{_q('w', 'pPr')}/{_q('w', 'pStyle')}")
        name = (style.get(_q("w", "val"), "") if style is not None else "").lower()
        m = re.match(r"(?:heading|berschrift|titre|titolo)\D*(\d)", name)
        if name == "title":
            return f"<h1>{content}</h1>"
        if m:
            level = min(6, int(m.group(1)) + 1)
            return f"<h{level}>{content}</h{level}>"
        if p.find(f"{_q('w', 'pPr')}/{_q('w', 'numPr')}") is not None:
            return f"<ul><li>{content}</li></ul>"
        return f"<p>{content or '&nbsp;'}</p>"

    def cell_text(tc) -> str:
        return "\n".join("".join(t.text or "" for t in p.iter(_q("w", "t"))) for p in tc.iter(_q("w", "p")))

    out = []
    for el in body:
        if el.tag == _q("w", "p"):
            out.append(para(el))
        elif el.tag == _q("w", "tbl"):
            rows = [[cell_text(tc) for tc in tr.findall(_q("w", "tc"))] for tr in el.findall(_q("w", "tr"))]
            out.append(_table(rows))
    return "\n".join(out)


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def _xlsx(z: zipfile.ZipFile) -> str:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_q("s", "si")):
            shared.append("".join(t.text or "" for t in si.iter(_q("s", "t"))))
    book = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in z.namelist():
        for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall(_q("rel", "Relationship")):
            target = rel.get("Target", "")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rels[rel.get("Id")] = target
    out = []
    sheets = book.find(_q("s", "sheets"))
    for n, sheet in enumerate(sheets if sheets is not None else [], 1):
        part = rels.get(sheet.get(_q("r", "id")), f"xl/worksheets/sheet{n}.xml")
        if part not in z.namelist():
            continue
        rows: list[list[str]] = []
        for row in ET.fromstring(z.read(part)).iter(_q("s", "row")):
            if len(rows) >= MAX_ROWS:
                break
            r = int(row.get("r", len(rows) + 1)) - 1
            while len(rows) < r:
                rows.append([])
            values: list[str] = []
            for c in row.findall(_q("s", "c")):
                col = _col_index(c.get("r", "")) if c.get("r") else len(values)
                if col >= MAX_COLS:
                    continue
                kind = c.get("t", "")
                v = c.find(_q("s", "v"))
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(_q("s", "t")))
                elif v is None:
                    text = ""
                elif kind == "s":
                    idx = int(v.text or 0)
                    text = shared[idx] if idx < len(shared) else ""
                elif kind == "b":
                    text = "WAHR" if v.text == "1" else "FALSCH"
                else:
                    text = v.text or ""
                values += [""] * (col - len(values))
                values.append(text)
            rows.append(values)
        out.append(f"<h2 class='sheet'>{_esc(sheet.get('name', f'Blatt {n}'))}</h2>" + _table(rows))
    return "\n".join(out)


def _pptx(z: zipfile.ZipFile) -> str:
    def number(name: str) -> int:
        m = re.search(r"(\d+)\.xml$", name)
        return int(m.group(1)) if m else 0

    slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=number)
    out = []
    for n, name in enumerate(slides, 1):
        root = ET.fromstring(z.read(name))
        out.append(f"<p class='slide'>Folie {n}</p>")
        for p in root.iter(_q("a", "p")):
            text = "".join(t.text or "" for t in p.iter(_q("a", "t")))
            if text.strip():
                out.append(f"<p>{_esc(text)}</p>")
    return "\n".join(out)


def _odf_text(el) -> str:
    """Text eines ODF-Elements samt Leerzeichen-, Tab- und Umbruch-Elementen."""
    parts = [el.text or ""]
    for child in el:
        if child.tag == _q("text", "s"):
            parts.append(" " * int(child.get(_q("text", "c"), "1")))
        elif child.tag == _q("text", "tab"):
            parts.append("\t")
        elif child.tag == _q("text", "line-break"):
            parts.append("\n")
        else:
            parts.append(_odf_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _odf_table(table, named: bool) -> str:
    rows = []
    for row in table.iter(_q("table", "table-row")):
        if len(rows) >= MAX_ROWS:
            break
        values = []
        for cell in row:
            if cell.tag not in (_q("table", "table-cell"), _q("table", "covered-table-cell")):
                continue
            text = "\n".join(_odf_text(p) for p in cell.findall(_q("text", "p")))
            repeat = min(int(cell.get(_q("table", "number-columns-repeated"), "1")), MAX_COLS)
            values += [text] * repeat
        while values and not values[-1].strip():
            values.pop()
        repeat = int(row.get(_q("table", "number-rows-repeated"), "1"))
        rows += [values] * (min(repeat, MAX_ROWS - len(rows)) if values else 1)
    # Blattnamen nur in Tabellendokumenten; in Writer heissen Tabellen "Tabelle1" …
    name = table.get(_q("table", "name"), "") if named else ""
    return (f"<h2 class='sheet'>{_esc(name)}</h2>" if name else "") + _table(rows)


def _odf_block(el, out: list[str], sheets: bool = False) -> None:
    for child in el:
        if child.tag == _q("text", "h"):
            level = min(6, int(child.get(_q("text", "outline-level"), "1")))
            out.append(f"<h{level}>{_esc(_odf_text(child))}</h{level}>")
        elif child.tag == _q("text", "p"):
            text = _odf_text(child)
            out.append(f"<p>{_esc(text) if text else '&nbsp;'}</p>")
        elif child.tag == _q("text", "list"):
            items = []
            for item in child.iter(_q("text", "list-item")):
                text = " ".join(_odf_text(p) for p in item.findall(_q("text", "p")))
                if text:
                    items.append(f"<li>{_esc(text)}</li>")
            out.append("<ul>" + "".join(items) + "</ul>")
        elif child.tag == _q("table", "table"):
            out.append(_odf_table(child, sheets))
        elif child.tag == _q("draw", "page"):
            out.append(f"<p class='slide'>{_esc(child.get(_q('draw', 'name'), 'Folie'))}</p>")
            _odf_block(child, out, sheets)
        else:
            _odf_block(child, out, sheets or child.tag == _q("office", "spreadsheet"))


def _odf(root) -> str:
    body = root.find(_q("office", "body"))
    out: list[str] = []
    if body is not None:
        _odf_block(body, out)
    return "\n".join(out)


def _csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    return _table(list(csv.reader(io.StringIO(text), dialect)), header=True)


def to_html(path: Path) -> str:
    """Text und Tabellen des Dokuments als schlichtes HTML. ``Unsupported`` fuer
    Formate, die es nur mit LibreOffice/Office zu sehen gibt."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return STYLE + _csv(path.read_bytes())
    if suffix in (".fodt", ".fods", ".fodp", ".fodg"):
        return STYLE + _odf(ET.fromstring(path.read_bytes()))
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "word/document.xml" in names:
                return STYLE + _docx(z)
            if "xl/workbook.xml" in names:
                return STYLE + _xlsx(z)
            if any(n.startswith("ppt/slides/") for n in names):
                return STYLE + _pptx(z)
            if "content.xml" in names:
                return STYLE + _odf(ET.fromstring(z.read("content.xml")))
    except zipfile.BadZipFile:
        pass
    except (KeyError, ET.ParseError) as exc:
        raise Unsupported(f"Datei beschädigt oder unbekannter Aufbau ({exc})") from exc
    raise Unsupported("Dieses Format lässt sich ohne LibreOffice oder Microsoft Office nicht anzeigen.")
