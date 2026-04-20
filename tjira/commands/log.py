"""`tjira log` subcommand — register a single worklog."""

from __future__ import annotations

from typing import Optional

import typer

from tjira.client import JiraClient
from tjira.errors import TjiraError, UserError, fail
from tjira.formatters import emit, log, normalize_worklog
from tjira.tz import parse_user_datetime, to_jira_datetime


def register(app: typer.Typer) -> None:
    @app.command("log", help="Register a worklog on an issue")
    def log_cmd(
        issue: str = typer.Argument(..., help="Issue key (e.g. PROJ-123)"),
        time_spent: str = typer.Argument(..., help='Time spent (e.g. "2h", "1h 30m", "45m")'),
        started: Optional[str] = typer.Argument(
            None,
            help='Optional date/time (e.g. "2026-04-20" or "2026-04-20 09:00")',
        ),
        comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Worklog comment"),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            started_iso: Optional[str] = None
            if started:
                try:
                    dt = parse_user_datetime(started)
                except ValueError as exc:
                    raise UserError(str(exc)) from exc
                started_iso = to_jira_datetime(dt)

            client = JiraClient()
            log(f"Logging {time_spent} on {issue}...")
            result = client.add_worklog(issue, time_spent, started_iso, comment)
            emit(
                normalize_worklog(result),
                as_json=json_out,
                human_fn=lambda d: print(
                    f"OK: Worklog registered (ID: {d.get('id')}, {d.get('time_spent')})"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)
