"""Packt das WordPress-Plugin als Zip zum Hochladen (Plugins → Plugin hochladen).

    python wordpress/build_zip.py   ->  dist/completionistqr-online-tracker.zip
"""
from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "completionistqr-online-tracker"


def build(out: Path = HERE.parent / "dist" / "completionistqr-online-tracker.zip") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PLUGIN.rglob("*")):
            if f.is_file():
                # WordPress erwartet den Plugin-Ordner als oberste Ebene im Zip
                z.write(f, f.relative_to(HERE).as_posix())
    return out


if __name__ == "__main__":
    print(build())
