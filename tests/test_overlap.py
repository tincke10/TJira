"""Tests for `tjira.overlap` — pure logic, no I/O."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tjira.overlap import (
    find_overlap,
    intervals_overlap,
    parse_time_spent,
    worklog_interval,
)


# ==================== parse_time_spent ====================

@pytest.mark.parametrize(
    "raw, expected_seconds",
    [
        ("1h", 3600),
        ("30m", 1800),
        ("2h 30m", 9000),
        ("2h30m", 9000),
        ("45m", 2700),
        ("1h 0m", 3600),
        ("0h 15m", 900),
        ("4h", 14400),
    ],
)
def test_parse_time_spent_accepts_jira_formats(raw, expected_seconds):
    assert parse_time_spent(raw) == timedelta(seconds=expected_seconds)


def test_parse_time_spent_rejects_empty():
    with pytest.raises(ValueError):
        parse_time_spent("")


def test_parse_time_spent_rejects_garbage():
    with pytest.raises(ValueError):
        parse_time_spent("two hours")


def test_parse_time_spent_rejects_zero():
    with pytest.raises(ValueError):
        parse_time_spent("0m")


# ==================== intervals_overlap ====================

def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 4, 20, h, m, tzinfo=timezone.utc)


def test_intervals_overlap_partial():
    assert intervals_overlap(_dt(9), _dt(10), _dt(9, 30), _dt(10, 30)) is True


def test_intervals_overlap_full_containment():
    assert intervals_overlap(_dt(9), _dt(12), _dt(10), _dt(11)) is True


def test_intervals_back_to_back_do_not_overlap():
    # A ends at 10:00, B starts at 10:00 — no overlap (strict).
    assert intervals_overlap(_dt(9), _dt(10), _dt(10), _dt(11)) is False


def test_intervals_disjoint_do_not_overlap():
    assert intervals_overlap(_dt(9), _dt(10), _dt(11), _dt(12)) is False


def test_intervals_same_start_overlap():
    assert intervals_overlap(_dt(9), _dt(10), _dt(9), _dt(11)) is True


# ==================== worklog_interval ====================

def test_worklog_interval_parses_started_and_duration():
    wl = {
        "started": "2026-04-20T09:00:00.000+0000",
        "timeSpentSeconds": 3600,
    }
    start, end = worklog_interval(wl)
    assert start == _dt(9)
    assert end == _dt(10)


def test_worklog_interval_falls_back_to_time_spent_string():
    """If timeSpentSeconds is missing, parse timeSpent."""
    wl = {
        "started": "2026-04-20T09:00:00.000+0000",
        "timeSpent": "2h 30m",
    }
    start, end = worklog_interval(wl)
    assert end - start == timedelta(hours=2, minutes=30)


def test_worklog_interval_handles_offset_with_colon():
    wl = {
        "started": "2026-04-20T09:00:00.000+00:00",
        "timeSpentSeconds": 1800,
    }
    start, end = worklog_interval(wl)
    assert (end - start) == timedelta(minutes=30)


# ==================== find_overlap ====================

def test_find_overlap_returns_none_when_no_conflict():
    target_start, target_end = _dt(9), _dt(10)
    candidates = [
        {"id": "1", "started": "2026-04-20T11:00:00.000+0000", "timeSpentSeconds": 3600},
    ]
    assert find_overlap(target_start, target_end, candidates) is None


def test_find_overlap_returns_first_conflict():
    target_start, target_end = _dt(9), _dt(11)
    candidates = [
        {"id": "1", "started": "2026-04-20T07:00:00.000+0000", "timeSpentSeconds": 3600},
        {"id": "2", "started": "2026-04-20T10:00:00.000+0000", "timeSpentSeconds": 3600},
        {"id": "3", "started": "2026-04-20T12:00:00.000+0000", "timeSpentSeconds": 3600},
    ]
    hit = find_overlap(target_start, target_end, candidates)
    assert hit is not None
    assert hit["id"] == "2"


def test_find_overlap_ignores_back_to_back():
    target_start, target_end = _dt(10), _dt(11)
    candidates = [
        {"id": "1", "started": "2026-04-20T09:00:00.000+0000", "timeSpentSeconds": 3600},
        {"id": "2", "started": "2026-04-20T11:00:00.000+0000", "timeSpentSeconds": 3600},
    ]
    assert find_overlap(target_start, target_end, candidates) is None
