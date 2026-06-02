"""Shared validation helpers for Jira issue keys.

Used by `tjira.commands.timer`, `tjira.commands.sprint`, and `tjira.commands.board`.
"""

from __future__ import annotations

import re

from tjira.errors import UserError

# Jira issue key pattern: uppercase project key (1+ chars), dash, one or more digits.
# Examples: PROJ-1, AB-999, A-0, MYPROJECT-12345
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")


def validate_issue_key(key: str) -> None:
    """Raise :class:`~tjira.errors.UserError` (exit 1) if *key* is not a valid Jira issue key.

    A valid key matches ``^[A-Z][A-Z0-9]+-[0-9]+$``.
    """
    if not key or not ISSUE_KEY_RE.match(key):
        raise UserError(
            f"Invalid issue key: {key!r}. Expected format: PROJ-123",
            payload={"issue_key": key},
        )
