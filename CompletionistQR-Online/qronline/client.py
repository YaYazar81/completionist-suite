"""Die paar Aufrufe der Server-API (server/index.php)."""
from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import date

import requests
import urllib3.util.connection as _urllib3_connection

# Verbindungsaufbau hoechstens so lange, Antwort hoechstens so lange (Sekunden)
TIMEOUT = (8, 20)

_create_connection = _urllib3_connection.create_connection


def _connect_ipv4_first(address, *args, **kwargs):
    """IPv4 zuerst, IPv6 nur als Ausweg.

    urllib3 probiert die Adressen eines Servers nacheinander und wartet bei jeder bis zur
    Zeitueberschreitung. Hat der Server eine IPv6-Adresse, die vom Anschluss aus nicht
    erreichbar ist (haeufig bei Heim-Routern), hing so jeder Verbindungsaufbau rund zehn
    Sekunden, bevor es mit IPv4 klappte -- Browser probieren beides parallel und merken
    davon nichts. Verbunden wird mit der IP-Adresse, Zertifikat und Servername (SNI)
    bleiben die des Hosts."""
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


_urllib3_connection.create_connection = _connect_ipv4_first


class ServerError(Exception):
    """Server nicht erreichbar oder Anfrage abgelehnt; die Meldung ist für die Oberfläche."""


@dataclass
class Link:
    code: str
    target: str
    label: str
    created: str
    scans: int
    last_scan: str | None
    url: str  # die Adresse, die im QR-Code steht

    @property
    def title(self) -> str:
        return self.label or self.target


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float | tuple = TIMEOUT,
                 session: requests.Session | None = None):
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    def short_url(self, code: str) -> str:
        return f"{self.base_url}/{code}"

    def _call(self, method: str, path: str, json: dict | None = None, params: dict | None = None):
        if not self.base_url.lower().startswith(("http://", "https://")):
            raise ServerError("Bitte unter „Server …“ die Adresse mit https:// eintragen.")
        try:
            r = self.session.request(method, f"{self.base_url}/api/{path}", json=json, params=params,
                                     headers={"X-Api-Key": self.api_key}, timeout=self.timeout,
                                     allow_redirects=False)
        except requests.RequestException as exc:
            raise ServerError(f"Server nicht erreichbar: {exc}") from exc
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code >= 400 or data is None:
            msg = data.get("error") if isinstance(data, dict) else None
            raise ServerError(msg or f"Unerwartete Antwort vom Server (HTTP {r.status_code}). "
                                     "Liegt index.php unter dieser Adresse?")
        return data

    def _link(self, row: dict) -> Link:
        return Link(code=row["code"], target=row["target"], label=row.get("label") or "",
                    created=row["created"], scans=int(row.get("scans") or 0),
                    last_scan=row.get("last_scan"),
                    # Mit eigener kurzer Domain (config.php: short_url) liefert der Server die Adresse
                    url=row.get("url") or self.short_url(row["code"]))

    def ping(self) -> None:
        self._call("GET", "ping")

    def links(self) -> list[Link]:
        return [self._link(r) for r in self._call("GET", "links")]

    def create(self, target: str, label: str = "") -> Link:
        return self._link(self._call("POST", "links", json={"target": target, "label": label}))

    def update(self, code: str, target: str | None = None, label: str | None = None) -> Link:
        data = {k: v for k, v in (("target", target), ("label", label)) if v is not None}
        return self._link(self._call("POST", f"links/{code}", json=data))

    def delete(self, code: str) -> None:
        self._call("DELETE", f"links/{code}")

    def scans(self, code: str, since: date | None = None) -> list[dict]:
        params = {"since": since.isoformat()} if since else None
        return self._call("GET", f"scans/{code}", params=params)
