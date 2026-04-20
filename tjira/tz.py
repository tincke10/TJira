"""Configurable timezone handling.

The zone is resolved in this order:
    1. `JIRA_TIMEZONE` environment variable (e.g. `America/Argentina/Buenos_Aires`)
    2. System local timezone
    3. UTC as a last resort

Previously this was hardcoded to `+0100` (Europe/Spain), which broke worklogs
for any user outside that timezone.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]


def get_timezone():
    """Return the configured tzinfo."""
    tz_name = os.getenv("JIRA_TIMEZONE")
    if tz_name and ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    local = datetime.now().astimezone().tzinfo
    return local or timezone.utc


def to_jira_datetime(dt: datetime) -> str:
    """Convert a datetime to the ISO format Jira expects for worklogs.

    Format: `YYYY-MM-DDTHH:MM:SS.000±HHMM`
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_timezone())
    # Jira requires 3-digit milliseconds and an offset without `:`.
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    offset = dt.strftime("%z") or "+0000"
    return f"{base}.000{offset}"


def parse_user_datetime(date_str: str) -> datetime:
    """Parse flexible user-supplied date strings.

    Accepts: `YYYY-MM-DD HH:MM`, `YYYY-MM-DD`, `DD/MM/YYYY HH:MM`, `DD/MM/YYYY`.
    If no time is supplied, assumes 09:00. If no tz is supplied, uses the
    configured one.
    """
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if ":" not in date_str:
            dt = dt.replace(hour=9, minute=0)
        return dt.replace(tzinfo=get_timezone())

    raise ValueError(f"Unrecognized date format: {date_str}")
