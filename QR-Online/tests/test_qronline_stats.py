"""Auswertung der Scans: Tage, Wochen, Uhrzeit, Anteile."""
from __future__ import annotations

from datetime import date, timedelta, timezone

from qronline import stats

BERLIN_SUMMER = timezone(timedelta(hours=2))


def rows(*items):
    return [{"ts": ts, "device": dev, "os": os_, "lang": lang} for ts, dev, os_, lang in items]


def test_parse_converts_utc_to_local_day():
    # 22:30 UTC ist in Berlin (Sommerzeit) schon 00:30 am naechsten Tag
    scans = stats.parse(rows(("2026-10-20T22:30:00Z", "Smartphone", "iOS", "de")), BERLIN_SUMMER)
    assert scans[0].time.date() == date(2026, 10, 21)
    assert scans[0].time.hour == 0


def test_parse_skips_broken_rows():
    assert stats.parse([{"ts": "gestern"}, {}, {"ts": None}]) == []


def test_daily_fills_days_without_scans():
    today = date(2026, 10, 21)
    scans = stats.parse(rows(("2026-10-21T08:00:00Z", "Smartphone", "iOS", "de"),
                             ("2026-10-21T09:00:00Z", "Smartphone", "Android", "de"),
                             ("2026-10-19T09:00:00Z", "Computer", "Windows", "en")), timezone.utc)
    per_day = stats.daily(scans, 7, today)
    assert len(per_day) == 7
    assert per_day[0][0] == date(2026, 10, 15)
    assert per_day[-1] == (today, 2)
    assert dict(per_day)[date(2026, 10, 19)] == 1
    assert sum(n for _, n in per_day) == 3


def test_in_range_and_query_since():
    today = date(2026, 10, 21)
    scans = stats.parse(rows(("2026-10-14T23:59:00Z", "Computer", "Windows", "de"),
                             ("2026-10-15T00:00:00Z", "Computer", "Windows", "de")), timezone.utc)
    assert len(stats.in_range(scans, 7, today)) == 1
    # Der Server liefert einen Tag mehr, damit der Zeitzonen-Versatz nichts abschneidet
    assert stats.query_since(7, today) == date(2026, 10, 14)


def test_weekly_groups_by_monday():
    per_day = [(date(2026, 10, 18) + timedelta(days=i), 1) for i in range(9)]  # So .. Mo
    weeks = stats.weekly(per_day)
    assert weeks == [(date(2026, 10, 12), 1), (date(2026, 10, 19), 7), (date(2026, 10, 26), 1)]


def test_hourly_and_weekday():
    scans = stats.parse(rows(("2026-10-19T07:10:00Z", "Smartphone", "iOS", "de"),
                             ("2026-10-19T07:50:00Z", "Smartphone", "iOS", "de")), timezone.utc)
    hours = dict(stats.hourly(scans))
    assert len(hours) == 24 and hours["7"] == 2
    assert dict(stats.by_weekday(scans))["Mo"] == 2


def test_breakdown_groups_rest_as_other():
    items = [("2026-10-19T07:00:00Z", "Smartphone", f"OS{i}", "de") for i in range(8)]
    items += [("2026-10-19T08:00:00Z", "Smartphone", "OS0", "de")]
    result = stats.breakdown(stats.parse(rows(*items)), "os", top=4)
    assert result[0] == ("OS0", 2)
    assert len(result) == 4 and result[-1] == ("Andere", 5)
    assert sum(n for _, n in result) == 9


def test_language_names():
    assert stats.language_name("de") == "Deutsch"
    assert stats.language_name("?") == "unbekannt"
    assert stats.language_name("xx") == "xx"
