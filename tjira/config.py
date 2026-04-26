"""Resolve the active Jira profile for runtime use.

This module bridges the user-facing ``--profile`` flag and the underlying
:class:`~tjira.profiles.ProfileStore`. Commands and clients that need
credentials should call :func:`resolve_profile` rather than reading any
environment variable.

The previous environment-variable / ``.env`` based configuration was removed
in the multi-profile rewrite — see CHANGELOG and ``tjira profile add --help``
for the migration path.
"""

from __future__ import annotations

from tjira.errors import UserError
from tjira.profiles import Profile, ProfileStore

_override: str | None = None


def set_profile_override(name: str | None) -> None:
    """Record the ``--profile`` flag value for the current invocation."""
    global _override
    _override = name or None


def get_profile_override() -> str | None:
    return _override


def resolve_profile() -> Profile:
    """Return the profile to use for this invocation.

    Resolution order:
        1. The override set via :func:`set_profile_override` (``--profile X``).
        2. The active profile recorded in the TOML store.

    Raises:
        UserError: when no profile can be resolved. The payload includes a
            ``hint`` suggesting the next CLI command to run.
    """
    store = ProfileStore.load()

    if _override:
        return store.get(_override)

    current = store.get_current()
    if current is not None:
        return current

    if store.is_empty():
        raise UserError(
            "No Jira profile configured.",
            payload={
                "hint": "Run `tjira profile add <name>` to create one.",
                "config_path": str(store.path),
            },
        )

    raise UserError(
        "No active profile selected.",
        payload={
            "hint": "Run `tjira switch <name>` to choose one.",
            "available": store.names(),
        },
    )


def has_any_profile() -> bool:
    """Return ``True`` when at least one profile is configured.

    Used by onboarding flows that prompt the user to create a profile when the
    store is empty.
    """
    return not ProfileStore.load().is_empty()
