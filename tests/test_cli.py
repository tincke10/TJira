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

@responses.activate
def test_log_happy_path_json(runner, app):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"id": "77", "timeSpent": "2h",
              "started": "2026-04-20T09:00:00.000+0000"},
        status=201,
    )
    result = runner.invoke(app, ["log", "PROJ-1", "2h", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["id"] == "77"


@responses.activate
def test_log_api_error_exits_2(runner, app):
    responses.post(
        "https://example.atlassian.net/rest/api/3/issue/PROJ-1/worklog",
        json={"errorMessages": ["Issue does not exist"]},
        status=404,
    )
    result = runner.invoke(app, ["log", "PROJ-1", "2h", "--json"])
    assert result.exit_code == 2
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False
    assert envelope["status"] == 404


def test_log_invalid_date_exits_1(runner, app):
    result = runner.invoke(app, ["log", "PROJ-1", "2h", "not-a-date", "--json"])
    assert result.exit_code == 1
    envelope = _last_json_line(result.stderr)
    assert envelope["ok"] is False


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


# ========== worklog ==========

def test_worklog_import_missing_csv_exits_1(runner, app, tmp_path):
    result = runner.invoke(app, ["worklog", "import", str(tmp_path / "nope.csv"), "--json"])
    assert result.exit_code == 1


def test_worklog_import_dry_run_no_http(runner, app, tmp_path):
    csv = tmp_path / "wl.csv"
    csv.write_text(
        "Jira Key,Time Spent,Started\n"
        "PROJ-1,2h,2026-04-20T09:00:00.000+0000\n"
        "PROJ-2,1h,2026-04-20T10:00:00.000+0000\n",
        encoding="utf-8",
    )
    # Without `@responses.activate`, any real HTTP would make the test flaky.
    # In dry-run the client is never constructed.
    result = runner.invoke(app, ["worklog", "import", str(csv), "--dry-run", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["dry_run"] is True
    assert data["success_count"] == 2
    assert data["error_count"] == 0
