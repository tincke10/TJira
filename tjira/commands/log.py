"""`tjira log` subcommand — register a single worklog with overlap detection."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer

from tjira.client import JiraClient
from tjira.errors import OverlapError, TjiraError, UserError, fail
from tjira.formatters import emit, log, normalize_worklog
from tjira.overlap import find_overlap, parse_time_spent
from tjira.tz import get_timezone, parse_user_datetime, to_jira_datetime


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
        force: bool = typer.Option(
            False,
            "--force",
            help="Skip the overlap pre-check and post the worklog as-is",
        ),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            if started:
                try:
                    started_dt = parse_user_datetime(started)
                except ValueError as exc:
                    raise UserError(str(exc)) from exc
            else:
                started_dt = datetime.now(tz=get_timezone())

            try:
                duration = parse_time_spent(time_spent)
            except ValueError as exc:
                raise UserError(str(exc)) from exc

            started_iso = to_jira_datetime(started_dt)
            client = JiraClient()

            if not force:
                target_end = started_dt + duration
                day = started_dt.date()
                existing = client.search_user_worklogs(day, day)
                conflict = find_overlap(started_dt, target_end, existing)
                if conflict is not None:
                    from tjira.overlap import worklog_interval
                    _, conflict_end = worklog_interval(conflict)
                    raise OverlapError(
                        "Worklog overlap with an existing entry — same user, "
                        f"issue {conflict.get('_issue_key')}",
                        payload={
                            "conflict": {
                                "issue": conflict.get("_issue_key"),
                                "worklog_id": conflict.get("id"),
                                "started": conflict.get("started"),
                                "time_spent": conflict.get("timeSpent"),
                            },
                            "suggested_start": to_jira_datetime(conflict_end),
                            "requested": {
                                "issue": issue,
                                "started": started_iso,
                                "time_spent": time_spent,
                            },
                        },
                    )

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
