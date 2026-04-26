"""`tjira doctor` subcommand — setup verification.

Runs configuration and connectivity checks, and reports them in human or JSON
format. Useful for onboarding and for agents (Claude, CI) that need to
validate the environment is ready before running business commands.

Checks:
    1. An active Jira profile is configured and resolvable
    2. ``profile.domain`` has a plausible shape (host only, no scheme)
    3. ``JIRA_TIMEZONE`` is a valid IANA zone (if set)
    4. Live call to ``GET /myself`` to validate credentials

Exit codes:
    0 -> all checks passed
    1 -> at least one check failed (config or credentials)
"""

from __future__ import annotations

import os
from typing import Any

import typer

from tjira import __version__
from tjira.config import resolve_profile
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit
from tjira.profiles import Profile

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]


CheckResult = dict[str, Any]


def register(app: typer.Typer) -> None:
    @app.command("doctor", help="Verify configuration, credentials and connectivity")
    def doctor_cmd(
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            checks = _run_checks()
            data = {
                "version": __version__,
                "all_passed": all(c["passed"] for c in checks),
                "checks": checks,
            }
            emit(data, as_json=json_out, human_fn=_print_human)
            if not data["all_passed"]:
                raise UserError(
                    "One or more checks failed",
                    payload={"failed": [c["name"] for c in checks if not c["passed"]]},
                )
        except TjiraError as err:
            fail(err, as_json=json_out)


def _run_checks() -> list[CheckResult]:
    """Run the checks independently; never aborts on the first failure."""
    profile_check, profile = _check_profile()
    return [
        profile_check,
        _check_domain_shape(profile),
        _check_timezone(),
        _check_jira_connectivity(profile),
    ]


def _check_profile() -> tuple[CheckResult, Profile | None]:
    try:
        profile = resolve_profile()
    except UserError as exc:
        return (
            {
                "name": "profile",
                "passed": False,
                "detail": exc.message,
                **exc.payload,
            },
            None,
        )
    return (
        {
            "name": "profile",
            "passed": True,
            "detail": f"Active profile: {profile.name} ({profile.email})",
            "profile": profile.name,
        },
        profile,
    )


def _check_domain_shape(profile: Profile | None) -> CheckResult:
    if profile is None:
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": "Cannot validate domain without a resolvable profile",
        }
    domain = profile.domain
    if domain.startswith(("http://", "https://")) or domain.endswith("/"):
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": (
                "Profile domain must be the host only, without scheme or trailing slash "
                "(e.g. 'your-company.atlassian.net')"
            ),
            "value": domain,
        }
    return {
        "name": "domain_shape",
        "passed": True,
        "detail": f"Host: {domain}",
    }


def _check_timezone() -> CheckResult:
    tz_name = os.getenv("JIRA_TIMEZONE")
    if not tz_name:
        return {
            "name": "timezone",
            "passed": True,
            "detail": "JIRA_TIMEZONE unset — the system local timezone will be used",
        }
    if ZoneInfo is None:
        return {
            "name": "timezone",
            "passed": False,
            "detail": "zoneinfo is not available in this Python version",
        }
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return {
            "name": "timezone",
            "passed": False,
            "detail": f"Invalid IANA timezone: '{tz_name}'",
            "value": tz_name,
        }
    return {
        "name": "timezone",
        "passed": True,
        "detail": f"Valid timezone: {tz_name}",
    }


def _check_jira_connectivity(profile: Profile | None) -> CheckResult:
    if profile is None:
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": "Cannot validate connectivity without a resolvable profile",
        }
    try:
        from tjira.client import JiraClient
        client = JiraClient(profile=profile)
        me = client.get_myself()
    except APIError as exc:
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": f"Jira API did not respond OK: {exc.message}",
            **exc.payload,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": f"Unexpected error contacting Jira: {exc}",
        }
    return {
        "name": "jira_connectivity",
        "passed": True,
        "detail": f"Authenticated as {me.get('displayName')} ({me.get('emailAddress')})",
        "account_id": me.get("accountId"),
    }


def _print_human(data: dict) -> None:
    print(f"tjira {data['version']} — health check\n")
    for check in data["checks"]:
        icon = "OK   " if check["passed"] else "FAIL "
        print(f"  [{icon}] {check['name']:<20} {check['detail']}")
    print()
    if data["all_passed"]:
        print("All checks passed — your setup is ready.")
    else:
        print("One or more checks failed. Review the details above.")
