"""End-to-end tests: real subprocess against a localhost mock HTTP server.

These tests validate the contract that an external caller (the IA, a shell
script, CI) actually sees:
    - the binary boots
    - exit codes are what the spec promises (0/1/2/3)
    - stdout (data) and stderr (logs/errors) are properly separated
    - JSON envelopes can be parsed by an outsider

`pytest-httpserver` spins up a Werkzeug server in a thread; the subprocess hits
it through TJIRA_API_BASE_URL / TJIRA_AGILE_BASE_URL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def tjira_env(httpserver, tmp_path: Path) -> dict[str, str]:
    """Env that points the CLI at the mock server with a seeded profile."""
    cfg_dir = tmp_path / "tjira"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text(
        'current_profile = "default"\n'
        '\n'
        '[profiles.default]\n'
        'domain = "mock.invalid"\n'
        'email = "test@example.com"\n'
        'api_token = "test-token"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({
        "XDG_CONFIG_HOME": str(tmp_path),
        "TJIRA_API_BASE_URL": httpserver.url_for("/rest/api/3"),
        "TJIRA_AGILE_BASE_URL": httpserver.url_for("/rest/agile/1.0"),
        "JIRA_TIMEZONE": "UTC",
        "NO_COLOR": "1",
    })
    return env


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke `python -m tjira ...` as a real subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "tjira", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


# ==================== smoke: process boots ====================

def test_e2e_version_no_server_needed():
    """--version doesn't touch the network and must exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "tjira", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "tjira" in result.stdout
    assert "0.1.0" in result.stdout


# ==================== exit 0 happy path ====================

def test_e2e_log_happy_path_returns_exit_0(tjira_env, httpserver):
    httpserver.expect_request("/rest/api/3/myself").respond_with_json(
        {"accountId": "me-123"}
    )
    httpserver.expect_request("/rest/api/3/search/jql", method="POST").respond_with_json(
        {"issues": []}
    )
    httpserver.expect_request(
        "/rest/api/3/issue/PROJ-1/worklog", method="POST"
    ).respond_with_json(
        {"id": "77", "timeSpent": "1h", "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )

    result = _run(tjira_env, "log", "PROJ-1", "1h", "2026-04-20 09:00", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["id"] == "77"
    assert envelope["data"]["time_spent"] == "1h"


# ==================== exit 3: overlap (the CRITICAL contract for IA) ====================

def test_e2e_log_overlap_exits_3_with_parseable_payload(tjira_env, httpserver):
    """The IA reads exit code from the OS and parses error JSON from stderr."""
    httpserver.expect_request("/rest/api/3/myself").respond_with_json(
        {"accountId": "me-123"}
    )
    httpserver.expect_request("/rest/api/3/search/jql", method="POST").respond_with_json(
        {"issues": [{"key": "PROJ-9"}]}
    )
    httpserver.expect_request(
        "/rest/api/3/issue/PROJ-9/worklog", method="GET"
    ).respond_with_json({"worklogs": [{
        "id": "55",
        "author": {"accountId": "me-123"},
        "started": "2026-04-20T09:30:00.000+0000",
        "timeSpentSeconds": 3600,
        "timeSpent": "1h",
    }]})

    result = _run(tjira_env, "log", "PROJ-1", "1h", "2026-04-20 09:00", "--json")

    # The crucial assertion: exit code 3 reaches the OS unchanged.
    assert result.returncode == 3, f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
    # Stdout must be empty — error JSON goes to stderr.
    assert result.stdout == ""
    # Last JSON line on stderr is the error envelope.
    json_line = next(
        (line for line in reversed(result.stderr.splitlines()) if line.strip().startswith("{")),
        None,
    )
    assert json_line is not None, f"no JSON in stderr: {result.stderr!r}"
    envelope = json.loads(json_line)
    assert envelope["ok"] is False
    assert envelope["conflict"]["issue"] == "PROJ-9"
    assert envelope["conflict"]["worklog_id"] == "55"
    assert "10:30" in envelope["suggested_start"]
    assert envelope["requested"]["issue"] == "PROJ-1"


# ==================== exit 2: API error ====================

def test_e2e_log_api_error_exits_2(tjira_env, httpserver):
    httpserver.expect_request("/rest/api/3/myself").respond_with_json(
        {"accountId": "me-123"}
    )
    httpserver.expect_request("/rest/api/3/search/jql", method="POST").respond_with_json(
        {"issues": []}
    )
    httpserver.expect_request(
        "/rest/api/3/issue/PROJ-1/worklog", method="POST"
    ).respond_with_json({"errorMessages": ["Issue does not exist"]}, status=404)

    result = _run(tjira_env, "log", "PROJ-1", "1h", "2026-04-20 09:00", "--json")
    assert result.returncode == 2, f"stderr: {result.stderr}"


# ==================== exit 1: user error ====================

def test_e2e_log_invalid_date_exits_1(tjira_env):
    """No server hit at all — user-input validation fires first."""
    result = _run(tjira_env, "log", "PROJ-1", "1h", "not-a-date", "--json")
    assert result.returncode == 1


# ==================== --force bypasses pre-check (no /myself, no /search/jql) ====================

def test_e2e_log_force_skips_overlap_lookup(tjira_env, httpserver):
    """--force must NOT call /myself or /search/jql."""
    httpserver.expect_request(
        "/rest/api/3/issue/PROJ-1/worklog", method="POST"
    ).respond_with_json(
        {"id": "99", "timeSpent": "1h", "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )
    result = _run(
        tjira_env, "log", "PROJ-1", "1h", "2026-04-20 09:00", "--force", "--json"
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["data"]["id"] == "99"

    # Assert that the only request hit was the worklog POST.
    paths = [str(r.path) for r, _ in httpserver.log]
    assert paths == ["/rest/api/3/issue/PROJ-1/worklog"]


# ==================== list boards (sanity for agile endpoint) ====================

def test_e2e_list_boards_uses_agile_base_url(tjira_env, httpserver):
    httpserver.expect_request("/rest/agile/1.0/board").respond_with_json(
        {"values": [{"id": 1, "name": "Board A", "type": "scrum"}]}
    )
    result = _run(tjira_env, "list", "boards", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    envelope = json.loads(result.stdout)
    assert envelope["data"][0]["name"] == "Board A"
