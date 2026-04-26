"""Multi-profile credential storage for TJira.

Profiles are persisted in a single TOML file at
``$XDG_CONFIG_HOME/tjira/config.toml`` (defaults to
``~/.config/tjira/config.toml``).

Schema::

    current_profile = "work"

    [profiles.work]
    domain = "company.atlassian.net"
    email = "you@company.com"
    api_token = "ATATT..."

    [profiles.personal]
    domain = "personal.atlassian.net"
    email = "you@gmail.com"
    api_token = "ATATT..."

The file is written with ``0600`` permissions so the API tokens — stored in
plaintext — are at least not readable by other users on the host.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from tjira.errors import UserError

_REQUIRED_PROFILE_FIELDS = ("domain", "email", "api_token")
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Any of these in a host string can hijack the request target via URL parsing
# rules (e.g. "real.atlassian.net@evil.com" → urllib resolves `evil.com`).
_INVALID_DOMAIN_CHARS = frozenset("/?#@\\\"'\t\n\r ")


def validate_profile_name(name: str) -> None:
    """Reject names that aren't simple identifiers.

    Raises:
        UserError: when the name is empty or contains characters outside
            ``[A-Za-z0-9._-]``, or starts with ``.``/``-``/``_``.
    """
    if not isinstance(name, str) or not _PROFILE_NAME_RE.match(name):
        raise UserError(
            "Profile name must start with a letter or digit and contain only "
            "letters, digits, dots, dashes, or underscores.",
            payload={"name": name},
        )


def validate_domain(domain: str) -> None:
    """Reject host strings that look like URLs or carry path/auth/whitespace.

    A valid Jira host is a bare hostname like ``company.atlassian.net``.
    Anything beyond letters/digits/dots/dashes/colons can change the request
    target via URL parsing and leak the API token to a different host.

    Raises:
        UserError: when the domain is empty, padded with whitespace, or
            contains a scheme, path, query, fragment, userinfo, or whitespace.
    """
    if not isinstance(domain, str) or not domain or domain.strip() != domain:
        raise UserError(
            "Domain must be a non-empty bare host with no surrounding whitespace.",
            payload={"domain": domain},
        )
    if any(ch in domain for ch in _INVALID_DOMAIN_CHARS):
        raise UserError(
            "Domain must be a bare host (e.g. company.atlassian.net) — no "
            "scheme, path, query, fragment, userinfo, or whitespace.",
            payload={"domain": domain},
        )


@dataclass(frozen=True, slots=True)
class Profile:
    """A single Jira credential set, identified by ``name``."""

    name: str
    domain: str
    email: str
    api_token: str


def default_config_path() -> Path:
    """Resolve the path to the TOML config, honoring ``$XDG_CONFIG_HOME``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "tjira" / "config.toml"


class ProfileStore:
    """In-memory view of the TOML config, with explicit save."""

    def __init__(
        self,
        profiles: dict[str, Profile] | None = None,
        current: str | None = None,
        path: Path | None = None,
    ) -> None:
        self._profiles: dict[str, Profile] = dict(profiles or {})
        self._current: str | None = current
        self._path: Path = path or default_config_path()

    # ---------- persistence ----------

    @classmethod
    def load(cls, path: Path | None = None) -> "ProfileStore":
        """Load the store from disk.

        Returns an empty store when the config file does not exist. Raises
        :class:`UserError` when the file is present but malformed or any
        profile section is missing required fields.
        """
        resolved = path or default_config_path()
        if not resolved.exists():
            return cls(path=resolved)

        try:
            with resolved.open("rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise UserError(
                f"Malformed TOML in {resolved}: {exc}",
                payload={"path": str(resolved)},
            ) from exc

        profiles: dict[str, Profile] = {}
        for name, section in (data.get("profiles") or {}).items():
            if not isinstance(section, dict):
                raise UserError(
                    f"Profile '{name}' must be a TOML table",
                    payload={"profile": name, "path": str(resolved)},
                )
            missing = [field for field in _REQUIRED_PROFILE_FIELDS if not section.get(field)]
            if missing:
                raise UserError(
                    f"Profile '{name}' is missing required fields",
                    payload={
                        "profile": name,
                        "missing": missing,
                        "path": str(resolved),
                    },
                )
            profiles[name] = Profile(
                name=name,
                domain=section["domain"],
                email=section["email"],
                api_token=section["api_token"],
            )

        current = data.get("current_profile") or None
        if current is not None and current not in profiles:
            # Defensive: a stale current_profile pointer should not crash the CLI.
            current = None

        return cls(profiles=profiles, current=current, path=resolved)

    def save(self) -> None:
        """Persist atomically to ``self.path`` with ``0600`` permissions.

        Writes to a sibling tempfile and renames over the target so a crash
        mid-write cannot corrupt the only credential store on disk. The leaf
        directory is locked down to ``0700`` so the file's existence is hidden
        from other users on the host (defense in depth — the file itself is
        already ``0600``).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass  # best effort — never fail save() over directory perms

        payload: dict[str, object] = {}
        if self._current:
            payload["current_profile"] = self._current
        if self._profiles:
            payload["profiles"] = {
                name: {
                    "domain": prof.domain,
                    "email": prof.email,
                    "api_token": prof.api_token,
                }
                for name, prof in sorted(self._profiles.items())
            }

        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=".tjira-config-",
            suffix=".toml.tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                tomli_w.dump(payload, fh)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    # ---------- read ----------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def current(self) -> str | None:
        return self._current

    def is_empty(self) -> bool:
        return not self._profiles

    def names(self) -> list[str]:
        return sorted(self._profiles)

    def has(self, name: str) -> bool:
        return name in self._profiles

    def get(self, name: str) -> Profile:
        """Return the profile by name. Raises :class:`UserError` if missing."""
        try:
            return self._profiles[name]
        except KeyError:
            raise UserError(
                f"Profile not found: {name}",
                payload={"profile": name, "available": self.names()},
            ) from None

    def get_current(self) -> Profile | None:
        """Return the active profile, or ``None`` if none is set."""
        return self._profiles[self._current] if self._current else None

    # ---------- write ----------

    def add(self, profile: Profile, *, overwrite: bool = False) -> None:
        """Add a profile. Raises :class:`UserError` on conflict unless ``overwrite``."""
        if profile.name in self._profiles and not overwrite:
            raise UserError(
                f"Profile already exists: {profile.name}",
                payload={"profile": profile.name},
            )
        self._profiles[profile.name] = profile

    def remove(self, name: str) -> None:
        """Remove a profile. Clears ``current`` if it pointed to ``name``."""
        if name not in self._profiles:
            raise UserError(
                f"Profile not found: {name}",
                payload={"profile": name, "available": self.names()},
            )
        del self._profiles[name]
        if self._current == name:
            self._current = None

    def set_current(self, name: str) -> None:
        """Set the active profile. Raises :class:`UserError` if the name is unknown."""
        if name not in self._profiles:
            raise UserError(
                f"Profile not found: {name}",
                payload={"profile": name, "available": self.names()},
            )
        self._current = name
