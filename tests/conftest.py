"""Fixtures compartidas para tests de tjira.

`tjira.config` lee variables al importarse vía `load_dotenv()` — si el dev
tiene un `.env` real en cwd, los tests heredan esas credenciales. Forzamos un
entorno determinístico acá para que los tests no dependan del host.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla las variables JIRA_* por default; los tests que las necesiten las setean."""
    for key in ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_TIMEZONE", "JIRA_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)

    # Purgamos módulos que cachean env en import-time para que el monkeypatch aplique.
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
    """Entorno Jira válido para los tests que corren con credenciales puestas."""
    monkeypatch.setenv("JIRA_DOMAIN", "example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
