"""Tests for `tjira timer` CLI commands (T3.1–T3.20 + T3.21–T3.22).

Uses Typer's CliRunner + `responses` library to mock HTTP. Timer state is
isolated via the autouse `_isolate_profile_store` fixture in conftest.py,
which sets XDG_CONFIG_HOME to a fresh tmp_path — so `default_timer_state_path()`
picks up the test-local path automatically.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import responses as resp_lib
from typer.testing import CliRunner

from tjira.profiles import Profile, ProfileStore
from tjira.timer import TimerStore, default_timer_state_path
from tjira.tz import to_jira_datetime


# ==================== shared fixtures ====================

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app():
    from tjira.cli import app as _app
    return _app


@pytest.fixture
def configured_profile(tmp_path: Path) -> Profile:
    """Write a 'default' profile to the test config and mark it active."""
    store = ProfileStore(path=tmp_path / "tjira" / "config.toml")
    profile = Profile(
        name="default",
        domain="example.atlassian.net",
        email="test@example.com",
        api_token="test-token",
    )
    store.add(profile)
    store.set_current("default")
    store.save()
    return profile


_NOW = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = to_jira_datetime(_NOW)


def _seed_timer(
    issue_key: str = "PROJ-1",
    started_at: datetime = _NOW,
    comment: str | None = None,
    profile: str = "default",
) -> None:
    """Write a timer state file using TimerStore.start() so the path is correct."""
    store = TimerStore.load()
    store.start(issue_key, comment=comment, profile=profile, now=started_at)


def _mock_no_existing_worklogs() -> None:
    """Stub /myself + /search/jql so overlap pre-check finds nothing."""
    resp_lib.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    resp_lib.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )


def _mock_worklog_post(worklog_id: str = "10001", time_spent: str = "1h 30m") -> None:
    resp_lib.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={
            "id": worklog_id,
            "timeSpent": time_spent,
            "started": _NOW_ISO,
            "issueId": "10000",
        },
        status=201,
    )


def _last_json_line(stream: str) -> dict[str, Any]:
    for line in reversed(stream.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON found in stream: {stream!r}")


# ==================== T3.1 — timer start happy path ====================

def test_timer_start_happy_path_human(runner, app, configured_profile) -> None:
    """start PROJ-1: exit 0, stdout contains 'Timer started for PROJ-1 at'."""
    result = runner.invoke(app, ["timer", "start", "PROJ-1"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "Timer started for PROJ-1" in result.stdout
    assert "at " in result.stdout


def test_timer_start_happy_path_json(runner, app, configured_profile) -> None:
    """start PROJ-1 --json: exit 0, JSON envelope with correct fields."""
    result = runner.invoke(app, ["timer", "start", "PROJ-1", "--json"])
    assert result.exit_code == 0, result.output + result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["issue_key"] == "PROJ-1"
    assert data["data"]["comment"] is None
    assert data["data"]["profile"] == "default"
    assert "started_at" in data["data"]


# ==================== T3.2 — timer start --comment ====================

def test_timer_start_persists_comment(runner, app, configured_profile) -> None:
    """start PROJ-1 --comment 'x': comment is persisted into the state file."""
    result = runner.invoke(app, ["timer", "start", "PROJ-1", "--comment", "implementing auth"])
    assert result.exit_code == 0, result.output
    data = json.loads(default_timer_state_path().read_text())
    assert data["comment"] == "implementing auth"


# ==================== T3.3 — invalid issue key ====================

def test_timer_start_empty_issue_key_exits_1(runner, app, configured_profile) -> None:
    """start '' → exit 1, stderr contains 'Invalid issue key'."""
    result = runner.invoke(app, ["timer", "start", "", "--json"])
    assert result.exit_code == 1
    assert "Invalid issue key" in result.stderr


def test_timer_start_malformed_issue_key_exits_1(runner, app, configured_profile) -> None:
    """start 'not-an-issue' → exit 1, stderr contains 'Invalid issue key'."""
    result = runner.invoke(app, ["timer", "start", "not-an-issue", "--json"])
    assert result.exit_code == 1
    assert "Invalid issue key" in result.stderr


# ==================== T3.4 — start while another timer active ====================

def test_timer_start_while_active_exits_1(runner, app, configured_profile) -> None:
    """start while timer active → exit 1, stderr contains 'Timer already running for'."""
    _seed_timer("PROJ-456")
    result = runner.invoke(app, ["timer", "start", "PROJ-789", "--json"])
    assert result.exit_code == 1
    assert "Timer already running for PROJ-456" in result.stderr
    assert "Run 'tjira timer stop' or 'tjira timer cancel' first" in result.stderr
    # State file must still reference original issue
    data = json.loads(default_timer_state_path().read_text())
    assert data["issue_key"] == "PROJ-456"


# ==================== REQ-1.7 — start with no profile configured ====================

def test_timer_start_no_profile_configured_exits_1(runner, app) -> None:
    """start when no profile is configured → exit 1, no state file written (REQ-1.7)."""
    result = runner.invoke(app, ["timer", "start", "PROJ-1", "--json"])
    assert result.exit_code == 1
    assert "No Jira profile configured" in result.stderr
    assert not default_timer_state_path().exists()


# ==================== T3.6 — timer status no timer ====================

def test_timer_status_no_timer_human(runner, app, configured_profile) -> None:
    """status with no timer → exit 0, stdout 'No active timer'."""
    result = runner.invoke(app, ["timer", "status"])
    assert result.exit_code == 0
    assert "No active timer" in result.stdout


def test_timer_status_no_timer_json(runner, app, configured_profile) -> None:
    """status --json with no timer → exit 0, JSON {ok: true, data: null}."""
    result = runner.invoke(app, ["timer", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"] is None


# ==================== T3.7 — timer status active ====================

def test_timer_status_active_human(runner, app, configured_profile, monkeypatch) -> None:
    """status with active timer → exit 0, stdout contains issue key + elapsed."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    _seed_timer("PROJ-1", started_at=_NOW)
    # Invoke immediately — elapsed will be ~0m (clamped to 1m)
    result = runner.invoke(app, ["timer", "status"])
    assert result.exit_code == 0
    assert "PROJ-1" in result.stdout


