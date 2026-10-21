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
