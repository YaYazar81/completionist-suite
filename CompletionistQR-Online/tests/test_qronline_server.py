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


def php_args() -> list[str]:
    """php mit pdo_sqlite; laedt die Erweiterung bei Bedarf (z. B. das PHP der
    Windows-Runner von GitHub hat sie nicht aktiviert)."""
    php = shutil.which("php")
    for extra in ([], ["-d", f"extension_dir={Path(php).resolve().parent / 'ext'}",
                       "-d", "extension=pdo_sqlite", "-d", "extension=sqlite3"]):
        mods = subprocess.run([php, *extra, "-m"], capture_output=True, text=True).stdout
        if "pdo_sqlite" in mods.lower():
            return [php, *extra]
    pytest.skip("PHP ohne pdo_sqlite")


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
    proc = subprocess.Popen([*php_args(), "-S", f"127.0.0.1:{port}", "-t", str(root), str(root / "index.php")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    # Warten, bis der Server antwortet. Die erste Anfrage legt die Datenbank an und
    # braucht auf langsamen Rechnern (Windows-Runner) laenger -- auch Timeouts abwarten.
    deadline = time.monotonic() + 20
    while True:
        try:
            requests.get(base, timeout=5)
            break
        except requests.RequestException:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail("PHP-Server ist nicht angelaufen")
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


def test_short_domain_from_config(server):
    """Eigene kurze Domain (config.php: short_url): der Server liefert die Adresse für den
    QR-Code mit, App und WordPress-Plugin übernehmen sie."""
    base, root = server
    (root / "config.php").write_text(
        f"<?php return ['api_key' => '{KEY}', 'db' => __DIR__ . '/data/test.sqlite', "
        "'home' => '', 'short_url' => 'https://c10t.de/'];", encoding="utf-8")
    client = Client(base, KEY)
    link = client.create("https://example.org/kurz")
    assert link.url == f"https://c10t.de/{link.code}"
    assert [x.url for x in client.links()] == [link.url]
    assert client.update(link.code, label="Kurz").url == link.url
    ping = requests.get(f"{base}/api/ping", headers={"X-Api-Key": KEY}, timeout=5).json()
    assert ping["short_url"] == "https://c10t.de"
    # Gezählt und weitergeleitet wird unter jeder Adresse, die auf den Ordner zeigt
    r = scan(f"{base}/{link.code}", ANDROID)
    assert r.status_code == 302 and r.headers["Location"] == "https://example.org/kurz"


def test_prepared_server_folder_works(tmp_path):
    """„Server einrichten" in der App: der vorbereitete Ordner (mit erzeugtem Schlüssel)
    läuft so, wie er ist, auf dem Webspace."""
    from qronline import server_files

    key = server_files.generate_key()
    assert len(key) == 48 and key != server_files.generate_key()
    root = server_files.write_server_files(tmp_path / "upload", key)
    names = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert names == [".htaccess", "config.php", "data/.htaccess", "index.php"]
    config = (root / "config.php").read_text(encoding="utf-8")
    assert f"'api_key' => '{key}'" in config and "HIER-" not in config
    lint = subprocess.run([*php_args(), "-l", str(root / "config.php")], capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr

    port = free_port()
    proc = subprocess.Popen([*php_args(), "-S", f"127.0.0.1:{port}", "-t", str(root), str(root / "index.php")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                requests.get(base, timeout=5)
                break
            except requests.RequestException:
                if time.monotonic() > deadline:
                    pytest.fail("PHP-Server ist nicht angelaufen")
                time.sleep(0.1)
        assert server_files.check_connection(base, key) == ""
        assert "falsch" in server_files.check_connection(base, "y" * 48)
        link = Client(base, key).create("https://example.org/neu")
        assert scan(f"{base}/{link.code}", ANDROID).status_code == 302
    finally:
        proc.terminate()
        proc.wait(5)


def test_config_rejects_unsafe_keys():
    from qronline import server_files

    for bad in ("kurz", "mit'anfuehrung'und-mehr-als-16", "x" * 10):
        with pytest.raises(ValueError):
            server_files.config_php(bad)
    assert "'short_url' => 'https://c10t.de'" in server_files.config_php("a" * 32, "c10t.de/")


def test_connects_ipv4_first(monkeypatch):
    """Eine unerreichbare IPv6-Adresse darf den Verbindungsaufbau nicht aufhalten: der
    Client verbindet zuerst über IPv4, IPv6 nur, wenn es keine IPv4-Adresse gibt."""
    import socket as socketmod

    from qronline import client as clientmod

    server = socketmod.socket(socketmod.AF_INET, socketmod.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    real = socketmod.getaddrinfo
    seen = []

    def fake_getaddrinfo(host, p, family=0, *args, **kwargs):
        seen.append((host, family))
        if host == "qr.example.test":
            if family == socketmod.AF_INET:
                return real("127.0.0.1", p, socketmod.AF_INET, *args, **kwargs)
            raise AssertionError("IPv6 nicht zuerst fragen")
        return real(host, p, family, *args, **kwargs)

    monkeypatch.setattr(clientmod.socket, "getaddrinfo", fake_getaddrinfo)
    sock = clientmod._connect_ipv4_first(("qr.example.test", port), 3)
    assert sock.getpeername() == ("127.0.0.1", port)
    sock.close()
    server.close()

    # Ohne IPv4-Adresse: der normale Weg (dort auch IPv6)
    calls = []
    monkeypatch.setattr(clientmod, "_create_connection", lambda address, *a, **k: calls.append(address))
    monkeypatch.setattr(clientmod.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(socketmod.gaierror("keine A-Adresse")))
    clientmod._connect_ipv4_first(("nur-ipv6.example.test", 443), 3)
    assert calls == [("nur-ipv6.example.test", 443)]
