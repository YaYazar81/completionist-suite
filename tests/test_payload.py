from completionistqr.core import payload


def test_wifi_escaping():
    s = payload.wifi('My;Net', 'p\\a;ss:"x"', "WPA")
    assert s == 'WIFI:T:WPA;S:My\\;Net;P:p\\\\a\\;ss\\:\\"x\\";;'


def test_wifi_open_network_has_no_password():
    assert payload.wifi("Gast", "geheim", "nopass") == "WIFI:T:nopass;S:Gast;;"


def test_vcard_umlauts_and_escaping():
    s = payload.vcard(first="Jürgen", last="Müller", org="Firma, GmbH", phone="+49 170 1234")
    assert "N:Müller;Jürgen;;;" in s
    assert "FN:Jürgen Müller" in s
    assert "ORG:Firma\\, GmbH" in s
    assert s.startswith("BEGIN:VCARD") and s.endswith("END:VCARD")


def test_url_adds_scheme():
    assert payload.url("example.com") == "https://example.com"
    assert payload.url("http://x.de") == "http://x.de"


def test_epc_girocode():
    s = payload.epc("Max Mustermann", "DE89 3704 0044 0532 0130 00", "12,5", "Rechnung 42")
    assert s.split("\n") == ["BCD", "002", "1", "SCT", "", "Max Mustermann",
                             "DE89370400440532013000", "EUR12.50", "", "", "Rechnung 42"]
    assert len(s.encode("utf-8")) <= 331


def test_epc_rejects_bad_iban_and_amount():
    import pytest

    with pytest.raises(ValueError, match="IBAN"):
        payload.epc("A", "DE89 3704 0044 0532 0130 01")
    with pytest.raises(ValueError, match="Betrag"):
        payload.epc("A", "DE89370400440532013000", "0")
    assert payload.epc("A", "DE89370400440532013000").endswith("DE89370400440532013000")


def test_amount_formats():
    assert payload.epc("A", "DE89370400440532013000", "1.234,56").split("\n")[7] == "EUR1234.56"
    assert payload.epc("A", "DE89370400440532013000", "7").split("\n")[7] == "EUR7.00"


def test_paypal_whatsapp_social_feedback():
    assert payload.paypal("@max", "5") == "https://paypal.me/max/5.00EUR"
    assert payload.paypal("https://paypal.me/max") == "https://paypal.me/max"
    assert payload.whatsapp("0170 123 4567", "Hallo du") == "https://wa.me/491701234567?text=Hallo%20du"
    assert payload.whatsapp("+43 660 1234567") == "https://wa.me/436601234567"
    assert payload.social("tiktok", "@name") == "https://www.tiktok.com/@name"
    assert payload.social("instagram", "https://instagram.com/x") == "https://instagram.com/x"
    assert payload.feedback("", "a@b.de") == "mailto:a@b.de?subject=Feedback"
    assert payload.feedback("forms.gle/abc") == "https://forms.gle/abc"


def test_maps_link():
    assert payload.maps("52,52", "13.405") == "https://www.google.com/maps/search/?api=1&query=52.52,13.405"
    assert payload.maps(address="Unter den Linden 1, Berlin").endswith("Unter%20den%20Linden%201%2C%20Berlin")


def test_batch_csv_and_export(tmp_path):
    from completionistqr.core import batch
    from completionistqr.core.config import QRDesign

    csv_file = tmp_path / "liste.csv"
    csv_file.write_text("Dateiname;Link\nStand A;https://a.example\n;https://b.example\n\n",
                        encoding="utf-8-sig")
    rows = batch.read_rows(csv_file)
    assert rows == [("https://a.example", "Stand A"), ("https://b.example", "")]
    files, bad = batch.export_all(QRDesign(), rows, tmp_path / "out", ".png", 256, 150)
    assert [f.name for f in files] == ["Stand_A.png", "b.example.png"]
    assert bad == []


def test_batch_without_header(tmp_path):
    from completionistqr.core import batch

    f = tmp_path / "x.csv"
    f.write_text("https://a.de,Erster\nhttps://b.de,Zweiter\n", encoding="utf-8")
    assert batch.read_rows(f) == [("https://a.de", "Erster"), ("https://b.de", "Zweiter")]


def test_short_formats():
    assert payload.email("a@b.de", "Hallo Welt") == "mailto:a@b.de?subject=Hallo%20Welt"
    assert payload.phone("+49 30 123") == "tel:+4930123"
    assert payload.sms("0170 1", "Hi") == "SMSTO:01701:Hi"
    assert payload.geo("52,52", "13.405") == "geo:52.52,13.405"
