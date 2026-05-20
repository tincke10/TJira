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


# ==================== T5.1: issue create --parent (wire payload) ====================

def test_e2e_issue_create_with_parent_sends_correct_payload(tjira_env, httpserver):
    """T5.1: POST body must contain fields.parent = {"key": "EPIC-1"}."""
    httpserver.expect_request("/rest/api/3/issue", method="POST").respond_with_json(
        {"key": "PROJ-99", "id": "10099"},
        status=201,
    )

    result = _run(
        tjira_env, "issue", "create", "PROJ", "My task", "--parent", "EPIC-1", "--json"
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["key"] == "PROJ-99"
    assert envelope["data"]["parent_key"] == "EPIC-1"

    # Verify the wire payload sent to Jira contained the parent field.
    assert len(httpserver.log) == 1, "Expected exactly one HTTP request"
    request, _ = httpserver.log[0]
    body = json.loads(request.data)
    assert body["fields"]["parent"] == {"key": "EPIC-1"}, (
        f"Expected fields.parent to be {{\"key\": \"EPIC-1\"}}, got: {body['fields'].get('parent')!r}"
    )


# ==================== T5.2: issue update --parent set and clear ====================

def test_e2e_issue_update_parent_set_sends_correct_payload(tjira_env, httpserver):
    """T5.2a: PUT body must contain fields.parent = {"key": "EPIC-2"} when setting parent."""
    httpserver.expect_request("/rest/api/3/issue/PROJ-10", method="PUT").respond_with_data(
        "", status=204
    )

    result = _run(
        tjira_env, "issue", "update", "PROJ-10", "--parent", "EPIC-2", "--json"
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["parent_key"] == "EPIC-2"

    # Verify the wire payload.
    assert len(httpserver.log) >= 1
    put_requests = [
        (req, resp) for req, resp in httpserver.log if req.method == "PUT"
    ]
    assert len(put_requests) == 1
    body = json.loads(put_requests[0][0].data)
    assert body["fields"]["parent"] == {"key": "EPIC-2"}, (
        f"Expected fields.parent {{\"key\": \"EPIC-2\"}}, got: {body['fields'].get('parent')!r}"
    )


def test_e2e_issue_update_parent_none_sends_null_payload(tjira_env, httpserver):
    """T5.2b: --parent NONE must send fields.parent = null in the PUT body."""
    httpserver.expect_request("/rest/api/3/issue/PROJ-10", method="PUT").respond_with_data(
        "", status=204
    )

    result = _run(
        tjira_env, "issue", "update", "PROJ-10", "--parent", "NONE", "--json"
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["parent_key"] is None

    # Verify the wire payload: "parent" must be JSON null, not the string "NONE".
    put_requests = [
        (req, resp) for req, resp in httpserver.log if req.method == "PUT"
    ]
    assert len(put_requests) == 1
    body = json.loads(put_requests[0][0].data)
    assert "parent" in body["fields"], "Expected 'parent' key in fields"
    assert body["fields"]["parent"] is None, (
        f"Expected fields.parent to be null, got: {body['fields']['parent']!r}"
    )


# ==================== T5.3: list projects -- pagination collected ====================

def test_e2e_list_projects_returns_all_projects(tjira_env, httpserver):
    """T5.3: list projects --json returns the full set from the server response."""
    httpserver.expect_request("/rest/api/3/project/search").respond_with_json({
        "values": [
            {"key": "ALPHA", "name": "Alpha Project", "projectTypeKey": "software", "style": "next-gen"},
            {"key": "BETA", "name": "Beta Project", "projectTypeKey": "business", "style": "classic"},
        ],
        "isLast": True,
        "maxResults": 50,
        "startAt": 0,
        "total": 2,
    })

    result = _run(tjira_env, "list", "projects", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    projects = envelope["data"]
    assert len(projects) == 2
    keys = {p["key"] for p in projects}
    assert keys == {"ALPHA", "BETA"}
    for proj in projects:
        assert "key" in proj
        assert "name" in proj
        assert "type" in proj
        assert "style" in proj


# ==================== T5.4: list fields two-roundtrip flow ====================

def test_e2e_list_fields_two_roundtrip_flow(tjira_env, httpserver):
    """T5.4: list fields PROJ Task --json performs two HTTP requests:
    1) issuetypes lookup to resolve "Task" → id "10001"
    2) fields fetch for issuetype 10001
    """
    # Step 1 response: issuetypes endpoint
    httpserver.expect_request(
        "/rest/api/3/issue/createmeta/PROJ/issuetypes"
    ).respond_with_json({
        "values": [
            {"id": "10001", "name": "Task", "subtask": False, "description": "A task"},
            {"id": "10002", "name": "Bug", "subtask": False, "description": "A bug"},
        ],
        "isLast": True,
        "startAt": 0,
        "maxResults": 50,
        "total": 2,
    })

    # Step 2 response: fields for issuetype 10001
    httpserver.expect_request(
        "/rest/api/3/issue/createmeta/PROJ/issuetypes/10001"
    ).respond_with_json({
        "values": [
            {
                "name": "Summary",
                "key": "summary",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "Priority",
                "key": "priority",
                "required": False,
                "schema": {"type": "priority"},
                "allowedValues": [{"name": "High"}, {"name": "Medium"}, {"name": "Low"}],
            },
        ],
        "isLast": True,
        "startAt": 0,
        "maxResults": 100,
        "total": 2,
    })

    result = _run(tjira_env, "list", "fields", "PROJ", "Task", "--json")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    fields = envelope["data"]
    assert len(fields) == 2

    # Verify the two-roundtrip flow: both endpoints were called.
    paths_hit = [str(req.path) for req, _ in httpserver.log]
    assert "/rest/api/3/issue/createmeta/PROJ/issuetypes" in paths_hit, (
        f"Expected issuetypes lookup request, got: {paths_hit}"
    )
    assert "/rest/api/3/issue/createmeta/PROJ/issuetypes/10001" in paths_hit, (
        f"Expected fields fetch request, got: {paths_hit}"
    )

    # Verify field shape
    summary_field = next((f for f in fields if f["key"] == "summary"), None)
    assert summary_field is not None
    assert summary_field["required"] is True
    assert summary_field["type"] == "string"

    priority_field = next((f for f in fields if f["key"] == "priority"), None)
    assert priority_field is not None
    assert priority_field["allowed_values"] == ["High", "Medium", "Low"]


# ==================== T5.1: timer start -> stop -> POST /worklog ====================

def test_e2e_timer_start_then_stop_posts_worklog(tjira_env, httpserver):
    """T5.1: full start → stop subprocess flow.

    1. `tjira timer start PROJ-1 --json` → exit 0, JSON envelope.
    2. `tjira timer stop --json` → exit 0; asserts timeSpent + started in wire body;
       asserts worklog_id in stdout JSON.
    """
    # -- stop will run an overlap pre-check: GET /myself + POST /search/jql --
    httpserver.expect_ordered_request(
        "/rest/api/3/myself", method="GET"
    ).respond_with_json({"accountId": "me-123"})

    httpserver.expect_ordered_request(
        "/rest/api/3/search/jql", method="POST"
    ).respond_with_json({"issues": []})

    httpserver.expect_ordered_request(
        "/rest/api/3/issue/PROJ-1/worklog", method="POST"
    ).respond_with_json(
        {"id": "88", "timeSpent": "1m", "started": "2026-05-20T09:00:00.000+0000"},
        status=201,
    )

    # -- start timer --
    start_result = _run(tjira_env, "timer", "start", "PROJ-1", "--json")
    assert start_result.returncode == 0, f"timer start stderr: {start_result.stderr}"
    start_envelope = json.loads(start_result.stdout)
    assert start_envelope["ok"] is True
    assert start_envelope["data"]["issue_key"] == "PROJ-1"
    recorded_started_at = start_envelope["data"]["started_at"]

    # -- stop timer (uses overlap pre-check then posts worklog) --
    stop_result = _run(tjira_env, "timer", "stop", "--json")
    assert stop_result.returncode == 0, f"timer stop stderr: {stop_result.stderr}"
    stop_envelope = json.loads(stop_result.stdout)
    assert stop_envelope["ok"] is True
    data = stop_envelope["data"]
    assert data["issue_key"] == "PROJ-1"
    assert data["worklog_id"] == "88"
    assert "time_spent" in data     # e.g. "1m" (elapsed < 1 min in test)
    assert "started_at" in data

    # Verify the wire payload sent to Jira had the required fields.
    worklog_requests = [
        (req, resp)
        for req, resp in httpserver.log
        if req.method == "POST" and "worklog" in str(req.path)
    ]
    assert len(worklog_requests) == 1, "Expected exactly one worklog POST"
    body = json.loads(worklog_requests[0][0].data)
    assert "timeSpent" in body, f"Missing timeSpent in wire body: {body}"
    assert "started" in body, f"Missing started in wire body: {body}"
    # started in wire must match what timer start recorded
    assert body["started"] == recorded_started_at


# ==================== T5.2: timer start -> cancel -> no /worklog POST ====================

def test_e2e_timer_start_then_cancel_no_worklog_post(tjira_env, httpserver):
    """T5.2: start → cancel subprocess. httpserver received ZERO requests to POST /worklog."""
    # -- start timer (no server interaction) --
    start_result = _run(tjira_env, "timer", "start", "PROJ-1", "--json")
    assert start_result.returncode == 0, f"timer start stderr: {start_result.stderr}"

    # -- cancel timer (must NOT hit any Jira endpoints) --
    cancel_result = _run(tjira_env, "timer", "cancel", "--json")
    assert cancel_result.returncode == 0, f"timer cancel stderr: {cancel_result.stderr}"
    cancel_envelope = json.loads(cancel_result.stdout)
    assert cancel_envelope["ok"] is True
    assert cancel_envelope["data"]["cancelled"] is True
    assert cancel_envelope["data"]["issue_key"] == "PROJ-1"

    # Assert httpserver received ZERO requests to worklog endpoint.
    worklog_posts = [
        (req, resp)
        for req, resp in httpserver.log
        if req.method == "POST" and "worklog" in str(req.path)
    ]
    assert len(worklog_posts) == 0, (
        f"Expected no worklog POST but got: {[str(r.path) for r, _ in worklog_posts]}"
    )
