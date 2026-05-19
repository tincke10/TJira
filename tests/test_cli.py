"""Smoke tests of the CLI layer using Typer's CliRunner.

Focus: that every subcommand registers, accepts `--help`, and that `--json`
plus exit codes behave correctly on both happy paths and error paths.
"""

from __future__ import annotations

import json

import pytest
import responses
from typer.testing import CliRunner


@pytest.fixture
def runner():
    # In Click 8.2+ stdout and stderr are always captured separately — the
    # former `mix_stderr=False` was removed because that is the implicit default.
    return CliRunner()


def _last_json_line(stream: str) -> dict:
    """stderr may contain progress logs followed by the error JSON — grab the JSON."""
    for line in reversed(stream.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON found in stream: {stream!r}")


@pytest.fixture
def app(configured_profile):
    """CLI app with a seeded ``default`` profile in the test config."""
    from tjira.cli import app
    return app


# ========== help & version ==========

def test_help_lists_all_subcommands(runner, app):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("log", "issue", "list", "worklog", "doctor"):
        assert cmd in result.stdout


def test_version_flag(runner, app):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "tjira" in result.stdout
    assert "0.1.0" in result.stdout


def test_no_args_shows_dashboard_with_active_profile(runner, app):
    """`tjira` (no subcommand) renders the dashboard view of the active profile."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Active profile" in result.stdout
    assert "default" in result.stdout
    assert "example.atlassian.net" in result.stdout


def test_no_args_dashboard_when_empty_shows_onboarding_hint(runner):
    """No profile + non-TTY → empty-state hint, no prompt."""
    from tjira.cli import app
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "No Jira profile configured" in result.stdout
    assert "tjira profile add" in result.stdout


# ========== doctor ==========

@responses.activate
def test_doctor_all_checks_pass(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"displayName": "Test User", "emailAddress": "test@example.com",
              "accountId": "abc"},
        status=200,
    )
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["all_passed"] is True


def test_doctor_reports_invalid_domain_shape(runner, tmp_path):
    """Profile with a malformed domain (scheme included) flags ``domain_shape``."""
    from tjira.profiles import Profile, ProfileStore
    store = ProfileStore(path=tmp_path / "tjira" / "config.toml")
    store.add(Profile("default", "https://example.atlassian.net/", "x@x.com", "t"))
    store.set_current("default")
    store.save()

    from tjira.cli import app
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert envelope["data"]["all_passed"] is False
    failed_names = {c["name"] for c in envelope["data"]["checks"] if not c["passed"]}
    assert "domain_shape" in failed_names


def test_doctor_fails_when_no_profile_configured(runner):
    """Without ``configured_profile`` the store is empty and ``profile`` check fails."""
    from tjira.cli import app
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    failed = [c["name"] for c in envelope["data"]["checks"] if not c["passed"]]
    assert "profile" in failed


# ========== log ==========

def _mock_no_existing_worklogs() -> None:
    """Stub /myself + /search/jql so the overlap pre-check finds nothing."""
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )


@responses.activate
def test_log_happy_path_json(runner, app):
    _mock_no_existing_worklogs()
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "77", "timeSpent": "2h",
              "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )
    result = runner.invoke(
        app, ["log", "PROJ-1", "2h", "2026-04-20 09:00", "--json"]
    )
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["id"] == "77"


@responses.activate
def test_log_api_error_exits_2(runner, app):
    _mock_no_existing_worklogs()
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"errorMessages": ["Issue does not exist"]},
        status=404,
    )
    result = runner.invoke(
        app, ["log", "PROJ-1", "2h", "2026-04-20 09:00", "--json"]
    )
    assert result.exit_code == 2
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False
    assert envelope["status"] == 404


def test_log_invalid_date_exits_1(runner, app):
    result = runner.invoke(app, ["log", "PROJ-1", "2h", "not-a-date", "--json"])
    assert result.exit_code == 1
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False


@responses.activate
def test_log_overlap_exits_3_with_payload(runner, app, monkeypatch):
    """Existing worklog 09:30-10:30 UTC; user logs 09:00-10:00 UTC → exit 3."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-9"}]},
        status=200,
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-9/worklog",
        json={"worklogs": [{
            "id": "55",
            "author": {"accountId": "me-123"},
            "started": "2026-04-20T09:30:00.000+0000",
            "timeSpentSeconds": 3600,
            "timeSpent": "1h",
        }]},
        status=200,
    )
    # No POST registered — if the command tries to post, the test fails.
    result = runner.invoke(
        app, ["log", "PROJ-1", "1h", "2026-04-20 09:00", "--json"]
    )
    assert result.exit_code == 3
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False
    assert envelope["conflict"]["issue"] == "PROJ-9"
    assert envelope["conflict"]["worklog_id"] == "55"
    # Existing ends at 10:30 — suggested start aligns with that.
    assert "10:30" in envelope["suggested_start"]


