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
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtWebChannel", "PyQt6.QtWebSockets",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DExtras", "PyQt6.Qt3DInput",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization", "PyQt6.QtBluetooth", "PyQt6.QtNfc",
    "PyQt6.QtPositioning", "PyQt6.QtLocation", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtDesigner",
    "PyQt6.QtHelp", "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets", "PyQt6.QtSpatialAudio",
    "PyQt6.QtTextToSpeech", "PyQt6.QtRemoteObjects", "PyQt6.QtStateMachine",
    "PyQt6.QtNetwork",
    # Pillow las nur das Emoji-Testbild, das macht jetzt QImage
    # (count_saturated_pixels in core/typst_engine.py). Ohne OpenSSL: die App
    # geht nie ins Netz, hashlib.sha1 kommt ohne _hashlib aus.
    "PIL", "ssl", "_ssl", "_hashlib",
    "tkinter", "unittest", "pydoc",
]

# Der Editor braucht QtWebEngine samt dessen Abhaengigkeiten (WebChannel,
# Qml/Quick, Positioning, OpenGL ...) -- dort nur sicher Unbenutztes weglassen.
EXCLUDES_MD = [
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DExtras", "PyQt6.Qt3DInput",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization", "PyQt6.QtBluetooth", "PyQt6.QtNfc",
    "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtSql", "PyQt6.QtTest",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtSpatialAudio",
    "PyQt6.QtTextToSpeech", "PyQt6.QtRemoteObjects",
    # QtPdf/QtPdfWidgets bleiben: PDF-Vorschau-Tab (mdeditor/tabs.py)
    "PyQt6.QtQuick3D", "PyQt6.QtWebEngineQuick", "PyQt6.QtStateMachine",
    "PyQt6.QtWebSockets", "PyQt6.QtOpenGLWidgets",
    # QtWebEngineWidgets laedt auf Python-Seite nur QtNetwork, QtWebChannel und
    # QtPrintSupport nach; die Quick-/Qml-DLLs selbst bleiben (siehe unten).
    "PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets", "PyQt6.QtOpenGL",
    "PyQt6.QtPositioning",
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
    "PyQt6/Qt6/bin/opengl32sw.dll",
    # Qt-Uebersetzungen: keine der Apps installiert einen QTranslator.
    "PyQt6/Qt6/translations/*.qm",
    # TLS, Netzwerkstatus, Standort, Touch-Eingabegeraete
    "PyQt6/Qt6/plugins/tls/*", "PyQt6/Qt6/plugins/networkinformation/*",
    "PyQt6/Qt6/plugins/position/*", "PyQt6/Qt6/plugins/generic/*",
]
# Pythons OpenSSL -- von den Qt-Apps geht nur MD ins Netz (Google-Drive-Sync, core/drive.py);
# QR nimmt den Filter nicht (install_file_filter nur fuer pdf/md) und behaelt OpenSSL
DROP_NO_TLS = ["libcrypto-*.dll", "libssl-*.dll"]
DROP_MD = [
    # Nur fuer Debug-Builds von Qt bzw. fuer die Chromium-Entwicklerwerkzeuge
    "PyQt6/Qt6/resources/*.debug.*",
    "PyQt6/Qt6/resources/qtwebengine_devtools_resources.pak",
    # Qt-Quick-Module (QML-Dateien und Plugins); QWebEngineView braucht nur
    # die DLLs, die Qt6WebEngineCore.dll direkt laedt.
    "PyQt6/Qt6/qml/*",
    # PDF als Bildformat -- die PDF-Vorschau nutzt QtPdf direkt, nicht dieses Plugin
    "PyQt6/Qt6/plugins/imageformats/qpdf.dll",
]
# Chromium-Oberflaechentexte (Kontextmenue, Fehlerseiten): nur Deutsch und
# Englisch; fehlt die Systemsprache, nimmt Chromium en-US.
KEEP_WEBENGINE_LOCALES = {"de.pak", "en-US.pak", "en-GB.pak"}

# CompletionistQR braucht Tkinter, aber kein Qt und nichts aus der PDF-Kette.
# Dazu ein Brocken, den Pillow sonst mitschleppt:
#   PIL._avif        AVIF-Decoder, 7,5 MB -- die App liest PNG/JPG/WebP
# numpy wurde ganz abgeloest, siehe completionistqr/core/colors.py.
# ssl/_ssl/_hashlib bleiben (frueher ausgeschlossen): "Datei in Google Drive
# hochladen" spricht HTTPS (core/drive.py, completionistqr/ui/drive_upload.py).
EXCLUDES_QR = [
    "PyQt6", "typst", "markdown_it", "mdit_py_plugins",
    "numpy",
    "PIL.AvifImagePlugin", "PIL._avif",
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
      StringStruct('CompanyName', 'Completionist Suite'),
      StringStruct('FileDescription', '{name} – {DESCRIPTIONS[app]}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '{name}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('LegalCopyright', 'CC BY-NC-ND 4.0')])]),
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
    locales_dir = "pyqt6/qt6/translations/qtwebengine_locales/"
    keep_locales = {n.lower() for n in KEEP_WEBENGINE_LOCALES}

    def dropped(dest: str) -> bool:
        dest = dest.replace("\\", "/").lower()
        if dest.startswith(locales_dir):
            return dest[len(locales_dir):] not in keep_locales
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
    """Entfernt DLLs aus PyQt6/Qt6/bin, die keine mitgenommene Datei laedt.

    PyInstallers Qt-Hooks sammeln ganze Modulfamilien ein (Qt Quick 3D, Quick
    Controls, Multimedia ...). Geladen wird davon nur, was ueber die
    Importtabellen der .pyd-Module, Plugins und QtWebEngineProcess.exe
    erreichbar ist -- genau diese Huelle bleibt drin.
    """
    from PyInstaller.depend.bindepend import get_imports

    def is_qt_dll(dest: str) -> bool:
        dest = dest.replace("\\", "/").lower()
        return dest.startswith("pyqt6/qt6/bin/") and dest.endswith(".dll")

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
    data_dirs = app["data"]

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
            "--hidden-import", "PyQt6.QtPdf",
            "--hidden-import", "PyQt6.QtPdfWidgets",
        ]
        excludes = EXCLUDES
    elif args.app == "md":
        cmd += [
            "--hidden-import", "PyQt6.QtWebEngineWidgets",
            "--hidden-import", "PyQt6.QtWebEngineCore",
            # erst beim Oeffnen eines PDF-Tabs importiert (mdeditor/tabs.py)
            "--hidden-import", "PyQt6.QtPdf",
            "--hidden-import", "PyQt6.QtPdfWidgets",
        ]
        excludes = EXCLUDES_MD
    else:
        cmd += [
            # CustomTkinter laedt Themes als Dateien, zxing-cpp ist eine native
            # Erweiterung -- beides findet PyInstaller nicht von allein.
            "--collect-data", "customtkinter",
            "--collect-binaries", "zxingcpp",
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
