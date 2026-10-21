"""Gesamter Zustand eines QR-Designs.

Die GUI schreibt in ein QRDesign, die Renderer lesen daraus. Dasselbe Objekt
ist als JSON zugleich das Preset-Format.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

MODULE_STYLES = ["square", "gapped_square", "circle", "rounded", "diamond",
                 "vertical_bars", "horizontal_bars"]
EYE_STYLES = ["square", "rounded", "circle", "leaf", "dots"]
GRADIENTS = ["none", "linear", "radial"]
FRAMES = ["none", "thin", "card", "banner_bottom", "banner_top", "ticket"]
ECC_LEVELS = ["L", "M", "Q", "H"]

# Felder, die zum Inhalt gehören und beim Anwenden eines Presets erhalten bleiben.
CONTENT_FIELDS = {"payload", "logo_path"}


@dataclass
class QRDesign:
    # Inhalt
    payload: str = "https://example.com"
    ecc: str = "H"
    border: int = 4  # Quiet Zone in Modulen

    # Module
    module_style: str = "square"
    fg_color: str = "#000000"
    bg_color: str = "#FFFFFF"
    transparent_bg: bool = False
    gradient: str = "none"
    gradient_color: str = "#3B82F6"
    gradient_angle: int = 45

    # Augen (Finder-Patterns)
    eye_outer_style: str = "square"
    eye_inner_style: str = "square"
    eye_custom_color: bool = False
    eye_outer_color: str = "#000000"
    eye_inner_color: str = "#000000"

    # Logo
    logo_path: str = ""
    logo_size: float = 0.20  # Anteil an der Codebreite
    logo_plate: bool = True
    logo_plate_color: str = "#FFFFFF"
    logo_radius: float = 0.25  # Eckenradius der Unterlage relativ zu ihrer Größe
    logo_padding: float = 0.08  # Innenabstand relativ zur Logo-Größe

    # Rahmen & Beschriftung
    frame: str = "none"
    frame_color: str = "#000000"
    caption: str = ""
    caption_font: str = "Montserrat"
    caption_bold: bool = True
    caption_size: int = 100  # Prozent der automatisch berechneten Maximalgröße
    caption_color: str = "#000000"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QRDesign":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def apply_style(self, style: dict) -> "QRDesign":
        """Übernimmt ein Preset auf Basis der Standardwerte; Inhalt, Logo und
        ein selbst getippter Beschriftungstext bleiben erhalten."""
        data = QRDesign().to_dict()
        for k in (*CONTENT_FIELDS, "ecc", "caption", "logo_size", "logo_plate",
                  "logo_radius", "logo_padding"):
            data[k] = getattr(self, k)
        data.update({k: v for k, v in style.items() if k not in CONTENT_FIELDS})
        return QRDesign.from_dict(data)

    def style_dict(self) -> dict:
        return {k: v for k, v in self.to_dict().items() if k not in CONTENT_FIELDS}
