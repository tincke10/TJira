"""Formateadores dual: human (tabla/plano) vs JSON estructurado.

Regla de oro:
    - stdout = data (humano o JSON) → parseable
    - stderr = progreso/logs → no contamina el output

Los formateadores JSON devuelven estructuras estables y documentadas,
pensadas para que un agente (Claude, GPT, script) las consuma de forma
confiable. Los formateadores humanos son best-effort para terminal.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable


def emit(data: Any, *, as_json: bool, human_fn=None) -> None:
    """Imprime a stdout en el formato pedido.

    Args:
        data: Estructura ya normalizada lista para serializar como JSON.
        as_json: Si True, imprime JSON; si False, invoca `human_fn(data)`.
        human_fn: Callable que recibe `data` y imprime la versión humana.
    """
    if as_json:
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))
        return
    if human_fn is None:
        print(data)
        return
    human_fn(data)


def log(message: str) -> None:
    """Mensaje de progreso a stderr (nunca contamina stdout)."""
    print(message, file=sys.stderr)


# ==================== NORMALIZADORES ====================
# Convierten respuestas crudas de Jira en dicts/listas estables.

def normalize_issue(issue: dict) -> dict:
    """Aplana una issue de Jira a un dict predecible."""
    fields = issue.get("fields", {}) or {}
    assignee = fields.get("assignee") or {}
    status = fields.get("status") or {}
    issuetype = fields.get("issuetype") or {}
    priority = fields.get("priority") or {}

    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": fields.get("summary"),
        "type": issuetype.get("name"),
        "status": status.get("name"),
        "priority": priority.get("name"),
        "assignee": {
            "account_id": assignee.get("accountId"),
            "display_name": assignee.get("displayName"),
            "email": assignee.get("emailAddress"),
        } if assignee else None,
        "description": _extract_adf_text(fields.get("description")),
        "attachments": [
            {"id": a.get("id"), "filename": a.get("filename"), "size": a.get("size")}
            for a in (fields.get("attachment") or [])
        ],
    }


def normalize_worklog(worklog: dict) -> dict:
    """Aplana un worklog a un dict predecible."""
    author = worklog.get("author") or {}
    return {
        "id": worklog.get("id"),
        "issue_id": worklog.get("issueId"),
        "time_spent": worklog.get("timeSpent"),
        "time_spent_seconds": worklog.get("timeSpentSeconds"),
        "started": worklog.get("started"),
        "author": {
            "account_id": author.get("accountId"),
            "display_name": author.get("displayName"),
            "email": author.get("emailAddress"),
        } if author else None,
    }


def normalize_board(board: dict) -> dict:
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "type": board.get("type"),
    }


def normalize_sprint(sprint: dict) -> dict:
    return {
        "id": sprint.get("id"),
        "name": sprint.get("name"),
        "state": sprint.get("state"),
        "start_date": sprint.get("startDate"),
        "end_date": sprint.get("endDate"),
    }


def normalize_filter(flt: dict) -> dict:
    return {
        "id": flt.get("id"),
        "name": flt.get("name"),
        "jql": flt.get("jql"),
        "owner": (flt.get("owner") or {}).get("displayName"),
    }


def normalize_transition(transition: dict) -> dict:
    return {
        "id": transition.get("id"),
        "name": transition.get("name"),
        "to": (transition.get("to") or {}).get("name"),
    }


def _extract_adf_text(adf: dict | None) -> str | None:
    """Extrae texto plano de un documento ADF (Atlassian Document Format)."""
    if not adf or not isinstance(adf, dict):
        return None
    chunks: list[str] = []
    for block in adf.get("content", []) or []:
        for item in block.get("content", []) or []:
            if item.get("type") == "text":
                chunks.append(item.get("text", ""))
        chunks.append("\n")
    text = "".join(chunks).strip()
    return text or None


# ==================== HUMAN PRINTERS ====================

def print_issues_table(issues: Iterable[dict]) -> None:
    issues = list(issues)
    if not issues:
        print("No se encontraron tareas")
        return
    print(f"{'KEY':<15} {'TIPO':<10} {'ESTADO':<15} {'TITULO'}")
    print("-" * 80)
    for it in issues:
        key = (it.get("key") or "-")[:15]
        tipo = (it.get("type") or "-")[:10]
        estado = (it.get("status") or "-")[:15]
        titulo = (it.get("summary") or "-")[:45]
        print(f"{key:<15} {tipo:<10} {estado:<15} {titulo}")
    print(f"\nTotal: {len(issues)} tareas")


def print_issue_detail(issue: dict) -> None:
    print(f"Issue: {issue.get('key')}")
    print(f"  Titulo: {issue.get('summary')}")
    print(f"  Tipo: {issue.get('type')}")
    print(f"  Estado: {issue.get('status')}")
    assignee = issue.get("assignee")
    print(f"  Asignado: {assignee['display_name'] if assignee else 'Sin asignar'}")
    desc = issue.get("description")
    if desc:
        print("  Descripcion:")
        for line in desc.splitlines():
            print(f"    {line}")
    attachments = issue.get("attachments") or []
    if attachments:
        print(f"  Adjuntos ({len(attachments)}):")
        for a in attachments:
            size_kb = (a.get("size") or 0) // 1024
            print(f"    - {a.get('filename')} ({size_kb}KB)")


def print_boards_table(boards: Iterable[dict]) -> None:
    boards = list(boards)
    if not boards:
        print("No se encontraron boards")
        return
    print(f"{'ID':<8} {'TIPO':<10} {'NOMBRE'}")
    print("-" * 60)
    for b in boards:
        print(f"{str(b.get('id') or '-'):<8} {(b.get('type') or '-'):<10} {b.get('name') or '-'}")
    print(f"\nTotal: {len(boards)} boards")


def print_sprints_table(sprints: Iterable[dict]) -> None:
    sprints = list(sprints)
    if not sprints:
        print("No se encontraron sprints")
        return
    print(f"{'ID':<8} {'ESTADO':<10} {'NOMBRE'}")
    print("-" * 60)
    for s in sprints:
        print(f"{str(s.get('id') or '-'):<8} {(s.get('state') or '-'):<10} {s.get('name') or '-'}")
    print(f"\nTotal: {len(sprints)} sprints")


def print_filters_table(filters_: Iterable[dict]) -> None:
    filters_ = list(filters_)
    if not filters_:
        print("No se encontraron filtros")
        return
    print(f"{'ID':<8} {'NOMBRE':<35} {'JQL'}")
    print("-" * 100)
    for f in filters_:
        name = (f.get("name") or "-")[:35]
        jql = (f.get("jql") or "-")[:50]
        print(f"{str(f.get('id') or '-'):<8} {name:<35} {jql}")
    print(f"\nTotal: {len(filters_)} filtros")


def print_transitions_table(transitions: Iterable[dict]) -> None:
    transitions = list(transitions)
    if not transitions:
        print("No hay transiciones disponibles")
        return
    print("Transiciones disponibles:")
    for t in transitions:
        to = t.get("to") or "-"
        print(f"  [{t.get('id')}] {t.get('name')} -> {to}")
