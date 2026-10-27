"""Lädt die kuratierten Google Fonts (OFL bzw. Apache 2.0) nach completionistqr/assets/fonts.

Aufruf:  .venv\\Scripts\\python.exe tools\\fetch_fonts.py

Pro Familie wird das Verzeichnis im Repository github.com/google/fonts über die
GitHub-API aufgelistet; geladen werden die nicht-kursiven TTF-Dateien und die
Lizenzdatei (OFL.txt bzw. LICENSE.txt). Zum Schluss wird ein Manifest (fonts.json) geschrieben, das
completionistqr/core/fonts.py liest.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "completionistqr" / "assets" / "fonts"

# Anzeigename -> Verzeichnis unter github.com/google/fonts/ofl/ (bzw. apache/..., wenn angegeben)
FAMILIES = {
    "Inter": "inter",
    "Montserrat": "montserrat",
    "Poppins": "poppins",
    "Oswald": "oswald",
    "Bebas Neue": "bebasneue",
    "Anton": "anton",
    "Playfair Display": "playfairdisplay",
    "Lora": "lora",
    "Roboto Mono": "robotomono",
    "Caveat": "caveat",
    # Handschriften; Satisfy kommt der Schrift im Design "Handschrift mit Pfeil" am naechsten
    "Satisfy": "apache/satisfy",
    "Kaushan Script": "kaushanscript",
    "Dancing Script": "dancingscript",
    "Pacifico": "pacifico",
    "Great Vibes": "greatvibes",
    "Permanent Marker": "apache/permanentmarker",
}

API = "https://api.github.com/repos/google/fonts/contents/{}"
HEADERS = {"User-Agent": "CompletionistQR-font-fetcher", "Accept": "application/vnd.github+json"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_family(name: str, path: str) -> dict | None:
    if "/" not in path:
        path = f"ofl/{path}"
    slug = path.rsplit("/", 1)[1]
    listing = json.loads(_get(API.format(path)))
    ttfs = [f for f in listing if f["name"].endswith(".ttf") and "Italic" not in f["name"]]
    if not ttfs:
        print(f"  ! keine TTF-Dateien für {name}")
        return None

    target = DEST / slug
    target.mkdir(parents=True, exist_ok=True)

    entry: dict = {"dir": slug, "regular": None, "bold": None, "variable": False}
    for f in ttfs:
        fname = f["name"]
        # Nur Regular, Bold oder eine Variable-Datei – alles andere wird nicht gebraucht.
        if "[" in fname:
            entry["regular"] = fname
            entry["variable"] = True
        elif fname.endswith("-Regular.ttf"):
            entry["regular"] = fname
        elif fname.endswith("-Bold.ttf"):
            entry["bold"] = fname
        else:
            continue
        (target / fname).write_bytes(_get(f["download_url"]))
        print(f"  + {fname}")

    for f in listing:
        if f["name"] in ("OFL.txt", "LICENSE.txt"):
            (target / f["name"]).write_bytes(_get(f["download_url"]))

    if entry["variable"]:
        entry["bold"] = None  # Fett über die wght-Achse
    return entry if entry["regular"] else None


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    for name, slug in FAMILIES.items():
        print(name)
        try:
            entry = fetch_family(name, slug)
        except Exception as exc:  # Netzwerkfehler: Familie überspringen
            print(f"  ! Fehler: {exc}")
            continue
        if entry:
            manifest[name] = entry
    (DEST / "fonts.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)}/{len(FAMILIES)} Familien geladen -> {DEST}")
    return 0 if len(manifest) == len(FAMILIES) else 1


if __name__ == "__main__":
    sys.exit(main())
