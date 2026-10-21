r"""Baut die Programmordner von CompletionistPDF, -MD und -QR mit PyInstaller.

    python build_exe.py            # dist/CompletionistPDF/ (Programmordner)
    python build_exe.py --app md   # der Editor (dist/CompletionistMD/)
    python build_exe.py --app qr   # der QR-Generator (dist/CompletionistQR/)
    python build_exe.py --onefile  # stattdessen eine einzelne .exe (nur noch zum Testen)
    python build_exe.py --console  # mit Konsolenfenster (zeigt Tracebacks)

Verteilt werden die Ordner ueber die Setups (build_setup.ps1): der Start ist
sofort da, weil nichts bei jedem Aufruf in den Temp-Ordner entpackt wird.
    python build_exe.py --workpath %TEMP%\cpdf-build   # falls build/ gesperrt ist

Der Typst-Compiler steckt als native Erweiterung im Python-Paket ``typst``
und wird mit eingesammelt -- eine separate typst.exe ist nicht noetig.

CompletionistMD bringt QtWebEngine (Chromium) mit und wird deshalb deutlich
groesser. Das Tiptap-Bundle muss vorher gebaut sein (build_editor.ps1); der
Quelltext in editor-src/ und das Node in tools/ kommen nicht mit in die .exe.

CompletionistQR bringt als einziges Programm CustomTkinter statt Qt mit und
laeuft deshalb in einem eigenen Fenster. Die Knoepfe "PDF" und "QR" finden die
anderen Programme ueber deren Setup (core/qr_launcher.py).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "icon.ico"

# Was je App gebaut wird: Startskript, Name, Datenordner, eigenes Icon
# Aus assets/ nimmt jede App nur, was sie zur Laufzeit liest: PDF die Schriften,
# MD das Editor-Bundle, beide ihr eigenes Fenster-Icon.
APPS = {
    "pdf": {"script": "main.py", "name": "CompletionistPDF",
            "data": ["templates", "presets", "assets/fonts", "assets/icon_pdf.ico"],
            "icon": "assets/icon_pdf.ico"},
    "md": {"script": "main_md.py", "name": "CompletionistMD",
           "data": ["assets/editor", "assets/filetypes", "assets/icon_md.ico"],
           "icon": "assets/icon_md.ico"},
    "qr": {"script": "run_completionistqr.py", "name": "CompletionistQR",
           "data": ["completionistqr/assets"],
           "icon": "completionistqr/assets/icon.ico"},
}

# Qt-Module, die die App nicht braucht -- spart deutlich Platz.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects", "PySide6.QtStateMachine",
    "PySide6.QtNetwork",
    # Pillow las nur das Emoji-Testbild, das macht jetzt QImage
    # (count_saturated_pixels in core/typst_engine.py). Ohne OpenSSL: die App
    # geht nie ins Netz, hashlib.sha1 kommt ohne _hashlib aus.
    "PIL", "ssl", "_ssl", "_hashlib",
    "tkinter", "unittest", "pydoc",
]

# Der Editor braucht QtWebEngine samt dessen Abhaengigkeiten (WebChannel,
# Qml/Quick, Positioning, OpenGL ...) -- dort nur sicher Unbenutztes weglassen.
EXCLUDES_MD = [
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects",
    # QtPdf/QtPdfWidgets bleiben: PDF-Vorschau-Tab (mdeditor/tabs.py)
    "PySide6.QtQuick3D", "PySide6.QtWebEngineQuick", "PySide6.QtStateMachine",
    "PySide6.QtWebSockets", "PySide6.QtOpenGLWidgets",
    # QtWebEngineWidgets laedt auf Python-Seite nur QtNetwork, QtWebChannel und
    # QtPrintSupport nach; die Quick-/Qml-DLLs selbst bleiben (siehe unten).
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.QtOpenGL",
    "PySide6.QtPositioning",
    "typst", "markdown_it", "mdit_py_plugins", "PIL",
    # ssl/_ssl/_hashlib bleiben: der Google-Drive-Sync spricht HTTPS.
    "tkinter", "unittest", "pydoc",
]

# Dateien, die PyInstaller mit Qt einsammelt, die aber nie geladen werden
# (Pfade relativ zu _internal). Gemessen an einem --onedir-Build, siehe
# CompletionistPDF.md bzw. CompletionistMD.md.
DROP_COMMON = [
    # Software-OpenGL (20 MB): Notloesung fuer Rechner ohne OpenGL-Treiber.
    # Die Widgets-Oberflaeche zeichnet ohne OpenGL, QtWebEngine ueber Direct3D.
    "PySide6/opengl32sw.dll",
    # Qt-Uebersetzungen ausser KEEP_QT_TRANSLATIONS (core/qt_translations.py)
    "PySide6/translations/*.qm",
    # TLS, Netzwerkstatus, Standort, Touch-Eingabegeraete
    "PySide6/plugins/tls/*", "PySide6/plugins/networkinformation/*",
    "PySide6/plugins/position/*", "PySide6/plugins/generic/*",
]
# Pythons OpenSSL -- von den Qt-Apps geht nur MD ins Netz (Google-Drive-Sync, core/drive.py);
# QR nimmt den Filter nicht (install_file_filter nur fuer pdf/md) und behaelt OpenSSL
# Diese Kataloge laedt core/qt_translations.py -- alle Sprachen, damit Ja/Nein und
# Kontextmenues in jeder Systemsprache stimmen (zusammen rund 2 MB).
KEEP_QT_TRANSLATIONS = ("qtbase_", "qtwebengine_")
DROP_NO_TLS = ["libcrypto-*.dll", "libssl-*.dll"]
DROP_MD = [
    # Nur fuer Debug-Builds von Qt bzw. fuer die Chromium-Entwicklerwerkzeuge
    "PySide6/resources/*.debug.*",
    "PySide6/resources/qtwebengine_devtools_resources.pak",
    # Qt-Quick-Module (QML-Dateien und Plugins); QWebEngineView braucht nur
    # die DLLs, die Qt6WebEngineCore.dll direkt laedt.
    "PySide6/qml/*",
    # PDF als Bildformat -- die PDF-Vorschau nutzt QtPdf direkt, nicht dieses Plugin
    "PySide6/plugins/imageformats/qpdf.dll",
]
# Chromium-Oberflaechentexte (Kontextmenue, Fehlerseiten): nur Deutsch und
# Englisch; fehlt die Systemsprache, nimmt Chromium en-US.
KEEP_WEBENGINE_LOCALES = {"de.pak", "en-US.pak", "en-GB.pak"}

# CompletionistQR braucht Tkinter, aber kein Qt und nichts aus der PDF-Kette.
# numpy wurde ganz abgeloest, siehe completionistqr/core/colors.py.
# Der AVIF-Decoder von Pillow (PIL._avif) bleibt seit QR 1.3.0 drin: Logos
# duerfen auch .avif sein.
# ssl/_ssl/_hashlib bleiben (frueher ausgeschlossen): "Datei in Google Drive
# hochladen" spricht HTTPS (core/drive.py, completionistqr/ui/drive_upload.py).
EXCLUDES_QR = [
    "PySide6", "shiboken6", "typst", "markdown_it", "mdit_py_plugins",
    "numpy",
    "pytest", "unittest", "pydoc",
]


def ensure_icon() -> None:
    """Erzeugt ein schlichtes Icon, falls keins vorhanden ist."""
    if ICON.exists():
        return
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([28, 12, 228, 244], radius=26, fill=(0, 137, 123, 255))
    d.polygon([(168, 12), (228, 72), (168, 72)], fill=(0, 96, 86, 255))
    for i, y in enumerate((112, 146, 180)):
        d.rounded_rectangle([64, y, 192 - i * 28, y + 14], radius=7, fill=(255, 255, 255, 235))
    d.rounded_rectangle([64, 66, 140, 90], radius=8, fill=(255, 214, 120, 255))
    ICON.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icon erzeugt: {ICON}")


# Pakete je App, deren Lizenztexte in den Ordner "Lizenzen" der App kommen
# (aus den *.dist-info der .venv). Fehlende Pakete werden uebersprungen.
_QT = ["PySide6", "PySide6_Essentials", "PySide6_Addons", "PySide6_WebEngine", "PySide6_Pdf",
       "shiboken6"]
_NET = ["google-auth", "google-auth-oauthlib", "requests", "requests-oauthlib", "oauthlib",
        "urllib3", "certifi", "idna", "charset-normalizer", "pyasn1", "pyasn1-modules", "rsa",
        "cachetools"]
LICENSE_PACKAGES = {
    "pdf": _QT + ["typst", "markdown-it-py", "mdit-py-plugins", "mdurl", "pyinstaller"],
    "md": _QT + _NET + ["pyinstaller"],
    "qr": ["pillow", "qrcode", "customtkinter", "darkdetect", "packaging", "zxing-cpp",
           "uharfbuzz", "pyinstaller"] + _NET,
}


def collect_licenses(app: str, target: Path) -> Path:
    """Legt ``<Programmordner>/Lizenzen`` an: eigene Lizenz, Fremdkomponenten-Liste,
    Lizenztexte aller mitgelieferten Pakete, Python, ggf. Schriften."""
    from importlib import metadata

    out = target / "Lizenzen"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", out / "LICENSE (Completionist Suite).txt")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", out / "THIRD_PARTY_NOTICES.md")
    py_license = Path(sys.base_prefix) / "LICENSE.txt"
    if py_license.is_file():
        shutil.copyfile(py_license, out / "Python - LICENSE.txt")
    for name in LICENSE_PACKAGES[app]:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        files = [f for f in (dist.files or [])
                 if any(k in f.name.upper() for k in ("LICEN", "COPYING", "NOTICE"))]
        if not files:
            continue
        folder = out / f"{dist.metadata['Name']} {dist.version}"
        folder.mkdir(exist_ok=True)
        for f in files:
            src = Path(dist.locate_file(f))
            if src.is_file():
                shutil.copyfile(src, folder / src.name)
    if app == "qr":
        fonts = ROOT / "completionistqr" / "assets" / "fonts"
        for ofl in fonts.glob("*/OFL.txt"):
            shutil.copyfile(ofl, out / f"Schrift {ofl.parent.name} - OFL.txt")
    if app == "md":
        # Editor-Bundle: Lizenztexte von Tiptap und ProseMirror aus editor-src/node_modules
        nm = ROOT / "editor-src" / "node_modules"
        for pkg in ("@tiptap/core", "prosemirror-model", "prosemirror-view", "prosemirror-state"):
            for lic in (nm / pkg).glob("LICENSE*"):
                shutil.copyfile(lic, out / f"{pkg.replace('/', '-')} - {lic.name}")
    return out


VERSION_PACKAGES = {"pdf": "core", "md": "mdeditor", "qr": "completionistqr"}
DESCRIPTIONS = {"pdf": "Markdown zu PDF mit Typst, PDF-Viewer",
                "md": "WYSIWYG-Markdown-Editor", "qr": "Gestaltete QR-Codes"}


def app_version(app: str) -> str:
    """``__version__`` aus dem Paket der App -- die einzige Stelle mit der Nummer."""
    import re

    init = ROOT / VERSION_PACKAGES[app] / "__init__.py"
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"Keine __version__ in {init}")
    return m.group(1)


def write_version_file(app: str, folder: Path) -> Path:
    """Versionsressource fuer PyInstaller (--version-file)."""
    version = app_version(app)
    nums = ([int(x) for x in version.split(".") if x.isdigit()] + [0, 0, 0, 0])[:4]
    name = APPS[app]["name"]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'Completionist Library'),
      StringStruct('FileDescription', '{name} – {DESCRIPTIONS[app]}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '{name}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('LegalCopyright', '© 2026 Mike-Dominique Horch (Completionist Library)'),
      StringStruct('Comments', 'Lizenz: CC BY-NC-ND 4.0{"" if app == "qr" else "; Qt/PySide6: LGPL v3"}; Kontakt: mail@mike-horch.de')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def install_file_filter(app: str) -> None:
    """Laesst PyInstaller die DROP_*-Dateien und unbenutzte Qt-DLLs weglassen.

    Auf der Kommandozeile kennt PyInstaller nur --exclude-module; Daten und
    DLLs filtert man sonst von Hand in einer .spec-Datei. Hier wird stattdessen
    die Analysis-Klasse umhuellt, die die erzeugte .spec benutzt.
    """
    from fnmatch import fnmatchcase

    from PyInstaller.building import build_main

    patterns = [p.lower() for p in DROP_COMMON + (DROP_MD if app == "md" else DROP_NO_TLS)]
    locales_dir = "pyside6/translations/qtwebengine_locales/"
    keep_locales = {n.lower() for n in KEEP_WEBENGINE_LOCALES}

    def dropped(dest: str) -> bool:
        dest = dest.replace("\\", "/").lower()
        if dest.startswith(locales_dir):
            return dest[len(locales_dir):] not in keep_locales
        if dest.startswith("pyside6/translations/") and dest.endswith(".qm") \
                and dest.rsplit("/", 1)[1].startswith(KEEP_QT_TRANSLATIONS):
            return False
        return any(fnmatchcase(dest, p) for p in patterns)

    class FilteredAnalysis(build_main.Analysis):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            before = len(self.binaries) + len(self.datas)
            self.datas = [e for e in self.datas if not dropped(e[0])]
            self.binaries = drop_unused_qt_dlls([e for e in self.binaries if not dropped(e[0])])
            print(f"Dateifilter: {before - len(self.binaries) - len(self.datas)} Dateien weggelassen")

    build_main.Analysis = FilteredAnalysis


def drop_unused_qt_dlls(binaries: list) -> list:
    """Entfernt DLLs direkt in PySide6/, die keine mitgenommene Datei laedt.

    PyInstallers Qt-Hooks sammeln ganze Modulfamilien ein (Qt Quick 3D, Quick
    Controls, Multimedia ...). Geladen wird davon nur, was ueber die
    Importtabellen der .pyd-Module, Plugins und QtWebEngineProcess.exe
    erreichbar ist -- genau diese Huelle bleibt drin.
    """
    from PyInstaller.depend.bindepend import get_imports

    def is_qt_dll(dest: str) -> bool:
        dest = dest.replace("\\", "/").lower()
        # PySide6 legt die Qt-DLLs (samt FFmpeg fuer QtMultimedia) direkt in den Paketordner
        return dest.startswith("pyside6/") and dest.count("/") == 1 and dest.endswith(".dll")

    by_name = {Path(dest).name.lower(): src for dest, src, _ in binaries}
    todo = [src for dest, src, _ in binaries if not is_qt_dll(dest)]
    reached: set[str] = set()
    while todo:
        for name, _ in get_imports(todo.pop()):
            name = name.lower()
            if name in by_name and name not in reached:
                reached.add(name)
                todo.append(by_name[name])
    return [e for e in binaries if not is_qt_dll(e[0]) or Path(e[0]).name.lower() in reached]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", choices=sorted(APPS), default="pdf",
                        help="pdf = CompletionistPDF (Standard), md = Editor CompletionistMD, "
                             "qr = CompletionistQR")
    parser.add_argument("--onedir", action="store_true",
                        help="Programmordner (Standard; nur noch aus Kompatibilitaet)")
    parser.add_argument("--onefile", action="store_true",
                        help="einzelne .exe statt Programmordner")
    parser.add_argument("--console", action="store_true", help="Konsolenfenster anzeigen")
    parser.add_argument(
        "--distpath", type=Path, default=ROOT / "dist",
        help="Zielordner fuer die fertige .exe (Standard: dist/).",
    )
    parser.add_argument(
        "--workpath", type=Path, default=ROOT / "build",
        help="Ordner fuer Zwischendateien (Standard: build/). Hilft, wenn build/ "
             "von einem anderen Programm gesperrt ist.",
    )
    args = parser.parse_args()

    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("PyInstaller fehlt:  pip install pyinstaller", file=sys.stderr)
        return 1

    app = APPS[args.app]
    name = app["name"]
    # Fremdkomponenten-Liste fuer den Dialog "Über …" (core/legal.py)
    data_dirs = app["data"] + ["THIRD_PARTY_NOTICES.md"]

    if args.app == "md" and not (ROOT / "assets" / "editor" / "tiptap.bundle.js").is_file():
        print("assets/editor/tiptap.bundle.js fehlt -- erst build_editor.ps1 ausfuehren.",
              file=sys.stderr)
        return 1

    if args.app == "qr" and not (ROOT / "completionistqr" / "assets" / "fonts" / "fonts.json").is_file():
        print("Schriftarten fehlen -- erst  python tools/fetch_fonts.py  ausfuehren.",
              file=sys.stderr)
        return 1

    icon = ROOT / app["icon"] if "icon" in app else ICON
    if icon == ICON:
        ensure_icon()

    # Arbeitsreste aus frueheren Kompilierungen nicht mit einpacken
    for d in data_dirs:
        if (ROOT / d).is_dir():
            for junk in (ROOT / d).rglob(".completionistpdf"):
                shutil.rmtree(junk, ignore_errors=True)

    onedir = not args.onefile

    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        str(ROOT / app["script"]),
        "--name", name,
        "--noconfirm",
        "--clean",
        "--onedir" if onedir else "--onefile",
        "--console" if args.console else "--windowed",
        "--icon", str(icon),
        # Version in den Dateieigenschaften der .exe (Explorer -> Details)
        "--version-file", str(write_version_file(args.app, args.workpath / args.app)),
        "--distpath", str(args.distpath),
        "--workpath", str(args.workpath / args.app),
        "--specpath", str(args.workpath / args.app),
        "--paths", str(ROOT),
    ]
    if args.app == "pdf":
        cmd += [
            # Typst: native Erweiterung + Python-Teil
            "--collect-all", "typst",
            # markdown-it laedt Regeln teils dynamisch
            "--collect-submodules", "markdown_it",
            "--collect-submodules", "mdit_py_plugins",
            "--hidden-import", "PySide6.QtPdf",
            "--hidden-import", "PySide6.QtPdfWidgets",
        ]
        excludes = EXCLUDES
    elif args.app == "md":
        cmd += [
            "--hidden-import", "PySide6.QtWebEngineWidgets",
            "--hidden-import", "PySide6.QtWebEngineCore",
            # erst beim Oeffnen eines PDF-Tabs importiert (mdeditor/tabs.py)
            "--hidden-import", "PySide6.QtPdf",
            "--hidden-import", "PySide6.QtPdfWidgets",
        ]
        excludes = EXCLUDES_MD
    else:
        cmd += [
            # CustomTkinter laedt Themes als Dateien, zxing-cpp ist eine native
            # Erweiterung -- beides findet PyInstaller nicht von allein.
            "--collect-data", "customtkinter",
            "--collect-binaries", "zxingcpp",
            # Pillow laedt es erst, wenn Tk ein Bild zeigt (ImageTk) -- ohne stuerzt
            # der Aufbau der Vorlagen-Galerie mit ModuleNotFoundError ab
            "--hidden-import", "PIL._tkinter_finder",
        ]
        excludes = EXCLUDES_QR
    for d in data_dirs:
        # Ziel ist immer ein Ordner: bei einzelnen Dateien der uebergeordnete
        dest = d if (ROOT / d).is_dir() else str(Path(d).parent)
        cmd += ["--add-data", f"{ROOT / d}{sep}{dest}"]
    for mod in excludes:
        cmd += ["--exclude-module", mod]
    if args.app in ("pdf", "md"):
        install_file_filter(args.app)

    print("PyInstaller", " ".join(cmd))
    pyi.run(cmd)

    target = args.distpath / (name if onedir else f"{name}.exe")
    if not onedir:
        bad = verify_onefile(target)
        if bad:
            print(f"\nFEHLER: {len(bad)} Eintrag/Eintraege in {target.name} sind beschaedigt:",
                  file=sys.stderr)
            for entry in bad[:10]:
                print("   ", entry, file=sys.stderr)
            print("Die Datei wurde fehlerhaft auf den Datentraeger geschrieben -- "
                  "neu bauen, ggf. mit --distpath auf ein anderes Laufwerk.", file=sys.stderr)
            return 1
        print("Integritaet geprueft: alle Eintraege entpackbar.")
    if onedir:
        lic = collect_licenses(args.app, target)
        print(f"Lizenzen: {sum(1 for _ in lic.rglob('*') if _.is_file())} Dateien in {lic}")
    print(f"\nFertig: {target}")
    return 0


def verify_onefile(exe: Path) -> list[str]:
    """Entpackt jeden Eintrag der onefile-.exe probeweise im Speicher.

    Genau das tut der Starter bei jedem Programmstart; ein einzelner kaputter
    Block auf dem Datentraeger ("decompression resulted in return code -3")
    faellt so schon beim Bauen auf statt erst beim Anwender.
    """
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    bad = []
    for entry in reader.toc:
        try:
            reader.extract(entry)
        except Exception as exc:  # zlib.error u. a.
            bad.append(f"{entry}: {exc}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
