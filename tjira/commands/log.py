"""Subcomando `tjira log` — registrar un worklog individual."""

from __future__ import annotations

from typing import Optional

import typer

from tjira.client import JiraClient
from tjira.errors import TjiraError, UserError, fail
from tjira.formatters import emit, log, normalize_worklog
from tjira.tz import parse_user_datetime, to_jira_datetime


def register(app: typer.Typer) -> None:
    @app.command("log", help="Registrar un worklog en una issue")
    def log_cmd(
        issue: str = typer.Argument(..., help="Clave de la issue (ej: PROJ-123)"),
        time_spent: str = typer.Argument(..., help='Tiempo trabajado (ej: "2h", "1h 30m", "45m")'),
        started: Optional[str] = typer.Argument(
            None,
            help='Fecha/hora opcional (ej: "2026-04-20" o "2026-04-20 09:00")',
        ),
        comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Comentario del worklog"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
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
            log(f"Registrando {time_spent} en {issue}...")
            result = client.add_worklog(issue, time_spent, started_iso, comment)
            emit(
                normalize_worklog(result),
                as_json=json_out,
                human_fn=lambda d: print(
                    f"OK: Worklog registrado (ID: {d.get('id')}, {d.get('time_spent')})"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)
