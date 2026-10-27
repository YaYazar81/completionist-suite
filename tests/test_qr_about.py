"""Fenster "Über CompletionistQR": Links in den Reitern werden erkannt."""
from __future__ import annotations

import pytest

about = pytest.importorskip("completionistqr.ui.about", exc_type=ImportError)


def test_links_and_mail_addresses_are_found():
    text = ("Kontakt\nE-Mail: kontakt@completionist-library.de oder via\n"
            "GitHub: https://github.com/YaYazar81/completionist-suite.\n"
            "(siehe https://creativecommons.org/licenses/by-nc-nd/4.0/deed.de)")
    links = [m.group() for m in about.LINK_RE.finditer(text)]
    assert links == ["kontakt@completionist-library.de",
                     "https://github.com/YaYazar81/completionist-suite",
                     "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.de"]
    assert about._target(links[0]) == "mailto:kontakt@completionist-library.de"
    assert about._target(links[1]) == links[1]
