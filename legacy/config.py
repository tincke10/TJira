"""Centralized config for the legacy Jira scripts.

Reads ``JIRA_DOMAIN`` / ``JIRA_EMAIL`` / ``JIRA_API_TOKEN`` from the process
environment. If you keep a ``.env`` file from the pre-tjira era, source it
before running these scripts:

    set -a && . ./.env && set +a
    python legacy/log_hours.py PROJ-123 2h

For new code prefer the ``tjira`` CLI, which manages credentials in
``~/.config/tjira/config.toml`` via ``tjira profile add``.
"""

import os

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


def validate_config():
    """Verify the legacy env vars are present."""
    missing = []
    if not JIRA_DOMAIN:
        missing.append("JIRA_DOMAIN")
    if not JIRA_EMAIL:
        missing.append("JIRA_EMAIL")
    if not JIRA_API_TOKEN:
        missing.append("JIRA_API_TOKEN")

    if missing:
        raise ValueError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Source your .env (`set -a && . ./.env && set +a`) or export them "
            "manually before running."
        )

    return True
