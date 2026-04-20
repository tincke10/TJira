"""`tjira doctor` subcommand — setup verification.

Runs configuration and connectivity checks, and reports them in human or JSON
format. Useful for onboarding and for agents (Claude, CI) that need to
validate the environment is ready before running business commands.

Checks:
    1. `.env` (or environment variables) with credentials present
    2. `JIRA_DOMAIN` with a plausible shape (host only, no scheme)
    3. `JIRA_TIMEZONE` is a valid IANA zone (if set)
    4. Live call to `GET /myself` to validate credentials

Exit codes:
    0 -> all checks passed
    1 -> at least one check failed (config or credentials)
"""

from __future__ import annotations

import os
from typing import Any

import typer

from tjira import __version__
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit

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
    return [
        _check_env_vars(),
        _check_domain_shape(),
        _check_timezone(),
        _check_jira_connectivity(),
    ]


def _check_env_vars() -> CheckResult:
    required = ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        return {
            "name": "env_vars",
            "passed": False,
            "detail": f"Missing variables: {', '.join(missing)}",
            "missing": missing,
        }
    return {
        "name": "env_vars",
        "passed": True,
        "detail": "All required variables are present",
    }


def _check_domain_shape() -> CheckResult:
    domain = os.getenv("JIRA_DOMAIN") or ""
    if not domain:
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": "JIRA_DOMAIN is not set",
        }
    if domain.startswith(("http://", "https://")) or domain.endswith("/"):
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": (
                "JIRA_DOMAIN must be the host only, without scheme or trailing slash "
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


def _check_jira_connectivity() -> CheckResult:
    # Deferred import: if credentials are missing, `JiraClient()` raises on init.
    missing = [n for n in ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN") if not os.getenv(n)]
    if missing:
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": "Cannot validate connectivity without complete credentials",
            "skipped_due_to": missing,
        }
    try:
        from tjira.client import JiraClient
        client = JiraClient()
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
