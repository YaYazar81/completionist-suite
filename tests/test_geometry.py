import pytest

from completionistqr.core import render_svg
from completionistqr.core.config import EYE_STYLES, FRAMES, MODULE_STYLES, QRDesign
from completionistqr.core.geometry import Layer, build_scene
from completionistqr.core.matrix import build


def test_matrix_size_and_finders():
    m = build("hello", "H")
    assert m.size == 17 + 4 * m.version
    assert m.finder_origins() == [(0, 0), (m.size - 7, 0), (0, m.size - 7)]
    # Finder-Pattern: Außenring dunkel, Ring darin hell, Kern dunkel
    assert m.dark(0, 0) and not m.dark(1, 1) and m.dark(3, 3)


def _module_layer(scene):
    return [i for i in scene.items if isinstance(i, Layer)][-1]


@pytest.mark.parametrize("style", MODULE_STYLES)
def test_every_module_style_produces_shapes(style):
    scene = build_scene(QRDesign(payload="test", module_style=style))
    assert len(_module_layer(scene).shapes) > 10


def test_module_count_matches_matrix_for_squares():
    d = QRDesign(payload="abc")
    m = build(d.payload, d.ecc)
    dark = sum(m.dark(x, y) and not m.in_finder(x, y) for y in range(m.size) for x in range(m.size))
    shapes = _module_layer(build_scene(d, matrix=m)).shapes
    assert len(shapes) == dark + 3 * 2  # + Ring und Pupille je Auge


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("eye", EYE_STYLES)
def test_frames_and_eyes_render_svg(frame, eye):
    d = QRDesign(payload="x", frame=frame, eye_outer_style=eye, eye_inner_style=eye,
                 caption="SCAN ME", gradient="linear")
    svg = render_svg.render(d, 256)
    assert svg.startswith("<svg") and "linearGradient" in svg
    assert "SCAN ME" in svg


def _text(scene):
    from completionistqr.core.geometry import TextItem

    return next(i for i in scene.items if isinstance(i, TextItem))


@pytest.mark.parametrize("frame", ["none", "thin", "card", "arrow"])
def test_caption_above_or_below(frame):
    below = build_scene(QRDesign(payload="x", frame=frame, caption="Scan mich"))
    above = build_scene(QRDesign(payload="x", frame=frame, caption="Scan mich", caption_position="top"))
    assert (below.width, below.height) == (above.width, above.height)
    _, oy, _, n = below.code_box
    assert _text(below).baselines[0] > oy + n  # Schrift unter dem Code
    _, oy, _, _ = above.code_box
    assert _text(above).baselines[-1] < oy  # Schrift über dem Code


def test_arrow_points_at_the_card_and_turns_with_the_caption():
    def arrow(position):
        d = QRDesign(payload="x", frame="arrow", caption="Scan mich", arrow_color="#123456",
                     caption_position=position)
        scene = build_scene(d)
        layer = next(i for i in scene.items if isinstance(i, Layer) and i.paint.color == "#123456")
        head = layer.shapes[-1].points
        return scene, head[0], [p for p in layer.shapes[0].points]

    scene, tip, shaft = arrow("bottom")
    ox = scene.code_box[0]
    assert tip[0] < ox and all(x < ox for x, _ in shaft)  # links neben der Karte
    assert shaft[0][1] > tip[1]  # von der Schrift unten nach oben
    scene2, tip2, shaft2 = arrow("top")
    assert tip2 == pytest.approx((tip[0], scene2.height - tip[1]))  # gespiegelt
    assert shaft2[0][1] < tip2[1]


def test_handwriting_fonts_are_bundled():
    from completionistqr.core import fonts

    for family in ("Satisfy", "Kaushan Script", "Dancing Script", "Pacifico", "Great Vibes",
                   "Permanent Marker"):
        assert family in fonts.families()
        path, _ = fonts.font_file(family)
        assert fonts.FONT_DIR in path.parents


def test_arrow_frame_in_svg_and_pdf(tmp_path):
    from completionistqr.core import export

    d = QRDesign(payload="x", frame="arrow", caption="MapGenie.io", caption_font="Satisfy",
                 arrow_color="#03485B", caption_position="top", transparent_bg=True)
    for ext in (".svg", ".pdf", ".png"):
        out = export.save(d, tmp_path / f"qr{ext}", 400)
        assert out.stat().st_size > 1000
    assert 'fill="#03485B"' in (tmp_path / "qr.svg").read_text(encoding="utf-8")
