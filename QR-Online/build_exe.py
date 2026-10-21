r"""Baut den Programmordner dist\QR-Online\ mit PyInstaller.

    python build_exe.py            # dist\QR-Online\QR-Online.exe (Programmordner)
    python build_exe.py --console  # mit Konsolenfenster (zeigt Tracebacks)

Bewusst ein Ordner statt einer einzelnen .exe: die .exe selbst bleibt klein und
startet sofort, weil nichts bei jedem Aufruf in den Temp-Ordner entpackt wird.
Verteilt wird der Ordner ueber das Setup (build_setup.ps1).

Das Programmsymbol ist vorerst das von CompletionistQR.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "QR-Online"
ICON = ROOT.parent / "completionistqr" / "assets" / "icon.ico"
# Pakete, deren Lizenztexte in den Ordner Lizenzen kommen
LICENSED = ["requests", "urllib3", "certifi", "idna", "charset-normalizer", "customtkinter",
            "darkdetect", "qrcode", "pillow", "matplotlib", "contourpy", "cycler", "fonttools",
            "kiwisolver", "numpy", "packaging", "pyparsing", "python-dateutil", "six"]


def app_version() -> str:
    text = (ROOT / "qronline" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("Keine __version__ in qronline/__init__.py")
    return m.group(1)


def write_version_file(folder: Path) -> Path:
    """Versionsressource fuer PyInstaller (Explorer -> Eigenschaften -> Details)."""
    version = app_version()
    nums = ([int(x) for x in version.split(".") if x.isdigit()] + [0, 0, 0, 0])[:4]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'Completionist Library'),
      StringStruct('FileDescription', '{NAME} – QR-Codes mit Scan-Statistik'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('ProductName', '{NAME}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('LegalCopyright', '© 2026 Mike-Dominique Horch (Completionist Library)'),
      StringStruct('Comments', 'Lizenz: CC BY-NC-ND 4.0; Kontakt: mail@mike-horch.de')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def collect_licenses(target: Path) -> Path:
    """Eigene Lizenz und die Lizenztexte der mitgelieferten Pakete nach Lizenzen\\."""
    from importlib import metadata

    out = target / "Lizenzen"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT.parent / "LICENSE", out / "QR-Online - LICENSE.txt")
    for pkg in LICENSED:
        try:
            dist = metadata.distribution(pkg)
        except metadata.PackageNotFoundError:
            continue
        for f in dist.files or []:
            if re.search(r"(LICEN[CS]E|COPYING|NOTICE)", f.name, re.I) and "dist-info" in str(f):
                src = Path(dist.locate_file(f))
                if src.is_file():
                    shutil.copyfile(src, out / f"{pkg} - {f.name}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--console", action="store_true", help="mit Konsolenfenster")
    parser.add_argument("--distpath", type=Path, default=ROOT / "dist")
    parser.add_argument("--workpath", type=Path, default=ROOT / "build")
    args = parser.parse_args()
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("PyInstaller fehlt:  pip install pyinstaller", file=sys.stderr)
        return 1

    cmd = [
        str(ROOT / "run_qronline.py"),
        "--name", NAME,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console" if args.console else "--windowed",
        "--icon", str(ICON),
        "--version-file", str(write_version_file(args.workpath)),
        "--distpath", str(args.distpath),
        "--workpath", str(args.workpath),
        "--specpath", str(args.workpath),
        "--paths", str(ROOT),
        # CustomTkinter laedt seine Themes als Dateien
        "--collect-data", "customtkinter",
        # charts.py wird erst nach dem Fensteraufbau importiert
        "--hidden-import", "qronline.charts",
        "--hidden-import", "matplotlib.backends.backend_tkagg",
    ]
    # Andere matplotlib-Oberflaechen braucht die App nicht
    for mod in ("PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "gi", "IPython",
                "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_wxagg",
                "matplotlib.backends.backend_gtk3agg", "matplotlib.backends.backend_gtk4agg"):
        cmd += ["--exclude-module", mod]
    print("PyInstaller", " ".join(cmd))
    pyi.run(cmd)

    target = args.distpath / NAME
    lic = collect_licenses(target)
    print(f"Lizenzen: {sum(1 for _ in lic.iterdir())} Dateien in {lic}")
    print(f"\nFertig: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
