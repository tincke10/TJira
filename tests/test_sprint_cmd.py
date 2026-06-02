"""`tjira sprint add` command tests — SA-CMD-1..13.

Strict TDD: every scenario maps to a test. Uses Typer CliRunner + `responses`
library for HTTP mocking. Profile is seeded via the global `configured_profile`
fixture from conftest.py (autouse `_isolate_profile_store` handles XDG isolation).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import responses as resp_lib
from typer.testing import CliRunner

from tjira.commands.sprint import _is_epic


# ==================== shared fixtures ====================


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app(configured_profile):
    from tjira.cli import app as _app
    return _app


_DOMAIN = "https://example.atlassian.net"
_SPRINT_URL = f"{_DOMAIN}/rest/agile/1.0/sprint/42/issue"
_SPRINT_10_URL = f"{_DOMAIN}/rest/agile/1.0/sprint/10/issue"


def _issue_url(key: str) -> str:
    return f"{_DOMAIN}/rest/api/3/issue/{key}"


def _non_epic_payload(key: str = "PROJ-1") -> dict[str, Any]:
    return {
        "key": key,
        "fields": {"issuetype": {"name": "Story", "hierarchyLevel": 0}},
    }


def _epic_payload(key: str = "EPIC-1") -> dict[str, Any]:
    return {
        "key": key,
        "fields": {"issuetype": {"name": "Epic", "hierarchyLevel": 1}},
    }


def _mock_get_issue(key: str, payload: dict[str, Any]) -> None:
    resp_lib.get(_issue_url(key), json=payload, status=200)


def _mock_sprint_post(sprint_id: int = 42, status: int = 204) -> None:
    resp_lib.post(
        f"{_DOMAIN}/rest/agile/1.0/sprint/{sprint_id}/issue",
        body=b"",
        status=status,
    )


def _last_json_line(stream: str) -> dict[str, Any]:
    for line in reversed(stream.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON found in stream: {stream!r}")


# ==================== SA-CMD-12 — _is_epic unit tests ====================
# (Placed first — no HTTP needed, pure logic)


def test_is_epic_hierarchy_level_1_custom_name() -> None:
    """hierarchyLevel=1 with custom name → True (SA-CMD-12a)."""
    issue = {"fields": {"issuetype": {"name": "Custom Epic Type", "hierarchyLevel": 1}}}
    assert _is_epic(issue) is True


def test_is_epic_hierarchy_level_2_custom_name() -> None:
    """hierarchyLevel=2 (e.g. Initiative) → True (hierarchyLevel >= 1)."""
    issue = {"fields": {"issuetype": {"name": "Initiative", "hierarchyLevel": 2}}}
    assert _is_epic(issue) is True


def test_is_epic_hierarchy_level_none_name_epic() -> None:
    """hierarchyLevel absent, name='Epic' → True (fallback, SA-CMD-12b)."""
    issue = {"fields": {"issuetype": {"name": "Epic", "hierarchyLevel": None}}}
    assert _is_epic(issue) is True


def test_is_epic_hierarchy_level_none_name_missing_fallback() -> None:
    """hierarchyLevel absent, name='Epic' via missing key → True."""
    issue = {"fields": {"issuetype": {"name": "Epic"}}}
    assert _is_epic(issue) is True


def test_is_epic_story_false() -> None:
    """hierarchyLevel=0, name='Story' → False (SA-CMD-12c)."""
    issue = {"fields": {"issuetype": {"name": "Story", "hierarchyLevel": 0}}}
    assert _is_epic(issue) is False


def test_is_epic_task_false() -> None:
    """hierarchyLevel=0, name='Task' → False."""
    issue = {"fields": {"issuetype": {"name": "Task", "hierarchyLevel": 0}}}
    assert _is_epic(issue) is False


def test_is_epic_missing_fields_safe() -> None:
    """Missing nested keys don't crash — returns False."""
    assert _is_epic({}) is False
    assert _is_epic({"fields": {}}) is False
    assert _is_epic({"fields": {"issuetype": {}}}) is False


# ==================== SA-CMD-1 — happy path human ====================