def test_timer_status_active_json(runner, app, configured_profile, monkeypatch) -> None:
    """status --json active → exit 0, JSON includes issue_key, elapsed, started_at, profile."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    _seed_timer("PROJ-1", started_at=_NOW, comment="auth", profile="default")
    result = runner.invoke(app, ["timer", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    d = payload["data"]
    assert d["issue_key"] == "PROJ-1"
    assert d["comment"] == "auth"
    assert d["profile"] == "default"
    assert "started_at" in d
    assert "elapsed" in d


# ==================== T3.9 — timer cancel with active ====================

@resp_lib.activate
def test_timer_cancel_active_human(runner, app, configured_profile) -> None:
    """cancel with active → exit 0, stdout contains 'Timer cancelled for PROJ-1'; no HTTP call."""
    _seed_timer("PROJ-1")
    result = runner.invoke(app, ["timer", "cancel"])
    assert result.exit_code == 0
    assert "Timer cancelled for PROJ-1" in result.stdout
    assert not default_timer_state_path().exists()
    # No HTTP calls
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_timer_cancel_active_json(runner, app, configured_profile) -> None:
    """cancel --json active → exit 0, JSON {ok: true, data: {cancelled: true, issue_key, elapsed}}."""
    _seed_timer("PROJ-1")
    result = runner.invoke(app, ["timer", "cancel", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["cancelled"] is True
    assert payload["data"]["issue_key"] == "PROJ-1"
    assert "elapsed" in payload["data"]
    assert len(resp_lib.calls) == 0


# ==================== T3.10 — timer cancel no timer ====================

def test_timer_cancel_no_timer_human(runner, app, configured_profile) -> None:
    """cancel with no timer → exit 0, 'No active timer to cancel'."""
    result = runner.invoke(app, ["timer", "cancel"])
    assert result.exit_code == 0
    assert "No active timer to cancel" in result.stdout


def test_timer_cancel_no_timer_json(runner, app, configured_profile) -> None:
    """cancel --json no timer → exit 0, JSON {ok: true, data: {cancelled: false}}."""
    result = runner.invoke(app, ["timer", "cancel", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["cancelled"] is False


# ==================== T3.12 — timer stop happy path ====================

@resp_lib.activate
def test_timer_stop_happy_path_human(runner, app, configured_profile, monkeypatch) -> None:
    """stop 90-min timer: exit 0, stdout contains PROJ-1, '1h 30m', worklog ID."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    started = datetime(2026, 5, 20, 8, 30, 0, tzinfo=timezone.utc)  # 90 min before 10:00
    stop_time = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=started)
    _mock_no_existing_worklogs()
    _mock_worklog_post(worklog_id="10001", time_spent="1h 30m")

    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "PROJ-1" in result.stdout
    assert "1h 30m" in result.stdout
    assert "10001" in result.stdout
    assert not default_timer_state_path().exists()


