"""Tests for `tjira.timer` — TimerStore unit tests (T2.1–T2.11)."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tjira.errors import UserError


# ==================== T2.1 — default_timer_state_path ====================

def test_default_timer_state_path_uses_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """XDG_CONFIG_HOME set → path is $XDG_CONFIG_HOME/tjira/timer.json."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from tjira.timer import default_timer_state_path
    assert default_timer_state_path() == tmp_path / "tjira" / "timer.json"


def test_default_timer_state_path_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """XDG_CONFIG_HOME unset → falls back to ~/.config/tjira/timer.json."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    from tjira.timer import default_timer_state_path
    assert default_timer_state_path() == Path.home() / ".config" / "tjira" / "timer.json"


# ==================== T2.2 — load from missing file ====================

def test_load_missing_file_returns_inactive_store() -> None:
    """Missing timer.json → is_active=False, no exception."""
    from tjira.timer import TimerStore
    store = TimerStore.load()
    assert store.is_active is False
    assert store.state is None


# ==================== T2.3 — load from corrupt JSON ====================

def test_load_corrupt_json_emits_warning_and_returns_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Corrupt JSON → stderr warning + is_active=False; does NOT crash; does NOT delete file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    timer_dir = tmp_path / "tjira"
    timer_dir.mkdir(parents=True)
    timer_file = timer_dir / "timer.json"
    timer_file.write_text("{{invalid json}}")

    from tjira.timer import TimerStore
    store = TimerStore.load()

    assert store.is_active is False
    assert store.state is None
    captured = capsys.readouterr()
    assert "corrupt" in captured.err.lower() or "warning" in captured.err.lower()
    # File must NOT be deleted
    assert timer_file.exists()


# ==================== T2.4 — start writes atomically with 0o600 ====================

_NOW = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)


def test_start_writes_atomically_with_correct_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """start() writes state file atomically; mode is 0o600."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore
    store = TimerStore.load()
    store.start("PROJ-1", comment=None, profile="default", now=_NOW)

    from tjira.timer import default_timer_state_path
    path = default_timer_state_path()
    assert path.exists()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    data = json.loads(path.read_text())
    assert data["issue_key"] == "PROJ-1"
    assert data["comment"] is None
    assert data["profile"] == "default"


def test_start_persists_comment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """start() persists the comment field into the state file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore
    store = TimerStore.load()
    store.start("PROJ-2", comment="implementing auth", profile="work", now=_NOW)

    from tjira.timer import default_timer_state_path
    data = json.loads(default_timer_state_path().read_text())
    assert data["comment"] == "implementing auth"
    assert data["profile"] == "work"


# ==================== T2.5 — start while already active → UserError ====================

def test_start_while_active_raises_user_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """start() while already active → UserError exit 1; state file unchanged."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore, default_timer_state_path
    store = TimerStore.load()
    store.start("PROJ-1", comment=None, profile="default", now=_NOW)

    # Read the original file contents
    original = default_timer_state_path().read_text()

    with pytest.raises(UserError) as exc_info:
        store.start("PROJ-2", comment=None, profile="default", now=_NOW)

    assert exc_info.value.exit_code == 1
    # State file must reference original issue (unchanged)
    assert default_timer_state_path().read_text() == original


# ==================== T2.6 — stop returns state+elapsed, does NOT delete file ====================

def test_stop_returns_state_and_elapsed_and_preserves_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop() returns (state, elapsed timedelta); does NOT delete the state file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore, default_timer_state_path
    store = TimerStore.load()
    store.start("PROJ-1", comment=None, profile="default", now=_NOW)

    stop_time = _NOW + timedelta(hours=1, minutes=30)
    state, elapsed = store.stop(now=stop_time)

    assert state.issue_key == "PROJ-1"
    assert elapsed == timedelta(hours=1, minutes=30)
    # File MUST still exist — caller calls clear() after successful POST
    assert default_timer_state_path().exists()


# ==================== T2.7 — stop while not active → UserError ====================

def test_stop_while_not_active_raises_user_error() -> None:
    """stop() with no active timer → UserError('No active timer')."""
    from tjira.timer import TimerStore
    store = TimerStore.load()
    with pytest.raises(UserError) as exc_info:
        store.stop()
    assert "No active timer" in str(exc_info.value)


# ==================== T2.8 — cancel with active timer ====================

def test_cancel_with_active_timer_deletes_file_and_returns_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cancel() deletes state file and returns the cancelled TimerState."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore, default_timer_state_path
    store = TimerStore.load()
    store.start("PROJ-1", comment=None, profile="default", now=_NOW)

    cancelled = store.cancel()

    assert cancelled is not None
    assert cancelled.issue_key == "PROJ-1"
    assert not default_timer_state_path().exists()


# ==================== T2.9 — cancel with no active timer → None ====================

def test_cancel_with_no_active_timer_returns_none() -> None:
    """cancel() with no active timer → None (idempotent, no exception)."""
    from tjira.timer import TimerStore
    store = TimerStore.load()
    result = store.cancel()
    assert result is None


# ==================== T2.10 — status ====================

def test_status_returns_state_and_elapsed_when_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status() returns (TimerState, elapsed) when active."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore
    store = TimerStore.load()
    store.start("PROJ-1", comment="auth", profile="work", now=_NOW)

    status_time = _NOW + timedelta(minutes=45)
    result = store.status(now=status_time)

    assert result is not None
    state, elapsed = result
    assert state.issue_key == "PROJ-1"
    assert state.comment == "auth"
    assert state.profile == "work"
    assert elapsed == timedelta(minutes=45)


def test_status_returns_none_when_not_active() -> None:
    """status() returns None when no timer is running."""
    from tjira.timer import TimerStore
    store = TimerStore.load()
    assert store.status() is None


# ==================== T2.11 — clear ====================

def test_clear_deletes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """clear() deletes the timer file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from tjira.timer import TimerStore, default_timer_state_path
    store = TimerStore.load()
    store.start("PROJ-1", comment=None, profile="default", now=_NOW)

    store.clear()
    assert not default_timer_state_path().exists()


def test_clear_is_idempotent_when_file_missing() -> None:
    """clear() when no timer.json exists → no exception (idempotent)."""
    from tjira.timer import TimerStore
    store = TimerStore.load()
    store.clear()  # should not raise