@resp_lib.activate
def test_sprint_add_single_issue_human(runner, app) -> None:
    """SA-CMD-1: single non-epic issue, human output — exit 0, stdout contains OK."""
    _mock_get_issue("PROJ-1", _non_epic_payload("PROJ-1"))
    _mock_sprint_post(42)

    result = runner.invoke(app, ["sprint", "add", "42", "PROJ-1"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "OK" in result.stdout
    assert "1" in result.stdout
    assert "42" in result.stdout
    assert "PROJ-1" in result.stdout


# ==================== SA-CMD-2 — happy path --json ====================


@resp_lib.activate
def test_sprint_add_single_issue_json(runner, app) -> None:
    """SA-CMD-2: single non-epic issue, --json — exact envelope shape."""
    _mock_get_issue("PROJ-1", _non_epic_payload("PROJ-1"))
    _mock_sprint_post(42)

    result = runner.invoke(app, ["sprint", "add", "42", "PROJ-1", "--json"])
    assert result.exit_code == 0, result.output + result.stderr

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["sprint_id"] == 42
    assert data["added"] == ["PROJ-1"]
    assert data["expanded_from_epics"] == {}
    assert data["chunks"] == 1
    assert data["count"] == 1


# ==================== SA-CMD-3 — multiple non-epic issues ====================


@resp_lib.activate
def test_sprint_add_multiple_non_epic_issues(runner, app) -> None:
    """SA-CMD-3: 3 non-epics → exit 0, stdout has count 3, exactly 1 POST."""
    for key in ("PROJ-1", "PROJ-2", "PROJ-3"):
        _mock_get_issue(key, _non_epic_payload(key))
    _mock_sprint_post(10)

    result = runner.invoke(app, ["sprint", "add", "10", "PROJ-1", "PROJ-2", "PROJ-3", "--json"])
    assert result.exit_code == 0, result.output + result.stderr

    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = json.loads(post_calls[0].request.body)
    assert body["issues"] == ["PROJ-1", "PROJ-2", "PROJ-3"]

    data = json.loads(result.stdout)["data"]
    assert data["count"] == 3


# ==================== SA-CMD-4 — 51 issues → 2 chunks ====================


@resp_lib.activate
def test_sprint_add_51_issues_two_chunks(runner, app) -> None:
    """SA-CMD-4: 51 non-epic issues → exit 0, 2 POST requests, data.chunks == 2."""
    keys = [f"PROJ-{i}" for i in range(1, 52)]  # 51 keys
    for key in keys:
        _mock_get_issue(key, _non_epic_payload(key))
    # Two POST responses — 204 No Content: use body=b"" to avoid IncompleteRead
    resp_lib.post(
        f"{_DOMAIN}/rest/agile/1.0/sprint/10/issue", body=b"", status=204
    )
    resp_lib.post(
        f"{_DOMAIN}/rest/agile/1.0/sprint/10/issue", body=b"", status=204
    )

    result = runner.invoke(app, ["sprint", "add", "10"] + keys + ["--json"])
    assert result.exit_code == 0, result.output + result.stderr

    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 2
    first_body = json.loads(post_calls[0].request.body)
    second_body = json.loads(post_calls[1].request.body)
    assert len(first_body["issues"]) == 50
    assert len(second_body["issues"]) == 1

    data = json.loads(result.stdout)["data"]
    assert data["chunks"] == 2


# ==================== SA-CMD-5 — epic without --children → exit 1 ====================


@resp_lib.activate
def test_sprint_add_epic_without_children_flag_exits_1(runner, app) -> None:
    """SA-CMD-5: epic detected without --children → UserError exit 1, teaching message."""
    _mock_get_issue("EPIC-1", _epic_payload("EPIC-1"))

    result = runner.invoke(app, ["sprint", "add", "42", "EPIC-1"])
    assert result.exit_code == 1, result.output + result.stderr
    assert "cannot be added to a sprint" in result.stderr
    assert "--children" in result.stderr

    # No agile POST should have been made
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 0


# ==================== SA-CMD-6 — epic WITH --children expands ====================


@resp_lib.activate
def test_sprint_add_epic_with_children_expands(runner, app) -> None:
    """SA-CMD-6: epic + --children → children added, no epic key in added."""
    _mock_get_issue("EPIC-1", _epic_payload("EPIC-1"))
    # Search for children of EPIC-1
    resp_lib.post(
        f"{_DOMAIN}/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-2"}, {"key": "PROJ-3"}]},
        status=200,
    )
    _mock_sprint_post(42)

    result = runner.invoke(app, ["sprint", "add", "42", "EPIC-1", "--children", "--json"])
    assert result.exit_code == 0, result.output + result.stderr

    data = json.loads(result.stdout)["data"]
    assert data["added"] == ["PROJ-2", "PROJ-3"]
    assert data["expanded_from_epics"] == {"EPIC-1": ["PROJ-2", "PROJ-3"]}
    assert "EPIC-1" not in data["added"]

    # Verify POST body
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"
                  and "/sprint/" in c.request.url]
    assert len(post_calls) == 1
    body = json.loads(post_calls[0].request.body)
    assert body["issues"] == ["PROJ-2", "PROJ-3"]


