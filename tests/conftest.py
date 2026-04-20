"""Shared fixtures for tjira tests.

`tjira.config` reads environment variables at import time via `load_dotenv()` —
if a developer has a real `.env` in cwd, tests would inherit those
credentials. We force a deterministic environment here so tests do not depend
on the host.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate JIRA_* variables by default; tests that need them set them explicitly."""
    for key in ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_TIMEZONE", "JIRA_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)

    # Drop modules that cache env at import-time so the monkeypatch actually applies.
    for mod in [
        "tjira.config",
        "tjira.client",
        "tjira.commands.doctor",
        "tjira.commands.log",
        "tjira.commands.issue",
        "tjira.commands.list_cmd",
        "tjira.commands.worklog",
        "tjira.cli",
    ]:
        sys.modules.pop(mod, None)


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid Jira environment for tests that run with credentials set."""
    monkeypatch.setenv("JIRA_DOMAIN", "example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
