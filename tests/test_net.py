"""IPv4 zuerst beim Verbindungsaufbau (core/net.py) -- ohne Netz."""
import socket

import urllib3.util.connection as urllib3_connection

from core import net


def test_installed_once():
    assert urllib3_connection.create_connection is net._connect_ipv4_first
    net.install()
    assert net._create_connection is not net._connect_ipv4_first


def test_core_drive_uses_it():
    from core import drive

    drive.DriveClient(session=object())  # mit eigener Sitzung: kein Google-Import
    assert urllib3_connection.create_connection is net._connect_ipv4_first


def test_ipv4_address_first(monkeypatch):
    families, calls = [], []

    def getaddrinfo(host, port, family=0, *args, **kwargs):
        families.append(family)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    def connect(address, *args, **kwargs):
        calls.append(address)
        if address[0] == "192.0.2.1":
            raise OSError("nicht erreichbar")
        return "sock"

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(net, "_create_connection", connect)
    assert net._connect_ipv4_first(("www.googleapis.com", 443), timeout=5) == "sock"
    assert families == [socket.AF_INET]
    assert calls == [("192.0.2.1", 443), ("192.0.2.2", 443)]


def test_without_ipv4_the_normal_way(monkeypatch):
    def getaddrinfo(*args, **kwargs):
        raise socket.gaierror("keine IPv4-Adresse")

    calls = []
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(net, "_create_connection", lambda address, *a, **k: calls.append(address) or "sock")
    assert net._connect_ipv4_first(("v6only.example", 443)) == "sock"
    assert calls == [("v6only.example", 443)]
