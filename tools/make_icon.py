"""Erzeugt completionistqr/assets/icon.ico aus completionistqr/assets/icon_source.png.

    python tools\\make_icon.py                 # aus dem hinterlegten Quellbild
    python tools\\make_icon.py bild.png        # aus einem anderen Bild

Das Quellbild sollte quadratisch und mindestens 256x256 gross sein; ein
transparenter Hintergrund bleibt erhalten. Die .ico bekommt alle Groessen, die
Windows braucht -- vom Explorer-Symbol bis zur Kachel.

Frueher erzeugte dieses Skript ein Platzhalter-Icon aus einem gerenderten
QR-Code. Es ueberschreibt icon.ico, laeuft aber nicht mehr automatisch beim
Build mit.
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "completionistqr" / "assets"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS / "icon_source.png"
    if not source.is_file():
        print(f"Quellbild fehlt: {source}", file=sys.stderr)
        return 1

    img = Image.open(source).convert("RGBA")
    if img.width != img.height:
        print(f"Warnung: {img.width}x{img.height} ist nicht quadratisch -- "
              "Windows verzerrt das Symbol.", file=sys.stderr)

    out = ASSETS / "icon.ico"
    # Pillow skaliert jede Groesse mit LANCZOS aus diesem Bild; deshalb das
    # grosse Original uebergeben und nicht vorher verkleinern.
    img.save(out, format="ICO", sizes=SIZES)
    print(f"{out}  ({', '.join(f'{w}x{h}' for w, h in SIZES)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
