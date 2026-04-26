"""Tests for ``tjira profile``, ``tjira switch`` and the global ``--profile`` flag.

Each test runs against a fresh ``XDG_CONFIG_HOME`` (see ``conftest.py``) so the
real ``~/.config/tjira/`` is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tjira.profiles import Profile, ProfileStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app():
    from tjira.cli import app as _app
    return _app


def _store(tmp_path: Path) -> ProfileStore:
    return ProfileStore.load(tmp_path / "tjira" / "config.toml")


# ====================== profile add ======================


def test_profile_add_with_flags(runner, app, tmp_path):
    result = runner.invoke(
        app,
        [
            "profile", "add", "work",
            "--domain", "company.atlassian.net",
            "--email", "me@company.com",
            "--token", "tok-123",
        ],
    )
    assert result.exit_code == 0, result.output
    store = _store(tmp_path)
    assert store.get("work") == Profile(
        "work", "company.atlassian.net", "me@company.com", "tok-123"
    )


def test_profile_add_first_profile_becomes_active(runner, app, tmp_path):
    runner.invoke(
        app,
        ["profile", "add", "work",
         "--domain", "x.atlassian.net", "--email", "x@x.com", "--token", "t"],
    )
    assert _store(tmp_path).current == "work"


def test_profile_add_second_profile_does_not_steal_active(runner, app, tmp_path, configured_profile):
    runner.invoke(
        app,
        ["profile", "add", "personal",
         "--domain", "y.atlassian.net", "--email", "y@y.com", "--token", "t"],
    )
    store = _store(tmp_path)
    assert store.current == "default"
    assert "personal" in store.names()


def test_profile_add_rejects_existing_without_force(runner, app, configured_profile):
    result = runner.invoke(
        app,
        ["profile", "add", "default",
         "--domain", "x.atlassian.net", "--email", "x@x.com", "--token", "t"],
    )
    assert result.exit_code == 1


def test_profile_add_force_overwrites(runner, app, tmp_path, configured_profile):
    result = runner.invoke(
        app,
        ["profile", "add", "default",
         "--domain", "new.atlassian.net", "--email", "new@x.com", "--token", "t2",
         "--force"],
    )
    assert result.exit_code == 0, result.output
    assert _store(tmp_path).get("default").domain == "new.atlassian.net"


def test_profile_add_interactive(runner, app, tmp_path):
    """No credential flags → CLI prompts for each field."""
    result = runner.invoke(
        app,
        ["profile", "add", "work"],
        input="company.atlassian.net\nme@company.com\ntok-int\n",
    )
    assert result.exit_code == 0, result.output
    p = _store(tmp_path).get("work")
    assert p.domain == "company.atlassian.net"
    assert p.email == "me@company.com"
    assert p.api_token == "tok-int"


def test_profile_add_from_env(runner, app, tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_DOMAIN", "company.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "me@company.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-env")
    result = runner.invoke(app, ["profile", "add", "migrated", "--from-env"])
    assert result.exit_code == 0, result.output
    p = _store(tmp_path).get("migrated")
    assert p.domain == "company.atlassian.net"
    assert p.email == "me@company.com"
    assert p.api_token == "tok-env"


def test_profile_add_from_env_missing_vars_exits_1(runner, app, monkeypatch):
    for var in ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    result = runner.invoke(app, ["profile", "add", "migrated", "--from-env"])
    assert result.exit_code == 1


# ====================== profile list ======================


def test_profile_list_empty_human(runner, app):
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "No profiles" in result.stdout


def test_profile_list_empty_json(runner, app):
    result = runner.invoke(app, ["profile", "list", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"] == {"current": None, "profiles": []}


def test_profile_list_marks_active(runner, app, tmp_path, configured_profile):
    store = _store(tmp_path)
    store.add(Profile("other", "y.atlassian.net", "y@y.com", "t"))
    store.save()

    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "other" in result.stdout
    # the active line must have a visible marker (asterisk is the convention)
    active_line = next(
        line for line in result.stdout.splitlines() if "default" in line and "@" in line
    )
    assert "*" in active_line


def test_profile_list_json_payload(runner, app, configured_profile):
    result = runner.invoke(app, ["profile", "list", "--json"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    data = envelope["data"]
    assert data["current"] == "default"
    names = [p["name"] for p in data["profiles"]]
    assert "default" in names
    # tokens MUST NOT leak in the JSON payload
    payload_str = json.dumps(data)
    assert "test-token" not in payload_str


# ====================== profile current ======================


def test_profile_current_prints_active_name(runner, app, configured_profile):
    result = runner.invoke(app, ["profile", "current"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "default"


def test_profile_current_no_active_exits_1(runner, app):
    result = runner.invoke(app, ["profile", "current"])
    assert result.exit_code == 1


# ====================== profile rm ======================


def test_profile_rm_removes_with_yes(runner, app, tmp_path, configured_profile):
    store = _store(tmp_path)
    store.add(Profile("other", "y.atlassian.net", "y@y.com", "t"))
    store.save()
    result = runner.invoke(app, ["profile", "rm", "other", "--yes"])
    assert result.exit_code == 0, result.output
    assert not _store(tmp_path).has("other")


def test_profile_rm_missing_exits_1(runner, app):
    result = runner.invoke(app, ["profile", "rm", "ghost", "--yes"])
    assert result.exit_code == 1


def test_profile_rm_active_clears_current(runner, app, tmp_path, configured_profile):
    result = runner.invoke(app, ["profile", "rm", "default", "--yes"])
    assert result.exit_code == 0, result.output
    assert _store(tmp_path).current is None


def test_profile_rm_prompts_when_no_yes_flag(runner, app, tmp_path, configured_profile):
    """Without --yes the command prompts; answering "n" keeps the profile."""
    runner.invoke(app, ["profile", "rm", "default"], input="n\n")
    assert _store(tmp_path).has("default")


# ====================== switch ======================


def test_switch_changes_active(runner, app, tmp_path, configured_profile):
    store = _store(tmp_path)
    store.add(Profile("other", "y.atlassian.net", "y@y.com", "t"))
    store.save()
    result = runner.invoke(app, ["switch", "other"])
    assert result.exit_code == 0, result.output
    assert _store(tmp_path).current == "other"


def test_switch_unknown_exits_1(runner, app, configured_profile):
    result = runner.invoke(app, ["switch", "ghost"])
    assert result.exit_code == 1


# ====================== --profile global flag ======================


def test_global_profile_flag_warns_on_stderr(runner, app, tmp_path, configured_profile):
    store = _store(tmp_path)
    store.add(Profile("personal", "y.atlassian.net", "y@y.com", "t"))
    store.save()

    result = runner.invoke(app, ["--profile", "personal", "profile", "current"])
    assert result.exit_code == 0
    assert "Using profile: personal" in result.stderr


def test_global_profile_flag_silent_when_matches_active(runner, app, configured_profile):
    result = runner.invoke(app, ["--profile", "default", "profile", "current"])
    assert "Using profile: default" not in result.stderr


# ====================== security: domain hijack mitigation ======================


def test_profile_add_rejects_domain_with_userinfo(runner, app, tmp_path):
    """A domain like ``real@evil.com`` would route the token to the attacker."""
    result = runner.invoke(
        app,
        ["profile", "add", "work",
         "--domain", "real.atlassian.net@evil.com",
         "--email", "x@x.com",
         "--token", "tok-secret"],
    )
    assert result.exit_code == 1
    assert not (tmp_path / "tjira" / "config.toml").exists()


def test_profile_add_rejects_domain_with_scheme(runner, app, tmp_path):
    result = runner.invoke(
        app,
        ["profile", "add", "work",
         "--domain", "https://x.atlassian.net",
         "--email", "x@x.com",
         "--token", "t"],
    )
    assert result.exit_code == 1
    assert not (tmp_path / "tjira" / "config.toml").exists()


def test_profile_add_rejects_domain_with_path(runner, app, tmp_path):
    result = runner.invoke(
        app,
        ["profile", "add", "work",
         "--domain", "x.atlassian.net/admin",
         "--email", "x@x.com",
         "--token", "t"],
    )
    assert result.exit_code == 1
    assert not (tmp_path / "tjira" / "config.toml").exists()


def test_profile_add_from_env_rejects_malicious_domain(runner, app, tmp_path, monkeypatch):
    """``--from-env`` is the highest-risk path: env vars may be attacker-controlled."""
    monkeypatch.setenv("JIRA_DOMAIN", "real.atlassian.net@evil.com")
    monkeypatch.setenv("JIRA_EMAIL", "x@x.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-leaked")
    result = runner.invoke(app, ["profile", "add", "x", "--from-env"])
    assert result.exit_code == 1
    assert not (tmp_path / "tjira" / "config.toml").exists()


def test_profile_add_rejects_invalid_name(runner, app):
    result = runner.invoke(
        app,
        ["profile", "add", "../etc/passwd",
         "--domain", "x.atlassian.net",
         "--email", "x@x.com",
         "--token", "t"],
    )
    assert result.exit_code == 1


def test_profile_add_rejects_empty_name(runner, app):
    result = runner.invoke(
        app,
        ["profile", "add", "",
         "--domain", "x.atlassian.net",
         "--email", "x@x.com",
         "--token", "t"],
    )
    assert result.exit_code != 0