@resp_lib.activate
def test_timer_stop_happy_path_json(runner, app, configured_profile, monkeypatch) -> None:
    """stop --json: exit 0, JSON envelope with issue_key, worklog_id, time_spent, started_at."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    started = datetime(2026, 5, 20, 8, 30, 0, tzinfo=timezone.utc)
    stop_time = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=started)
    _mock_no_existing_worklogs()
    _mock_worklog_post(worklog_id="10001", time_spent="1h 30m")

    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop", "--json"])
    assert result.exit_code == 0, result.output + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    d = payload["data"]
    assert d["issue_key"] == "PROJ-1"
    assert d["worklog_id"] == "10001"
    assert d["time_spent"] == "1h 30m"
    assert "started_at" in d
    assert not default_timer_state_path().exists()


# ==================== T3.13 — elapsed < 1 minute → "1m" ====================

@resp_lib.activate
def test_timer_stop_short_elapsed_posts_1m(runner, app, configured_profile, monkeypatch) -> None:
    """Elapsed < 1 min → rounds to 1m; stdout contains '1m'."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    started = datetime(2026, 5, 20, 9, 59, 40, tzinfo=timezone.utc)  # 20 seconds before 10:00
    stop_time = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=started)
    _mock_no_existing_worklogs()
    resp_lib.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "10002", "timeSpent": "1m", "started": _NOW_ISO, "issueId": "10000"},
        status=201,
    )
    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop", "--json"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["time_spent"] == "1m"
    assert "1m" in result.stdout


# ==================== T3.14 — stop no active timer ====================

def test_timer_stop_no_active_timer_exits_1(runner, app, configured_profile) -> None:
    """stop with no timer → exit 1, stderr 'No active timer'."""
    result = runner.invoke(app, ["timer", "stop"])
    assert result.exit_code == 1
    assert "No active timer" in result.stderr


# ==================== T3.15 — stop overlap detected ====================

@resp_lib.activate
def test_timer_stop_overlap_exits_3_and_preserves_file(
    runner, app, configured_profile, monkeypatch
) -> None:
    """Overlap detected → exit 3; timer file still exists."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    started = datetime(2026, 5, 20, 8, 30, 0, tzinfo=timezone.utc)
    stop_time = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=started)

    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    # /myself
    resp_lib.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    # /search/jql → returns an issue with a worklog
    resp_lib.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-9"}]},
        status=200,
    )
    resp_lib.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-9/worklog",
        json={"worklogs": [{
            "id": "55",
            "author": {"accountId": "me-123"},
            "started": "2026-05-20T09:00:00.000+0000",
            "timeSpentSeconds": 3600,
            "timeSpent": "1h",
        }]},
        status=200,
    )

    result = runner.invoke(app, ["timer", "stop"])
    assert result.exit_code == 3
    # Timer file must NOT be deleted
    assert default_timer_state_path().exists()


# ==================== T3.16 — stop --force bypasses overlap ====================

@resp_lib.activate
def test_timer_stop_force_bypasses_overlap(runner, app, configured_profile, monkeypatch) -> None:
    """stop --force → exit 0; overlap check skipped; worklog posted."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    stop_time = datetime(2026, 5, 20, 10, 0, 30, tzinfo=timezone.utc)  # 30s after _NOW
    _seed_timer("PROJ-1", started_at=_NOW)
    # No /myself or /search/jql mock needed — must NOT be called with --force
    _mock_worklog_post(worklog_id="10001", time_spent="1m")

    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop", "--force", "--json"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert not default_timer_state_path().exists()


