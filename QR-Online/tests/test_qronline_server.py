"""server/index.php mit dem PHP-Entwicklungsserver, angesprochen ueber den Client."""
from __future__ import annotations

import shutil
import socket
import sqlite3
import subprocess
import time
from datetime import date
from pathlib import Path

import pytest
import requests

from qronline.client import Client, ServerError

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
KEY = "test-schluessel-0123456789"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
ANDROID = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/130.0 Mobile Safari/537.36")
WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="PHP nicht installiert")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "www"
    shutil.copytree(SERVER_DIR, root, ignore=shutil.ignore_patterns("config.php", "*.sqlite*"))
    (root / "config.php").write_text(
        f"<?php return ['api_key' => '{KEY}', 'db' => __DIR__ . '/data/test.sqlite', "
        "'home' => ''];", encoding="utf-8")
    port = free_port()
    proc = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", str(root), str(root / "index.php")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            requests.get(base, timeout=0.5)
            break
        except requests.ConnectionError:
            time.sleep(0.1)
    yield base, root
    proc.terminate()
    proc.wait(5)


def scan(url: str, ua: str, lang: str = "de-DE,de;q=0.9") -> requests.Response:
    return requests.get(url, headers={"User-Agent": ua, "Accept-Language": lang},
                        allow_redirects=False, timeout=5)


def test_create_scan_and_statistics(server):
    base, root = server
    client = Client(base, KEY)
    client.ping()
    link = client.create("https://example.org/seite?x=1", "Flyer Oktober")
    assert len(link.code) == 6 and link.url == f"{base}/{link.code}"
    assert link.scans == 0

    r = scan(link.url, IPHONE)
    assert r.status_code == 302
    assert r.headers["Location"] == "https://example.org/seite?x=1"
    assert "no-store" in r.headers["Cache-Control"]
    scan(link.url.lower(), ANDROID, "en-US")      # Kleinschreibung geht auch
    scan(f"{base}/index.php?c={link.code}", WINDOWS)  # ohne mod_rewrite
    scan(link.url, "WhatsApp/2.23.20.0")           # Link-Vorschau: kein Scan
    assert requests.head(link.url, headers={"User-Agent": IPHONE}, allow_redirects=False,
                         timeout=5).status_code == 302  # HEAD zaehlt nicht

    rows = client.scans(link.code)
    assert [(r["device"], r["os"], r["lang"]) for r in rows] == [
        ("Smartphone", "iOS", "de"), ("Smartphone", "Android", "en"), ("Computer", "Windows", "de")]
    assert all(r["ts"].endswith("Z") for r in rows)
    assert client.scans(link.code, since=date(2999, 1, 1)) == []

    [listed] = client.links()
    assert listed.scans == 3 and listed.label == "Flyer Oktober" and listed.last_scan

    # Keine IP-Adresse in der Datenbank
    db = sqlite3.connect(root / "data" / "test.sqlite")
    columns = [c[1] for c in db.execute("PRAGMA table_info(scans)")]
    db.close()
    assert columns == ["id", "code", "ts", "device", "os", "lang"]


def test_update_target_and_delete(server):
    base, _root = server
    client = Client(base, KEY)
    link = client.create("https://example.org/alt")
    updated = client.update(link.code, target="https://example.org/neu", label="Neu")
    assert updated.target == "https://example.org/neu" and updated.label == "Neu"
    assert scan(link.url, IPHONE).headers["Location"] == "https://example.org/neu"

    client.delete(link.code)
    assert client.links() == []
    assert scan(link.url, IPHONE).status_code == 404
    with pytest.raises(ServerError, match="gibt es nicht"):
        client.scans(link.code)


def test_rejects_wrong_key_and_bad_targets(server):
    base, _root = server
    with pytest.raises(ServerError, match="API-Schlüssel"):
        Client(base, "falsch").links()
    client = Client(base, KEY)
    for bad in ("javascript:alert(1)", "ftp://example.org", "kein link", ""):
        with pytest.raises(ServerError, match="http"):
            client.create(bad)
    assert scan(f"{base}/ZZZZZZ", IPHONE).status_code == 404


def test_unreachable_server_gives_readable_error():
    with pytest.raises(ServerError, match="nicht erreichbar"):
        Client(f"http://127.0.0.1:{free_port()}", KEY, timeout=2).ping()
    with pytest.raises(ServerError, match="https://"):
        Client("qr.example.de", KEY).ping()


def test_works_without_mod_rewrite(server):
    """Adresse mit index.php: Links lauten dann …/index.php/CODE."""
    base, _root = server
    client = Client(f"{base}/index.php", KEY)
    link = client.create("https://example.org/ohne-rewrite")
    assert link.url == f"{base}/index.php/{link.code}"
    r = scan(link.url, ANDROID)
    assert r.status_code == 302 and r.headers["Location"] == "https://example.org/ohne-rewrite"
    assert len(client.scans(link.code)) == 1


def test_redirect_survives_failing_scan_insert(server):
    """Kann der Scan nicht gespeichert werden, wird trotzdem weitergeleitet."""
    base, root = server
    link = Client(base, KEY).create("https://example.org/immer")
    db = sqlite3.connect(root / "data" / "test.sqlite")
    db.execute("CREATE TRIGGER kaputt BEFORE INSERT ON scans BEGIN SELECT RAISE(ABORT, 'x'); END")
    db.commit()
    db.close()
    r = scan(link.url, IPHONE)
    assert r.status_code == 302 and r.headers["Location"] == "https://example.org/immer"
