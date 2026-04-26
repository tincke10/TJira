"""Shared fixtures for tjira tests.

Profiles live in ``$XDG_CONFIG_HOME/tjira/config.toml``. Every test runs with
``XDG_CONFIG_HOME`` pointed at a fresh ``tmp_path`` so we never read or write
the developer's real ``~/.config/tjira/`` while tests are running.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tjira.profiles import Profile, ProfileStore


@pytest.fixture(autouse=True)
def _isolate_profile_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect the profile store path and reset the per-invocation override."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Reset any --profile override that a previous test may have set.
    import tjira.config as cfg
    monkeypatch.setattr(cfg, "_override", None)

    # Defensive: clear any host JIRA_TIMEZONE/JIRA_TIMEOUT that could change behavior.
    for key in ("JIRA_TIMEZONE", "JIRA_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def configured_profile(tmp_path: Path) -> Profile:
    """Write a single ``default`` profile to the test config and mark it active."""
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
