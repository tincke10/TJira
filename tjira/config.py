"""Centralized configuration for the CLI.

Credentials are read from environment variables (or `.env` in cwd).
Timezone handling lives in `tjira.tz`.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from tjira.errors import UserError

load_dotenv()

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


def validate_config() -> None:
    """Verify that the minimum required credentials are present.

    Raises:
        UserError: if any required variable is missing. The payload includes
            the list of missing variables so an agent can act on the
            structured error.
    """
    missing = [
        name
        for name, value in (
            ("JIRA_DOMAIN", JIRA_DOMAIN),
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        )
        if not value
    ]
    if missing:
        raise UserError(
            f"Missing environment variables: {', '.join(missing)}",
            payload={"missing": missing},
        )