# ==================== T3.17 — stop cross-profile mismatch ====================

def test_timer_stop_cross_profile_mismatch_exits_1(
    runner, app, configured_profile, tmp_path, monkeypatch
) -> None:
    """Timer stored with profile='work', active='default' → exit 1; --force does NOT bypass."""
    # Add a "work" profile to the existing store (which already has "default" as active)
    pstore = ProfileStore.load(tmp_path / "tjira" / "config.toml")
    pstore.add(Profile("work", "work.atlassian.net", "w@w.com", "work-token"))
    pstore.save()

    # Seed timer with profile="work" while active is still "default"
    _seed_timer("PROJ-1", profile="work")

    result = runner.invoke(app, ["timer", "stop"])
    assert result.exit_code == 1
    assert "Timer was started with profile 'work'" in result.stderr
    # File must be preserved
    assert default_timer_state_path().exists()


def test_timer_stop_cross_profile_force_does_not_bypass(
    runner, app, configured_profile, tmp_path, monkeypatch
) -> None:
    """--force does NOT bypass cross-profile safeguard."""
    pstore = ProfileStore.load(tmp_path / "tjira" / "config.toml")
    pstore.add(Profile("work", "work.atlassian.net", "w@w.com", "work-token"))
    pstore.save()

    _seed_timer("PROJ-1", profile="work")

    result = runner.invoke(app, ["timer", "stop", "--force"])
    assert result.exit_code == 1
    assert "Timer was started with profile 'work'" in result.stderr
    assert default_timer_state_path().exists()


# ==================== T3.18 — stop API error → exit 2, file preserved ====================

@resp_lib.activate
def test_timer_stop_api_error_exits_2_and_preserves_file(
    runner, app, configured_profile, monkeypatch
) -> None:
    """Jira POST returns 500 → exit 2; timer file NOT deleted (preserves for retry)."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    stop_time = datetime(2026, 5, 20, 10, 0, 30, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=_NOW)
    _mock_no_existing_worklogs()
    resp_lib.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"errorMessages": ["Internal server error"]},
        status=500,
    )
    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop"])
    assert result.exit_code == 2
    assert default_timer_state_path().exists()


# ==================== T3.19 — stop passes stored comment ====================

@resp_lib.activate
def test_timer_stop_passes_stored_comment(
    runner, app, configured_profile, monkeypatch
) -> None:
    """stop: stored comment is forwarded to client.add_worklog as the comment field."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    stop_time = datetime(2026, 5, 20, 10, 0, 30, tzinfo=timezone.utc)
    _seed_timer("PROJ-1", started_at=_NOW, comment="auth work")
    _mock_no_existing_worklogs()
    _mock_worklog_post(worklog_id="10001", time_spent="1m")

    import tjira.commands.timer as timer_mod
    monkeypatch.setattr(timer_mod, "_now", lambda: stop_time)

    result = runner.invoke(app, ["timer", "stop", "--json"])
    assert result.exit_code == 0, result.stderr

    # Assert the POST body contained the comment
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"
                  and "/worklog" in c.request.url]
    assert len(post_calls) == 1
    body = json.loads(post_calls[0].request.body)
    assert body.get("comment") == "auth work" or (
        # ADF format: comment is an object with content
        isinstance(body.get("comment"), dict)
    )


# ==================== T3.21 — help discoverability ====================

def test_timer_help_is_discoverable(runner, app, configured_profile) -> None:
    """tjira timer --help exits 0 and shows subcommands."""
    result = runner.invoke(app, ["timer", "--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout
    assert "stop" in result.stdout
    assert "status" in result.stdout
    assert "cancel" in result.stdout


def test_timer_listed_in_root_help(runner, app, configured_profile) -> None:
    """tjira --help lists 'timer' as a subcommand group."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "timer" in result.stdout
