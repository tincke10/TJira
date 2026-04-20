"""Tests para manejo de timezones y parsing de fechas del usuario."""

from __future__ import annotations

from datetime import datetime

import pytest

from tjira.tz import get_timezone, parse_user_datetime, to_jira_datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


def test_get_timezone_honors_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "America/Argentina/Buenos_Aires")
    tz = get_timezone()
    assert tz is not None
    assert str(tz) == "America/Argentina/Buenos_Aires"


def test_get_timezone_falls_back_to_local_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JIRA_TIMEZONE", raising=False)
    tz = get_timezone()
    assert tz is not None  # algún tz siempre


def test_get_timezone_ignores_invalid_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "Not/A/Real/Timezone")
    tz = get_timezone()
    # Cae al local; el invariante es que no explota y devuelve algo.
    assert tz is not None


def test_to_jira_datetime_formats_correctly():
    if ZoneInfo is None:
        pytest.skip("zoneinfo no disponible")
    dt = datetime(2026, 4, 20, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
    result = to_jira_datetime(dt)
    assert result == "2026-04-20T14:30:00.000+0000"


def test_to_jira_datetime_adds_tz_when_naive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    naive = datetime(2026, 4, 20, 9, 0, 0)
    result = to_jira_datetime(naive)
    assert result.startswith("2026-04-20T09:00:00.000")
    assert result.endswith("+0000")


def test_parse_user_datetime_iso_date_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    dt = parse_user_datetime("2026-04-20")
    assert dt.year == 2026 and dt.month == 4 and dt.day == 20
    assert dt.hour == 9 and dt.minute == 0  # default 09:00
    assert dt.tzinfo is not None


def test_parse_user_datetime_iso_datetime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    dt = parse_user_datetime("2026-04-20 14:30")
    assert dt.hour == 14 and dt.minute == 30


def test_parse_user_datetime_dd_mm_yyyy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    dt = parse_user_datetime("20/04/2026")
    assert dt.year == 2026 and dt.month == 4 and dt.day == 20


def test_parse_user_datetime_raises_on_unknown_format():
    with pytest.raises(ValueError, match="Formato de fecha"):
        parse_user_datetime("yesterday")
