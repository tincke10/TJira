"""``tjira profile`` subcommand group — manage Jira credential profiles."""

from __future__ import annotations

import os
from typing import Optional

import typer

from tjira.errors import TjiraError, UserError, fail
from tjira.formatters import emit
from tjira.profiles import (
    Profile,
    ProfileStore,
    validate_domain,
    validate_profile_name,
)


_LEGACY_ENV_VARS = ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN")


def register(app: typer.Typer) -> None:
    profile_app = typer.Typer(
        name="profile",
        help="Manage Jira credential profiles.",
        no_args_is_help=True,
    )

    @profile_app.command(
        "add",
        help="Create a profile (interactive when --domain/--email/--token are omitted)",
    )
    def profile_add(
        name: str = typer.Argument(..., help="Profile name"),
        domain: Optional[str] = typer.Option(
            None, "--domain", help="Jira host (e.g. company.atlassian.net)"
        ),
        email: Optional[str] = typer.Option(None, "--email"),
        token: Optional[str] = typer.Option(None, "--token", help="API token"),
        from_env: bool = typer.Option(
            False,
            "--from-env",
            help="Read JIRA_DOMAIN/EMAIL/API_TOKEN from the current environment",
        ),
        force: bool = typer.Option(
            False, "--force", help="Overwrite an existing profile with the same name"
        ),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            validate_profile_name(name)
            if from_env:
                profile = _profile_from_env(name)
            else:
                resolved_domain = domain or typer.prompt(
                    "Jira domain (e.g. company.atlassian.net)"
                )
                validate_domain(resolved_domain)
                profile = Profile(
                    name=name,
                    domain=resolved_domain,
                    email=email or typer.prompt("Email"),
                    api_token=token or typer.prompt("API token", hide_input=True),
                )

            store = ProfileStore.load()
            store.add(profile, overwrite=force)
            became_active = store.current is None
            if became_active:
                store.set_current(name)
            store.save()

            emit(
                {"name": name, "current": store.current, "became_active": became_active},
                as_json=json_out,
                human_fn=lambda d: print(
                    f"Profile '{d['name']}' added"
                    + (" (now active)." if d["became_active"] else ".")
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    @profile_app.command("list", help="List all profiles (the active one is marked with *)")
    def profile_list(
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            store = ProfileStore.load()
            profiles = [
                {
                    "name": n,
                    "domain": store.get(n).domain,
                    "email": store.get(n).email,
                    "active": n == store.current,
                }
                for n in store.names()
            ]
            emit(
                {"current": store.current, "profiles": profiles},
                as_json=json_out,
                human_fn=_print_list_human,
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    @profile_app.command("current", help="Print the active profile name")
    def profile_current(
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            store = ProfileStore.load()
            if store.current is None:
                raise UserError(
                    "No active profile",
                    payload={
                        "hint": "Use `tjira switch <name>` or `tjira profile add <name>`",
                        "available": store.names(),
                    },
                )
            emit(store.current, as_json=json_out, human_fn=print)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @profile_app.command("rm", help="Remove a profile")
    def profile_rm(
        name: str = typer.Argument(...),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            store = ProfileStore.load()
            if not store.has(name):
                raise UserError(
                    f"Profile not found: {name}",
                    payload={"profile": name, "available": store.names()},
                )
            if not yes and not typer.confirm(f"Delete profile '{name}'?", default=False):
                return
            was_active = store.current == name
            store.remove(name)
            store.save()
            emit(
                {"removed": name, "was_active": was_active},
                as_json=json_out,
                human_fn=lambda d: print(
                    f"Profile '{d['removed']}' removed"
                    + (" — no profile is currently active." if d["was_active"] else ".")
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    app.add_typer(profile_app, name="profile")


# ====================== helpers ======================


def _profile_from_env(name: str) -> Profile:
    values = {var: os.getenv(var) for var in _LEGACY_ENV_VARS}
    missing = [var for var, val in values.items() if not val]
    if missing:
        raise UserError(
            "Missing environment variables for --from-env",
            payload={"missing": missing},
        )
    validate_domain(values["JIRA_DOMAIN"])
    return Profile(
        name=name,
        domain=values["JIRA_DOMAIN"],
        email=values["JIRA_EMAIL"],
        api_token=values["JIRA_API_TOKEN"],
    )


def _print_list_human(data: dict) -> None:
    profiles = data["profiles"]
    if not profiles:
        print("No profiles configured. Run `tjira profile add <name>` to create one.")
        return
    print(f"  {'NAME':<20} {'EMAIL':<35} DOMAIN")
    print("-" * 90)
    for p in profiles:
        marker = "* " if p["active"] else "  "
        print(f"{marker}{p['name']:<20} {p['email']:<35} {p['domain']}")
