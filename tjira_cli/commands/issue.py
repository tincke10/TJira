"""Subcomando `tjira-cli issue` — create / update / get / transition."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from tjira_cli.client import JiraClient
from tjira_cli.errors import APIError, TjiraError, UserError, fail
from tjira_cli.formatters import (
    emit,
    log,
    normalize_issue,
    normalize_transition,
    print_issue_detail,
    print_transitions_table,
)


def register(app: typer.Typer) -> None:
    issue_app = typer.Typer(help="Gestión de issues (create, update, get, transitions)")
    app.add_typer(issue_app, name="issue")

    @issue_app.command("get", help="Obtener detalle de una issue")
    def issue_get(
        key: str = typer.Argument(..., help="Clave de la issue (ej: PROJ-123)"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_issue(key)
            emit(normalize_issue(raw), as_json=json_out, human_fn=print_issue_detail)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @issue_app.command("create", help="Crear una nueva issue")
    def issue_create(
        project: str = typer.Argument(..., help="Clave del proyecto (ej: PROJ)"),
        summary: str = typer.Argument(..., help="Título de la issue"),
        type_: str = typer.Option("Task", "--type", "-t", help="Tipo (Task, Bug, Story, Epic)"),
        description: Optional[str] = typer.Option(None, "--desc", "-d", help="Descripción"),
        assign: Optional[str] = typer.Option(None, "--assign", "-a", help="accountId o 'me'"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            assignee_id: str | None = None
            if assign:
                assignee_id = _resolve_assignee(client, assign)

            log(f"Creando {type_} en {project}...")
            result = client.create_issue(
                project_key=project,
                summary=summary,
                issue_type=type_,
                description=description,
                assignee_id=assignee_id,
            )
            data = {
                "key": result.get("key"),
                "id": result.get("id"),
                "url": f"{client.browse_url}/{result.get('key')}",
                "summary": summary,
                "type": type_,
            }
            emit(
                data,
                as_json=json_out,
                human_fn=lambda d: (
                    print(f"OK: {d['key']} - {d['summary']}") or print(f"URL: {d['url']}")
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    @issue_app.command("update", help="Actualizar una issue existente")
    def issue_update(
        key: str = typer.Argument(..., help="Clave de la issue"),
        summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Nuevo título"),
        status: Optional[str] = typer.Option(None, "--status", help="Nuevo estado (nombre de transición)"),
        assign: Optional[str] = typer.Option(None, "--assign", "-a", help="accountId o 'me'"),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Nueva descripción"),
        desc_file: Optional[Path] = typer.Option(
            None, "--desc-file", help="Descripción desde archivo de texto"
        ),
        comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Añadir comentario"),
        attach: Optional[List[Path]] = typer.Option(None, "--attach", help="Archivos a adjuntar"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            changes: dict[str, object] = {}

            if summary:
                client.update_issue(key, {"summary": summary})
                changes["summary"] = summary

            if status:
                transitions = client.get_transitions(key)
                match = next(
                    (t for t in transitions if (t.get("name") or "").lower() == status.lower()),
                    None,
                )
                if not match:
                    raise UserError(
                        f"Transición '{status}' no disponible",
                        payload={
                            "available": [t.get("name") for t in transitions],
                        },
                    )
                client.transition_issue(key, match["id"])
                changes["status"] = status

            if assign:
                assignee_id = _resolve_assignee(client, assign)
                client.assign_issue(key, assignee_id)
                changes["assignee"] = assignee_id

            if description:
                client.update_description(key, description)
                changes["description"] = "updated"
            elif desc_file:
                if not desc_file.exists():
                    raise UserError(f"Archivo no encontrado: {desc_file}")
                client.update_description(key, desc_file.read_text(encoding="utf-8"))
                changes["description"] = f"updated from {desc_file}"

            if comment:
                result = client.add_comment(key, comment)
                changes["comment_id"] = result.get("id")

            if attach:
                attached: list[str] = []
                for file_path in attach:
                    if not file_path.exists():
                        raise UserError(f"Archivo no encontrado: {file_path}")
                    result = client.add_attachment(key, str(file_path))
                    attached.extend(a.get("filename", "?") for a in result)
                changes["attachments"] = attached

            if not changes:
                raw = client.get_issue(key)
                emit(normalize_issue(raw), as_json=json_out, human_fn=print_issue_detail)
                return

            data = {"key": key, "changes": changes}
            emit(
                data,
                as_json=json_out,
                human_fn=lambda d: (
                    print(f"OK: {d['key']} actualizado")
                    or [print(f"  {k}: {v}") for k, v in d["changes"].items()]
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    @issue_app.command("transitions", help="Listar transiciones disponibles de una issue")
    def issue_transitions(
        key: str = typer.Argument(..., help="Clave de la issue"),
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            client = JiraClient()
            raw = client.get_transitions(key)
            items = [normalize_transition(t) for t in raw]
            emit(items, as_json=json_out, human_fn=print_transitions_table)
        except TjiraError as err:
            fail(err, as_json=json_out)


def _resolve_assignee(client: JiraClient, value: str) -> str:
    """Convierte 'me' al accountId del usuario autenticado."""
    if value.lower() == "me":
        try:
            me = client.get_myself()
        except APIError as exc:
            raise UserError("No se pudo obtener tu accountId") from exc
        account_id = me.get("accountId")
        if not account_id:
            raise UserError("Tu usuario no expone accountId")
        return account_id
    return value
