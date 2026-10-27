"""Design-System Completionist Pro: Stylesheet, Icons und QR-Theme passen zusammen."""
import ast
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import design  # noqa: E402


def _qapp():
    return QApplication.instance() or QApplication([])


def test_stylesheet_has_no_unresolved_tokens():
    for theme in ("dark", "light"):
        qss = design.stylesheet(theme)
        assert qss
        assert not re.findall(r"@[a-z_]+", qss.split("*/", 1)[1]), theme


def test_tinted_arrows_exist():
    qss = design.stylesheet("dark")
    for url in re.findall(r'url\("([^"]+)"\)', qss):
        assert Path(url).is_file(), url


def test_all_used_icons_exist():
    """Jeder Icon-Name in icon(...), icon=... und den _tool/_button/act-Helfern hat eine SVG-Datei."""
    helpers = {"icon", "_tool", "_button", "act"}
    name_like = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
    used = set()
    for folder in ("core", "gui", "mdeditor"):
        for py in (ROOT / folder).glob("*.py"):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                values = [k.value for k in node.keywords if k.arg == "icon"]
                if func in helpers:
                    values += node.args
                used |= {v.value for v in values if isinstance(v, ast.Constant)
                         and isinstance(v.value, str) and name_like.match(v.value)}
    known = {p.stem for p in design.ICON_DIR.glob("*.svg")}
    assert {"bold", "zoom-in", "folder-tree", "qr-code"} <= used
    assert used - known == set()


def test_icon_follows_state():
    _qapp()
    ico = design.icon("bold")
    assert not ico.isNull()
    normal = ico.pixmap(QSize(20, 20), QIcon.Mode.Normal, QIcon.State.Off).toImage()
    checked = ico.pixmap(QSize(20, 20), QIcon.Mode.Normal, QIcon.State.On).toImage()
    assert normal != checked
    assert design.icon("does-not-exist").isNull()


def test_qr_tokens_match_design():
    tree = ast.parse((ROOT / "completionistqr" / "ui" / "style.py").read_text(encoding="utf-8"))
    pairs = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()
             and isinstance(n.value, ast.Tuple)}
    for name in ("BG", "PANEL", "INPUT", "BORDER", "HOVER", "TEXT", "MUTED", "ACCENT_BG",
                 "ACCENT", "ACCENT_HI", "WARN", "DANGER"):
        key = name.lower()
        assert pairs[name] == (design.LIGHT[key], design.DARK[key]), name
    for icon in pairs["ICONS"]:
        for variant in ("light", "dark", "accent_light", "accent_dark"):
            assert (ROOT / "completionistqr" / "assets" / "icons" / f"{icon}_{variant}.png").is_file()


def test_qr_theme_is_valid_ctk_theme():
    theme = json.loads((ROOT / "completionistqr" / "assets" / "theme" / "completionist_pro.json")
                       .read_text(encoding="utf-8"))
    # customtkinter ruft .keys() auf jedem Eintrag auf
    assert all(isinstance(v, dict) for v in theme.values())
    assert theme["CTk"]["fg_color"] == [design.LIGHT["bg"], design.DARK["bg"]]
    assert theme["CTkFrame"]["corner_radius"] == 6
