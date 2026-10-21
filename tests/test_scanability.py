"""Der entscheidende Test: jedes Preset muss mit Logo bis 25 % lesbar bleiben."""
import pytest
from PIL import Image, ImageDraw

from completionistqr.core import export, presets, render_pil
from completionistqr.core.config import QRDesign

PAYLOAD = "https://example.com/qr-studio?ref=test-1234"


@pytest.fixture(scope="module")
def logo_path(tmp_path_factory):
    # Breites, buntes Test-Logo mit Transparenz
    img = Image.new("RGBA", (400, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, 399, 239], radius=60, fill=(220, 38, 38, 255))
    d.ellipse([140, 40, 260, 200], fill=(255, 255, 255, 255))
    p = tmp_path_factory.mktemp("logo") / "logo.png"
    img.save(p)
    return str(p)


@pytest.mark.parametrize("name", list(presets.builtin()))
@pytest.mark.parametrize("logo_size", [0.0, 0.20, 0.25])
def test_preset_scans(name, logo_size, logo_path):
    d = QRDesign(payload=PAYLOAD).apply_style(presets.builtin()[name])
    if logo_size:
        d.logo_path, d.logo_size = logo_path, logo_size
    img = render_pil.render(d, 800, supersample=2)
    assert export.decode(img) == PAYLOAD, f"{name} mit Logo {logo_size:.0%} nicht lesbar"


def test_export_formats(tmp_path, logo_path):
    d = QRDesign(payload=PAYLOAD, logo_path=logo_path, frame="banner_bottom", caption="SCAN ME",
                 caption_color="#FFFFFF")
    for ext in (".png", ".svg", ".pdf"):
        out = export.save(d, tmp_path / f"qr{ext}", 600)
        assert out.stat().st_size > 1000
    assert export.decode(Image.open(tmp_path / "qr.png")) == PAYLOAD


def test_avif_logo_loads_and_scans(tmp_path):
    from PIL import features

    from completionistqr.core.geometry import load_logo

    if not features.check("avif"):
        pytest.skip("Pillow ohne AVIF")
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([20, 20, 280, 180], fill=(37, 99, 235, 255))
    path = tmp_path / "logo.avif"
    img.save(path, quality=90)
    assert load_logo(str(path)).size == (300, 200)
    d = QRDesign(payload=PAYLOAD, logo_path=str(path), logo_size=0.2)
    assert export.decode(render_pil.render(d, 800, supersample=2)) == PAYLOAD
