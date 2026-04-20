"""Subcomando `tjira-cli list` — búsqueda y listados (issues, boards, sprints, filters, dashboards)."""

from __future__ import annotations

from typing import Optional

import typer

from tjira_cli.client import JiraClient
from tjira_cli.errors import TjiraError, fail
from tjira_cli.formatters import (
    emit,
    log,
    normalize_board,
    normalize_filter,
    normalize_issue,
    normalize_sprint,
    print_boards_table,
    print_filters_table,
    print_issues_table,
    print_sprints_table,
)


def register(app: typer.Typer) -> None:
    list_app = typer.Typer(help="Listar y buscar (issues, boards, sprints, filtros, dashboards)")
    app.add_typer(list_app, name="list")

    @list_app.command("issues", help="Buscar issues por proyecto/estado/asignado o JQL")
    def list_issues(
        project: Optional[str] = typer.Option(None, "--project", "-p", help="Filtrar por proyecto"),
        status: Optional[str] = typer.Option(None, "--status", "-s", help="Filtrar por estado"),
        assignee: str = typer.Option(
            "currentUser()", "--assignee", "-a", help="Filtrar por asignado"
        ),
        jql: Optional[str] = typer.Option(None, "--jql", help="JQL personalizado (ignora otros filtros)"),
        limit: int = typer.Option(20, "--limit", "-l", help="Máximo de resultados"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            if jql:
                final_jql = jql
            else:
                conditions: list[str] = []
                if project:
                    conditions.append(f"project = {project}")
                conditions.append(f"status = '{status}'" if status else "status != Done")
                if assignee:
                    conditions.append(f"assignee = {assignee}")
                final_jql = " AND ".join(conditions) + " ORDER BY updated DESC"

            log(f"Query: {final_jql}")
            raw = client.search_issues(final_jql, limit)
            data = {
                "jql": final_jql,
                "count": len(raw),
                "issues": [normalize_issue(i) for i in raw],
            }
            emit(
                data,
                as_json=json_out,
                human_fn=lambda d: print_issues_table(d["issues"]),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("boards", help="Listar boards (Scrum/Kanban)")
    def list_boards(
        project: Optional[str] = typer.Option(None, "--project", "-p", help="Filtrar por proyecto"),
        type_: Optional[str] = typer.Option(None, "--type", "-t", help="scrum o kanban"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_boards(project_key=project, board_type=type_)
            data = [normalize_board(b) for b in raw]
            emit(data, as_json=json_out, human_fn=print_boards_table)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("sprints", help="Listar sprints de un board")
    def list_sprints(
        board: int = typer.Argument(..., help="ID del board"),
        state: str = typer.Option("active", "--state", help="active, closed o future"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_board_sprints(board, state=state)
            data = [normalize_sprint(s) for s in raw]
            emit(data, as_json=json_out, human_fn=print_sprints_table)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("sprint-issues", help="Listar issues de un sprint")
    def list_sprint_issues(
        sprint: int = typer.Argument(..., help="ID del sprint"),
        limit: int = typer.Option(50, "--limit", "-l", help="Máximo de resultados"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_sprint_issues(sprint, limit)
            data = {"sprint_id": sprint, "count": len(raw), "issues": [normalize_issue(i) for i in raw]}
            emit(data, as_json=json_out, human_fn=lambda d: print_issues_table(d["issues"]))
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("board-issues", help="Listar issues de un board")
    def list_board_issues(
        board: int = typer.Argument(..., help="ID del board"),
        limit: int = typer.Option(50, "--limit", "-l", help="Máximo de resultados"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_board_issues(board, limit)
            data = {"board_id": board, "count": len(raw), "issues": [normalize_issue(i) for i in raw]}
            emit(data, as_json=json_out, human_fn=lambda d: print_issues_table(d["issues"]))
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("filters", help="Listar filtros guardados")
    def list_filters(
        name: Optional[str] = typer.Option(None, "--name", "-n", help="Filtrar por nombre"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_filters(filter_name=name)
            data = [normalize_filter(f) for f in raw]
            emit(data, as_json=json_out, human_fn=print_filters_table)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("filter-issues", help="Ejecutar un filtro guardado y listar sus issues")
    def list_filter_issues(
        filter_id: int = typer.Argument(..., help="ID del filtro"),
        limit: int = typer.Option(50, "--limit", "-l", help="Máximo de resultados"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            flt = client.get_filter(filter_id)
            raw = client.get_filter_issues(filter_id, limit)
            data = {
                "filter": normalize_filter(flt),
                "count": len(raw),
                "issues": [normalize_issue(i) for i in raw],
            }

            def _human(d: dict) -> None:
                f = d["filter"]
                print(f"Filtro: {f.get('name')}")
                print(f"JQL: {f.get('jql')}\n")
                print_issues_table(d["issues"])

            emit(data, as_json=json_out, human_fn=_human)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @list_app.command("dashboards", help="Listar dashboards disponibles")
    def list_dashboards(
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_dashboards()
            data = [{"id": d.get("id"), "name": d.get("name")} for d in raw]

            def _human(items: list[dict]) -> None:
                if not items:
                    print("No se encontraron dashboards")
                    return
                print(f"{'ID':<10} {'NOMBRE'}")
                print("-" * 50)
                for it in items:
                    print(f"{str(it.get('id') or '-'):<10} {it.get('name') or '-'}")
                print(f"\nTotal: {len(items)} dashboards")

            emit(data, as_json=json_out, human_fn=_human)
        except TjiraError as err:
            fail(err, as_json=json_out)