# ==================== SA-CMD-7 — epic with no children + other issue ====================


@resp_lib.activate
def test_sprint_add_epic_no_children_with_other_issue(runner, app) -> None:
    """SA-CMD-7: epic has no children → warning on stderr; PROJ-1 still added."""
    _mock_get_issue("EPIC-1", _epic_payload("EPIC-1"))
    resp_lib.post(
        f"{_DOMAIN}/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    _mock_get_issue("PROJ-1", _non_epic_payload("PROJ-1"))
    _mock_sprint_post(42)

    result = runner.invoke(
        app, ["sprint", "add", "42", "EPIC-1", "PROJ-1", "--children", "--json"]
    )
    assert result.exit_code == 0, result.output + result.stderr
    assert "EPIC-1" in result.stderr
    # warning: "no children" or "has no children"
    assert "children" in result.stderr.lower()

    data = json.loads(result.stdout)["data"]
    assert data["added"] == ["PROJ-1"]


# ==================== SA-CMD-8 — epic no children + no other issues → exit 1 ====================


@resp_lib.activate
def test_sprint_add_epic_no_children_only_exit_1(runner, app) -> None:
    """SA-CMD-8: single epic with no children → UserError exit 1 'Nothing to add'."""
    _mock_get_issue("EPIC-1", _epic_payload("EPIC-1"))
    resp_lib.post(
        f"{_DOMAIN}/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )

    result = runner.invoke(app, ["sprint", "add", "42", "EPIC-1", "--children"])
    assert result.exit_code == 1, result.output + result.stderr
    assert "Nothing to add" in result.stderr


# ==================== SA-CMD-9 — dedupe epic + explicit child ====================


@resp_lib.activate
def test_sprint_add_dedupe_epic_and_explicit_child(runner, app) -> None:
    """SA-CMD-9: EPIC-1 and its child PROJ-2 both supplied → PROJ-2 appears once."""
    _mock_get_issue("EPIC-1", _epic_payload("EPIC-1"))
    _mock_get_issue("PROJ-2", _non_epic_payload("PROJ-2"))
    resp_lib.post(
        f"{_DOMAIN}/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-2"}, {"key": "PROJ-3"}]},
        status=200,
    )
    _mock_sprint_post(42)

    result = runner.invoke(
        app, ["sprint", "add", "42", "EPIC-1", "PROJ-2", "--children", "--json"]
    )
    assert result.exit_code == 0, result.output + result.stderr

    data = json.loads(result.stdout)["data"]
    assert data["added"].count("PROJ-2") == 1, "PROJ-2 must appear exactly once"
    assert "PROJ-3" in data["added"]


# ==================== SA-CMD-10 — invalid key format → exit 1 ====================


@resp_lib.activate
def test_sprint_add_invalid_key_exits_1(runner, app) -> None:
    """SA-CMD-10: bad key format → UserError exit 1 'Invalid issue key'."""
    result = runner.invoke(app, ["sprint", "add", "42", "not-a-key"])
    assert result.exit_code == 1, result.output + result.stderr
    assert "Invalid issue key" in result.stderr
    assert len(resp_lib.calls) == 0


# ==================== SA-CMD-11 — Jira API error on POST → exit 2 ====================


@resp_lib.activate
def test_sprint_add_jira_api_error_exits_2(runner, app) -> None:
    """SA-CMD-11: POST sprint/42/issue returns 404 → APIError exit 2."""
    _mock_get_issue("PROJ-1", _non_epic_payload("PROJ-1"))
    resp_lib.post(
        f"{_DOMAIN}/rest/agile/1.0/sprint/42/issue",
        json={"errorMessages": ["Sprint not found"]},
        status=404,
    )

    result = runner.invoke(app, ["sprint", "add", "42", "PROJ-1"])
    assert result.exit_code == 2, result.output + result.stderr
    assert "Sprint not found" in result.stderr or "404" in result.stderr


# ==================== SA-CMD-13 — help discoverability ====================


def test_sprint_help_contains_add(runner, app) -> None:
    """SA-CMD-13a: 'sprint --help' → exit 0, stdout has 'add'."""
    result = runner.invoke(app, ["sprint", "--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout


def test_root_help_contains_sprint(runner, app) -> None:
    """SA-CMD-13b: '--help' → exit 0, stdout has 'sprint'."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sprint" in result.stdout
