"""Tests for configuration validation."""

from __future__ import annotations

import importlib

import pytest

from tjira.errors import UserError


def _reload_config(monkeypatch: pytest.MonkeyPatch):
    """Re-import `tjira.config` so it picks up env vars set by monkeypatch."""
    # Prevent `load_dotenv` from overriding env vars from a real host `.env`.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    import tjira.config as cfg
    return importlib.reload(cfg)


def test_validate_config_raises_when_all_missing(monkeypatch: pytest.MonkeyPatch):
    cfg = _reload_config(monkeypatch)
    with pytest.raises(UserError) as exc_info:
        cfg.validate_config()
    assert exc_info.value.payload["missing"] == [
        "JIRA_DOMAIN",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
    ]


def test_validate_config_reports_only_missing_subset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_DOMAIN", "example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    cfg = _reload_config(monkeypatch)
    with pytest.raises(UserError) as exc_info:
        cfg.validate_config()
    assert exc_info.value.payload["missing"] == ["JIRA_API_TOKEN"]


def test_validate_config_passes_when_all_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JIRA_DOMAIN", "example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    cfg = _reload_config(monkeypatch)
    cfg.validate_config()  # no raise
