"""Verbindungsaufbau: IPv4 zuerst, IPv6 nur als Ausweg.

urllib3 (unter requests und google-auth) probiert die Adressen eines Servers nacheinander
und wartet bei jeder bis zur Zeitueberschreitung. Hat der Server eine IPv6-Adresse, die vom
Anschluss aus nicht erreichbar ist (haeufig bei Heim-Routern), hing so jeder
Verbindungsaufbau zehn Sekunden und mehr, bevor es mit IPv4 klappte -- Browser probieren
beides parallel und merken davon nichts. Verbunden wird mit der IP-Adresse, Zertifikat und
Servername (SNI) bleiben die des Hosts.

Der Import genuegt; ``install()`` wirkt nur einmal.
"""
from __future__ import annotations

import socket

import urllib3.util.connection as _urllib3_connection

_create_connection = _urllib3_connection.create_connection


def _connect_ipv4_first(address, *args, **kwargs):
    host, port = address
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)}
    except (socket.gaierror, UnicodeError):
        addrs = set()
    for ip in sorted(addrs):
        try:
            return _create_connection((ip, port), *args, **kwargs)
        except OSError:
            continue
    return _create_connection(address, *args, **kwargs)


def install() -> None:
    if _urllib3_connection.create_connection is _create_connection:
        _urllib3_connection.create_connection = _connect_ipv4_first


install()
