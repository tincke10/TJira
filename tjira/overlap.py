"""Worklog overlap detection — pure functions, no I/O.

Definitions:
    - An interval is a half-open range ``[start, end)``.
    - Two intervals overlap iff ``a.start < b.end and b.start < a.end``.
    - Back-to-back (``a.end == b.start``) does NOT overlap by design — that is
      how worklogs naturally chain (09:00-10:00 followed by 10:00-11:00).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Match "1h", "30m", "2h 30m", "2h30m" — at least one of hours/minutes required.
_TIME_SPENT_RE = re.compile(
    r"^\s*(?:(?P<hours>\d+)\s*h)?\s*(?:(?P<minutes>\d+)\s*m)?\s*$"
)


def parse_time_spent(raw: str) -> timedelta:
    """Parse a Jira ``timeSpent`` string (``1h``, ``30m``, ``2h 30m``).

    Raises ``ValueError`` on empty input, malformed input, or zero duration.
    """
    if not raw or not raw.strip():
        raise ValueError("time_spent is empty")

    match = _TIME_SPENT_RE.match(raw)
    if not match or (match.group("hours") is None and match.group("minutes") is None):
        raise ValueError(f"Unrecognized time spent: {raw!r}")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    delta = timedelta(hours=hours, minutes=minutes)
    if delta <= timedelta(0):
        raise ValueError(f"time_spent must be positive: {raw!r}")
    return delta


def _parse_jira_started(started: str) -> datetime:
    """Parse Jira's ISO ``started`` field. Accepts ``+0000`` and ``+00:00``."""
    # Python's fromisoformat() handles "+00:00" but not "+0000" — normalize.
    iso = started
    if len(iso) >= 5 and iso[-5] in "+-" and iso[-3] != ":":
        iso = f"{iso[:-2]}:{iso[-2:]}"
    return datetime.fromisoformat(iso)


def worklog_interval(worklog: dict) -> tuple[datetime, datetime]:
    """Return ``(start, end)`` for an existing Jira worklog dict.

    Prefers ``timeSpentSeconds`` (server-canonical) over ``timeSpent`` (string).
    """
    started = worklog.get("started")
    if not started:
        raise ValueError("worklog has no 'started'")
    start = _parse_jira_started(started)

    seconds = worklog.get("timeSpentSeconds")
    if isinstance(seconds, int) and seconds > 0:
        delta = timedelta(seconds=seconds)
    else:
        delta = parse_time_spent(worklog.get("timeSpent") or "")
    return start, start + delta


def intervals_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    """True iff two half-open intervals share any instant."""
    return a_start < b_end and b_start < a_end


def find_overlap(
    target_start: datetime,
    target_end: datetime,
    candidates: list[dict],
) -> dict | None:
    """Return the first candidate worklog that overlaps with the target, else None."""
    for wl in candidates:
        try:
            c_start, c_end = worklog_interval(wl)
        except ValueError:
            continue
        if intervals_overlap(target_start, target_end, c_start, c_end):
            return wl
    return None
