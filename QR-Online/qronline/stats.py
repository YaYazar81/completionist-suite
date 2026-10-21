"""Auswertung der Scans für die Graphen.

Der Server liefert jeden Scan mit Zeit in UTC; gezählt wird nach lokaler Zeit
(ein Scan um 23:30 Uhr gehört zum selben Tag, auch wenn es in UTC schon morgen ist).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
LANGUAGES = {"de": "Deutsch", "en": "Englisch", "fr": "Französisch", "es": "Spanisch",
             "it": "Italienisch", "nl": "Niederländisch", "pl": "Polnisch", "tr": "Türkisch",
             "ru": "Russisch", "uk": "Ukrainisch", "pt": "Portugiesisch", "ar": "Arabisch",
             "zh": "Chinesisch", "ja": "Japanisch", "ko": "Koreanisch", "cs": "Tschechisch",
             "da": "Dänisch", "sv": "Schwedisch", "no": "Norwegisch", "nb": "Norwegisch",
             "fi": "Finnisch", "el": "Griechisch", "hu": "Ungarisch", "ro": "Rumänisch",
             "hr": "Kroatisch", "sr": "Serbisch", "bg": "Bulgarisch", "fa": "Persisch"}


def language_name(code: str) -> str:
    if code in ("", "?"):
        return "unbekannt"
    return LANGUAGES.get(code, code)


@dataclass(frozen=True)
class Scan:
    time: datetime  # lokale Zeit
    device: str
    os: str
    lang: str


def parse(rows: list[dict], tz: tzinfo | None = None) -> list[Scan]:
    out = []
    for r in rows:
        try:
            t = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        out.append(Scan(t.astimezone(tz), r.get("device") or "?", r.get("os") or "?",
                        r.get("lang") or "?"))
    return out


def query_since(days: int, today: date) -> date:
    """Ab wann der Server liefern soll: einen Tag Puffer für den Zeitzonen-Versatz."""
    return today - timedelta(days=days)


def in_range(scans: list[Scan], days: int, today: date) -> list[Scan]:
    first = today - timedelta(days=days - 1)
    return [s for s in scans if first <= s.time.date() <= today]


def daily(scans: list[Scan], days: int, today: date) -> list[tuple[date, int]]:
    """Scans je Tag der letzten ``days`` Tage, auch Tage ohne Scan (0)."""
    counts = Counter(s.time.date() for s in scans)
    first = today - timedelta(days=days - 1)
    return [(d, counts.get(d, 0)) for d in (first + timedelta(days=i) for i in range(days))]


def weekly(per_day: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """Fasst Tageswerte zu Wochen zusammen (Schlüssel: Montag der Woche)."""
    counts: dict[date, int] = {}
    for d, n in per_day:
        monday = d - timedelta(days=d.weekday())
        counts[monday] = counts.get(monday, 0) + n
    return sorted(counts.items())


def hourly(scans: list[Scan]) -> list[tuple[str, int]]:
    counts = Counter(s.time.hour for s in scans)
    return [(f"{h}", counts.get(h, 0)) for h in range(24)]


def by_weekday(scans: list[Scan]) -> list[tuple[str, int]]:
    counts = Counter(s.time.weekday() for s in scans)
    return [(name, counts.get(i, 0)) for i, name in enumerate(WEEKDAYS)]


def breakdown(scans: list[Scan], attr: str, top: int = 6) -> list[tuple[str, int]]:
    """Häufigste Werte eines Merkmals (device, os, lang); der Rest als „Andere“."""
    counts = Counter(getattr(s, attr) for s in scans).most_common()
    if len(counts) > top:
        counts = counts[:top - 1] + [("Andere", sum(n for _, n in counts[top - 1:]))]
    return counts