@responses.activate
def test_log_overlap_force_bypasses_check(runner, app):
    """--force skips the overlap pre-check entirely."""
    # No /myself or /search/jql mock — they must NOT be called when --force is set.
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "99", "timeSpent": "1h",
              "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )
    result = runner.invoke(
        app, ["log", "PROJ-1", "1h", "2026-04-20 09:00", "--force", "--json"]
    )
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"]["id"] == "99"


# ========== list ==========

@responses.activate
def test_list_boards_json(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/agile/1.0/board",
        json={"values": [{"id": 1, "name": "Board A", "type": "scrum"}]},
        status=200,
    )
    result = runner.invoke(app, ["list", "boards", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"][0]["name"] == "Board A"


@responses.activate
def test_list_issues_builds_jql_from_flags(runner, app):
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    result = runner.invoke(
        app, ["list", "issues", "--project", "PROJ", "--status", "Done", "--json"]
    )
    assert result.exit_code == 0
    sent_body = responses.calls[0].request.body
    if isinstance(sent_body, bytes):
        sent_body = sent_body.decode("utf-8")
    sent = json.loads(sent_body)
    assert "project = PROJ" in sent["jql"]
    assert "status = 'Done'" in sent["jql"]


# ========== issue ==========

@responses.activate
def test_issue_get_json(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1",
        json={"key": "PROJ-1", "fields": {"summary": "hi", "status": {"name": "To Do"}}},
        status=200,
    )
    result = runner.invoke(app, ["issue", "get", "PROJ-1", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"]["key"] == "PROJ-1"
    assert envelope["data"]["status"] == "To Do"


@responses.activate
def test_issue_transitions_lists(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/transitions",
        json={"transitions": [
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
            {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
        ]},
        status=200,
    )
    result = runner.invoke(app, ["issue", "transitions", "PROJ-1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 2
    assert {t["name"] for t in data} == {"Done", "In Progress"}


# ========== G3: issue create/update --parent ==========

@responses.activate
def test_issue_create_with_parent_exits_0_and_sends_parent_in_body(runner, app):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue",
        json={"key": "PROJ-99", "id": "200"},
        status=201,
    )
    result = runner.invoke(app, ["issue", "create", "PROJ", "My task", "--parent", "EPIC-1", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["parent_key"] == "EPIC-1"

    sent_body = responses.calls[0].request.body
    if isinstance(sent_body, bytes):
        sent_body = sent_body.decode("utf-8")
    payload = json.loads(sent_body)
    assert payload["fields"]["parent"] == {"key": "EPIC-1"}


@responses.activate
def test_issue_update_with_parent_sends_parent_in_body(runner, app):
    responses.put(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-10",
        status=204,
    )
    result = runner.invoke(app, ["issue", "update", "PROJ-10", "--parent", "EPIC-2", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"]["parent_key"] == "EPIC-2"

    sent_body = responses.calls[0].request.body
    if isinstance(sent_body, bytes):
        sent_body = sent_body.decode("utf-8")
    payload = json.loads(sent_body)
    assert payload["fields"]["parent"] == {"key": "EPIC-2"}


@responses.activate
def test_issue_update_with_parent_none_sends_null_parent(runner, app):
    responses.put(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-10",
        status=204,
    )
    result = runner.invoke(app, ["issue", "update", "PROJ-10", "--parent", "NONE", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"]["parent_key"] is None

    sent_body = responses.calls[0].request.body
    if isinstance(sent_body, bytes):
        sent_body = sent_body.decode("utf-8")
    payload = json.loads(sent_body)
    assert payload["fields"]["parent"] is None


@responses.activate
def test_issue_create_classic_project_error_becomes_user_error(runner, app):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue",
        json={"errors": {"customfield_10014": "Epic Link is required"}},
        status=400,
    )
    result = runner.invoke(app, ["issue", "create", "CLASSIC", "x", "--parent", "EPIC-1", "--json"])
    assert result.exit_code == 1
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False
    assert "classic" in envelope["error"].lower() or "classic-style" in envelope["error"].lower()
    assert "original_error" in envelope
    assert "parent_key" in envelope


# ========== worklog ==========

def test_worklog_import_missing_csv_exits_1(runner, app, tmp_path):
    result = runner.invoke(app, ["worklog", "import", str(tmp_path / "nope.csv"), "--json"])
    assert result.exit_code == 1


def test_worklog_import_dry_run_no_http(runner, app, tmp_path):
    csv = tmp_path / "wl.csv"
    csv.write_text(
        "Jira Key,Time Spent,Started\n"
        "PROJ-1,2h,2026-04-20T09:00:00.000+0000\n"
        "PROJ-2,1h,2026-04-20T11:00:00.000+0000\n",
        encoding="utf-8",
    )
    # --no-adjust + --dry-run = no HTTP at all (offline preview).
    result = runner.invoke(
        app, ["worklog", "import", str(csv), "--dry-run", "--no-adjust", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["dry_run"] is True
    assert data["success_count"] == 2
    assert data["error_count"] == 0
    assert data["adjusted_count"] == 0


@responses.activate
def test_worklog_import_cascade_adjusts_internal_overlaps(runner, app, tmp_path, monkeypatch):
    """Three rows that chain back-to-back when adjusted."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    csv = tmp_path / "wl.csv"
    csv.write_text(
        "Jira Key,Time Spent,Started\n"
        "PROJ-1,1h,2026-04-20T09:00:00.000+0000\n"
        "PROJ-2,1h,2026-04-20T09:30:00.000+0000\n"
        "PROJ-3,1h,2026-04-20T10:00:00.000+0000\n",
        encoding="utf-8",
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": []},
        status=200,
    )
    # We use --dry-run so no POSTs are needed.
    result = runner.invoke(
        app, ["worklog", "import", str(csv), "--dry-run", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["success_count"] == 3
    assert data["adjusted_count"] == 2  # rows 2 and 3 displaced
    starts = [s["started"] for s in data["success"]]
    # Row 1: 09:00 (untouched). Row 2: shifted to 10:00. Row 3: shifted to 11:00.
    assert "T09:00:00" in starts[0]
    assert "T10:00:00" in starts[1]
    assert "T11:00:00" in starts[2]


@responses.activate
def test_worklog_import_adjusts_against_existing_jira_worklog(runner, app, tmp_path, monkeypatch):
    """A row that would overlap with a worklog ALREADY in Jira gets pushed."""
    monkeypatch.setenv("JIRA_TIMEZONE", "UTC")
    csv = tmp_path / "wl.csv"
    csv.write_text(
        "Jira Key,Time Spent,Started\n"
        "PROJ-1,1h,2026-04-20T09:00:00.000+0000\n",
        encoding="utf-8",
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/myself",
        json={"accountId": "me-123"},
        status=200,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "PROJ-EXISTING"}]},
        status=200,
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-EXISTING/worklog",
        json={"worklogs": [{
            "id": "999",
            "author": {"accountId": "me-123"},
            "started": "2026-04-20T08:30:00.000+0000",
            "timeSpentSeconds": 3600,
            "timeSpent": "1h",
        }]},
        status=200,
    )
    result = runner.invoke(
        app, ["worklog", "import", str(csv), "--dry-run", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["adjusted_count"] == 1
    # Row pushed from 09:00 to 09:30 (end of the existing 08:30+1h).
    assert "T09:30:00" in data["success"][0]["started"]


# ========== G4: list discovery commands ==========

@responses.activate
def test_list_projects_json_returns_normalized_array(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/project/search",
        json={
            "values": [
                {"key": "PROJ", "name": "My Project", "projectTypeKey": "software", "style": "next-gen"},
                {"key": "OPS", "name": "Ops", "projectTypeKey": "business", "style": "classic"},
            ],
            "isLast": True,
        },
        status=200,
    )
    result = runner.invoke(app, ["list", "projects", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 2
    assert data[0]["key"] == "PROJ"
    assert data[0]["type"] == "software"
    assert data[0]["style"] == "next-gen"


@responses.activate
def test_list_projects_type_filter_forwarded_as_typekey(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/project/search",
        json={"values": [], "isLast": True},
        status=200,
    )
    result = runner.invoke(app, ["list", "projects", "--limit", "100", "--type", "software", "--json"])
    assert result.exit_code == 0

    import urllib.parse
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(responses.calls[0].request.url).query)
    assert qs["typeKey"] == ["software"]
    assert qs["maxResults"] == ["100"]


def test_list_projects_limit_zero_exits_1(runner, app):
    result = runner.invoke(app, ["list", "projects", "--limit", "0", "--json"])
    assert result.exit_code == 1
    assert len(responses.calls) == 0


@responses.activate
def test_list_projects_empty_returns_empty_json_array(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/project/search",
        json={"values": [], "isLast": True},
        status=200,
    )
    result = runner.invoke(app, ["list", "projects", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"] == []


@responses.activate
def test_list_issue_types_json_returns_normalized_array(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes",
        json={
            "values": [
                {"id": "10001", "name": "Task", "subtask": False, "description": "A task"},
                {"id": "10002", "name": "Bug", "subtask": False, "description": "A bug"},
            ],
            "isLast": True,
        },
        status=200,
    )
    result = runner.invoke(app, ["list", "issue-types", "PROJ", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 2
    assert data[0]["id"] == "10001"
    assert data[0]["subtask"] is False


def test_list_issue_types_empty_project_key_exits_1(runner, app):
    result = runner.invoke(app, ["list", "issue-types", "", "--json"])
    assert result.exit_code == 1
    assert len(responses.calls) == 0


@responses.activate
def test_list_issue_types_404_exits_2(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/GHOST/issuetypes",
        json={"errorMessages": ["project not found"]},
        status=404,
    )
    result = runner.invoke(app, ["list", "issue-types", "GHOST", "--json"])
    assert result.exit_code == 2
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False
    assert "project_key" in envelope


@responses.activate
def test_list_users_json_with_and_without_email(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/user/search",
        json=[
            {"accountId": "acc-1", "displayName": "John", "emailAddress": "john@x.com", "active": True},
            {"accountId": "acc-2", "displayName": "Jane", "active": True},
        ],
        status=200,
    )
    result = runner.invoke(app, ["list", "users", "john", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 2
    assert data[0]["email"] == "john@x.com"
    assert data[1]["email"] is None


def test_list_users_empty_query_exits_1(runner, app):
    result = runner.invoke(app, ["list", "users", "", "--json"])
    assert result.exit_code == 1
    assert len(responses.calls) == 0


def test_list_users_limit_zero_exits_1(runner, app):
    result = runner.invoke(app, ["list", "users", "john", "--limit", "0", "--json"])
    assert result.exit_code == 1


@responses.activate
def test_list_users_empty_response_returns_empty_array(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/user/search",
        json=[],
        status=200,
    )
    result = runner.invoke(app, ["list", "users", "nobody", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"] == []


@responses.activate
def test_list_fields_json_two_roundtrip(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes",
        json={
            "values": [{"id": "10001", "name": "Task", "subtask": False, "description": ""}],
            "isLast": True,
        },
        status=200,
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes/10001",
        json={
            "values": [
                {"name": "Summary", "key": "summary", "required": True, "schema": {"type": "string"}},
                {"name": "Priority", "key": "priority", "required": False,
                 "schema": {"type": "priority"},
                 "allowedValues": [{"name": "High"}, {"name": "Low"}]},
            ]
        },
        status=200,
    )
    result = runner.invoke(app, ["list", "fields", "PROJ", "Task", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 2
    summary = next(f for f in data if f["key"] == "summary")
    assert summary["required"] is True
    assert summary["allowed_values"] is None
    priority = next(f for f in data if f["key"] == "priority")
    assert priority["allowed_values"] == ["High", "Low"]
    assert len(responses.calls) == 2


@responses.activate
def test_list_fields_required_only_filters_output(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes",
        json={
            "values": [{"id": "10001", "name": "Task", "subtask": False, "description": ""}],
            "isLast": True,
        },
        status=200,
    )
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes/10001",
        json={
            "values": [
                {"name": "Summary", "key": "summary", "required": True, "schema": {"type": "string"}},
                {"name": "Priority", "key": "priority", "required": False, "schema": {"type": "priority"}},
                {"name": "Assignee", "key": "assignee", "required": False, "schema": {"type": "user"}},
            ]
        },
        status=200,
    )
    result = runner.invoke(app, ["list", "fields", "PROJ", "Task", "--required-only", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert len(data) == 1
    assert data[0]["required"] is True


@responses.activate
def test_list_fields_ghost_issuetype_exits_2(runner, app):
    responses.get(
        "https://example.atlassian.net/rest/api/3/issue/createmeta/PROJ/issuetypes",
        json={
            "values": [{"id": "10001", "name": "Task", "subtask": False, "description": ""}],
            "isLast": True,
        },
        status=200,
    )
    result = runner.invoke(app, ["list", "fields", "PROJ", "GhostType", "--json"])
    assert result.exit_code == 2
    envelope = _last_json_line(result.stderr)
    assert "GhostType" in envelope["error"]
    assert envelope["project_key"] == "PROJ"
    assert envelope["issue_type"] == "GhostType"
    assert "available_types" in envelope


def test_list_fields_limit_zero_exits_1(runner, app):
    result = runner.invoke(app, ["list", "fields", "PROJ", "Task", "--limit", "0", "--json"])
    assert result.exit_code == 1


@responses.activate
def test_worklog_import_no_adjust_keeps_legacy_behavior(runner, app, tmp_path):
    """--no-adjust skips the overlap check entirely; no /myself or /search/jql calls."""
    csv = tmp_path / "wl.csv"
    csv.write_text(
        "Jira Key,Time Spent,Started\n"
        "PROJ-1,1h,2026-04-20T09:00:00.000+0000\n"
        "PROJ-2,1h,2026-04-20T09:30:00.000+0000\n",
        encoding="utf-8",
    )
    # POSTs both rows as-is — no pre-flight calls.
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "1", "timeSpent": "1h",
              "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-2/worklog",
        json={"id": "2", "timeSpent": "1h",
              "started": "2026-04-20T09:30:00.000+0000"},
        status=201,
    )
    result = runner.invoke(
        app, ["worklog", "import", str(csv), "--no-adjust", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["success_count"] == 2
    assert data["adjusted_count"] == 0
