"""Timer state persistence — `TimerStore` with atomic write and XDG path resolution.

The timer state file lives at ``$XDG_CONFIG_HOME/tjira/timer.json`` (fallback:
``~/.config/tjira/timer.json``). It records a single in-flight worklog timer:
the issue key, when it was started, an optional comment, and which profile the
timer belongs to.

Atomic write mirrors the pattern in ``tjira.profiles.ProfileStore.save()``:
``tempfile.mkstemp`` + ``os.replace`` so a crash mid-write never leaves a
half-written file on disk.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from tjira.errors import UserError
from tjira.tz import to_jira_datetime


def default_timer_state_path() -> Path:
    """Resolve ``$XDG_CONFIG_HOME/tjira/timer.json`` with ``~/.config`` fallback."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "tjira" / "timer.json"


@dataclass(frozen=True)
class TimerState:
    """Immutable snapshot of a running timer."""

    issue_key: str
    started_at: datetime      # always tz-aware
    comment: Optional[str]
    profile: str


def _parse_iso(raw: str) -> datetime:
    """Parse a Jira-format ISO datetime string into a tz-aware datetime."""
    # Normalize "+0000" offset (no colon) to "+00:00" for fromisoformat().
    iso = raw
    if len(iso) >= 5 and iso[-5] in "+-" and iso[-3] != ":":
        iso = f"{iso[:-2]}:{iso[-2:]}"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TimerStore:
    """In-memory view of the timer state file with explicit persistence."""

    def __init__(self, state: TimerState | None = None, path: Path | None = None) -> None:
        self._state: TimerState | None = state
        self._path: Path = path or default_timer_state_path()

    # ---------- factory ----------

    @classmethod
    def load(cls, path: Path | None = None) -> "TimerStore":
        """Load timer state from disk.

        - Missing file → empty store (is_active=False).
        - Corrupt JSON → emit warning to stderr, return empty store, preserve file.
        """
        resolved = path or default_timer_state_path()
        if not resolved.exists():
            return cls(state=None, path=resolved)

        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(
                f"Warning: timer state file at {resolved} is corrupt; "
                "treating as no active timer.",
                file=sys.stderr,
                flush=True,
            )
            return cls(state=None, path=resolved)

        try:
            state = TimerState(
                issue_key=data["issue_key"],
                started_at=_parse_iso(data["started_at"]),
                comment=data.get("comment"),
                profile=data["profile"],
            )
        except (KeyError, ValueError):
            print(
                f"Warning: timer state file at {resolved} is corrupt; "
                "treating as no active timer.",
                file=sys.stderr,
                flush=True,
            )
            return cls(state=None, path=resolved)

        return cls(state=state, path=resolved)

    # ---------- properties ----------

    @property
    def is_active(self) -> bool:
        return self._state is not None

    @property
    def state(self) -> TimerState | None:
        return self._state

    # ---------- mutations ----------

    def start(
        self,
        issue_key: str,
        comment: str | None,
        profile: str,
        now: datetime | None = None,
    ) -> TimerState:
        """Write a new timer state. Raises :class:`UserError` if one is already active."""
        if self._state is not None:
            raise UserError(
                f"Timer already running for {self._state.issue_key} "
                f"(started {to_jira_datetime(self._state.started_at)}). "
                "Run 'tjira timer stop' or 'tjira timer cancel' first.",
            )

        started_at = now or datetime.now(tz=_local_tz())
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=_local_tz())

        new_state = TimerState(
            issue_key=issue_key,
            started_at=started_at,
            comment=comment,
            profile=profile,
        )
        self._write(new_state)
        self._state = new_state
        return new_state

    def stop(self, now: datetime | None = None) -> tuple[TimerState, timedelta]:
        """Return ``(state, elapsed)`` in-memory only. Does NOT delete the file.

        The caller must invoke :meth:`clear` after a successful Jira POST.
        Raises :class:`UserError` if no timer is active.
        """
        if self._state is None:
            raise UserError("No active timer")

        stop_time = now or datetime.now(tz=_local_tz())
        if stop_time.tzinfo is None:
            stop_time = stop_time.replace(tzinfo=_local_tz())

        elapsed = stop_time - self._state.started_at
        return self._state, elapsed

    def cancel(self) -> TimerState | None:
        """Delete the state file and return the cancelled state, or None if not active."""
        state = self._state
        self._state = None
        self._path.unlink(missing_ok=True)
        return state

    def status(self, now: datetime | None = None) -> tuple[TimerState, timedelta] | None:
        """Return ``(state, elapsed)`` if active, else ``None``."""
        if self._state is None:
            return None
        stop_time = now or datetime.now(tz=_local_tz())
        if stop_time.tzinfo is None:
            stop_time = stop_time.replace(tzinfo=_local_tz())
        elapsed = stop_time - self._state.started_at
        return self._state, elapsed

    def clear(self) -> None:
        """Delete the state file (idempotent — no error if already missing)."""
        self._state = None
        self._path.unlink(missing_ok=True)

    # ---------- private ----------

    def _write(self, state: TimerState) -> None:
        """Atomically write state to disk with mode 0o600."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "issue_key": state.issue_key,
            "started_at": to_jira_datetime(state.started_at),
            "comment": state.comment,
            "profile": state.profile,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=".tjira-timer-",
            suffix=".json.tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(encoded)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


def _local_tz():
    """Return local tz (mirrors tjira.tz.get_timezone without the import cycle risk)."""
    from tjira.tz import get_timezone
    return get_timezone()
