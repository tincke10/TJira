"""Main entry point for the `tjira` CLI.

Output conventions:
    - stdout = data (human-readable or JSON, depending on --json)
    - stderr = progress/logs/errors

Exit codes:
    0 -> OK
    1 -> User error (args, file not found, missing config)
    2 -> Jira API error (4xx/5xx, network, timeout)
"""

from __future__ import annotations

import sys

import typer

from tjira import __version__
from tjira.commands import doctor as doctor_cmd
from tjira.commands import issue as issue_cmd
from tjira.commands import list_cmd
from tjira.commands import log as log_cmd
from tjira.commands import profile as profile_cmd
from tjira.commands import switch as switch_cmd
from tjira.commands import timer as timer_cmd
from tjira.commands import worklog as worklog_cmd
from tjira.config import set_profile_override
from tjira.profiles import ProfileStore

app = typer.Typer(
    name="tjira",
    help="Unified CLI to manage Jira via REST, with AI-friendly JSON output.",
    add_completion=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tjira {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Run this command against a specific profile (overrides the active one).",
    ),
) -> None:
    """CLI root — run `tjira --help` to list subcommands or `tjira` for the dashboard."""
    set_profile_override(profile)
    if profile:
        # Opción C: warn on stderr when overriding the active profile.
        try:
            store = ProfileStore.load()
        except Exception:
            store = None
        if store is None or store.current != profile:
            print(f"[Using profile: {profile}]", file=sys.stderr, flush=True)

    if ctx.invoked_subcommand is None:
        _show_dashboard()


def _show_dashboard() -> None:
    """Render the no-args view: active profile + next steps."""
    store = ProfileStore.load()
    print(f"tjira {__version__}\n")

    if store.is_empty():
        print("No Jira profile configured.\n")
        print("Get started:")
        print("  tjira profile add <name>             # interactive setup")
        print("  tjira profile add <name> --from-env  # migrate from JIRA_DOMAIN/EMAIL/API_TOKEN")
        if sys.stdin.isatty() and sys.stdout.isatty():
            print()
            if typer.confirm("Set up a profile now?", default=True):
                _onboard_inline()
        return

    if store.current is None:
        print("No active profile selected.\n")
        print("Available profiles:")
        for name in store.names():
            print(f"  - {name}")
        print("\nRun `tjira switch <name>` to choose one.")
        return

    active = store.get_current()
    profile_count = len(store.names())
    other = profile_count - 1
    print(f"Active profile: * {active.name}")
    print(f"  Domain: {active.domain}")
    print(f"  Email:  {active.email}")
    if other > 0:
        print(f"  ({other} other profile{'s' if other > 1 else ''} configured — `tjira profile list`)")
    print("\nRun `tjira --help` for the full command list.")


def _onboard_inline() -> None:
    """Interactive first-run profile creation, triggered from the dashboard."""
    from tjira.profiles import Profile, validate_domain, validate_profile_name

    name = typer.prompt("Profile name", default="default")
    validate_profile_name(name)
    domain = typer.prompt("Jira domain (e.g. company.atlassian.net)")
    validate_domain(domain)
    profile = Profile(
        name=name,
        domain=domain,
        email=typer.prompt("Email"),
        api_token=typer.prompt("API token", hide_input=True),
    )
    store = ProfileStore.load()
    store.add(profile)
    store.set_current(name)
    store.save()
    print(f"\nProfile '{name}' created and set as active.")


# Register subcommands
log_cmd.register(app)
issue_cmd.register(app)
list_cmd.register(app)
worklog_cmd.register(app)
doctor_cmd.register(app)
profile_cmd.register(app)
switch_cmd.register(app)
timer_cmd.register(app)


if __name__ == "__main__":
    app()
