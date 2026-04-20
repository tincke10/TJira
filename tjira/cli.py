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

import typer

from tjira import __version__
from tjira.commands import doctor as doctor_cmd
from tjira.commands import issue as issue_cmd
from tjira.commands import list_cmd
from tjira.commands import log as log_cmd
from tjira.commands import worklog as worklog_cmd

app = typer.Typer(
    name="tjira",
    help="Unified CLI to manage Jira via REST, with AI-friendly JSON output.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tjira {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """CLI root — run `tjira --help` to list subcommands."""


# Register subcommands
log_cmd.register(app)
issue_cmd.register(app)
list_cmd.register(app)
worklog_cmd.register(app)
doctor_cmd.register(app)


if __name__ == "__main__":
    app()
